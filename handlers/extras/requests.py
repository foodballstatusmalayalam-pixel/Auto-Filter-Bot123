# ═══════════════════════════════════════════════════════════════════════════════
#  ⚡ TRINITY MODS · TRINITY AUTOFILTER
#  /request handler — fuzzy-resolve a title or log it to the request channel.
#  ─────────────────────────────────────────────────────────────────────────────
#  Developed & maintained by Trinity Mods (@trinityXmods)
#  GitHub   : github.com/Trinity-Mods
#  Source   : github.com/Trinity-Mods/Auto-Filter-Bot
#  Telegram : t.me/trinityXmods
#  🚫 Credit is license-locked — see brand.py. Please keep this header intact.
# ═══════════════════════════════════════════════════════════════════════════════

import asyncio
import logging

from imdb import IMDb
from rapidfuzz import process, fuzz

from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

# ── Trinity import contract ──────────────────────────────────────────────────
from config import REQ_CHANNEL, GRP_LNK
from toolbox import temp
from vault.media_index import get_search_results, get_all_files
from vault.registry import db

logger = logging.getLogger(__name__)

# A single Cinemagoer client reused across requests. IMDb() is cheap to keep
# around; the actual network calls go through asyncio.to_thread so they never
# block the event loop.
_imdb = IMDb()

# rapidfuzz score floor — a candidate title must score above this to be treated
# as the intended movie. ~80 mirrors the legacy fuzzywuzzy cutoff.
_FUZZY_CUTOFF = 80

# How many candidate titles we are willing to probe against the index before we
# give up and treat the request as "not in catalogue".
_MAX_CANDIDATE_PROBES = 5


# ──────────────────────────────────────────────────────────────────────────────
#  Spell-correction helpers
# ──────────────────────────────────────────────────────────────────────────────
def _imdb_titles(query: str):
    """Blocking IMDb search → list of plain title strings.

    Runs inside a worker thread (see callers) because Cinemagoer performs
    synchronous HTTP requests that would otherwise stall the bot.
    """
    try:
        results = _imdb.search_movie(query)
    except Exception as exc:  # cinemagoer raises a grab-bag of network errors
        logger.warning("IMDb lookup failed for %r: %s", query, exc)
        return []
    titles = []
    for movie in results:
        title = movie.get("title")
        if title:
            titles.append(title)
    return titles


async def _resolve_close_title(chat_id, wrong_name):
    """Try to map a mistyped request to a title that actually exists in the
    index.

    Strategy:
      1. Ask IMDb (off-thread) for plausible titles for the raw query.
      2. Use rapidfuzz to rank those titles against the raw query.
      3. Walk the ranked candidates; the first one that yields real files in
         the index is returned. Anything below the fuzzy cutoff is rejected.

    Returns the corrected title string, or ``None`` when nothing fit.
    """
    try:
        # Off-load the blocking Cinemagoer search so the loop stays responsive.
        candidates = await asyncio.to_thread(_imdb_titles, wrong_name)
        if not candidates:
            return None

        # Probe a bounded number of candidates so a bad query can't spin.
        for _ in range(_MAX_CANDIDATE_PROBES):
            if not candidates:
                break

            # rapidfuzz.extractOne → (title, score, index) or None.
            best = process.extractOne(
                wrong_name,
                candidates,
                scorer=fuzz.token_set_ratio,
            )
            if not best or best[1] <= _FUZZY_CUTOFF:
                return None

            corrected = best[0]
            files, _offset, _total = await get_search_results(
                chat_id=chat_id, query=corrected
            )
            if files:
                return corrected

            # That title wasn't in the index — drop it and try the next best.
            candidates.remove(corrected)

        return None
    except Exception as exc:
        logger.exception("Spell-check resolution crashed for %r: %s", wrong_name, exc)
        return None


def _available_text(file_name: str) -> str:
    """Bilingual 'it's already in the group' reply."""
    return (
        f"🎥 {file_name}\n\n"
        "The movie or series you requested is available in the group.\n\n"
        f"Group link = {GRP_LNK}\n\n"
        f"🎥 {file_name}\n\n"
        "आपने जो मूवी रिक्वेस्ट की है वो ग्रुप में उपलब्ध हैं\n\n"
        f"ग्रुप लिंक = {GRP_LNK}"
    )


def _logged_text(title: str, *, bilingual: bool) -> str:
    """Acknowledgement shown after a request is forwarded to admins."""
    english = (
        f"✅ Your movie <b>{title}</b> has been sent to our admin.\n\n"
        "🚀 We will notify you as soon as the movie is uploaded.\n\n"
        "📌 Note - The admin may be busy with other tasks, so it might take "
        "some time to upload the movie.\n\n"
    )
    hindi = (
        f"✅ आपकी फिल्म <b>{title}</b> हमारे एडमिन के पास भेज दिया गया है.\n\n"
        "🚀 जैसे ही फिल्म अपलोड होती हैं हम आपको मैसेज देंगे.\n\n"
        "📌 ध्यान दे - एडमिन अपने काम में व्यस्त हो सकते है इसलिए फिल्म अपलोड "
        "होने में टाइम लग सकता हैं"
    )
    return (english + hindi) if bilingual else hindi


def _request_card(message, user_id, query, *, header):
    """Build the (text, markup) pair for the admin request card.

    The callback_data prefixes (``not_release`` / ``not_available`` /
    ``uploaded`` / ``series`` / ``spelling_error`` / ``close_data``) are handled
    in handlers/searchcore.py — keep them byte-for-byte stable.
    """
    text = (
        f"{header}\n\n"
        f"ʙᴏᴛ - {temp.B_NAME}\n"
        f"ɴᴀᴍᴇ - {message.from_user.mention} (<code>{message.from_user.id}</code>)\n"
        f"Rᴇǫᴜᴇꜱᴛ - <code>{query}</code>"
    )
    markup = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "ɴᴏᴛ ʀᴇʟᴇᴀꜱᴇᴅ 📅",
                    callback_data=f"not_release:{user_id}:{query}",
                ),
                InlineKeyboardButton(
                    "ɴᴏᴛ ᴀᴠᴀɪʟᴀʙʟᴇ 🙅",
                    callback_data=f"not_available:{user_id}:{query}",
                ),
            ],
            [
                InlineKeyboardButton(
                    "ᴜᴘʟᴏᴀᴅᴇᴅ ✅",
                    callback_data=f"uploaded:{user_id}:{query}",
                ),
            ],
            [
                InlineKeyboardButton(
                    "ɪɴᴠᴀʟɪᴅ ғᴏʀᴍᴀᴛ 🙅",
                    callback_data=f"series:{user_id}:{query}",
                ),
                InlineKeyboardButton(
                    "ꜱᴘᴇʟʟ ᴍɪꜱᴛᴀᴋᴇ ✍️",
                    callback_data=f"spelling_error:{user_id}:{query}",
                ),
            ],
            [InlineKeyboardButton("⦉ ᴄʟᴏsᴇ ⦊", callback_data="close_data")],
        ]
    )
    return text, markup


# ───────────────────────────  ⚡ Trinity Mods · @trinityXmods  ───────────────────────────


async def _log_request(client, message, user_id, original_query, log_title, *, header):
    """Forward a request card to REQ_CHANNEL and register it as an open request
    so the indexer/autopost can DM the user once the file shows up.
    """
    card_text, card_markup = _request_card(
        message, user_id, original_query, header=header
    )
    try:
        await client.send_message(REQ_CHANNEL, card_text, reply_markup=card_markup)
    except Exception as exc:
        logger.error("Failed to post request card to REQ_CHANNEL: %s", exc)

    # Register the open request so a future matching upload pings this user.
    try:
        await db.add_open_request(user_id, log_title)
    except Exception as exc:
        logger.error("add_open_request failed for %s/%r: %s", user_id, log_title, exc)


# ──────────────────────────────────────────────────────────────────────────────
#  /request   ·   #request
# ──────────────────────────────────────────────────────────────────────────────
@Client.on_message(
    filters.command(["request", "Request"]) & filters.private
    | filters.regex("#request")
    | filters.regex("#Request")
)
async def handle_request(client, message):
    """Entry point for movie/series requests.

    Flow:
      • Empty query → show the usage hint.
      • Direct hit in the index → tell the user it's already available.
      • Fuzzy-corrected hit → same "available" reply with the fixed title.
      • Otherwise → acknowledge, post an admin card, log an open request.
    """
    raw = message.text or ""
    # Strip the trigger word; #request / #Request are left as-is by the user so
    # only the slash variants need cleaning.
    requested_movie = raw.replace("/request", "").replace("/Request", "").strip()
    user_id = message.from_user.id

    if not requested_movie:
        await message.reply_text(
            "🙅 To request a movie or webseries, please mention its name along "
            "with the year\nJust like this 👇\n<code>/request Barbie 2023</code>"
            "\n\n🙅 फिल्म रिक्वेस्ट करने के लिए कृपया फिल्म का नाम और साल साथ में "
            "लिखें\nकुछ इस तरह 👇\n<code>/request Barbie 2023</code>"
        )
        return

    # 1) Exact-ish match already in the index?
    files, _offset, _total = await get_search_results(
        chat_id=message.chat.id, query=requested_movie
    )
    if files:
        await message.reply_text(_available_text(files[0]["file_name"]))
        return

    # 2) Try to repair a possible spelling mistake against IMDb + the index.
    corrected = await _resolve_close_title(
        chat_id=message.chat.id, wrong_name=requested_movie
    )
    if corrected:
        files, _offset, _total = await get_search_results(
            chat_id=message.chat.id, query=corrected
        )
        if files:
            # The corrected title is genuinely available — surface it.
            await message.reply_text(_available_text(files[0]["file_name"]))
            return

        # Corrected to a real title but we don't have the file → log it.
        await message.reply_text(_logged_text(corrected, bilingual=True))
        await _log_request(
            client,
            message,
            user_id,
            requested_movie,
            corrected,
            header="☏ #𝙍𝙀𝙌𝙐𝙀𝙎𝙏𝙀𝘿_𝘾𝙊𝙉𝙏𝙀𝙉𝙏 ☎︎",
        )
        return

    # 3) Nothing matched — acknowledge and log the raw query for the admins.
    await message.reply_text(_logged_text(requested_movie, bilingual=False))
    await _log_request(
        client,
        message,
        user_id,
        requested_movie,
        requested_movie,
        header="📝 #REQUESTED_CONTENT 📝",
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  ⚡ Crafted by Trinity Mods (@trinityXmods) · Trinity AutoFilter
#  If this code helped you, keep the credit alive → github.com/Trinity-Mods
#  🚫 This credit is license-locked. See brand.py.
# ═══════════════════════════════════════════════════════════════════════════════
