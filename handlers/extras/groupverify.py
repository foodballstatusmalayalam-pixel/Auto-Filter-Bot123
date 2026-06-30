# ═══════════════════════════════════════════════════════════════════════════════
#  ⚡ TRINITY MODS · TRINITY AUTOFILTER
#  Group verification workflow — admin approval/rejection of bot-added groups.
#  ─────────────────────────────────────────────────────────────────────────────
#  Developed & maintained by Trinity Mods (@trinityXmods)
#  GitHub   : github.com/Trinity-Mods
#  Source   : github.com/Trinity-Mods/Auto-Filter-Bot
#  Telegram : t.me/trinityXmods
#  🚫 Credit is license-locked — see brand.py. Please keep this header intact.
# ═══════════════════════════════════════════════════════════════════════════════
"""
Group verification flow
========================
Groups that add the bot can request verification.  A `/verify` command issued by
a group admin (or a global ADMIN) posts a request card into ``GROUP_VERIFY_LOGS``
with inline approve/reject buttons.  Staff then press:

  * ``verify_group_<chat_id>``   → mark the group verified  (db.verify_group)
  * ``rejected_group_<chat_id>`` → mark the group rejected  (db.reject_group)

``/grp_delete`` lets global admins make the bot leave (and forget) every saved
group at once.

This is an original Trinity Mods rewrite of the legacy ``Group_Verify`` plugin.
Behaviour, command names and callback-data prefixes are preserved 1:1; the
internals are restructured, the unsafe inline ``<a href=...>`` tags are now
properly quoted, and every previously-silent ``except`` now logs.
"""

import logging

from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

# ── Trinity import contract ───────────────────────────────────────────────────
from config import *                       # ADMINS, GROUP_VERIFY_LOGS, …
from toolbox import temp                   # runtime cache (temp.U_NAME, …)
from vault.registry import db              # core DB wrapper (motor / async)

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
async def _resolve_group_link(client, chat_id, stored_info=None):
    """
    Work out the best public/invite link for ``chat_id``.

    Resolution order (mirrors legacy behaviour):
      1. A link previously stored on the chat record (``grp_link``).
      2. A public ``t.me/<username>`` link if the chat is public.
      3. A freshly-created invite link (requires invite permission).
      4. The literal string ``"No link available"`` as a last resort.

    Any failure while creating the invite link is logged instead of being
    swallowed silently (the old code had a bare ``except Exception`` that did
    nothing useful with the captured exception).
    """
    # 1) Prefer a stored link if the caller already fetched the chat record.
    if stored_info and stored_info.get("grp_link"):
        return stored_info["grp_link"]

    # 2/3) Otherwise inspect the live chat object.
    try:
        chat = await client.get_chat(chat_id)
    except Exception as exc:  # network / peer-resolution errors
        log.warning("Could not fetch chat %s for link resolution: %s", chat_id, exc)
        return "No link available"

    if chat.username:
        return f"https://t.me/{chat.username}"

    try:
        invite = await client.create_chat_invite_link(chat_id)
        return invite.invite_link
    except Exception as exc:
        # Usually means the bot lacks the "invite users via link" permission.
        log.warning("Failed to create invite link for %s: %s", chat_id, exc)
        return "No link available"


def _parse_chat_id(callback_data):
    """
    Pull the trailing chat id out of a ``verify_group_<id>`` /
    ``rejected_group_<id>`` callback payload.

    We ``rsplit`` on the LAST underscore so negative supergroup ids (e.g.
    ``-100123…``) and any future prefix changes stay safe.
    """
    return int(callback_data.rsplit("_", 1)[1])


def _verify_button(chat_id):
    """Single 'tap to verify' inline keyboard for a rejected group card."""
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("Tᴀᴘ Tᴏ Vᴇʀɪғʏ ✅", callback_data=f"verify_group_{chat_id}")]]
    )


def _reject_button(chat_id):
    """Single 'reject' inline keyboard for a verified group card."""
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("Rᴇᴊᴇᴄᴛ ⛔", callback_data=f"rejected_group_{chat_id}")]]
    )


async def _load_group_context(client, chat_id):
    """
    Gather the data common to both callback handlers.

    Returns a tuple ``(info, owner, owner_id, title, total)`` or ``None`` if the
    group has no stored record (caller should alert "group not found").
    """
    info = await db.get_chat(chat_id)
    if not info:
        return None

    owner_id = info.get("owner_id")
    title = info.get("title", "Unknown Group")

    # Resolve the owner's user object for a nice @mention (best-effort).
    owner = None
    if owner_id:
        try:
            owner = await client.get_users(owner_id)
        except Exception as exc:
            log.warning("Could not resolve owner %s of group %s: %s", owner_id, chat_id, exc)

    # Live member count (best-effort — group might be inaccessible).
    try:
        total = await client.get_chat_members_count(chat_id)
    except Exception as exc:
        log.warning("Could not count members of %s: %s", chat_id, exc)
        total = 0

    return info, owner, owner_id, title, total


# ─────────────────────────────────────────────────────────────────────────────
# Callback: approve a group
# ─────────────────────────────────────────────────────────────────────────────
@Client.on_callback_query(filters.regex(r"^verify_group_"))
async def on_verify_group(client, query):
    """Staff pressed 'Tap To Verify' on a pending/rejected group card."""
    chat_id = _parse_chat_id(query.data)

    context = await _load_group_context(client, chat_id)
    if context is None:
        await query.answer("ɢʀᴏᴜᴘ ɴᴏᴛ ғᴏᴜɴᴅ!", show_alert=True)
        return
    info, owner, owner_id, title, total = context

    group_link = await _resolve_group_link(client, chat_id, info)
    owner_mention = owner.mention if owner else "Unknown"

    # Flip the group out of the rejected list (if it was there) and verify it.
    if await db.rejected_group(chat_id):
        await db.un_rejected(chat_id)
    await db.verify_group(chat_id)

    await query.answer("ᴛʜᴇ ɢʀᴏᴜᴘ ʜᴀs ʙᴇᴇɴ ᴠᴇʀɪғɪᴇᴅ ✅", show_alert=True)

    # NOTE: href is now properly single-quoted (legacy left it unquoted).
    await query.message.edit_text(
        f"𝑩𝒐𝒕: {temp.U_NAME}\n"
        f"𝑮𝒓𝒐𝒖𝒑: <a href='{group_link}'>{title}</a>\n"
        f"𝑰𝑫: {chat_id}\n"
        f"𝑴𝒆𝒎𝒃𝒆𝒓𝒔: {total}\n"
        f"𝑼𝒔𝒆𝒓: {owner_mention}\n\n"
        f"Gʀᴏᴜᴘ Is Vᴇʀɪғɪᴇᴅ. ✅",
        reply_markup=_reject_button(chat_id),
    )

    # Let the requesting owner know the good news.
    if owner_id:
        try:
            await client.send_message(
                chat_id=owner_id,
                text=(
                    f"#𝐕𝐞𝐫𝐢𝐟𝐲𝐞𝐝_𝐆𝐫𝐨𝐮𝐩\n\n"
                    f"Gʀᴏᴜᴘ Nᴀᴍᴇ: {title}\n"
                    f"Iᴅ: {chat_id}\n\n"
                    f"Cᴏɴɢʀᴀᴛᴜʟᴀᴛɪᴏɴs Gʀᴏᴜᴘ Is Vᴇʀɪғɪᴇᴅ. ✅."
                ),
            )
        except Exception as exc:
            log.warning("Could not DM owner %s about verification: %s", owner_id, exc)


# ───────────────────────────  ⚡ Trinity Mods · @trinityXmods  ───────────────────────────


# ─────────────────────────────────────────────────────────────────────────────
# Callback: reject a group
# ─────────────────────────────────────────────────────────────────────────────
@Client.on_callback_query(filters.regex(r"^rejected_group_"))
async def on_reject_group(client, query):
    """Staff pressed 'Reject' on a pending/verified group card."""
    chat_id = _parse_chat_id(query.data)

    context = await _load_group_context(client, chat_id)
    if context is None:
        await query.answer("ɢʀᴏᴜᴘ ɴᴏᴛ ғᴏᴜɴᴅ!", show_alert=True)
        return
    info, owner, owner_id, title, total = context

    group_link = await _resolve_group_link(client, chat_id, info)
    owner_mention = owner.mention if owner else "Unknown"

    await db.reject_group(chat_id)
    await query.answer("ᴛʜᴇ ɢʀᴏᴜᴘ ʜᴀs ʙᴇᴇɴ ʀᴇᴊᴇᴄᴛᴇᴅ ❌", show_alert=True)

    # NOTE: href is now properly single-quoted (legacy left it unquoted).
    await query.message.edit_text(
        f"𝑩𝒐𝒕: {temp.U_NAME}\n"
        f"𝑮𝒓𝒐𝒖𝒑: <a href='{group_link}'>{title}</a>\n"
        f"𝑰𝑫: {chat_id}\n"
        f"𝑴𝒆𝒎𝒃𝒆𝒓𝒔: {total}\n"
        f"𝑼𝒔𝒆𝒓: {owner_mention}\n\n"
        f"Rᴇᴊᴇᴄᴛᴇᴅ Gʀᴏᴜᴘ ❌",
        reply_markup=_verify_button(chat_id),
    )

    # Notify the owner with troubleshooting hints.
    if owner_id:
        try:
            await client.send_message(
                chat_id=owner_id,
                text=(
                    f"#𝐑𝐞𝐣𝐞𝐜𝐭_𝐆𝐫𝐨𝐮𝐩❌\n\n"
                    f"Gʀᴏᴜᴘ Nᴀᴍᴇ: {title}\n"
                    f"Iᴅ: {chat_id}\n\n"
                    f"ʏᴏᴜʀ ɢʀᴏᴜᴘ ʜᴀs ʙᴇᴇɴ ʀᴇᴊᴇᴄᴛᴇᴅ\n\n"
                    f"ᴛʜɪꜱ ɪꜱ ᴘʀᴏʙᴀʙʟʏ ᴅᴜᴇ ᴛᴏ ᴛʜᴇ ʙᴏᴛ ɴᴏᴛ ʜᴀᴠɪɴɢ ᴀʟʟ ᴛʜᴇ "
                    f"ᴀᴅᴍɪɴ ᴘʀɪᴠɪʟᴇɢᴇꜱ.\n\n"
                    f"ɪꜰ ʏᴏᴜ ᴡɪꜱʜ ᴛᴏ ᴀᴅᴅ ᴛʜɪꜱ ʙᴏᴛ ᴀɢᴀɪɴ, ʏᴏᴜ ᴡɪʟʟ ʜᴀᴠᴇ ᴛᴏ "
                    f"ᴍᴀᴋᴇ ɪᴛ ᴀɴ ᴀᴅᴍɪɴ ᴡɪᴛʜ ᴀʟʟ ᴛʜᴇ ᴀᴅᴍɪɴ ᴘʀɪᴠɪʟᴇɢᴇꜱ ᴛᴜʀɴᴇᴅ ᴏɴ!\n\n"
                    f"ᴀꜱ ꜰᴏʀ ɴᴏᴡ, ᴄᴏɴᴛᴀᴄᴛ ꜱᴜᴘᴘᴏʀᴛ : @YourSupportBot"
                ),
            )
        except Exception as exc:
            log.warning("Could not DM owner %s about rejection: %s", owner_id, exc)


# ─────────────────────────────────────────────────────────────────────────────
# Command: /verify  (group admins request verification)
# ─────────────────────────────────────────────────────────────────────────────
@Client.on_message(filters.group & filters.command("verify"))
async def request_group_verification(bot, message):
    """A group admin (or global ADMIN) asks for the group to be verified."""
    chat = message.chat
    owner_id = message.from_user.id

    # Membership status → is the requester allowed to act?
    member = await bot.get_chat_member(chat.id, owner_id)
    is_privileged = member.status in (
        enums.ChatMemberStatus.ADMINISTRATOR,
        enums.ChatMemberStatus.OWNER,
    ) or str(owner_id) in ADMINS

    is_verified = await db.check_group_verification(chat.id)
    is_rejected = await db.rejected_group(chat.id)

    try:
        total = await bot.get_chat_members_count(chat.id)
    except Exception as exc:
        log.warning("Could not count members of %s: %s", chat.id, exc)
        total = 0

    # Resolve a shareable link for the request card.
    if chat.username:
        group_link = f"https://t.me/{chat.username}"
    else:
        try:
            invite = await bot.create_chat_invite_link(chat.id)
            group_link = invite.invite_link
        except Exception as exc:
            log.warning("Failed to create invite link for %s: %s", chat.id, exc)
            group_link = "No link available"

    # Already rejected → only privileged users get the detailed explanation.
    if is_rejected:
        if is_privileged:
            await message.reply_text(
                " ʏᴏᴜʀ ɢʀᴏᴜᴘ ʜᴀꜱ ʙᴇᴇɴ ʀᴇᴊᴇᴄᴛᴇᴅ ʙʏ ᴍʏ ᴍᴏᴅᴇʀᴀᴛᴏʀꜱ ᴀɴᴅ ᴀᴅᴍɪɴꜱ.\n\n"
                "ᴛʜɪꜱ ʜᴀᴘᴘᴇɴꜱ ᴍᴏꜱᴛʟʏ ᴡʜᴇɴ ɪ ᴅᴏ ɴᴏᴛ ʜᴀᴠᴇ ᴀʟʟ ᴛʜᴇ ᴀᴅᴍɪɴ "
                "ᴘʀɪᴠɪʟᴇɢᴇꜱ ᴛᴜʀɴᴇᴅ ᴏɴ.\n\n"
                "ᴄᴏɴᴛᴀᴄᴛ ꜱᴜᴘᴘᴏʀᴛ ꜰᴏʀ ᴀ ꜱᴏʟᴜᴛɪᴏɴ - @YourSupportBot"
            )
        else:
            await message.reply("ᴜsᴇ ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ ᴏɴʟʏ ɢʀᴏᴜᴘ ᴀᴅᴍɪɴs")
        return

    # Not rejected → must be privileged to request.
    if not is_privileged:
        await message.reply_text(text="<b>ᴜsᴇ ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ ᴏɴʟʏ ɢʀᴏᴜᴘ ᴀᴅᴍɪɴs</b>")
        return

    if is_verified:
        await message.reply("Gʀᴏᴜᴘ Aʟʀᴇᴀᴅʏ Vᴇʀɪғɪᴇᴅ ✅")
        return

    # Ensure a chat record exists before posting the request card.
    if not await db.get_chat(chat.id):
        await db.add_chat(chat.id, chat.title, owner_id)

    # Post the staff approval card. href is now properly single-quoted.
    await bot.send_message(
        chat_id=GROUP_VERIFY_LOGS,
        text=(
            f"<b>#𝐕𝐞𝐫𝐢𝐟𝐲_𝐆𝐫𝐨𝐮𝐩\n\n"
            f"𝑩𝒐𝒕: {temp.U_NAME}\n"
            f"𝑮𝒓𝒐𝒖𝒑:- <a href='{group_link}'>{chat.title}</a>\n"
            f"𝑰𝑫: {chat.id}\n"
            f"𝑴𝒆𝒎𝒃𝒆𝒓𝒔:- {total}\n"
            f"𝑼𝒔𝒆𝒓: {message.from_user.mention}</b>"
        ),
        reply_markup=InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("Tᴀᴘ Tᴏ Vᴇʀɪғʏ ✅", callback_data=f"verify_group_{chat.id}")],
                [InlineKeyboardButton("Rᴇᴊᴇᴄᴛ ⭕", callback_data=f"rejected_group_{chat.id}")],
            ]
        ),
    )
    await message.reply(
        "ᴠᴇʀɪғʏ ʀᴇǫᴜᴇsᴛ sᴇɴᴛ ᴛᴏ ᴍʏ ᴀᴅᴍɪɴ, ᴘʟᴇᴀsᴇ ᴡᴀɪᴛ ғᴏʀ ᴛʜᴇ ᴄᴏɴғɪʀᴍᴀᴛɪᴏɴ."
    )


# ─────────────────────────────────────────────────────────────────────────────
# Command: /grp_delete  (global admins purge & leave every saved group)
# ─────────────────────────────────────────────────────────────────────────────
@Client.on_message(filters.command("grp_delete") & filters.user(ADMINS))
async def purge_all_groups(bot, message):
    """Make the bot announce, leave and forget every saved group."""
    all_groups = await db.get_all_groups()
    for group in all_groups:
        gid = group["id"]
        try:
            await bot.send_message(
                gid, "The bot is now leaving this group as per the admin's instructions."
            )
            await bot.leave_chat(gid)
        except Exception as exc:
            # Legacy code printed this; we now route it through the logger.
            log.warning("Failed to leave chat %s: %s", gid, exc)

    await db.delete_all_groups()
    await message.reply_text(
        "All saved groups have been deleted and bot has left all groups."
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  ⚡ Crafted by Trinity Mods (@trinityXmods) · Trinity AutoFilter
#  If this code helped you, keep the credit alive → github.com/Trinity-Mods
#  🚫 This credit is license-locked. See brand.py.
# ═══════════════════════════════════════════════════════════════════════════════
