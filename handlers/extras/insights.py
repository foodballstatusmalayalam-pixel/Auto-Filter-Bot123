# ═══════════════════════════════════════════════════════════════════════════════
#  ⚡ TRINITY MODS · TRINITY AUTOFILTER
#  Search analytics — /trending leaderboard + /searchstats admin snapshot
#  ─────────────────────────────────────────────────────────────────────────────
#  Developed & maintained by Trinity Mods (@trinityXmods)
#  GitHub   : github.com/Trinity-Mods
#  Source   : github.com/Trinity-Mods/Auto-Filter-Bot
#  Telegram : t.me/trinityXmods
#  🚫 Credit is license-locked — see brand.py. Please keep this header intact.
# ═══════════════════════════════════════════════════════════════════════════════
"""
insights.py
───────────
A brand-new, read-only analytics surface for the bot's search log.

Every time a user searches, the core auto-filter pipeline calls
``db.log_query(term)`` which keeps a running ``hits`` counter per term inside the
``searches`` collection (see :mod:`vault.registry`). This module simply *reads*
that data back out for humans:

  * ``/trending``    — public; the ten most-searched terms, ranked by hits.
  * ``/searchstats`` — admins only; how many distinct terms we've ever tracked.

Nothing here mutates state, so no force-sub / verify / premium gating is applied
to ``/trending``. ``/searchstats`` is the only gated command (admin check) and it
performs a single lightweight ``count_documents`` call.
"""

import logging

from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup

# ── Trinity import contract ──────────────────────────────────────────────────
from config import *                       # ADMINS (and friends)
from phrases import phrases                 # branded string bank (kept for parity)
from vault.registry import db               # CoreDB instance — search analytics live here
from brand import inject_repo_button        # license-locked repo button

# Module-scoped logger — replaces every bare ``except:`` / ``print`` in this file.
logger = logging.getLogger(__name__)

# Medal glyphs for the top three slots; everything past third gets a plain dot.
_RANK_BADGES = ["🥇", "🥈", "🥉"]


def _rank_glyph(position: int) -> str:
    """Return a podium badge for the top three, otherwise a numbered marker.

    ``position`` is 1-based (1 == most-searched term).
    """
    if 1 <= position <= len(_RANK_BADGES):
        return _RANK_BADGES[position - 1]
    return f"{position}."


# ═══════════════════════════════════════════════════════════════════════════════
#  /trending — public, read-only leaderboard
# ═══════════════════════════════════════════════════════════════════════════════
@Client.on_message(filters.command("trending"))
async def trending_searches(client: Client, message: Message):
    """Render the ten most-searched terms as a tidy ranked list.

    Read-only and ungated by design — anyone may peek at what the crowd is
    hunting for. If the log is still empty we say so gracefully instead of
    sending a blank card.
    """
    try:
        # ``get_trending`` returns a list of (term, hits) tuples, already sorted
        # descending by hit-count and capped to the requested limit.
        rows = await db.get_trending(10)
    except Exception as err:  # noqa: BLE001 — surface DB hiccups, never a bare except
        logger.exception("Failed to fetch trending searches: %s", err)
        await message.reply_text(
            "⚠️ Couldn't pull the trending searches right now — please try again later."
        )
        return

    # No searches logged yet → friendly empty-state, no crash on an empty list.
    if not rows:
        await message.reply_text(
            "🔥 <b>Trending searches</b>\n\n"
            "No searches have been logged yet. Be the first — search for something! 🍿"
        )
        return

    # Assemble the leaderboard line by line. We pad the badge column so the term
    # names line up neatly regardless of single- vs. double-digit ranks.
    lines = ["🔥 <b>Trending searches</b>\n"]
    for position, (term, hits) in enumerate(rows, start=1):
        badge = _rank_glyph(position)
        # ``hits`` may technically be missing on legacy docs; default to 0.
        count = hits or 0
        # Pluralise "hit" for grammar polish.
        unit = "hit" if count == 1 else "hits"
        lines.append(f"{badge} <b>{term}</b> — <code>{count}</code> {unit}")

    text = "\n".join(lines)

    # Append the license-locked repo button (kept consistent across handlers).
    await message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(inject_repo_button([])),
        disable_web_page_preview=True,
    )


# ───────────────────────────  ⚡ Trinity Mods · @trinityXmods  ───────────────────────────


# ═══════════════════════════════════════════════════════════════════════════════
#  /searchstats — admin-only counters
# ═══════════════════════════════════════════════════════════════════════════════
@Client.on_message(filters.command("searchstats"))
async def search_stats(client: Client, message: Message):
    """Admin-only snapshot of how many *distinct* terms we've ever tracked.

    Gated on the ``ADMINS`` list — ordinary users get a polite refusal so the
    command stays invisible to the crowd. One cheap ``count_documents`` call.
    """
    # Manual admin gate (this is the only gated command in the module).
    if message.from_user is None or message.from_user.id not in ADMINS:
        await message.reply_text("🚫 This command is for admins only.")
        return

    try:
        # Total number of distinct search terms stored in the analytics collection.
        total_terms = await db.searches.count_documents({})
    except Exception as err:  # noqa: BLE001 — log, don't swallow silently
        logger.exception("Failed to count tracked search terms: %s", err)
        await message.reply_text(
            "⚠️ Couldn't read the search analytics right now — please try again later."
        )
        return

    await message.reply_text(
        "📊 <b>Search analytics</b>\n\n"
        f"Distinct terms tracked: <code>{total_terms}</code>",
        reply_markup=InlineKeyboardMarkup(inject_repo_button([])),
        disable_web_page_preview=True,
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  ⚡ Crafted by Trinity Mods (@trinityXmods) · Trinity AutoFilter
#  If this code helped you, keep the credit alive → github.com/Trinity-Mods
#  🚫 This credit is license-locked. See brand.py.
# ═══════════════════════════════════════════════════════════════════════════════
