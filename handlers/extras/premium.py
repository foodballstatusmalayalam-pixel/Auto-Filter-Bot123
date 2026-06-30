# ═══════════════════════════════════════════════════════════════════════════════
#  ⚡ TRINITY MODS · TRINITY AUTOFILTER
#  Premium suite — admin grant/revoke, user plan lookups, plans showcase & the
#  background sweeper that expires lapsed premium subscriptions.
#  ─────────────────────────────────────────────────────────────────────────────
#  Developed & maintained by Trinity Mods (@trinityXmods)
#  GitHub   : github.com/Trinity-Mods
#  Source   : github.com/Trinity-Mods/Auto-Filter-Bot
#  Telegram : t.me/trinityXmods
#  🚫 Credit is license-locked — see brand.py. Please keep this header intact.
# ═══════════════════════════════════════════════════════════════════════════════

import asyncio
import logging
from datetime import datetime, timedelta, timezone

import pytz
from pyrogram import Client, filters
from pyrogram.errors import FloodWait, UserIsBlocked, InputUserDeactivated, PeerIdInvalid
from pyrogram.errors.exceptions.bad_request_400 import MessageTooLong
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from config import ADMINS, PREMIUM_LOGS, PREMIUM_PIC, QR_CODE
from phrases import phrases
from toolbox import get_seconds
from vault.registry import db

logger = logging.getLogger(__name__)

# Single source of truth for the display timezone (India Standard Time).
# The database persists every expiry as tz-aware UTC; we only convert to IST
# at presentation time so users see a local, human-friendly date.
IST = pytz.timezone("Asia/Kolkata")

# Reusable strftime pattern for "expiry date + time" lines shown to users.
_EXPIRY_FMT = "%d-%m-%Y\n⏱️ ᴇxᴘɪʀʏ ᴛɪᴍᴇ : %I:%M:%S %p"


# ─────────────────────────── small helpers ───────────────────────────

def _to_ist(moment: datetime) -> datetime:
    """Return a tz-aware IST view of ``moment``.

    Legacy rows may have been stored naive; treat those as UTC so the
    conversion never raises and the comparison below stays aware-to-aware.
    """
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(IST)


def _format_time_left(expiry: datetime) -> str:
    """Human readable 'X days, Y hours, Z minutes' remaining until ``expiry``.

    Both operands are tz-aware (IST) so the subtraction is correct regardless
    of how the original timestamp was stored.
    """
    now_ist = datetime.now(IST)
    remaining = _to_ist(expiry) - now_ist
    days = remaining.days
    hours, rem = divmod(remaining.seconds, 3600)
    minutes, _seconds = divmod(rem, 60)
    return f"{days} ᴅᴀʏꜱ, {hours} ʜᴏᴜʀꜱ, {minutes} ᴍɪɴᴜᴛᴇꜱ"


def _format_expiry(expiry: datetime) -> str:
    """Pretty IST date/time string for an expiry timestamp."""
    return _to_ist(expiry).strftime(_EXPIRY_FMT)


# ─────────────────────────── background sweeper ───────────────────────────

async def check_expired_premium(bot):
    """Continuously expire premium users whose subscription has lapsed.

    Scheduled once by the launcher. We pass a tz-aware UTC ``now`` to
    ``db.get_expired`` because expiries are stored tz-aware UTC — comparing
    aware-to-aware avoids the classic naive/aware ``TypeError``.
    """
    while True:
        try:
            # tz-aware UTC 'now' — matches how the DB persists expiry_time.
            expired_users = await db.get_expired(datetime.now(timezone.utc))
        except Exception:
            logger.exception("premium sweeper: failed to fetch expired users")
            await asyncio.sleep(60)
            continue

        for record in expired_users:
            user_id = record["id"]

            # Revoke access first so a notify failure can't leave the user
            # stuck with active-but-expired premium.
            try:
                await db.remove_premium_access(user_id)
            except Exception:
                logger.exception("premium sweeper: could not revoke access for %s", user_id)
                continue

            try:
                user = await bot.get_users(user_id)
            except (PeerIdInvalid, IndexError, KeyError) as exc:
                logger.warning("premium sweeper: cannot resolve user %s: %s", user_id, exc)
                await asyncio.sleep(0.5)
                continue
            except Exception:
                logger.exception("premium sweeper: unexpected error resolving %s", user_id)
                await asyncio.sleep(0.5)
                continue

            # Best-effort DM to the (now ex-)premium user.
            try:
                await bot.send_message(
                    chat_id=user_id,
                    text=(
                        f"<b><i>Hᴇʏ Tʜᴇʀᴇ {user.mention} 👋</i>\n\n"
                        "<u>ʏᴏᴜʀ ᴘʀᴇᴍɪᴜᴍ ᴀᴄᴄᴇss ʜᴀs ᴇxᴘɪʀᴇᴅ ❗\n"
                        "ᴛʜᴀɴᴋ ʏᴏᴜ ꜰᴏʀ ᴜsɪɴɢ ᴏᴜʀ sᴇʀᴠɪᴄᴇ.</u>\n\n"
                        "ɪꜰ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ ᴛᴀᴋᴇ ᴛʜᴇ ᴘʀᴇᴍɪᴜᴍ ᴀɢᴀɪɴ, ᴛʜᴇɴ ᴄʟɪᴄᴋ "
                        "ᴏɴ ᴛʜᴇ /plans ꜰᴏʀ ᴛʜᴇ ᴅᴇᴛᴀɪʟs ᴏꜰ ᴛʜᴇ ᴘʟᴀɴs.</b>"
                    ),
                )
            except FloodWait as exc:
                await asyncio.sleep(getattr(exc, "value", getattr(exc, "x", 0)))
            except (UserIsBlocked, InputUserDeactivated, PeerIdInvalid) as exc:
                logger.info("premium sweeper: could not DM %s: %s", user_id, exc)
            except Exception:
                logger.exception("premium sweeper: DM failed for %s", user_id)

            # Audit log to the premium-logs channel (if configured).
            if PREMIUM_LOGS:
                try:
                    await bot.send_message(
                        PREMIUM_LOGS,
                        text=(
                            f"<b>#PREMIUM_EXPIRED\n\n"
                            f"Usᴇʀ : {user.mention}\n"
                            f"Usᴇʀ Iᴅ : <code>{user_id}</code></b>"
                        ),
                    )
                except FloodWait as exc:
                    await asyncio.sleep(getattr(exc, "value", getattr(exc, "x", 0)))
                except Exception:
                    logger.exception("premium sweeper: log post failed for %s", user_id)

            await asyncio.sleep(0.5)

        await asyncio.sleep(1)


# ─────────────────────────── admin: grant premium ───────────────────────────

@Client.on_message(filters.command("add_premium") & filters.user(ADMINS))
async def add_premium_cmd(client, message):
    """/add_premium <user_id> <amount> <unit> — grant timed premium access."""
    # Expect exactly: command, user_id, amount, unit  → 4 tokens.
    if len(message.command) != 4:
        await message.reply_text(
            "Usage : /add_premium user_id time (e.g., '1 day for days', "
            "'1 hour for hours', or '1 min for minutes', or '1 month for "
            "months' or '1 year for year')"
        )
        return

    try:
        user_id = int(message.command[1])
    except ValueError:
        await message.reply_text("ᴜser_id ᴍᴜsᴛ ʙᴇ ᴀ ɴᴜᴍʙᴇʀ.")
        return

    try:
        user = await client.get_users(user_id)
    except Exception:
        logger.exception("add_premium: cannot resolve user %s", user_id)
        await message.reply_text("ᴄᴏᴜʟᴅ ɴᴏᴛ ʀᴇsᴏʟᴠᴇ ᴛʜᴀᴛ ᴜsᴇʀ ɪᴅ.")
        return

    # Rebuild the human duration string, e.g. "1 day".
    duration = f"{message.command[2]} {message.command[3]}"
    seconds = await get_seconds(duration)
    if seconds <= 0:
        await message.reply_text(
            "Invalid time format. Please use '1 day for days', '1 hour for "
            "hours', or '1 min for minutes', or '1 month for months' or "
            "'1 year for year'"
        )
        return

    # Store expiry as tz-aware UTC so the sweeper's aware comparison works.
    expiry_time = datetime.now(timezone.utc) + timedelta(seconds=seconds)
    await db.update_user({"id": user_id, "expiry_time": expiry_time})

    # Read it back to render consistent IST strings.
    data = await db.get_user(user_id)
    expiry_str = _format_expiry(data.get("expiry_time"))
    joined_str = datetime.now(IST).strftime("%d-%m-%Y\n⏱️ ᴊᴏɪɴɪɴɢ ᴛɪᴍᴇ : %I:%M:%S %p")

    await message.reply_text(
        f"ᴘʀᴇᴍɪᴜᴍ ᴀᴅᴅᴇᴅ ꜱᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ ✅\n\n"
        f"👤 ᴜꜱᴇʀ : {user.mention}\n"
        f"⚡ ᴜꜱᴇʀ ɪᴅ : <code>{user_id}</code>\n"
        f"⏰ ᴘʀᴇᴍɪᴜᴍ ᴀᴄᴄᴇꜱꜱ : <code>{duration}</code>\n\n"
        f"⏳ ᴊᴏɪɴɪɴɢ ᴅᴀᴛᴇ : {joined_str}\n\n"
        f"⌛️ ᴇxᴘɪʀʏ ᴅᴀᴛᴇ : {expiry_str}",
        disable_web_page_preview=True,
    )

    # Notify the user themselves.
    try:
        await client.send_message(
            chat_id=user_id,
            text=(
                f"👋 ʜᴇʏ {user.mention},\n"
                "ᴛʜᴀɴᴋ ʏᴏᴜ ꜰᴏʀ ᴘᴜʀᴄʜᴀꜱɪɴɢ ᴘʀᴇᴍɪᴜᴍ.\n"
                "ᴇɴᴊᴏʏ !! ✨🎉\n\n"
                f"⏰ ᴘʀᴇᴍɪᴜᴍ ᴀᴄᴄᴇꜱꜱ : <code>{duration}</code>\n"
                f"⏳ ᴊᴏɪɴɪɴɢ ᴅᴀᴛᴇ : {joined_str}\n\n"
                f"⌛️ ᴇxᴘɪʀʏ ᴅᴀᴛᴇ : {expiry_str}"
            ),
            disable_web_page_preview=True,
        )
    except (UserIsBlocked, InputUserDeactivated, PeerIdInvalid) as exc:
        logger.info("add_premium: could not DM %s: %s", user_id, exc)
    except Exception:
        logger.exception("add_premium: DM failed for %s", user_id)

    # Audit log.
    if PREMIUM_LOGS:
        try:
            await client.send_message(
                PREMIUM_LOGS,
                text=(
                    f"#Added_Premium\n\n"
                    f"👤 ᴜꜱᴇʀ : {user.mention}\n"
                    f"⚡ ᴜꜱᴇʀ ɪᴅ : <code>{user_id}</code>\n"
                    f"⏰ ᴘʀᴇᴍɪᴜᴍ ᴀᴄᴄᴇꜱꜱ : <code>{duration}</code>\n\n"
                    f"⏳ ᴊᴏɪɴɪɴɢ ᴅᴀᴛᴇ : {joined_str}\n\n"
                    f"⌛️ ᴇxᴘɪʀʏ ᴅᴀᴛᴇ : {expiry_str}"
                ),
                disable_web_page_preview=True,
            )
        except Exception:
            logger.exception("add_premium: log post failed for %s", user_id)


# ─────────────────────────── admin: revoke premium ───────────────────────────

@Client.on_message(filters.command("remove_premium") & filters.user(ADMINS))
async def remove_premium_cmd(client, message):
    """/remove_premium <user_id> — strip a user's premium access."""
    if len(message.command) != 2:
        await message.reply_text("ᴜꜱᴀɢᴇ : /remove_premium user_id")
        return

    try:
        user_id = int(message.command[1])
    except ValueError:
        await message.reply_text("ᴜser_id ᴍᴜsᴛ ʙᴇ ᴀ ɴᴜᴍʙᴇʀ.")
        return

    try:
        user = await client.get_users(user_id)
    except Exception:
        logger.exception("remove_premium: cannot resolve user %s", user_id)
        await message.reply_text("ᴄᴏᴜʟᴅ ɴᴏᴛ ʀᴇsᴏʟᴠᴇ ᴛʜᴀᴛ ᴜsᴇʀ ɪᴅ.")
        return

    if await db.remove_premium_access(user_id):
        await message.reply_text("ᴜꜱᴇʀ ʀᴇᴍᴏᴠᴇᴅ ꜱᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ !")
        try:
            await client.send_message(
                chat_id=user_id,
                text=(
                    f"<b>ʜᴇʏ {user.mention},\n\n"
                    "ʏᴏᴜʀ ᴘʀᴇᴍɪᴜᴍ ᴀᴄᴄᴇss ʜᴀs ʙᴇᴇɴ ʀᴇᴍᴏᴠᴇᴅ.\n"
                    "ᴛʜᴀɴᴋ ʏᴏᴜ ꜰᴏʀ ᴜsɪɴɢ ᴏᴜʀ sᴇʀᴠɪᴄᴇ 😊\n"
                    "ᴄʟɪᴄᴋ ᴏɴ /plans ᴛᴏ ᴄʜᴇᴄᴋ ᴏᴜᴛ ᴏᴛʜᴇʀ ᴘʟᴀɴꜱ.</b>"
                ),
            )
        except (UserIsBlocked, InputUserDeactivated, PeerIdInvalid) as exc:
            logger.info("remove_premium: could not DM %s: %s", user_id, exc)
        except Exception:
            logger.exception("remove_premium: DM failed for %s", user_id)
    else:
        await message.reply_text(
            "ᴜɴᴀʙʟᴇ ᴛᴏ ʀᴇᴍᴏᴠᴇ ᴘʀᴇᴍɪᴜᴍ ᴀᴄᴄᴇꜱꜱ ꜰʀᴏᴍ ᴛʜᴇ ᴜꜱᴇʀ !\n"
            "ᴀʀᴇ ʏᴏᴜ ꜱᴜʀᴇ, ɪᴛ ᴡᴀꜱ ᴀ ᴘʀᴇᴍɪᴜᴍ ᴜꜱᴇʀ ɪᴅ ?"
        )


# ───────────────────────────  ⚡ Trinity Mods · @trinityXmods  ───────────────────────────


# ─────────────────────────── admin: inspect a user's plan ───────────────────────────

@Client.on_message(filters.command("get_premium") & filters.user(ADMINS))
async def get_premium_cmd(client, message):
    """/get_premium <user_id> — admin view of another user's premium plan."""
    if len(message.command) != 2:
        await message.reply_text("ᴜꜱᴀɢᴇ : /get_premium user_id")
        return

    try:
        user_id = int(message.command[1])
    except ValueError:
        await message.reply_text("ᴜser_id ᴍᴜsᴛ ʙᴇ ᴀ ɴᴜᴍʙᴇʀ.")
        return

    try:
        user = await client.get_users(user_id)
    except Exception:
        logger.exception("get_premium: cannot resolve user %s", user_id)
        await message.reply_text("ᴄᴏᴜʟᴅ ɴᴏᴛ ʀᴇsᴏʟᴠᴇ ᴛʜᴀᴛ ᴜsᴇʀ ɪᴅ.")
        return

    data = await db.get_user(user_id)
    if data and data.get("expiry_time"):
        expiry = data.get("expiry_time")
        await message.reply_text(
            f"⚜️ ᴘʀᴇᴍɪᴜᴍ ᴜꜱᴇʀ ᴅᴀᴛᴀ :\n\n"
            f"👤 ᴜꜱᴇʀ : {user.mention}\n"
            f"⚡ ᴜꜱᴇʀ ɪᴅ : <code>{user_id}</code>\n"
            f"⏰ ᴛɪᴍᴇ ʟᴇꜰᴛ : {_format_time_left(expiry)}\n"
            f"⌛️ ᴇxᴘɪʀʏ ᴅᴀᴛᴇ : {_format_expiry(expiry)}"
        )
    else:
        await message.reply_text(
            "ɴᴏ ᴀɴʏ ᴘʀᴇᴍɪᴜᴍ ᴅᴀᴛᴀ ᴏꜰ ᴛʜᴇ ᴡᴀꜱ ꜰᴏᴜɴᴅ ɪɴ ᴅᴀᴛᴀʙᴀꜱᴇ !"
        )


# ─────────────────────────── user: my own plan ───────────────────────────

@Client.on_message(filters.command("myplan"))
async def myplan_cmd(client, message):
    """/myplan — show the caller their own premium status."""
    mention = message.from_user.mention
    user_id = message.from_user.id

    data = await db.get_user(user_id)
    if data and data.get("expiry_time"):
        expiry = data.get("expiry_time")
        await message.reply_text(
            f"⚜️ ᴘʀᴇᴍɪᴜᴍ ᴜꜱᴇʀ ᴅᴀᴛᴀ :\n\n"
            f"👤 ᴜꜱᴇʀ : {mention}\n"
            f"⚡ ᴜꜱᴇʀ ɪᴅ : <code>{user_id}</code>\n"
            f"⏰ ᴛɪᴍᴇ ʟᴇꜰᴛ : {_format_time_left(expiry)}\n"
            f"⌛️ ᴇxᴘɪʀʏ ᴅᴀᴛᴇ : {_format_expiry(expiry)}"
        )
    else:
        await message.reply_text(
            f"ʜᴇʏ {mention},\n\nʏᴏᴜ ᴅᴏ ɴᴏᴛ ʜᴀᴠᴇ ᴀɴʏ ᴀᴄᴛɪᴠᴇ ᴘʀᴇᴍɪᴜᴍ ᴘʟᴀɴs, "
            "ɪꜰ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ ᴛᴀᴋᴇ ᴘʀᴇᴍɪᴜᴍ ᴛʜᴇɴ ᴄʟɪᴄᴋ ᴏɴ ʙᴇʟᴏᴡ ʙᴜᴛᴛᴏɴ 👇",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton(
                    "💸 ᴄʜᴇᴄᴋᴏᴜᴛ ᴘʀᴇᴍɪᴜᴍ ᴘʟᴀɴꜱ 💸",
                    callback_data="premium_pm",
                )]]
            ),
        )


# ─────────────────────────── admin: list every premium user ───────────────────────────

@Client.on_message(filters.command("premium_users") & filters.user(ADMINS))
async def premium_users_cmd(client, message):
    """/premium_users — dump all active premium subscribers."""
    status = await message.reply_text("<i>ꜰᴇᴛᴄʜɪɴɢ...</i>")

    report = "⚜️ ᴘʀᴇᴍɪᴜᴍ ᴜꜱᴇʀꜱ ʟɪꜱᴛ :\n\n"
    count = 1

    users = await db.get_all_users()
    async for entry in users:
        uid = entry["id"]
        data = await db.get_user(uid)
        if not (data and data.get("expiry_time")):
            continue

        expiry = data.get("expiry_time")

        # Resolving each user can fail (deleted account etc.) — log & skip.
        try:
            resolved = await client.get_users(uid)
            mention = resolved.mention
        except Exception as exc:
            logger.info("premium_users: cannot resolve %s: %s", uid, exc)
            mention = f"<code>{uid}</code>"

        report += (
            f"{count}. {mention}\n"
            f"👤 ᴜꜱᴇʀ ɪᴅ : {uid}\n"
            f"⏳ ᴇxᴘɪʀʏ ᴅᴀᴛᴇ : {_format_expiry(expiry)}\n"
            f"⏰ ᴛɪᴍᴇ ʟᴇꜰᴛ : {_format_time_left(expiry)}\n"
        )
        count += 1

    # If the message is too long for Telegram, fall back to a document.
    try:
        await status.edit_text(report)
    except MessageTooLong:
        with open("usersplan.txt", "w+", encoding="utf-8") as outfile:
            outfile.write(report)
        await message.reply_document("usersplan.txt", caption="Paid Users:")
    except Exception:
        logger.exception("premium_users: failed to render report")


# ─────────────────────────── public: plans showcase ───────────────────────────

@Client.on_message(filters.command("plans"))
async def plans_cmd(client, message):
    """/plans — show the premium plan card with QR / UPI buttons."""
    # The qr_info / upi_info / premium_pm callbacks are handled in searchcore;
    # we only need to keep the callback_data prefixes identical here.
    buttons = [
        [
            InlineKeyboardButton("🔲 Qʀ ", callback_data="qr_info"),
            InlineKeyboardButton("💳 Uᴘɪ ", callback_data="upi_info"),
        ],
        [InlineKeyboardButton("❌ ᴄʟᴏꜱᴇ ❌", callback_data="close_data")],
    ]
    await message.reply_photo(
        photo=PREMIUM_PIC,
        caption=phrases.PREMIUM_CMD,
        reply_markup=InlineKeyboardMarkup(buttons),
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  ⚡ Crafted by Trinity Mods (@trinityXmods) · Trinity AutoFilter
#  If this code helped you, keep the credit alive → github.com/Trinity-Mods
#  🚫 This credit is license-locked. See brand.py.
# ═══════════════════════════════════════════════════════════════════════════════
