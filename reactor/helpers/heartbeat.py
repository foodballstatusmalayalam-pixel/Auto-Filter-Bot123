# ═══════════════════════════════════════════════════════════════════════════════
#  ⚡ TRINITY MODS · TRINITY AUTOFILTER
#  reactor/helpers/heartbeat.py — keep-alive self-ping for free hosting tiers.
#  ─────────────────────────────────────────────────────────────────────────────
#  Developed & maintained by Trinity Mods (@trinityXmods)
#  GitHub   : github.com/Trinity-Mods
#  Source   : github.com/Trinity-Mods/Auto-Filter-Bot
#  Telegram : t.me/trinityXmods
#  🚫 Credit is license-locked — see brand.py. Please keep this header intact.
# ═══════════════════════════════════════════════════════════════════════════════
"""
Some free platforms (and the old Heroku dynos) idle a web process that receives
no traffic. ``ping_loop`` simply GETs the bot's own public URL every
``PING_INTERVAL`` seconds so the platform considers it "awake".

This is opt-in: the launcher only starts it when running on a platform that needs
it (``ON_HEROKU``), but it is safe to run anywhere.
"""

import asyncio
import logging

import aiohttp

# PING_INTERVAL has a sane default inside config.py so this import never explodes.
from config import PING_INTERVAL, URL

logger = logging.getLogger("trinity.heartbeat")


async def ping_loop():
    """Forever: ping our own URL on an interval, swallowing transient errors."""
    timeout = aiohttp.ClientTimeout(total=10)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        while True:
            await asyncio.sleep(PING_INTERVAL)
            try:
                async with session.get(URL) as resp:
                    logger.info("Heartbeat ping → %s (%s)", URL, resp.status)
            except asyncio.TimeoutError:
                logger.warning("Heartbeat ping timed out.")
            except Exception as exc:  # network blips shouldn't kill the loop
                logger.warning("Heartbeat ping failed: %s", exc)


# ───────────────────────────  ⚡ Trinity Mods · @trinityXmods  ───────────────────────────

# Backwards-compatible alias for the old public name (``ping_server``).
async def ping_server():
    """Alias of :func:`ping_loop` (kept for import compatibility)."""
    await ping_loop()


# ═══════════════════════════════════════════════════════════════════════════════
#  ⚡ Crafted by Trinity Mods (@trinityXmods) · Trinity AutoFilter
#  If this code helped you, keep the credit alive → github.com/Trinity-Mods
#  🚫 This credit is license-locked. See brand.py.
# ═══════════════════════════════════════════════════════════════════════════════
