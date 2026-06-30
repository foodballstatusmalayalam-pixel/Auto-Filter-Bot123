# ═══════════════════════════════════════════════════════════════════════════════
#  ⚡ TRINITY MODS · TRINITY AUTOFILTER
#  Auto-approve incoming chat join-requests and welcome new members.
#  ─────────────────────────────────────────────────────────────────────────────
#  Developed & maintained by Trinity Mods (@trinityXmods)
#  GitHub   : github.com/Trinity-Mods
#  Source   : github.com/Trinity-Mods/Auto-Filter-Bot
#  Telegram : t.me/trinityXmods
#  🚫 Credit is license-locked — see brand.py. Please keep this header intact.
# ═══════════════════════════════════════════════════════════════════════════════

# -----------------------------------------------------------------------------
#  WHAT THIS MODULE DOES
#  When a user taps "Join" on a channel/group that has *join requests* enabled,
#  Telegram emits a ``chat_join_request`` update instead of adding the user
#  straight away. If our bot is an admin with the "add members / approve users"
#  right, we can auto-approve that pending request — turning a manual-approval
#  channel into a frictionless one — and optionally drop the new member a short
#  welcome DM.
#
#  Registration follows the Pyrogram smart-plugins pattern: the handler is bound
#  to ``Client`` via the decorator, so every booted worker client loads it.
# -----------------------------------------------------------------------------

import asyncio
import logging

from pyrogram import Client
from pyrogram.errors import (
    FloodWait,
    UserIsBlocked,
    InputUserDeactivated,
    PeerIdInvalid,
    ChatAdminRequired,
    UserAlreadyParticipant,
    RPCError,
)

# Module logger — replaces the original's bare ``print`` debugging.
log = logging.getLogger(__name__)


# ───────────────────────────  ⚡ Trinity Mods · @trinityXmods  ───────────────────────────


async def _send_welcome(client, chat, member):
    """Best-effort welcome DM to a freshly approved member.

    Wrapped in its own try/except so that a blocked/deactivated user — or any
    delivery hiccup — never aborts the approval flow. Returns nothing; failures
    are logged at debug level because they are entirely expected (lots of users
    keep their PMs closed to bots).
    """
    # Smallcaps styling preserved from the original commented-out template so the
    # bot's "voice" stays consistent with the rest of Trinity AutoFilter.
    text = (
        f"ʜᴇʏ {member.mention}!\n"
        f"ʏᴏᴜʀ ʀᴇǫᴜᴇsᴛ ʜᴀs ʙᴇᴇɴ ᴀᴄᴄᴇᴘᴛᴇᴅ — ᴡᴇʟᴄᴏᴍᴇ ᴛᴏ {chat.title} 🎉"
    )
    try:
        await client.send_message(member.id, text)
    except FloodWait as e:
        # pyrofork v2 exposes the wait duration on ``.value`` (legacy ``.x``).
        await asyncio.sleep(getattr(e, "value", getattr(e, "x", 0)))
        try:
            await client.send_message(member.id, text)
        except RPCError as retry_err:
            log.debug("Welcome DM retry failed for %s: %s", member.id, retry_err)
    except (UserIsBlocked, InputUserDeactivated, PeerIdInvalid) as e:
        # User can't / won't receive the DM — nothing to do, just note it.
        log.debug("Could not DM welcome to %s: %s", member.id, e)
    except RPCError as e:
        log.warning("Unexpected error sending welcome DM to %s: %s", member.id, e)


@Client.on_chat_join_request()
async def approve_join_request(client, request):
    """Auto-approve a pending join request whenever the bot is able to.

    ``request`` is a ``ChatJoinRequest`` update carrying the target ``chat`` and
    the requesting ``from_user``.
    """
    chat = request.chat
    user = request.from_user

    try:
        # Approve the pending request. We attempt this directly rather than
        # pre-checking our own membership: the approval call itself surfaces the
        # precise permission error, which we then handle below. This avoids an
        # extra round-trip on the happy path.
        await client.approve_chat_join_request(chat.id, user.id)
        log.info("Approved join request: user=%s chat=%s", user.id, chat.id)

        # Optional welcome — guarded so a DM failure never undoes the approval.
        await _send_welcome(client, chat, user)

    except FloodWait as e:
        # Telegram is rate-limiting us; wait the requested span, then retry once.
        await asyncio.sleep(getattr(e, "value", getattr(e, "x", 0)))
        try:
            await client.approve_chat_join_request(chat.id, user.id)
            log.info(
                "Approved join request after FloodWait: user=%s chat=%s",
                user.id,
                chat.id,
            )
            await _send_welcome(client, chat, user)
        except RPCError as retry_err:
            log.error(
                "Retry after FloodWait failed for user=%s chat=%s: %s",
                user.id,
                chat.id,
                retry_err,
            )

    except UserAlreadyParticipant:
        # Race: the user got let in by someone/something else first. Harmless.
        log.debug("User %s already in chat %s; nothing to approve.", user.id, chat.id)

    except ChatAdminRequired:
        # The bot lacks the admin right to approve requests in this chat.
        log.warning(
            "Missing approve-members right in chat=%s (user=%s).", chat.id, user.id
        )

    except RPCError as e:
        # Catch-all for any other Telegram-side failure — logged, never silent.
        log.error(
            "Failed to approve join request user=%s chat=%s: %s", user.id, chat.id, e
        )


# ═══════════════════════════════════════════════════════════════════════════════
#  ⚡ Crafted by Trinity Mods (@trinityXmods) · Trinity AutoFilter
#  If this code helped you, keep the credit alive → github.com/Trinity-Mods
#  🚫 This credit is license-locked. See brand.py.
# ═══════════════════════════════════════════════════════════════════════════════
