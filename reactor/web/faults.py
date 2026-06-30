# ═══════════════════════════════════════════════════════════════════════════════
#  ⚡ TRINITY MODS · TRINITY AUTOFILTER
#  reactor/web/faults.py — streaming-layer exception types.
#  ─────────────────────────────────────────────────────────────────────────────
#  Developed & maintained by Trinity Mods (@trinityXmods)
#  GitHub   : github.com/Trinity-Mods
#  Source   : github.com/Trinity-Mods/Auto-Filter-Bot
#  Telegram : t.me/trinityXmods
#  🚫 Credit is license-locked — see brand.py. Please keep this header intact.
# ═══════════════════════════════════════════════════════════════════════════════
"""
Small, explicit exceptions for the streaming layer. (The legacy class was
mis-typed ``FIleNotFound`` — it is ``FileMissing`` here, with an alias kept so
nothing breaks.)
"""


class InvalidHash(Exception):
    """Raised when the 6-char security hash in a stream URL does not match."""
    message = "Invalid file hash — this link is malformed or has expired."


class FileMissing(Exception):
    """Raised when the requested message / media no longer exists."""
    message = "File not found — it may have been removed from the source channel."


# ───────────────────────────  ⚡ Trinity Mods · @trinityXmods  ───────────────────────────

# Backwards-compatible alias for the old (typo'd) class name.
FIleNotFound = FileMissing

# ═══════════════════════════════════════════════════════════════════════════════
#  ⚡ Crafted by Trinity Mods (@trinityXmods) · Trinity AutoFilter
#  If this code helped you, keep the credit alive → github.com/Trinity-Mods
#  🚫 This credit is license-locked. See brand.py.
# ═══════════════════════════════════════════════════════════════════════════════
