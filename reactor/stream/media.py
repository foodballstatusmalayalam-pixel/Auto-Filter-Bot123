# ═══════════════════════════════════════════════════════════════════════════════
#  ⚡ TRINITY MODS · TRINITY AUTOFILTER
#  reactor/stream/media.py — pull media metadata (FileId) out of a Telegram message.
#  ─────────────────────────────────────────────────────────────────────────────
#  Developed & maintained by Trinity Mods (@trinityXmods)
#  GitHub   : github.com/Trinity-Mods
#  Source   : github.com/Trinity-Mods/Auto-Filter-Bot
#  Telegram : t.me/trinityXmods
#  🚫 Credit is license-locked — see brand.py. Please keep this header intact.
# ═══════════════════════════════════════════════════════════════════════════════
"""
The streamer needs the raw Pyrogram ``FileId`` plus a few extra attributes
(size, mime type, filename, unique id). These helpers extract a media object
from any message type and decorate the decoded FileId with what we need.
"""

from typing import Any, Optional

from pyrogram import Client
from pyrogram.types import Message
from pyrogram.file_id import FileId

from reactor.web.faults import FileMissing

# Every media kind a Telegram message can carry, in priority order.
_MEDIA_TYPES = (
    "audio", "document", "photo", "sticker",
    "animation", "video", "voice", "video_note",
)


def get_media_from_message(message: "Message") -> Any:
    """Return the first media object present on a message, or None."""
    for attr in _MEDIA_TYPES:
        media = getattr(message, attr, None)
        if media:
            return media
    return None


async def parse_file_id(message: "Message") -> Optional[FileId]:
    """Decode the Pyrogram FileId from a message's media."""
    media = get_media_from_message(message)
    if media:
        return FileId.decode(media.file_id)
    return None


async def parse_file_unique_id(message: "Message") -> Optional[str]:
    """Return the media's file_unique_id (used to build the 6-char URL hash)."""
    media = get_media_from_message(message)
    if media:
        return media.file_unique_id
    return None


# ───────────────────────────  ⚡ Trinity Mods · @trinityXmods  ───────────────────────────


async def get_file_ids(client: Client, chat_id: int, message_id: int) -> Optional[FileId]:
    """
    Fetch a message from ``chat_id`` and return its decoded FileId, decorated
    with ``file_size`` / ``mime_type`` / ``file_name`` / ``unique_id``.

    Raises :class:`FileMissing` when the message (or its media) is gone.
    """
    message = await client.get_messages(chat_id, message_id)
    if not message or message.empty:
        raise FileMissing

    media = get_media_from_message(message)
    if not media:
        raise FileMissing

    file_unique_id = await parse_file_unique_id(message)
    file_id = await parse_file_id(message)
    # Pyrogram's FileId is a plain object — decorating it is the pragmatic choice
    # the whole streaming ecosystem uses.
    setattr(file_id, "file_size", getattr(media, "file_size", 0))
    setattr(file_id, "mime_type", getattr(media, "mime_type", ""))
    setattr(file_id, "file_name", getattr(media, "file_name", ""))
    setattr(file_id, "unique_id", file_unique_id)
    return file_id


def get_hash(media_msg: Message) -> str:
    """First 6 chars of the media's unique id — our lightweight URL access token."""
    media = get_media_from_message(media_msg)
    return getattr(media, "file_unique_id", "")[:6]


def get_name(media_msg: Message) -> str:
    """Return the media filename (empty string if none)."""
    media = get_media_from_message(media_msg)
    return getattr(media, "file_name", "") or ""


def get_media_file_size(media_msg: Message) -> int:
    """Return the media file size in bytes (0 if unknown)."""
    media = get_media_from_message(media_msg)
    return getattr(media, "file_size", 0) or 0


# ═══════════════════════════════════════════════════════════════════════════════
#  ⚡ Crafted by Trinity Mods (@trinityXmods) · Trinity AutoFilter
#  If this code helped you, keep the credit alive → github.com/Trinity-Mods
#  🚫 This credit is license-locked. See brand.py.
# ═══════════════════════════════════════════════════════════════════════════════
