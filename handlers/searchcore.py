# ═══════════════════════════════════════════════════════════════════════════════
#  ⚡ TRINITY MODS · TRINITY AUTOFILTER
#  Search core — auto-filter engine, result pagination, lang/quality/season/episode
#  filters, spell-check, /stream link generator and the master callback router.
#  ─────────────────────────────────────────────────────────────────────────────
#  Developed & maintained by Trinity Mods (@trinityXmods)
#  GitHub   : github.com/Trinity-Mods
#  Source   : github.com/Trinity-Mods/Auto-Filter-Bot
#  Telegram : t.me/trinityXmods
#  🚫 Credit is license-locked — see brand.py. Please keep this header intact.
# ═══════════════════════════════════════════════════════════════════════════════
"""
This is the heart of the bot. It turns a plain text message ("avengers 1080p")
into a paginated list of cached files, with optional IMDB poster captions and
language / quality / season / episode refinement keyboards.

Public surface used elsewhere:
    • auto_filter(client, message, spoll=False)  — imported by handlers.commandcenter
    • BUTTONS                                     — in-memory key→query map (bounded)
    • lock                                        — shared asyncio.Lock for bulk deletes

Everything else registers itself on Pyrogram's `Client` through the smart-plugins
loader (@Client.on_message / @Client.on_callback_query) exactly like the original.
"""

import ast
import math
import random
import asyncio
import logging
from collections import OrderedDict
from datetime import datetime, timedelta
from urllib.parse import quote_plus

import pytz
# rapidfuzz (MIT) replaces fuzzywuzzy + python-Levenshtein for spell-check ranking.
from rapidfuzz import process, fuzz

from pyrogram import Client, filters, enums
from pyrogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    InputMediaPhoto,
)
from pyrogram.errors import (
    FloodWait,
    UserIsBlocked,
    MessageNotModified,
    PeerIdInvalid,
    MessageIdInvalid,
    MessageDeleteForbidden,
    QueryIdInvalid,
)
from pyrogram.errors.exceptions.bad_request_400 import (
    MediaEmpty,
    PhotoInvalidDimensions,
    WebpageMediaEmpty,
)

# ── Trinity import contract (config/phrases/toolbox/vault/reactor/brand) ──────
from config import *
from phrases import phrases
from toolbox import (
    temp,
    get_settings,
    save_group_settings,
    get_size,
    get_poster,
    is_subscribed,
    is_req_subscribed,
    get_shortlink,
    stream_site,
    get_seconds,
    get_text,
    broadcast_messages,
    extract_user,
    get_file_id,
    imdb,  # Cinemagoer instance (blocking — always wrap in asyncio.to_thread)
)
from vault.media_index import (
    Media,
    get_search_results,
    get_file_details,
    get_bad_files,
    get_all_files,
    save_file,
    unpack_new_file_id,
)
from vault.registry import db
from vault.links import (
    active_connection,
    all_connections,
    delete_connection,
    if_active,
    make_active,
    make_inactive,
    add_connection,
)
from vault.referrals import referrals, sdb
from reactor.client import app, clients, loads
from reactor.stream.media import get_name, get_hash, get_media_file_size
from brand import inject_repo_button, repo_button

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
#  Module-level shared state
# ═══════════════════════════════════════════════════════════════════════════════

# Shared lock used by bulk file-deletion callbacks (and importable by siblings).
lock = asyncio.Lock()

# A bounded {key: search_query} map. Pagination callbacks only carry a short key in
# their callback_data (Telegram caps it at 64 bytes), so the real query string is
# parked here. FIX vs original: the old plain-dict grew forever; we cap it.
_BUTTONS_MAX = 500


class _BoundedButtons(OrderedDict):
    """An LRU-ish dict that evicts the oldest entry once it exceeds the cap.

    Behaves like the original `BUTTONS` plain dict for callers (get/set/`in`),
    but can never grow unbounded — every insert ages out the least-recently-set
    key when we are over capacity.
    """

    def __setitem__(self, key, value):
        if key in self:
            # Refresh recency so active searches survive eviction.
            self.move_to_end(key)
        super().__setitem__(key, value)
        while len(self) > _BUTTONS_MAX:
            # popitem(last=False) drops the oldest inserted/used entry.
            self.popitem(last=False)


# Public name kept identical to the original module.
BUTTONS = _BoundedButtons()

# Timezone-aware "now" helper — used for the "result in N seconds" stopwatch.
_TZ = pytz.timezone(TIMEZONE)


def _now_time():
    """Current wall-clock time() in the configured timezone."""
    return datetime.now(_TZ).time()


def _elapsed_seconds(start_time):
    """Seconds elapsed between an earlier .time() snapshot and now (2dp string)."""
    end_time = _now_time()
    delta = (
        timedelta(
            hours=end_time.hour,
            minutes=end_time.minute,
            seconds=end_time.second + end_time.microsecond / 1_000_000,
        )
        - timedelta(
            hours=start_time.hour,
            minutes=start_time.minute,
            seconds=start_time.second + start_time.microsecond / 1_000_000,
        )
    )
    return "{:.2f}".format(delta.total_seconds())


# Words/patterns stripped from a raw query before searching the DB.
_FILLER_WORDS = [
    "in", "upload", "series", "full", "horror", "thriller", "mystery", "print",
    "file", "send", "chahiye", "chiye", "movi", "movie", "bhejo", "dijiye",
    "jaldi", "hd", "bollywood", "hollywood", "south", "karo",
]
_FILLER_REGEX = (
    r"\b(pl(i|e)*?(s|z+|ease|se|ese|(e+)s(e)?)|((send|snd|giv(e)?|gib)(\sme)?)"
    r"|movie(s)?|new|latest|bro|bruh|broh|helo|that|find|dubbed|link|venum"
    r"|iruka|pannunga|pannungga|anuppunga|anupunga|anuppungga|anupungga|film"
    r"|undo|kitti|kitty|tharu|kittumo|kittum|movie|any(one)|with\ssubtitle(s)?)"
)

import re  # placed here so the regex constants above read top-down


def _clean_query(raw):
    """Normalise a user message into a clean search term (filler words removed)."""
    text = raw.lower()
    kept = [tok for tok in text.split(" ") if tok not in _FILLER_WORDS]
    search = " ".join(kept)
    search = re.sub(_FILLER_REGEX, "", search, flags=re.IGNORECASE)
    search = re.sub(r"\s+", " ", search).strip()
    return search.replace("-", " ").replace(":", "")


async def _schedule_auto_delete(settings, *messages):
    """Fire-and-forget auto-delete.

    FIX (vs original): the original blocked the handler with an inline
    `await asyncio.sleep(600)` and used a magic 600. We now:
      • honour the per-group `auto_delete` toggle,
      • use config.AUTO_DELETE_TIME instead of a magic number,
      • run the wait+delete in a detached task so the handler returns instantly,
      • swallow only the specific "already gone / not allowed" delete errors.
    """
    try:
        enabled = settings.get("auto_delete", True)
    except AttributeError:
        enabled = True
    if not enabled:
        return

    async def _worker():
        await asyncio.sleep(AUTO_DELETE_TIME)
        for m in messages:
            if not m:
                continue
            try:
                await m.delete()
            except (MessageIdInvalid, MessageDeleteForbidden):
                pass
            except Exception as exc:  # never let cleanup crash the loop
                logger.debug("auto-delete failed: %s", exc)

    asyncio.create_task(_worker())


# ═══════════════════════════════════════════════════════════════════════════════
#  Streaming — /stream command + "streaming#..." inline button
# ═══════════════════════════════════════════════════════════════════════════════

@Client.on_callback_query(filters.regex(r"^streaming"))
async def stream_download(bot, query):
    """Generate watch/download links for a file chosen from a results keyboard."""
    try:
        _, file_id, grp_id = query.data.split("#", 2)
        user_id = query.from_user.id
        settings = await get_settings(int(grp_id))
        username = query.from_user.mention

        # Cache the media into BIN_CHANNEL so it gets a stable message id for links.
        msg = await bot.send_cached_media(chat_id=BIN_CHANNEL, file_id=file_id)

        online = f"{URL}watch/{msg.id}/{quote_plus(get_name(msg))}?hash={get_hash(msg)}"
        download = f"{URL}{msg.id}/{quote_plus(get_name(msg))}?hash={get_hash(msg)}"
        non_online = await stream_site(online, grp_id)
        non_download = await stream_site(download, grp_id)

        premium = await db.has_premium_access(user_id)
        if not premium and settings.get("stream_mode", STREAM_MODE):
            # Free users in stream-mode groups get the shortened (ad) links.
            await msg.reply_text(
                text=(
                    f"••ᴜꜱᴇʀ ʟɪɴᴋ: tg://openmessage?user_id={user_id}\n\n"
                    f"•• ᴜꜱᴇʀɴᴀᴍᴇ : {username} \n\nꜱᴛʀᴇᴀᴍ ᴍᴏᴅᴇ ᴏɴ"
                ),
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("📥 ᴅᴏᴡɴʟᴏᴀᴅ 📥", url=non_download),
                    InlineKeyboardButton("🖥️ ꜱᴛʀᴇᴀᴍ 🖥️", url=non_online),
                ]]),
            )
            await query.answer(
                "🎀 ɴᴏᴛᴇ: ᴛʜᴇ ꜱᴛʀᴇᴀᴍ ᴀɴᴅ ᴅɪʀᴇᴄᴛ ᴅᴏᴡɴʟᴏᴀᴅ ꜰᴇᴀᴛᴜʀᴇꜱ ᴀʀᴇ "
                "ᴀᴠᴀɪʟᴀʙʟᴇ ᴛᴏ ᴛʜᴇ ᴘʀᴇᴍɪᴜᴍ ᴜꜱᴇʀꜱ ᴏɴʟʏ.\n\nʜᴏᴡᴇᴠᴇʀ, ʏᴏᴜ ᴄᴀɴ "
                "ꜱᴛɪʟʟ ᴡᴀᴛᴄʜ ᴀɴᴅ ᴅᴏᴡɴʟᴏᴀᴅ ᴛʜᴇ ꜰɪʟᴇꜱ ʙʏ ᴛʜᴇ ɴᴏʀᴍᴀʟ ᴀɴᴅ "
                "ᴜꜱᴜᴀʟ ᴍᴇᴛʜᴏᴅ! ✅",
                show_alert=True,
            )
            await query.edit_message_reply_markup(
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("📥 ᴅᴏᴡɴʟᴏᴀᴅ 📥", url=non_download),
                        InlineKeyboardButton("🖥️ ꜱᴛʀᴇᴀᴍ 🖥️", url=non_online),
                    ],
                    [InlineKeyboardButton("⁉️ ʜᴏᴡ ᴛᴏ ᴅᴏᴡɴʟᴏᴀᴅ ⁉️", url=STREAM_HTO)],
                ])
            )
            return

        # Premium users (or stream-mode off) get the raw, ad-free links.
        await msg.reply_text(
            text=(
                f"••ᴜꜱᴇʀ ʟɪɴᴋ: tg://openmessage?user_id={user_id}\n\n"
                f"•• ᴜꜱᴇʀɴᴀᴍᴇ : {username} \n\nꜱᴛʀᴇᴀᴍ ᴍᴏᴅᴇ ᴏꜰꜰ"
            ),
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("📥 ᴅᴏᴡɴʟᴏᴀᴅ 📥", url=download),
                InlineKeyboardButton("🖥️ ꜱᴛʀᴇᴀᴍ 🖥️", url=online),
            ]]),
        )
        await query.edit_message_reply_markup(
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("📥 ᴅᴏᴡɴʟᴏᴀᴅ 📥", url=download),
                    InlineKeyboardButton("🖥️ ꜱᴛʀᴇᴀᴍ 🖥️", url=online),
                ],
                [InlineKeyboardButton("⁉️ ᴄʟᴏsᴇ ⁉️", callback_data="close_data")],
            ])
        )
    except Exception as exc:
        logger.exception("stream_download failed: %s", exc)
        await query.answer(f"{exc}", show_alert=True)


@Client.on_message(filters.private & filters.command("stream"))
async def reply_stream(client, message):
    """/stream — reply to a video/document in PM to get watch+download links."""
    reply_message = message.reply_to_message
    user_id = message.from_user.id

    if not reply_message or not (reply_message.document or reply_message.video):
        return await message.reply_text("**Reply to a video or document.**")

    media = reply_message.document or reply_message.video

    try:
        msg = await reply_message.forward(chat_id=BIN_CHANNEL)
        await client.send_message(
            chat_id=BIN_CHANNEL,
            text=(
                f"<b>ꜱᴛʀᴇᴀᴍɪɴɢ ʟɪɴᴋ ʜᴀꜱ ʙᴇᴇɴ ɢᴇɴᴇʀᴀᴛᴇᴅ ʙʏ </b>:"
                f"{message.from_user.mention}  <code>{message.from_user.id}</code> 👁️✅"
            ),
            disable_web_page_preview=True,
        )
    except Exception as exc:
        logger.exception("reply_stream forward failed: %s", exc)
        return await message.reply_text(f"Error: {exc}")

    online = f"{URL}watch/{msg.id}/{quote_plus(get_name(msg))}?hash={get_hash(msg)}"
    download = f"{URL}{msg.id}/{quote_plus(get_name(msg))}?hash={get_hash(msg)}"
    # stream_site now requires a group id for shortener settings; PM has none, so
    # pass the user id (falls back to default shortener config).
    non_online = await stream_site(online, user_id)
    non_download = await stream_site(download, user_id)

    file_name = (
        (media.file_name or "file")
        .replace("_", " ")
        .replace(".mp4", "")
        .replace(".mkv", "")
        .replace(".", " ")
    )

    if not await db.has_premium_access(user_id) and STREAM_MODE:
        await message.reply_text(
            text=(
                f"<b>ʏᴏᴜʀ ʟɪɴᴋ ʜᴀꜱ ʙᴇᴇɴ ɢᴇɴᴇʀᴀᴛᴇᴅ !\n\n📂 Fɪʟᴇ ɴᴀᴍᴇ :</b> "
                f"<a href={CHNL_LNK}>{file_name}</a>\n\n"
                f"<b>📥 Dᴏᴡɴʟᴏᴀᴅ : {non_download}\n\n🖥WATCH  : {non_online}\n\n"
                f"⚠️ Tʜᴇ ʟɪɴᴋ ᴡɪʟʟ ɴᴏᴛ ᴇxᴘɪʀᴇ ᴜɴᴛɪʟ ᴛʜᴇ ʙᴏᴛ'ꜱ ꜱᴇʀᴠᴇʀ ɪꜱ ᴄʜᴀɴɢᴇᴅ. 🔋\n\n"
                f"🎀 ɴᴏᴛᴇ:\nᴛʜᴇ ᴀᴅꜱ-ꜰʀᴇᴇ ᴇxᴘᴇʀɪᴇɴᴄᴇ ʜᴀꜱ ʙᴇᴇɴ ʀᴇꜱᴇʀᴠᴇᴅ ꜰᴏʀ ᴛʜᴇ "
                f"ᴘʀᴇᴍɪᴜᴍ ᴜꜱᴇʀꜱ ᴇxᴄʟᴜꜱɪᴠᴇʟʏ.\n\nᴛᴏ ᴋɴᴏᴡ ᴍᴏʀᴇ, ᴄʜᴇᴄᴋ ʙᴇʟᴏᴡ!</b>"
            ),
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("📥 ᴅᴏᴡɴʟᴏᴀᴅ 📥", url=non_download),
                    InlineKeyboardButton("🖥️ ꜱᴛʀᴇᴀᴍ 🖥️", url=non_online),
                ],
                [InlineKeyboardButton("🔒 ʜᴏᴡ ᴛᴏ ᴅᴏᴡɴʟᴏᴀᴅ 🔒", url=STREAMHTO)],
                [InlineKeyboardButton("✨ ʀᴇᴍᴏᴠᴇ ᴀᴅꜱ ✨", callback_data="premium_info")],
            ]),
            disable_web_page_preview=True,
        )
    else:
        await message.reply_text(
            text=(
                f"<b>𝗬𝗼𝘂𝗿 𝗟𝗶𝗻𝗸 𝗚𝗲𝗻𝗲𝗿𝗮𝘁𝗲𝗱 !\n\n📂 Fɪʟᴇ ɴᴀᴍᴇ :</b> "
                f"<a href={CHNL_LNK}>{file_name}</a>\n\n"
                f"<b>📥 Dᴏᴡɴʟᴏᴀᴅ : {download}\n\n🖥WATCH  : {online}\n\n"
                f"⚠️ Tʜᴇ ʟɪɴᴋ ᴡɪʟʟ ɴᴏᴛ ᴇxᴘɪʀᴇ ᴜɴᴛɪʟ ᴛʜᴇ ʙᴏᴛ'ꜱ ꜱᴇʀᴠᴇʀ ɪꜱ ᴄʜᴀɴɢᴇᴅ. 🔋</b>"
            ),
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("📥 ᴅᴏᴡɴʟᴏᴀᴅ 📥", url=download),
                InlineKeyboardButton("🖥️ ꜱᴛʀᴇᴀᴍ 🖥️", url=online),
            ]]),
            disable_web_page_preview=True,
        )


# ═══════════════════════════════════════════════════════════════════════════════
#  Entry points — PM text + group text → auto_filter
# ═══════════════════════════════════════════════════════════════════════════════

@Client.on_message(filters.private & filters.text & filters.incoming)
async def pm_text(bot, message):
    """Any plain PM text becomes a search (if PM filter / premium allows it)."""
    if not await db.is_user_exist(message.from_user.id):
        await db.add_user(message.from_user.id, message.from_user.first_name)
    try:
        await message.react(emoji=random.choice(REACTION), big=True)
    except Exception as exc:  # reactions are non-critical
        logger.debug("pm reaction failed: %s", exc)

    if message.text.startswith("/") or message.text.startswith("#"):
        return

    pm_allowed = await db.get_setting("PM_FILTER", default=PM_FILTER)
    if pm_allowed or await db.has_premium_access(message.from_user.id):
        await auto_filter(bot, message)
    else:
        await message.reply_text(
            "<b>ɪꜰ ʏᴏᴜ ᴡɪꜱʜ ᴛᴏ ɢᴇᴛ ꜰɪʟᴇꜱ ɪɴ ᴛʜᴇ ʙᴏᴛ ᴛʜʀᴏᴜɢʜ 'ᴅɪʀᴇᴄᴛ ꜱᴇᴀʀᴄʜ' "
            "ɪɴ ᴛʜᴇ ʙᴏᴛ'ꜱ ᴘᴍ, ʏᴏᴜ ᴡɪʟʟ ʜᴀᴠᴇ ᴛᴏ ᴘᴜʀᴄʜᴀꜱᴇ ᴘʀᴇᴍɪᴜᴍ.\n\nʜᴏᴡᴇᴠᴇʀ, "
            "ʏᴏᴜ ᴄᴀɴ ꜱᴛɪʟʟ ɢᴇᴛ ꜰɪʟᴇꜱ ɪɴ ᴛʜᴇ ɢʀᴏᴜᴘꜱ ᴡʜᴇʀᴇ ɪ'ᴍ ᴄᴏɴɴᴇᴄᴛᴇᴅ ᴛᴏ\n\n"
            "यदि आप बॉट से मूवी लेना चाहते हैं तो आपको बॉट का प्रीमियम लेना होगा\n\n"
            "अन्यथा आप ग्रुप से मूवी ले सकते हैं.</b>",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Gʀᴏᴜᴘ Hᴇʀᴇ", url=GRP_LNK)],
                [InlineKeyboardButton("✨ʙᴜʏ ᴘʀᴇᴍɪᴜᴍ: ᴜɴʟᴏᴄᴋ ᴘᴍ ꜱᴇᴀʀᴄʜ✨",
                                      callback_data="premium_info")],
            ]),
        )


@Client.on_message(filters.group & filters.text & filters.incoming)
async def give_filter(bot, message):
    """Group text → auto_filter, gated by group verification + per-group toggle."""
    if not await db.is_user_exist(message.from_user.id):
        await db.add_user(message.from_user.id, message.from_user.first_name)
    try:
        await message.react(emoji=random.choice(REACTION), big=True)
    except Exception as exc:
        logger.debug("group reaction failed: %s", exc)

    is_verified = await db.check_group_verification(message.chat.id)
    is_rejected = await db.rejected_group(message.chat.id)
    member = await bot.get_chat_member(message.chat.id, message.from_user.id)
    owner = (
        member.status in [enums.ChatMemberStatus.ADMINISTRATOR,
                          enums.ChatMemberStatus.OWNER]
        or str(message.from_user.id) in ADMINS
    )

    if message.text.startswith("/") or message.text.startswith("#"):
        return

    if not is_rejected:
        if is_verified:
            settings = await get_settings(message.chat.id)
            if settings["auto_ffilter"]:
                await auto_filter(bot, message)
        elif owner:
            await message.reply_text(
                "Tʜɪs Gʀᴏᴜᴘ ɪs Nᴏᴛ Vᴇʀɪғɪᴇᴅ. Pʟᴇᴀsᴇ Usᴇ Tʜɪs /verify "
                "Cᴏᴍᴍᴀɴᴅ ᴛᴏ Vᴇʀɪғʏ Tʜᴇ Gʀᴏᴜᴘ."
            )
        else:
            await message.reply_text(
                " I Cᴀɴɴᴏᴛ Gɪᴠᴇ Mᴏᴠɪᴇs ɪɴ Tʜɪs Gʀᴏᴜᴘ ꜱɪɴᴄᴇ Tʜɪs Gʀᴏᴜᴘ ɪs Nᴏᴛ Vᴇʀɪғɪᴇᴅ."
            )
    elif owner:
        await message.reply_text(
            f"ʏᴏᴜʀ ɢʀᴏᴜᴘ ʜᴀs ʙᴇᴇɴ ʀᴇᴊᴇᴄᴛᴇᴅ. ᴄᴏɴᴛᴀᴄᴛ ᴍʏ ᴀᴅᴍɪɴ.\n@{SUPPORT_CHAT}"
        )
    else:
        await message.reply_text("ᴛʜɪs ɢʀᴏᴜᴘ ɪs ɴᴏᴛ ᴠᴇʀɪғɪᴇᴅ")


# ═══════════════════════════════════════════════════════════════════════════════
#  Pagination keyboard builder (shared by next_page + filter callbacks)
# ═══════════════════════════════════════════════════════════════════════════════

def _file_rows(files, single_button):
    """Build the per-file button rows (only when results aren't text-mode)."""
    if single_button:
        return []
    return [
        [InlineKeyboardButton(
            text=f"[{get_size(file.file_size)}] {file.file_name}",
            callback_data=f"files#{file.file_id}",
        )]
        for file in files
    ]


def _refine_header(req, *, lang_label="Lᴀɴɢᴜᴀɢᴇ", quality_label="Qᴜᴀʟɪᴛʏ",
                   season_label="Sᴇᴀꜱᴏɴ", episode_label="Eᴘɪsᴏᴅᴇ", key=None):
    """The 3 top rows: Send-All, Language/Quality, Season/Episode."""
    rows = []
    if key is not None:
        rows.append([InlineKeyboardButton("! Sᴇɴᴅ Aʟʟ !", callback_data=f"sendfiles#{key}")])
    rows.append([
        InlineKeyboardButton(lang_label, callback_data=f"select_lang#{req}"),
        InlineKeyboardButton(quality_label, callback_data=f"quality#{req}"),
    ])
    rows.append([
        InlineKeyboardButton(season_label, callback_data=f"seas#{req}"),
        InlineKeyboardButton(episode_label, callback_data=f"epi#{req}"),
    ])
    return rows


@Client.on_callback_query(filters.regex(r"^next"))
async def next_page(bot, query):
    """Handle the BACK / NEXT pagination buttons."""
    try:
        start_time = _now_time()
        _, req, key, offset = query.data.split("_")
        if int(req) not in [query.from_user.id, 0]:
            return await query.answer(
                phrases.ALRT_TXT.format(query.from_user.first_name), show_alert=True
            )
        try:
            offset = int(offset)
        except (TypeError, ValueError):
            offset = 0

        search = BUTTONS.get(key)
        files, n_offset, total = await get_search_results(
            query.message.chat.id, search, offset=offset, filter=True
        )
        try:
            n_offset = int(n_offset)
        except (TypeError, ValueError):
            n_offset = 0
        if not files:
            return

        settings = await get_settings(query.message.chat.id)
        temp.GETALL[key] = files
        temp.CHAT[query.from_user.id] = query.message.chat.id

        btn = _file_rows(files, settings["button"])
        # Header rows are *inserted at the top* (so build them last-first like the
        # original used .insert(0, ...)).
        for row in reversed(_refine_header(req, key=key)):
            btn.insert(0, row)

        # ── pager row ──────────────────────────────────────────────────────────
        try:
            page_size = 10 if settings["max_btn"] else int(MAX_B_TN)
        except KeyError:
            await save_group_settings(query.message.chat.id, "max_btn", True)
            page_size = 10

        if 0 < offset <= page_size:
            off_set = 0
        elif offset == 0:
            off_set = None
        else:
            off_set = offset - page_size

        pages_label = f"{math.ceil(int(offset) / page_size) + 1} / {math.ceil(total / page_size)}"
        if n_offset == 0:
            btn.append([
                InlineKeyboardButton("⌫ 𝐁𝐀𝐂𝐊", callback_data=f"next_{req}_{key}_{off_set}"),
                InlineKeyboardButton(pages_label, callback_data="pages"),
            ])
        elif off_set is None:
            btn.append([
                InlineKeyboardButton("𝐏𝐀𝐆𝐄", callback_data="pages"),
                InlineKeyboardButton(pages_label, callback_data="pages"),
                InlineKeyboardButton("𝐍𝐄𝐗𝐓 ➪", callback_data=f"next_{req}_{key}_{n_offset}"),
            ])
        else:
            btn.append([
                InlineKeyboardButton("⌫ 𝐁𝐀𝐂𝐊", callback_data=f"next_{req}_{key}_{off_set}"),
                InlineKeyboardButton(pages_label, callback_data="pages"),
                InlineKeyboardButton("𝐍𝐄𝐗𝐓 ➪", callback_data=f"next_{req}_{key}_{n_offset}"),
            ])

        if settings.get("button", SINGLE_BUTTON):
            remaining = _elapsed_seconds(start_time)
            cap = await get_text(settings, remaining, files, query, total, search)
            try:
                await query.message.edit_text(text=cap, reply_markup=InlineKeyboardMarkup(btn))
            except MessageNotModified:
                pass
        else:
            try:
                await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(btn))
            except MessageNotModified:
                pass
            await query.answer()
    except Exception as exc:
        logger.exception("next_page failed: %s", exc)
        await query.answer(f"error found out\n\n{exc}", show_alert=True)


# ═══════════════════════════════════════════════════════════════════════════════
#  Refinement filters — language / quality / season / episode
#  These four share an identical "re-run search with an appended token" shape, so
#  a single helper builds the keyboard + caption for all of them.
# ═══════════════════════════════════════════════════════════════════════════════

async def _apply_refinement(query, token, *, header_builder, empty_alert):
    """Re-run the cached search with `token` appended and rebuild the page.

    header_builder(userid, key) → the top refine rows for this filter type.
    Returns nothing; edits the message in place. `token` is "home"/"unknown"/value.
    """
    start_time = _now_time()
    movie = temp.KEYWORD.get(query.from_user.id)
    if token != "home":
        movie = f"{movie} {token}"

    files, offset, total_results = await get_search_results(
        query.message.chat.id, movie, offset=0, filter=True
    )
    if not files:
        return await query.answer(empty_alert.format(movie=movie), show_alert=True)

    settings = await get_settings(query.message.chat.id)
    key = f"{query.message.chat.id}-{query.message.id}"
    temp.GETALL[key] = files
    temp.CHAT[query.from_user.id] = query.message.chat.id

    btn = _file_rows(files, settings["button"])
    for row in reversed(header_builder(key)):
        btn.insert(0, row)

    # First-page pager row.
    if offset != "":
        BUTTONS[key] = movie
        req = query.data.split("#")[1]  # userid carried in callback data
        try:
            page_size = 10 if settings["max_btn"] else int(MAX_B_TN)
        except KeyError:
            await save_group_settings(query.message.chat.id, "max_btn", True)
            page_size = 10
        btn.append([
            InlineKeyboardButton("𝐏𝐀𝐆𝐄", callback_data="pages"),
            InlineKeyboardButton(f"1/{math.ceil(int(total_results) / page_size)}",
                                 callback_data="pages"),
            InlineKeyboardButton("𝐍𝐄𝐗𝐓 ➪", callback_data=f"next_{req}_{key}_{offset}"),
        ])
    else:
        btn.append([InlineKeyboardButton("𝐍𝐎 𝐌𝐎𝐑𝐄 𝐏𝐀𝐆𝐄𝐒 𝐀𝐕𝐀𝐈𝐋𝐀𝐁𝐋𝐄", callback_data="pages")])

    if settings.get("button", SINGLE_BUTTON):
        remaining = _elapsed_seconds(start_time)
        cap = await get_text(settings, remaining, files, query, total_results, movie)
        try:
            await query.message.edit_text(text=cap, reply_markup=InlineKeyboardMarkup(btn))
        except MessageNotModified:
            pass
    else:
        try:
            await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(btn))
        except MessageNotModified:
            pass
        await query.answer()


def _owns(query, userid):
    """True if the clicker is allowed to drive this result keyboard."""
    return int(userid) in [query.from_user.id, 0]


# ── Language ─────────────────────────────────────────────────────────────────
@Client.on_callback_query(filters.regex(r"^lang"))
async def language_check(bot, query):
    try:
        _, userid, language = query.data.split("#")
        if not _owns(query, userid):
            return await query.answer(
                phrases.ALRT_TXT.format(query.from_user.first_name), show_alert=True
            )
        if language == "unknown":
            return await query.answer(
                "Sᴇʟᴇᴄᴛ ᴀɴʏ ʟᴀɴɢᴜᴀɢᴇ ғʀᴏᴍ ᴛʜᴇ ʙᴜᴛᴛᴏɴs ʙᴇʟᴏᴡ!", show_alert=True
            )

        def header(key):
            return _refine_header(
                userid, key=key, lang_label="! Sᴇʟᴇᴄᴛ Aɢᴀɪɴ !",
            )

        await _apply_refinement(
            query, language, header_builder=header,
            empty_alert="Sᴏʀʀʏ ᴘᴏᴏᴋɪᴇ, Nᴏ ғɪʟᴇs ᴡᴇʀᴇ ғᴏᴜɴᴅ ғᴏʀ ʏᴏᴜʀ ᴏ̨ᴜᴇʀʏ <i>'{movie}'</i>.",
        )
    except Exception as exc:
        logger.exception("language_check failed: %s", exc)
        await query.answer(f"error found out\n\n{exc}", show_alert=True)


@Client.on_callback_query(filters.regex(r"^select_lang"))
async def select_language(bot, query):
    """Show the language picker keyboard."""
    _, userid = query.data.split("#")
    if not _owns(query, userid):
        return await query.answer(
            phrases.ALRT_TXT.format(query.from_user.first_name), show_alert=True
        )
    btn = [
        [InlineKeyboardButton("Sᴇʟᴇᴄᴛ Yᴏᴜʀ Dᴇꜱɪʀᴇᴅ Lᴀɴɢᴜᴀɢᴇ ↓",
                              callback_data=f"lang#{userid}#unknown")],
        [
            InlineKeyboardButton("Eɴɢʟɪꜱʜ", callback_data=f"lang#{userid}#eng"),
            InlineKeyboardButton("Tᴀᴍɪʟ", callback_data=f"lang#{userid}#tam"),
            InlineKeyboardButton("Hɪɴᴅɪ", callback_data=f"lang#{userid}#hin"),
        ],
        [
            InlineKeyboardButton("Kᴀɴɴᴀᴅᴀ", callback_data=f"lang#{userid}#kan"),
            InlineKeyboardButton("Tᴇʟᴜɢᴜ", callback_data=f"lang#{userid}#tel"),
        ],
        [InlineKeyboardButton("Mᴀʟᴀʏᴀʟᴀᴍ", callback_data=f"lang#{userid}#mal")],
        [
            InlineKeyboardButton("Gᴜᴊᴀʀᴀᴛɪ", callback_data=f"lang#{userid}#guj"),
            InlineKeyboardButton("Mᴀʀᴀᴛʜɪ", callback_data=f"lang#{userid}#mar"),
            InlineKeyboardButton("Pᴜɴᴊᴀʙɪ", callback_data=f"lang#{userid}#pun"),
        ],
        [
            InlineKeyboardButton("Mᴜʟᴛɪ Aᴜᴅɪᴏ", callback_data=f"lang#{userid}#multi"),
            InlineKeyboardButton("Dᴜᴀʟ Aᴜᴅɪᴏ", callback_data=f"lang#{userid}#dual"),
        ],
        [InlineKeyboardButton("Gᴏ Bᴀᴄᴋ", callback_data=f"lang#{userid}#home")],
    ]
    try:
        await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(btn))
    except MessageNotModified:
        pass
    await query.answer()


# ── Quality ──────────────────────────────────────────────────────────────────
# NOTE: the *check* callback keeps the original "lusifilms" data prefix so old
# inline keyboards (and the picker below) keep routing here unchanged.
@Client.on_callback_query(filters.regex(r"^lusifilms"))
async def quality_check(bot, query):
    try:
        _, userid, quality = query.data.split("#")
        if not _owns(query, userid):
            return await query.answer(
                phrases.ALRT_TXT.format(query.from_user.first_name), show_alert=True
            )
        if quality == "unknown":
            return await query.answer(
                "Sᴇʟᴇᴄᴛ ᴀɴʏ Qᴜᴀʟɪᴛʏꜱ ғʀᴏᴍ ᴛʜᴇ ʙᴇʟᴏᴡ ʙᴜᴛᴛᴏɴs !", show_alert=True
            )

        def header(key):
            return _refine_header(
                userid, key=key, quality_label="! Sᴇʟᴇᴄᴛ Aɢᴀɪɴ !",
            )

        await _apply_refinement(
            query, quality, header_builder=header,
            empty_alert="Sᴏʀʀʏ ᴘᴏᴏᴋɪᴇ, Nᴏ ғɪʟᴇs ᴡᴇʀᴇ ғᴏᴜɴᴅ ғᴏʀ ʏᴏᴜʀ ᴏ̨ᴜᴇʀʏ {movie}.",
        )
    except Exception as exc:
        logger.exception("quality_check failed: %s", exc)
        await query.answer(f"error found out\n\n{exc}", show_alert=True)


@Client.on_callback_query(filters.regex(r"^quality"))
async def select_quality(bot, query):
    """Show the quality picker keyboard."""
    _, userid = query.data.split("#")
    if not _owns(query, userid):
        return await query.answer(
            phrases.ALRT_TXT.format(query.from_user.first_name), show_alert=True
        )
    btn = [
        [InlineKeyboardButton("Sᴇʟᴇᴄᴛ Yᴏᴜʀ Dᴇꜱɪʀᴇᴅ Qᴜᴀʟɪᴛʏꜱ ↓",
                              callback_data=f"lusifilms#{userid}#unknown")],
        [
            InlineKeyboardButton("480p", callback_data=f"lusifilms#{userid}#480p"),
            InlineKeyboardButton("720p", callback_data=f"lusifilms#{userid}#720p"),
        ],
        [
            InlineKeyboardButton("1080p", callback_data=f"lusifilms#{userid}#1080p"),
            InlineKeyboardButton("1080p HQ", callback_data=f"lusifilms#{userid}#1080p HQ"),
        ],
        [
            InlineKeyboardButton("1440p", callback_data=f"lusifilms#{userid}#1440p"),
            InlineKeyboardButton("2160p", callback_data=f"lusifilms#{userid}#2160p"),
        ],
        [InlineKeyboardButton("Gᴏ Bᴀᴄᴋ", callback_data=f"lusifilms#{userid}#home")],
    ]
    try:
        await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(btn))
    except MessageNotModified:
        pass
    await query.answer()


# ───────────────────────────  ⚡ Trinity Mods · @trinityXmods  ───────────────────────────


# ── Season ───────────────────────────────────────────────────────────────────
@Client.on_callback_query(filters.regex(r"^seasons"))
async def seasons_check(bot, query):
    try:
        _, userid, seasons = query.data.split("#")
        if not _owns(query, userid):
            return await query.answer(
                phrases.ALRT_TXT.format(query.from_user.first_name), show_alert=True
            )
        if seasons == "unknown":
            return await query.answer(
                "Sᴇʟᴇᴄᴛ ᴀɴʏ Sᴇᴀꜱᴏɴ ғʀᴏᴍ ᴛʜᴇ ʙᴜᴛᴛᴏɴs ʙᴇʟᴏᴡ !", show_alert=True
            )

        def header(key):
            return _refine_header(
                userid, key=key, season_label="! Sᴇʟᴇᴄᴛ Aɢᴀɪɴ !",
            )

        await _apply_refinement(
            query, seasons, header_builder=header,
            empty_alert="Sᴏʀʀʏ ᴘᴏᴏᴋɪᴇ, Nᴏ ғɪʟᴇs ᴡᴇʀᴇ ғᴏᴜɴᴅ ғᴏʀ ʏᴏᴜʀ ᴏ̨ᴜᴇʀʏ {movie}.",
        )
    except Exception as exc:
        logger.exception("seasons_check failed: %s", exc)
        await query.answer(f"error found out\n\n{exc}", show_alert=True)


@Client.on_callback_query(filters.regex(r"^seas"))
async def select_seasons(bot, query):
    """Show the season picker keyboard."""
    _, userid = query.data.split("#")
    if not _owns(query, userid):
        return await query.answer(
            phrases.ALRT_TXT.format(query.from_user.first_name), show_alert=True
        )
    btn = [
        [InlineKeyboardButton("Sᴇʟᴇᴄᴛ Yᴏᴜʀ Dᴇꜱɪʀᴇᴅ Sᴇᴀꜱᴏɴ ↓",
                              callback_data=f"seasons#{userid}#unknown")],
        [
            InlineKeyboardButton("Sᴇᴀꜱᴏɴ 𝟷", callback_data=f"seasons#{userid}#s01"),
            InlineKeyboardButton("Sᴇᴀꜱᴏɴ 𝟸", callback_data=f"seasons#{userid}#s02"),
        ],
        [
            InlineKeyboardButton("Sᴇᴀꜱᴏɴ 𝟹", callback_data=f"seasons#{userid}#s03"),
            InlineKeyboardButton("Sᴇᴀꜱᴏɴ 𝟺", callback_data=f"seasons#{userid}#s04"),
        ],
        [
            InlineKeyboardButton("Sᴇᴀꜱᴏɴ 𝟻", callback_data=f"seasons#{userid}#s05"),
            InlineKeyboardButton("Sᴇᴀꜱᴏɴ 𝟼", callback_data=f"seasons#{userid}#s06"),
        ],
        [
            InlineKeyboardButton("Sᴇᴀꜱᴏɴ 𝟽", callback_data=f"seasons#{userid}#s07"),
            InlineKeyboardButton("Sᴇᴀꜱᴏɴ 𝟾", callback_data=f"seasons#{userid}#s08"),
        ],
        [
            InlineKeyboardButton("Sᴇᴀꜱᴏɴ 𝟿", callback_data=f"seasons#{userid}#s09"),
            InlineKeyboardButton("Sᴇᴀꜱᴏɴ 𝟷𝟶", callback_data=f"seasons#{userid}#s10"),
        ],
        [InlineKeyboardButton("Gᴏ Bᴀᴄᴋ", callback_data=f"seasons#{userid}#home")],
    ]
    try:
        await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(btn))
    except MessageNotModified:
        pass
    await query.answer()


# ── Episode ──────────────────────────────────────────────────────────────────
@Client.on_callback_query(filters.regex(r"^episode"))
async def episode_check(bot, query):
    try:
        _, userid, episode = query.data.split("#")
        if not _owns(query, userid):
            return await query.answer(
                phrases.ALRT_TXT.format(query.from_user.first_name), show_alert=True
            )
        if episode == "unknown":
            return await query.answer(
                "Sᴇʟᴇᴄᴛ ᴀɴʏ ᴇᴘɪꜱᴏᴅᴇ ғʀᴏᴍ ᴛʜᴇ ʙᴜᴛᴛᴏɴs ʙᴇʟᴏᴡ !", show_alert=True
            )

        def header(key):
            return _refine_header(
                userid, key=key, episode_label="! Sᴇʟᴇᴄᴛ Aɢᴀɪɴ !",
            )

        await _apply_refinement(
            query, episode, header_builder=header,
            empty_alert="Sᴏʀʀʏ ᴘᴏᴏᴋɪᴇ, Nᴏ ғɪʟᴇs ᴡᴇʀᴇ ғᴏᴜɴᴅ ғᴏʀ ʏᴏᴜʀ ᴏ̨ᴜᴇʀʏ {movie}.",
        )
    except Exception as exc:
        logger.exception("episode_check failed: %s", exc)
        await query.answer(f"error found out\n\n{exc}", show_alert=True)


def _episode_button_grid(userid, lo, hi):
    """Rows of 5 episode buttons covering episodes lo..hi (inclusive)."""
    rows, current = [], []
    for n in range(lo, hi + 1):
        current.append(
            InlineKeyboardButton(f"ᴇᴘ {n}", callback_data=f"episode#{userid}#e{n:02d}")
        )
        if len(current) == 5:
            rows.append(current)
            current = []
    if current:
        rows.append(current)
    return rows


@Client.on_callback_query(filters.regex(r"^epi2"))
async def select_episode2(bot, query):
    """Show episodes 16–30 (page 2 of the episode picker)."""
    _, userid = query.data.split("#")
    if not _owns(query, userid):
        return await query.answer(
            phrases.ALRT_TXT.format(query.from_user.first_name), show_alert=True
        )
    btn = [[InlineKeyboardButton("Sᴇʟᴇᴄᴛ Yᴏᴜʀ Dᴇꜱɪʀᴇᴅ Eᴘɪsᴏᴅᴇ ↓",
                                 callback_data=f"episode#{userid}#unknown")]]
    btn += _episode_button_grid(userid, 16, 30)
    btn.append([
        InlineKeyboardButton("⥢ Bᴀᴄᴋ", callback_data=f"epi#{userid}"),
        InlineKeyboardButton("≪Bᴀᴄᴋ ᴛᴏ Hᴏᴍᴇ≫", callback_data=f"episode#{userid}#home"),
    ])
    try:
        await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(btn))
    except MessageNotModified:
        pass
    await query.answer()


@Client.on_callback_query(filters.regex(r"^epi"))
async def select_episode(bot, query):
    """Show episodes 1–15 (page 1 of the episode picker)."""
    _, userid = query.data.split("#")
    if not _owns(query, userid):
        return await query.answer(
            phrases.ALRT_TXT.format(query.from_user.first_name), show_alert=True
        )
    btn = [[InlineKeyboardButton("Sᴇʟᴇᴄᴛ Yᴏᴜʀ Dᴇꜱɪʀᴇᴅ Eᴘɪsᴏᴅᴇ ↓",
                                 callback_data=f"episode#{userid}#unknown")]]
    btn += _episode_button_grid(userid, 1, 15)
    btn.append([
        InlineKeyboardButton("⥢ Bᴀᴄᴋ", callback_data=f"episode#{userid}#home"),
        InlineKeyboardButton("ɴᴇxᴛ ➮", callback_data=f"epi2#{userid}"),
    ])
    try:
        await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(btn))
    except MessageNotModified:
        pass
    await query.answer()


# ═══════════════════════════════════════════════════════════════════════════════
#  Spell-check suggestion click (spol#...) → re-run auto_filter for chosen title
# ═══════════════════════════════════════════════════════════════════════════════

@Client.on_callback_query(filters.regex(r"^spol"))
async def pm_spoll_choker(bot, query):
    """User tapped one of the IMDB spell-suggestion buttons."""
    _, movie_id, user = query.data.split("#")
    if int(user) != 0 and query.from_user.id != int(user):
        return await query.answer(
            phrases.ALRT_TXT.format(query.from_user.first_name), show_alert=True
        )

    # Blocking IMDB lookup → off-thread.
    movie = await get_poster(movie_id, id=True)
    search = movie.get("title")
    await query.answer("ᴄʜᴇᴄᴋɪɴɢ ɪɴ ᴍʏ ᴅᴀᴛᴀʙᴀꜱᴇ 🌚")

    files, offset, total_results = await get_search_results(query.message.chat.id, search)
    if files:
        await auto_filter(bot, query, (search, files, offset, total_results))
        return

    # Nothing found — log to the request channel and show the "not found" notice.
    reqstr1 = query.from_user.id if query.from_user else 0
    try:
        reqstr = await bot.get_users(reqstr1)
        chat_total = await bot.get_chat_members_count(query.message.chat.id)
        log_text = phrases.NORSLTS.format(
            query.message.chat.title, query.message.chat.id, chat_total,
            temp.B_NAME, reqstr.mention, search,
        )
    except Exception as exc:
        # In PM (or any get-users failure) fall back to the PM-flavoured log text.
        logger.debug("spoll log fallback: %s", exc)
        try:
            reqstr = await bot.get_users(reqstr1)
            log_text = phrases.PMNORSLTS.format(temp.B_NAME, reqstr.mention, search)
        except Exception:
            log_text = None

    if NO_RESULTS_MSG and log_text:
        no_result_kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("ɴᴏᴛ ʀᴇʟᴇᴀꜱᴇᴅ 📅",
                                     callback_data=f"not_release:{reqstr1}:{search}"),
                InlineKeyboardButton("ɴᴏᴛ ᴀᴠᴀɪʟᴀʙʟᴇ 🙅",
                                     callback_data=f"not_available:{reqstr1}:{search}"),
            ],
            [InlineKeyboardButton("ᴜᴘʟᴏᴀᴅᴇᴅ ✅",
                                  callback_data=f"uploaded:{reqstr1}:{search}")],
            [
                InlineKeyboardButton("ɪɴᴠᴀʟɪᴅ ғᴏʀᴍᴀᴛ🙅",
                                     callback_data=f"series:{reqstr1}:{search}"),
                InlineKeyboardButton("ꜱᴘᴇʟʟ ᴍɪꜱᴛᴀᴋᴇ✍️",
                                     callback_data=f"spelling_error:{reqstr1}:{search}"),
            ],
            [InlineKeyboardButton("⁉️ Close ⁉️", callback_data="close_data")],
        ])
        try:
            await bot.send_message(chat_id=LOG_CHANNEL, text=log_text, reply_markup=no_result_kb)
        except Exception as exc:
            logger.warning("spoll: could not post no-result log: %s", exc)

    k = await query.message.edit(phrases.MVE_NT_FND)
    await asyncio.sleep(SPELL_TIMEOUT)
    try:
        await k.delete()
    except (MessageIdInvalid, MessageDeleteForbidden):
        pass
    try:
        await query.message.reply_to_message.delete()
    except (MessageIdInvalid, MessageDeleteForbidden, AttributeError):
        pass


# ═══════════════════════════════════════════════════════════════════════════════
#  Master callback router — everything not matched by a specific handler above.
#  (Connections panel, file delivery, settings toggles, start menu, request logs…)
# ═══════════════════════════════════════════════════════════════════════════════

def _parse_group_id(raw):
    """Validate a connection-callback group id as an int (FIX: was unchecked).

    Returns the int id, or None if it's not a valid integer — callers must guard.
    """
    raw = str(raw).strip()
    if re.fullmatch(r"-?\d+", raw):
        return int(raw)
    return None


def _settings_keyboard(settings, grp_id):
    """Build the per-group settings toggle keyboard (used in 3 places)."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Rᴇꜱᴜʟᴛ Pᴀɢᴇ",
                                 callback_data=f'setgs#button#{settings["button"]}#{grp_id}'),
            InlineKeyboardButton("Tᴇxᴛ" if settings["button"] else "Bᴜᴛᴛᴏɴ",
                                 callback_data=f'setgs#button#{settings["button"]}#{grp_id}'),
        ],
        [
            InlineKeyboardButton("Iᴍᴅʙ", callback_data=f'setgs#imdb#{settings["imdb"]}#{grp_id}'),
            InlineKeyboardButton("✔ Oɴ" if settings["imdb"] else "✘ Oғғ",
                                 callback_data=f'setgs#imdb#{settings["imdb"]}#{grp_id}'),
        ],
        [
            InlineKeyboardButton("Sᴘᴇʟʟ Cʜᴇᴄᴋ",
                                 callback_data=f'setgs#spell_check#{settings["spell_check"]}#{grp_id}'),
            InlineKeyboardButton("✔ Oɴ" if settings["spell_check"] else "✘ Oғғ",
                                 callback_data=f'setgs#spell_check#{settings["spell_check"]}#{grp_id}'),
        ],
        [
            InlineKeyboardButton("Wᴇʟᴄᴏᴍᴇ Msɢ",
                                 callback_data=f'setgs#welcome#{settings["welcome"]}#{grp_id}'),
            InlineKeyboardButton("✔ Oɴ" if settings["welcome"] else "✘ Oғғ",
                                 callback_data=f'setgs#welcome#{settings["welcome"]}#{grp_id}'),
        ],
        [
            InlineKeyboardButton("Aᴜᴛᴏ-Dᴇʟᴇᴛᴇ",
                                 callback_data=f'setgs#auto_delete#{settings["auto_delete"]}#{grp_id}'),
            InlineKeyboardButton("10 Mɪɴs" if settings["auto_delete"] else "✘ Oғғ",
                                 callback_data=f'setgs#auto_delete#{settings["auto_delete"]}#{grp_id}'),
        ],
        [
            InlineKeyboardButton("Aᴜᴛᴏ-Fɪʟᴛᴇʀ",
                                 callback_data=f'setgs#auto_ffilter#{settings["auto_ffilter"]}#{grp_id}'),
            InlineKeyboardButton("✔ Oɴ" if settings["auto_ffilter"] else "✘ Oғғ",
                                 callback_data=f'setgs#auto_ffilter#{settings["auto_ffilter"]}#{grp_id}'),
        ],
        [
            InlineKeyboardButton("Mᴀx Bᴜᴛᴛᴏɴs",
                                 callback_data=f'setgs#max_btn#{settings["max_btn"]}#{grp_id}'),
            InlineKeyboardButton("10" if settings["max_btn"] else f"{MAX_B_TN}",
                                 callback_data=f'setgs#max_btn#{settings["max_btn"]}#{grp_id}'),
        ],
        [
            InlineKeyboardButton("Fɪʟᴇ Lɪᴍɪᴛ",
                                 callback_data=f'setgs#filelock#{settings.get("filelock", LIMIT_MODE)}#{grp_id}'),
            InlineKeyboardButton("ᴏɴ ✔️" if settings.get("filelock", LIMIT_MODE) else "ᴏғғ ✗",
                                 callback_data=f'setgs#filelock#{settings.get("filelock", LIMIT_MODE)}#{grp_id}'),
        ],
        [
            InlineKeyboardButton("Sᴛʀᴇᴀᴍ Sʜᴏʀᴛ",
                                 callback_data=f'setgs#stream_mode#{settings.get("stream_mode", STREAM_MODE)}#{grp_id}'),
            InlineKeyboardButton("✔ Oɴ" if settings.get("stream_mode", STREAM_MODE) else "✘ Oғғ",
                                 callback_data=f'setgs#stream_mode#{settings.get("stream_mode", STREAM_MODE)}#{grp_id}'),
        ],
        [
            InlineKeyboardButton("Vᴇʀɪғʏ",
                                 callback_data=f'setgs#is_verify#{settings.get("is_verify", IS_VERIFY)}#{grp_id}'),
            InlineKeyboardButton("✔ Oɴ" if settings.get("is_verify", IS_VERIFY) else "✘ Oғғ",
                                 callback_data=f'setgs#is_verify#{settings.get("is_verify", IS_VERIFY)}#{grp_id}'),
        ],
    ])


async def _send_request_log(client, query, data, txt_attr, status_label):
    """Shared body for the not_available / uploaded / not_release / etc logs.

    Sends the user a DM via the given phrases.* attribute and edits the admin log.
    """
    _, user_id, movie = data.split(":")
    try:
        kb = InlineKeyboardMarkup(
            [[InlineKeyboardButton("🗑 Delete Log ❌", callback_data="close_data")]]
        )
        await client.send_message(
            int(user_id), getattr(phrases, txt_attr).format(movie),
            parse_mode=enums.ParseMode.HTML,
        )
        await query.edit_message_text(
            text=(
                f"Mᴇꜱꜱᴀɢᴇ SᴇɴT Sᴜᴄᴄᴇꜱꜱғᴜʟʟʏ ✅\n\n⏳ꜱᴛᴀᴛᴜꜱ : {status_label}\n"
                f"🪪ᴜꜱᴇʀɪᴅ : `{user_id}`\n🎞ᴄᴏɴᴛᴇɴᴛ : `{movie}`"
            ),
            reply_markup=kb,
        )
    except Exception as exc:
        logger.warning("request-log send failed: %s", exc)
        await query.answer(f"{exc}", show_alert=True)


@Client.on_callback_query()
async def cb_handler(client: Client, query: CallbackQuery):
    """Catch-all router for every callback not handled by a specific decorator."""
    data = query.data

    # ── close / no-op ────────────────────────────────────────────────────────
    if data == "close_data":
        await query.message.delete()

    elif data == "pages":
        await query.answer()

    # ── group connection panel ───────────────────────────────────────────────
    elif "groupcb" in data:
        await query.answer()
        parts = data.split(":")
        group_id = _parse_group_id(parts[1])
        if group_id is None:
            return await query.answer("Iɴᴠᴀʟɪᴅ ɢʀᴏᴜᴘ ɪᴅ.", show_alert=True)
        act = parts[2]
        try:
            chat = await client.get_chat(group_id)
        except Exception as exc:
            logger.warning("groupcb get_chat failed: %s", exc)
            return await query.answer("Cᴏᴜʟᴅɴ'ᴛ ᴏᴘᴇɴ ᴛʜᴀᴛ ɢʀᴏᴜᴘ.", show_alert=True)
        title = chat.title

        stat, cb = ("CONNECT", "connectcb") if act == "" else ("DISCONNECT", "disconnect")
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(f"{stat}", callback_data=f"{cb}:{group_id}"),
                InlineKeyboardButton("DELETE", callback_data=f"deletecb:{group_id}"),
            ],
            [InlineKeyboardButton("BACK", callback_data="backcb")],
        ])
        await query.message.edit_text(
            f"Gʀᴏᴜᴘ Nᴀᴍᴇ : **{title}**\nGʀᴏᴜᴘ ID : `{group_id}`",
            reply_markup=keyboard, parse_mode=enums.ParseMode.MARKDOWN,
        )
        return await query.answer(MSG_ALRT)

    elif "connectcb" in data:
        await query.answer()
        group_id = _parse_group_id(data.split(":")[1])
        if group_id is None:
            return await query.answer("Iɴᴠᴀʟɪᴅ ɢʀᴏᴜᴘ ɪᴅ.", show_alert=True)
        try:
            chat = await client.get_chat(group_id)
        except Exception as exc:
            logger.warning("connectcb get_chat failed: %s", exc)
            return await query.answer("Cᴏᴜʟᴅɴ'ᴛ ᴏᴘᴇɴ ᴛʜᴀᴛ ɢʀᴏᴜᴘ.", show_alert=True)
        title = chat.title
        user_id = query.from_user.id
        if await make_active(str(user_id), str(group_id)):
            await query.message.edit_text(f"Cᴏɴɴᴇᴄᴛᴇᴅ ᴛᴏ **{title}**",
                                          parse_mode=enums.ParseMode.MARKDOWN)
        else:
            await query.message.edit_text("Sᴏᴍᴇ ᴇʀʀᴏʀ ᴏᴄᴄᴜʀʀᴇᴅ!!",
                                          parse_mode=enums.ParseMode.MARKDOWN)
        return await query.answer(MSG_ALRT)

    elif "disconnect" in data:
        await query.answer()
        group_id = _parse_group_id(data.split(":")[1])
        if group_id is None:
            return await query.answer("Iɴᴠᴀʟɪᴅ ɢʀᴏᴜᴘ ɪᴅ.", show_alert=True)
        try:
            chat = await client.get_chat(group_id)
        except Exception as exc:
            logger.warning("disconnect get_chat failed: %s", exc)
            return await query.answer("Cᴏᴜʟᴅɴ'ᴛ ᴏᴘᴇɴ ᴛʜᴀᴛ ɢʀᴏᴜᴘ.", show_alert=True)
        title = chat.title
        user_id = query.from_user.id
        if await make_inactive(str(user_id)):
            await query.message.edit_text(f"Dɪsᴄᴏɴɴᴇᴄᴛᴇᴅ ғʀᴏᴍ **{title}**",
                                          parse_mode=enums.ParseMode.MARKDOWN)
        else:
            await query.message.edit_text("Sᴏᴍᴇ ᴇʀʀᴏʀ ᴏᴄᴄᴜʀʀᴇᴅ!!",
                                          parse_mode=enums.ParseMode.MARKDOWN)
        return await query.answer(MSG_ALRT)

    elif "deletecb" in data:
        await query.answer()
        user_id = query.from_user.id
        group_id = _parse_group_id(data.split(":")[1])
        if group_id is None:
            return await query.answer("Iɴᴠᴀʟɪᴅ ɢʀᴏᴜᴘ ɪᴅ.", show_alert=True)
        if await delete_connection(str(user_id), str(group_id)):
            await query.message.edit_text("ᴄᴏɴɴᴇᴄᴛɪᴏɴ ᴅᴇʟᴇᴛᴇᴅ Sᴜᴄᴄᴇssғᴜʟʟʏ!")
        else:
            await query.message.edit_text("Sᴏᴍᴇ ᴇʀʀᴏʀ ᴏᴄᴄᴜʀʀᴇᴅ!!",
                                          parse_mode=enums.ParseMode.MARKDOWN)
        return await query.answer(MSG_ALRT)

    elif data == "backcb":
        await query.answer()
        userid = query.from_user.id
        groupids = await all_connections(str(userid))
        if groupids is None:
            await query.message.edit_text(
                "Tʜᴇʀᴇ ᴀʀᴇ ɴᴏ ᴀᴄᴛɪᴠᴇ ᴄᴏɴɴᴇᴄᴛɪᴏɴs!! Cᴏɴɴᴇᴄᴛ ᴛᴏ sᴏᴍᴇ ɢʀᴏᴜᴘs ғɪʀsᴛ."
            )
            return await query.answer(MSG_ALRT)
        buttons = []
        for groupid in groupids:
            gid = _parse_group_id(groupid)
            if gid is None:
                continue
            try:
                ttl = await client.get_chat(gid)
                active = await if_active(str(userid), str(groupid))
                act = " - ACTIVE" if active else ""
                buttons.append([InlineKeyboardButton(
                    text=f"{ttl.title}{act}", callback_data=f"groupcb:{groupid}:{act}"
                )])
            except Exception as exc:
                logger.debug("backcb group skip %s: %s", groupid, exc)
        if buttons:
            await query.message.edit_text(
                "Yᴏᴜʀ ᴄᴏɴɴᴇᴄᴛᴇᴅ ɢʀᴏᴜᴘ ᴅᴇᴛᴀɪʟs :\n\n",
                reply_markup=InlineKeyboardMarkup(buttons),
            )

    # ── deliver a single file / send-all ─────────────────────────────────────
    elif data.startswith("files"):
        ident, file_id = data.split("#")
        try:
            owner_id = query.message.reply_to_message.from_user.id
        except AttributeError:
            owner_id = 0
        if int(owner_id) != 0 and query.from_user.id != int(owner_id):
            return await query.answer(
                phrases.ALRT_TXT.format(query.from_user.first_name), show_alert=True
            )
        await query.answer(
            url=f"https://t.me/{temp.U_NAME}?start=files_{query.message.chat.id}_{file_id}"
        )

    elif data.startswith("sendfiles"):
        ident, key = data.split("#")
        try:
            await query.answer(
                url=f"https://telegram.me/{temp.U_NAME}?start=allfiles_{query.message.chat.id}_{key}"
            )
        except UserIsBlocked:
            await query.answer("Uɴʙʟᴏᴄᴋ ᴛʜᴇ ʙᴏᴛ ᴍᴀɴ !", show_alert=True)
        except PeerIdInvalid:
            await query.answer(url=f"https://telegram.me/{temp.U_NAME}?start=sendfiles3_{key}")
        except Exception as exc:
            logger.exception("sendfiles failed: %s", exc)
            await query.answer(url=f"https://telegram.me/{temp.U_NAME}?start=sendfiles4_{key}")

    # ── bulk delete bad files (admin tool) ───────────────────────────────────
    elif data.startswith("killfilesdq"):
        ident, keyword = data.split("#")
        await query.message.edit_text(
            f"<b>Fᴇᴛᴄʜɪɴɢ Fɪʟᴇs ғᴏʀ ʏᴏᴜʀ ᴏ̨ᴜᴇʀʏ {keyword} ᴏɴ DB... Pʟᴇᴀsᴇ ᴡᴀɪᴛ...</b>"
        )
        files, total = await get_bad_files(keyword)
        await query.message.edit_text(
            f"<b>Fᴏᴜɴᴅ {total} Fɪʟᴇs ғᴏʀ ʏᴏᴜʀ ᴏ̨ᴜᴇʀʏ {keyword} !\n\n"
            f"Fɪʟᴇ ᴅᴇʟᴇᴛɪᴏɴ ᴘʀᴏᴄᴇss ᴡɪʟʟ sᴛᴀʀᴛ ɪɴ 5 sᴇᴄᴏɴᴅs!</b>"
        )
        await asyncio.sleep(5)
        deleted = 0
        async with lock:
            try:
                for file in files:
                    result = await Media.collection.delete_one({"_id": file.file_id})
                    if result.deleted_count:
                        logger.info("killfilesdq: deleted %s for '%s'",
                                    file.file_name, keyword)
                    deleted += 1
                    if deleted % 20 == 0:
                        await query.message.edit_text(
                            f"<b>Pʀᴏᴄᴇss sᴛᴀʀᴛᴇᴅ ғᴏʀ ᴅᴇʟᴇᴛɪɴɢ ғɪʟᴇs ғʀᴏᴍ DB. "
                            f"Sᴜᴄᴄᴇssғᴜʟʟʏ ᴅᴇʟᴇᴛᴇᴅ {deleted} ғɪʟᴇs ғʀᴏᴍ DB ғᴏʀ "
                            f"ʏᴏᴜʀ ᴏ̨ᴜᴇʀʏ {keyword} !\n\nPʟᴇᴀsᴇ ᴡᴀɪᴛ...</b>"
                        )
            except Exception as exc:
                logger.exception("killfilesdq failed: %s", exc)
                await query.message.edit_text(f"Eʀʀᴏʀ: {exc}")
            else:
                await query.message.edit_text(
                    f"<b>Pʀᴏᴄᴇss Cᴏᴍᴘʟᴇᴛᴇᴅ ғᴏʀ ғɪʟᴇ ᴅᴇʟᴇᴛɪᴏɴ !\n\n"
                    f"Sᴜᴄᴄᴇssғᴜʟʟʏ ᴅᴇʟᴇᴛᴇᴅ {deleted} ғɪʟᴇs ғʀᴏᴍ DB ғᴏʀ "
                    f"ʏᴏᴜʀ ᴏ̨ᴜᴇʀʏ {keyword}.</b>"
                )

    # ── reset group settings to defaults ─────────────────────────────────────
    elif data.startswith("reset_grp_data"):
        grp_id = query.message.chat.id
        defaults = {
            "verify": VERIFY_URL, "verify_api": VERIFY_API,
            "verify_2": VERIFY_URL2, "verify_api2": VERIFY_API2,
            "verify_3": VERIFY_URL3, "verify_api3": VERIFY_API3,
            "verify_time": TWO_VERIFY_GAP, "verify_time2": THIRD_VERIFY_GAP,
            "template": IMDB_TEMPLATE, "tutorial": TUTORIAL,
            "tutorial2": TUTORIAL2, "tutorial3": TUTORIAL3,
            "caption": CUSTOM_FILE_CAPTION, "fsub_id": AUTH_CHANNEL,
            "log": LOG_CHANNEL, "file_limit": FILE_LIMITE,
            "streamapi": STREAM_API, "streamsite": STREAM_SITE,
            "all_limit": SEND_ALL_LIMITE,
        }
        for key, value in defaults.items():
            await save_group_settings(grp_id, key, value)
        await query.answer("ꜱᴜᴄᴄᴇꜱꜱғᴜʟʟʏ ʀᴇꜱᴇᴛ...")
        await query.message.edit_text(
            "<b>ꜱᴜᴄᴄᴇꜱꜱғᴜʟʟʏ ʀᴇꜱᴇᴛ ɢʀᴏᴜᴘ ꜱᴇᴛᴛɪɴɢꜱ...\n\nɴᴏᴡ ꜱᴇɴᴅ /details ᴀɢᴀɪɴ</b>",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("✂️ ᴄʟᴏsᴇ ✂️️", callback_data="close_data")]]
            ),
        )

    # ── open settings panel in group / in PM ─────────────────────────────────
    elif data.startswith("opnsetgrp"):
        ident, grp_id = data.split("#")
        userid = query.from_user.id if query.from_user else None
        st = await client.get_chat_member(grp_id, userid)
        if (
            st.status != enums.ChatMemberStatus.ADMINISTRATOR
            and st.status != enums.ChatMemberStatus.OWNER
            and str(userid) not in ADMINS
        ):
            return await query.answer("Yᴏᴜ Dᴏɴ'ᴛ Hᴀᴠᴇ Tʜᴇ Rɪɢʜᴛs Tᴏ Dᴏ Tʜɪs !",
                                      show_alert=True)
        title = query.message.chat.title
        settings = await get_settings(grp_id)
        if settings is not None:
            await query.message.edit_text(
                text=f"<b>Cʜᴀɴɢᴇ Yᴏᴜʀ Sᴇᴛᴛɪɴɢs Fᴏʀ {title} As ᴘᴇʀ Yᴏᴜʀ Wɪsʜ ⚙</b>",
                disable_web_page_preview=True, parse_mode=enums.ParseMode.HTML,
            )
            await query.message.edit_reply_markup(_settings_keyboard(settings, str(grp_id)))

    elif data.startswith("opnsetpm"):
        ident, grp_id = data.split("#")
        userid = query.from_user.id if query.from_user else None
        st = await client.get_chat_member(grp_id, userid)
        if (
            st.status != enums.ChatMemberStatus.ADMINISTRATOR
            and st.status != enums.ChatMemberStatus.OWNER
            and str(userid) not in ADMINS
        ):
            return await query.answer("Yᴏᴜ Dᴏɴ'ᴛ Hᴀᴠᴇ Tʜᴇ Rɪɢʜᴛs Tᴏ Dᴏ Tʜɪs !",
                                      show_alert=True)
        title = query.message.chat.title
        settings = await get_settings(grp_id)
        await query.message.edit_text(
            f"<b>Yᴏᴜʀ sᴇᴛᴛɪɴɢs ᴍᴇɴᴜ ғᴏʀ {title} ʜᴀs ʙᴇᴇɴ sᴇɴᴛ ᴛᴏ ʏᴏᴜʀ PM</b>"
        )
        await query.message.edit_reply_markup(
            InlineKeyboardMarkup([[InlineKeyboardButton("Cʜᴇᴄᴋ PM", url=f"t.me/{temp.U_NAME}")]])
        )
        if settings is not None:
            await client.send_message(
                chat_id=userid,
                text=f"<b>Cʜᴀɴɢᴇ Yᴏᴜʀ Sᴇᴛᴛɪɴɢs Fᴏʀ {title} As ᴘᴇʀ Yᴏᴜʀ Wɪsʜ ⚙</b>",
                reply_markup=_settings_keyboard(settings, str(grp_id)),
                disable_web_page_preview=True, parse_mode=enums.ParseMode.HTML,
                reply_to_message_id=query.message.id,
            )

    # ── start / help / about menus ───────────────────────────────────────────
    elif data == "start":
        buttons = [
            [InlineKeyboardButton("☆ ᴀᴅᴅ ᴍᴇ ᴛᴏ ʏᴏᴜʀ ɢʀᴏᴜᴘ ☆",
                                  url=f"http://telegram.me/{temp.U_NAME}?startgroup=true")],
            [
                InlineKeyboardButton("🆕 ᴜᴘᴅᴀᴛᴇꜱ", callback_data="channels"),
                InlineKeyboardButton("💡 ꜰᴇᴀᴛᴜʀᴇꜱ", callback_data="features"),
            ],
            [
                InlineKeyboardButton("🛠️ Hᴇʟᴘ", callback_data="help"),
                InlineKeyboardButton("🤖 ᴀʙᴏᴜᴛ", callback_data="about"),
            ],
            [
                InlineKeyboardButton("🆓 ꜰʀᴇᴇ ᴘʀᴇᴍɪᴜᴍ", callback_data="pm_reff"),
                InlineKeyboardButton("✨ ʙᴜʏ ᴘʀᴇᴍɪᴜᴍ", callback_data="premium_info"),
            ],
            [InlineKeyboardButton("☎️ ꜱᴜᴘᴘᴏʀᴛ", url=f"https://t.me/{SUPPORT_CHAT}")],
        ]
        # The locked Trinity credit button lives in handlers/commandcenter.py per
        # brand.py; here we append it via the shared injector so it stays in sync.
        buttons = inject_repo_button(buttons)
        await client.edit_message_media(
            query.message.chat.id, query.message.id,
            InputMediaPhoto(random.choice(PICS), has_spoiler=True),
        )
        await query.message.edit_text(
            text=phrases.START_TXT.format(query.from_user.mention, temp.U_NAME, temp.B_NAME),
            reply_markup=InlineKeyboardMarkup(buttons), parse_mode=enums.ParseMode.HTML,
        )
        await query.answer(MSG_ALRT)

    elif data == "features":
        await query.message.edit_text(
            text=phrases.FEATURES,
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("⋞ ʙᴀᴄᴋ", callback_data="start")]]
            ),
            parse_mode=enums.ParseMode.HTML,
        )

    # ── referral points ──────────────────────────────────────────────────────
    elif data == "show_pm":
        user_id = query.from_user.id
        points = await referrals.get_refer_points(user_id)  # NOW ASYNC
        await query.answer(text=f"You Have: {points} Refferal Points", show_alert=True)

    elif data == "pm_reff":
        try:
            user_id = query.from_user.id
            points = await referrals.get_refer_points(user_id)  # NOW ASYNC
            share_url = (
                "https://t.me/share/url?url="
                "%E0%A4%AF%E0%A5%87%20Bot%20%E0%A4%9F%E0%A5%87%E0%A4%B2%E0%A5%80%E0%A4%97%E0%A5%8D%E0%A4%B0%E0%A4%BE%E0%A4%AE%20"
                "%E0%A4%AA%E0%A4%B0%20%20%E0%A4%B8%E0%A4%AC%E0%A4%B8%E0%A5%87%20%E0%A4%AA%E0%A4%B9%E0%A4%B2%E0%A5%87%20"
                "%E0%A4%AE%E0%A5%82%E0%A4%B5%E0%A5%80%20%E0%A4%94%E0%A4%B0%20%E0%A4%B8%E0%A5%80%E0%A4%B0%E0%A5%80%E0%A4%9C%20"
                "%E0%A4%85%E0%A4%AA%E0%A4%B2%E0%A5%8B%E0%A4%A1%20%E0%A4%95%E0%A4%B0%20%E0%A4%A6%E0%A5%87%E0%A4%A4%E0%A4%BE%20"
                "%E0%A4%B9%E0%A5%88%20%0A%0ALink%3Dhttps://t.me/" + str(temp.U_NAME) + "?start=reff_" + str(user_id)
            )
            buttons = [[
                InlineKeyboardButton("ɪɴᴠɪᴛᴇ 🔗", url=share_url),
                InlineKeyboardButton(text=f"⏳{points}", callback_data="show_pm"),
                InlineKeyboardButton("⇚Back", callback_data="start"),
            ]]
            await client.edit_message_media(
                query.message.chat.id, query.message.id, InputMediaPhoto(REFFER_PIC)
            )
            await query.message.edit_text(
                text=phrases.REFFER_TXT.format(temp.U_NAME, user_id),
                reply_markup=InlineKeyboardMarkup(buttons), parse_mode=enums.ParseMode.HTML,
            )
        except Exception as exc:
            await query.answer(f"{exc}", show_alert=True)

    # ── request-status log buttons (admin DM-back) ───────────────────────────
    elif data.startswith("not_available"):
        await _send_request_log(client, query, data, "NOT_AVAILABLE_TXT",
                                "Nᴏᴛ Aᴠᴀɪʟᴀʙʟᴇ 😒.")
    elif data.startswith("uploaded"):
        await _send_request_log(client, query, data, "UPLOADED_TXT", "Uᴘʟᴏᴀᴅᴇᴅ 🎊.")
    elif data.startswith("not_release"):
        await _send_request_log(client, query, data, "NOT_RELEASE_TXT",
                                "ɴᴏᴛ ʀᴇʟᴇᴀsᴇᴅ 🙅.")
    elif data.startswith("spelling_error"):
        await _send_request_log(client, query, data, "SPELL_TXT",
                                "Sᴘᴇʟʟɪɴɢ Eʀʀᴏʀ 🕵️.")
    elif data.startswith("series"):
        await _send_request_log(client, query, data, "SERIES_FORMAT_TXT",
                                "Sᴇʀɪᴇs Eʀʀᴏʀ 🕵️.")

    # ── premium / payment info ───────────────────────────────────────────────
    elif data == "premium_info":
        await query.message.reply_photo(
            photo=PREMIUM_PIC, caption=phrases.PREMIUM_CMD,
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("🔲 Qʀ", callback_data="qr_info"),
                    InlineKeyboardButton("💳 Uᴘɪ", callback_data="upi_info"),
                ],
                [InlineKeyboardButton("🚫 ᴄʟᴏꜱᴇ 🚫", callback_data="close_data")],
            ]),
            parse_mode=enums.ParseMode.HTML,
        )

    elif data == "qr_info":
        await query.message.reply_photo(
            QR_CODE, caption=phrases.QR_TXT,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📸sᴇɴᴅ ᴘᴀʏᴍᴇɴᴛ sᴄʀᴇᴇɴsʜᴏᴛ📸",
                                      url=f"https://t.me/{OWNER_USER_NAME}")],
                [InlineKeyboardButton("🚫 ᴄʟᴏꜱᴇ 🚫", callback_data="close_data")],
            ]),
            parse_mode=enums.ParseMode.HTML,
        )

    elif data == "upi_info":
        await query.message.reply_text(
            phrases.UPI_TXT,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📸sᴇɴᴅ ᴘᴀʏᴍᴇɴᴛ sᴄʀᴇᴇɴsʜᴏᴛ📸",
                                      url=f"https://t.me/{OWNER_USER_NAME}")],
                [InlineKeyboardButton("🚫 ᴄʟᴏꜱᴇ 🚫", callback_data="close_data")],
            ]),
            parse_mode=enums.ParseMode.HTML,
        )

    elif data == "give_trial":
        user_id = query.from_user.id
        await db.give_free_trial(user_id)
        await query.message.reply_text(
            text=(
                "ʏᴏᴜ ʜᴀᴠᴇ ʙᴇᴇɴ ᴀᴅᴅᴇᴅ ᴛᴏ ᴘʀᴇᴍɪᴜᴍ✨ ғᴏʀ 5 ᴍɪɴᴜᴛᴇs\n\n"
                "ɴᴏᴡ ʏᴏᴜ ᴄᴀɴ ᴅᴏᴡɴʟᴏᴀᴅ ғɪʟᴇs ᴡɪᴛʜᴏᴜᴛ ᴠᴇʀɪғɪᴄᴀᴛɪᴏɴ\n\n"
                "sᴇᴇ ʏᴏᴜʀ ᴘʟᴀɴ /myplan"
            ),
            disable_web_page_preview=True,
        )
        await query.message.delete()
        return

    elif data == "channels":
        await query.message.edit_text(
            text=phrases.CHANNELS.format(query.from_user.mention),
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("ʙᴏᴛ ᴜᴘᴅᴀᴛᴇꜱ", url=CHNL_LNK),
                    InlineKeyboardButton("ᴍᴏᴠɪᴇ ᴜᴘᴅᴀᴛᴇꜱ", url="https://t.me/+xJ4x_LnXS8IzMmVl"),
                ],
                [InlineKeyboardButton("⇇ ʙᴀᴄᴋ", callback_data="start")],
            ]),
            parse_mode=enums.ParseMode.HTML,
        )

    elif data == "users":
        await query.message.edit_text(
            text=phrases.USERS_TXT,
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("⇋ ʙᴀᴄᴋ ⇋", callback_data="help")]]
            ),
            parse_mode=enums.ParseMode.HTML,
        )

    elif data == "group":
        await query.message.edit_text(
            text=phrases.GROUP_TXT,
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("⇋ ʙᴀᴄᴋ ⇋", callback_data="help")]]
            ),
            parse_mode=enums.ParseMode.HTML,
        )

    elif data == "admic":
        if query.from_user.id not in ADMINS:
            return await query.answer("⚠️ ʏᴏᴜ'ʀᴇ ɴᴏᴛ ᴀ ʙᴏᴛ ᴀᴅᴍɪɴ !", show_alert=True)
        await client.edit_message_media(
            query.message.chat.id, query.message.id,
            InputMediaPhoto(random.choice(PICS), has_spoiler=True),
        )
        await query.message.edit_text(
            text=phrases.ADMIC_TXT,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("⬅︎ ʙᴀᴄᴋ", callback_data="help"),
                InlineKeyboardButton("ɴᴇxᴛ ➡︎", callback_data="admic2"),
            ]]),
            parse_mode=enums.ParseMode.HTML,
        )

    elif data == "admic2":
        await client.edit_message_media(
            query.message.chat.id, query.message.id,
            InputMediaPhoto(random.choice(PICS), has_spoiler=True),
        )
        await query.message.edit_text(
            text=phrases.ADMIC_TEX2T,
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("⬅︎ ʙᴀᴄᴋ", callback_data="admic")]]
            ),
            parse_mode=enums.ParseMode.HTML,
        )

    elif data == "help":
        await client.edit_message_media(
            query.message.chat.id, query.message.id,
            InputMediaPhoto(random.choice(PICS), has_spoiler=True),
        )
        await query.message.edit_text(
            text=phrases.HELP_TXT.format(query.from_user.mention),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("ᴀᴅᴍɪɴ - ᴄᴏᴍᴍᴀɴᴅꜱ", callback_data="admic")],
                [
                    InlineKeyboardButton("ᴜꜱᴇʀ - ᴄᴏᴍᴍᴀɴᴅꜱ", callback_data="users"),
                    InlineKeyboardButton("ɢʀᴏᴜᴘ - ᴄᴏᴍᴍᴀɴᴅꜱ", callback_data="group"),
                ],
                [InlineKeyboardButton("⇋ ʙᴀᴄᴋ ᴛᴏ ʜᴏᴍᴇ ⇋", callback_data="start")],
            ]),
            parse_mode=enums.ParseMode.HTML,
        )

    elif data == "about":
        await client.edit_message_media(
            query.message.chat.id, query.message.id,
            InputMediaPhoto(random.choice(PICS), has_spoiler=True),
        )
        await query.message.edit_text(
            text=phrases.ABOUT_TXT.format(temp.U_NAME, temp.B_NAME),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("‼️ ᴅɪꜱᴄʟᴀɪᴍᴇʀ ‼️", callback_data="disclaimer")],
                [InlineKeyboardButton("⇋ ʙᴀᴄᴋ ᴛᴏ ʜᴏᴍᴇ ⇋", callback_data="start")],
            ]),
            parse_mode=enums.ParseMode.HTML,
        )

    elif data == "disclaimer":
        await query.message.edit_text(
            text=phrases.DISCLAIMER_TXT,
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("⇋ ʙᴀᴄᴋ ⇋", callback_data="about")]]
            ),
            parse_mode=enums.ParseMode.HTML,
        )

    # ── live stats (wrapped so a Mongo hiccup never hangs the user) ───────────
    elif data in ("stats", "rfrsh"):
        if data == "stats" and query.from_user.id not in ADMINS:
            return await query.answer("⚠️ ʏᴏᴜ'ʀᴇ ɴᴏᴛ ᴀ ʙᴏᴛ ᴀᴅᴍɪɴ !", show_alert=True)
        if data == "rfrsh":
            await query.answer("Fetching MongoDb DataBase")
        back_cb = "start" if data == "stats" else "help"
        buttons = InlineKeyboardMarkup([[
            InlineKeyboardButton("⟸ Bᴀᴄᴋ", callback_data=back_cb),
            InlineKeyboardButton("⟲ Rᴇғʀᴇsʜ", callback_data="rfrsh"),
        ]])
        await client.edit_message_media(
            query.message.chat.id, query.message.id,
            InputMediaPhoto(random.choice(PICS), has_spoiler=True),
        )
        try:
            total = await Media.count_documents()
            users = await db.total_users_count()
            chats = await db.total_chat_count()
            monsize = await db.get_db_size()
            free = get_size(536870912 - monsize)
            monsize = get_size(monsize)
            text = phrases.STATUS_TXT.format(total, users, chats, monsize, free)
        except Exception as exc:
            logger.exception("stats db error: %s", exc)
            text = "⚠️ Cᴏᴜʟᴅɴ'ᴛ ʀᴇᴀᴄʜ ᴛʜᴇ ᴅᴀᴛᴀʙᴀsᴇ. Pʟᴇᴀsᴇ ᴛʀʏ ᴀɢᴀɪɴ."
        await query.message.edit_text(text=text, reply_markup=buttons,
                                      parse_mode=enums.ParseMode.HTML)

    # ── settings toggle ──────────────────────────────────────────────────────
    elif data.startswith("setgs"):
        ident, set_type, status, grp_id = data.split("#")
        grpid = await active_connection(str(query.from_user.id))
        if str(grp_id) != str(grpid) and query.from_user.id not in ADMINS:
            await query.message.edit(
                "Yᴏᴜʀ Aᴄᴛɪᴠᴇ Cᴏɴɴᴇᴄᴛɪᴏɴ Hᴀs Bᴇᴇɴ Cʜᴀɴɢᴇᴅ. Gᴏ Tᴏ /connections "
                "ᴀɴᴅ ᴄʜᴀɴɢᴇ ʏᴏᴜʀ ᴀᴄᴛɪᴠᴇ ᴄᴏɴɴᴇᴄᴛɪᴏɴ."
            )
            return await query.answer(MSG_ALRT)
        await save_group_settings(grpid, set_type, status != "True")
        settings = await get_settings(grpid)
        if settings is not None:
            await query.message.edit_reply_markup(_settings_keyboard(settings, str(grp_id)))

    await query.answer(MSG_ALRT)


# ═══════════════════════════════════════════════════════════════════════════════
#  Spell-check helpers
# ═══════════════════════════════════════════════════════════════════════════════

async def ai_spell_check(chat_id, wrong_name):
    """Try to repair a misspelled title using IMDB titles + rapidfuzz ranking.

    Returns the best in-DB matching title, or None. Blocking Cinemagoer calls run
    via asyncio.to_thread so the event loop is never stalled.
    """
    try:
        try:
            search_results = await asyncio.wait_for(
                asyncio.to_thread(imdb.search_movie, wrong_name), timeout=SPELL_TIMEOUT
            )
        except asyncio.TimeoutError:
            logger.warning("ai_spell_check: IMDB lookup timed out for %r", wrong_name)
            return None
        movie_list = [m["title"] for m in search_results]
        if not movie_list:
            return None

        # rapidfuzz.process.extractOne with token_set_ratio scorer + 80 cutoff —
        # equivalent ranking to the old fuzzywuzzy default but MIT-licensed/faster.
        for _ in range(5):
            best = process.extractOne(
                wrong_name, movie_list, scorer=fuzz.token_set_ratio, score_cutoff=80
            )
            if not best:
                return None
            candidate = best[0]
            files, _o, _t = await get_search_results(chat_id=chat_id, query=candidate)
            if files:
                return candidate
            movie_list.remove(candidate)
        return None
    except Exception as exc:
        logger.exception("ai_spell_check error: %s", exc)
        return None


# ═══════════════════════════════════════════════════════════════════════════════
#  auto_filter — THE core search routine (imported by commandcenter)
# ═══════════════════════════════════════════════════════════════════════════════

async def auto_filter(client, msg, spoll=False):
    """Search the DB for `msg.text` and render a paginated result message.

    `msg` is a Message in normal mode, or a CallbackQuery in spoll mode. When
    `spoll` is a 4-tuple (search, files, offset, total) it means a spell-check
    suggestion was clicked and we already have results in hand.
    """
    try:
        start_time = _now_time()

        if not spoll:
            message = msg
            if message.text.startswith("/"):
                return  # ignore commands
            if re.findall(r"((^\/|^,|^!|^\.|^[\U0001F600-\U000E007F]).*)", message.text):
                return
            if len(message.text) >= 100:
                return

            # Greet with a "searching…" sticker then clean the raw query.
            search = _clean_query(message.text)
            m = await message.reply_sticker(
                sticker="CAACAgUAAxkBAAIFnGdEvhhXklJHOeZAEiOas7jkeNjeAALdCgACiVdhVxmB0t2QzTKsHgQ",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("🆆🅰️🅸🆃 🅿️🅾️🅾️🅺🅸🅴", url=CHNL_LNK)]]
                ),
            )

            files, offset, total_results = await get_search_results(
                message.chat.id, search, offset=0, filter=True
            )
            settings = await get_settings(message.chat.id)

            # NEW: feed /trending analytics (guarded by config + wrapped).
            if INSIGHTS_MODE:
                try:
                    await db.log_query(search, message.chat.id)
                except Exception as exc:
                    logger.debug("log_query failed: %s", exc)

            if not files:
                await m.delete()
                if settings["spell_check"]:
                    ai_sts = await message.reply_sticker(
                        sticker="CAACAgQAAxkBAAIFrWdEvvayqcqFnmnE9I854Zq0QO-UAAIWGQACBz0IUfk3O8NjyDd_HgQ"
                    )
                    st = await message.reply("<b>Ai is Cheking For Your Spelling. Please Wait.</b>")
                    suggestion = await ai_spell_check(chat_id=message.chat.id, wrong_name=search)
                    if suggestion:
                        await st.edit(
                            f"<b>Ai Suggested <code>{suggestion}</code> name\n"
                            f"So Im Searching for <code>{suggestion}</code></b>"
                        )
                        await asyncio.sleep(2)
                        msg.text = suggestion
                        await ai_sts.delete()
                        await st.delete()
                        return await auto_filter(client, msg)
                    await ai_sts.delete()
                    await st.delete()
                    return await advantage_spell_chok(client, msg)
                return
        else:
            # spoll mode: `msg` is the callback query; reuse pre-fetched results.
            message = msg.message.reply_to_message
            search, files, offset, total_results = spoll
            m = await message.reply_sticker(
                sticker="CAACAgUAAxkBAAIFnGdEvhhXklJHOeZAEiOas7jkeNjeAALdCgACiVdhVxmB0t2QzTKsHgQ",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("🆆🅰️🅸🆃 🅿️🅾️🅾️🅺🅸🅴", url=CHNL_LNK)]]
                ),
            )
            settings = await get_settings(message.chat.id)

        # ── stash results for the pagination/filter callbacks ────────────────
        key = f"{message.chat.id}-{message.id}"
        temp.GETALL[key] = files
        temp.CHAT[message.from_user.id] = message.chat.id
        temp.KEYWORD[message.from_user.id] = search

        single_button = settings.get("button", SINGLE_BUTTON)
        btn = _file_rows(files, single_button)
        for row in reversed(_refine_header(message.from_user.id, key=key)):
            btn.insert(0, row)

        # ── first-page pager row ─────────────────────────────────────────────
        if offset != "":
            BUTTONS[key] = search
            req = message.from_user.id if message.from_user else 0
            try:
                page_size = 10 if settings["max_btn"] else int(MAX_B_TN)
            except KeyError:
                await save_group_settings(message.chat.id, "max_btn", True)
                page_size = 10
            btn.append([
                InlineKeyboardButton("𝐏𝐀𝐆𝐄", callback_data="pages"),
                InlineKeyboardButton(f"1/{math.ceil(int(total_results) / page_size)}",
                                     callback_data="pages"),
                InlineKeyboardButton("𝐍𝐄𝐗𝐓 ➪", callback_data=f"next_{req}_{key}_{offset}"),
            ])
        else:
            btn.append([InlineKeyboardButton("𝐍𝐎 𝐌𝐎𝐑𝐄 𝐏𝐀𝐆𝐄𝐒 𝐀𝐕𝐀𝐈𝐋𝐀𝐁𝐋𝐄", callback_data="pages")])

        # ── caption (IMDB template, or a plain fallback) ─────────────────────
        poster = await get_poster(search, file=files[0].file_name) if settings["imdb"] else None
        remaining = _elapsed_seconds(start_time)

        if poster:
            cap = settings["template"].format(
                query=search, title=poster["title"], votes=poster["votes"],
                aka=poster["aka"], seasons=poster["seasons"],
                box_office=poster["box_office"], localized_title=poster["localized_title"],
                kind=poster["kind"], imdb_id=poster["imdb_id"], cast=poster["cast"],
                runtime=poster["runtime"], countries=poster["countries"],
                certificates=poster["certificates"], languages=poster["languages"],
                director=poster["director"], writer=poster["writer"],
                producer=poster["producer"], composer=poster["composer"],
                cinematographer=poster["cinematographer"], music_team=poster["music_team"],
                distributors=poster["distributors"], release_date=poster["release_date"],
                year=poster["year"], genres=poster["genres"], poster=poster["poster"],
                plot=poster["plot"], rating=poster["rating"], url=poster["url"],
            )
            temp.IMDB_CAP[message.from_user.id] = cap
            if single_button:
                for file in files:
                    cap += (
                        f"<b>\n\n<a href='https://telegram.me/{temp.U_NAME}"
                        f"?start=files_{message.chat.id}_{file.file_id}'> 📁 "
                        f"{get_size(file.file_size)} ▷ {file.file_name}</a></b>"
                    )
        else:
            cap = (
                f"<b>☠️ ᴛɪᴛʟᴇ : <code>{search}</code>\n"
                f"📂 ᴛᴏᴛᴀʟ ꜰɪʟᴇꜱ : <code>{total_results}</code>\n"
                f"📝 ʀᴇǫᴜᴇsᴛᴇᴅ ʙʏ : {message.from_user.first_name}\n"
                f"⏰ ʀᴇsᴜʟᴛ ɪɴ : <code>{remaining} Sᴇᴄᴏɴᴅs</code>\n\n"
                f"📚 Your Requested Files 👇\n\n</b>"
            )
            if single_button:
                for file in files:
                    cap += (
                        f"<b><a href='https://telegram.me/{temp.U_NAME}"
                        f"?start=files_{message.chat.id}_{file.file_id}'> 📁 "
                        f"{get_size(file.file_size)} ▷ {file.file_name}\n\n</a></b>"
                    )

        markup = InlineKeyboardMarkup(btn)

        # ── send the result; auto-delete is now scheduled, not inline ────────
        if poster and poster.get("poster"):
            try:
                sent = await message.reply_photo(
                    photo=poster.get("poster"), caption=cap, reply_markup=markup
                )
            except (MediaEmpty, PhotoInvalidDimensions, WebpageMediaEmpty):
                # Retry with the IMDB hi-res variant before giving up on a photo.
                fixed = poster.get("poster").replace(".jpg", "._V1_UX360.jpg")
                try:
                    sent = await message.reply_photo(
                        photo=fixed, caption=cap, reply_markup=markup
                    )
                except Exception as exc:
                    logger.warning("poster retry failed: %s", exc)
                    sent = await message.reply_text(text=cap, reply_markup=markup)
            except Exception as exc:
                logger.exception("poster send failed: %s", exc)
                sent = await message.reply_text(text=cap, reply_markup=markup)
            await m.delete()
            await _schedule_auto_delete(settings, sent, message)
        else:
            sent = await message.reply_text(text=cap, reply_markup=markup)
            await m.delete()
            await _schedule_auto_delete(settings, sent, message)

        if spoll:
            await msg.message.delete()
    except Exception as exc:
        logger.exception("auto_filter failed: %s", exc)
        try:
            await msg.reply(f"{exc}") if not spoll else await msg.message.reply(f"{exc}")
        except Exception:
            pass


async def advantage_spell_chok(client, message):
    """Fallback spell-check: offer IMDB title suggestions as spol# buttons."""
    search = message.text
    settings = await get_settings(message.chat.id)

    # Blocking bulk IMDB lookup → off-thread (was a sync .get_poster call).
    try:
        movies = await get_poster(search, bulk=True)
    except Exception as exc:
        logger.debug("advantage_spell_chok poster error: %s", exc)
        k = await message.reply(phrases.I_CUDNT.format(search))
        await asyncio.sleep(SPELL_TIMEOUT)
        try:
            await k.delete()
            await message.delete()
        except (MessageIdInvalid, MessageDeleteForbidden):
            pass
        return

    if not movies:
        google = search.replace(" ", "+")
        k = await message.reply_text(
            text=phrases.I_CUDNT.format(search),
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔍 ᴄʜᴇᴄᴋ sᴘᴇʟʟɪɴɢ ᴏɴ ɢᴏᴏɢʟᴇ 🔍",
                                     url=f"https://www.google.com/search?q={google}")
            ]]),
        )
        await asyncio.sleep(2 * SPELL_TIMEOUT)
        try:
            await k.delete()
            await message.delete()
        except (MessageIdInvalid, MessageDeleteForbidden):
            pass
        return

    user = message.from_user.id if message.from_user else 0
    buttons = [
        [InlineKeyboardButton(text=movie.get("title"),
                              callback_data=f"spol#{movie.movieID}#{user}")]
        for movie in movies
    ]
    buttons.append([InlineKeyboardButton(text="🚫 ᴄʟᴏsᴇ 🚫", callback_data="close_data")])
    d = await message.reply_text(
        text=phrases.CUDNT_FND.format(search),
        reply_markup=InlineKeyboardMarkup(buttons),
        reply_to_message_id=message.id,
    )
    await asyncio.sleep(2 * SPELL_TIMEOUT)
    try:
        await d.delete()
        await message.delete()
    except (MessageIdInvalid, MessageDeleteForbidden):
        pass


# ═══════════════════════════════════════════════════════════════════════════════
#  ⚡ Crafted by Trinity Mods (@trinityXmods) · Trinity AutoFilter
#  If this code helped you, keep the credit alive → github.com/Trinity-Mods
#  🚫 This credit is license-locked. See brand.py.
# ═══════════════════════════════════════════════════════════════════════════════
