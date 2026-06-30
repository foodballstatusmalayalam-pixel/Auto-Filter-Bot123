# ═══════════════════════════════════════════════════════════════════════════════
#  ⚡ TRINITY MODS · TRINITY AUTOFILTER
#  Redeem-code system — generate, redeem, list and purge premium gift codes
#  ─────────────────────────────────────────────────────────────────────────────
#  Developed & maintained by Trinity Mods (@trinityXmods)
#  GitHub   : github.com/Trinity-Mods
#  Source   : github.com/Trinity-Mods/Auto-Filter-Bot
#  Telegram : t.me/trinityXmods
#  🚫 Credit is license-locked — see brand.py. Please keep this header intact.
# ═══════════════════════════════════════════════════════════════════════════════

import re
import string
import random
import hashlib
import logging
from datetime import datetime, timedelta, timezone

import pytz
from pyrogram import Client, filters
from pyrogram.errors import RPCError

from config import ADMINS, PREMIUM_LOGS
from vault.registry import db

logger = logging.getLogger(__name__)

# IST is used purely for *human-readable* display; everything persisted/compared
# internally is stored as tz-aware UTC (see grant_premium below).
IST = pytz.timezone("Asia/Kolkata")

# Codes are 10 chars from this alphabet → 36^10 keyspace, plenty for gift codes.
_CODE_ALPHABET = string.ascii_uppercase + string.digits
_CODE_LENGTH = 10

# Map a duration *unit* (singular stem) to its length in seconds. The regex below
# accepts both singular and plural spellings; we normalise to the stem to look up.
_UNIT_SECONDS = {
    "minute": 60,
    "hour": 60 * 60,
    "day": 24 * 60 * 60,
    "week": 7 * 24 * 60 * 60,
    "month": 30 * 24 * 60 * 60,
}

# e.g. "1month", "30 minutes", "2 weeks" — number then a known unit.
_DURATION_RE = re.compile(
    r"(\d+)\s*(minutes?|hours?|days?|weeks?|months?)$",
    re.IGNORECASE,
)


# ── crypto / parsing helpers ────────────────────────────────────────────────────
def _hash_code(plaintext: str) -> str:
    """Return the SHA-256 hex digest of a code.

    We NEVER persist the plaintext code — only this hash lands in the DB, so a
    leaked database dump cannot be used to redeem anybody's codes.
    """
    return hashlib.sha256(plaintext.encode()).hexdigest()


def _parse_duration(duration_str: str):
    """Convert a human duration like '2weeks' into a number of seconds.

    Returns ``None`` when the string is not a recognised duration so callers can
    surface a friendly error instead of crashing.
    """
    match = _DURATION_RE.match(duration_str.strip().lower())
    if not match:
        return None
    value, unit = match.groups()
    # Strip a trailing 's' to reduce the plural spelling to its singular stem.
    stem = unit.rstrip("s")
    multiplier = _UNIT_SECONDS.get(stem)
    if multiplier is None:
        return None
    return int(value) * multiplier


async def _grant_premium(user_id: int, seconds: int) -> datetime:
    """Grant ``user_id`` premium that expires ``seconds`` from now.

    Expiry is stored as a tz-aware UTC datetime so registry.has_premium_access
    (which compares against ``datetime.now(timezone.utc)``) works correctly. The
    aware UTC value is returned so the caller can render it in IST for display.
    """
    expiry_utc = datetime.now(timezone.utc) + timedelta(seconds=seconds)
    await db.update_user({"id": user_id, "expiry_time": expiry_utc})
    return expiry_utc


async def _new_code(duration_str: str) -> str:
    """Mint a fresh code, store only its hash + metadata, and return the plaintext.

    The plaintext is handed back to the admin exactly once (in the reply); it is
    deliberately not written to the database.
    """
    plaintext = "".join(random.choices(_CODE_ALPHABET, k=_CODE_LENGTH))
    await db.codes.insert_one({
        "code_hash": _hash_code(plaintext),
        "duration": duration_str,
        "used": False,
        "user_id": None,
        "created_at": datetime.now(timezone.utc),
    })
    return plaintext


# ── /code — admin: generate a redeemable premium code ───────────────────────────
@Client.on_message(filters.command("code") & filters.user(ADMINS))
async def cmd_generate_code(client, message):
    # Expect exactly: /code <duration>
    if len(message.command) != 2:
        await message.reply_text("Usage: /code 1month")
        return

    duration_str = message.command[1]
    if _parse_duration(duration_str) is None:
        await message.reply_text(
            "❌ ɪɴᴠᴀʟɪᴅ ᴅᴜʀᴀᴛɪᴏɴ ғᴏʀᴍᴀᴛ. ᴘʟᴇᴀsᴇ ᴇɴᴛᴇʀ ᴀ ᴠᴀʟɪᴅ ᴅᴜʀᴀᴛɪᴏɴ ʟɪᴋᴇ "
            "'1minute', '1hours', '1days', '1months', etc."
        )
        return

    token = await _new_code(duration_str)
    await message.reply_text(
        f"✅ ᴄᴏᴅᴇ ɢᴇɴᴇʀᴀᴛᴇᴅ sᴜᴄᴄᴇssғᴜʟʟʏ ♻️\n\n"
        f"🔑 ᴄᴏᴅᴇ: `{token}`\n"
        f"⌛ Vᴀʟɪᴅɪᴛʏ: {duration_str}\n\n"
        f"𝐔𝐬𝐚𝐠𝐞 : /redeem {token}\n\n"
        f"𝐍𝐨𝐭𝐞 : ᴄᴏᴅᴇ ᴜꜱᴀɢᴇ ɪꜱ ʟɪᴍɪᴛᴇᴅ ᴛᴏ ᴀ ꜱɪɴɢʟᴇ ᴜꜱᴇʀ ᴏɴʟʏ"
    )


# ───────────────────────────  ⚡ Trinity Mods · @trinityXmods  ───────────────────────────


# ── /redeem — user: redeem a code for premium access ────────────────────────────
@Client.on_message(filters.command("redeem"))
async def cmd_redeem_code(client, message):
    # Expect exactly: /redeem <code>
    if len(message.command) != 2:
        await message.reply_text("Usage: /redeem <code>")
        return

    code = message.command[1]
    user_id = message.from_user.id

    # Already-premium users cannot stack codes — bail out early and clearly.
    if await db.has_premium_access(user_id):
        await message.reply_text("❌ ʏᴏᴜ ᴀʟʀᴇᴀᴅʏ ʜᴀᴠᴇ ᴘʀᴇᴍɪᴜᴍ ᴀᴄᴄᴇss.")
        return

    code_hash = _hash_code(code)

    # ATOMIC redemption: flip used False→True and stamp the owner in a single op.
    # Because the filter requires ``used: False``, two users racing on the same
    # code can never both win — exactly one find_one_and_update matches; the other
    # gets ``None`` back and is told the code is already used.
    code_doc = await db.codes.find_one_and_update(
        {"code_hash": code_hash, "used": False},
        {"$set": {"used": True, "user_id": user_id}},
    )

    if code_doc is None:
        # Either the code never existed, or it was already claimed. Disambiguate
        # for a better message without leaking whether the hash exists.
        existing = await db.codes.find_one({"code_hash": code_hash})
        if existing is not None:
            await message.reply_text("🚫 ᴛʜɪs ᴄᴏᴅᴇ ʜᴀꜱ ʙᴇᴇɴ ᴀʟʀᴇᴀᴅʏ ᴜꜱᴇᴅ!!")
        else:
            await message.reply_text("🚫 ɪɴᴠᴀʟɪᴅ ᴏʀ ᴇxᴘɪʀᴇᴅ ᴄᴏᴅᴇ.")
        return

    # We won the code. Resolve its validity window and grant premium.
    seconds = _parse_duration(code_doc.get("duration", ""))
    if seconds is None:
        # Malformed stored duration — roll the claim back so the code isn't burned.
        await db.codes.update_one(
            {"_id": code_doc["_id"]},
            {"$set": {"used": False, "user_id": None}},
        )
        await message.reply_text("🚫 ɪɴᴠᴀʟɪᴅ ᴅᴜʀᴀᴛɪᴏɴ ɪɴ ᴛʜᴇ ᴄᴏᴅᴇ.")
        return

    expiry_utc = await _grant_premium(user_id, seconds)
    expiry_display = expiry_utc.astimezone(IST).strftime(
        "⌛️ ᴇxᴘɪʀʏ ᴅᴀᴛᴇ: %d-%m-%Y\n⏱️ ᴇxᴘɪʀʏ ᴛɪᴍᴇ: %I:%M:%S %p"
    )
    await message.reply_text(
        f"🎉 ᴄᴏᴅᴇ ʀᴇᴅᴇᴇᴍᴇᴅ sᴜᴄᴄᴇssғᴜʟʟʏ!\n"
        f"ʏᴏᴜ ʜᴀᴠᴇ ᴜɴʟᴏᴄᴋᴇᴅ ᴘʀᴇᴍɪᴜᴍ ᴀᴄᴄᴇꜱꜱ ᴜɴᴛɪʟ:\n\n"
        f"✨ᴅᴜʀᴀᴛɪᴏɴ: {code_doc['duration']}\n{expiry_display}"
    )

    # Best-effort audit trail to the premium log channel (never block the user).
    if PREMIUM_LOGS:
        try:
            await client.send_message(
                PREMIUM_LOGS,
                f"🎟️ <b>Code redeemed</b>\n"
                f"👤 User: <code>{user_id}</code>\n"
                f"⌛ Duration: {code_doc['duration']}",
            )
        except RPCError as err:
            logger.warning("Could not post redeem log to PREMIUM_LOGS: %s", err)


# ── /clearcodes — admin: purge every stored code ────────────────────────────────
@Client.on_message(filters.command("clearcodes") & filters.user(ADMINS))
async def cmd_clear_codes(client, message):
    result = await db.codes.delete_many({})
    if result.deleted_count > 0:
        await message.reply_text(
            f"✅ ᴀʟʟ {result.deleted_count} ᴄᴏᴅᴇs ʜᴀᴠᴇ ʙᴇᴇɴ ʀᴇᴍᴏᴠᴇᴅ sᴜᴄᴄᴇssғᴜʟʟʏ."
        )
    else:
        await message.reply_text("⚠️ ɴᴏ ᴄᴏᴅᴇs ғᴏᴜɴᴅ ᴛʜᴀᴛ ᴄᴏᴜʟᴅ ʙᴇ ᴄʟᴇᴀʀᴇᴅ.")


# ── /allcodes — admin: list every code's metadata ───────────────────────────────
@Client.on_message(filters.command("allcodes") & filters.user(ADMINS))
async def cmd_all_codes(client, message):
    all_codes = await db.codes.find({}).to_list(length=None)
    if not all_codes:
        await message.reply_text("⚠️ ᴛʜᴇʀᴇ ᴀʀᴇ ɴᴏ ᴄᴏᴅᴇs ᴀᴠᴀɪʟᴀʙʟᴇ.")
        return

    lines = ["📝 **ɢᴇɴᴇʀᴀᴛᴇᴅ ᴄᴏᴅᴇs ᴅᴇᴛᴀɪʟs:**\n\n"]
    for code_data in all_codes:
        duration = code_data.get("duration", "Unknown")
        used = "Yes ✅" if code_data.get("used", False) else "No ⭕"

        # created_at is stored tz-aware UTC; render it in IST. Guard legacy rows.
        created_raw = code_data.get("created_at")
        if isinstance(created_raw, datetime):
            if created_raw.tzinfo is None:
                created_raw = created_raw.replace(tzinfo=timezone.utc)
            created_at = created_raw.astimezone(IST).strftime("%d-%m-%Y %I:%M %p")
        else:
            created_at = "Unknown"

        # We only persist the hash, so we can no longer show the plaintext code.
        # Surface a short hash fingerprint to help admins eyeball/diff entries.
        code_fingerprint = code_data.get("code_hash", "Unknown")[:12]

        redeemer_id = code_data.get("user_id")
        if redeemer_id:
            user_mention = f"[user](tg://user?id={redeemer_id})"
            try:
                user = await client.get_users(redeemer_id)
                display = user.first_name or "Unknown User"
                user_mention = f"[{display}](tg://user?id={redeemer_id})"
            except RPCError as err:
                logger.warning("Could not resolve redeemer %s: %s", redeemer_id, err)
        else:
            user_mention = "Not Redeemed"

        lines.append(
            f"**🔑 Hash**: `{code_fingerprint}…`\n"
            f"**⌛ Duration**: {duration}\n"
            f"**‼ Used**: {used}\n"
            f"**🕓 Created At**: {created_at}\n"
            f"**🙎 User ID**: {user_mention}\n\n"
        )

    # Telegram caps messages at 4096 chars — chunk the report so it always sends.
    report = "".join(lines)
    for start in range(0, len(report), 4096):
        await message.reply_text(report[start:start + 4096])


# ═══════════════════════════════════════════════════════════════════════════════
#  ⚡ Crafted by Trinity Mods (@trinityXmods) · Trinity AutoFilter
#  If this code helped you, keep the credit alive → github.com/Trinity-Mods
#  🚫 This credit is license-locked. See brand.py.
# ═══════════════════════════════════════════════════════════════════════════════
