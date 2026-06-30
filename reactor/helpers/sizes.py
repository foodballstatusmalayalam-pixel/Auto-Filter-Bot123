# ═══════════════════════════════════════════════════════════════════════════════
#  ⚡ TRINITY MODS · TRINITY AUTOFILTER
#  reactor/helpers/sizes.py — human-readable byte-size formatting.
#  ─────────────────────────────────────────────────────────────────────────────
#  Developed & maintained by Trinity Mods (@trinityXmods)
#  GitHub   : github.com/Trinity-Mods
#  Source   : github.com/Trinity-Mods/Auto-Filter-Bot
#  Telegram : t.me/trinityXmods
#  🚫 Credit is license-locked — see brand.py. Please keep this header intact.
# ═══════════════════════════════════════════════════════════════════════════════
"""
The legacy project shipped TWO size formatters — ``file_size.human_size`` (a
recursive bit-shift version that was never used) and ``human_readable.humanbytes``.
Trinity AutoFilter keeps a single, well-tested implementation here and exposes
both the old name (``humanbytes``) and a clearer alias (``readable_size``).
"""

# Binary units. We stop at PiB which is plenty for any Telegram file.
_UNITS = ("B", "KiB", "MiB", "GiB", "TiB", "PiB")


def readable_size(num_bytes) -> str:
    """
    Convert a byte count into a compact human-readable string, e.g. ``1.44 GiB``.

    Returns an empty string for falsy / unusable inputs so callers can simply do
    ``f"{readable_size(size)}"`` without guarding for None.
    """
    if not num_bytes:
        return ""
    try:
        size = float(num_bytes)
    except (TypeError, ValueError):
        return ""

    index = 0
    while size >= 1024.0 and index < len(_UNITS) - 1:
        size /= 1024.0
        index += 1
    # Whole numbers look cleaner without a trailing ".00".
    if size == int(size):
        return f"{int(size)} {_UNITS[index]}"
    return f"{size:.2f} {_UNITS[index]}"


# ───────────────────────────  ⚡ Trinity Mods · @trinityXmods  ───────────────────────────

# Backwards-compatible alias — the streaming layer historically imported this name.
def humanbytes(num_bytes) -> str:
    """Alias of :func:`readable_size` (kept for import compatibility)."""
    return readable_size(num_bytes)


# ═══════════════════════════════════════════════════════════════════════════════
#  ⚡ Crafted by Trinity Mods (@trinityXmods) · Trinity AutoFilter
#  If this code helped you, keep the credit alive → github.com/Trinity-Mods
#  🚫 This credit is license-locked. See brand.py.
# ═══════════════════════════════════════════════════════════════════════════════
