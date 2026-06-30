# ═══════════════════════════════════════════════════════════════════════════════
#  ⚡ TRINITY MODS · TRINITY AUTOFILTER
#  reactor/web/pages.py — render the in-browser watch / download HTML pages.
#  ─────────────────────────────────────────────────────────────────────────────
#  Developed & maintained by Trinity Mods (@trinityXmods)
#  GitHub   : github.com/Trinity-Mods
#  Source   : github.com/Trinity-Mods/Auto-Filter-Bot
#  Telegram : t.me/trinityXmods
#  🚫 Credit is license-locked — see brand.py. Please keep this header intact.
# ═══════════════════════════════════════════════════════════════════════════════
"""
Given a BIN_CHANNEL message id + the 6-char access hash, render either the video
player page (``stream.html``) or the generic download page (``download.html``).

NOTE: the legacy renderer made a wasteful HTTP GET to its OWN stream URL just to
read Content-Length for non-video files — which could hang. We already hold the
exact file size in the FileId, so we format it locally and never self-request.
"""

import os
import logging
import urllib.parse

import jinja2

from config import BIN_CHANNEL, URL
from reactor.client import app
from reactor.helpers.sizes import humanbytes
from reactor.stream.media import get_file_ids
from reactor.web.faults import InvalidHash

logger = logging.getLogger("trinity.pages")

_TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")


def _load_template(name: str) -> jinja2.Template:
    """Read and compile a Jinja2 template from reactor/web/templates/."""
    with open(os.path.join(_TEMPLATE_DIR, name), encoding="utf-8") as fh:
        return jinja2.Template(fh.read())


async def render_page(message_id, secure_hash, src=None) -> str:
    """Return the rendered HTML for the watch/download page of a file."""
    file_data = await get_file_ids(app, int(BIN_CHANNEL), int(message_id))

    # The first 6 chars of the unique id act as a lightweight access token.
    if file_data.unique_id[:6] != secure_hash:
        logger.debug("Hash mismatch for message %s", message_id)
        raise InvalidHash

    # Direct stream/download URL for this file.
    src = urllib.parse.urljoin(
        URL,
        f"{message_id}/{urllib.parse.quote_plus(file_data.file_name or 'file')}?hash={secure_hash}",
    )

    media_kind = (file_data.mime_type or "application/octet-stream").split("/")[0].strip()
    file_size = humanbytes(file_data.file_size)          # computed locally — no self-GET
    file_name = (file_data.file_name or "Unknown file").replace("_", " ")

    template_name = "stream.html" if media_kind in ("video", "audio") else "download.html"
    template = _load_template(template_name)

    return template.render(
        file_name=file_name,
        file_url=src,
        file_size=file_size,
        file_unique_id=file_data.unique_id,
        media_kind=media_kind,
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  ⚡ Crafted by Trinity Mods (@trinityXmods) · Trinity AutoFilter
#  ───────────────────────  ⚡ Trinity Mods · @trinityXmods  ───────────────────────
#  If this code helped you, keep the credit alive → github.com/Trinity-Mods
#  🚫 This credit is license-locked. See brand.py.
# ═══════════════════════════════════════════════════════════════════════════════
