# ═══════════════════════════════════════════════════════════════════════════════
#  ⚡ TRINITY MODS · TRINITY AUTOFILTER
#  reactor/web/__init__.py — embedded aiohttp web server factory.
#  ─────────────────────────────────────────────────────────────────────────────
#  Developed & maintained by Trinity Mods (@trinityXmods)
#  GitHub   : github.com/Trinity-Mods
#  Source   : github.com/Trinity-Mods/Auto-Filter-Bot
#  Telegram : t.me/trinityXmods
#  🚫 Credit is license-locked — see brand.py. Please keep this header intact.
# ═══════════════════════════════════════════════════════════════════════════════
"""
Builds the tiny aiohttp application that runs alongside the bot inside the same
event loop. It serves the landing page, a /health + /status endpoint (so free
hosting keeps the process alive), the on-the-fly file stream, and the watch page.
"""

from aiohttp import web

from reactor.web.endpoints import routes


async def build_app() -> web.Application:
    """Create and configure the aiohttp Application."""
    web_app = web.Application(client_max_size=30_000_000)  # 30 MB request cap
    web_app.add_routes(routes)
    return web_app


# ───────────────────────────  ⚡ Trinity Mods · @trinityXmods  ───────────────────────────

# Backwards-compatible alias for the old public name.
async def web_server() -> web.Application:
    """Alias of :func:`build_app` (kept for import compatibility)."""
    return await build_app()


# ═══════════════════════════════════════════════════════════════════════════════
#  ⚡ Crafted by Trinity Mods (@trinityXmods) · Trinity AutoFilter
#  If this code helped you, keep the credit alive → github.com/Trinity-Mods
#  🚫 This credit is license-locked. See brand.py.
# ═══════════════════════════════════════════════════════════════════════════════
