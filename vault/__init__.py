# ═══════════════════════════════════════════════════════════════════════════════
#  ⚡ TRINITY MODS · TRINITY AUTOFILTER
#  vault/__init__.py — the data layer; owns ONE shared async MongoDB client.
#  ─────────────────────────────────────────────────────────────────────────────
#  Developed & maintained by Trinity Mods (@trinityXmods)
#  GitHub   : github.com/Trinity-Mods
#  Source   : github.com/Trinity-Mods/Auto-Filter-Bot
#  Telegram : t.me/trinityXmods
#  🚫 Credit is license-locked — see brand.py. Please keep this header intact.
# ═══════════════════════════════════════════════════════════════════════════════
"""
The legacy project opened FOUR separate MongoDB connections (two async motor
clients + two synchronous pymongo clients used inside async handlers — which
blocked the event loop). Trinity AutoFilter opens ONE shared async ``motor``
client here and every sub-module reuses it:

  • vault.media_index — the searchable file index (umongo Document `Media`)
  • vault.registry    — users, groups, premium, verification, settings (`db`)
  • vault.links       — user↔group connection mappings
  • vault.referrals   — referral points ledger (`referrals` / `sdb`)
"""

from motor.motor_asyncio import AsyncIOMotorClient

from config import DATABASE_URI, DATABASE_NAME

# One client, sane pool settings, reused everywhere.
mongo_client = AsyncIOMotorClient(
    DATABASE_URI,
    serverSelectionTimeoutMS=10000,
    maxPoolSize=50,
)
database = mongo_client[DATABASE_NAME]

# ───────────────────────────  ⚡ Trinity Mods · @trinityXmods  ───────────────────────────

__all__ = ["mongo_client", "database"]

# ═══════════════════════════════════════════════════════════════════════════════
#  ⚡ Crafted by Trinity Mods (@trinityXmods) · Trinity AutoFilter
#  If this code helped you, keep the credit alive → github.com/Trinity-Mods
#  🚫 This credit is license-locked. See brand.py.
# ═══════════════════════════════════════════════════════════════════════════════
