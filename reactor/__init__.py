# ═══════════════════════════════════════════════════════════════════════════════
#  ⚡ TRINITY MODS · TRINITY AUTOFILTER
#  reactor/__init__.py — runtime + streaming engine package root.
#  ─────────────────────────────────────────────────────────────────────────────
#  Developed & maintained by Trinity Mods (@trinityXmods)
#  GitHub   : github.com/Trinity-Mods
#  Source   : github.com/Trinity-Mods/Auto-Filter-Bot
#  Telegram : t.me/trinityXmods
#  🚫 Credit is license-locked — see brand.py. Please keep this header intact.
# ═══════════════════════════════════════════════════════════════════════════════
"""
The ``reactor`` package is Trinity AutoFilter's engine room. It holds:

  • reactor.client    — the Pyrogram client (``app``) + the multi-client registries
  • reactor.fleet     — boots optional extra worker clients for load balancing
  • reactor.stream    — the on-the-fly Telegram→HTTP byte streamer + media probing
  • reactor.web       — the embedded aiohttp server (health, streaming, watch pages)
  • reactor.helpers   — small self-contained utilities (sizes, clock, tokens, ping)

It deliberately knows nothing about the Telegram *handlers* — those live in the
``handlers`` package and import from here, never the other way around.
"""

import time

from version import VERSION, PRETTY_VERSION, CODENAME, ENGINE  # single source of truth

# Process start time — used by the /status endpoint to report uptime.
StartTime = time.time()

# Re-export version info under the names the streaming layer historically used.
__version__ = VERSION
__author__ = "Trinity Mods (@trinityXmods)"
__repo__ = "https://github.com/Trinity-Mods/Auto-Filter-Bot"

# ───────────────────────────  ⚡ Trinity Mods · @trinityXmods  ───────────────────────────

__all__ = ["StartTime", "__version__", "__author__", "__repo__",
           "PRETTY_VERSION", "CODENAME", "ENGINE"]

# ═══════════════════════════════════════════════════════════════════════════════
#  ⚡ Crafted by Trinity Mods (@trinityXmods) · Trinity AutoFilter
#  If this code helped you, keep the credit alive → github.com/Trinity-Mods
#  🚫 This credit is license-locked. See brand.py.
# ═══════════════════════════════════════════════════════════════════════════════
