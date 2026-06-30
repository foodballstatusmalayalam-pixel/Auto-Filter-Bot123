# ═══════════════════════════════════════════════════════════════════════════════
#  ⚡ TRINITY MODS · TRINITY AUTOFILTER
#  Consolidated admin/user toolkit — /id, /info, IMDb search, new-group welcome,
#  group lifecycle (leave/disable/enable/invite), moderation (ban/unban) and stats.
#  ─────────────────────────────────────────────────────────────────────────────
#  Developed & maintained by Trinity Mods (@trinityXmods)
#  GitHub   : github.com/Trinity-Mods
#  Source   : github.com/Trinity-Mods/Auto-Filter-Bot
#  Telegram : t.me/trinityXmods
#  🚫 Credit is license-locked — see brand.py. Please keep this header intact.
# ═══════════════════════════════════════════════════════════════════════════════
"""
Trinity AutoFilter · handlers/toolkit.py

This single module merges what the legacy tree split across ``plugins/misc.py``
and its EXACT duplicate ``plugins/p_ttishow.py``.  Everything now lives here once:

    user/info utilities ......... /id, /info, /imdb (+ /search), imdb# callback
    group lifecycle ............. new-group save + welcome, /leave, /disable,
                                  /enable, /invite
    moderation .................. /ban, /unban
    listings & stats ............ /stats, /users, /chats

All handlers register straight onto the Pyrogram ``Client`` via the smart-plugin
decorators, exactly like the originals, so behaviour and command names are
preserved 1:1.
"""

import os
import asyncio
import logging
from datetime import datetime

from pyrogram import Client, filters, enums
from pyrogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    CallbackQuery,
)
from pyrogram.errors import ChatAdminRequired
from pyrogram.errors.exceptions.bad_request_400 import (
    UserNotParticipant,
    MediaEmpty,
    PhotoInvalidDimensions,
    WebpageMediaEmpty,
    MessageTooLong,
    PeerIdInvalid,
)

# ── Import contract (new module layout) ───────────────────────────────────────
from config import (
    IMDB_TEMPLATE,
    ADMINS,
    LOG_CHANNEL,
    SUPPORT_CHAT,
    MELCOW_NEW_USERS,
    WELCOME_VID,
    CHNL_LNK,
    GRP_LNK,
    AUTO_DELETE_TIME,
)
from phrases import phrases
from toolbox import temp, get_settings, get_size, get_poster, extract_user, get_file_id
from vault.media_index import Media
from vault.registry import db

# Module logger — replaces the old bare ``except:`` swallowing with real logs.
logger = logging.getLogger(__name__)


# IMDb template fields we explicitly feed into ``.format(...)``.  The legacy code
# leaked ``**locals()`` into the format call; we now pass ONLY the documented keys
# so an unrelated local can never collide with a template placeholder.
_IMDB_FIELDS = (
    "query", "title", "votes", "aka", "seasons", "box_office", "localized_title",
    "kind", "imdb_id", "cast", "runtime", "countries", "certificates", "languages",
    "director", "writer", "producer", "composer", "cinematographer", "music_team",
    "distributors", "release_date", "year", "genres", "poster", "plot", "rating",
    "url",
)


def _support_url() -> str:
    """Build the support-chat deep link from config (was hardcoded 'YourSupportBot')."""
    return f"https://t.me/{SUPPORT_CHAT}"


def _close_markup() -> InlineKeyboardMarkup:
    """Reusable single-row 'Close' keyboard shared by the info cards."""
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔐 Close", callback_data="close_data")]])


# ══════════════════════════════════════════════════════════════════════════════
#  USER / INFO UTILITIES
# ══════════════════════════════════════════════════════════════════════════════

@Client.on_message(filters.command("id"))
async def show_id(client, message):
    """`/id` — report the relevant Telegram IDs for the current context."""
    chat_type = message.chat.type

    if chat_type == enums.ChatType.PRIVATE:
        # Private chat: report the requesting user's own identity card.
        user_id = message.chat.id
        first = message.from_user.first_name
        last = message.from_user.last_name or ""
        username = message.from_user.username
        dc_id = message.from_user.dc_id or ""
        await message.reply_text(
            f"<b>➲ First Name:</b> {first}\n"
            f"<b>➲ Last Name:</b> {last}\n"
            f"<b>➲ Username:</b> {username}\n"
            f"<b>➲ Telegram ID:</b> <code>{user_id}</code>\n"
            f"<b>➲ Data Centre:</b> <code>{dc_id}</code>",
            quote=True,
        )
        return

    if chat_type in (enums.ChatType.GROUP, enums.ChatType.SUPERGROUP):
        # Group chat: chat id + (optionally) the replied user's id + any file id.
        lines = [f"<b>➲ Chat ID</b>: <code>{message.chat.id}</code>\n"]
        author = message.from_user.id if message.from_user else "Anonymous"

        if message.reply_to_message:
            replied = (
                message.reply_to_message.from_user.id
                if message.reply_to_message.from_user
                else "Anonymous"
            )
            lines.append(f"<b>➲ User ID</b>: <code>{author}</code>\n")
            lines.append(f"<b>➲ Replied User ID</b>: <code>{replied}</code>\n")
            file_info = get_file_id(message.reply_to_message)
        else:
            lines.append(f"<b>➲ User ID</b>: <code>{author}</code>\n")
            file_info = get_file_id(message)

        if file_info:
            lines.append(f"<b>{file_info.message_type}</b>: <code>{file_info.file_id}</code>\n")

        await message.reply_text("".join(lines), quote=True)


@Client.on_message(filters.command(["info"]))
async def who_is(client, message):
    """`/info` — fetch and display a user's profile card (with DP when available)."""
    status_message = await message.reply_text("`Fetching user info...`")
    await status_message.edit("`Processing user info...`")

    # Resolve the target from reply/argument/self.
    from_user_id, _ = extract_user(message)
    try:
        from_user = await client.get_users(from_user_id)
    except Exception as error:  # get_users raises a variety of RPC errors
        logger.warning("info: get_users failed for %s: %s", from_user_id, error)
        await status_message.edit(str(error))
        return

    if from_user is None:
        await status_message.edit("no valid user_id / message specified")
        return

    # Build the profile card text.
    last_name = from_user.last_name or "<b>None</b>"
    username = from_user.username or "<b>None</b>"
    dc_id = from_user.dc_id or "[User Doesn't Have A Valid DP]"
    card = (
        f"<b>➲First Name:</b> {from_user.first_name}\n"
        f"<b>➲Last Name:</b> {last_name}\n"
        f"<b>➲Telegram ID:</b> <code>{from_user.id}</code>\n"
        f"<b>➲Data Centre:</b> <code>{dc_id}</code>\n"
        f"<b>➲User Name:</b> @{username}\n"
        f"<b>➲User 𝖫𝗂𝗇𝗄:</b> <a href='tg://user?id={from_user.id}'><b>Click Here</b></a>\n"
    )

    # In groups/channels, annotate when the user joined this chat.
    if message.chat.type in (enums.ChatType.SUPERGROUP, enums.ChatType.CHANNEL):
        try:
            chat_member_p = await message.chat.get_member(from_user.id)
            joined_date = (chat_member_p.joined_date or datetime.now()).strftime(
                "%Y.%m.%d %H:%M:%S"
            )
            card += f"<b>➲Joined this Chat on:</b> <code>{joined_date}</code>\n"
        except UserNotParticipant:
            pass

    reply_markup = _close_markup()
    chat_photo = from_user.photo

    if chat_photo:
        # Download the big DP, send it as a photo card, then clean the temp file.
        local_user_photo = await client.download_media(message=chat_photo.big_file_id)
        await message.reply_photo(
            photo=local_user_photo,
            quote=True,
            reply_markup=reply_markup,
            caption=card,
            parse_mode=enums.ParseMode.HTML,
            disable_notification=True,
        )
        # FIX: guard os.remove — the download path may already be gone / never written.
        try:
            if local_user_photo and os.path.exists(local_user_photo):
                os.remove(local_user_photo)
        except OSError as cleanup_err:
            logger.warning("info: could not remove temp photo %s: %s", local_user_photo, cleanup_err)
    else:
        await message.reply_text(
            text=card,
            reply_markup=reply_markup,
            quote=True,
            parse_mode=enums.ParseMode.HTML,
            disable_notification=True,
        )

    await status_message.delete()


@Client.on_message(filters.command(["imdb", "search"]))
async def imdb_search(client, message):
    """`/imdb` / `/search <name>` — list IMDb matches as inline buttons."""
    if " " in message.text:
        searching = await message.reply("Searching ImDB")
        _, title = message.text.split(None, 1)
        movies = await get_poster(title, bulk=True)
        if not movies:
            await searching.edit("No results Found")
            return
        buttons = [
            [
                InlineKeyboardButton(
                    text=f"{movie.get('title')} - {movie.get('year')}",
                    callback_data=f"imdb#{movie.movieID}",
                )
            ]
            for movie in movies
        ]
        await searching.edit(
            "Here is what i found on IMDb",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
    else:
        await message.reply("Give me a movie / series Name")


@Client.on_callback_query(filters.regex("^imdb"))
async def imdb_callback(bot: Client, query: CallbackQuery):
    """Render the full IMDb card when a user taps one of the search results."""
    _, movie_id = query.data.split("#")
    imdb = await get_poster(query=movie_id, id=True)

    if imdb:
        # FIX: build the format kwargs from the documented field list ONLY, instead
        # of leaking ``**locals()`` into template.format(...).
        fields = {key: imdb.get(key) for key in _IMDB_FIELDS}
        # ``query`` placeholder historically mirrors the resolved title.
        fields["query"] = imdb.get("title")
        caption = IMDB_TEMPLATE.format(**fields)
        link_button = [[InlineKeyboardButton(text=f"{imdb.get('title')}", url=imdb["url"])]]
    else:
        caption = "No Results"
        link_button = []

    markup = InlineKeyboardMarkup(link_button) if link_button else None

    if imdb and imdb.get("poster"):
        try:
            await query.message.reply_photo(
                photo=imdb["poster"], caption=caption, reply_markup=markup
            )
        except (MediaEmpty, PhotoInvalidDimensions, WebpageMediaEmpty):
            # Telegram occasionally rejects the raw poster — retry the resized variant.
            poster = imdb["poster"].replace(".jpg", "._V1_UX360.jpg")
            await query.message.reply_photo(
                photo=poster, caption=caption, reply_markup=markup
            )
        except Exception as exc:  # noqa: BLE001 — last-resort text fallback
            logger.exception("imdb_callback: poster send failed: %s", exc)
            await query.message.reply(
                caption, reply_markup=markup, disable_web_page_preview=False
            )
        await query.message.delete()
    else:
        await query.message.edit(
            caption, reply_markup=markup, disable_web_page_preview=False
        )

    await query.answer()


# ───────────────────────────  ⚡ Trinity Mods · @trinityXmods  ───────────────────────────


# ══════════════════════════════════════════════════════════════════════════════
#  NEW-GROUP SAVE + WELCOME
# ══════════════════════════════════════════════════════════════════════════════

@Client.on_message(filters.new_chat_members & filters.group)
async def save_group(bot, message):
    """Persist freshly-added groups, greet members, and enforce the ban list."""
    joined_ids = [u.id for u in message.new_chat_members]

    # Branch 1: the bot itself was added to a new group.
    if temp.ME in joined_ids:
        if not await db.get_chat(message.chat.id):
            total = await bot.get_chat_members_count(message.chat.id)
            added_by = message.from_user.mention if message.from_user else "Anonymous"
            await bot.send_message(
                LOG_CHANNEL,
                phrases.LOG_TEXT_G.format(
                    temp.B_NAME, message.chat.title, message.chat.id, total, added_by
                ),
            )
            await db.add_chat(message.chat.id, message.chat.title, message.from_user.id)

        # If this chat is on the banned list, announce + leave immediately.
        if message.chat.id in temp.BANNED_CHATS:
            # FIX: GRP_NLK was a typo for GRP_LNK.
            buttons = [[InlineKeyboardButton("Support", url=GRP_LNK)]]
            notice = await message.reply(
                text=(
                    "<b>CHAT NOT ALLOWED 🐞\n\nMy admins has restricted me from "
                    "working here ! If you want to know more about it contact "
                    "support..</b>"
                ),
                reply_markup=InlineKeyboardMarkup(buttons),
            )
            try:
                await notice.pin()
            except Exception as pin_err:  # not admin / pin disabled
                logger.info("save_group: could not pin ban notice: %s", pin_err)
            await bot.leave_chat(message.chat.id)
            return

        # Normal welcome for the bot's own arrival.
        await message.reply_text(
            text=(
                f"<b>ᴛʜᴀɴᴋ ʏᴏᴜ ғᴏʀ ᴀᴅᴅɪɴɢ ᴍᴇ ɪɴ {message.chat.title} ɢʀᴏᴜᴘ ❣️\n\n"
                "ɪғ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ ᴛᴀᴋᴇ ꜰɪʟᴇꜱ ɪɴ ᴛʜɪs ɢʀᴏᴜᴘ,\n\n"
                "ᴛʜᴇɴ ғɪʀsᴛ ʏᴏᴜ ʜᴀᴠᴇ ᴛᴏ ᴠᴇʀɪғʏ ᴛʜᴇ ɢʀᴏᴜᴘ.\n\n"
                "ᴠᴇʀɪғʏ ᴛʜᴇ ɢʀᴏᴜᴘ ᴡɪᴛʜ /verify ᴄᴏᴍᴍᴀɴᴅ! ⌛</b>"
            )
        )
        return

    # Branch 2: ordinary users joined — greet them if welcome is enabled.
    settings = await get_settings(message.chat.id)
    if settings.get("welcome"):
        for user in message.new_chat_members:
            # Replace the previous welcome message (one greeting at a time).
            previous = temp.MELCOW.get("welcome")
            if previous is not None:
                try:
                    await previous.delete()
                except Exception as del_err:
                    logger.info("save_group: stale welcome delete failed: %s", del_err)
            temp.MELCOW["welcome"] = await message.reply_video(
                video=WELCOME_VID,
                caption=phrases.MELCOW_ENG.format(user.mention, message.chat.title),
                parse_mode=enums.ParseMode.HTML,
            )

    # Tidy up the service "X joined" message.
    await message.delete()

    # Optionally auto-delete the welcome after the configured window.
    if settings.get("auto_delete"):
        welcome_msg = temp.MELCOW.get("welcome")
        if welcome_msg is not None:
            # Schedule rather than blocking the handler on a magic sleep(600).
            asyncio.create_task(_expire_welcome(welcome_msg, AUTO_DELETE_TIME))


async def _expire_welcome(welcome_msg, delay):
    """Background task: wait ``delay`` seconds then drop the welcome message."""
    try:
        await asyncio.sleep(delay)
        await welcome_msg.delete()
    except Exception as exc:
        logger.info("welcome auto-delete failed: %s", exc)


# ══════════════════════════════════════════════════════════════════════════════
#  GROUP LIFECYCLE  (admin-only)
# ══════════════════════════════════════════════════════════════════════════════

@Client.on_message(filters.command("leave") & filters.user(ADMINS))
async def leave_a_chat(bot, message):
    """`/leave <chat_id>` — post a farewell then leave the chat."""
    if len(message.command) == 1:
        await message.reply("ɢɪᴠᴇ ᴍᴇ ᴀ ᴄʜᴀᴛ ɪᴅ")
        return

    chat = message.command[1]
    try:
        chat = int(chat)
    except ValueError:
        pass  # allow @usernames as-is

    try:
        buttons = [[InlineKeyboardButton("Support", url=_support_url())]]
        await bot.send_message(
            chat_id=chat,
            text=(
                "<blockquote><b>ʜᴇʟʟᴏ, ᴘᴏᴏᴋɪᴇꜱ!</b></blockquote>\n\n"
                "ᴛʜᴇʀᴇ ʜᴀꜱ ʙᴇᴇɴ ᴀ ʙɪᴛ ᴏꜰ ᴀɴ ɪꜱꜱᴜᴇ ᴛʜᴀᴛ ᴍʏ ᴍᴏᴅᴇʀᴀᴛᴏʀꜱ ʙʀᴏᴜɢʜᴛ "
                "ᴜᴘ, ᴀɴᴅ ᴛʜᴇʏ ʜᴀᴠᴇ ᴀꜱᴋᴇᴅ ᴍᴇ ᴛᴏ ꜱᴛᴇᴘ ᴏᴜᴛ ᴏꜰ ᴛʜɪꜱ ɢʀᴏᴜᴘ ᴀɴᴅ "
                "ᴘᴀᴜꜱᴇ ᴍʏ ᴡᴏʀᴋ ʜᴇʀᴇ.\n\nᴛʜɪꜱ ᴍᴏꜱᴛʟʏ ʜᴀᴘᴘᴇɴᴇᴅ ʙᴇᴄᴀᴜꜱᴇ ᴛʜᴇ ɢʀᴏᴜᴘ "
                "ᴀᴅᴍɪɴꜱ ʜᴀᴠᴇ ɴᴏᴛ ʙᴇᴇɴ ꜰᴏʟʟᴏᴡɪɴɢ ᴛʜᴇ ᴘʀᴏᴘᴇʀ ɪɴꜱᴛʀᴜᴄᴛɪᴏɴꜱ ᴏɴ ʜᴏᴡ "
                "ᴛᴏ ᴜꜱᴇ ᴍᴇ.\n\nɪꜰ ʏᴏᴜ ᴛʜɪɴᴋ ᴛʜɪꜱ ᴅᴇᴄɪꜱɪᴏɴ ɪꜱ ᴀ ᴍɪꜱᴛᴀᴋᴇ ᴏʀ ʜᴀᴠᴇ "
                f"ᴀɴʏ Qᴜᴇꜱᴛɪᴏɴꜱ, ꜰᴇᴇʟ ꜰʀᴇᴇ ᴛᴏ ʀᴇᴀᴄʜ ᴏᴜᴛ ᴛᴏ ꜱᴜᴘᴘᴏʀᴛ ᴀᴛ @{SUPPORT_CHAT}"
            ),
            reply_markup=InlineKeyboardMarkup(buttons),
        )
        await bot.leave_chat(chat)
        await message.reply(f"left the chat `{chat}`")
    except Exception as exc:  # noqa: BLE001 — surface any RPC failure to the admin
        logger.warning("leave_a_chat failed for %s: %s", chat, exc)
        await message.reply(f"Error - {exc}")


@Client.on_message(filters.command("disable") & filters.user(ADMINS))
async def disable_chat(bot, message):
    """`/disable <chat_id> [reason]` — blacklist a chat and leave it."""
    if len(message.command) == 1:
        await message.reply("Give me a chat id")
        return

    parts = message.text.split(None)
    if len(parts) > 2:
        reason = message.text.split(None, 2)[2]
        chat = message.text.split(None, 2)[1]
    else:
        chat = message.command[1]
        reason = "No reason Provided"

    try:
        chat_id = int(chat)
    except ValueError:
        await message.reply("Give Me A Valid Chat ID")
        return

    record = await db.get_chat(chat_id)
    if not record:
        await message.reply("Chat Not Found In DB")
        return
    if record["is_disabled"]:
        await message.reply(
            f"This chat is already disabled:\nReason-<code> {record['reason']} </code>"
        )
        return

    await db.disable_chat(chat_id, reason)
    temp.BANNED_CHATS.append(chat_id)
    await message.reply("Chat Successfully Disabled")

    try:
        buttons = [[InlineKeyboardButton("Support", url=_support_url())]]
        await bot.send_message(
            chat_id=chat_id,
            text=(
                "<b>Hello Friends, \nMy admin has asked me to leave this group so i "
                f"need to get going! If you want to add me again contact my support "
                f"on @{SUPPORT_CHAT}</b> \nReason : <code>{reason}</code>"
            ),
            reply_markup=InlineKeyboardMarkup(buttons),
        )
        await bot.leave_chat(chat_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("disable_chat: leave failed for %s: %s", chat_id, exc)
        await message.reply(f"Error - {exc}")


@Client.on_message(filters.command("enable") & filters.user(ADMINS))
async def re_enable_chat(bot, message):
    """`/enable <chat_id>` — remove a chat from the blacklist."""
    if len(message.command) == 1:
        await message.reply("Give me a chat id")
        return

    try:
        chat_id = int(message.command[1])
    except ValueError:
        await message.reply("Give Me A Valid Chat ID")
        return

    record = await db.get_chat(chat_id)
    if not record:
        await message.reply("Chat Not Found In DB !")
        return
    if not record.get("is_disabled"):
        await message.reply("This chat is not yet disabled.")
        return

    await db.re_enable_chat(chat_id)
    # Only drop it if actually present, so a stale state can't raise ValueError.
    if chat_id in temp.BANNED_CHATS:
        temp.BANNED_CHATS.remove(chat_id)
    await message.reply("Chat Successfully re-enabled")


@Client.on_message(filters.command("invite") & filters.user(ADMINS))
async def gen_invite(bot, message):
    """`/invite <chat_id>` — mint an invite link for a chat we administer."""
    if len(message.command) == 1:
        await message.reply("Give me a chat id")
        return

    try:
        chat_id = int(message.command[1])
    except ValueError:
        await message.reply("Give Me A Valid Chat ID")
        return

    try:
        link = await bot.create_chat_invite_link(chat_id)
    except ChatAdminRequired:
        await message.reply(
            "Invite Link Generation Failed, I am Not Having Sufficient Rights"
        )
        return
    except Exception as exc:  # noqa: BLE001
        logger.warning("gen_invite failed for %s: %s", chat_id, exc)
        await message.reply(f"Error {exc}")
        return

    await message.reply(f"Here is your Invite Link {link.invite_link}")


# ══════════════════════════════════════════════════════════════════════════════
#  MODERATION  (admin-only)
# ══════════════════════════════════════════════════════════════════════════════

async def _resolve_target_user(bot, message):
    """Shared parse helper for /ban and /unban → (user, reason) or (None, error)."""
    parts = message.text.split(None)
    if len(parts) > 2:
        reason = message.text.split(None, 2)[2]
        chat = message.text.split(None, 2)[1]
    else:
        chat = message.command[1]
        reason = "No reason Provided"

    try:
        chat = int(chat)
    except ValueError:
        pass  # allow @usernames

    try:
        user = await bot.get_users(chat)
    except PeerIdInvalid:
        return None, "This is an invalid user, make sure they have started me atleast."
    except IndexError:
        return None, "This might be a channel, make sure its a user."
    except Exception as exc:  # noqa: BLE001
        logger.warning("resolve user %s failed: %s", chat, exc)
        return None, f"Error - {exc}"

    return user, reason


@Client.on_message(filters.command("ban") & filters.user(ADMINS))
async def ban_a_user(bot, message):
    """`/ban <user> [reason]` — blacklist a user from using the bot."""
    if len(message.command) == 1:
        await message.reply("Give me a user id / username")
        return

    user, reason = await _resolve_target_user(bot, message)
    if user is None:
        await message.reply(reason)  # ``reason`` carries the error text here
        return

    status = await db.get_ban_status(user.id)
    if status["is_banned"]:
        await message.reply(
            f"{user.mention} is already banned\nReason: {status['ban_reason']}"
        )
        return

    await db.ban_user(user.id, reason)
    temp.BANNED_USERS.append(user.id)
    await message.reply(f"Successfully banned {user.mention}")


@Client.on_message(filters.command("unban") & filters.user(ADMINS))
async def unban_a_user(bot, message):
    """`/unban <user>` — lift a user's ban."""
    if len(message.command) == 1:
        await message.reply("Give me a user id / username")
        return

    user, _reason = await _resolve_target_user(bot, message)
    if user is None:
        await message.reply(_reason)
        return

    status = await db.get_ban_status(user.id)
    if not status["is_banned"]:
        await message.reply(f"{user.mention} is not yet banned.")
        return

    await db.remove_ban(user.id)
    if user.id in temp.BANNED_USERS:
        temp.BANNED_USERS.remove(user.id)
    await message.reply(f"Successfully unbanned {user.mention}")


# ══════════════════════════════════════════════════════════════════════════════
#  STATS & LISTINGS  (admin-only)
# ══════════════════════════════════════════════════════════════════════════════

@Client.on_message(filters.command("stats") & filters.user(ADMINS))
async def get_stats(bot, message):
    """`/stats` — total files / users / chats and DB storage usage."""
    status = await message.reply("Fetching stats..")
    total_users = await db.total_users_count()
    total_chats = await db.total_chat_count()
    files = await Media.count_documents()
    used = await db.get_db_size()
    free = 536870912 - used  # 512 MiB free-tier cap
    await status.edit(
        phrases.STATUS_TXT.format(
            files, total_users, total_chats, get_size(used), get_size(free)
        )
    )


@Client.on_message(filters.command("users") & filters.user(ADMINS))
async def list_users(bot, message):
    """`/users` — dump every saved user (file fallback when too long)."""
    status = await message.reply("Getting List Of Users")
    users = await db.get_all_users()
    out = "Users Saved In DB Are:\n\n"
    async for user in users:
        out += f"<a href=tg://user?id={user['id']}>{user['name']}</a>"
        if user["ban_status"]["is_banned"]:
            out += "( Banned User )"
        out += "\n"

    try:
        await status.edit_text(out)
    except MessageTooLong:
        path = "users.txt"
        with open(path, "w+") as outfile:
            outfile.write(out)
        await message.reply_document(path, caption="List Of Users")
        # Clean up the spooled listing file.
        try:
            os.remove(path)
        except OSError:
            pass


@Client.on_message(filters.command("chats") & filters.user(ADMINS))
async def list_chats(bot, message):
    """`/chats` — dump every saved chat (file fallback when too long)."""
    status = await message.reply("Getting List Of chats")
    chats = await db.get_all_chats()
    out = "Chats Saved In DB Are:\n\n"
    async for chat in chats:
        out += f"**Title:** `{chat['title']}`\n**- ID:** `{chat['id']}`"
        if chat["chat_status"]["is_disabled"]:
            out += "( Disabled Chat )"
        out += "\n"

    try:
        await status.edit_text(out)
    except MessageTooLong:
        path = "chats.txt"
        with open(path, "w+") as outfile:
            outfile.write(out)
        await message.reply_document(path, caption="List Of Chats")
        try:
            os.remove(path)
        except OSError:
            pass


# ═══════════════════════════════════════════════════════════════════════════════
#  ⚡ Crafted by Trinity Mods (@trinityXmods) · Trinity AutoFilter
#  If this code helped you, keep the credit alive → github.com/Trinity-Mods
#  🚫 This credit is license-locked. See brand.py.
# ═══════════════════════════════════════════════════════════════════════════════
