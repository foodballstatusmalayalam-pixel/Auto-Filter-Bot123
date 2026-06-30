# ═══════════════════════════════════════════════════════════════════════════════
#  ⚡ TRINITY MODS · TRINITY AUTOFILTER
#  reactor/client.py — the primary Pyrogram client and multi-client registries.
#  ─────────────────────────────────────────────────────────────────────────────
#  Developed & maintained by Trinity Mods (@trinityXmods)
#  GitHub   : github.com/Trinity-Mods
#  Source   : github.com/Trinity-Mods/Auto-Filter-Bot
#  Telegram : t.me/trinityXmods
#  🚫 Credit is license-locked — see brand.py. Please keep this header intact.
# ═══════════════════════════════════════════════════════════════════════════════
"""
``app`` is the one bot client every handler binds to. Telegram handlers live in
the ``handlers`` package and are auto-loaded via Pyrogram "smart plugins"
(``plugins={"root": "handlers"}``) — so we load them ONCE here, never manually
(the legacy bot loaded them twice, which double-registered every handler).

``clients`` / ``loads`` are the registries the streaming engine uses to spread
load across the optional worker fleet (see reactor.fleet).
"""

import logging
from typing import Union, Optional, AsyncGenerator

from pyrogram import Client, types

from config import API_ID, API_HASH, BOT_TOKEN, SESSION, WORKERS, SLEEP_THRESHOLD

logger = logging.getLogger("trinity.client")


class FilterClient(Client):
    """The main Trinity AutoFilter bot client (also acts as streaming client #0)."""

    def __init__(self):
        super().__init__(
            name=SESSION,
            api_id=API_ID,
            api_hash=API_HASH,
            bot_token=BOT_TOKEN,
            workers=WORKERS,
            # Auto-discover and load every handler module under handlers/.
            plugins={"root": "handlers"},
            # A generous sleep threshold lets Pyrogram absorb short FloodWaits
            # itself instead of bubbling them up into our handlers.
            sleep_threshold=max(SLEEP_THRESHOLD, 180),
        )
        self.username = None  # filled in at startup once we know who we are

    async def iter_messages(
        self,
        chat_id: Union[int, str],
        limit: int,
        offset: int = 0,
    ) -> Optional[AsyncGenerator["types.Message", None]]:
        """
        Iterate messages in a chat from ``offset`` up to ``limit`` (used by the
        indexer). Pyrogram has no public bulk iterator for arbitrary id ranges,
        so we page through ``get_messages`` in chunks of 200 (its hard cap).
        """
        current = offset
        while True:
            new_diff = min(200, limit - current)
            if new_diff <= 0:
                return
            # Inclusive id range — message ids are sequential per chat.
            ids = list(range(current, current + new_diff + 1))
            messages = await self.get_messages(chat_id, ids)
            for message in messages:
                yield message
                current += 1


# ───────────────────────────  ⚡ Trinity Mods · @trinityXmods  ───────────────────────────

# The singleton client used everywhere.
app = FilterClient()

# Streaming worker registries.
#   clients : {client_id: Client}            (was `multi_clients`)
#   loads   : {client_id: active_request_n}  (was `work_loads`)
clients: dict = {}
loads: dict = {}

# Legacy aliases so any straggler import keeps working.
multi_clients = clients
work_loads = loads
TrinityBot = app

# ═══════════════════════════════════════════════════════════════════════════════
#  ⚡ Crafted by Trinity Mods (@trinityXmods) · Trinity AutoFilter
#  If this code helped you, keep the credit alive → github.com/Trinity-Mods
#  🚫 This credit is license-locked. See brand.py.
# ═══════════════════════════════════════════════════════════════════════════════
