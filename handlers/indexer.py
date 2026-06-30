# ═══════════════════════════════════════════════════════════════════════════════
#  ⚡ TRINITY MODS · TRINITY AUTOFILTER
#  File-indexing pipeline: submit links/forwards, moderator accept/reject,
#  skip-offset control, bulk walk-and-save into the media vault — plus legacy
#  user/group broadcast (bcast/gcast) helpers.
#  ─────────────────────────────────────────────────────────────────────────────
#  Developed & maintained by Trinity Mods (@trinityXmods)
#  GitHub   : github.com/Trinity-Mods
#  Source   : github.com/Trinity-Mods/Auto-Filter-Bot
#  Telegram : t.me/trinityXmods
#  🚫 Credit is license-locked — see brand.py. Please keep this header intact.
# ═══════════════════════════════════════════════════════════════════════════════

import re
import time
import asyncio
import logging
import datetime

from pyrogram import Client, filters, enums
from pyrogram.errors import FloodWait
from pyrogram.errors.exceptions.bad_request_400 import (
    ChannelInvalid,
    ChatAdminRequired,
    UsernameInvalid,
    UsernameNotModified,
)
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ── Trinity import contract (new module layout) ────────────────────────────────
from config import ADMINS, INDEX_REQ_CHANNEL as LOG_CHANNEL
from toolbox import temp, broadcast_messages
from vault.media_index import save_file
from vault.registry import db

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# A single global lock so only one indexing pass walks a channel at a time.
# Two concurrent passes would double-count progress and hammer the API.
_index_lock = asyncio.Lock()

# Regex matching a public/private t.me message link → (…, chat, msg_id).
_LINK_RE = re.compile(
    r"(https://)?(t\.me/|telegram\.me/|telegram\.dog/)(c/)?(\d+|[a-zA-Z_0-9]+)/(\d+)$"
)


# ═══════════════════════════════════════════════════════════════════════════════
#  CALLBACK · index accept / reject / cancel
# ═══════════════════════════════════════════════════════════════════════════════
@Client.on_callback_query(filters.regex(r"^index"))
async def index_files(bot, query):
    """Handle the inline buttons attached to an index request."""

    # The lightweight "cancel" button just flips a flag the worker polls.
    if query.data.startswith("index_cancel"):
        temp.CANCEL = True
        return await query.answer("Cancelling Indexing")

    # callback_data layout: index#<verdict>#<chat>#<last_msg_id>#<from_user>
    _, verdict, chat, last_msg_id, from_user = query.data.split("#")

    # ── Rejection path: drop the request card and notify the submitter. ─────────
    if verdict == "reject":
        await query.message.delete()
        await bot.send_message(
            int(from_user),
            f"Your Submission for indexing {chat} has been decliened by our moderators.",
            reply_to_message_id=int(last_msg_id),
        )
        return

    # Refuse to start a second pass while one is already running.
    if _index_lock.locked():
        return await query.answer(
            "Wait until previous process is finished.", show_alert=True
        )

    status_msg = query.message
    await query.answer("Processing...⏳", show_alert=True)

    # Tell the (non-admin) contributor their submission was accepted.
    if int(from_user) not in ADMINS:
        await bot.send_message(
            int(from_user),
            f"Your Submission for indexing {chat} has been accepted by our "
            f"moderators and the index has already started!",
            reply_to_message_id=int(last_msg_id),
        )

    await status_msg.edit(
        "Starting Indexing",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("Cancel", callback_data="index_cancel")]]
        ),
    )

    # Numeric chat ids must be passed as int; usernames stay as-is.
    try:
        chat = int(chat)
    except (TypeError, ValueError):
        pass  # leave `chat` as the username string

    await index_files_to_db(int(last_msg_id), chat, status_msg, bot)


# ═══════════════════════════════════════════════════════════════════════════════
#  COMMAND · legacy admin broadcast to all users  (/bcast)
# ═══════════════════════════════════════════════════════════════════════════════
# FIX: gated on filters.user(ADMINS) instead of a hardcoded numeric user id.
@Client.on_message(filters.command("bcast") & filters.user(ADMINS) & filters.reply)
async def broadcast_to_users(bot, message):
    """Reply to a message with /bcast to forward it to every known user."""
    users = await db.get_all_users()
    payload = message.reply_to_message
    status = await message.reply_text(text="Broadcasting your messages...")

    start_time = time.time()
    total_users = await db.total_users_count()

    # FIX: every counter is initialised before the loop touches it.
    done = blocked = deleted = failed = success = 0

    async for user in users:
        sent, reason = await broadcast_messages(int(user["id"]), payload)
        if sent:
            success += 1
        elif sent is False:
            if reason == "Blocked":
                blocked += 1
            elif reason == "Deleted":
                deleted += 1
            elif reason == "Error":
                failed += 1
        done += 1
        await asyncio.sleep(2)
        if not done % 20:
            await status.edit(
                f"Broadcast in progress:\n\nTotal Users {total_users}\n"
                f"Completed: {done} / {total_users}\nSuccess: {success}\n"
                f"Blocked: {blocked}\nDeleted: {deleted}"
            )

    time_taken = datetime.timedelta(seconds=int(time.time() - start_time))
    await status.edit(
        f"Broadcast Completed:\nCompleted in {time_taken} seconds.\n\n"
        f"Total Users {total_users}\nCompleted: {done} / {total_users}\n"
        f"Success: {success}\nBlocked: {blocked}\nDeleted: {deleted}"
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  COMMAND · legacy admin broadcast to all groups  (/gcast)
# ═══════════════════════════════════════════════════════════════════════════════
# FIX: gated on filters.user(ADMINS) instead of a hardcoded numeric user id.
@Client.on_message(filters.command("gcast") & filters.user(ADMINS) & filters.reply)
async def broadcast_to_groups(bot, message):
    """Reply to a message with /gcast to forward it to every connected group."""
    chats = await db.get_all_chats()
    payload = message.reply_to_message
    status = await message.reply_text(text="Broadcasting your messages...")

    start_time = time.time()
    total_chats = await db.total_chat_count()

    # FIX: blocked/deleted initialised here too (the original used them
    # without defining them, raising NameError on the first failed chat).
    done = blocked = deleted = failed = success = 0

    async for chat in chats:
        sent, reason = await broadcast_messages(int(chat["id"]), payload)
        if sent:
            success += 1
        elif sent is False:
            if reason == "Blocked":
                blocked += 1
            elif reason == "Deleted":
                deleted += 1
            elif reason == "Error":
                failed += 1
        done += 1
        await asyncio.sleep(2)
        if not done % 20:
            await status.edit(
                f"Broadcast in progress:\n\nTotal Chats {total_chats}\n"
                f"Completed: {done} / {total_chats}\nSuccess: {success}\n"
                f"Failed: {failed}"
            )

    time_taken = datetime.timedelta(seconds=int(time.time() - start_time))
    await status.edit(
        f"Broadcast Completed:\nCompleted in {time_taken} seconds.\n\n"
        f"Total Chats {total_chats}\nCompleted: {done} / {total_chats}\n"
        f"Success: {success}\nFailed: {failed}"
    )


# ───────────────────────────  ⚡ Trinity Mods · @trinityXmods  ───────────────────────────


# ═══════════════════════════════════════════════════════════════════════════════
#  MESSAGE · accept a forward or a t.me link as an index submission
# ═══════════════════════════════════════════════════════════════════════════════
@Client.on_message(
    (
        filters.forwarded
        | (filters.regex(_LINK_RE.pattern) & filters.text)
    )
    & filters.private
    & filters.incoming
)
async def send_for_index(bot, message):
    """Resolve a submitted link/forward and either index (admin) or queue it."""

    # ── Work out the target chat + the last message id to walk back from. ───────
    if message.text:
        match = _LINK_RE.match(message.text)
        if not match:
            return await message.reply("Invalid link")
        chat_id = match.group(4)
        last_msg_id = int(match.group(5))
        if chat_id.isnumeric():
            # Private channel exported as a `c/<id>` link → restore -100 prefix.
            chat_id = int("-100" + chat_id)
    elif message.forward_from_chat and message.forward_from_chat.type == enums.ChatType.CHANNEL:
        last_msg_id = message.forward_from_message_id
        chat_id = message.forward_from_chat.username or message.forward_from_chat.id
    else:
        # Forward that isn't from a channel — nothing we can index.
        return

    # ── Make sure we can actually see that chat. ────────────────────────────────
    try:
        await bot.get_chat(chat_id)
    except ChannelInvalid:
        return await message.reply(
            "This may be a private channel / group. Make me an admin over "
            "there to index the files."
        )
    except (UsernameInvalid, UsernameNotModified):
        return await message.reply("Invalid Link specified.")
    except Exception as exc:  # noqa: BLE001 — surface unexpected resolution errors
        logger.exception("get_chat failed for %s", chat_id)
        return await message.reply(f"Errors - {exc}")

    try:
        probe = await bot.get_messages(chat_id, last_msg_id)
    except Exception:  # noqa: BLE001
        logger.exception("get_messages failed for %s/%s", chat_id, last_msg_id)
        return await message.reply(
            "Make Sure That I am An Admin In The Channel, if channel is private"
        )

    if probe.empty:
        return await message.reply(
            "This may be group and i am not a admin of the group."
        )

    # ── Admins index immediately (single confirm button). ───────────────────────
    if message.from_user.id in ADMINS:
        buttons = [
            [
                InlineKeyboardButton(
                    "Yes",
                    callback_data=f"index#accept#{chat_id}#{last_msg_id}#{message.from_user.id}",
                )
            ],
            [InlineKeyboardButton("close", callback_data="close_data")],
        ]
        return await message.reply(
            f"Do you Want To Index This Channel/ Group ?\n\n"
            f"Chat ID/ Username: <code>{chat_id}</code>\n"
            f"Last Message ID: <code>{last_msg_id}</code>",
            reply_markup=InlineKeyboardMarkup(buttons),
        )

    # ── Non-admins: build an invite link and route to moderators. ───────────────
    if isinstance(chat_id, int):
        try:
            link = (await bot.create_chat_invite_link(chat_id)).invite_link
        except ChatAdminRequired:
            return await message.reply(
                "Make sure iam an admin in the chat and have permission to "
                "invite users."
            )
    else:
        link = f"@{message.forward_from_chat.username}"

    buttons = [
        [
            InlineKeyboardButton(
                "Accept Index",
                callback_data=f"index#accept#{chat_id}#{last_msg_id}#{message.from_user.id}",
            )
        ],
        [
            InlineKeyboardButton(
                "Reject Index",
                callback_data=f"index#reject#{chat_id}#{message.id}#{message.from_user.id}",
            )
        ],
    ]
    await bot.send_message(
        LOG_CHANNEL,
        f"#IndexRequest\n\nBy : {message.from_user.mention} "
        f"(<code>{message.from_user.id}</code>)\n"
        f"Chat ID/ Username - <code> {chat_id}</code>\n"
        f"Last Message ID - <code>{last_msg_id}</code>\nInviteLink - {link}",
        reply_markup=InlineKeyboardMarkup(buttons),
    )
    await message.reply(
        "ThankYou For the Contribution, Wait For My Moderators to verify the files."
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  COMMAND · set the skip offset for the next index pass  (/setskip N)
# ═══════════════════════════════════════════════════════════════════════════════
@Client.on_message(filters.command("setskip") & filters.user(ADMINS))
async def set_skip_number(bot, message):
    """Skip the first N messages when the next indexing pass runs."""
    if " " in message.text:
        _, skip = message.text.split(" ", 1)
        try:
            skip = int(skip)
        except ValueError:
            return await message.reply("Skip number should be an integer.")
        await message.reply(f"Successfully set SKIP number as {skip}")
        temp.CURRENT = skip
    else:
        await message.reply("Give me a skip number")


# ═══════════════════════════════════════════════════════════════════════════════
#  WORKER · walk messages from newest→oldest and persist supported media
# ═══════════════════════════════════════════════════════════════════════════════
async def index_files_to_db(last_msg_id, chat, status_msg, bot):
    """Iterate a chat's history and save every video/audio/document found."""

    total_files = duplicate = errors = deleted = no_media = unsupported = 0

    async with _index_lock:
        try:
            current = temp.CURRENT
            temp.CANCEL = False

            # app.iter_messages walks message ids from `last_msg_id` down.
            async for message in bot.iter_messages(chat, last_msg_id, temp.CURRENT):
                # Honour a mid-pass cancel request.
                if temp.CANCEL:
                    await status_msg.edit(
                        f"Successfully Cancelled!!\n\nSaved "
                        f"<code>{total_files}</code> files to dataBase!\n"
                        f"Duplicate Files Skipped: <code>{duplicate}</code>\n"
                        f"Deleted Messages Skipped: <code>{deleted}</code>\n"
                        f"Non-Media messages skipped: "
                        f"<code>{no_media + unsupported}</code>"
                        f"(Unsupported Media - `{unsupported}` )\n"
                        f"Errors Occurred: <code>{errors}</code>"
                    )
                    break

                current += 1
                # Refresh the progress card every 100 messages.
                if current % 100 == 0:
                    reply = InlineKeyboardMarkup(
                        [[InlineKeyboardButton("Cancel", callback_data="index_cancel")]]
                    )
                    await status_msg.edit_text(
                        text=(
                            f"Total messages fetched: <code>{current}</code>\n"
                            f"Total messages saved: <code>{total_files}</code>\n"
                            f"Duplicate Files Skipped: <code>{duplicate}</code>\n"
                            f"Deleted Messages Skipped: <code>{deleted}</code>\n"
                            f"Non-Media messages skipped: "
                            f"<code>{no_media + unsupported}</code>"
                            f"(Unsupported Media - `{unsupported}` )\n"
                            f"Errors Occurred: <code>{errors}</code>"
                        ),
                        reply_markup=reply,
                    )
                    await asyncio.sleep(1)

                # ── Classify the message. ───────────────────────────────────────
                if message.empty:
                    deleted += 1
                    continue
                if not message.media:
                    no_media += 1
                    continue
                if message.media not in (
                    enums.MessageMediaType.VIDEO,
                    enums.MessageMediaType.AUDIO,
                    enums.MessageMediaType.DOCUMENT,
                ):
                    unsupported += 1
                    continue

                media = getattr(message, message.media.value, None)
                if not media:
                    unsupported += 1
                    continue

                media.file_type = message.media.value
                media.caption = message.caption

                # ── Persist. save_file returns (ok, file_id). ───────────────────
                # FIX: validate the result is a 2-tuple before unpacking instead
                # of assuming the shape (a crash here would abort the whole pass).
                result = await save_file(media)
                if not isinstance(result, tuple) or len(result) != 2:
                    errors += 1
                    logger.warning("save_file returned unexpected value: %r", result)
                    continue
                ok, _file_id = result

                if ok:
                    total_files += 1
                    # NEW · request-fulfillment ping. If anyone asked for a title
                    # that this freshly-saved file matches, DM them. Best-effort
                    # and cheap — failures here never break indexing.
                    try:
                        await _notify_requesters(bot, getattr(media, "file_name", ""))
                    except Exception:  # noqa: BLE001
                        logger.exception("request-fulfillment ping failed")
                elif _file_id is not None:
                    # Non-None id with ok=False → DuplicateKeyError (already have it).
                    duplicate += 1
                else:
                    # ok=False and no id → validation/other failure.
                    errors += 1

        except FloodWait as exc:
            # pyrofork v2 exposes the wait seconds on `.value`.
            await asyncio.sleep(getattr(exc, "value", getattr(exc, "x", 0)))
            logger.warning("FloodWait during indexing on chat %s", chat)
            await status_msg.edit("Hit a FloodWait — please retry indexing.")
        except Exception as exc:  # noqa: BLE001 — report, don't crash the worker
            logger.exception("Indexing failed for chat %s", chat)
            await status_msg.edit(f"Error: {exc}")
        else:
            await status_msg.edit(
                f"Succesfully saved <code>{total_files}</code> to dataBase!\n"
                f"Duplicate Files Skipped: <code>{duplicate}</code>\n"
                f"Deleted Messages Skipped: <code>{deleted}</code>\n"
                f"Non-Media messages skipped: "
                f"<code>{no_media + unsupported}</code>"
                f"(Unsupported Media - `{unsupported}` )\n"
                f"Errors Occurred: <code>{errors}</code>"
            )


async def _notify_requesters(bot, file_name):
    """DM every user whose open request matches `file_name` (best-effort)."""
    if not file_name:
        return
    reqs = await db.take_matching_requests(file_name)
    for r in reqs or []:
        try:
            await bot.send_message(
                int(r["user_id"]),
                f"✅ Your requested title is now available:\n<code>{file_name}</code>",
            )
        except Exception:  # noqa: BLE001 — blocked/invalid users are expected
            logger.info("Could not notify requester %s", r.get("user_id"))


# ═══════════════════════════════════════════════════════════════════════════════
#  ⚡ Crafted by Trinity Mods (@trinityXmods) · Trinity AutoFilter
#  If this code helped you, keep the credit alive → github.com/Trinity-Mods
#  🚫 This credit is license-locked. See brand.py.
# ═══════════════════════════════════════════════════════════════════════════════
