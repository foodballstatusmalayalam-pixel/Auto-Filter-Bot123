# ═══════════════════════════════════════════════════════════════════════════════
#  ⚡ TRINITY MODS · TRINITY AUTOFILTER
#  Sticker tools — reveal the file_id / file_unique_id of any replied sticker.
#  ─────────────────────────────────────────────────────────────────────────────
#  Developed & maintained by Trinity Mods (@trinityXmods)
#  GitHub   : github.com/Trinity-Mods
#  Source   : github.com/Trinity-Mods/Auto-Filter-Bot
#  Telegram : t.me/trinityXmods
#  🚫 Credit is license-locked — see brand.py. Please keep this header intact.
# ═══════════════════════════════════════════════════════════════════════════════

import logging

from pyrogram import Client, filters

# Module-scoped logger so we never fall back to a bare ``except:`` swallow.
log = logging.getLogger(__name__)


# ───────────────────────────  ⚡ Trinity Mods · @trinityXmods  ───────────────────────────


@Client.on_message(filters.command(["sticker_id"]))
async def reveal_sticker_id(client, message):
    """
    Handle ``/sticker_id``.

    Usage: reply to a sticker with the command. The bot echoes back both the
    ``file_id`` (reusable, bot-scoped) and the ``file_unique_id`` (stable,
    global identifier) of that sticker.

    Behaviour preserved from the original handler, with one fix: we guard the
    presence of ``reply_to_message`` BEFORE touching ``.sticker`` so the command
    no longer raises ``AttributeError`` when invoked without a reply.
    """
    # --- Guard 1: the command must be a reply to something. ---------------
    # The original code went straight for ``message.reply_to_message.sticker``
    # which blew up with AttributeError on a bare ``/sticker_id``. Bail early.
    replied = message.reply_to_message
    if not replied:
        return await message.reply("Reply to a sticker")

    # --- Guard 2: the replied message must actually be a sticker. ---------
    sticker = replied.sticker
    if not sticker:
        return await message.reply("<b>Oops !! Not a sticker file</b>")

    # --- Happy path: surface both identifiers back to the user. ----------
    await message.reply(
        f"**Sticker ID is**  \n `{sticker.file_id}` \n \n "
        f"** Unique ID is ** \n\n`{sticker.file_unique_id}`",
        quote=True,
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  ⚡ Crafted by Trinity Mods (@trinityXmods) · Trinity AutoFilter
#  If this code helped you, keep the credit alive → github.com/Trinity-Mods
#  🚫 This credit is license-locked. See brand.py.
# ═══════════════════════════════════════════════════════════════════════════════
