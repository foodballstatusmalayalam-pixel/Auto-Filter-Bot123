# ═══════════════════════════════════════════════════════════════════════════════
#  ⚡ TRINITY MODS · TRINITY AUTOFILTER
#  Media uploader — push a small (<5MB) photo/video to envs.sh and return a link.
#  ─────────────────────────────────────────────────────────────────────────────
#  Developed & maintained by Trinity Mods (@trinityXmods)
#  GitHub   : github.com/Trinity-Mods
#  Source   : github.com/Trinity-Mods/Auto-Filter-Bot
#  Telegram : t.me/trinityXmods
#  🚫 Credit is license-locked — see brand.py. Please keep this header intact.
# ═══════════════════════════════════════════════════════════════════════════════

import os
import uuid
import asyncio
import logging

import requests
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# Trinity import contract — config / phrases / brand helpers.
from config import *
from phrases import phrases
from brand import inject_repo_button

log = logging.getLogger(__name__)

# Remote anonymous file host. Returns the public URL as plain text on success.
ENVS_HOST = "https://envs.sh"

# How long we are willing to wait on the network before giving up (seconds).
_UPLOAD_TIMEOUT = 60

# Telegram side limit we advertise to the user (host friendly small-media cap).
_MAX_MB = 5


def _push_to_host(local_path: str) -> str | None:
    """
    Synchronously upload a single file to envs.sh.

    This is a *blocking* requests call, so callers must run it off the event
    loop (see ``asyncio.to_thread`` below). Returns the shareable URL string on
    success, or ``None`` on any failure (the failure is logged, never printed).
    """
    try:
        with open(local_path, "rb") as fh:
            # envs.sh expects a multipart "file" field.
            resp = requests.post(
                ENVS_HOST,
                files={"file": fh},
                timeout=_UPLOAD_TIMEOUT,
            )
    except requests.exceptions.RequestException as err:
        # Covers connection errors, timeouts, DNS issues, etc.
        log.error("envs.sh upload network error: %s", err)
        return None
    except OSError as err:
        # Local file vanished / permission problem while opening.
        log.error("Could not read temp file for upload: %s", err)
        return None

    if resp.status_code == 200:
        link = resp.text.strip()
        # Defensive: an empty 200 body is not a usable link.
        return link or None

    log.warning("envs.sh responded with HTTP %s", resp.status_code)
    return None


# ───────────────────────────  ⚡ Trinity Mods · @trinityXmods  ───────────────────────────


@Client.on_message(filters.command("telegraph") & filters.private)
async def telegraph_upload(bot, update):
    """
    /telegraph — prompt the user for a sub-5MB photo/video, upload it to
    envs.sh, and reply with a shareable link plus quick-action buttons.
    """
    # Ask the user (pyromod .ask) to send the media in this private chat.
    prompt = await bot.ask(
        chat_id=update.from_user.id,
        text=f"Now send me your photo or video under {_MAX_MB}MB to get a media link.",
    )

    # Only media payloads make sense here.
    if not prompt.media:
        return await update.reply_text("**Only media is supported.**")

    status = await update.reply_text("<b>ᴜᴘʟᴏᴀᴅɪɴɢ...</b>")

    # Download to a UNIQUE temp path so concurrent users never collide, and so
    # we always know exactly which file to clean up afterwards.
    local_path = None
    try:
        unique_name = f"trinity_upload_{uuid.uuid4().hex}"
        local_path = await prompt.download(file_name=unique_name)

        # Run the blocking upload off the event loop.
        media_url = await asyncio.to_thread(_push_to_host, local_path)

        if not media_url:
            return await status.edit_text("**Failed to upload file. Please try again later.**")

        # Build the action buttons; inject the locked Trinity repo button.
        rows = [
            [
                InlineKeyboardButton(text="Open Link", url=media_url),
                InlineKeyboardButton(
                    text="Share Link",
                    url=f"https://telegram.me/share/url?url={media_url}",
                ),
            ],
            [InlineKeyboardButton(text="✗ Close ✗", callback_data="close")],
        ]
        rows = inject_repo_button(rows)

        await status.edit_text(
            text=f"<b>Link :-</b>\n\n<code>{media_url}</code>",
            disable_web_page_preview=True,
            reply_markup=InlineKeyboardMarkup(rows),
        )
    except Exception as err:  # noqa: BLE001 — last-resort guard, fully logged
        log.exception("Unexpected error during /telegraph upload: %s", err)
        try:
            await status.edit_text("**Upload failed due to an internal error.**")
        except Exception:  # editing might fail if the message is gone
            log.debug("Could not update status message after failure.")
    finally:
        # Always remove the downloaded temp file, success or failure.
        if local_path and os.path.exists(local_path):
            try:
                os.remove(local_path)
            except OSError as err:
                log.warning("Failed to remove temp file %s: %s", local_path, err)


# ═══════════════════════════════════════════════════════════════════════════════
#  ⚡ Crafted by Trinity Mods (@trinityXmods) · Trinity AutoFilter
#  If this code helped you, keep the credit alive → github.com/Trinity-Mods
#  🚫 This credit is license-locked. See brand.py.
# ═══════════════════════════════════════════════════════════════════════════════
