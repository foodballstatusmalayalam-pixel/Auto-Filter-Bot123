# ═══════════════════════════════════════════════════════════════════════════════
#  ⚡ TRINITY MODS · TRINITY AUTOFILTER
#  Channel auto-save + IMDb auto-post engine: index media from source channels and
#  publish IMDb cards to post channels on trigger keywords (with request fulfilment).
#  ─────────────────────────────────────────────────────────────────────────────
#  Developed & maintained by Trinity Mods (@trinityXmods)
#  GitHub   : github.com/Trinity-Mods
#  Source   : github.com/Trinity-Mods/Auto-Filter-Bot
#  Telegram : t.me/trinityXmods
#  🚫 Credit is license-locked — see brand.py. Please keep this header intact.
# ═══════════════════════════════════════════════════════════════════════════════

"""
What this handler does
----------------------
1. Listens on every configured source CHANNEL for incoming media (document / video
   / audio) and saves it to the searchable media index.
2. Whenever a brand-new file is saved, it best-effort fulfils any open user
   *requests* whose query matches the file name (DMing each requester).
3. Implements a small "collect then publish" state machine driven by caption
   keywords:
       • "post count"  → start collecting files for this channel
       • "send post"   → stop collecting and publish a single IMDb card that
                         bundles every collected file's deep-link to POST_CHANNELS.

Concurrency note
----------------
Telegram delivers channel updates concurrently, so the original module's two
module-level globals (``collected_files`` / ``post_active``) were a data race:
two channels (or two bursts) clobbered each other's state. We now keep all
mutable collection state in a per-chat-id dictionary, every mutation of which is
serialised behind a single ``asyncio.Lock``. That keeps each channel's batch
isolated and free of interleaving corruption.
"""

import re
import asyncio
import logging

from pyrogram import Client, filters, enums

# ── Trinity import contract ──────────────────────────────────────────────────
from config import CHANNELS, POST_CHANNELS
from toolbox import temp, get_poster, get_size
from vault.media_index import save_file, get_file_details
from vault.registry import db

logger = logging.getLogger(__name__)

# Only react to actual media (the three indexable kinds).
media_filter = filters.document | filters.video | filters.audio

# ─────────────────────────────────────────────────────────────────────────────
# Per-chat collection state.
#
# Instead of two raw module globals we keep a dict keyed by source-chat id:
#       _sessions[chat_id] = {"active": bool, "files": [ (file_id, name,
#                                                          caption, size), ... ]}
# Every read/modify happens while holding ``_state_lock`` so concurrent updates
# from the same (or different) channels can't interleave and corrupt a batch.
# ─────────────────────────────────────────────────────────────────────────────
_sessions: dict[int, dict] = {}
_state_lock = asyncio.Lock()

# Keyword triggers (matched case-insensitively against the caption).
_START_TRIGGER = "post count"
_PUBLISH_TRIGGER = "send post"

# Language-code / name normalisation table. Keys are tokens that may appear in a
# caption; values are the human-readable language we render on the IMDb card.
LANGUAGE_MAP = {
    "hin": "Hindi",
    "eng": "English",
    "en": "English",
    "tel": "Telugu",
    "tam": "Tamil",
    "jap": "Japanese",
    "mar": "Marathi",
    "guj": "Gujarati",
    "Pun": "Punjabi",
    "Hindi": "Hindi",
    "English": "English",
    "Telugu": "Telugu",
    "Tamil": "Tamil",
    "Japanese": "Japanese",
    "Marathi": "Marathi",
    "Gujarati": "Gujarati",
    "Punjabi": "Punjabi",
}

# Pre-compile the language detector once (alternation of every known token).
_LANGUAGE_RE = re.compile(r"\b(" + "|".join(map(re.escape, LANGUAGE_MAP.keys())) + r")\b")


def _session_for(chat_id: int) -> dict:
    """Return (creating if needed) the collection session for ``chat_id``.

    MUST be called while holding ``_state_lock``.
    """
    return _sessions.setdefault(chat_id, {"active": False, "files": []})


def _detect_languages(caption: str) -> str:
    """Pull recognised language tokens out of ``caption`` → comma-joined names.

    De-duplicates while preserving first-seen order so "Hindi, English" never
    becomes "Hindi, Hindi, English".
    """
    seen: list[str] = []
    for token in _LANGUAGE_RE.findall(caption or ""):
        name = LANGUAGE_MAP.get(token)
        if name and name not in seen:
            seen.append(name)
    return ", ".join(seen)


def _deeplink(file_id: str, file_name: str, size_bytes) -> str:
    """Build the HTML "📁 [size] → name" deep-link line for one file."""
    return (
        f"📁 [{get_size(size_bytes)}]👇\n"
        f"<a href='https://t.me/{temp.U_NAME}?start=files_{CHANNELS[0]}_{file_id}'>"
        f"{file_name}</a>"
    )


async def _fulfil_requests(bot, file_name: str) -> None:
    """Best-effort: notify users whose open request matches this new file.

    Failures (blocked bot, deleted account, malformed record) are swallowed per
    recipient so one bad DM never aborts the indexing flow.
    """
    try:
        matched = await db.take_matching_requests(file_name)
    except Exception:
        logger.exception("Failed to look up matching requests for %r", file_name)
        return

    for req in matched or []:
        user_id = req.get("user_id")
        if not user_id:
            continue
        try:
            await bot.send_message(
                chat_id=user_id,
                text=(
                    "✅ <b>Your requested file is now available!</b>\n\n"
                    f"🔍 You searched: <code>{req.get('query', '')}</code>\n"
                    f"📁 Added: <b>{file_name}</b>\n\n"
                    "Search it in the group to grab it. 🎬"
                ),
                parse_mode=enums.ParseMode.HTML,
            )
        except Exception:
            # Blocked us, account gone, etc. — non-fatal, just log and move on.
            logger.debug("Could not DM requester %s", user_id, exc_info=True)


# ───────────────────────────  ⚡ Trinity Mods · @trinityXmods  ───────────────────────────


@Client.on_message(filters.chat(CHANNELS) & media_filter)
async def channel_media(bot, message):
    """Save incoming channel media to the index and drive the auto-post batch."""

    # 1) Pick whichever media kind this message actually carries.
    media_obj = None
    for kind in ("document", "video", "audio"):
        media_obj = getattr(message, kind, None)
        if media_obj is not None:
            media_obj.file_type = kind
            break
    else:
        # Filter guarantees one of them, but guard anyway.
        return

    # Carry the caption onto the media object so save_file() can persist it.
    media_obj.caption = message.caption
    caption_text = message.caption or ""
    caption_lower = caption_text.lower()

    # 2) Persist to the searchable index.
    saved, file_id = await save_file(media_obj)

    # On a genuinely new save, try to fulfil any matching open requests.
    if saved and getattr(media_obj, "file_name", None):
        await _fulfil_requests(bot, media_obj.file_name)

    # If we have a file_id but get_file_details returns a richer/canonical row,
    # prefer that id. Only overwrite AFTER confirming a non-empty result so a
    # missing detail row never blanks out the id we already hold.
    if file_id:
        details = await get_file_details(file_id)
        if details:
            resolved = details[0].get("file_id")
            if resolved:
                file_id = resolved

    chat_id = message.chat.id

    # 3) Drive the collect/publish state machine under the lock so concurrent
    #    channel updates can't corrupt a batch.
    async with _state_lock:
        session = _session_for(chat_id)

        # "post count" → begin a fresh collection window for this channel.
        if saved and _START_TRIGGER in caption_lower:
            session["active"] = True
            session["files"] = []

        # While collecting, append this file (with a language-annotated caption).
        if session["active"] and file_id:
            languages = _detect_languages(caption_text)
            annotated = f"{caption_text}\n\nLanguage: {languages}"
            file_name = (getattr(media_obj, "file_name", "") or "").replace("_", " ")
            session["files"].append(
                (file_id, file_name, annotated, media_obj.file_size)
            )

        # "send post" → close the window and snapshot the batch to publish below.
        batch = None
        if saved and _PUBLISH_TRIGGER in caption_lower:
            session["active"] = False
            batch = session["files"]
            session["files"] = []  # reset so the next "post count" starts clean

    # Publish OUTSIDE the lock — network calls shouldn't block other channels.
    if batch:
        await _publish_card(bot, batch)


async def _publish_card(bot, batch: list) -> None:
    """Render and post a single IMDb card bundling every file in ``batch``."""
    if not batch:
        return

    # ── Resolve IMDb info from the FIRST file's caption (title before '|'). ──
    imdb_info = None
    # Initialise the language string BEFORE the loop so it always exists, even
    # if IMDb lookup or caption parsing falls through.
    language_in_caption = ""

    for _fid, _name, caption, _size in batch:
        # Capture the language we annotated onto this file's caption earlier.
        if "Language:" in caption:
            language_in_caption = caption.split("Language:")[-1].strip()
        try:
            movie_name = caption.split("|")[0].strip()
            logger.info("Searching IMDb for: %s", movie_name)
            imdb_info = await get_poster(movie_name)
            if not imdb_info:
                logger.warning("IMDb info not found for: %s", movie_name)
            else:
                break  # got a hit — stop probing further files
        except Exception:
            logger.exception("Error fetching IMDb info for a collected file")
        # Only consult the first file for the title (matches original behaviour).
        break

    # Pre-build every file's deep-link line (shared by both render paths).
    url_lines = "\n\n".join(
        _deeplink(fid, name, size) for fid, name, _cap, size in batch
    )

    if imdb_info:
        # Guard every dict access with .get(...) so a partial IMDb payload can't
        # raise KeyError mid-render.
        title = imdb_info.get("title", "N/A")
        rating = imdb_info.get("rating", "N/A")
        genre = imdb_info.get("genres", "N/A")
        year = imdb_info.get("year", "N/A")
        poster_url = imdb_info.get("poster")

        final_caption = (
            f"<b>🏷 Title: {title}\n"
            f"🎭 Genres: {genre}\n"
            f"📆 Year: {year}\n"
            f"🌟 Rating: {rating}\n"
            f"🔊 Language: {language_in_caption}\n\n"
            f"{url_lines}</b>"
        )
    else:
        # No IMDb data — fall back to a plain "info not available" card.
        poster_url = None
        final_caption = (
            f"<b>#Information_Not_Available\n\n"
            f"Total Files: {len(batch)}\n\n"
            f"{url_lines}</b>"
        )

    # Telegram caps photo captions at 1024 chars — trim defensively.
    photo_caption = final_caption[:1024]

    for channel in POST_CHANNELS:
        if poster_url:
            try:
                await bot.send_photo(
                    chat_id=channel,
                    photo=poster_url,
                    caption=photo_caption,
                    parse_mode=enums.ParseMode.HTML,
                )
                continue
            except Exception:
                # Poster rejected (bad dims / MediaEmpty) — fall back to text.
                logger.warning(
                    "Could not send poster to %s; sending text instead",
                    channel,
                    exc_info=True,
                )
        try:
            await bot.send_message(
                chat_id=channel,
                text=final_caption,
                parse_mode=enums.ParseMode.HTML,
            )
        except Exception:
            logger.exception("Failed to publish card to channel %s", channel)


# ═══════════════════════════════════════════════════════════════════════════════
#  ⚡ Crafted by Trinity Mods (@trinityXmods) · Trinity AutoFilter
#  If this code helped you, keep the credit alive → github.com/Trinity-Mods
#  🚫 This credit is license-locked. See brand.py.
# ═══════════════════════════════════════════════════════════════════════════════
