# ═══════════════════════════════════════════════════════════════════════════════
#  ⚡ TRINITY MODS · TRINITY AUTOFILTER
#  Command center — /start, file delivery, /settings panel & every admin config command.
#  ─────────────────────────────────────────────────────────────────────────────
#  Developed & maintained by Trinity Mods (@trinityXmods)
#  GitHub   : github.com/Trinity-Mods
#  Source   : github.com/Trinity-Mods/Auto-Filter-Bot
#  Telegram : t.me/trinityXmods
#  🚫 Credit is license-locked — see brand.py. Please keep this header intact.
# ═══════════════════════════════════════════════════════════════════════════════

import os
import sys
import string
import random
import base64
import asyncio
import logging

import pytz
import requests
from datetime import datetime

from pyrogram import Client, filters, enums
from pyrogram.errors import (
    ChatAdminRequired,
    FloodWait,
    MessageIdInvalid,
    MessageDeleteForbidden,
)
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

# ── Trinity import contract (new module layout) ───────────────────────────────
from config import *
from phrases import phrases
from toolbox import (
    temp,
    get_settings,
    save_group_settings,
    get_size,
    is_subscribed,
    is_req_subscribed,
    get_shortlink,
)
from vault.media_index import Media, get_file_details, unpack_new_file_id
from vault.registry import db
from vault.links import active_connection
from vault.referrals import referrals, sdb          # sdb is an alias of referrals
from brand import inject_repo_button, repo_button
# The ONLY cross-handler dependency: the search entrypoint lives in searchcore.
from handlers.searchcore import auto_filter

logger = logging.getLogger(__name__)

# Indian Standard Time — used for verify timestamps / logs (fixed spelling).
IST = pytz.timezone("Asia/Kolkata")

# Sticker shown briefly before the start photo (kept identical to original).
START_STICKER = "CAACAgIAAxkBAAIBr2dDI0XOnpPn62EjCB1U9pGIidx0AAJ8EgAC8ZgxS6cvrXhhVMIIHgQ"


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────
def _is_admin(user_id) -> bool:
    """True if this user_id is a bot owner/admin (ADMINS holds string ids)."""
    return str(user_id) in ADMINS


async def _is_group_owner(client, chat_id, user_id) -> bool:
    """True if the user is admin/owner of the group, or a global bot admin."""
    member = await client.get_chat_member(chat_id, user_id)
    if member.status in (
        enums.ChatMemberStatus.ADMINISTRATOR,
        enums.ChatMemberStatus.OWNER,
    ):
        return True
    return _is_admin(user_id)


def _start_menu_buttons() -> InlineKeyboardMarkup:
    """
    Build the PM /start keyboard.

    The locked Trinity repo button is appended as its OWN row via
    brand.inject_repo_button(). Removing it (or the marker comment below) makes
    the bot refuse to start — see brand.verify_integrity().
    """
    rows = [
        [
            InlineKeyboardButton(
                "☆ ᴀᴅᴅ ᴍᴇ ᴛᴏ ʏᴏᴜʀ ɢʀᴏᴜᴘ ☆",
                url=f"http://telegram.me/{temp.U_NAME}?startgroup=true",
            )
        ],
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
    # TRINITY-REPO-BUTTON (LOCKED)
    rows = inject_repo_button(rows)
    return InlineKeyboardMarkup(rows)


def _schedule_autodelete(*messages, notice=None):
    """
    Schedule deletion of delivered file message(s) after config.AUTO_DELETE_TIME.

    We do NOT inline `await asyncio.sleep(...)` in the handler (that would block
    the whole call). Instead we capture the sent messages and fire-and-forget a
    background task; every delete is wrapped so a vanished/forbidden message can
    never crash the worker.
    """
    delay = getattr_safe_autodelete()

    async def _worker():
        await asyncio.sleep(delay)
        for sent in messages:
            try:
                await sent.delete()
            except (MessageIdInvalid, MessageDeleteForbidden):
                # Already gone, or the user revoked our delete rights — fine.
                pass
            except Exception as err:  # noqa: BLE001 — log anything unexpected
                logger.warning("auto-delete failed: %s", err)
        if notice is not None:
            try:
                await notice.edit_text(
                    "<b>ᴀʟʟ ᴛʜᴇ ꜱᴇɴᴛ ꜰɪʟᴇꜱ ʜᴀᴠᴇ ʙᴇᴇɴ ᴅᴇʟᴇᴛᴇᴅ ꜱᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ 📢</b>"
                )
            except (MessageIdInvalid, MessageDeleteForbidden):
                pass
            except Exception as err:  # noqa: BLE001
                logger.warning("auto-delete notice edit failed: %s", err)

    asyncio.create_task(_worker())


def getattr_safe_autodelete() -> int:
    """Resolve the auto-delete delay from config, defaulting to 600 seconds."""
    try:
        return int(AUTO_DELETE_TIME)
    except (NameError, TypeError, ValueError):
        return 600


# ──────────────────────────────────────────────────────────────────────────────
# /start  —  greeting, deep-link routing, verification gate & file delivery
# ──────────────────────────────────────────────────────────────────────────────
@Client.on_message(filters.command("start") & filters.incoming)
async def start(client, message):
    try:
        # React with a random emoji (best-effort; never fatal).
        try:
            await message.react(emoji=random.choice(REACTION), big=True)
        except Exception:  # noqa: BLE001 — reactions can be disabled in chat
            pass

        user_id = message.from_user.id
        send_count = await db.files_count(user_id, "send_all") or 0
        files_counts = await db.files_count(user_id, "files_count") or 0

        # ── /start issued inside a group: nudge user to DM, then register chat ──
        if message.chat.type in (enums.ChatType.GROUP, enums.ChatType.SUPERGROUP):
            reply_markup = InlineKeyboardMarkup(
                [[
                    InlineKeyboardButton(
                        "☆ ᴀᴅᴅ ᴍᴇ ᴛᴏ ʏᴏᴜʀ ɢʀᴏᴜᴘ ☆",
                        url=f"http://t.me/{temp.U_NAME}?startgroup=true",
                    )
                ]]
            )
            await message.reply_text(
                text="ᴏᴋ, ɪ ᴄᴀɴ ʜᴇʟᴘ ʏᴏᴜ ɪꜰ ʏᴏᴜ ᴊᴜsᴛ sᴛᴀʀᴛ ᴍᴇ ᴘᴇʀꜱᴏɴᴀʟʟʏ ɪɴ ᴍʏ ᴅᴍꜱ",
                reply_markup=reply_markup,
                parse_mode=enums.ParseMode.HTML,
            )
            await asyncio.sleep(2)  # give Telegram a beat before the membership check
            if not await db.get_chat(message.chat.id):
                total = await client.get_chat_members_count(message.chat.id)
                await client.send_message(
                    LOG_CHANNEL,
                    phrases.LOG_TEXT_G.format(
                        temp.B_NAME, message.chat.title, message.chat.id, total, "Unknown"
                    ),
                )
                await db.add_chat(message.chat.id, message.chat.title, user_id)
            return

        # ── Register first-time PM users ──
        if not await db.is_user_exist(user_id):
            await db.add_user(user_id, message.from_user.first_name)
            await client.send_message(
                LOG_CHANNEL,
                phrases.LOG_TEXT_P.format(user_id, message.from_user.mention, temp.B_NAME),
            )

        # ── Plain /start (no payload) → show the main menu ──
        if len(message.command) != 2:
            await _send_start_card(client, message)
            return

        payload = message.command[1]

        # ── /start <generic keyword> → also just show the main menu ──
        if payload in ("subscribe", "error", "okay", "help"):
            await _send_start_card(client, message)
            return

        # ── /start trinity → premium purchase card ──
        if payload == "trinity":
            reply_markup = InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton(
                        "📲 ꜱᴇɴᴅ ᴘᴀʏᴍᴇɴᴛ ꜱᴄʀᴇᴇɴꜱʜᴏᴛ",
                        url=f"https://t.me/{OWNER_USER_NAME}",
                    )],
                    [InlineKeyboardButton("❌ ᴄʟᴏꜱᴇ ❌", callback_data="close_data")],
                ]
            )
            await message.reply_photo(
                photo=PREMIUM_PIC,
                caption=phrases.PREMIUM_CMD,
                reply_markup=reply_markup,
                parse_mode=enums.ParseMode.HTML,
            )
            return

        # ── /start getfile-<query> → re-run the auto-filter for that query ──
        if payload.startswith("getfile"):
            parts = payload.split("-", 1)
            if len(parts) < 2:
                return await message.reply("Iɴᴠᴀʟɪᴅ ɢᴇᴛꜰɪʟᴇ ʟɪɴᴋ.")
            message.text = parts[1].replace("-", " ")
            await auto_filter(client, message)
            return

        # ── /start reff_<refid> → referral reward flow (all referrals calls awaited) ──
        if payload.startswith("reff_"):
            await _handle_referral(client, message, payload)
            return

        # ── /start verify_… / sendall_… → grant a completed verification ──
        if payload.startswith(("verify", "sendall")):
            handled = await _handle_verify_callback(client, message, payload)
            if handled:
                return
            # if not handled (malformed), fall through to generic delivery below

        # ── Everything else is a file/batch delivery deep-link ──
        await _deliver_payload(client, message, payload, send_count, files_counts)

    except Exception as err:  # noqa: BLE001 — last-resort guard so /start never dies silently
        logger.exception("start handler crashed: %s", err)
        try:
            await message.reply(f"{err}")
        except Exception:  # noqa: BLE001
            pass


async def _send_start_card(client, message):
    """Send the sticker teaser then the branded start photo + menu."""
    teaser = await message.reply_sticker(START_STICKER)
    await asyncio.sleep(2)
    try:
        await teaser.delete()
    except (MessageIdInvalid, MessageDeleteForbidden):
        pass
    await message.reply_photo(
        photo=random.choice(PICS),
        caption=phrases.START_TXT.format(message.from_user.mention, temp.U_NAME, temp.B_NAME),
        reply_markup=_start_menu_buttons(),
        has_spoiler=True,
        parse_mode=enums.ParseMode.HTML,
    )


async def _handle_referral(client, message, payload):
    """
    Award referral points for /start reff_<referrer_id>.

    All ledger calls (referrals/sdb) are async in the new vault and MUST be awaited.
    """
    parts = payload.split("_")
    if len(parts) < 2:
        return await message.reply_text("Invalid refer!")
    try:
        referrer_id = int(parts[1])
    except ValueError:
        return await message.reply_text("Invalid refer!")

    new_user = message.from_user.id

    # Reject self-referrals.
    if referrer_id == new_user:
        await message.reply_text(
            "Hᴇʏ Dᴜᴅᴇ, Yᴏᴜ Cᴀɴ'ᴛ Rᴇғᴇʀ Yᴏᴜʀsᴇʟғ 🤣!\n\n"
            "sʜᴀʀᴇ ʟɪɴᴋ ᴡɪᴛʜ ʏᴏᴜʀ ꜰʀɪᴇɴᴅꜱ ᴏʀ ꜰᴀᴍɪʟʏ ᴀɴᴅ ɢᴇᴛ 10 ʀᴇғᴇʀʀᴀʟ ᴘᴏɪɴᴛs ꜰᴏʀ ᴇᴀᴄʜ ʀᴇꜰᴇʀʀᴀʟ.\n\n"
            "ɪғ ʏᴏᴜ ᴄᴏʟʟᴇᴄᴛ 50 ʀᴇғᴇʀʀᴀʟ ᴘᴏɪɴᴛs, ᴛʜᴇɴ ʏᴏᴜ ᴄᴀɴ ɢᴇᴛ 1 ᴍᴏɴᴛʜ ғʀᴇᴇ ᴘʀᴇᴍɪᴜᴍ ᴍᴇᴍʙᴇʀsʜɪᴘ."
        )
        return

    # Credit only on a user's first-ever referral acceptance.
    if await referrals.is_user_in_list(new_user):
        return await message.reply_text("Yᴏᴜ ʜᴀᴠᴇ ʙᴇᴇɴ ᴀʟʀᴇᴀᴅʏ ɪɴᴠɪᴛᴇᴅ ❗")

    try:
        referrer = await client.get_users(referrer_id)
    except Exception as err:  # noqa: BLE001 — referrer may have deleted account
        logger.info("referral: cannot resolve referrer %s: %s", referrer_id, err)
        return

    await referrals.add_user(new_user)
    new_total = (await referrals.get_refer_points(referrer_id)) + 10
    await referrals.add_refer_points(referrer_id, new_total)

    await message.reply_text(
        f"ʏᴏᴜ ʜᴀᴠᴇ ʙᴇᴇɴ ꜱᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ ɪɴᴠɪᴛᴇᴅ ʙʏ {referrer.mention}!"
    )
    await client.send_message(
        referrer_id,
        f"ᴄᴏɴɢʀᴀᴛᴜʟᴀᴛɪᴏɴꜱ ᴘᴏᴏᴋɪᴇ! ʏᴏᴜ ᴊᴜꜱᴛ ᴇᴀʀɴᴇᴅ 10 ʀᴇꜰᴇʀʀᴀʟ ᴘᴏɪɴᴛꜱ ᴀꜱ "
        f"{message.from_user.mention} ᴊᴜꜱᴛ ᴄʟɪᴄᴋᴇᴅ ᴏɴ ʏᴏᴜʀ ʀᴇꜰᴇʀʀᴀʟ ʟɪɴᴋ ᴛᴏ ꜱᴛᴀʀᴛ ᴍᴇ!"
    )

    # Hit the reward threshold → grant a month of premium, reset the counter.
    if new_total == REFFER_POINT:
        await db.give_referal(referrer_id)
        await referrals.add_refer_points(referrer_id, 0)
        await client.send_message(
            chat_id=referrer_id,
            text=(
                f"<b>Hᴇʏ {referrer.mention}\n\n"
                "Yᴏᴜ ɢᴏᴛ 1 ᴍᴏɴᴛʜ ᴘʀᴇᴍɪᴜᴍ sᴜʙsᴄʀɪᴘᴛɪᴏɴ ꜰᴏʀ ɪɴᴠɪᴛɪɴɢ 5 ᴜsᴇʀs ❗</b>"
            ),
            disable_web_page_preview=True,
        )
        for admin in ADMINS:
            await client.send_message(
                chat_id=admin,
                text=(
                    "ᴛᴀꜱᴋ ᴄᴏᴍᴘʟᴇᴛᴇᴅ ꜱᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ ʙʏ ᴛʜɪꜱ ᴜꜱᴇʀ ʜᴇʀᴇ:\n\n"
                    f"ᴜꜱᴇʀ ɴᴀᴍᴇ: {referrer.mention}\n\nᴜꜱᴇʀ ɪᴅ: {referrer.id}!"
                ),
            )


async def _handle_verify_callback(client, message, payload):
    """
    Handle a completed verification deep-link:
      verify_<userid>_<verify_id>_<file_id>  or  sendall_<userid>_<verify_id>_<file_id>

    SECURITY: the embedded userid MUST equal the caller's id, otherwise we ignore
    the link entirely (prevents one user redeeming another's verification token).
    Returns True if it consumed the payload, False if it was malformed.
    """
    parts = payload.split("_", 3)
    if len(parts) != 4:
        return False
    _, userid_raw, verify_id, file_id = parts

    try:
        token_user_id = int(userid_raw)
    except ValueError:
        return False

    # 🔒 Token must belong to the person clicking it.
    if token_user_id != message.from_user.id:
        logger.warning(
            "verify token user mismatch: token=%s caller=%s",
            token_user_id, message.from_user.id,
        )
        return True  # consumed (ignored) — do not fall through to delivery

    user_id = token_user_id
    grp_id = temp.CHAT.get(user_id, 0)
    settings = await get_settings(grp_id)

    verify_id_info = await db.get_verify_id_info(user_id, verify_id)
    if not verify_id_info or verify_id_info["verified"]:
        await message.reply("<b>ʟɪɴᴋ ʜᴀꜱ ᴇxᴘɪʀᴇᴅ, ᴘᴏᴏᴋɪᴇ! ᴛʀʏ ᴀɢᴀɪɴ ʟᴀᴛᴇʀ ⌛</b>")
        return True

    # Decide which verification tier this completion belongs to.
    if await db.user_verified(user_id):
        key, num, complete_msg = "third_verified", 3, phrases.THIRDT_COMPLETE_TEXT
    elif await db.is_user_verified(user_id):
        key, num, complete_msg = "second_verified", 2, phrases.SECOND_COMPLETE_TEXT
    else:
        key, num, complete_msg = "last_verified", 1, phrases.VERIFY_COMPLETE_TEXT

    now_ist = datetime.now(tz=IST)
    await db.update_trinity_user(user_id, {key: now_ist})
    await db.update_verify_id_info(user_id, verify_id, {"verified": True})

    if payload.startswith("sendall"):
        get_file_url = f"https://telegram.me/{temp.U_NAME}?start=allfiles_{grp_id}_{file_id}"
    else:
        get_file_url = f"https://telegram.me/{temp.U_NAME}?start=files_{grp_id}_{file_id}"

    await client.send_message(
        settings["log"],
        phrases.VERIFIED_LOG_TEXT.format(
            message.from_user.mention,
            user_id,
            datetime.now(IST).strftime("%d %B %Y"),
            num,
        ),
    )

    reply_markup = InlineKeyboardMarkup(
        [[InlineKeyboardButton("✅ ɢᴇᴛ ꜰɪʟᴇ ✅", url=get_file_url)]]
    )
    sent = await message.reply_photo(
        photo=VERIFY_IMG,
        caption=complete_msg.format(message.from_user.mention),
        reply_markup=reply_markup,
        parse_mode=enums.ParseMode.HTML,
    )
    # Schedule the success card for auto-deletion (non-blocking).
    _schedule_autodelete(sent)
    return True


# ───────────────────────────  ⚡ Trinity Mods · @trinityXmods  ───────────────────────────


async def _deliver_payload(client, message, payload, send_count, files_counts):
    """
    Resolve a file/batch deep-link, enforce force-sub + verify + daily limits,
    then deliver the requested cached media to the user's PM.
    """
    user_id = message.from_user.id

    # Bounds-checked split: payload is normally `<pre>_<grp_id>_<file_id>`.
    bits = payload.split("_", 2)
    if len(bits) == 3:
        pre, grp_id, file_id = bits
    else:
        pre, grp_id, file_id = "", 0, payload

    # grp_id used for per-group settings lookup.
    try:
        grp_lookup = int(grp_id)
    except (TypeError, ValueError):
        grp_lookup = 0
    settings = await get_settings(grp_lookup)

    # ── Force-subscribe gate (request-join channel OR normal channel) ──
    if not await _force_sub_ok(client, message, settings, payload, grp_id, file_id):
        return

    # ── Verification gate (only for non-premium users when verify is enabled) ──
    if not await db.has_premium_access(user_id):
        if await _maybe_request_verification(
            client, message, settings, grp_id, file_id, payload
        ):
            return

    # ── allfiles_… → batch send-all delivery ──
    if payload.startswith("allfiles"):
        await _deliver_all(client, message, payload, grp_id, file_id, pre, send_count)
        return

    # ── Single file delivery ──
    await _deliver_single(
        client, message, payload, grp_id, file_id, pre, settings, files_counts
    )


async def _force_sub_ok(client, message, settings, payload, grp_id, file_id) -> bool:
    """
    Return True if the user satisfies force-sub, else send a Join card and False.
    Distinguishes the request-join channel from a normal force-sub channel.
    """
    fsub_id = settings.get("fsub_id", AUTH_CHANNEL)

    def _retry_button():
        kind = "allfiles" if payload.startswith("allfiles") else "files"
        return InlineKeyboardButton(
            "♻️ ᴛʀʏ ᴀɢᴀɪɴ ♻️",
            url=f"https://t.me/{temp.U_NAME}?start={kind}_{grp_id}_{file_id}",
        )

    # Case 1: group uses the request-to-join channel.
    if fsub_id == AUTH_REQ_CHANNEL:
        if AUTH_REQ_CHANNEL and not await is_req_subscribed(client, message):
            try:
                invite_link = await client.create_chat_invite_link(
                    int(AUTH_REQ_CHANNEL), creates_join_request=True
                )
            except ChatAdminRequired:
                logger.error("Bot must be admin in the force-sub (request) channel.")
                return False
            btn = [[InlineKeyboardButton("⛔️ ᴊᴏɪɴ ɴᴏᴡ ⛔️", url=invite_link.invite_link)]]
            if payload != "subscribe":
                btn.append([_retry_button()])
            await client.send_message(
                chat_id=message.from_user.id,
                text=phrases.FSUB_TXT.format(message.from_user.mention),
                reply_markup=InlineKeyboardMarkup(btn),
                parse_mode=enums.ParseMode.HTML,
            )
            return False
        return True

    # Case 2: normal channel membership.
    if fsub_id:
        try:
            channel = int(fsub_id)
        except (TypeError, ValueError):
            logger.error("Invalid fsub_id configured: %r", fsub_id)
            return True  # misconfig — don't block delivery
        if not await is_subscribed(client, message.from_user.id, channel):
            invite_link = await client.create_chat_invite_link(
                channel, creates_join_request=True
            )
            btn = [[InlineKeyboardButton("⛔️ ᴊᴏɪɴ ɴᴏᴡ ⛔️", url=invite_link.invite_link)]]
            if payload != "subscribe":
                btn.append([_retry_button()])
            await client.send_message(
                chat_id=message.from_user.id,
                text=phrases.FSUB_TXT.format(message.from_user.mention),
                reply_markup=InlineKeyboardMarkup(btn),
                parse_mode=enums.ParseMode.HTML,
            )
            return False
    return True


async def _maybe_request_verification(
    client, message, settings, grp_id, file_id, payload
) -> bool:
    """
    If verification is required and not yet satisfied, send the verify card and
    return True (caller should stop). Otherwise return False.
    """
    user_id = message.from_user.id
    is_verify = settings["is_verify"]
    if not is_verify:
        is_verify = await db.get_setting("IS_VERIFY", default=IS_VERIFY)

    user_verified = await db.is_user_verified(user_id)
    is_second = await db.use_second_shortener(
        user_id, settings.get("verify_time", TWO_VERIFY_GAP)
    )
    is_third = await db.use_third_shortener(
        user_id, settings.get("verify_time", THIRD_VERIFY_GAP)
    )

    if not ((not user_verified or is_second or is_third) and is_verify):
        return False

    verify_id = "".join(random.choices(string.ascii_uppercase + string.digits, k=7))
    await db.create_verify_id(user_id, verify_id)
    temp.CHAT[user_id] = grp_id

    tutorial = (
        settings.get("tutorial3", TUTORIAL3) if is_third
        else settings.get("tutorial2", TUTORIAL2) if is_second
        else settings.get("tutorial", TUTORIAL)
    )

    if payload.startswith("allfiles"):
        target = f"https://telegram.me/{temp.U_NAME}?start=sendall_{user_id}_{verify_id}_{file_id}"
    else:
        target = f"https://telegram.me/{temp.U_NAME}?start=verify_{user_id}_{verify_id}_{file_id}"
    verify_url = await get_shortlink(target, grp_id, is_second, is_third)

    # Third button differs depending on whether a free trial is still available.
    if not await db.check_trial_status(user_id):
        third_btn = InlineKeyboardButton(
            "✨5 ᴍɪɴ Pʀᴇᴍɪᴜᴍ Tʀᴀɪʟ✨", callback_data="give_trial"
        )
    else:
        third_btn = InlineKeyboardButton(
            "✨ ʀᴇᴍᴏᴠᴇ ᴠᴇʀɪғʏ ✨", callback_data="premium_info"
        )
    reply_markup = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✅️ ᴠᴇʀɪғʏ ✅️", url=verify_url)],
            [InlineKeyboardButton("⁉️ ʜᴏᴡ ᴛᴏ ᴠᴇʀɪғʏ ⁉️", url=tutorial)],
            [third_btn],
        ]
    )

    if await db.user_verified(user_id):
        msg = phrases.THIRDT_VERIFICATION_TEXT
    else:
        msg = phrases.SECOND_VERIFICATION_TEXT if is_second else phrases.VERIFICATION_TEXT

    card = await message.reply_text(
        text=msg.format(message.from_user.mention),
        protect_content=False,
        reply_markup=reply_markup,
        parse_mode=enums.ParseMode.HTML,
    )
    # Auto-clean the verify prompt (and the user's trigger) without blocking.
    _schedule_autodelete(card, message)
    return True


async def _deliver_all(client, message, payload, grp_id, file_id, pre, send_count):
    """Deliver every cached file behind an `allfiles_<...>` send-all link."""
    user_id = message.from_user.id
    files = temp.GETALL.get(file_id)
    if not files:
        return await message.reply("<b><i>ɴᴏ ꜱᴜᴄʜ ꜰɪʟᴇ ᴇxɪꜱᴛꜱ.</i></b>")

    settings = await get_settings(int(grp_id)) if str(grp_id).lstrip("-").isdigit() else await get_settings(0)
    caption_tpl = settings.get("caption", CUSTOM_FILE_CAPTION)
    sent_files = []

    for file in files:
        f_id = file.file_id
        details = await get_file_details(f_id)
        if not details:
            continue
        meta = details[0]
        f_caption = caption_tpl.format(
            file_name=meta.file_name,
            file_size=get_size(meta.file_size),
            file_caption=meta.caption,
        )

        # Daily send-all limit for non-premium users.
        if not await db.has_premium_access(user_id):
            limit = settings.get("all_limit", SEND_ALL_LIMITE)
            if settings.get("filelock", LIMIT_MODE):
                await db.update_files(user_id, "send_all", send_count + 1)
                used = await db.files_count(user_id, "send_all")
                f_caption += f"<b>\n\nAʟʟ Bᴜᴛᴛᴏɴ Lɪᴍɪᴛ : {used}/{limit}</b>"
                if send_count is not None and send_count >= limit:
                    reply_markup = InlineKeyboardMarkup(
                        [[InlineKeyboardButton("✨ Rᴇᴍᴏᴠᴇ Lɪᴍɪᴛ ✨", callback_data="premium_info")]]
                    )
                    return await message.reply_text(phrases.BUTTON_LIMIT, reply_markup=reply_markup)

        reply_markup = InlineKeyboardMarkup(
            [[InlineKeyboardButton("🖥️ ᴡᴀᴛᴄʜ / ᴅᴏᴡɴʟᴏᴀᴅ 📥", callback_data=f"streaming#{f_id}#{grp_id}")]]
        )
        sent = await client.send_cached_media(
            chat_id=user_id,
            file_id=f_id,
            caption=f_caption,
            protect_content=(pre == "filep"),
            reply_markup=reply_markup,
        )
        sent_files.append(sent)

    # Auto-delete reminder + scheduled cleanup (non-blocking).
    if await db.get_setting("AUTO_FILE_DELETE", default=AUTO_FILE_DELETE):
        notice = await client.send_message(
            chat_id=user_id,
            text=(
                "<b><u>❗️❗️❗️ʀᴇᴍɪɴᴅᴇʀ❗️️❗️❗️</u></b>\n\n"
                "ᴛʜᴇ ꜰɪʟᴇꜱ ꜱʜᴀʟʟ ʙᴇ ᴅᴇʟᴇᴛᴇᴅ ꜱᴏᴏɴ 🫥 <i>(ᴅᴜᴇ ᴛᴏ ᴄᴏᴘʏʀɪɢʜᴛ ɪꜱꜱᴜᴇs)</i>.\n\n"
                "<b><i>ᴘʟᴇᴀꜱᴇ ꜰᴏʀᴡᴀʀᴅ ᴀʟʟ ᴛʜᴇ ꜰɪʟᴇꜱ ᴛᴏ ʏᴏᴜʀ ꜱᴀᴠᴇᴅ ᴍᴇꜱꜱᴀɢᴇꜱ ᴀɴᴅ ꜱᴛᴀʀᴛ ᴅᴏᴡɴʟᴏᴀᴅɪɴɢ ᴛʜᴇᴍ ᴛʜᴇʀᴇ</i></b>"
            ),
        )
        _schedule_autodelete(*sent_files, notice=notice)


async def _deliver_single(
    client, message, payload, grp_id, file_id, pre, settings, files_counts
):
    """Deliver one cached file behind a `files_<...>` / base64 link."""
    user_id = message.from_user.id
    details = await get_file_details(file_id)

    if not details:
        # Legacy base64 link: decode `<pre>_<file_id>` (re-pad before decode).
        try:
            padded = payload + "=" * (-len(payload) % 4)
            decoded = base64.urlsafe_b64decode(padded).decode("ascii")
            pre, file_id = decoded.split("_", 1)
        except (ValueError, UnicodeDecodeError, base64.binascii.Error) as err:
            logger.info("base64 deep-link decode failed: %s", err)
            return await message.reply("Nᴏ sᴜᴄʜ ғɪʟᴇ ᴇxɪꜱᴛꜱ.")

        try:
            if not await db.has_premium_access(user_id):
                limit = settings.get("file_limit", FILE_LIMITE)
                if settings.get("filelock", LIMIT_MODE):
                    await db.update_files(user_id, "files_count", files_counts + 1)
                    used = await db.files_count(user_id, "files_count")
                    if files_counts is not None and files_counts >= limit:
                        reply_markup = InlineKeyboardMarkup(
                            [[InlineKeyboardButton("✨ Rᴇᴍᴏᴠᴇ Lɪᴍɪᴛ ✨", callback_data="premium_info")]]
                        )
                        return await message.reply_text(phrases.FILE_LIMIT, reply_markup=reply_markup)

            reply_markup = InlineKeyboardMarkup(
                [[InlineKeyboardButton("🖥️ ᴡᴀᴛᴄʜ / ᴅᴏᴡɴʟᴏᴀᴅ 📥", callback_data=f"streaming#{file_id}#{grp_id}")]]
            )
            sent = await client.send_cached_media(
                chat_id=user_id,
                file_id=file_id,
                protect_content=(pre == "filep"),
                reply_markup=reply_markup,
            )
            media_type = sent.media
            media = getattr(sent, media_type.value)
            title = media.file_name
            size = get_size(media.file_size)
            f_caption = f"<code>{title}</code>"
            if CUSTOM_FILE_CAPTION:
                try:
                    f_caption = CUSTOM_FILE_CAPTION.format(
                        file_name="" if title is None else title,
                        file_size="" if size is None else size,
                        file_caption="",
                    )
                except (KeyError, IndexError) as err:
                    logger.warning("custom caption format failed: %s", err)
                    f_caption = f"<code>{title}</code>"
            await sent.edit_caption(f_caption)
            return
        except Exception as err:  # noqa: BLE001
            logger.warning("legacy file delivery failed: %s", err)
            return await message.reply("Nᴏ sᴜᴄʜ ғɪʟᴇ ᴇxɪꜱᴛꜱ.")

    # Modern path: details found directly.
    meta = details[0]
    settings = await get_settings(int(grp_id)) if str(grp_id).lstrip("-").isdigit() else settings
    caption_tpl = settings.get("caption", CUSTOM_FILE_CAPTION)
    f_caption = caption_tpl.format(
        file_name=meta.file_name,
        file_size=get_size(meta.file_size),
        file_caption=meta.caption,
    )

    if not await db.has_premium_access(user_id):
        limit = settings.get("file_limit", FILE_LIMITE)
        if settings.get("filelock", LIMIT_MODE):
            await db.update_files(user_id, "files_count", files_counts + 1)
            used = await db.files_count(user_id, "files_count")
            f_caption += f"<b>\n\nDᴀɪʟʏ Fɪʟᴇ Lɪᴍɪᴛ: {used}/{limit}</b>"
            if files_counts is not None and files_counts >= limit:
                reply_markup = InlineKeyboardMarkup(
                    [[InlineKeyboardButton("✨ Rᴇᴍᴏᴠᴇ Lɪᴍɪᴛ ✨", callback_data="premium_info")]]
                )
                return await message.reply_text(phrases.FILE_LIMIT, reply_markup=reply_markup)

    reply_markup = InlineKeyboardMarkup(
        [[InlineKeyboardButton("🖥️ ᴡᴀᴛᴄʜ / ᴅᴏᴡɴʟᴏᴀᴅ 📥", callback_data=f"streaming#{file_id}#{grp_id}")]]
    )
    sent = await client.send_cached_media(
        chat_id=user_id,
        file_id=file_id,
        caption=f_caption,
        protect_content=(pre == "filep"),
        reply_markup=reply_markup,
    )

    if await db.get_setting("AUTO_FILE_DELETE", default=AUTO_FILE_DELETE):
        notice = await message.reply(
            "<b>⚠️ᴛʜɪs ғɪʟᴇ ᴡɪʟʟ ʙᴇ ᴅᴇʟᴇᴛᴇᴅ ꜱᴏᴏɴ\n\n"
            "ᴘʟᴇᴀsᴇ ғᴏʀᴡᴀʀᴅ ᴛʜᴇ ғɪʟᴇ sᴏᴍᴇᴡʜᴇʀᴇ ʙᴇғᴏʀᴇ ᴅᴏᴡɴʟᴏᴀᴅɪɴɢ..</b>"
        )
        _schedule_autodelete(sent, notice=notice)


# ──────────────────────────────────────────────────────────────────────────────
# Admin: indexed channel info / logs / single + bulk DB deletes
# ──────────────────────────────────────────────────────────────────────────────
@Client.on_message(filters.command("channel") & filters.user(ADMINS))
async def channel_info(bot, message):
    """List every indexed channel/group (file → document if too long)."""
    if isinstance(CHANNELS, (int, str)):
        channels = [CHANNELS]
    elif isinstance(CHANNELS, list):
        channels = CHANNELS
    else:
        raise ValueError("Uɴᴇxᴘᴇᴄᴛᴇᴅ ᴛʏᴘᴇ ᴏғ ᴄʜᴀɴɴᴇʟꜱ")

    text = "📑 **Iɴᴅᴇxᴇᴅ ᴄʜᴀɴɴᴇʟs/ɢʀᴏᴜᴘs**\n"
    for channel in channels:
        chat = await bot.get_chat(channel)
        if chat.username:
            text += "\n@" + chat.username
        else:
            text += "\n" + (chat.title or chat.first_name)
    text += f"\n\n**Total:** {len(channels)}"

    if len(text) < 4096:
        await message.reply(text)
    else:
        path = "Indexed channels.txt"
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        await message.reply_document(path)
        if os.path.exists(path):
            os.remove(path)


@Client.on_message(filters.command("logs") & filters.user(ADMINS))
async def log_file(bot, message):
    """Send the runtime log file."""
    try:
        await message.reply_document("Logs.txt")
    except Exception as err:  # noqa: BLE001 — file may not exist yet
        await message.reply(str(err))


@Client.on_message(filters.command("delete") & filters.user(ADMINS))
async def delete(bot, message):
    """Delete one file (the replied media) from the database."""
    reply = message.reply_to_message
    if reply and reply.media:
        status = await message.reply("Pʀᴏᴄᴇssɪɴɢ...⏳", quote=True)
    else:
        return await message.reply(
            "Rᴇᴘʟʏ ᴛᴏ ғɪʟᴇ ᴡɪᴛʜ /delete ᴡʜɪᴄʜ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ ᴅᴇʟᴇᴛᴇ", quote=True
        )

    for file_type in ("document", "video", "audio"):
        media = getattr(reply, file_type, None)
        if media is not None:
            break
    else:
        return await status.edit("Tʜɪs ɪs ɴᴏᴛ sᴜᴘᴘᴏʀᴛᴇᴅ ғɪʟᴇ ғᴏʀᴍᴀᴛ")

    if not getattr(media, "file_id", None):
        return await status.edit("Cᴏᴜʟᴅ ɴᴏᴛ ʀᴇᴀᴅ ᴛʜᴇ ғɪʟᴇ ɪᴅ.")
    file_id, _file_ref = unpack_new_file_id(media.file_id)

    result = await Media.collection.delete_one({"_id": file_id})
    if result.deleted_count:
        return await status.edit("Fɪʟᴇ ɪs sᴜᴄᴄᴇssғᴜʟʟʏ ᴅᴇʟᴇᴛᴇᴅ ғʀᴏᴍ ᴅᴀᴛᴀʙᴀsᴇ")

    # Fall back to matching on the cleaned file name + size + mime.
    import re as _re
    cleaned_name = _re.sub(r"(_|\-|\.|\+)", " ", str(media.file_name))
    result = await Media.collection.delete_many(
        {"file_name": cleaned_name, "file_size": media.file_size, "mime_type": media.mime_type}
    )
    if result.deleted_count:
        return await status.edit("Fɪʟᴇ ɪs sᴜᴄᴄᴇssғᴜʟʟʏ ᴅᴇʟᴇᴛᴇᴅ ғʀᴏᴍ ᴅᴀᴛᴀʙᴀsᴇ")

    # Files indexed before the EvaMaria filename-clean commit keep the raw name.
    result = await Media.collection.delete_many(
        {"file_name": media.file_name, "file_size": media.file_size, "mime_type": media.mime_type}
    )
    if result.deleted_count:
        await status.edit("Fɪʟᴇ ɪs sᴜᴄᴄᴇssғᴜʟʟʏ ᴅᴇʟᴇᴛᴇᴅ ғʀᴏᴍ ᴅᴀᴛᴀʙᴀsᴇ")
    else:
        await status.edit("Fɪʟᴇ ɴᴏᴛ ғᴏᴜɴᴅ ɪɴ ᴅᴀᴛᴀʙᴀsᴇ")


@Client.on_message(filters.command("deleteall") & filters.user(ADMINS))
async def delete_all_index(bot, message):
    """Confirm before nuking the entire media collection."""
    await message.reply_text(
        "Tʜɪs ᴡɪʟʟ ᴅᴇʟᴇᴛᴇ ᴀʟʟ ɪɴᴅᴇxᴇᴅ ғɪʟᴇs.\nDᴏ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ ᴄᴏɴᴛɪɴᴜᴇ ?",
        reply_markup=InlineKeyboardMarkup(
            [
                [InlineKeyboardButton(text="Yᴇs", callback_data="autofilter_delete")],
                [InlineKeyboardButton(text="Cᴀɴᴄᴇʟ", callback_data="close_data")],
            ]
        ),
        quote=True,
    )


@Client.on_callback_query(filters.regex(r"^autofilter_delete"))
async def delete_all_index_confirm(bot, message):
    """Drop the whole media collection after confirmation."""
    await Media.collection.drop()
    await message.answer("Eᴠᴇʀʏᴛʜɪɴɢ's Gᴏɴᴇ")
    await message.message.edit("Sᴜᴄᴄᴇsғᴜʟʟʏ Dᴇʟᴇᴛᴇᴅ Aʟʟ Tʜᴇ Iɴᴅᴇxᴇᴅ Fɪʟᴇs.")


# ──────────────────────────────────────────────────────────────────────────────
# /settings — per-group control panel
# ──────────────────────────────────────────────────────────────────────────────
@Client.on_message(filters.command("settings"))
async def settings(client, message):
    userid = message.from_user.id if message.from_user else None
    if not userid:
        return await message.reply(
            f"Yᴏᴜ ᴀʀᴇ ᴀɴᴏɴʏᴍᴏᴜs ᴀᴅᴍɪɴ. Usᴇ /connect {message.chat.id} ɪɴ PM"
        )
    chat_type = message.chat.type

    if chat_type == enums.ChatType.PRIVATE:
        grpid = await active_connection(str(userid))
        if grpid is None:
            return await message.reply_text("I'ᴍ ɴᴏᴛ ᴄᴏɴɴᴇᴄᴛᴇᴅ ᴛᴏ ᴀɴʏ ɢʀᴏᴜᴘs !", quote=True)
        grp_id = grpid
        try:
            chat = await client.get_chat(grpid)
            title = chat.title
        except Exception as err:  # noqa: BLE001
            logger.info("settings: cannot fetch connected chat: %s", err)
            return await message.reply_text(
                "Mᴀᴋᴇ sᴜʀᴇ I'ᴍ ᴘʀᴇsᴇɴᴛ ɪɴ ʏᴏᴜʀ ɢʀᴏᴜᴘ !", quote=True
            )
    elif chat_type in (enums.ChatType.GROUP, enums.ChatType.SUPERGROUP):
        grp_id = message.chat.id
        title = message.chat.title
    else:
        return

    st = await client.get_chat_member(grp_id, userid)
    if (
        st.status != enums.ChatMemberStatus.ADMINISTRATOR
        and st.status != enums.ChatMemberStatus.OWNER
        and not _is_admin(userid)
    ):
        return

    settings = await get_settings(grp_id)
    # Ensure max_btn key exists (older groups may lack it).
    try:
        _ = settings["max_btn"]
    except KeyError:
        await save_group_settings(grp_id, "max_btn", False)
        settings = await get_settings(grp_id)

    if settings is None:
        return

    buttons = [
        [
            InlineKeyboardButton("Rᴇꜱᴜʟᴛ Pᴀɢᴇ", callback_data=f'setgs#button#{settings["button"]}#{grp_id}'),
            InlineKeyboardButton("Tᴇxᴛ" if settings["button"] else "Bᴜᴛᴛᴏɴ", callback_data=f'setgs#button#{settings["button"]}#{grp_id}'),
        ],
        [
            InlineKeyboardButton("Iᴍᴅʙ", callback_data=f'setgs#imdb#{settings["imdb"]}#{grp_id}'),
            InlineKeyboardButton("✔ Oɴ" if settings["imdb"] else "✘ Oғғ", callback_data=f'setgs#imdb#{settings["imdb"]}#{grp_id}'),
        ],
        [
            InlineKeyboardButton("Sᴘᴇʟʟ Cʜᴇᴄᴋ", callback_data=f'setgs#spell_check#{settings["spell_check"]}#{grp_id}'),
            InlineKeyboardButton("✔ Oɴ" if settings["spell_check"] else "✘ Oғғ", callback_data=f'setgs#spell_check#{settings["spell_check"]}#{grp_id}'),
        ],
        [
            InlineKeyboardButton("Wᴇʟᴄᴏᴍᴇ Msɢ", callback_data=f'setgs#welcome#{settings["welcome"]}#{grp_id}'),
            InlineKeyboardButton("✔ Oɴ" if settings["welcome"] else "✘ Oғғ", callback_data=f'setgs#welcome#{settings["welcome"]}#{grp_id}'),
        ],
        [
            InlineKeyboardButton("Aᴜᴛᴏ-Dᴇʟᴇᴛᴇ", callback_data=f'setgs#auto_delete#{settings["auto_delete"]}#{grp_id}'),
            InlineKeyboardButton("10 Mɪɴs" if settings["auto_delete"] else "✘ Oғғ", callback_data=f'setgs#auto_delete#{settings["auto_delete"]}#{grp_id}'),
        ],
        [
            InlineKeyboardButton("Aᴜᴛᴏ-Fɪʟᴛᴇʀ", callback_data=f'setgs#auto_ffilter#{settings["auto_ffilter"]}#{grp_id}'),
            InlineKeyboardButton("✔ 𝕋𝕣𝕦𝕖" if settings["auto_ffilter"] else "✘ 𝔽𝕒𝕝𝕤𝕖", callback_data=f'setgs#auto_ffilter#{settings["auto_ffilter"]}#{grp_id}'),
        ],
        [
            InlineKeyboardButton("Mᴀx Bᴜᴛᴛᴏɴs", callback_data=f'setgs#max_btn#{settings["max_btn"]}#{grp_id}'),
            InlineKeyboardButton("10" if settings["max_btn"] else f"{MAX_B_TN}", callback_data=f'setgs#max_btn#{settings["max_btn"]}#{grp_id}'),
        ],
        [
            InlineKeyboardButton("Fɪʟᴇ Lɪᴍɪᴛ", callback_data=f'setgs#filelock#{settings.get("filelock", LIMIT_MODE)}#{grp_id}'),
            InlineKeyboardButton("✔ Oɴ" if settings.get("filelock", LIMIT_MODE) else "✘ Oғғ", callback_data=f'setgs#filelock#{settings.get("filelock", LIMIT_MODE)}#{grp_id}'),
        ],
        [
            InlineKeyboardButton("Sᴛʀᴇᴀᴍ Sʜᴏʀᴛ", callback_data=f'setgs#stream_mode#{settings.get("stream_mode", STREAM_MODE)}#{grp_id}'),
            InlineKeyboardButton("✔ Oɴ" if settings.get("stream_mode", STREAM_MODE) else "✘ Oғғ", callback_data=f'setgs#stream_mode#{settings.get("stream_mode", STREAM_MODE)}#{grp_id}'),
        ],
        [
            InlineKeyboardButton("Vᴇʀɪғʏ", callback_data=f'setgs#is_verify#{settings.get("is_verify", IS_VERIFY)}#{grp_id}'),
            InlineKeyboardButton("✔ Oɴ" if settings.get("is_verify", IS_VERIFY) else "✘ Oғғ", callback_data=f'setgs#is_verify#{settings.get("is_verify", IS_VERIFY)}#{grp_id}'),
        ],
    ]

    if chat_type in (enums.ChatType.GROUP, enums.ChatType.SUPERGROUP):
        # In-group: offer to open the panel here or in PM.
        open_btn = [[
            InlineKeyboardButton("Oᴘᴇɴ Hᴇʀᴇ ↓", callback_data=f"opnsetgrp#{grp_id}"),
            InlineKeyboardButton("Oᴘᴇɴ Iɴ PM ⇲", callback_data=f"opnsetpm#{grp_id}"),
        ]]
        await message.reply_text(
            text="<b>Dᴏ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ ᴏᴘᴇɴ sᴇᴛᴛɪɴɢs ʜᴇʀᴇ ?</b>",
            reply_markup=InlineKeyboardMarkup(open_btn),
            disable_web_page_preview=True,
            parse_mode=enums.ParseMode.HTML,
            reply_to_message_id=message.id,
        )
    else:
        await message.reply_text(
            text=f"<b>Cʜᴀɴɢᴇ Yᴏᴜʀ Sᴇᴛᴛɪɴɢs Fᴏʀ {title} As ᴘᴇʀ Yᴏᴜʀ Wɪsʜ ⚙</b>",
            reply_markup=InlineKeyboardMarkup(buttons),
            disable_web_page_preview=True,
            parse_mode=enums.ParseMode.HTML,
            reply_to_message_id=message.id,
        )


# ──────────────────────────────────────────────────────────────────────────────
# Tutorial setters (1 / 2 / 3)
# ──────────────────────────────────────────────────────────────────────────────
async def _set_tutorial(client, message, key, label):
    """Shared implementation for /set_tutorial[_2|_3]."""
    if message.chat.type not in (enums.ChatType.GROUP, enums.ChatType.SUPERGROUP):
        return await message.reply_text("<b>ᴜsᴇ ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ ɪɴ ɢʀᴏᴜᴘ!</b>")
    grp_id = message.chat.id
    title = message.chat.title
    invite_link = await client.export_chat_invite_link(grp_id)
    if not await _is_group_owner(client, message.chat.id, message.from_user.id):
        return await message.reply_text("<b>ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ᴀᴅᴍɪɴ ɪɴ ᴛʜɪꜱ ɢʀᴏᴜᴘ</b>")
    try:
        tutorial = message.text.split(" ", 1)[1]
    except IndexError:
        return await message.reply_text(
            "<b>Command Incomplete!!\n\nuse like this -</b>\n\n"
            "<code>/set_tutorial https://t.me/YourUpdatesChannel</code>"
        )
    await save_group_settings(grp_id, key, tutorial)
    await message.reply_text(
        f"<b>Successfully changed tutorial for {title}</b>\n\nLink - {tutorial}",
        disable_web_page_preview=True,
    )
    await client.send_message(
        LOG_CHANNEL,
        f"{label} for {title} (Group ID: {grp_id}, Invite Link: {invite_link}) "
        f"has been updated by {message.from_user.username}",
    )


@Client.on_message(filters.command("set_tutorial"))
async def set_tutorial_1(client, message):
    await _set_tutorial(client, message, "tutorial", "Tutorial")


@Client.on_message(filters.command("set_tutorial_2"))
async def set_tutorial_2(client, message):
    await _set_tutorial(client, message, "tutorial2", "Tutorial 2")


@Client.on_message(filters.command("set_tutorial_3"))
async def set_tutorial_3(client, message):
    await _set_tutorial(client, message, "tutorial3", "Tutorial 3")


# ──────────────────────────────────────────────────────────────────────────────
# Shortener setters (verify 1/2/3 + stream) — shared implementation
# ──────────────────────────────────────────────────────────────────────────────
async def _set_shortener(c, m, *, url_key, api_key, default_url, default_api,
                         log_tag, example, restart, usage):
    """
    Shared verify/stream shortener setter.

    FIX vs original: every parameter reference uses `m` (the real handler arg) —
    the legacy code referenced an undefined `message` here.
    """
    if m.chat.type not in (enums.ChatType.GROUP, enums.ChatType.SUPERGROUP):
        return await m.reply_text("<b>ᴜsᴇ ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ ɪɴ ɢʀᴏᴜᴘ...</b>")
    grp_id = m.chat.id
    if not await _is_group_owner(c, m.chat.id, m.from_user.id):
        return await m.reply_text("<b>ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ᴀᴅᴍɪɴ ɪɴ ᴛʜɪꜱ ɢʀᴏᴜᴘ</b>")
    if len(m.text.split()) == 1:
        return await m.reply(usage)

    sts = await m.reply("<b>♻️ ᴄʜᴇᴄᴋɪɴɢ...</b>")
    try:
        # Bounds-check before indexing command[1]/command[2].
        if len(m.command) < 3:
            raise ValueError("missing site/api argument")
        url = m.command[1]
        api = m.command[2]
        resp = requests.get(
            f"https://{url}/api?api={api}&url=https://telegram.dog/TrinityBotts"
        ).json()
        short_link = resp["shortenedUrl"] if resp.get("status") == "success" else "—"

        await save_group_settings(grp_id, url_key, url)
        await save_group_settings(grp_id, api_key, api)
        await sts.edit(
            f"<b><u>✅ ʏᴏᴜʀ ꜱʜᴏʀᴛᴇɴᴇʀ ɪꜱ ᴀᴅᴅᴇᴅ ꜱᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ</u>\n\n"
            f"ᴅᴇᴍᴏ - {short_link}\n\nsɪᴛᴇ - `{url}`\n\nᴀᴘɪ - `{api}`</b>"
        )
        user_info = f"@{m.from_user.username}" if m.from_user.username else f"{m.from_user.mention}"
        link = (await c.get_chat(m.chat.id)).invite_link
        grp_link = f"[{m.chat.title}]({link})"
        await c.send_message(
            LOG_CHANNEL,
            f"{log_tag}\n\nName - {user_info}\nId - `{m.from_user.id}`\n\n"
            f"Domain name - {url}\nApi - `{api}`\nGroup link - {grp_link}   `{grp_id}`",
            disable_web_page_preview=True,
        )
        # Verify shortener changes trigger a restart (stream does not).
        if restart:
            os.execl(sys.executable, sys.executable, *sys.argv)
    except Exception as err:  # noqa: BLE001 — fall back to defaults on any failure
        logger.warning("%s setter failed: %s", log_tag, err)
        await save_group_settings(grp_id, url_key, default_url)
        await save_group_settings(grp_id, api_key, default_api)
        await sts.edit(
            f"<b><u>❌ ᴇʀʀᴏʀ ᴏᴄᴄᴏᴜʀᴇᴅ ❌</u>\n\nᴀᴜᴛᴏ ᴀᴅᴅᴇᴅ ᴅᴇꜰᴜʟᴛ sʜᴏʀᴛɴᴇʀ\n\n"
            "ɪꜰ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ ᴄʜᴀɴɢᴇ ᴛʜᴇɴ ᴜsᴇ ᴄᴏʀʀᴇᴄᴛ ꜰᴏʀᴍᴀᴛ ᴏʀ ᴀᴅᴅ ᴠᴀʟɪᴅ sʜᴏʀᴛʟɪɴᴋ ᴅᴏᴍᴀɪɴ ɴᴀᴍᴇ & ᴀᴘɪ\n\n"
            f"ʏᴏᴜ ᴄᴀɴ ᴀʟsᴏ ᴄᴏɴᴛᴀᴄᴛ ᴏᴜʀ <a href=https://t.me/{SUPPORT_CHAT}>ꜱᴜᴘᴘᴏʀᴛ</a> ꜰᴏʀ sᴏʟᴠᴇ ᴛʜɪs ɪssᴜᴇ...\n\n"
            f"ʟɪᴋᴇ -\n\n`{example}`\n\n💔 ᴇʀʀᴏʀ - <code>{err}</code></b>"
        )


@Client.on_message(filters.command("set_verify"))
async def set_verify(c, m):
    await _set_shortener(
        c, m,
        url_key="verify", api_key="verify_api",
        default_url=VERIFY_URL, default_api=VERIFY_API,
        log_tag="#New_Shortner_Set_For_1st_Verify",
        example="/set_verify droplink.co 5c6377b71bb8c36629bad14b3c67d9749c4f62e6",
        restart=True,
        usage="<b>Use this command like this - \n\n`/set_verify ziplinker.net c992d5c6d3a74f6ceccbf9bc34aa27c8487c11d2`</b>",
    )


@Client.on_message(filters.command("set_verify2"))
async def set_verify2(c, m):
    await _set_shortener(
        c, m,
        url_key="verify_2", api_key="verify_api2",
        default_url=VERIFY_URL2, default_api=VERIFY_API2,
        log_tag="#New_Shortner_Set_For_2nd_Verify",
        example="/set_verify2 shortyfi.link 465d89bf8d7b71277a822b890f7cc3e2489acf73",
        restart=True,
        usage="<b>Use this command like this - \n\n`/set_verify2 tnshort.net 06b24eb6bbb025713cd522fb3f696b6d5de11354`</b>",
    )


@Client.on_message(filters.command("set_verify3"))
async def set_verify3(c, m):
    await _set_shortener(
        c, m,
        url_key="verify_3", api_key="verify_api3",
        default_url=VERIFY_URL3, default_api=VERIFY_API3,
        log_tag="#New_Shortner_Set_For_3nd_Verify",
        example="/set_verify3 droplink.co 5c6377b71bb8c36629bad14b3c67d9749c4f62e6",
        restart=True,
        usage="<b>Use this command like this - \n\n`/set_verify3 tnshort.net 06b24eb6bbb025713cd522fb3f696b6d5de11354`</b>",
    )


@Client.on_message(filters.command("set_stream"))
async def set_stream(c, m):
    await _set_shortener(
        c, m,
        url_key="streamsite", api_key="streamapi",
        default_url=STREAM_SITE, default_api=STREAM_API,
        log_tag="#New_Stream_link_set",
        example="/set_stream sharedisklinks.com 587f94f0e0b1813a52aed61290af6ea79d6ee464",
        restart=False,
        usage="<b>ᴜꜱᴇ ᴄᴏᴍᴍᴀɴᴅ ɪɴ ᴛʜɪꜱ ᴍᴀɴɴᴇʀ - \n\n`/set_stream tnshort.net 06b24eb6bbb025713cd522fb3f696b6d5de11354`</b>",
    )


# ──────────────────────────────────────────────────────────────────────────────
# Caption / force-sub / log channel setters
# ──────────────────────────────────────────────────────────────────────────────
@Client.on_message(filters.command("set_caption"))
async def save_caption(client, message):
    if message.chat.type not in (enums.ChatType.GROUP, enums.ChatType.SUPERGROUP):
        return await message.reply_text("<b>ᴜsᴇ ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ ɪɴ ɢʀᴏᴜᴘ...</b>")
    grp_id = message.chat.id
    title = message.chat.title
    invite_link = await client.export_chat_invite_link(grp_id)
    if not await _is_group_owner(client, message.chat.id, message.from_user.id):
        return await message.reply_text("<b>ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ᴀᴅᴍɪɴ ɪɴ ᴛʜɪꜱ ɢʀᴏᴜᴘ</b>")
    try:
        caption = message.text.split(" ", 1)[1]
    except IndexError:
        return await message.reply_text(
            "<code>ɢɪᴠᴇ ᴍᴇ ᴀ ᴄᴀᴘᴛɪᴏɴ ᴀʟᴏɴɢ ᴡɪᴛʜ ɪᴛ.\n\nᴇxᴀᴍᴘʟᴇ -\n\n"
            "ꜰᴏʀ ꜰɪʟᴇ ɴᴀᴍᴇ ꜱᴇɴᴅ {file_name}\nꜰᴏʀ ꜰɪʟᴇ ꜱɪᴢᴇ ꜱᴇɴᴅ {file_size}\n\n"
            "/set_caption {file_name}</code>"
        )
    await save_group_settings(grp_id, "caption", caption)
    await message.reply_text(
        f"Successfully changed caption for {title}\n\nCaption - {caption}",
        disable_web_page_preview=True,
    )
    await client.send_message(
        LOG_CHANNEL,
        f"Caption for {title} (Group ID: {grp_id}, Invite Link: {invite_link}) "
        f"has been updated by {message.from_user.username}",
    )


@Client.on_message(filters.command("set_fsub"))
async def set_fsub(client, message):
    if message.chat.type not in (enums.ChatType.GROUP, enums.ChatType.SUPERGROUP):
        return await message.reply_text("<b>ᴜsᴇ ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ ɪɴ ɢʀᴏᴜᴘ...</b>")
    grp_id = message.chat.id
    title = message.chat.title
    if not await _is_group_owner(client, message.chat.id, message.from_user.id):
        return await message.reply_text("<b>ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ᴀᴅᴍɪɴ ɪɴ ᴛʜɪꜱ ɢʀᴏᴜᴘ</b>")
    try:
        channel_id = int(message.text.split(" ", 1)[1])
    except IndexError:
        return await message.reply_text(
            "<b>ᴄᴏᴍᴍᴀɴᴅ ɪɴᴄᴏᴍᴘʟᴇᴛᴇ\n\nꜱᴇɴᴅ ᴍᴇ ᴄʜᴀɴɴᴇʟ ɪᴅ ᴡɪᴛʜ ᴄᴏᴍᴍᴀɴᴅ, ʟɪᴋᴇ <code>/set_fsub -100******</code></b>"
        )
    except ValueError:
        return await message.reply_text("<b>ᴍᴀᴋᴇ ꜱᴜʀᴇ ᴛʜᴇ ɪᴅ ɪꜱ ᴀɴ ɪɴᴛᴇɢᴇʀ.</b>")
    try:
        chat = await client.get_chat(channel_id)
    except Exception as err:  # noqa: BLE001
        return await message.reply_text(
            f"<b><code>{channel_id}</code> ɪꜱ ɪɴᴠᴀʟɪᴅ. ᴍᴀᴋᴇ ꜱᴜʀᴇ "
            f"<a href=https://t.me/{temp.B_LINK}>ʙᴏᴛ</a> ɪꜱ ᴀᴅᴍɪɴ ɪɴ ᴛʜᴀᴛ ᴄʜᴀɴɴᴇʟ\n\n<code>{err}</code></b>"
        )
    if chat.type != enums.ChatType.CHANNEL:
        return await message.reply_text(
            f"🫥 <code>{channel_id}</code> ᴛʜɪꜱ ɪꜱ ɴᴏᴛ ᴄʜᴀɴɴᴇʟ, ꜱᴇɴᴅ ᴍᴇ ᴏɴʟʏ ᴄʜᴀɴɴᴇʟ ɪᴅ ɴᴏᴛ ɢʀᴏᴜᴘ ɪᴅ"
        )
    await save_group_settings(grp_id, "fsub_id", channel_id)
    await client.send_message(
        LOG_CHANNEL,
        f"#Fsub_Channel_set\n\nUser - {message.from_user.mention} set the force channel "
        f"for {title}:\n\nFsub channel - {chat.title}\nId - `{channel_id}`",
    )
    await message.reply_text(
        f"<b>ꜱᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ ꜱᴇᴛ ꜰᴏʀᴄᴇ ꜱᴜʙꜱᴄʀɪʙᴇ ᴄʜᴀɴɴᴇʟ ꜰᴏʀ {title}\n\n"
        f"ᴄʜᴀɴɴᴇʟ ɴᴀᴍᴇ - {chat.title}\nɪᴅ - <code>{channel_id}</code></b>"
    )


@Client.on_message(filters.command("remove_fsub"))
async def remove_fsub(client, message):
    if message.chat.type not in (enums.ChatType.GROUP, enums.ChatType.SUPERGROUP):
        return await message.reply_text("<b>ᴜsᴇ ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ ɪɴ ɢʀᴏᴜᴘ!</b>")
    grp_id = message.chat.id
    title = message.chat.title
    if not await _is_group_owner(client, message.chat.id, message.from_user.id):
        return await message.reply_text("<b>ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ᴀᴅᴍɪɴ ɪɴ ᴛʜɪꜱ ɢʀᴏᴜᴘ</b>")
    settings = await get_settings(grp_id)
    if settings["fsub_id"] == AUTH_CHANNEL:
        await message.reply_text(
            "<b>ᴄᴜʀʀᴇɴᴛʟʏ ɴᴏ ᴀᴄᴛɪᴠᴇ ꜰᴏʀᴄᴇ ꜱᴜʙ ᴄʜᴀɴɴᴇʟ ɪꜱ ꜰᴏᴜɴᴅ... <code>[ᴅᴇғᴀᴜʟᴛ ᴀᴄᴛɪᴠᴀᴛᴇ]</code></b>"
        )
    else:
        await save_group_settings(grp_id, "fsub_id", AUTH_CHANNEL)
        await client.send_message(
            LOG_CHANNEL,
            f"#Remove_Fsub_Channel\n\nUser - {message.from_user.mention} he remove fsub channel from {title}",
        )
        await message.reply_text("<b>✅ ꜱᴜᴄᴄᴇꜱꜱғᴜʟʟʏ ʀᴇᴍᴏᴠᴇᴅ ғᴏʀᴄᴇ ꜱᴜʙ ᴄʜᴀɴɴᴇʟ.</b>")


@Client.on_message(filters.command("set_log"))
async def set_log(client, message):
    """FIX: the original referenced an undefined `m` here — now uses `message`."""
    if message.chat.type not in (enums.ChatType.GROUP, enums.ChatType.SUPERGROUP):
        return await message.reply_text("<b>ᴜsᴇ ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ ɪɴ ɢʀᴏᴜᴘ...</b>")
    grp_id = message.chat.id
    title = message.chat.title
    if not await _is_group_owner(client, message.chat.id, message.from_user.id):
        return await message.reply_text("<b>ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ᴀᴅᴍɪɴ ɪɴ ᴛʜɪꜱ ɢʀᴏᴜᴘ</b>")
    if len(message.text.split()) == 1:
        return await message.reply("<b>Use this command like this - \n\n`/set_log -100******`</b>")

    sts = await message.reply("<b>♻️ ᴄʜᴇᴄᴋɪɴɢ...</b>")
    await asyncio.sleep(1.2)
    await sts.delete()
    try:
        log = int(message.text.split(" ", 1)[1])
    except IndexError:
        return await message.reply_text(
            "<b><u>ɪɴᴠᴀɪʟᴅ ꜰᴏʀᴍᴀᴛ!!</u>\n\nᴜsᴇ ʟɪᴋᴇ ᴛʜɪs - `/set_log -100xxxxxxxx`</b>"
        )
    except ValueError:
        return await message.reply_text("<b>ᴍᴀᴋᴇ sᴜʀᴇ ɪᴅ ɪs ɪɴᴛᴇɢᴇʀ...</b>")
    try:
        ping = await client.send_message(chat_id=log, text="<b>ʜᴇʏ ᴡʜᴀᴛ's ᴜᴘ!!</b>")
        await asyncio.sleep(3)
        await ping.delete()
    except Exception as err:  # noqa: BLE001
        return await message.reply_text(
            f"<b><u>😐 ᴍᴀᴋᴇ sᴜʀᴇ ᴛʜɪs ʙᴏᴛ ᴀᴅᴍɪɴ ɪɴ ᴛʜᴀᴛ ᴄʜᴀɴɴᴇʟ...</u>\n\n💔 ᴇʀʀᴏʀ - <code>{err}</code></b>"
        )
    await save_group_settings(grp_id, "log", log)
    await message.reply_text(
        f"<b>✅ sᴜᴄᴄᴇssꜰᴜʟʟʏ sᴇᴛ ʏᴏᴜʀ ʟᴏɢ ᴄʜᴀɴɴᴇʟ ꜰᴏʀ {title}\n\nɪᴅ - `{log}`</b>",
        disable_web_page_preview=True,
    )
    # FIX: build the log line from `message`, not the undefined legacy `m`.
    user_info = (
        f"@{message.from_user.username}" if message.from_user.username
        else f"{message.from_user.mention}"
    )
    link = (await client.get_chat(message.chat.id)).invite_link
    grp_link = f"[{message.chat.title}]({link})"
    await client.send_message(
        LOG_CHANNEL,
        f"#New_Log_Channel_Set\n\nName - {user_info}\nId - `{message.from_user.id}`\n\n"
        f"Log channel id - `{log}`\nGroup link - {grp_link}   `{grp_id}`",
        disable_web_page_preview=True,
    )


# ──────────────────────────────────────────────────────────────────────────────
# /details — dump the group's full settings
# ──────────────────────────────────────────────────────────────────────────────
@Client.on_message(filters.command("details"))
async def all_settings(client, message):
    if message.chat.type not in (enums.ChatType.GROUP, enums.ChatType.SUPERGROUP):
        return await message.reply_text("<b>ᴜsᴇ ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ ɪɴ ɢʀᴏᴜᴘ...</b>")
    grp_id = message.chat.id
    title = message.chat.title
    if not await _is_group_owner(client, message.chat.id, message.from_user.id):
        return await message.reply_text("<b>ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ᴀᴅᴍɪɴ ɪɴ ᴛʜɪꜱ ɢʀᴏᴜᴘ</b>")
    settings = await get_settings(grp_id)
    # FIX: original had a broken `u>` (missing opening `<`) on the third-verify line.
    text = f"""<b><u>⚙️ ʏᴏᴜʀ sᴇᴛᴛɪɴɢs ꜰᴏʀ -</u> {title}

<u>✅️ 1sᴛ ᴠᴇʀɪꜰʏ sʜᴏʀᴛɴᴇʀ ɴᴀᴍᴇ/ᴀᴘɪ</u>
ɴᴀᴍᴇ - `{settings.get("verify", VERIFY_URL)}`
ᴀᴘɪ - `{settings.get("verify_api", VERIFY_API)}`

<u>✅️ 2ɴᴅ ᴠᴇʀɪꜰʏ sʜᴏʀᴛɴᴇʀ ɴᴀᴍᴇ/ᴀᴘɪ</u>
ɴᴀᴍᴇ - `{settings.get("verify_2", VERIFY_URL2)}`
ᴀᴘɪ - `{settings.get("verify_api2", VERIFY_API2)}`

<u>✅️ ᴛʜɪʀᴅ ᴠᴇʀɪꜰʏ sʜᴏʀᴛɴᴇʀ ɴᴀᴍᴇ/ᴀᴘɪ</u>
ɴᴀᴍᴇ - `{settings.get("verify_3", VERIFY_URL3)}`
ᴀᴘɪ - `{settings.get("verify_api3", VERIFY_API3)}`

🧭 2ɴᴅ ᴠᴇʀɪꜰɪᴄᴀᴛɪᴏɴ ᴛɪᴍᴇ ɢᴀᴘ - `{settings.get("verify_time", TWO_VERIFY_GAP)}`

🧭 ᴛʜɪʀᴅ ᴠᴇʀɪꜰɪᴄᴀᴛɪᴏɴ ᴛɪᴍᴇ ɢᴀᴘ - `{settings.get("verify_time2", THIRD_VERIFY_GAP)}`

📝 ʟᴏɢ ᴄʜᴀɴɴᴇʟ ɪᴅ - `{settings.get('log', LOG_CHANNEL)}`

🌀 ғᴏʀᴄᴇ ᴄʜᴀɴɴᴇʟ - `{settings.get('fsub_id', AUTH_CHANNEL)}`

1️⃣ ᴛᴜᴛᴏʀɪᴀʟ ʟɪɴᴋ 1 - {settings.get('tutorial', TUTORIAL)}

2️⃣ ᴛᴜᴛᴏʀɪᴀʟ ʟɪɴᴋ 2 - {settings.get('tutorial2', TUTORIAL2)}

3️⃣ ᴛᴜᴛᴏʀɪᴀʟ ʟɪɴᴋ 3 - {settings.get('tutorial3', TUTORIAL3)}

📂 ꜰɪʟᴇ ᴄᴀᴘᴛɪᴏɴ - `{settings.get('caption', CUSTOM_FILE_CAPTION)}`

📁 ᴅᴀɪʟʏ ғɪʟᴇ ʟɪᴍɪᴛ - `{settings.get('file_limit', FILE_LIMITE)}`

📀 sᴇᴅɴ ᴀʟʟ ʙᴜᴛᴛᴏɴ ʟɪᴍɪᴛ - `{settings.get('all_limit', SEND_ALL_LIMITE)}`

🎯 ɪᴍᴅʙ ᴛᴇᴍᴘʟᴀᴛᴇ - `{settings.get('template', IMDB_TEMPLATE)}`</b>"""

    reply_markup = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("ʀᴇꜱᴇᴛ ᴅᴀᴛᴀ", callback_data="reset_grp_data")],
            [InlineKeyboardButton("ᴄʟᴏsᴇ", callback_data="close_data")],
        ]
    )
    card = await message.reply_text(text, reply_markup=reply_markup, disable_web_page_preview=True)
    # Non-blocking auto-clean after 5 minutes (kept identical timing via a task).
    async def _clean():
        await asyncio.sleep(300)
        try:
            await card.delete()
        except (MessageIdInvalid, MessageDeleteForbidden):
            pass
    asyncio.create_task(_clean())


# ──────────────────────────────────────────────────────────────────────────────
# Verify-gap / file-limit / send-limit setters (shared numeric setter)
# ──────────────────────────────────────────────────────────────────────────────
async def _set_numeric(client, message, *, key, usage, success, log_line):
    """Shared implementation for the integer-valued group setters."""
    if message.chat.type not in (enums.ChatType.GROUP, enums.ChatType.SUPERGROUP):
        return await message.reply_text("<b>ᴜsᴇ ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ ɪɴ ɢʀᴏᴜᴘ!</b>")
    grp_id = message.chat.id
    title = message.chat.title
    invite_link = await client.export_chat_invite_link(grp_id)
    if not await _is_group_owner(client, message.chat.id, message.from_user.id):
        return await message.reply_text("<b>ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ᴀᴅᴍɪɴ ɪɴ ᴛʜɪꜱ ɢʀᴏᴜᴘ</b>")
    parts = message.text.split(" ", 1)
    if len(parts) < 2:
        return await message.reply_text(usage)
    try:
        value = int(parts[1])
    except ValueError:
        return await message.reply_text(usage)
    await save_group_settings(grp_id, key, value)
    await message.reply_text(success.format(title=title, value=value))
    await client.send_message(
        LOG_CHANNEL,
        log_line.format(
            value=value, title=title, grp_id=grp_id, invite_link=invite_link,
            user=message.from_user.username,
        ),
    )


@Client.on_message(filters.command("verify_gap"))
async def verify_gap(client, message):
    await _set_numeric(
        client, message, key="verify_time",
        usage="<b>ᴄᴏᴍᴍᴀɴᴅ ɪɴᴄᴏᴍᴘʟᴇᴛᴇ\n\nᴜꜱᴇ ᴛʜɪꜱ ᴄᴏᴍᴍᴀɴᴅ ʟɪᴋᴇ ᴛʜɪꜱ - <code>/verify_gap 600</code> [ ᴛɪᴍᴇ ᴍᴜꜱᴛ ʙᴇ ɪɴ ꜱᴇᴄᴏɴᴅꜱ ]</b>",
        success="<b>✅️ ꜱᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ ꜱᴇᴛ 2ɴᴅ ᴠᴇʀɪꜰʏ ᴛɪᴍᴇ ꜰᴏʀ {title}\n\nᴛɪᴍᴇ - <code>{value}</code></b>",
        log_line="2nd verify time for {title} (Group ID: {grp_id}, Invite Link: {invite_link}) has been updated by {user}",
    )


@Client.on_message(filters.command("verify_gap2"))
async def verify_gap2(client, message):
    await _set_numeric(
        client, message, key="verify_time2",
        usage="<b>ᴄᴏᴍᴍᴀɴᴅ ɪɴᴄᴏᴍᴘʟᴇᴛᴇ\n\nᴜꜱᴇ ᴛʜɪꜱ ᴄᴏᴍᴍᴀɴᴅ ʟɪᴋᴇ ᴛʜɪꜱ - <code>/verify_gap2 600</code> [ ᴛɪᴍᴇ ᴍᴜꜱᴛ ʙᴇ ɪɴ ꜱᴇᴄᴏɴᴅꜱ ]</b>",
        success="<b>✅️ ꜱᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ ꜱᴇᴛ ᴛʜɪʀᴅ ᴠᴇʀɪꜰʏ ᴛɪᴍᴇ ꜰᴏʀ {title}\n\nᴛɪᴍᴇ - <code>{value}</code></b>",
        log_line="third verify time for {title} (Group ID: {grp_id}, Invite Link: {invite_link}) has been updated by {user}",
    )


@Client.on_message(filters.command("set_file_limit"))
async def set_file_limit(client, message):
    await _set_numeric(
        client, message, key="file_limit",
        usage="<b>ᴄᴏᴍᴍᴀɴᴅ ɪɴᴄᴏᴍᴘʟᴇᴛᴇ\n\nᴜꜱᴇ ᴛʜɪꜱ ᴄᴏᴍᴍᴀɴᴅ ʟɪᴋᴇ ᴛʜɪꜱ - <code>/set_file_limit 15</code></b>",
        success="<b>✅️ ꜱᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ ꜱᴇᴛ ғɪʟᴇ ʟɪᴍɪᴛ ꜰᴏʀ {title}\n\nғɪʟᴇ ʟɪᴍɪᴛ - <u><code>{value}</code></u></b>",
        log_line="file limit seted `{value}` for {title} (Group ID: {grp_id}, Invite Link: {invite_link}) has been updated by {user}",
    )


@Client.on_message(filters.command("set_send_limit"))
async def set_send_limit(client, message):
    await _set_numeric(
        client, message, key="all_limit",
        usage="<b>ᴄᴏᴍᴍᴀɴᴅ ɪɴᴄᴏᴍᴘʟᴇᴛᴇ\n\nᴜꜱᴇ ᴛʜɪꜱ ᴄᴏᴍᴍᴀɴᴅ ʟɪᴋᴇ ᴛʜɪꜱ - <code>/set_send_limit 3</code></b>",
        success="<b>✅️ ꜱᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ ꜱᴇᴛ sᴇɴᴅ ʙᴜᴛᴛᴏɴ ʟɪᴍɪᴛ ꜰᴏʀ {title}\n\nsᴇɴᴅ ʙᴜᴛᴛᴏɴ ʟɪᴍɪᴛ - <u><code>{value}</code></u></b>",
        log_line="send button limit seted `{value}` for {title} (Group ID: {grp_id}, Invite Link: {invite_link}) has been updated by {user}",
    )


# ──────────────────────────────────────────────────────────────────────────────
# Template setters
# ──────────────────────────────────────────────────────────────────────────────
@Client.on_message(filters.command("set_template"))
async def save_template(client, message):
    if message.chat.type not in (enums.ChatType.GROUP, enums.ChatType.SUPERGROUP):
        return await message.reply_text("<b>ᴜꜱᴇ ᴛʜɪꜱ ᴄᴏᴍᴍᴀɴᴅ ɪɴ ɢʀᴏᴜᴘ...</b>")
    grp_id = message.chat.id
    title = message.chat.title
    if not await _is_group_owner(client, message.chat.id, message.from_user.id):
        return await message.reply_text("<b>ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ᴀᴅᴍɪɴ ɪɴ ᴛʜɪꜱ ɢʀᴏᴜᴘ</b>")
    try:
        template = message.text.split(" ", 1)[1]
    except IndexError:
        return await message.reply_text("Command Incomplete!")
    await save_group_settings(grp_id, "template", template)
    await message.reply_text(
        f"Successfully changed template for {title} to\n\n{template}",
        disable_web_page_preview=True,
    )


@Client.on_message(filters.command("del_template"))
async def delete_template(client, message):
    sts = await message.reply("Dᴇʟᴇᴛɪɴɢ ᴛᴇᴍᴘʟᴀᴛᴇ...")
    userid = message.from_user.id if message.from_user else None
    if not userid:
        return await message.reply(
            f"Yᴏᴜ ᴀʀᴇ ᴀɴᴏɴʏᴍᴏᴜs ᴀᴅᴍɪɴ. Usᴇ /connect {message.chat.id} ɪɴ PM"
        )
    chat_type = message.chat.type

    if chat_type == enums.ChatType.PRIVATE:
        grpid = await active_connection(str(userid))
        if grpid is None:
            return await message.reply_text("I'ᴍ ɴᴏᴛ ᴄᴏɴɴᴇᴄᴛᴇᴅ ᴛᴏ ᴀɴʏ ɢʀᴏᴜᴘs!", quote=True)
        grp_id = grpid
        try:
            chat = await client.get_chat(grpid)
            title = chat.title
        except Exception as err:  # noqa: BLE001
            logger.info("del_template: cannot fetch connected chat: %s", err)
            return await message.reply_text(
                "Mᴀᴋᴇ sᴜʀᴇ I'ᴍ ᴘʀᴇsᴇɴᴛ ɪɴ ʏᴏᴜʀ ɢʀᴏᴜᴘ!!", quote=True
            )
    elif chat_type in (enums.ChatType.GROUP, enums.ChatType.SUPERGROUP):
        grp_id = message.chat.id
        title = message.chat.title
    else:
        return

    st = await client.get_chat_member(grp_id, userid)
    if (
        st.status != enums.ChatMemberStatus.ADMINISTRATOR
        and st.status != enums.ChatMemberStatus.OWNER
        and not _is_admin(userid)
    ):
        return

    # Reset the template back to the default.
    await save_group_settings(grp_id, "template", IMDB_TEMPLATE)
    await sts.edit(f"Sᴜᴄᴄᴇssғᴜʟʟʏ ᴅᴇʟᴇᴛᴇᴅ ᴛᴇᴍᴘʟᴀᴛᴇ ғᴏʀ {title}.")


# ──────────────────────────────────────────────────────────────────────────────
# Admin tools: targeted /send, /deletefiles, /restart, /set_value
# ──────────────────────────────────────────────────────────────────────────────
@Client.on_message(filters.command("send") & filters.user(ADMINS))
async def send_msg(bot, message):
    """Copy a replied message to a single target user (if they exist in DB)."""
    if not message.reply_to_message:
        return await message.reply_text(
            "<b>Usᴇ ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ ᴀs ᴀ ʀᴇᴘʟʏ ᴛᴏ ᴀɴʏ ᴍᴇssᴀɢᴇ ᴜsɪɴɢ ᴛʜᴇ ᴛᴀʀɢᴇᴛ ᴄʜᴀᴛ ɪᴅ. "
            "Fᴏʀ ᴇɢ: /send ᴜsᴇʀɪᴅ</b>"
        )
    parts = message.text.split(" ", 1)
    if len(parts) < 2:
        return await message.reply_text("<b>Pʟᴇᴀsᴇ ᴘʀᴏᴠɪᴅᴇ ᴀ ᴛᴀʀɢᴇᴛ ᴜsᴇʀ ɪᴅ. Eɢ: /send ᴜsᴇʀɪᴅ</b>")
    target_id = parts[1]
    try:
        user = await bot.get_users(target_id)
        out = "Usᴇʀs Sᴀᴠᴇᴅ Iɴ DB Aʀᴇ:\n\n"
        async for usr in await db.get_all_users():
            out += f"{usr['id']}\n"
        if str(user.id) in out:
            await message.reply_to_message.copy(int(user.id))
            await message.reply_text(
                f"<b>Yᴏᴜʀ ᴍᴇssᴀɢᴇ ʜᴀs ʙᴇᴇɴ sᴜᴄᴄᴇssғᴜʟʟʏ ꜱᴇɴᴛ ᴛᴏ {user.mention}.</b>"
            )
        else:
            await message.reply_text("<b>Tʜɪs ᴜsᴇʀ ᴅɪᴅ ɴᴏᴛ ᴇᴠᴇɴ ꜱᴛᴀʀᴛ ᴛʜᴇ ʙᴏᴛ ʏᴇᴛ! 🤣</b>")
    except Exception as err:  # noqa: BLE001
        await message.reply_text(f"<b>Eʀʀᴏʀ: {err}</b>")


@Client.on_message(filters.command("deletefiles") & filters.user(ADMINS))
async def deletemultiplefiles(bot, message):
    """Confirm a keyword-based bulk file delete (PM only)."""
    if message.chat.type != enums.ChatType.PRIVATE:
        return await message.reply_text(
            f"<b>Hᴇʏ {message.from_user.mention}, Tʜɪs ᴄᴏᴍᴍᴀɴᴅ ᴡᴏɴ'ᴛ ᴡᴏʀᴋ ɪɴ ɢʀᴏᴜᴘs. "
            "Iᴛ ᴏɴʟʏ ᴡᴏʀᴋs ᴏɴ ᴍʏ PM!</b>"
        )
    parts = message.text.split(" ", 1)
    if len(parts) < 2:
        return await message.reply_text(
            f"<b>Hᴇʏ {message.from_user.mention}, Gɪᴠᴇ ᴍᴇ ᴀ ᴋᴇʏᴡᴏʀᴅ ᴀʟᴏɴɢ ᴡɪᴛʜ ᴛʜᴇ ᴄᴏᴍᴍᴀɴᴅ ᴛᴏ ᴅᴇʟᴇᴛᴇ ғɪʟᴇs.</b>"
        )
    keyword = parts[1]
    btn = [
        [InlineKeyboardButton("Yᴇs, Cᴏɴᴛɪɴᴜᴇ !", callback_data=f"killfilesdq#{keyword}")],
        [InlineKeyboardButton("Nᴏ, Aʙᴏʀᴛ ᴏᴘᴇʀᴀᴛɪᴏɴ !", callback_data="close_data")],
    ]
    await message.reply_text(
        text="<b>Aʀᴇ ʏᴏᴜ sᴜʀᴇ? Dᴏ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ ᴄᴏɴᴛɪɴᴜᴇ?\n\n"
        "Nᴏᴛᴇ:- Tʜɪs ᴄᴏᴜʟᴅ ʙᴇ ᴀ ᴅᴇsᴛʀᴜᴄᴛɪᴠᴇ ᴀᴄᴛɪᴏɴ!</b>",
        reply_markup=InlineKeyboardMarkup(btn),
        parse_mode=enums.ParseMode.HTML,
    )


@Client.on_message(filters.command("restart") & filters.user(ADMINS))
async def stop_button(bot, message):
    """Restart the process (re-exec)."""
    msg = await bot.send_message(
        text="<b><i>ʙᴏᴛ ɪꜱ ʀᴇꜱᴛᴀʀᴛɪɴɢ</i></b>", chat_id=message.chat.id
    )
    await asyncio.sleep(3)
    await msg.edit("<b><i><u>ʙᴏᴛ ɪꜱ ʀᴇꜱᴛᴀʀᴛᴇᴅ</u> ✅</i></b>")
    os.execl(sys.executable, sys.executable, *sys.argv)


@Client.on_message(filters.command("set_value") & filters.user(ADMINS))
async def set_mode(client, message):
    """Toggle a global runtime mode flag (stored in DB settings)."""
    try:
        args = message.text.split()
        if len(args) == 3:
            mode_name = args[1]
            value = args[2].lower() == "true"  # string → boolean
            valid_modes = ["PM_FILTER", "IS_VERIFY", "LIMIT_MODE", "AUTO_FILE_DELETE"]
            if mode_name in valid_modes:
                await db.set_setting(mode_name, value)
                await message.reply(f"{mode_name} has been set to {value}.")
            else:
                await message.reply(
                    "Invalid mode name. Please use one of the following:\n\n"
                    "PM_FILTER\n\nIS_VERIFY\nLIMIT_MODE\nAUTO_FILE_DELETE"
                )
        else:
            await message.reply(
                "Please specify the mode name and 'True' or 'False' as arguments. "
                "Example: /set_value PM_FILTER True"
            )
    except Exception as err:  # noqa: BLE001
        await message.reply(f"An error occurred: {err}")


# ═══════════════════════════════════════════════════════════════════════════════
#  ⚡ Crafted by Trinity Mods (@trinityXmods) · Trinity AutoFilter
#  If this code helped you, keep the credit alive → github.com/Trinity-Mods
#  🚫 This credit is license-locked. See brand.py.
# ═══════════════════════════════════════════════════════════════════════════════
