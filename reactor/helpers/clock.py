# ═══════════════════════════════════════════════════════════════════════════════
#  ⚡ TRINITY MODS · TRINITY AUTOFILTER
#  reactor/helpers/clock.py — turn a number of seconds into a readable duration.
#  ─────────────────────────────────────────────────────────────────────────────
#  Developed & maintained by Trinity Mods (@trinityXmods)
#  GitHub   : github.com/Trinity-Mods
#  Source   : github.com/Trinity-Mods/Auto-Filter-Bot
#  Telegram : t.me/trinityXmods
#  🚫 Credit is license-locked — see brand.py. Please keep this header intact.
# ═══════════════════════════════════════════════════════════════════════════════
"""
Used by the /status endpoint and the restart log to print uptime.

NOTE: the legacy ``time_format.get_readable_time`` had a real bug — it divided by
24 when extracting hours/minutes (it should divide by 60), so any uptime over an
hour was reported nonsensically. This version is correct.
"""


def readable_time(seconds: int) -> str:
    """
    Format a duration in seconds as ``Xd, Xh, Xm, Xs`` (omitting leading zero units).

    Examples
    --------
    >>> readable_time(0)
    '0s'
    >>> readable_time(95)
    '1m, 35s'
    >>> readable_time(90061)
    '1d, 1h, 1m, 1s'
    """
    seconds = int(seconds)
    if seconds <= 0:
        return "0s"

    periods = (
        ("d", 60 * 60 * 24),
        ("h", 60 * 60),
        ("m", 60),
        ("s", 1),
    )
    parts = []
    for suffix, length in periods:
        if seconds >= length:
            value, seconds = divmod(seconds, length)
            parts.append(f"{value}{suffix}")
    return ", ".join(parts)


# ───────────────────────────  ⚡ Trinity Mods · @trinityXmods  ───────────────────────────

# Backwards-compatible alias for the old public name.
def get_readable_time(seconds: int) -> str:
    """Alias of :func:`readable_time` (kept for import compatibility)."""
    return readable_time(seconds)


# ═══════════════════════════════════════════════════════════════════════════════
#  ⚡ Crafted by Trinity Mods (@trinityXmods) · Trinity AutoFilter
#  If this code helped you, keep the credit alive → github.com/Trinity-Mods
#  🚫 This credit is license-locked. See brand.py.
# ═══════════════════════════════════════════════════════════════════════════════
