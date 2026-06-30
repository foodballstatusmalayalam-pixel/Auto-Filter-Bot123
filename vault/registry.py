# ═══════════════════════════════════════════════════════════════════════════════
#  ⚡ TRINITY MODS · TRINITY AUTOFILTER
#  vault/registry.py — users, groups, premium, verification, settings & analytics.
#  ─────────────────────────────────────────────────────────────────────────────
#  Developed & maintained by Trinity Mods (@trinityXmods)
#  GitHub   : github.com/Trinity-Mods
#  Source   : github.com/Trinity-Mods/Auto-Filter-Bot
#  Telegram : t.me/trinityXmods
#  🚫 Credit is license-locked — see brand.py. Please keep this header intact.
# ═══════════════════════════════════════════════════════════════════════════════
"""
``db`` is the central record-keeper. It owns the user accounts, group registry,
per-group settings, the premium/trial ledger, the daily-verification clock, the
redeem-code store and (new) lightweight search analytics + open movie requests.

Fixes vs the legacy ``Database`` class:
  • ``reset_daily_files_count`` wrote the typo key ``files_coun`` → fixed.
  • the premium collection was named ``uersz`` → renamed ``premium_users``.
  • premium expiry is stored tz-aware in UTC (legacy mixed naive/aware datetimes,
    so /myplan was 5h30m off on UTC hosts).
  • the free-trial length is configurable (TRIAL_TIME) instead of hardcoded.
"""

import logging
from datetime import datetime, timedelta, timezone

import pytz

from config import (
    IMDB, IMDB_TEMPLATE, MELCOW_NEW_USERS, SINGLE_BUTTON, SPELL_CHECK_REPLY,
    AUTO_DELETE, MAX_BTN, AUTO_FFILTER, TUTORIAL, TUTORIAL2, TUTORIAL3,
    REFERAL_TIME, TRIAL_TIME, STREAM_API, STREAM_SITE, VERIFY_URL, VERIFY_API,
    VERIFY_URL2, VERIFY_API2, VERIFY_URL3, VERIFY_API3, LIMIT_MODE, TWO_VERIFY_GAP,
    THIRD_VERIFY_GAP, STREAM_MODE, LOG_CHANNEL, IS_VERIFY, AUTH_CHANNEL,
    CUSTOM_FILE_CAPTION, FILE_LIMITE, SEND_ALL_LIMITE, TIMEZONE,
)
from vault import database          # the ONE shared motor database

logger = logging.getLogger("trinity.registry")

_TZ = pytz.timezone(TIMEZONE)
# Sentinel "verified long ago" timestamps for new verification rows.
_LONG_AGO_1 = datetime(2020, 5, 17, tzinfo=_TZ)
_LONG_AGO_2 = datetime(2019, 5, 17, tzinfo=_TZ)
_LONG_AGO_3 = datetime(2018, 5, 17, tzinfo=_TZ)


class CoreDB:
    """Async MongoDB record-keeper for everything except the file index."""

    def __init__(self):
        self.db = database
        self.col = self.db.users               # main user accounts
        self.grp = self.db.groups              # group registry
        self.premium = self.db.premium_users   # premium ledger (was the 'uersz' typo)
        self.codes = self.db.codes             # redeem codes
        self.trinity = self.db.verify_clock    # daily-verification timestamps
        self.req = self.db.join_requests       # force-sub join requests
        self.verify_id = self.db.verify_id     # one-time verify handshakes
        self.settings_col = self.db.settings   # global settings k/v
        self.searches = self.db.searches       # NEW: search analytics
        self.open_requests = self.db.open_requests  # NEW: pending movie requests

    # ── document templates ───────────────────────────────────────────────────
    def new_user(self, id, name):
        return dict(
            id=id, name=name, send_all=0, files_count=0, lifetime_files=0,
            ban_status=dict(is_banned=False, ban_reason=""),
        )

    def new_group(self, id, title, owner_id):
        return dict(
            id=id, title=title, owner_id=owner_id,
            is_verified=False, is_rejected=False,
            chat_status=dict(is_disabled=False, reason=""),
        )

    # ── global settings k/v ──────────────────────────────────────────────────
    async def get_setting(self, key, default=None):
        doc = await self.settings_col.find_one({"name": key})
        return doc.get("value", default) if doc else default

    async def set_setting(self, key, value):
        await self.settings_col.update_one({"name": key}, {"$set": {"value": value}}, upsert=True)

    # ── force-sub join requests ──────────────────────────────────────────────
    async def find_join_req(self, id):
        return bool(await self.req.find_one({"id": id}))

    async def add_join_req(self, id):
        await self.req.update_one({"id": id}, {"$set": {"id": id}}, upsert=True)

    async def del_join_req(self):
        await self.req.drop()

    # ── daily verification clock (IST midnight reset) ────────────────────────
    async def get_trinity_user(self, user_id):
        user_id = int(user_id)
        user = await self.trinity.find_one({"user_id": user_id})
        if not user:
            user = {"user_id": user_id, "last_verified": _LONG_AGO_1, "second_verified": _LONG_AGO_2}
            await self.trinity.insert_one(user)
        return user

    async def update_trinity_user(self, user_id, value: dict):
        return await self.trinity.update_one({"user_id": int(user_id)}, {"$set": value})

    async def _verified_today(self, user_id, field):
        user = await self.get_trinity_user(user_id)
        stamp = user.get(field) or _LONG_AGO_1
        stamp = stamp.astimezone(_TZ)
        now = datetime.now(_TZ)
        midnight = datetime(now.year, now.month, now.day, tzinfo=_TZ)
        seconds_since_midnight = (now - midnight).total_seconds()
        return (now - stamp).total_seconds() <= seconds_since_midnight

    async def is_user_verified(self, user_id):
        return await self._verified_today(user_id, "last_verified")

    async def user_verified(self, user_id):
        return await self._verified_today(user_id, "second_verified")

    async def use_second_shortener(self, user_id, gap):
        user = await self.get_trinity_user(user_id)
        if not user.get("second_verified"):
            await self.update_trinity_user(user_id, {"second_verified": _LONG_AGO_2})
            user = await self.get_trinity_user(user_id)
        if await self.is_user_verified(user_id):
            last = user["last_verified"].astimezone(_TZ)
            if (datetime.now(_TZ) - last) > timedelta(seconds=gap):
                return user["second_verified"].astimezone(_TZ) < last
        return False

    async def use_third_shortener(self, user_id, gap):
        user = await self.get_trinity_user(user_id)
        if not user.get("third_verified"):
            await self.update_trinity_user(user_id, {"third_verified": _LONG_AGO_3})
            user = await self.get_trinity_user(user_id)
        if await self.user_verified(user_id):
            second = user["second_verified"].astimezone(_TZ)
            if (datetime.now(_TZ) - second) > timedelta(seconds=gap):
                return user["third_verified"].astimezone(_TZ) < second
        return False

    # ── one-time verify handshakes ───────────────────────────────────────────
    async def create_verify_id(self, user_id: int, hash):
        return await self.verify_id.insert_one({"user_id": user_id, "hash": hash, "verified": False})

    async def get_verify_id_info(self, user_id: int, hash):
        return await self.verify_id.find_one({"user_id": user_id, "hash": hash})

    async def update_verify_id_info(self, user_id, hash, value: dict):
        return await self.verify_id.update_one({"user_id": user_id, "hash": hash}, {"$set": value})

    # ───────────────────────  ⚡ Trinity Mods · @trinityXmods  ───────────────────────
    # ── user accounts ────────────────────────────────────────────────────────
    async def add_user(self, id, name):
        await self.col.insert_one(self.new_user(id, name))

    async def is_user_exist(self, id):
        return bool(await self.col.find_one({"id": int(id)}))

    async def total_users_count(self):
        return await self.col.count_documents({})

    async def remove_ban(self, id):
        await self.col.update_one({"id": id}, {"$set": {"ban_status": dict(is_banned=False, ban_reason="")}})

    async def ban_user(self, user_id, ban_reason="No Reason"):
        await self.col.update_one({"id": user_id}, {"$set": {"ban_status": dict(is_banned=True, ban_reason=ban_reason)}})

    async def get_ban_status(self, id):
        default = dict(is_banned=False, ban_reason="")
        user = await self.col.find_one({"id": int(id)})
        return user.get("ban_status", default) if user else default

    async def get_all_users(self):
        return self.col.find({})

    async def delete_user(self, user_id):
        await self.col.delete_many({"id": int(user_id)})

    async def get_banned(self):
        users = self.col.find({"ban_status.is_banned": True})
        chats = self.grp.find({"chat_status.is_disabled": True})
        b_users = [u["id"] async for u in users]
        b_chats = [c["id"] async for c in chats]
        return b_users, b_chats

    # ── daily file counters ──────────────────────────────────────────────────
    async def files_count(self, user_id, key):
        user = await self.col.find_one({"id": user_id})
        if user is None:
            await self.add_user(user_id, "None")
            return 0
        return user.get(key, 0)

    async def update_files(self, user_id, key, value):
        await self.col.update_one({"id": user_id}, {"$set": {key: value}})

    async def reset_all_files_count(self):
        await self.col.update_many({}, {"$set": {"files_count": 0}})

    async def reset_allsend_files(self):
        await self.col.update_many({}, {"$set": {"send_all": 0}})

    async def reset_daily_files_count(self, user_id):
        # FIX: legacy wrote the typo key "files_coun" — corrected to "files_count".
        if await self.col.find_one({"id": user_id}):
            await self.col.update_one({"id": user_id}, {"$set": {"files_count": 0}})

    # ── group registry & settings ────────────────────────────────────────────
    async def add_chat(self, chat, title, owner_id):
        await self.grp.insert_one(self.new_group(chat, title, owner_id))

    async def get_chat(self, chat_id):
        chat = await self.grp.find_one({"id": int(chat_id)})
        return chat if chat else False

    async def re_enable_chat(self, id):
        await self.grp.update_one({"id": int(id)}, {"$set": {"chat_status": dict(is_disabled=False, reason="")}})

    async def update_settings(self, id, settings):
        await self.grp.update_one({"id": int(id)}, {"$set": {"settings": settings}})

    async def get_settings(self, id):
        default = {
            "button": SINGLE_BUTTON, "imdb": IMDB, "spell_check": SPELL_CHECK_REPLY,
            "welcome": MELCOW_NEW_USERS, "auto_delete": AUTO_DELETE, "auto_ffilter": AUTO_FFILTER,
            "max_btn": MAX_BTN, "template": IMDB_TEMPLATE, "verify": VERIFY_URL, "verify_api": VERIFY_API,
            "verify_2": VERIFY_URL2, "verify_api2": VERIFY_API2, "verify_3": VERIFY_URL3,
            "verify_api3": VERIFY_API3, "verify_time": TWO_VERIFY_GAP, "verify_time2": THIRD_VERIFY_GAP,
            "tutorial": TUTORIAL, "tutorial2": TUTORIAL2, "tutorial3": TUTORIAL3, "filelock": LIMIT_MODE,
            "log": LOG_CHANNEL, "is_verify": IS_VERIFY, "fsub_id": AUTH_CHANNEL, "file_limit": FILE_LIMITE,
            "all_limit": SEND_ALL_LIMITE, "stream_mode": STREAM_MODE, "streamapi": STREAM_API,
            "streamsite": STREAM_SITE, "caption": CUSTOM_FILE_CAPTION,
        }
        chat = await self.grp.find_one({"id": int(id)})
        return chat.get("settings", default) if chat else default

    async def disable_chat(self, chat, reason="No Reason"):
        await self.grp.update_one({"id": int(chat)}, {"$set": {"chat_status": dict(is_disabled=True, reason=reason)}})

    async def verify_group(self, chat_id):
        await self.grp.update_one({"id": int(chat_id)}, {"$set": {"is_verified": True}})

    async def un_rejected(self, chat_id):
        await self.grp.update_one({"id": int(chat_id)}, {"$set": {"is_rejected": False}})

    async def reject_group(self, chat_id):
        await self.grp.update_one({"id": int(chat_id)}, {"$set": {"is_rejected": True}})

    async def check_group_verification(self, chat_id):
        chat = await self.get_chat(chat_id)
        return chat.get("is_verified") if chat else False

    async def rejected_group(self, chat_id):
        chat = await self.get_chat(chat_id)
        return chat.get("is_rejected") if chat else False

    async def get_all_groups(self):
        return await self.grp.find().to_list(None)

    async def delete_all_groups(self):
        await self.grp.delete_many({})

    async def total_chat_count(self):
        return await self.grp.count_documents({})

    async def get_all_chats(self):
        return self.grp.find({})

    async def get_db_size(self):
        return (await self.db.command("dbstats"))["dataSize"]

    # ── premium / trial / referral (tz-aware UTC) ────────────────────────────
    async def get_user(self, user_id):
        return await self.premium.find_one({"id": user_id})

    async def update_user(self, user_data):
        await self.premium.update_one({"id": user_data["id"]}, {"$set": user_data}, upsert=True)

    async def has_premium_access(self, user_id):
        data = await self.get_user(user_id)
        if not data:
            return False
        expiry = data.get("expiry_time")
        if expiry is None:
            return False
        if expiry.tzinfo is None:                    # tolerate legacy naive rows
            expiry = expiry.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) <= expiry:
            return True
        await self.premium.update_one({"id": user_id}, {"$set": {"expiry_time": None}})
        return False

    async def update_one(self, filter_query, update_data):
        try:
            result = await self.premium.update_one(filter_query, update_data)
            return result.matched_count == 1
        except Exception:
            logger.exception("premium update_one failed")
            return False

    async def get_expired(self, current_time):
        expired = []
        async for user in self.premium.find({"expiry_time": {"$lt": current_time}}):
            expired.append(user)
        return expired

    async def remove_premium_access(self, user_id):
        return await self.update_one({"id": user_id}, {"$set": {"expiry_time": None}})

    async def check_trial_status(self, user_id):
        data = await self.get_user(user_id)
        return data.get("has_free_trial", False) if data else False

    async def give_free_trial(self, user_id):
        expiry = datetime.now(timezone.utc) + timedelta(seconds=TRIAL_TIME)
        await self.premium.update_one(
            {"id": user_id},
            {"$set": {"id": user_id, "expiry_time": expiry, "has_free_trial": True}},
            upsert=True,
        )

    async def give_referal(self, userid):
        expiry = datetime.now(timezone.utc) + timedelta(seconds=REFERAL_TIME)
        await self.premium.update_one(
            {"id": userid},
            {"$set": {"id": userid, "expiry_time": expiry, "has_free_trial": True}},
            upsert=True,
        )

    # ── NEW: search analytics (powers /trending) ─────────────────────────────
    async def log_query(self, term, chat_id=None):
        term = (term or "").strip().lower()
        if not term:
            return
        await self.searches.update_one(
            {"term": term},
            {"$inc": {"hits": 1}, "$set": {"last_chat": chat_id}},
            upsert=True,
        )

    async def get_trending(self, limit=10):
        cursor = self.searches.find().sort("hits", -1).limit(limit)
        return [(d["term"], d.get("hits", 0)) async for d in cursor]

    # ── NEW: open movie requests (powers request-fulfillment pings) ──────────
    async def add_open_request(self, user_id, query):
        query = (query or "").strip().lower()
        if query:
            await self.open_requests.update_one(
                {"user_id": user_id, "query": query},
                {"$set": {"user_id": user_id, "query": query}},
                upsert=True,
            )

    async def take_matching_requests(self, file_name):
        """Pop and return open requests whose query appears in ``file_name``."""
        name = (file_name or "").lower()
        matched = []
        async for r in self.open_requests.find():
            if r.get("query") and r["query"] in name:
                matched.append(r)
        if matched:
            await self.open_requests.delete_many({"_id": {"$in": [m["_id"] for m in matched]}})
        return matched


# The singleton used everywhere.
db = CoreDB()

# ═══════════════════════════════════════════════════════════════════════════════
#  ⚡ Crafted by Trinity Mods (@trinityXmods) · Trinity AutoFilter
#  If this code helped you, keep the credit alive → github.com/Trinity-Mods
#  🚫 This credit is license-locked. See brand.py.
# ═══════════════════════════════════════════════════════════════════════════════
