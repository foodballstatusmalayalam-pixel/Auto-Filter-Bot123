# ═══════════════════════════════════════════════════════════════════════════════
#  ⚡ TRINITY MODS · TRINITY AUTOFILTER
#  reactor/web/endpoints.py — HTTP routes: landing, health, watch & stream.
#  ─────────────────────────────────────────────────────────────────────────────
#  Developed & maintained by Trinity Mods (@trinityXmods)
#  GitHub   : github.com/Trinity-Mods
#  Source   : github.com/Trinity-Mods/Auto-Filter-Bot
#  Telegram : t.me/trinityXmods
#  🚫 Credit is license-locked — see brand.py. Please keep this header intact.
# ═══════════════════════════════════════════════════════════════════════════════
"""
The aiohttp routes for the embedded web server:

  GET /                landing page
  GET /health          plain "OK" (cheap uptime probe for hosting platforms)
  GET /status          JSON: uptime, connected workers, per-worker load, version
  GET /watch/<id>      HTML player / download page (via reactor.web.pages)
  GET /<id>            the actual byte stream (HTTP Range / 206 aware)

Byte-range maths are INCLUSIVE on both ends — getting the ``+1`` wrong truncates
the last byte of every range and breaks video seeking, so it is centralised in
``_range_bounds`` and commented carefully.
"""

import os
import re
import math
import time
import logging
import secrets
import mimetypes

from aiohttp import web
from aiohttp.http_exceptions import BadStatusLine

import config
from reactor import StartTime, __version__
from reactor.client import clients, loads, app
from reactor.stream.streamer import ByteCaster
from reactor.helpers.clock import readable_time
from reactor.web.faults import FileMissing, InvalidHash
from reactor.web.pages import render_page
from version import CODENAME, PRETTY_VERSION

logger = logging.getLogger("trinity.endpoints")

routes = web.RouteTableDef()

_TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")
with open(os.path.join(_TEMPLATE_DIR, "home.html"), encoding="utf-8") as _fh:
    _HOME_HTML = _fh.read()

# One ByteCaster per client, reused across requests.
_caster_cache: dict = {}


def _parse_path(request: web.Request):
    """
    Extract (message_id, secure_hash) from a request path, supporting both
    ``/<hash><id>`` and ``/<id>?hash=<hash>`` forms. (Shared by watch & stream
    so the logic lives in exactly one place.)
    """
    path = request.match_info["path"]
    match = re.search(r"^([a-zA-Z0-9_-]{6})(\d+)$", path)
    if match:
        return int(match.group(2)), match.group(1)
    message_id = int(re.search(r"(\d+)(?:/\S+)?", path).group(1))
    return message_id, request.rel_url.query.get("hash")


# ── landing & health ─────────────────────────────────────────────────────────
@routes.get("/", allow_head=True)
async def home(request: web.Request):
    # Simple token replace (NOT str.format) so CSS curly braces in the template
    # don't need escaping.
    html = _HOME_HTML.replace("{{VERSION}}", PRETTY_VERSION).replace("{{CODENAME}}", CODENAME)
    return web.Response(text=html, content_type="text/html")


@routes.get("/health", allow_head=True)
async def health(request: web.Request):
    """Cheapest possible 200 — used by platform health checks / keep-alive."""
    return web.Response(text="OK")


@routes.get("/status", allow_head=True)
async def status(request: web.Request):
    return web.json_response({
        "status": "running",
        "product": CODENAME,
        "version": __version__,
        "uptime": readable_time(time.time() - StartTime),
        "telegram_bot": "@" + (app.username or "Trinity"),
        "connected_workers": len(clients),
        "loads": {
            f"worker{c + 1}": l
            for c, (_, l) in enumerate(sorted(loads.items(), key=lambda x: x[1], reverse=True))
        },
        "maintainer": "Trinity Mods (@trinityXmods)",
        "repo": "https://github.com/Trinity-Mods/Auto-Filter-Bot",
    })


# ───────────────────────────  ⚡ Trinity Mods · @trinityXmods  ───────────────────────────


# ── watch page & stream ──────────────────────────────────────────────────────
@routes.get(r"/watch/{path:\S+}", allow_head=True)
async def watch(request: web.Request):
    try:
        message_id, secure_hash = _parse_path(request)
        return web.Response(
            text=await render_page(message_id, secure_hash),
            content_type="text/html",
        )
    except InvalidHash as exc:
        raise web.HTTPForbidden(text=exc.message)
    except FileMissing as exc:
        raise web.HTTPNotFound(text=exc.message)
    except (AttributeError, BadStatusLine, ConnectionResetError) as exc:
        logger.warning("watch: client connection issue: %s", exc)
        raise web.HTTPBadRequest(text="Bad request")
    except Exception as exc:
        logger.exception("watch: unexpected error")
        raise web.HTTPInternalServerError(text=str(exc))


@routes.get(r"/{path:\S+}", allow_head=True)
async def stream(request: web.Request):
    try:
        message_id, secure_hash = _parse_path(request)
        return await _media_streamer(request, message_id, secure_hash)
    except InvalidHash as exc:
        raise web.HTTPForbidden(text=exc.message)
    except FileMissing as exc:
        raise web.HTTPNotFound(text=exc.message)
    except (AttributeError, BadStatusLine, ConnectionResetError) as exc:
        logger.warning("stream: client connection issue: %s", exc)
        raise web.HTTPBadRequest(text="Bad request")
    except Exception as exc:
        logger.exception("stream: unexpected error")
        raise web.HTTPInternalServerError(text=str(exc))


def _range_bounds(range_header, http_range, file_size, chunk_size):
    """
    Resolve an HTTP Range request into the byte/chunk arithmetic the streamer
    needs. Ranges are INCLUSIVE on both ends.
    """
    if range_header:
        from_bytes, until_bytes = range_header.replace("bytes=", "").split("-")
        from_bytes = int(from_bytes)
        until_bytes = int(until_bytes) if until_bytes else file_size - 1
    else:
        from_bytes = http_range.start or 0
        until_bytes = (http_range.stop or file_size) - 1

    until_bytes = min(until_bytes, file_size - 1)
    offset = from_bytes - (from_bytes % chunk_size)
    first_part_cut = from_bytes - offset
    last_part_cut = (until_bytes % chunk_size) + 1
    req_length = until_bytes - from_bytes + 1
    part_count = math.ceil(until_bytes / chunk_size) - math.floor(offset / chunk_size)
    return from_bytes, until_bytes, offset, first_part_cut, last_part_cut, req_length, part_count


async def _media_streamer(request: web.Request, message_id: int, secure_hash: str):
    range_header = request.headers.get("Range", 0)

    # Route this request to the least-busy worker client.
    index = min(loads, key=loads.get)
    faster_client = clients[index]
    if config.MULTI_CLIENT:
        logger.info("Worker %s serving %s", index, request.remote)

    caster = _caster_cache.get(faster_client)
    if caster is None:
        caster = ByteCaster(faster_client)
        _caster_cache[faster_client] = caster

    file_id = await caster.get_file_properties(message_id)
    if file_id.unique_id[:6] != secure_hash:
        logger.debug("Invalid hash for message %s", message_id)
        raise InvalidHash

    file_size = file_id.file_size
    chunk_size = 1024 * 1024  # 1 MiB

    (from_bytes, until_bytes, offset, first_part_cut,
     last_part_cut, req_length, part_count) = _range_bounds(
        range_header, request.http_range, file_size, chunk_size
    )

    if (until_bytes >= file_size) or (from_bytes < 0) or (until_bytes < from_bytes):
        return web.Response(
            status=416, body="416: Range not satisfiable",
            headers={"Content-Range": f"bytes */{file_size}"},
        )

    body = caster.yield_file(
        file_id, index, offset, first_part_cut, last_part_cut, part_count, chunk_size
    )

    # Work out a sensible filename + content type for the download.
    mime_type = file_id.mime_type
    file_name = file_id.file_name
    if mime_type:
        if not file_name:
            try:
                file_name = f"{secrets.token_hex(2)}.{mime_type.split('/')[1]}"
            except (IndexError, AttributeError):
                file_name = f"{secrets.token_hex(2)}.unknown"
    else:
        if file_name:
            mime_type = mimetypes.guess_type(file_name)[0] or "application/octet-stream"
        else:
            mime_type = "application/octet-stream"
            file_name = f"{secrets.token_hex(2)}.unknown"

    return web.Response(
        status=206 if range_header else 200,
        body=body,
        headers={
            "Content-Type": mime_type,
            "Content-Range": f"bytes {from_bytes}-{until_bytes}/{file_size}",
            "Content-Length": str(req_length),
            "Content-Disposition": f'attachment; filename="{file_name}"',
            "Accept-Ranges": "bytes",
        },
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  ⚡ Crafted by Trinity Mods (@trinityXmods) · Trinity AutoFilter
#  If this code helped you, keep the credit alive → github.com/Trinity-Mods
#  🚫 This credit is license-locked. See brand.py.
# ═══════════════════════════════════════════════════════════════════════════════
