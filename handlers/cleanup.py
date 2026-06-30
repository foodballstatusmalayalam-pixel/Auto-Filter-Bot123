# ═══════════════════════════════════════════════════════════════════════════════
#  ⚡ TRINITY MODS · TRINITY AUTOFILTER
#  Auto-prune the media index when a matching file is posted in a delete channel.
#  ─────────────────────────────────────────────────────────────────────────────
#  Developed & maintained by Trinity Mods (@trinityXmods)
#  GitHub   : github.com/Trinity-Mods
#  Source   : github.com/Trinity-Mods/Auto-Filter-Bot
#  Telegram : t.me/trinityXmods
#  🚫 Credit is license-locked — see brand.py. Please keep this header intact.
# ═══════════════════════════════════════════════════════════════════════════════
"""
handlers/cleanup.py
===================
Listens to the channels named in ``DELETE_CHANNELS``.  Whenever a media message
(document / video / audio) lands there, we treat it as an instruction to *purge*
the corresponding entry from the indexed-file collection.

Matching is attempted in three escalating tiers so that we still catch records
that were indexed slightly differently from the incoming file:

    Tier 1 — exact primary-key match on the unpacked ``file_id`` (``_id``).
    Tier 2 — normalized filename + size + mime  (underscores/dashes/dots/plus
             collapsed to spaces, the way the indexer stores names).
    Tier 3 — literal (un-normalized) filename + size + mime, for older rows.

As soon as a tier deletes something we stop; if nothing ever matches we simply
log it and move on.
"""

import re
import logging

from pyrogram import Client, filters

# ── Trinity import contract ─────────────────────────────────────────────────
from config import *
from vault.media_index import Media, unpack_new_file_id

# Module-scoped logger (replaces the old bare ``except:`` / print style).
log = logging.getLogger(__name__)

# Any of these media kinds posted in a delete channel triggers a purge.
MEDIA_FILTER = filters.document | filters.video | filters.audio

# Order in which we probe a message for an attached media object.
_MEDIA_FIELDS = ("document", "video", "audio")

# Characters the indexer normalizes to a single space inside file names.
_NAME_SEPARATORS = re.compile(r"[_\-.+]")


# ───────────────────────────  ⚡ Trinity Mods · @trinityXmods  ───────────────────────────


def _extract_media(message):
    """Return the first media object found on ``message`` (or ``None``).

    Mirrors the original loop but as a small helper so the handler reads clean.
    """
    for field in _MEDIA_FIELDS:
        media = getattr(message, field, None)
        if media is not None:
            return media
    return None


def _normalize_name(raw_name):
    """Collapse ``_ - . +`` into spaces — the same shape the indexer persists."""
    return _NAME_SEPARATORS.sub(" ", str(raw_name))


async def _purge_by_filename(media, normalized):
    """Tier 2 / Tier 3 helper: delete rows by (name, size, mime).

    ``normalized`` toggles whether we match the cleaned-up name (Tier 2) or the
    literal name straight off the file (Tier 3).
    """
    file_name = _normalize_name(media.file_name) if normalized else media.file_name
    result = await Media.collection.delete_many(
        {
            "file_name": file_name,
            "file_size": media.file_size,
            "mime_type": media.mime_type,
        }
    )
    return result.deleted_count


@Client.on_message(filters.chat(DELETE_CHANNELS) & MEDIA_FILTER)
async def purge_indexed_media(bot, message):
    """Remove an indexed file from the database when it appears in a delete channel."""

    # 1) Locate the attached media; ignore anything without one.
    media = _extract_media(message)
    if media is None:
        return

    # FIX (bug checklist): older / odd messages can carry media with no
    # ``file_id``.  Calling ``unpack_new_file_id(None)`` would raise — so we
    # null-check first and fall back to the filename tiers instead of crashing.
    deleted = 0
    if getattr(media, "file_id", None):
        # ── Tier 1: exact primary-key (unpacked file_id) match. ──────────────
        try:
            file_id, _file_ref = unpack_new_file_id(media.file_id)
        except (ValueError, TypeError, AttributeError) as exc:
            # A malformed file_id should never take the whole handler down.
            log.warning("Could not unpack file_id for purge: %s", exc)
            file_id = None

        if file_id is not None:
            result = await Media.collection.delete_one({"_id": file_id})
            deleted = result.deleted_count

    if deleted:
        log.info("Purged indexed file by file_id from %s.", message.chat.id)
        return

    # ── Tier 2: normalized name + size + mime. ───────────────────────────────
    deleted = await _purge_by_filename(media, normalized=True)
    if deleted:
        log.info("Purged %d indexed file(s) by normalized name.", deleted)
        return

    # ── Tier 3: literal name + size + mime (legacy rows). ────────────────────
    deleted = await _purge_by_filename(media, normalized=False)
    if deleted:
        log.info("Purged %d indexed file(s) by literal name.", deleted)
        return

    # Nothing matched any tier — that's fine, just record it.
    log.info("No matching indexed file found to purge for incoming media.")


# ═══════════════════════════════════════════════════════════════════════════════
#  ⚡ Crafted by Trinity Mods (@trinityXmods) · Trinity AutoFilter
#  If this code helped you, keep the credit alive → github.com/Trinity-Mods
#  🚫 This credit is license-locked. See brand.py.
# ═══════════════════════════════════════════════════════════════════════════════
