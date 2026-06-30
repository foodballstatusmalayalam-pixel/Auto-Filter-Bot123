# ═══════════════════════════════════════════════════════════════════════════════
#  ⚡ TRINITY MODS · TRINITY AUTOFILTER
#  /getfile — fetch IMDb metadata (with optional Hindi plot) and post to channels
#  ─────────────────────────────────────────────────────────────────────────────
#  Developed & maintained by Trinity Mods (@trinityXmods)
#  GitHub   : github.com/Trinity-Mods
#  Source   : github.com/Trinity-Mods/Auto-Filter-Bot
#  Telegram : t.me/trinityXmods
#  🚫 Credit is license-locked — see brand.py. Please keep this header intact.
# ═══════════════════════════════════════════════════════════════════════════════
"""
fetchpost.py
────────────
Implements the ``/getfile`` admin/user utility:

  1. Look up a movie/series on IMDb via :func:`toolbox.get_poster`.
  2. Optionally render a Hindi translation of the plot (googletrans).
  3. Show a preview to the requester with a yes/no confirmation.
  4. On "yes", broadcast the assembled poster card to every channel listed in
     ``POST_CHANNELS``.

Behaviour preserved from the original module, with the following fixes:

  * Callback data is parsed with ``rsplit('_', 1)`` so movie names that contain
    underscores no longer corrupt the decoded filename.
  * ``print()`` debugging replaced by the standard ``logging`` module.
  * Bare ``except:`` clauses replaced with specific exceptions + logging.
"""

import logging

from googletrans import Translator
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ── Trinity import contract ──────────────────────────────────────────────────
from config import *                       # POST_CHANNELS (and friends)
from phrases import phrases                 # branded string bank (kept for parity)
from toolbox import temp, get_poster       # runtime cache + IMDb poster helper
from brand import inject_repo_button        # license-locked repo button

# Module-scoped logger — no more stray print() calls.
logger = logging.getLogger(__name__)

# A single Translator instance is reused across requests (it is cheap to keep).
_translator = Translator()


# ─────────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────────
async def translate_to_hindi(plot_text: str) -> str:
    """Return the Hindi translation of ``plot_text``.

    googletrans occasionally raises on rate-limits / network hiccups; in that
    case we log the failure and gracefully fall back to the original text so the
    post is never blocked by a translation error.
    """
    try:
        rendered = _translator.translate(plot_text, dest="hi")
        return rendered.text
    except Exception as exc:  # googletrans raises a grab-bag of exception types
        logger.warning("Hindi translation failed: %s", exc)
        return plot_text


def _build_caption(meta: dict, hindi_plot: str) -> str:
    """Assemble the HTML poster caption shared by the preview and the channel post.

    Centralising this keeps the preview and the broadcast perfectly in sync.
    """
    return (
        f"<b>🔖Title: {meta.get('title', 'N/A')}</b>\n"
        f"<b>🎬 Genres: {meta.get('genres', 'N/A')}</b>\n"
        f"<b>⭐️ Rating: {meta.get('rating', 'N/A')}/10</b>\n"
        f"<b>📆 Year: {meta.get('year', 'N/A')}</b>\n\n"
        f"📕 Story: {meta.get('plot', 'N/A')}\n\n"
        f"📕 Story: {hindi_plot}"
    )


def _get_file_button(file_name: str) -> InlineKeyboardMarkup:
    """Build the public "Get File" deep-link button for a given movie name.

    The deep link mirrors the original ``?start=getfile-<slug>`` contract so the
    start handler keeps recognising these links.
    """
    slug = file_name.replace(" ", "-").lower()
    deep_link = f"https://t.me/{temp.U_NAME}?start=getfile-{slug}"
    rows = [[InlineKeyboardButton("Get File 📁", url=deep_link)]]
    # Keep the Trinity repo button attached per the brand lock.
    return InlineKeyboardMarkup(inject_repo_button(rows))


# ─────────────────────────────────────────────────────────────────────────────
#  /getfile — fetch IMDb metadata and offer to publish it
# ─────────────────────────────────────────────────────────────────────────────
@Client.on_message(filters.command("getfile"))
async def getfile(client, message):
    """Handle ``/getfile <movie name>``: preview an IMDb card + ask to publish."""
    try:
        # Split off the query argument; require at least one word after the cmd.
        parts = message.text.split(" ", 1)
        if len(parts) < 2 or not parts[1].strip():
            return await message.reply_text(
                "<b>Usage:</b> /getfile <movie_name>\n\n"
                "Example: /getfile Money Heist"
            )

        file_name = parts[1].strip()

        # Blocking IMDb lookup wrapped by get_poster (already async in toolbox).
        meta = await get_poster(file_name)
        if not meta:
            return await message.reply_text(
                f"No results found for {file_name} on IMDB."
            )

        poster = meta.get("poster", None)
        hindi_plot = await translate_to_hindi(meta.get("plot", "N/A"))
        caption = _build_caption(meta, hindi_plot)

        # Public deep-link card (shown to the requester as a preview).
        file_markup = _get_file_button(file_name)

        # Yes/No confirmation. The callback_data prefix `post_<yes|no>_` is kept
        # IDENTICAL so the regex below and any external refs still match.
        confirm_markup = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("Yes", callback_data=f"post_yes_{file_name}"),
                InlineKeyboardButton("No", callback_data=f"post_no_{file_name}"),
            ]
        ])

        # Render the preview — with a photo when a poster is available, else text.
        if poster:
            await message.reply_photo(
                poster,
                caption=caption,
                reply_markup=file_markup,
                parse_mode=enums.ParseMode.HTML,
            )
        else:
            await message.reply_text(
                caption,
                reply_markup=file_markup,
                parse_mode=enums.ParseMode.HTML,
            )

        # Ask the requester whether to push the card to the post channels.
        await message.reply_text(
            "Do you want to post this content on @movieplexus ?",
            reply_markup=confirm_markup,
        )

    except Exception as exc:
        logger.exception("getfile failed: %s", exc)
        await message.reply_text(f"Error: {exc}")


# ───────────────────────────  ⚡ Trinity Mods · @trinityXmods  ───────────────────────────


# ─────────────────────────────────────────────────────────────────────────────
#  Confirmation callback — publish (or cancel) the IMDb card
# ─────────────────────────────────────────────────────────────────────────────
@Client.on_callback_query(filters.regex(r"^post_(yes|no)_"))
async def post_to_channels(client, callback_query):
    """Act on the yes/no confirmation produced by :func:`getfile`.

    FIX: the original split on every ``_`` which mangled movie names that
    contain underscores. We strip the fixed ``post_`` prefix, then ``rsplit``
    once on ``_`` to cleanly separate the action from the (possibly
    underscore-laden) movie name.
    """
    data = callback_query.data

    # Remove the constant "post_" prefix → "<action>_<file_name>".
    remainder = data[len("post_"):]
    # Split ONLY on the first separator: action is yes/no (never contains "_"),
    # everything after it is the movie name verbatim.
    action, file_name = remainder.split("_", 1)

    if action == "no":
        return await callback_query.message.edit_text(
            "Movie details will not be posted to dedicated channel."
        )

    # action == "yes" → re-fetch metadata and broadcast to POST_CHANNELS.
    meta = await get_poster(file_name)
    if not meta:
        return await callback_query.message.reply_text(
            f"No results found for {file_name} on IMDB."
        )

    poster = meta.get("poster", None)
    hindi_plot = await translate_to_hindi(meta.get("plot", "N/A"))
    caption = _build_caption(meta, hindi_plot)
    file_markup = _get_file_button(file_name)

    # Fan the card out to every configured post channel; isolate per-channel
    # failures so one bad channel does not abort the rest.
    for channel_id in POST_CHANNELS:
        try:
            if poster:
                await client.send_photo(
                    chat_id=channel_id,
                    photo=poster,
                    caption=caption,
                    reply_markup=file_markup,
                    parse_mode=enums.ParseMode.HTML,
                )
            else:
                await client.send_message(
                    chat_id=channel_id,
                    text=caption,
                    reply_markup=file_markup,
                    parse_mode=enums.ParseMode.HTML,
                )
        except Exception as exc:
            logger.error("Failed posting to channel %s: %s", channel_id, exc)
            await callback_query.message.reply_text(
                f"Error posting to channel {channel_id}: {exc}"
            )

    await callback_query.message.edit_text(
        "Movie details successfully posted to dedicated channel"
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  ⚡ Crafted by Trinity Mods (@trinityXmods) · Trinity AutoFilter
#  If this code helped you, keep the credit alive → github.com/Trinity-Mods
#  🚫 This credit is license-locked. See brand.py.
# ═══════════════════════════════════════════════════════════════════════════════
