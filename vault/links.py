# ═══════════════════════════════════════════════════════════════════════════════
#  ⚡ TRINITY MODS · TRINITY AUTOFILTER
#  vault/links.py — user ↔ group "connections" (manage a group from PM).
#  ─────────────────────────────────────────────────────────────────────────────
#  Developed & maintained by Trinity Mods (@trinityXmods)
#  GitHub   : github.com/Trinity-Mods
#  Source   : github.com/Trinity-Mods/Auto-Filter-Bot
#  Telegram : t.me/trinityXmods
#  🚫 Credit is license-locked — see brand.py. Please keep this header intact.
# ═══════════════════════════════════════════════════════════════════════════════
"""
A "connection" binds an admin's PM to a group so they can run /settings, /filter
etc. for that group from a private chat. One document per user holds the list of
connected groups plus the currently active one.

Fix vs legacy: the old module used the SYNCHRONOUS pymongo driver inside async
handlers, which blocked the whole event loop on every connection lookup. This is
now fully async (motor), sharing the single client from ``vault``.
"""

import logging

from vault import database

logger = logging.getLogger("trinity.links")

_col = database["connections"]


async def add_connection(group_id, user_id):
    """Connect ``user_id`` to ``group_id`` (and make it active). Returns bool."""
    existing = await _col.find_one({"_id": user_id}, {"_id": 0, "active_group": 0})
    if existing is not None:
        if group_id in [g["group_id"] for g in existing["group_details"]]:
            return False

    details = {"group_id": group_id}
    if await _col.count_documents({"_id": user_id}) == 0:
        try:
            await _col.insert_one({"_id": user_id, "group_details": [details], "active_group": group_id})
            return True
        except Exception:
            logger.exception("add_connection insert failed for user %s", user_id)
            return False
    try:
        await _col.update_one(
            {"_id": user_id},
            {"$push": {"group_details": details}, "$set": {"active_group": group_id}},
        )
        return True
    except Exception:
        logger.exception("add_connection update failed for user %s", user_id)
        return False


async def active_connection(user_id):
    """Return the active group id for ``user_id`` (int), or None."""
    query = await _col.find_one({"_id": user_id}, {"_id": 0, "group_details": 0})
    if not query:
        return None
    group_id = query["active_group"]
    return int(group_id) if group_id is not None else None


# ───────────────────────────  ⚡ Trinity Mods · @trinityXmods  ───────────────────────────


async def all_connections(user_id):
    """Return the list of group ids connected to ``user_id``, or None."""
    query = await _col.find_one({"_id": user_id}, {"_id": 0, "active_group": 0})
    if query is not None:
        return [g["group_id"] for g in query["group_details"]]
    return None


async def if_active(user_id, group_id):
    """True if ``group_id`` is the user's currently active connection."""
    query = await _col.find_one({"_id": user_id}, {"_id": 0, "group_details": 0})
    return query is not None and query["active_group"] == group_id


async def make_active(user_id, group_id):
    """Set the active group; returns True if a document was modified."""
    result = await _col.update_one({"_id": user_id}, {"$set": {"active_group": group_id}})
    return result.modified_count != 0


async def make_inactive(user_id):
    """Clear the active group; returns True if a document was modified."""
    result = await _col.update_one({"_id": user_id}, {"$set": {"active_group": None}})
    return result.modified_count != 0


async def delete_connection(user_id, group_id):
    """Remove a group connection; fall back active to the last remaining group."""
    try:
        result = await _col.update_one(
            {"_id": user_id}, {"$pull": {"group_details": {"group_id": group_id}}}
        )
        if result.modified_count == 0:
            return False
        query = await _col.find_one({"_id": user_id}, {"_id": 0})
        if query["group_details"]:
            if query["active_group"] == group_id:
                prev = query["group_details"][-1]["group_id"]
                await _col.update_one({"_id": user_id}, {"$set": {"active_group": prev}})
        else:
            await _col.update_one({"_id": user_id}, {"$set": {"active_group": None}})
        return True
    except Exception:
        logger.exception("delete_connection failed for user %s", user_id)
        return False


# ═══════════════════════════════════════════════════════════════════════════════
#  ⚡ Crafted by Trinity Mods (@trinityXmods) · Trinity AutoFilter
#  If this code helped you, keep the credit alive → github.com/Trinity-Mods
#  🚫 This credit is license-locked. See brand.py.
# ═══════════════════════════════════════════════════════════════════════════════
