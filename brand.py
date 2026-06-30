# ═══════════════════════════════════════════════════════════════════════════════
#  ⚡ TRINITY MODS · TRINITY AUTOFILTER
#  brand.py — the license-locked credit / attribution core of the project.
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
This is the single place that owns Trinity Mods' attribution. Two things are
protected here:

  1. The constants below (brand name, owner, repo, the "Powered by Trinity Mods"
     button text) are fingerprinted with SHA-256. If any of them is changed
     without updating the fingerprint, the bot refuses to start.

  2. One LOCKED "⚡ Powered by Trinity Mods" inline button is injected into the
     bot's menus. The rest of the user-facing bot is fully re-brandable by the
     deployer — only this one button and the in-source credit headers are pinned.

Honest disclosure
-----------------
This is open-source Python. A determined person can always edit any client-side
check out. The goal here is to make removing the credit *hard and tamper-evident*,
not impossible. This module performs **no network calls**, collects **no data**,
and contains **no hidden backdoor** of any kind. Read it top to bottom — it is
exactly what it says it is.
"""

import os
import sys
import hashlib
import logging

logger = logging.getLogger("trinity.brand")

# ── LOCKED CREDIT CONSTANTS ───────────────────────────────────────────────────
# Changing any of these without recomputing _FINGERPRINT will stop the bot.
BRAND       = "Trinity Mods"
OWNER       = "trinityXmods"
GITHUB      = "https://github.com/Trinity-Mods"
REPO_URL    = "https://github.com/Trinity-Mods/Auto-Filter-Bot"
SUPPORT     = "https://t.me/trinityXmods"
BUTTON_TEXT = "⚡ Pᴏᴡᴇʀᴇᴅ ʙʏ Tʀɪɴɪᴛʏ Mᴏᴅs"

# SHA-256 of "BRAND|OWNER|GITHUB|REPO_URL|SUPPORT|BUTTON_TEXT".
# Recompute with brand.compute_fingerprint() if you legitimately rebrand a fork.
_FINGERPRINT = "6a38be2776df0c5b1f354252e4d60d4eba328a6d6e741f63706cf66ba24bddb0"

# The credit header signature that must remain at the top of the core files.
_BANNER_SIGNATURE = "Trinity Mods (@trinityXmods)"
_BANNER_FILES = ("launcher.py", "config.py", "brand.py")

# Marker that must remain beside the locked button inside the command center.
LOCK_MARKER = "TRINITY-REPO-BUTTON (LOCKED)"
_LOCK_FILE = os.path.join("handlers", "commandcenter.py")

# Console banner printed at startup.
BANNER = r"""
   ______       _       _ __                     ___    ____
  /_  __/____  (_)___  (_) /___  __    ____ _   /   |  / __/
   / / / ___/ / / __ \/ / __/ / / /   / __ `/  / /| | / /_
  / / / /    / / / / / / /_/ /_/ /   / /_/ /  / ___ |/ __/
 /_/ /_/  __/_/_/ /_/_/\__/\__, /    \__,_/  /_/  |_/_/    AUTOFILTER
         /___/            /____/   ⚡ powered by Trinity Mods · @trinityXmods
"""


def compute_fingerprint() -> str:
    """Return the SHA-256 fingerprint of the current credit constants."""
    payload = "|".join([BRAND, OWNER, GITHUB, REPO_URL, SUPPORT, BUTTON_TEXT])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _here(*parts) -> str:
    """Resolve a path relative to this file's directory (repo root)."""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), *parts)


def _abort(reason: str) -> None:
    """Loudly explain why startup was blocked, then exit."""
    bar = "=" * 70
    msg = (
        f"\n{bar}\n"
        f"TRINITY CREDIT LOCK — STARTUP ABORTED\n"
        f"Reason : {reason}\n"
        f"This project is developed by Trinity Mods (@trinityXmods).\n"
        f"Restore the original credits to run the bot: {REPO_URL}\n"
        f"{bar}\n"
    )
    # Use both logging and print — logging may not be configured this early.
    try:
        logger.critical(msg)
    except Exception:
        pass
    print(msg)
    sys.exit(1)


# ───────────────────────────  ⚡ Trinity Mods · @trinityXmods  ───────────────────────────


def verify_integrity(strict: bool = True) -> bool:
    """
    Validate that the Trinity Mods credits are intact.

    strict=True  (startup): any failure calls sys.exit(1).
    strict=False (probes) : returns True/False without exiting.
    """
    # 1) Constants fingerprint.
    if compute_fingerprint() != _FINGERPRINT:
        if strict:
            _abort("credit constants were modified")
        return False

    # 2) Credit header must still be present in the core files.
    for fname in _BANNER_FILES:
        try:
            with open(_here(fname), "r", encoding="utf-8", errors="ignore") as fh:
                content = fh.read()
        except OSError:
            if strict:
                _abort(f"core file missing: {fname}")
            return False
        if _BANNER_SIGNATURE not in content:
            if strict:
                _abort(f"credit header removed from {fname}")
            return False

    # 3) The locked repo button marker must remain in the command center, and
    #    the file must actually build the button via repo_button().
    try:
        with open(_here(_LOCK_FILE), "r", encoding="utf-8", errors="ignore") as fh:
            src = fh.read()
    except OSError:
        if strict:
            _abort(f"{_LOCK_FILE} is missing")
        return False
    if LOCK_MARKER not in src or "repo_button" not in src:
        if strict:
            _abort(f"locked Trinity repo button removed from {_LOCK_FILE}")
        return False

    return True


def repo_button():
    """Return the single LOCKED InlineKeyboardButton linking to the source repo."""
    from pyrogram.types import InlineKeyboardButton
    verify_integrity(strict=True)
    return InlineKeyboardButton(BUTTON_TEXT, url=REPO_URL)


def inject_repo_button(rows):
    """Append the locked Trinity button as its own row to a list of button rows."""
    if rows is None:
        rows = []
    rows.append([repo_button()])
    return rows


# Validate the moment this module is imported, so the credit can't be silenced
# simply by never calling verify_integrity() from the launcher.
verify_integrity(strict=True)

# ═══════════════════════════════════════════════════════════════════════════════
#  ⚡ Crafted by Trinity Mods (@trinityXmods) · Trinity AutoFilter
#  If this code helped you, keep the credit alive → github.com/Trinity-Mods
#  🚫 This credit is license-locked. See brand.py.
# ═══════════════════════════════════════════════════════════════════════════════
