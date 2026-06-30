# ═══════════════════════════════════════════════════════════════════════════════
#  ⚡ TRINITY MODS · TRINITY AUTOFILTER
#  config.py — every deployer-tunable setting, read from environment variables.
#  ─────────────────────────────────────────────────────────────────────────────
#  Developed & maintained by Trinity Mods (@trinityXmods)
#  GitHub   : github.com/Trinity-Mods
#  Source   : github.com/Trinity-Mods/Auto-Filter-Bot
#  Telegram : t.me/trinityXmods
#  🚫 Credit is license-locked — see brand.py. Please keep this header intact.
# ═══════════════════════════════════════════════════════════════════════════════
"""
HOW TO CONFIGURE
================
Every setting below reads from an environment variable (recommended for
Koyeb / Render / Railway / Docker / VPS). The value after the comma is the
DEFAULT used when the variable is not set. Read the comment above each line to
know exactly what to put. Lines marked "🔴 REQUIRED" MUST be filled in.

See ``sample.env`` for a copy-paste template of every variable.

A note on names: the EXTERNAL variable names (BOT_TOKEN, API_ID, ...) are kept
standard so existing deployments keep working. A couple of legacy typo'd keys
(FILE_LIMITE, SEND_ALL_LIMITE) are still honoured as fall-backs, but the cleaner
new names (DAILY_FILE_LIMIT, DAILY_SENDALL_LIMIT) are preferred.
"""

import re
from os import environ, getenv

from phrases import phrases

# Matches an optionally-negative integer (e.g. a -100… channel id or a user id).
id_pattern = re.compile(r"^-?\d+$")


def is_enabled(value: str, default: bool) -> bool:
    """Parse a truthy/falsy env string into a bool, falling back to ``default``."""
    if value is None:
        return default
    value = str(value).strip().lower()
    if value in ("true", "yes", "1", "enable", "on", "y"):
        return True
    if value in ("false", "no", "0", "disable", "off", "n"):
        return False
    return default


def as_int(value, default=0) -> int:
    """Best-effort int() that never raises (returns ``default`` on bad input)."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


# ──────────────────────────── BOT IDENTITY ──────────────────────────────────
# Pyrogram session name. You usually do not need to change this.
SESSION = environ.get("SESSION", "TrinityFilter")
# 🔴 REQUIRED — Telegram API ID from https://my.telegram.org/apps
API_ID = as_int(environ.get("API_ID", "0"))
# 🔴 REQUIRED — Telegram API HASH from https://my.telegram.org/apps
API_HASH = environ.get("API_HASH", "")
# 🔴 REQUIRED — Bot token from https://t.me/BotFather
BOT_TOKEN = environ.get("BOT_TOKEN", "")
# Timezone used across the bot (dates, daily resets). Default: Asia/Kolkata.
TIMEZONE = environ.get("TIMEZONE", "Asia/Kolkata")

# ──────────────────────────── LOOK & FEEL ───────────────────────────────────
# Seconds Telegram caches inline results. Leave as default.
CACHE_TIME = as_int(environ.get("CACHE_TIME", "300"), 300)
# Also search inside file captions (not just filenames). True / False.
USE_CAPTION_FILTER = is_enabled(environ.get("USE_CAPTION_FILTER", "True"), True)
# Space-separated image URLs shown at random on the /start photo.
PICS = (environ.get(
    "PICS",
    "https://envs.sh/z_N.jpg https://envs.sh/z_H.jpg https://envs.sh/z_f.jpg "
    "https://envs.sh/z_a.jpg https://envs.sh/z_m.jpg"
)).split()
# Optional welcome video URL.
WELCOME_VID = environ.get("WELCOME_VID", "")
# Emoji reactions the bot randomly reacts with. No need to change.
REACTION = ["🔥", "❤️", "😍", "⚡", "👍", "🥰", "👏", "😁", "🎉", "🤩", "🙏", "👌", "🕊", "😇", "🤗", "😘", "🙊", "😎"]

# ──────────────────────────── IMAGES (PREMIUM / REFER / VERIFY) ──────────────
REFFER_PIC = environ.get("REFFER_PIC", "https://envs.sh/KH7.jpg")
PREMIUM_PIC = environ.get("SUBSCRIPTION", "https://envs.sh/KH8.jpg")
QR_CODE = environ.get("QR_CODE", "")
VERIFY_IMG = environ.get("VERIFY_IMG", "https://graph.org/file/1669ab9af68eaa62c3ca4.jpg")

# ──────────────────────────── ADMINS · CHANNELS · USERS ─────────────────────
# 🔴 REQUIRED — Telegram user IDs of bot admins. Separate multiple IDs by space.
ADMINS = [int(a) if id_pattern.search(a) else a for a in environ.get("ADMINS", "").split()]
# Your Telegram username WITHOUT @ (used for payment/contact). e.g. yourname
OWNER_USER_NAME = environ.get("OWNER_USER_NAME", "")
# Channel(s) the bot auto-indexes files from. Username/ID, separated by space.
CHANNELS = [int(c) if id_pattern.search(c) else c for c in environ.get("CHANNELS", "0").split()]
# Channel IDs (comma-separated) where newly added movies are auto-posted.
POST_CHANNELS = [as_int(c.strip()) for c in environ.get("POST_CHANNELS", "0").split(",") if c.strip()]
# Force-subscribe channel(s). Users must join to use the bot. Space-separated, 0 = off.
# Supports a SINGLE id (legacy) or MULTIPLE ids (new) — both work.
AUTH_CHANNELS = [as_int(c) for c in environ.get("AUTH_CHANNEL", "0").split() if c.strip()]
AUTH_CHANNEL = AUTH_CHANNELS[0] if AUTH_CHANNELS else 0   # legacy single-channel alias
# Force-subscribe channel used by the request feature. 0 = disabled.
AUTH_REQ_CHANNEL = as_int(environ.get("AUTH_REQ_CHANNEL", "0"))
# Log a message when a search returns no result. True / False.
NO_RESULTS_MSG = is_enabled(environ.get("NO_RESULTS_MSG", "True"), False)

# ──────────────────────────── MONGODB ───────────────────────────────────────
# 🔴 REQUIRED — MongoDB connection URI from https://www.mongodb.com (Atlas).
DATABASE_URI = environ.get("DATABASE_URI", "")
DATABASE_NAME = environ.get("DATABASE_NAME", "TrinityFilter")
# Files collection name (use a unique name per bot).
COLLECTION_NAME = environ.get("COLLECTION_NAME", "Trinity_files")

# ──────────────────────────── STREAM LINK SHORTENER ─────────────────────────
STREAM_SITE = environ.get("STREAM_SITE", "")
STREAM_API = environ.get("STREAM_API", "")
# "How to open" tutorial link shown with shortened stream links.
STREAM_HTO = environ.get("STREAMHTO", "")
STREAMHTO = STREAM_HTO            # legacy alias — some handlers imported both spellings
STREAM_MODE = is_enabled(environ.get("STREAM_MODE", "False"), False)

# ──────────────────────────── TOKEN VERIFICATION (3 TIERS) ──────────────────
IS_VERIFY = is_enabled(environ.get("IS_VERIFY", "False"), False)
VERIFY_URL = environ.get("VERIFY_URL", "")
VERIFY_API = environ.get("VERIFY_API", "")
TWO_VERIFY_GAP = as_int(environ.get("TWO_VERIFY_GAP", "600"), 600)
VERIFY_URL2 = environ.get("VERIFY_URL2", "")
VERIFY_API2 = environ.get("VERIFY_API2", "")
THIRD_VERIFY_GAP = as_int(environ.get("THIRD_VERIFY_GAP", "600"), 600)
VERIFY_URL3 = environ.get("VERIFY_URL3", "")
VERIFY_API3 = environ.get("VERIFY_API3", "")
TUTORIAL = environ.get("TUTORIAL", "")
TUTORIAL2 = environ.get("TUTORIAL2", "")
TUTORIAL3 = environ.get("TUTORIAL3", "")
# Secret used to HMAC-sign verify/deep-link payloads (security hardening). Set a
# long random string in production. A default is provided so the bot still runs.
VERIFY_SECRET = environ.get("VERIFY_SECRET", "trinity-mods-change-me")

# ──────────────────────────── LIMITS · PREMIUM · REFERRAL ───────────────────
# Daily free-user file limit. New name preferred; old FILE_LIMITE still honoured.
FILE_LIMITE = as_int(environ.get("DAILY_FILE_LIMIT") or environ.get("FILE_LIMITE") or "5", 5)
# Daily free-user "Send All" limit. New name preferred; old key still honoured.
SEND_ALL_LIMITE = as_int(environ.get("DAILY_SENDALL_LIMIT") or environ.get("SEND_ALL_LIMITE") or "2", 2)
DAILY_FILE_LIMIT = FILE_LIMITE          # clean aliases
DAILY_SENDALL_LIMIT = SEND_ALL_LIMITE
# Turn the daily file/button limit system on or off. True / False.
LIMIT_MODE = is_enabled(environ.get("LIMIT_MODE", "False"), False)
# How long premium earned via referral lasts (seconds). Default 30 days.
REFERAL_TIME = as_int(environ.get("REFERAL_USER_TIME", "2592000"), 2592000)
# Referral points required to unlock premium.
REFFER_POINT = as_int(environ.get("USER_POINT", "50"), 50)
# Free trial length in seconds (was hardcoded to 300). Configurable now.
TRIAL_TIME = as_int(environ.get("TRIAL_TIME", "300"), 300)
# Channel where premium purchase logs are posted (e.g. -1001234567890). Optional.
_premium = environ.get("PREMIUM_LOGS", "0")
PREMIUM_LOGS = int(_premium) if _premium and id_pattern.search(_premium) else None

# ──────────────────────────── AUTO FILE DELETE ─────────────────────────────
# Auto-delete sent files after a delay (reduces copyright exposure). True / False.
AUTO_FILE_DELETE = is_enabled(environ.get("AUTO_FILE_DELETE", "True"), False)
# Seconds before a delivered file is auto-deleted (was a hardcoded 600).
AUTO_DELETE_TIME = as_int(environ.get("AUTO_DELETE_TIME", "600"), 600)
# Channel(s) whose media uploads trigger DB deletion. Space-separated.
DELETE_CHANNELS = [int(d) if id_pattern.search(d) else d for d in environ.get("DELETE_CHANNELS", "0").split()]

# ──────────────────────────── RESULT BUTTONS / SEARCH UX ────────────────────
# Max result buttons per page when MAX_BTN is off.
MAX_B_TN = environ.get("MAX_B_TN", "7")
# Show 10 buttons/page (True) instead of MAX_B_TN. True / False.
MAX_BTN = is_enabled(environ.get("MAX_BTN", "True"), True)
# Show filename + size in one button instead of two. True / False.
SINGLE_BUTTON = is_enabled(environ.get("SINGLE_BUTTON", "True"), True)
# Show IMDb poster + details with results. True / False.
IMDB = is_enabled(environ.get("IMDB", "False"), False)
# Automatic filtering of files in groups. True / False.
AUTO_FFILTER = is_enabled(environ.get("AUTO_FFILTER", "True"), True)
# Auto-delete the result message itself. True / False.
AUTO_DELETE = is_enabled(environ.get("AUTO_DELETE", "True"), True)
# Allow users to search & get files inside the bot's PM. True / False.
PM_FILTER = is_enabled(environ.get("PM_FILTER", "True"), False)
# Suggest similar movies when nothing is found (spell-check). True / False.
SPELL_CHECK_REPLY = is_enabled(environ.get("SPELL_CHECK_REPLY", "True"), True)
# Seconds before spell-check suggestions time out (was an inconsistent 120).
SPELL_TIMEOUT = as_int(environ.get("SPELL_TIMEOUT", "60"), 60)
# Custom caption attached to every file the bot sends.
CUSTOM_FILE_CAPTION = environ.get("CUSTOM_FILE_CAPTION", f"{phrases.CAPTION}")
# Custom IMDb result template. Leave default unless you know the placeholders.
IMDB_TEMPLATE = environ.get("IMDB_TEMPLATE", f"{phrases.IMDB_TEMPLATE_TXT}")
# Use the long IMDb storyline instead of the short one. True / False.
LONG_IMDB_DESCRIPTION = is_enabled(environ.get("LONG_IMDB_DESCRIPTION", "False"), False)
# Trim long cast/crew lists to this many entries. Empty = full list.
MAX_LIST_ELM = environ.get("MAX_LIST_ELM", None)
# Send a welcome message when added to a new group. True / False.
MELCOW_NEW_USERS = is_enabled(environ.get("MELCOW_NEW_USERS", "True"), True)

# ──────────────────────────── LINKS · LOGS · SUPPORT ────────────────────────
# Your main group invite link (shown to users).
GRP_LNK = environ.get("GRP_LNK", "")
# Your updates channel link (shown to users). The LOCKED Trinity repo button is
# added separately and automatically — this is your OWN channel.
CHNL_LNK = environ.get("CHNL_LNK", "")
# Pop-up alert text shown when a user taps something not meant for them.
MSG_ALRT = environ.get("MSG_ALRT", "Wʜᴀᴛ Aʀᴇ Yᴏᴜ Lᴏᴏᴋɪɴɢ Aᴛ ?")
# 🔴 REQUIRED — Log channel ID where the bot posts logs. Bot must be admin there.
LOG_CHANNEL = as_int(environ.get("LOG_CHANNEL", "0"))
# Channel where group-verification stats are posted. 0 = use log channel.
GROUP_VERIFY_LOGS = as_int(environ.get("GROUP_VERIFY_LOGS", LOG_CHANNEL if LOG_CHANNEL else 0))
# Channel where movie requests are sent. 0 = use log channel.
REQ_CHANNEL = as_int(environ.get("REQ_CHANNEL", LOG_CHANNEL if LOG_CHANNEL else 0))
# Channel used to confirm indexing requests. 0 = use log channel.
INDEX_REQ_CHANNEL = as_int(environ.get("INDEX_REQ_CHANNEL", LOG_CHANNEL if LOG_CHANNEL else 0))
# Your support bot/group username WITHOUT @ (shown as the Support button).
SUPPORT_CHAT = environ.get("SUPPORT_CHAT", "")

# ──────────────────────────── ANALYTICS (NEW) ──────────────────────────────
# Record search queries to power /trending + the analytics dashboard. True/False.
INSIGHTS_MODE = is_enabled(environ.get("INSIGHTS_MODE", "True"), True)

# ──────────────────────────── STREAMING WEB SERVER ─────────────────────────
# 🔴 REQUIRED for streaming — Channel ID where streamed files are stored (bin).
BIN_CHANNEL = as_int(environ.get("BIN_CHANNEL", "0"))
# Web server port. Set by the platform; defined ONCE here (legacy code set it twice).
PORT = as_int(environ.get("PORT", "8080"), 8080)
# Set True if your platform exposes the app without a port in the URL.
NO_PORT = is_enabled(environ.get("NO_PORT", "False"), True)
# Address the web server binds to. Usually 0.0.0.0.
BIND_ADRESS = str(getenv("WEB_SERVER_BIND_ADDRESS", "0.0.0.0"))
SLEEP_THRESHOLD = as_int(environ.get("SLEEP_THRESHOLD", "60"), 60)
WORKERS = as_int(environ.get("WORKERS", "50"), 50)
SESSION_NAME = str(environ.get("SESSION_NAME", "TrinityFilter"))
MULTI_CLIENT = False
PING_INTERVAL = as_int(environ.get("PING_INTERVAL", "1200"), 1200)
HAS_SSL = is_enabled(environ.get("HAS_SSL", "False"), False)

# Heroku compatibility (auto-detected). TMSL = "Trinity Mods Streaming Link" — your
# app's public domain WITHOUT https:// and a trailing slash — e.g. my-app.koyeb.app
APP_NAME = None
if "DYNO" in environ:
    ON_HEROKU = True
    APP_NAME = environ.get("APP_NAME")
else:
    ON_HEROKU = False
# TMSL = Trinity Mods Streaming Link — the public domain used to build stream links.
_tmsl = getenv("TMSL")
if ON_HEROKU and not _tmsl:
    TMSL = f"{APP_NAME}.herokuapp.com"
else:
    TMSL = _tmsl or BIND_ADRESS
# Public base URL used to build stream/watch links.
if ON_HEROKU or NO_PORT:
    URL = f"https://{TMSL}/"
else:
    URL = f"https://{TMSL}:{PORT}/"

# ──────────────────────────── STARTUP LOG SUMMARY ──────────────────────────
LOG_STR = "Current Trinity AutoFilter configuration:\n"
LOG_STR += ("• IMDB cards: ON — search results show IMDb details.\n" if IMDB else "• IMDB cards: OFF.\n")
LOG_STR += ("• SINGLE_BUTTON: ON — name+size in one button.\n" if SINGLE_BUTTON else "• SINGLE_BUTTON: OFF — name and size as separate buttons.\n")
LOG_STR += (f"• CUSTOM_FILE_CAPTION set.\n" if CUSTOM_FILE_CAPTION else "• Default file caption in use.\n")
LOG_STR += ("• Long IMDb storyline: ON.\n" if LONG_IMDB_DESCRIPTION else "• Long IMDb storyline: OFF (short plot).\n")
LOG_STR += ("• Spell-check suggestions: ON.\n" if SPELL_CHECK_REPLY else "• Spell-check suggestions: OFF.\n")
LOG_STR += (f"• Cast/crew lists trimmed to {MAX_LIST_ELM} entries.\n" if MAX_LIST_ELM else "• Full cast/crew lists shown.\n")

# ───────────────────────────  ⚡ Trinity Mods · @trinityXmods  ───────────────────────────

# ═══════════════════════════════════════════════════════════════════════════════
#  ⚡ Crafted by Trinity Mods (@trinityXmods) · Trinity AutoFilter
#  If this code helped you, keep the credit alive → github.com/Trinity-Mods
#  🚫 This credit is license-locked. See brand.py.
# ═══════════════════════════════════════════════════════════════════════════════
