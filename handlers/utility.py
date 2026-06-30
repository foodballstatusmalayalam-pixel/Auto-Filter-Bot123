# ═══════════════════════════════════════════════════════════════════════════════
#  ⚡ TRINITY MODS · TRINITY AUTOFILTER
#  Lightweight diagnostic commands — /ping (round-trip latency) and /alive (status).
#  ─────────────────────────────────────────────────────────────────────────────
#  Developed & maintained by Trinity Mods (@trinityXmods)
#  GitHub   : github.com/Trinity-Mods
#  Source   : github.com/Trinity-Mods/Auto-Filter-Bot
#  Telegram : t.me/trinityXmods
#  🚫 Credit is license-locked — see brand.py. Please keep this header intact.
# ═══════════════════════════════════════════════════════════════════════════════
"""
What this module does
---------------------
Two tiny, self-contained user commands that every bot deployer expects:

  • ``/ping``  — measures the real Telegram round-trip. We snapshot a monotonic
                 clock, send a placeholder message, then edit it with how many
                 milliseconds the send+edit cycle actually took. ``time.monotonic``
                 is used on purpose: it never jumps backwards if the system clock
                 is adjusted, so the delta is always a trustworthy elapsed time.

  • ``/alive`` — a short "I'm up" status card showing the bot name, the single
                 source-of-truth version (from ``version.py``) and a link to the
                 Trinity support channel, with the license-locked repo button.

These handlers register themselves on the Pyrogram ``Client`` via
``@Client.on_message`` so Pyrogram's smart-plugin loader picks them up
automatically (the same pattern every other handler in this package uses).

Note: there is intentionally NO ``/id`` command here — that already lives in
``handlers/toolkit.py``; duplicating it would double-register the handler.
"""

import time
import logging

from pyrogram import Client, filters
from pyrogram.types import (
    Message,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from pyrogram.errors import RPCError

# ── New-layout imports (the old info/utils/database paths no longer exist) ─────
from toolbox import temp
from brand import inject_repo_button
from version import PRETTY_VERSION, CODENAME

# Single source of truth for the project version metadata — imported, never
# re-typed, so /alive can never disagree with /status or the startup banner.

# Module-scoped logger: any swallowed Telegram error leaves a trail instead of
# vanishing into a bare `except: pass`.
log = logging.getLogger(__name__)

# The Trinity support / community channel surfaced on the /alive card.
SUPPORT_LINK = "https://t.me/trinityXmods"


# ═══════════════════════════════════════════════════════════════════════════════
#  /ping — measure the live Telegram round-trip latency
# ═══════════════════════════════════════════════════════════════════════════════

@Client.on_message(filters.command("ping"))
async def ping_command(client: Client, message: Message):
    """
    Report the bot's current round-trip latency in milliseconds.

    We deliberately measure across a *real* network operation (send → edit)
    rather than a fake number: snapshot the monotonic clock, send the
    placeholder, then compute the delta right before editing it in place.
    """
    # Snapshot BEFORE we touch the network. monotonic() is immune to wall-clock
    # changes, so the resulting delta is always a clean elapsed measurement.
    started = time.monotonic()

    try:
        # The placeholder reply — the very act of sending it is what we time.
        pong = await message.reply_text("🏓 Pinging...", quote=True)
    except RPCError as exc:
        # If we cannot even send the placeholder there is nothing to edit; just
        # log it so the failure is visible instead of silently disappearing.
        log.warning("Failed to send /ping placeholder: %s", exc)
        return

    # Elapsed time for the full send cycle, converted seconds → milliseconds.
    elapsed_ms = (time.monotonic() - started) * 1000

    try:
        await pong.edit_text(f"🏓 **Pong!**\n`{elapsed_ms:.2f} ms`")
    except RPCError as exc:
        # Editing can fail (message deleted, etc.) — log rather than crash.
        log.warning("Failed to edit /ping result: %s", exc)


# ───────────────────────────  ⚡ Trinity Mods · @trinityXmods  ───────────────────────────


# ═══════════════════════════════════════════════════════════════════════════════
#  /alive — short "the bot is up" status card
# ═══════════════════════════════════════════════════════════════════════════════

@Client.on_message(filters.command("alive"))
async def alive_command(client: Client, message: Message):
    """
    Reply with a compact status card: bot name, version and a support link,
    finished with the license-locked Trinity repo button.
    """
    # Prefer the live, resolved bot name (filled in at startup); fall back to a
    # sensible default if startup hasn't populated temp.B_NAME yet.
    bot_name = temp.B_NAME or CODENAME

    # Build the status text. PRETTY_VERSION already carries the build/channel
    # tag, so callers never have to re-format the version string.
    status_text = (
        f"✅ **{bot_name} is alive!**\n\n"
        f"⚡ **Engine** : {CODENAME}\n"
        f"🏷 **Version** : `{PRETTY_VERSION}`\n"
        f"💬 **Updates** : [Trinity Mods]({SUPPORT_LINK})"
    )

    # Start with our own support-channel row, then let brand.inject_repo_button
    # append the single LOCKED "Powered by Trinity Mods" row beneath it.
    rows = [[InlineKeyboardButton("💬 Support", url=SUPPORT_LINK)]]
    rows = inject_repo_button(rows)

    try:
        await message.reply_text(
            status_text,
            reply_markup=InlineKeyboardMarkup(rows),
            disable_web_page_preview=True,
            quote=True,
        )
    except RPCError as exc:
        # Never let a transient Telegram error bubble up unlogged.
        log.warning("Failed to send /alive card: %s", exc)


# ═══════════════════════════════════════════════════════════════════════════════
#  ⚡ Crafted by Trinity Mods (@trinityXmods) · Trinity AutoFilter
#  If this code helped you, keep the credit alive → github.com/Trinity-Mods
#  🚫 This credit is license-locked. See brand.py.
# ═══════════════════════════════════════════════════════════════════════════════
