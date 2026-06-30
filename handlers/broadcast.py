# ═══════════════════════════════════════════════════════════════════════════════
#  ⚡ TRINITY MODS · TRINITY AUTOFILTER
#  Admin broadcast handlers — fan a replied message out to every user / group.
#  ─────────────────────────────────────────────────────────────────────────────
#  Developed & maintained by Trinity Mods (@trinityXmods)
#  GitHub   : github.com/Trinity-Mods
#  Source   : github.com/Trinity-Mods/Auto-Filter-Bot
#  Telegram : t.me/trinityXmods
#  🚫 Credit is license-locked — see brand.py. Please keep this header intact.
# ═══════════════════════════════════════════════════════════════════════════════

import asyncio
import time
import datetime
import logging

from pyrogram import Client, filters

from config import ADMINS
from toolbox import broadcast_messages
from vault.registry import db

# Module-level logger — replaces the bare ``except:`` swallowing of the legacy code.
log = logging.getLogger(__name__)

# How many user-broadcasts may be in flight at once. ``broadcast_messages`` itself
# already absorbs FloodWait and prunes dead accounts, so a modest ceiling keeps us
# friendly to Telegram's rate limits while still parallelising the slow network hops.
CONCURRENCY_LIMIT = 10

# How often (in completed sends) we refresh the live progress message.
USER_PROGRESS_EVERY = 50
GROUP_PROGRESS_EVERY = 20

# Politeness delay between group sends — groups are far fewer than users, so we can
# afford to pace them and avoid bursty traffic.
GROUP_SEND_DELAY = 2


def _classify(delivered, reason, tallies):
    """Fold one ``broadcast_messages`` outcome into a running tally dict.

    ``broadcast_messages`` returns ``(delivered: bool, reason: str)``. A truthy
    ``delivered`` means success; otherwise ``reason`` is one of
    "Blocked" / "Deleted" / "Error" and we bump the matching counter.
    """
    if delivered:
        tallies["success"] += 1
    elif reason == "Blocked":
        tallies["blocked"] += 1
    elif reason == "Deleted":
        tallies["deleted"] += 1
    elif reason == "Error":
        tallies["failed"] += 1
    tallies["done"] += 1


# ═══════════════════════════════════════════════════════════════════════════════
#  /broadcast — deliver a replied message to every registered USER (concurrent).
# ═══════════════════════════════════════════════════════════════════════════════
@Client.on_message(filters.command("broadcast") & filters.user(ADMINS) & filters.reply)
async def broadcast_to_users(bot, message):
    # The payload is whatever the admin replied to.
    payload = message.reply_to_message
    status = await message.reply_text("Broadcasting your messages...")

    started_at = time.time()
    total_users = await db.total_users_count()

    # One shared tally that every concurrent worker folds its result into.
    tallies = {"success": 0, "blocked": 0, "deleted": 0, "failed": 0, "done": 0}

    # Bound concurrency so we never flood Telegram with thousands of simultaneous
    # copy() calls — see CONCURRENCY_LIMIT above.
    gate = asyncio.Semaphore(CONCURRENCY_LIMIT)

    async def deliver(user):
        """Send to one user under the semaphore, returning its outcome tuple."""
        async with gate:
            return await broadcast_messages(int(user["id"]), payload)

    # Spin up one task per user as we stream them from the database.
    users = await db.get_all_users()
    jobs = []
    async for user in users:
        jobs.append(asyncio.ensure_future(deliver(user)))

    # Drain the results, updating the tally and the live progress message.
    for result in await asyncio.gather(*jobs):
        delivered, reason = result
        _classify(delivered, reason, tallies)

        if not tallies["done"] % USER_PROGRESS_EVERY:
            try:
                await status.edit(
                    f"Broadcast in progress:\n\n"
                    f"Total Users {total_users}\n"
                    f"Completed: {tallies['done']} / {total_users}\n"
                    f"Success: {tallies['success']}\n"
                    f"Blocked: {tallies['blocked']}\n"
                    f"Deleted: {tallies['deleted']}"
                )
            except Exception as exc:  # progress edit is best-effort, never fatal
                log.warning("Could not edit user-broadcast progress: %s", exc)

    elapsed = datetime.timedelta(seconds=int(time.time() - started_at))
    await status.edit(
        f"Broadcast Completed:\n"
        f"Completed in {elapsed} seconds.\n\n"
        f"Total Users {total_users}\n"
        f"Completed: {tallies['done']} / {total_users}\n"
        f"Success: {tallies['success']}\n"
        f"Blocked: {tallies['blocked']}\n"
        f"Deleted: {tallies['deleted']}"
    )


# ───────────────────────────  ⚡ Trinity Mods · @trinityXmods  ───────────────────────────


# ═══════════════════════════════════════════════════════════════════════════════
#  /grp_broadcast — deliver a replied message to every connected GROUP (paced).
# ═══════════════════════════════════════════════════════════════════════════════
@Client.on_message(filters.command("grp_broadcast") & filters.user(ADMINS) & filters.reply)
async def broadcast_to_groups(bot, message):
    payload = message.reply_to_message
    status = await message.reply_text("Broadcasting your messages...")

    started_at = time.time()
    total_chats = await db.total_chat_count()

    # BUGFIX: the legacy version never initialised ``blocked`` / ``deleted`` before
    # the loop, so the first time a group was blocked or deleted it raised
    # NameError. All four counters now start at zero.
    success = 0
    blocked = 0
    deleted = 0
    failed = 0
    done = 0

    chats = await db.get_all_chats()
    async for chat in chats:
        delivered, reason = await broadcast_messages(int(chat["id"]), payload)
        if delivered:
            success += 1
        elif reason == "Blocked":
            blocked += 1
        elif reason == "Deleted":
            deleted += 1
        elif reason == "Error":
            failed += 1
        done += 1

        # Pace group sends to stay gentle on the rate limiter.
        await asyncio.sleep(GROUP_SEND_DELAY)

        if not done % GROUP_PROGRESS_EVERY:
            try:
                await status.edit(
                    f"Broadcast in progress:\n\n"
                    f"Total Chats {total_chats}\n"
                    f"Completed: {done} / {total_chats}\n"
                    f"Success: {success}\n"
                    f"Failed: {failed}"
                )
            except Exception as exc:  # progress edit is best-effort, never fatal
                log.warning("Could not edit group-broadcast progress: %s", exc)

    elapsed = datetime.timedelta(seconds=int(time.time() - started_at))
    await status.edit(
        f"Broadcast Completed:\n"
        f"Completed in {elapsed} seconds.\n\n"
        f"Total Chats {total_chats}\n"
        f"Completed: {done} / {total_chats}\n"
        f"Success: {success}\n"
        f"Failed: {failed}"
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  ⚡ Crafted by Trinity Mods (@trinityXmods) · Trinity AutoFilter
#  If this code helped you, keep the credit alive → github.com/Trinity-Mods
#  🚫 This credit is license-locked. See brand.py.
# ═══════════════════════════════════════════════════════════════════════════════
