# ═══════════════════════════════════════════════════════════════════════════════
#  ⚡ TRINITY MODS · TRINITY AUTOFILTER
#  reactor/fleet.py — boot optional extra worker clients for load balancing.
#  ─────────────────────────────────────────────────────────────────────────────
#  Developed & maintained by Trinity Mods (@trinityXmods)
#  GitHub   : github.com/Trinity-Mods
#  Source   : github.com/Trinity-Mods/Auto-Filter-Bot
#  Telegram : t.me/trinityXmods
#  🚫 Credit is license-locked — see brand.py. Please keep this header intact.
# ═══════════════════════════════════════════════════════════════════════════════
"""
If the deployer supplies extra bot tokens (MULTI_TOKEN1, MULTI_TOKEN2, …) we
start each as its own lightweight client. The streaming engine then routes every
download to the least-busy client (see reactor.web.endpoints), multiplying
throughput and spreading Telegram's rate limits.

This is entirely optional — with no extra tokens the bot runs perfectly on the
single primary client.
"""

import asyncio
import logging

import config
from pyrogram import Client
from pyrogram.errors import FloodWait

from config import API_ID, API_HASH, SLEEP_THRESHOLD
from reactor.client import clients, loads, app
from reactor.helpers.tokens import TokenParser

logger = logging.getLogger("trinity.fleet")


async def boot_clients():
    """Register the primary client and start any worker clients from env tokens."""
    clients[0] = app
    loads[0] = 0

    tokens = TokenParser().parse_from_env()
    if not tokens:
        logger.info("No worker tokens found — running on the single primary client.")
        return

    async def _start(client_id: int, token: str):
        try:
            worker = Client(
                name=str(client_id),
                api_id=API_ID,
                api_hash=API_HASH,
                bot_token=token,
                sleep_threshold=SLEEP_THRESHOLD,
                no_updates=True,   # workers only stream; they don't handle updates
                in_memory=True,    # unique in-memory session avoids SQLite lock clashes
            )
            await worker.start()
            loads[client_id] = 0
            logger.info("Worker client %s started.", client_id)
            return client_id, worker
        except FloodWait as exc:
            # Stagger-retry once after the flood window instead of dying.
            wait = getattr(exc, "value", getattr(exc, "x", 5))
            logger.warning("Worker %s hit FloodWait(%ss); retrying once.", client_id, wait)
            await asyncio.sleep(wait)
            try:
                worker = Client(
                    name=str(client_id), api_id=API_ID, api_hash=API_HASH,
                    bot_token=token, sleep_threshold=SLEEP_THRESHOLD,
                    no_updates=True, in_memory=True,
                )
                await worker.start()
                loads[client_id] = 0
                return client_id, worker
            except Exception:
                logger.exception("Worker %s failed after retry.", client_id)
                return None
        except Exception:
            logger.exception("Worker %s failed to start.", client_id)
            return None

    started = await asyncio.gather(*[_start(cid, tok) for cid, tok in tokens.items()])
    # FIX: drop any failed (None) clients before merging — the legacy code merged
    # None values into the dict and crashed the streamer later.
    started = [pair for pair in started if pair]
    clients.update(dict(started))

    # Publish a real, importable flag instead of a stray local variable.
    config.MULTI_CLIENT = len(clients) > 1
    logger.info(
        "Fleet ready: %s client(s)%s.",
        len(clients),
        " (multi-client mode)" if config.MULTI_CLIENT else "",
    )
    return config.MULTI_CLIENT


# ───────────────────────────  ⚡ Trinity Mods · @trinityXmods  ───────────────────────────

# Backwards-compatible alias for the old public name.
async def initialize_clients():
    """Alias of :func:`boot_clients` (kept for import compatibility)."""
    return await boot_clients()


# ═══════════════════════════════════════════════════════════════════════════════
#  ⚡ Crafted by Trinity Mods (@trinityXmods) · Trinity AutoFilter
#  If this code helped you, keep the credit alive → github.com/Trinity-Mods
#  🚫 This credit is license-locked. See brand.py.
# ═══════════════════════════════════════════════════════════════════════════════
