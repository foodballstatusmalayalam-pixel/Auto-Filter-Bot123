# ═══════════════════════════════════════════════════════════════════════════════
#  ⚡ TRINITY MODS · TRINITY AUTOFILTER
#  Moderation gatekeepers — silences banned users and disabled chats before any
#  other handler can run, then politely shows them the door.
#  ─────────────────────────────────────────────────────────────────────────────
#  Developed & maintained by Trinity Mods (@trinityXmods)
#  GitHub   : github.com/Trinity-Mods
#  Source   : github.com/Trinity-Mods/Auto-Filter-Bot
#  Telegram : t.me/trinityXmods
#  🚫 Credit is license-locked — see brand.py. Please keep this header intact.
# ═══════════════════════════════════════════════════════════════════════════════

import logging

from pyrogram import Client, filters
from pyrogram.types import (
    Message,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from pyrogram.errors import (
    ChatAdminRequired,
    MessageIdInvalid,
    RPCError,
)

# ── New-layout imports (old `info`/`utils`/`database` paths are gone) ──────────
from config import SUPPORT_CHAT
from toolbox import temp
from vault.registry import db

# Module-scoped logger so swallowed errors leave a trail instead of vanishing.
log = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
#  Custom filter predicates
#
#  `temp.BANNED_USERS` / `temp.BANNED_CHATS` are in-memory sets kept hot by the
#  registry so we never hit the DB on the message hot-path. These two predicates
#  decide, per incoming update, whether the sender/chat is currently blocked.
# ═══════════════════════════════════════════════════════════════════════════════

async def _is_banned_user(_, __, message: Message) -> bool:
    """
    True only when a *real* human user (not an anonymous channel/sender_chat post)
    sent the message AND that user's id sits in the banned set.

    BUG FIX vs legacy: the original used `from_user is not None OR not sender_chat`,
    which short-circuits to True for almost every message and then dereferences
    `message.from_user.id` even when `from_user` is None — crashing on channel
    posts. The correct gate requires a genuine user: it must exist *and* the
    message must not be a sender_chat (anonymous) post. Only then is the id lookup
    safe and meaningful.
    """
    return (
        message.from_user is not None
        and not message.sender_chat
        and message.from_user.id in temp.BANNED_USERS
    )


async def _is_disabled_chat(_, __, message: Message) -> bool:
    """True when this chat has been administratively disabled by a bot admin."""
    return message.chat.id in temp.BANNED_CHATS


# Materialise the predicates into reusable Pyrogram filter objects.
banned_user = filters.create(_is_banned_user)
disabled_group = filters.create(_is_disabled_chat)


# ═══════════════════════════════════════════════════════════════════════════════
#  Handler: banned user reaches out in PM
# ═══════════════════════════════════════════════════════════════════════════════

@Client.on_message(filters.private & banned_user & filters.incoming)
async def notify_banned_user(bot: Client, message: Message):
    """Reply to a banned user's private message with their ban reason."""
    ban_record = await db.get_ban_status(message.from_user.id)
    reason = ban_record.get("ban_reason") if ban_record else None

    try:
        await message.reply(
            "Sorry Dude, You are Banned to use Me.\n"
            f"Ban Reason: {reason}"
        )
    except RPCError as err:
        # User may have blocked the bot, etc. — note it and move on.
        log.warning("Could not deliver ban notice to %s: %s",
                    message.from_user.id, err)


# ───────────────────────────  ⚡ Trinity Mods · @trinityXmods  ───────────────────────────


# ═══════════════════════════════════════════════════════════════════════════════
#  Handler: bot is active in a disabled group
# ═══════════════════════════════════════════════════════════════════════════════

@Client.on_message(filters.group & disabled_group & filters.incoming)
async def leave_disabled_chat(bot: Client, message: Message):
    """
    Announce that the chat is off-limits, pin the notice (best effort), then
    leave the group entirely.
    """
    support_button = InlineKeyboardMarkup(
        [[InlineKeyboardButton("Support", url=f"https://t.me/{SUPPORT_CHAT}")]]
    )

    chat_record = await db.get_chat(message.chat.id)
    reason = chat_record.get("reason") if chat_record else None

    notice = await message.reply(
        text=(
            "CHAT NOT ALLOWED 🐞\n\n"
            "My admins has restricted me from working here ! If you want to "
            "know more about it contact support..\n"
            f"Reason : <code>{reason}</code>."
        ),
        reply_markup=support_button,
    )

    # BUG FIX vs legacy: the old code swallowed pin failures with a bare
    # `except: pass`. We now narrow to the realistic causes (missing admin
    # rights, races where the message was already deleted) and LOG them.
    try:
        await notice.pin()
    except (ChatAdminRequired, MessageIdInvalid) as err:
        log.info("Skipped pinning leave-notice in %s: %s", message.chat.id, err)
    except RPCError as err:
        log.warning("Unexpected error pinning leave-notice in %s: %s",
                    message.chat.id, err)

    # Finally, exit the disabled chat.
    await bot.leave_chat(message.chat.id)


# ═══════════════════════════════════════════════════════════════════════════════
#  ⚡ Crafted by Trinity Mods (@trinityXmods) · Trinity AutoFilter
#  If this code helped you, keep the credit alive → github.com/Trinity-Mods
#  🚫 This credit is license-locked. See brand.py.
# ═══════════════════════════════════════════════════════════════════════════════
