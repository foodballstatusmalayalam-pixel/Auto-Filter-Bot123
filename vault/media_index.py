# ═══════════════════════════════════════════════════════════════════════════════
#  ⚡ TRINITY MODS · TRINITY AUTOFILTER
#  vault/media_index.py — the searchable file index (store + regex search).
#  ─────────────────────────────────────────────────────────────────────────────
#  Developed & maintained by Trinity Mods (@trinityXmods)
#  GitHub   : github.com/Trinity-Mods
#  Source   : github.com/Trinity-Mods/Auto-Filter-Bot
#  Telegram : t.me/trinityXmods
#  🚫 Credit is license-locked — see brand.py. Please keep this header intact.
# ═══════════════════════════════════════════════════════════════════════════════
"""
Every indexed document/video/audio is stored as a ``Media`` record keyed by its
decoded Telegram file_id. Searching is done with a separator-tolerant regex so
messy real-world filenames (``Movie.Name.2021.1080p.x264``) still match a plain
``movie name 2021`` query. Decoupling search from Telegram means files remain
findable even after they're deleted from the source channel, and survive restarts.
"""

import re
import base64
import logging
from struct import pack

from pyrogram.file_id import FileId
from pymongo.errors import DuplicateKeyError
from umongo import Instance, Document, fields
from marshmallow.exceptions import ValidationError

from config import USE_CAPTION_FILTER, MAX_B_TN, COLLECTION_NAME
from vault import database                     # the ONE shared motor database
from toolbox import get_settings, save_group_settings
from phrases import phrases

logger = logging.getLogger("trinity.media_index")

# Bind umongo to our shared motor database.
instance = Instance.from_db(database)


@instance.register
class Media(Document):
    """One indexed Telegram file."""
    file_id = fields.StrField(attribute="_id")
    file_ref = fields.StrField(allow_none=True)
    file_name = fields.StrField(required=True)
    file_size = fields.IntField(required=True)
    file_type = fields.StrField(allow_none=True)
    mime_type = fields.StrField(allow_none=True)
    caption = fields.StrField(allow_none=True)

    class Meta:
        indexes = ("$file_name",)
        collection_name = COLLECTION_NAME


async def save_file(media):
    """
    Persist a media object. Returns ``(saved: bool, file_id)``.

    A re-indexed file (same decoded id) raises DuplicateKeyError, which we treat
    as "already have it" rather than letting it crash the indexer.
    """
    file_id, file_ref = unpack_new_file_id(media.file_id)
    file_name = re.sub(r"[_\-.+]", " ", str(media.file_name))
    try:
        record = Media(
            file_id=file_id,
            file_ref=file_ref,
            file_name=file_name,
            file_size=media.file_size,
            file_type=media.file_type,
            mime_type=media.mime_type,
            caption=media.caption.html if media.caption else None,
        )
    except ValidationError:
        logger.exception("Validation error while saving %s", getattr(media, "file_name", "?"))
        return False, None

    try:
        await record.commit()
    except DuplicateKeyError:
        logger.info("Already indexed: %s", getattr(media, "file_name", "?"))
        return False, file_id
    logger.info("Indexed: %s", getattr(media, "file_name", "?"))
    return True, file_id


def _build_pattern(query: str):
    """Build a separator-tolerant, case-insensitive regex from a query string."""
    query = query.strip()
    if not query:
        raw = "."
    elif " " not in query:
        raw = r"(\b|[.+\-_])" + re.escape(query) + r"(\b|[.+\-_])"
    else:
        # Allow any separators between the words of a multi-word query.
        raw = re.escape(query).replace(r"\ ", r".*[\s.+\-_]")
    try:
        return re.compile(raw, flags=re.IGNORECASE)
    except re.error as exc:
        logger.warning("Bad search pattern for %r: %s", query, exc)
        return None


# ───────────────────────────  ⚡ Trinity Mods · @trinityXmods  ───────────────────────────


async def get_search_results(chat_id, query, file_type=None, max_results=10, offset=0, filter=False):
    """Return ``(files, next_offset, total_results)`` for a paginated search."""
    if chat_id is not None:
        settings = await get_settings(int(chat_id))
        try:
            max_results = 10 if settings["max_btn"] else int(MAX_B_TN)
        except KeyError:
            await save_group_settings(int(chat_id), "max_btn", False)
            max_results = int(MAX_B_TN)

    regex = _build_pattern(query)
    if regex is None:
        return [], "", 0

    if USE_CAPTION_FILTER:
        mongo_filter = {"$or": [{"file_name": regex}, {"caption": regex}]}
    else:
        mongo_filter = {"file_name": regex}
    if file_type:
        mongo_filter["file_type"] = file_type

    total_results = await Media.count_documents(mongo_filter)
    next_offset = offset + max_results
    if next_offset >= total_results:
        next_offset = ""

    cursor = Media.find(mongo_filter)
    cursor.sort("$natural", -1)                  # newest first
    cursor.skip(offset).limit(max_results)
    files = await cursor.to_list(length=max_results)
    _strip_blacklist(files)
    return files, next_offset, total_results


async def get_bad_files(query, file_type=None, filter=False):
    """Return ``(files, total_results)`` for ALL matches (used by /deletefiles)."""
    regex = _build_pattern(query)
    if regex is None:
        return [], 0

    if USE_CAPTION_FILTER:
        mongo_filter = {"$or": [{"file_name": regex}, {"caption": regex}]}
    else:
        mongo_filter = {"file_name": regex}
    if file_type:
        mongo_filter["file_type"] = file_type

    total_results = await Media.count_documents(mongo_filter)
    cursor = Media.find(mongo_filter)
    cursor.sort("$natural", -1)
    files = await cursor.to_list(length=total_results)
    return files, total_results


async def get_file_details(query):
    """Fetch a single file by id, with blacklist words stripped from the name."""
    try:
        cursor = Media.find({"file_id": query})
        details = await cursor.to_list(length=1)
        if details:
            file = details[0]
            name = getattr(file, "file_name", "") or ""
            for word in phrases.BLACKLIST:
                name = re.compile(re.escape(word), re.IGNORECASE).sub("", name).strip()
            setattr(file, "file_name", name or "File")
        return details
    except Exception:
        logger.exception("get_file_details failed")
        return None


async def get_all_files():
    """
    Return every indexed file name. NOTE: capped at 50,000 to avoid loading a huge
    library into memory — used only by the request spell-checker, which doesn't
    need the long tail.
    """
    cursor = Media.find()
    all_files = await cursor.to_list(length=50000)
    return [f["file_name"] for f in all_files]


def _strip_blacklist(files):
    """Remove blacklisted words (piracy tags, junk channels) from result names."""
    for file in files:
        for word in phrases.BLACKLIST:
            pattern = re.compile(re.escape(word), re.IGNORECASE)
            file["file_name"] = pattern.sub("", file["file_name"]).strip()


# ── Pyrogram file-id (un)packing — compact storage of Telegram references ──────
def encode_file_id(s: bytes) -> str:
    r, n = b"", 0
    for byte in s + bytes([22]) + bytes([4]):
        if byte == 0:
            n += 1
        else:
            if n:
                r += b"\x00" + bytes([n])
                n = 0
            r += bytes([byte])
    return base64.urlsafe_b64encode(r).decode().rstrip("=")


def encode_file_ref(file_ref: bytes) -> str:
    return base64.urlsafe_b64encode(file_ref).decode().rstrip("=")


def unpack_new_file_id(new_file_id):
    """Decode a Pyrogram file_id into the compact (file_id, file_ref) we store."""
    decoded = FileId.decode(new_file_id)
    file_id = encode_file_id(
        pack("<iiqq", int(decoded.file_type), decoded.dc_id, decoded.media_id, decoded.access_hash)
    )
    file_ref = encode_file_ref(decoded.file_reference)
    return file_id, file_ref


# ═══════════════════════════════════════════════════════════════════════════════
#  ⚡ Crafted by Trinity Mods (@trinityXmods) · Trinity AutoFilter
#  If this code helped you, keep the credit alive → github.com/Trinity-Mods
#  🚫 This credit is license-locked. See brand.py.
# ═══════════════════════════════════════════════════════════════════════════════
