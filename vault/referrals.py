# ═══════════════════════════════════════════════════════════════════════════════
#  ⚡ TRINITY MODS · TRINITY AUTOFILTER
#  vault/referrals.py — the "refer & earn" points ledger.
#  ─────────────────────────────────────────────────────────────────────────────
#  Developed & maintained by Trinity Mods (@trinityXmods)
#  GitHub   : github.com/Trinity-Mods
#  Source   : github.com/Trinity-Mods/Auto-Filter-Bot
#  Telegram : t.me/trinityXmods
#  🚫 Credit is license-locked — see brand.py. Please keep this header intact.
# ═══════════════════════════════════════════════════════════════════════════════
"""
Tracks who has been referred and how many referral points each user has earned.
Reaching ``REFFER_POINT`` points unlocks premium (see handlers/extras/premium).

Fixes vs legacy ``UserPoint``:
  • Was synchronous pymongo inside async handlers → now async (motor, shared client).
  • ``add_refer_points`` used ``$set`` which OVERWROTE the total — now ``$inc`` so
    points actually accumulate.

NOTE: every method here is ASYNC — callers must ``await`` them.
"""

import logging

from vault import database

logger = logging.getLogger("trinity.referrals")


class ReferLedger:
    """Async ledger of referred users and their accumulated points."""

    def __init__(self):
        self.users = database["refer_users"]    # who has already been referred
        self.points = database["refer_points"]  # per-user point totals

    async def add_user(self, user_id):
        """Mark a user as referred (idempotent)."""
        try:
            await self.users.update_one({"user_id": user_id}, {"$set": {"user_id": user_id}}, upsert=True)
        except Exception:
            logger.exception("referrals.add_user failed for %s", user_id)

    async def remove_user(self, user_id):
        try:
            await self.users.delete_one({"user_id": user_id})
        except Exception:
            logger.exception("referrals.remove_user failed for %s", user_id)

    async def is_user_in_list(self, user_id):
        return bool(await self.users.find_one({"user_id": user_id}))

    async def add_refer_points(self, user_id: int, points: int = 1):
        """Add ``points`` to a user's total (accumulates via $inc)."""
        try:
            await self.points.update_one({"user_id": user_id}, {"$inc": {"points": points}}, upsert=True)
        except Exception:
            logger.exception("referrals.add_refer_points failed for %s", user_id)

    async def get_refer_points(self, user_id: int):
        doc = await self.points.find_one({"user_id": user_id})
        return doc.get("points", 0) if doc else 0


# ───────────────────────────  ⚡ Trinity Mods · @trinityXmods  ───────────────────────────

# The singleton + a legacy alias (the old code imported it as ``sdb``).
referrals = ReferLedger()
sdb = referrals

# ═══════════════════════════════════════════════════════════════════════════════
#  ⚡ Crafted by Trinity Mods (@trinityXmods) · Trinity AutoFilter
#  If this code helped you, keep the credit alive → github.com/Trinity-Mods
#  🚫 This credit is license-locked. See brand.py.
# ═══════════════════════════════════════════════════════════════════════════════
