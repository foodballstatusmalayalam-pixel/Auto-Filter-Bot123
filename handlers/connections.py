# ═══════════════════════════════════════════════════════════════════════════════
#  ⚡ TRINITY MODS · TRINITY AUTOFILTER
#  Group ↔ PM connection commands — /connect, /disconnect, /connections.
#  ─────────────────────────────────────────────────────────────────────────────
#  Developed & maintained by Trinity Mods (@trinityXmods)
#  GitHub   : github.com/Trinity-Mods
#  Source   : github.com/Trinity-Mods/Auto-Filter-Bot
#  Telegram : t.me/trinityXmods
#  🚫 Credit is license-locked — see brand.py. Please keep this header intact.
# ═══════════════════════════════════════════════════════════════════════════════
"""
A "connection" lets a group admin manage their group (settings, filters, …) from
the bot's private chat. This handler exposes the three user-facing commands:

  • /connect [group_id]  — bind the caller's PM to a group they administer.
  • /disconnect          — drop the connection from inside the group.
  • /connections         — list the caller's connected groups (PM only), each
                           rendered as an inline button whose callback the
                           settings panel (handlers/searchcore) consumes.

All persistence lives in ``vault.links`` and is now fully async (motor), so every
lookup/mutation is awaited rather than blocking the event loop like the legacy
synchronous pymongo version did.
"""

import logging

from pyrogram import filters, Client, enums
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

# Async connection store (motor-backed). Signatures of note:
#   add_connection(group_id, user_id)   delete_connection(user_id, group_id)
#   all_connections(user_id)            if_active(user_id, group_id)
from vault.links import add_connection, all_connections, if_active, delete_connection
from config import ADMINS

logger = logging.getLogger("trinity.handlers.connections")


# ─────────────────────────────────────────────────────────────────────────────
# Small internal helpers
# ─────────────────────────────────────────────────────────────────────────────
def _is_global_admin(user_id) -> bool:
    """True if ``user_id`` is a configured bot admin (ADMINS may hold ints/strs)."""
    return user_id in ADMINS or str(user_id) in [str(a) for a in ADMINS]


async def _is_group_admin(client, group_id, user_id) -> bool:
    """
    Verify the caller actually administers the target group via get_chat_member.
    Bot-level admins bypass the check. Raises on lookup failure so the caller can
    surface the "invalid group / bot not present" message.
    """
    if _is_global_admin(user_id):
        return True
    member = await client.get_chat_member(group_id, user_id)
    return member.status in (
        enums.ChatMemberStatus.ADMINISTRATOR,
        enums.ChatMemberStatus.OWNER,
    )


# ─────────────────────────────────────────────────────────────────────────────
# /connect — bind a PM to a group the caller administers
# ─────────────────────────────────────────────────────────────────────────────
@Client.on_message((filters.private | filters.group) & filters.command("connect"))
async def add_connection_handler(client, message):
    # Anonymous admins have no from_user; they must connect explicitly from PM.
    user_id = message.from_user.id if message.from_user else None
    if not user_id:
        return await message.reply(
            f"You are anonymous admin. Use /connect {message.chat.id} in PM"
        )

    chat_type = message.chat.type

    # Resolve the target group id depending on where the command was issued.
    if chat_type == enums.ChatType.PRIVATE:
        # Expect "/connect <group_id>" — bounds-check the split.
        parts = message.text.split(" ", 1)
        if len(parts) < 2 or not parts[1].strip():
            await message.reply_text(
                "<b>Enter in correct format!</b>\n\n"
                "<code>/connect groupid</code>\n\n"
                "<i>Get your Group id by adding this bot to your group and use  <code>/id</code></i>",
                quote=True,
            )
            return
        group_id = parts[1].strip()
    elif chat_type in (enums.ChatType.GROUP, enums.ChatType.SUPERGROUP):
        group_id = message.chat.id
    else:
        # Channels / other chat types are not connectable.
        return

    # Step 1 — confirm the CALLER administers the target group.
    try:
        caller_is_admin = await _is_group_admin(client, group_id, user_id)
    except Exception as exc:  # noqa: BLE001 — invalid id / bot not in chat
        logger.warning("connect: caller admin-check failed for group %s: %s", group_id, exc)
        await message.reply_text(
            "Invalid Group ID!\n\nIf correct, Make sure I'm present in your group!!",
            quote=True,
        )
        return
    if not caller_is_admin:
        await message.reply_text("You should be an admin in Given group!", quote=True)
        return

    # Step 2 — confirm the BOT itself is an admin, then persist the connection.
    try:
        bot_member = await client.get_chat_member(group_id, "me")
        if bot_member.status != enums.ChatMemberStatus.ADMINISTRATOR:
            await message.reply_text("Add me as an admin in group", quote=True)
            return

        chat = await client.get_chat(group_id)
        title = chat.title

        # vault.links signature is add_connection(group_id, user_id).
        connected = await add_connection(str(group_id), str(user_id))
        if connected:
            await message.reply_text(
                f"Successfully connected to **{title}**\nNow manage your group from my pm !",
                quote=True,
                parse_mode=enums.ParseMode.MARKDOWN,
            )
            # If the command came from inside the group, also confirm in PM.
            if chat_type in (enums.ChatType.GROUP, enums.ChatType.SUPERGROUP):
                await client.send_message(
                    user_id,
                    f"Connected to **{title}** !",
                    parse_mode=enums.ParseMode.MARKDOWN,
                )
        else:
            await message.reply_text("You're already connected to this chat!", quote=True)
    except Exception as exc:  # noqa: BLE001
        logger.exception("connect: failed to connect user %s to group %s: %s", user_id, group_id, exc)
        await message.reply_text("Some error occurred! Try again later.", quote=True)
        return


# ───────────────────────────  ⚡ Trinity Mods · @trinityXmods  ───────────────────────────


# ─────────────────────────────────────────────────────────────────────────────
# /disconnect — drop the connection from inside the group
# ─────────────────────────────────────────────────────────────────────────────
@Client.on_message((filters.private | filters.group) & filters.command("disconnect"))
async def delete_connection_handler(client, message):
    user_id = message.from_user.id if message.from_user else None
    if not user_id:
        return await message.reply(
            f"You are anonymous admin. Use /connect {message.chat.id} in PM"
        )

    chat_type = message.chat.type

    # In PM there's no single "current" group — point users at /connections.
    if chat_type == enums.ChatType.PRIVATE:
        await message.reply_text(
            "Run /connections to view or disconnect from groups!", quote=True
        )
        return

    if chat_type not in (enums.ChatType.GROUP, enums.ChatType.SUPERGROUP):
        return

    group_id = message.chat.id

    # Only group admins (or bot admins) may disconnect.
    try:
        if not await _is_group_admin(client, group_id, user_id):
            return
    except Exception as exc:  # noqa: BLE001
        logger.warning("disconnect: admin-check failed for group %s: %s", group_id, exc)
        return

    # vault.links signature is delete_connection(user_id, group_id).
    removed = await delete_connection(str(user_id), str(group_id))
    if removed:
        await message.reply_text("Successfully disconnected from this chat", quote=True)
    else:
        await message.reply_text(
            "This chat isn't connected to me!\nDo /connect to connect.", quote=True
        )


# ─────────────────────────────────────────────────────────────────────────────
# /connections — list the caller's connected groups (PM only)
# ─────────────────────────────────────────────────────────────────────────────
@Client.on_message(filters.private & filters.command(["connections"]))
async def list_connections_handler(client, message):
    user_id = message.from_user.id

    group_ids = await all_connections(str(user_id))
    if group_ids is None:
        await message.reply_text(
            "There are no active connections!! Connect to some groups first.",
            quote=True,
        )
        return

    buttons = []
    for group_id in group_ids:
        try:
            chat = await client.get_chat(int(group_id))
            title = chat.title
            active = await if_active(str(user_id), str(group_id))
            # Preserve the original callback_data shape: "groupcb:<gid>:<act>".
            act = " - ACTIVE" if active else ""
            buttons.append(
                [
                    InlineKeyboardButton(
                        text=f"{title}{act}",
                        callback_data=f"groupcb:{group_id}:{act}",
                    )
                ]
            )
        except Exception as exc:  # noqa: BLE001 — skip groups we can't resolve
            logger.debug("connections: skipping group %s: %s", group_id, exc)
            continue

    if buttons:
        await message.reply_text(
            "Your connected group details ;\n\n",
            reply_markup=InlineKeyboardMarkup(buttons),
            quote=True,
        )
    else:
        await message.reply_text(
            "There are no active connections!! Connect to some groups first.",
            quote=True,
        )


# ═══════════════════════════════════════════════════════════════════════════════
#  ⚡ Crafted by Trinity Mods (@trinityXmods) · Trinity AutoFilter
#  If this code helped you, keep the credit alive → github.com/Trinity-Mods
#  🚫 This credit is license-locked. See brand.py.
# ═══════════════════════════════════════════════════════════════════════════════
