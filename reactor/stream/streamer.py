# ═══════════════════════════════════════════════════════════════════════════════
#  ⚡ TRINITY MODS · TRINITY AUTOFILTER
#  reactor/stream/streamer.py — stream raw bytes from Telegram DCs on demand.
#  ─────────────────────────────────────────────────────────────────────────────
#  Developed & maintained by Trinity Mods (@trinityXmods)
#  GitHub   : github.com/Trinity-Mods
#  Source   : github.com/Trinity-Mods/Auto-Filter-Bot
#  Telegram : t.me/trinityXmods
#  🚫 Credit is license-locked — see brand.py. Please keep this header intact.
# ═══════════════════════════════════════════════════════════════════════════════
"""
``ByteCaster`` turns a Telegram file into an HTTP-streamable byte source. It talks
the raw MTProto ``upload.GetFile`` API directly (in 1 MiB chunks) so nothing is
ever buffered to disk — Telegram effectively becomes a free CDN.

Lineage / credit: the MTProto chunking technique originates from Eyaadh's
megadlbot (github.com/eyaadh/megadlbot_oss). This is an independent, re-commented
Trinity Mods implementation of the same idea — not a copy.
"""

import asyncio
import logging
from typing import Dict, Union

from pyrogram import Client, utils, raw
from pyrogram.session import Session, Auth
from pyrogram.errors import AuthBytesInvalid, FloodWait
from pyrogram.file_id import FileId, FileType, ThumbnailSource

from config import BIN_CHANNEL
from reactor.client import loads
from reactor.stream.media import get_file_ids
from reactor.web.faults import FileMissing

logger = logging.getLogger("trinity.streamer")


class ByteCaster:
    """
    Holds per-client caches (file properties + media sessions) and yields file
    bytes for the HTTP layer.

    One instance is created per worker client and reused (see endpoints.py).
    """

    def __init__(self, client: Client):
        self.client: Client = client
        self.cached_file_ids: Dict[int, FileId] = {}
        self.clean_timer = 30 * 60  # purge the property cache every 30 minutes
        asyncio.create_task(self._cache_janitor())

    # ── file properties ──────────────────────────────────────────────────────
    async def get_file_properties(self, message_id: int) -> FileId:
        """Return the (cached) FileId for a BIN_CHANNEL message."""
        if message_id not in self.cached_file_ids:
            await self._generate_file_properties(message_id)
            logger.debug("Cached file properties for message %s", message_id)
        return self.cached_file_ids[message_id]

    async def _generate_file_properties(self, message_id: int) -> FileId:
        """Resolve and cache the FileId for a message; raise FileMissing if gone."""
        file_id = await get_file_ids(self.client, BIN_CHANNEL, message_id)
        if not file_id:
            logger.debug("Message %s not found in bin channel", message_id)
            raise FileMissing
        self.cached_file_ids[message_id] = file_id
        return file_id

    # ── media sessions (cross-DC auth) ───────────────────────────────────────
    async def generate_media_session(self, client: Client, file_id: FileId) -> Session:
        """Create (or reuse) an authorized media session for the file's DC."""
        media_session = client.media_sessions.get(file_id.dc_id, None)
        if media_session is not None:
            return media_session

        if file_id.dc_id != await client.storage.dc_id():
            media_session = Session(
                client, file_id.dc_id,
                await Auth(client, file_id.dc_id, await client.storage.test_mode()).create(),
                await client.storage.test_mode(), is_media=True,
            )
            await media_session.start()
            # Export/import auth so this client can read from a foreign DC.
            for _ in range(6):
                exported = await client.invoke(
                    raw.functions.auth.ExportAuthorization(dc_id=file_id.dc_id)
                )
                try:
                    await media_session.send(
                        raw.functions.auth.ImportAuthorization(
                            id=exported.id, bytes=exported.bytes
                        )
                    )
                    break
                except AuthBytesInvalid:
                    logger.debug("Invalid auth bytes for DC %s; retrying", file_id.dc_id)
                    continue
            else:
                await media_session.stop()
                raise AuthBytesInvalid
        else:
            media_session = Session(
                client, file_id.dc_id,
                await client.storage.auth_key(),
                await client.storage.test_mode(), is_media=True,
            )
            await media_session.start()

        client.media_sessions[file_id.dc_id] = media_session
        logger.debug("Created media session for DC %s", file_id.dc_id)
        return media_session

    # ───────────────────────  ⚡ Trinity Mods · @trinityXmods  ───────────────────────
    @staticmethod
    async def get_location(file_id: FileId) -> Union[
        raw.types.InputPhotoFileLocation,
        raw.types.InputDocumentFileLocation,
        raw.types.InputPeerPhotoFileLocation,
    ]:
        """Build the InputFileLocation needed by ``upload.GetFile``."""
        file_type = file_id.file_type
        if file_type == FileType.CHAT_PHOTO:
            if file_id.chat_id > 0:
                peer = raw.types.InputPeerUser(
                    user_id=file_id.chat_id, access_hash=file_id.chat_access_hash
                )
            elif file_id.chat_access_hash == 0:
                peer = raw.types.InputPeerChat(chat_id=-file_id.chat_id)
            else:
                peer = raw.types.InputPeerChannel(
                    channel_id=utils.get_channel_id(file_id.chat_id),
                    access_hash=file_id.chat_access_hash,
                )
            return raw.types.InputPeerPhotoFileLocation(
                peer=peer, volume_id=file_id.volume_id, local_id=file_id.local_id,
                big=file_id.thumbnail_source == ThumbnailSource.CHAT_PHOTO_BIG,
            )
        if file_type == FileType.PHOTO:
            return raw.types.InputPhotoFileLocation(
                id=file_id.media_id, access_hash=file_id.access_hash,
                file_reference=file_id.file_reference, thumb_size=file_id.thumbnail_size,
            )
        return raw.types.InputDocumentFileLocation(
            id=file_id.media_id, access_hash=file_id.access_hash,
            file_reference=file_id.file_reference, thumb_size=file_id.thumbnail_size,
        )

    # ── the byte generator ───────────────────────────────────────────────────
    async def yield_file(
        self, file_id: FileId, index: int, offset: int,
        first_part_cut: int, last_part_cut: int, part_count: int, chunk_size: int,
    ):
        """
        Yield the requested byte-range of the file, one (trimmed) chunk at a time.
        ``index`` identifies the worker so we can track its load.
        """
        client = self.client
        loads[index] += 1  # mark this worker busy
        try:
            media_session = await self.generate_media_session(client, file_id)
            location = await self.get_location(file_id)
            current_part = 1

            response = await media_session.send(
                raw.functions.upload.GetFile(location=location, offset=offset, limit=chunk_size)
            )
            if isinstance(response, raw.types.upload.File):
                while True:
                    chunk = response.bytes
                    if not chunk:
                        break
                    if part_count == 1:
                        yield chunk[first_part_cut:last_part_cut]
                    elif current_part == 1:
                        yield chunk[first_part_cut:]
                    elif current_part == part_count:
                        yield chunk[:last_part_cut]
                    else:
                        yield chunk

                    current_part += 1
                    offset += chunk_size
                    if current_part > part_count:
                        break
                    response = await media_session.send(
                        raw.functions.upload.GetFile(location=location, offset=offset, limit=chunk_size)
                    )
        except FloodWait as exc:
            wait = getattr(exc, "value", getattr(exc, "x", 0))
            logger.warning("FloodWait(%ss) while streaming on client %s", wait, index)
            await asyncio.sleep(wait)
        except (TimeoutError, asyncio.TimeoutError):
            # Don't silently swallow — a logged warning makes stalled streams visible.
            logger.warning("Timed out while streaming file on client %s", index)
        except AttributeError:
            logger.warning("Client disconnected mid-stream on client %s", index)
        finally:
            loads[index] -= 1  # always free the worker, even on error

    # ── housekeeping ─────────────────────────────────────────────────────────
    async def _cache_janitor(self) -> None:
        """Periodically clear the file-property cache to keep memory flat."""
        while True:
            await asyncio.sleep(self.clean_timer)
            self.cached_file_ids.clear()
            logger.debug("Cleared streamer property cache")


# Backwards-compatible alias for the old class name.
ByteStreamer = ByteCaster

# ═══════════════════════════════════════════════════════════════════════════════
#  ⚡ Crafted by Trinity Mods (@trinityXmods) · Trinity AutoFilter
#  If this code helped you, keep the credit alive → github.com/Trinity-Mods
#  🚫 This credit is license-locked. See brand.py.
# ═══════════════════════════════════════════════════════════════════════════════
