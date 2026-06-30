# ═══════════════════════════════════════════════════════════════════════════════
#  ⚡ TRINITY MODS · TRINITY AUTOFILTER
#  version.py — single source of truth for the project version / build metadata.
#  ─────────────────────────────────────────────────────────────────────────────
#  Developed & maintained by Trinity Mods (@trinityXmods)
#  GitHub   : github.com/Trinity-Mods
#  Source   : github.com/Trinity-Mods/trinity-autofilter
#  Telegram : t.me/trinityXmods
#  🚫 Credit is license-locked — see brand.py. Please keep this header intact.
# ═══════════════════════════════════════════════════════════════════════════════
"""
Why this file exists
--------------------
The legacy bot tracked its version in three different places (``Script.py`` said
``v2.7.1``, the *About* text said ``v4.2`` and the streaming engine said ``2.0.0``).
That drift is exactly the kind of thing that makes a project look unmaintained.

Trinity AutoFilter keeps ONE version here and everybody imports it, so the number
shown on ``/about``, the streaming landing page, the restart log and the HTTP
``/status`` endpoint can never disagree again.
"""

# Human-facing product identity ------------------------------------------------
CODENAME = "Trinity AutoFilter"          # the product name shown to users
ENGINE   = "Trinity Filter Engine"       # the streaming/runtime engine name

# Semantic version of the whole project. Bump this on every release.
VERSION  = "3.0.0"

# A short, friendly build tag appended after the version in logs/menus.
BUILD    = "Aurora"                       # release codename for 3.0.0
CHANNEL  = "stable"                       # stable | beta | dev

# Pre-computed "pretty" string so callers don't re-format it everywhere.
PRETTY_VERSION = f"v{VERSION} ({BUILD}) [{CHANNEL}]"

# ───────────────────────────  ⚡ Trinity Mods · @trinityXmods  ───────────────────────────

# Attribution constants (kept in sync with brand.py — the license-locked source).
AUTHOR = "Trinity Mods (@trinityXmods)"
REPO   = "https://github.com/Trinity-Mods/Auto-Filter-Bot"


def banner() -> str:
    """Return a one-line version banner used by logs and the web status page."""
    return f"{CODENAME} {PRETTY_VERSION} · by {AUTHOR}"


# ═══════════════════════════════════════════════════════════════════════════════
#  ⚡ Crafted by Trinity Mods (@trinityXmods) · Trinity AutoFilter
#  If this code helped you, keep the credit alive → github.com/Trinity-Mods
#  🚫 This credit is license-locked. See brand.py.
# ═══════════════════════════════════════════════════════════════════════════════
