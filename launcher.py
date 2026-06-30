# ═══════════════════════════════════════════════════════════════════════════════
#  ⚡ TRINITY MODS · TRINITY AUTOFILTER
#  launcher.py — the entry point. Boots the bot, the worker fleet & the web server.
#  ─────────────────────────────────────────────────────────────────────────────
#  Developed & maintained by Trinity Mods (@trinityXmods)
#  GitHub   : github.com/Trinity-Mods
#  Source   : github.com/Trinity-Mods/Auto-Filter-Bot
#  Telegram : t.me/trinityXmods
#  🚫 Credit is license-locked — see brand.py. Please keep this header intact.
# ═══════════════════════════════════════════════════════════════════════════════
"""
Run with:  python3 launcher.py

Startup sequence:
  1. configure logging                    5. warm the file-index indexes
  2. verify the Trinity credit lock        6. schedule background tasks
  3. start the bot + worker fleet          7. start the embedded web server
  4. cache bot identity & banned lists     8. idle (serve) until stopped

Unlike the legacy bot, handlers are loaded ONCE via Pyrogram smart-plugins
(``plugins={"root": "handlers"}``) — there is no second manual import loop, so
no handler is ever registered twice.
"""

import os
import logging
import logging.config
import asyncio
from datetime import date, datetime

import pytz
from aiohttp import web
from pyrogram import idle, __version__ as pyro_version
from pyrogram.raw.all import layer

# ── 1. logging ────────────────────────────────────────────────────────────────
if os.path.exists("logging.conf"):
    logging.config.fileConfig("logging.conf")
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logging.getLogger().setLevel(logging.INFO)
for noisy in ("pyrogram", "imdbpy", "cinemagoer", "aiohttp", "aiohttp.web"):
    logging.getLogger(noisy).setLevel(logging.ERROR)

logger = logging.getLogger("trinity.launcher")

# ── 2. credit lock (refuses to start if the Trinity credits are tampered) ─────
import brand
brand.verify_integrity(strict=True)

# ── imports that depend on config/clients ─────────────────────────────────────
from config import (
    LOG_CHANNEL, PORT, BIND_ADRESS, ON_HEROKU, TIMEZONE, LOG_STR,
)
from phrases import phrases
from version import banner as version_banner
from reactor.client import app
from reactor.fleet import boot_clients
from reactor.web import build_app
from reactor.helpers.heartbeat import ping_loop
from vault.media_index import Media
from vault.registry import db
from toolbox import temp, check_reset_time
from handlers.extras.premium import check_expired_premium


async def main():
    """The full async startup → serve → shutdown lifecycle."""
    print(brand.BANNER)
    print(f"Booting {version_banner()} …")

    await app.start()
    me = await app.get_me()
    app.username = "@" + me.username
    temp.ME, temp.U_NAME, temp.B_NAME = me.id, me.username, me.first_name

    # 3. worker fleet (optional extra clients)
    await boot_clients()

    # 4. banned lists into memory
    temp.BANNED_USERS, temp.BANNED_CHATS = await db.get_banned()

    # 5. ensure the file-index indexes exist
    await Media.ensure_indexes()

    # 6. background tasks: premium expiry sweeper, daily counter reset, keep-alive
    app.loop.create_task(check_expired_premium(app))
    app.loop.create_task(check_reset_time())
    if ON_HEROKU:
        app.loop.create_task(ping_loop())

    logger.info("%s started for Pyrofork v%s (Layer %s) on @%s.", me.first_name, pyro_version, layer, me.username)
    logger.info(LOG_STR)
    logger.info(phrases.LOGO)

    # 7. embedded web server (health + streaming + watch pages)
    runner = web.AppRunner(await build_app())
    await runner.setup()
    await web.TCPSite(runner, BIND_ADRESS, PORT).start()
    logger.info("Trinity streaming server listening on %s:%s ✓", BIND_ADRESS, PORT)

    # startup notice to the log channel (so restarts are observable)
    tz = pytz.timezone(TIMEZONE)
    now = datetime.now(tz)
    if LOG_CHANNEL:
        try:
            await app.send_message(
                LOG_CHANNEL,
                phrases.RESTART_TXT.format(me.username, me.first_name,
                                           date.today(), now.strftime("%H:%M:%S %p")),
            )
        except Exception as exc:
            logger.warning("Could not post startup notice to LOG_CHANNEL: %s", exc)

    # 8. serve until stopped
    await idle()
    await app.stop()
    logger.info("Service stopped — bye 👋 | Trinity Mods")


# ───────────────────────────  ⚡ Trinity Mods · @trinityXmods  ───────────────────────────

if __name__ == "__main__":
    try:
        app.run(main())
    except KeyboardInterrupt:
        logging.info("Service stopped via KeyboardInterrupt — Trinity Mods")

# ═══════════════════════════════════════════════════════════════════════════════
#  ⚡ Crafted by Trinity Mods (@trinityXmods) · Trinity AutoFilter
#  If this code helped you, keep the credit alive → github.com/Trinity-Mods
#  🚫 This credit is license-locked. See brand.py.
# ═══════════════════════════════════════════════════════════════════════════════
