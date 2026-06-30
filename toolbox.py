# ═══════════════════════════════════════════════════════════════════════════════
#  ⚡ TRINITY MODS · TRINITY AUTOFILTER
#  toolbox.py — shared helpers + the in-memory `temp` state used everywhere.
#  ─────────────────────────────────────────────────────────────────────────────
#  Developed & maintained by Trinity Mods (@trinityXmods)
#  GitHub   : github.com/Trinity-Mods
#  Source   : github.com/Trinity-Mods/Auto-Filter-Bot
#  Telegram : t.me/trinityXmods
#  🚫 Credit is license-locked — see brand.py. Please keep this header intact.
# ═══════════════════════════════════════════════════════════════════════════════
"""
Grab-bag of helpers shared by the handlers: IMDb lookups, force-sub checks, the
broadcast worker, per-group settings cache, shortlink generation and the result
caption builder. ``temp`` holds light in-memory runtime state (banned lists, bot
identity, per-chat caches).

Fixes vs the legacy utils.py:
  • ``list_to_str`` no longer leaves a trailing ", ".
  • ``get_users`` referenced an undefined ``user_col`` (NameError) — now uses db.
  • ``get_poster`` initialises ``plot`` and guards the (blocking) IMDb call, which
    is now run in a thread so it never stalls the event loop.
  • The datetime/time import collision is gone.
  • FloodWait reads ``e.value`` (pyrofork v2) and the broadcast retry is a loop.
"""

import os
import re
import asyncio
import logging
from datetime import datetime, timedelta, date, time

import pytz
import aiohttp
import requests
from bs4 import BeautifulSoup
from shortzy import Shortzy
from imdb import Cinemagoer
from pyrogram import enums
from pyrogram.types import Message
from pyrogram.errors import (
    InputUserDeactivated, UserNotParticipant, FloodWait, UserIsBlocked, PeerIdInvalid,
)

from config import *                         # noqa: F401,F403 — exposes UPPER_SNAKE settings
from phrases import phrases
from vault.registry import db

logger = logging.getLogger("trinity.toolbox")

imdb = Cinemagoer()

# Regex used to parse [text](buttonurl:...) markup in custom messages.
BTN_URL_REGEX = re.compile(r"(\[([^\[]+?)\]\((buttonurl|buttonalert):(?:/{0,2})(.+?)(:same)?\))")

_TZ = pytz.timezone(TIMEZONE)


def _flood_wait(exc) -> int:
    """Return the FloodWait sleep duration regardless of pyrogram/pyrofork version."""
    return getattr(exc, "value", getattr(exc, "x", 0))


class temp(object):
    """Light, process-local runtime state (lost on restart — that's intentional)."""
    BANNED_USERS = []
    BANNED_CHATS = []
    ME = None
    CURRENT = int(os.environ.get("SKIP", 2))
    CANCEL = False
    MELCOW = {}
    U_NAME = None
    B_NAME = None
    B_LINK = None
    SETTINGS = {}
    KEYWORD = {}
    GETALL = {}
    SPELL_CHECK = {}
    IMDB_CAP = {}
    CHAT = {}


async def check_reset_time():
    """Reset daily file/send-all counters at 23:59 local time, forever."""
    while True:
        now = datetime.now(_TZ)
        target = _TZ.localize(datetime.combine(now.date(), time(23, 59)))
        if now > target:
            target += timedelta(days=1)
        diff = (target - now).total_seconds()
        logger.info("Next daily counter reset in %.0f minutes.", diff / 60)
        await asyncio.sleep(diff)
        await db.reset_all_files_count()
        await db.reset_allsend_files()
        logger.info("Daily file/send counts reset.")


async def get_seconds(time_string: str) -> int:
    """Parse a string like '5min' / '2 hour' / '1day' into seconds."""
    value, index = "", 0
    while index < len(time_string) and time_string[index].isdigit():
        value += time_string[index]
        index += 1
    unit = time_string[index:].strip()
    value = int(value) if value else 0
    return {
        "s": value, "min": value * 60, "hour": value * 3600,
        "day": value * 86400, "month": value * 86400 * 30, "year": value * 86400 * 365,
    }.get(unit, 0)


# ── force-subscribe checks ─────────────────────────────────────────────────
async def is_req_subscribed(bot, query):
    """True if the user satisfies request-to-join force-sub (join req OR member)."""
    if await db.find_join_req(query.from_user.id):
        return True
    try:
        member = await bot.get_chat_member(AUTH_CHANNEL, query.from_user.id)
    except UserNotParticipant:
        return False
    except Exception as exc:
        logger.warning("is_req_subscribed error: %s", exc)
        return False
    return member.status != enums.ChatMemberStatus.BANNED


async def is_subscribed(bot, user_id, channel_id):
    """True if ``user_id`` is a (non-banned) member of ``channel_id``."""
    try:
        member = await bot.get_chat_member(channel_id, user_id)
    except UserNotParticipant:
        return False
    except Exception as exc:
        logger.warning("is_subscribed(%s) error: %s", channel_id, exc)
        return False
    return member.status != enums.ChatMemberStatus.BANNED


# ───────────────────────────  ⚡ Trinity Mods · @trinityXmods  ───────────────────────────


async def get_poster(query, bulk=False, id=False, file=None):
    """Look up IMDb metadata for ``query`` (or an IMDb id). Returns a dict or None.

    The blocking Cinemagoer calls are run in a worker thread so the event loop
    keeps serving other users while IMDb responds.
    """
    plot = ""
    if not id:
        query = (query.strip()).lower()
        title = query
        year = re.findall(r"[1-2]\d{3}$", query, re.IGNORECASE)
        if year:
            year = list_to_str(year[:1])
            title = query.replace(year, "").strip()
        elif file is not None:
            found = re.findall(r"[1-2]\d{3}", file, re.IGNORECASE)
            year = list_to_str(found[:1]) if found else None
        else:
            year = None
        try:
            movies = await asyncio.to_thread(imdb.search_movie, title.lower(), 10)
        except Exception as exc:
            logger.warning("IMDb search failed for %r: %s", title, exc)
            return None
        if not movies:
            return None
        if year:
            filtered = list(filter(lambda k: str(k.get("year")) == str(year), movies)) or movies
        else:
            filtered = movies
        movies = list(filter(lambda k: k.get("kind") in ["movie", "tv series"], filtered)) or filtered
        if bulk:
            return movies
        movieid = movies[0].movieID
    else:
        movieid = query

    try:
        movie = await asyncio.to_thread(imdb.get_movie, movieid)
    except Exception as exc:
        logger.warning("IMDb get_movie failed for %s: %s", movieid, exc)
        return None

    if movie.get("original air date"):
        release_date = movie["original air date"]
    elif movie.get("year"):
        release_date = movie.get("year")
    else:
        release_date = "N/A"

    if not LONG_IMDB_DESCRIPTION:
        plot = movie.get("plot")
        plot = plot[0] if plot else ""
    else:
        plot = movie.get("plot outline") or ""
    if plot and len(plot) > 800:
        plot = plot[:800] + "..."

    return {
        "title": movie.get("title"), "votes": movie.get("votes"),
        "aka": list_to_str(movie.get("akas")), "seasons": movie.get("number of seasons"),
        "box_office": movie.get("box office"), "localized_title": movie.get("localized title"),
        "kind": movie.get("kind"), "imdb_id": f"tt{movie.get('imdbID')}",
        "cast": list_to_str(movie.get("cast")), "runtime": list_to_str(movie.get("runtimes")),
        "countries": list_to_str(movie.get("countries")), "certificates": list_to_str(movie.get("certificates")),
        "languages": list_to_str(movie.get("languages")), "director": list_to_str(movie.get("director")),
        "writer": list_to_str(movie.get("writer")), "producer": list_to_str(movie.get("producer")),
        "composer": list_to_str(movie.get("composer")), "cinematographer": list_to_str(movie.get("cinematographer")),
        "music_team": list_to_str(movie.get("music department")), "distributors": list_to_str(movie.get("distributors")),
        "release_date": release_date, "year": movie.get("year"), "genres": list_to_str(movie.get("genres")),
        "poster": movie.get("full-size cover url"), "plot": plot, "rating": str(movie.get("rating")),
        "url": f"https://www.imdb.com/title/tt{movieid}",
    }


async def broadcast_messages(user_id, message):
    """Copy ``message`` to a single user; prune dead users; loop on FloodWait."""
    while True:
        try:
            await message.copy(chat_id=user_id)
            return True, "Success"
        except FloodWait as exc:
            await asyncio.sleep(_flood_wait(exc))
            continue
        except InputUserDeactivated:
            await db.delete_user(int(user_id))
            return False, "Deleted"
        except UserIsBlocked:
            return False, "Blocked"
        except PeerIdInvalid:
            await db.delete_user(int(user_id))
            return False, "Error"
        except Exception:
            return False, "Error"


# ── per-group settings cache ───────────────────────────────────────────────
async def get_settings(group_id):
    settings = temp.SETTINGS.get(group_id)
    if not settings:
        settings = await db.get_settings(group_id)
        temp.SETTINGS[group_id] = settings
    return settings


async def save_group_settings(group_id, key, value):
    current = await get_settings(group_id)
    current[key] = value
    temp.SETTINGS[group_id] = current
    await db.update_settings(group_id, current)


# ── small formatting helpers ───────────────────────────────────────────────
def get_size(size):
    """Return a human-readable size like ``1.44 GB``."""
    units = ["Bytes", "KB", "MB", "GB", "TB", "PB", "EB"]
    size = float(size)
    i = 0
    while size >= 1024.0 and i < len(units) - 1:
        i += 1
        size /= 1024.0
    return "%.2f %s" % (size, units[i])


def list_to_str(k):
    """Join a list into 'a, b, c' (legacy left a trailing comma)."""
    if not k:
        return "N/A"
    if len(k) == 1:
        return str(k[0])
    return ", ".join(str(elem) for elem in k)


def get_file_id(msg: Message):
    """Return the media object on a message, tagged with its message_type."""
    if msg.media:
        for kind in ("photo", "animation", "audio", "document", "video", "video_note", "voice", "sticker"):
            obj = getattr(msg, kind)
            if obj:
                setattr(obj, "message_type", kind)
                return obj
    return None


def extract_user(message: Message):
    """Extract (user_id, first_name) from a reply, a mention, or the sender."""
    user_id = user_first_name = None
    if message.reply_to_message:
        user_id = message.reply_to_message.from_user.id
        user_first_name = message.reply_to_message.from_user.first_name
    elif len(message.command) > 1:
        if len(message.entities) > 1 and message.entities[1].type == enums.MessageEntityType.TEXT_MENTION:
            entity = message.entities[1]
            user_id = entity.user.id
            user_first_name = entity.user.first_name
        else:
            user_id = message.command[1]
            user_first_name = user_id
        try:
            user_id = int(user_id)
        except ValueError:
            pass
    else:
        user_id = message.from_user.id
        user_first_name = message.from_user.first_name
    return user_id, user_first_name


# ── shorteners ──────────────────────────────────────────────────────────────
async def stream_site(link, grp_id):
    """Shorten a streaming link with the group's (or default) stream shortener."""
    try:
        settings = await get_settings(grp_id) or {}
        api = settings.get("streamapi", STREAM_API)
        site = settings.get("streamsite", STREAM_SITE)
        shortzy = Shortzy(api, site)
        try:
            return await shortzy.convert(link)
        except Exception:
            return await shortzy.get_quick_link(link)
    except Exception as exc:
        logger.error("stream_site error: %s", exc)
        return link


async def get_shortlink(link, grp_id, is_second_shortener=False, is_third_shortener=False):
    """Shorten a verification link using the appropriate tier's shortener."""
    settings = await get_settings(grp_id) or {}
    if is_third_shortener:
        api, site = settings.get("verify_api3", VERIFY_API3), settings.get("verify_3", VERIFY_URL3)
    elif is_second_shortener:
        api, site = settings.get("verify_api2", VERIFY_API2), settings.get("verify_2", VERIFY_URL2)
    else:
        api, site = settings.get("verify_api", VERIFY_API), settings.get("verify", VERIFY_URL)
    shortzy = Shortzy(api, site)
    try:
        return await shortzy.convert(link)
    except Exception:
        return await shortzy.get_quick_link(link)


async def get_users():
    """Return ``(count, [user_docs])`` for the premium ledger (used by sweepers)."""
    count = await db.premium.count_documents({})
    cursor = db.premium.find({})
    users = await cursor.to_list(length=int(count))
    return count, users


# ── result caption builder ──────────────────────────────────────────────────
async def get_text(settings, remaining_seconds, files, query, total_results, search):
    """Build the inline-result caption (with or without an IMDb card)."""
    username = temp.U_NAME or "YourBot"
    base = (
        f"☠️ ᴛɪᴛʟᴇ : <code>{search}</code>\n"
        f"📂 ᴛᴏᴛᴀʟ ꜰɪʟᴇs : <code>{total_results}</code>\n"
        f"📝 ʀᴇǫᴜᴇsᴛᴇᴅ ʙʏ : {query.from_user.first_name}\n"
        f"⏰ ʀᴇsᴜʟᴛ ɪɴ : <code>{remaining_seconds} sᴇᴄᴏɴᴅs</code>\n\n"
    )
    try:
        if settings.get("imdb"):
            cap = temp.IMDB_CAP.get(query.from_user.id)
            if cap:
                pass  # reuse the cached IMDb card
            else:
                movie = await get_poster(search, file=(files[0]).file_name)
                if movie:
                    cap = phrases.IMDB_TEMPLATE_TXT.format(
                        query=search, title=movie["title"], votes=movie["votes"], aka=movie["aka"],
                        seasons=movie["seasons"], box_office=movie["box_office"],
                        localized_title=movie["localized_title"], kind=movie["kind"],
                        imdb_id=movie["imdb_id"], cast=movie["cast"], runtime=movie["runtime"],
                        countries=movie["countries"], certificates=movie["certificates"],
                        languages=movie["languages"], director=movie["director"], writer=movie["writer"],
                        producer=movie["producer"], composer=movie["composer"],
                        cinematographer=movie["cinematographer"], music_team=movie["music_team"],
                        distributors=movie["distributors"], release_date=movie["release_date"],
                        year=movie["year"], genres=movie["genres"], poster=movie["poster"],
                        plot=movie["plot"], rating=movie["rating"], url=movie["url"],
                    )
                else:
                    cap = base + "<b>📚 <u>Your Requested Files</u> 👇</b>\n\n"
            for file in files:
                cap += (
                    f"\n\n<b><a href='https://telegram.me/{username}?start=files_"
                    f"{query.message.chat.id}_{file.file_id}'>📁 {get_size(file.file_size)} ▷ {file.file_name}</a></b>"
                )
        else:
            cap = base + "<b>📚 <u>Your Requested Files</u> 👇</b>\n\n"
            for file in files:
                cap += (
                    f"<b><a href='https://telegram.me/{username}?start=files_"
                    f"{query.message.chat.id}_{file.file_id}'>📁 {get_size(file.file_size)} ▷ {file.file_name}</a></b>\n\n"
                )
        return cap
    except Exception as exc:
        await query.answer(f"{exc}", show_alert=True)
        return base


# ═══════════════════════════════════════════════════════════════════════════════
#  ⚡ Crafted by Trinity Mods (@trinityXmods) · Trinity AutoFilter
#  If this code helped you, keep the credit alive → github.com/Trinity-Mods
#  🚫 This credit is license-locked. See brand.py.
# ═══════════════════════════════════════════════════════════════════════════════
