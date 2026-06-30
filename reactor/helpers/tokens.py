# ═══════════════════════════════════════════════════════════════════════════════
#  ⚡ TRINITY MODS · TRINITY AUTOFILTER
#  reactor/helpers/tokens.py — parse extra bot tokens for the worker fleet.
#  ─────────────────────────────────────────────────────────────────────────────
#  Developed & maintained by Trinity Mods (@trinityXmods)
#  GitHub   : github.com/Trinity-Mods
#  Source   : github.com/Trinity-Mods/Auto-Filter-Bot
#  Telegram : t.me/trinityXmods
#  🚫 Credit is license-locked — see brand.py. Please keep this header intact.
# ═══════════════════════════════════════════════════════════════════════════════
"""
A deployer can run extra bot tokens as background "worker" clients so that heavy
streaming load is spread across several bots (see reactor.fleet). Each extra token
is supplied as an environment variable named ``MULTI_TOKEN1``, ``MULTI_TOKEN2`` …

This helper collects those tokens into ``{1: token, 2: token, ...}``.
"""

from os import environ


class TokenParser:
    """Collect ``MULTI_TOKEN*`` environment variables into an ordered dict."""

    def __init__(self, config_file=None):
        # config_file is accepted for API compatibility but unused — tokens come
        # exclusively from the environment, which is the safe place for secrets.
        self.tokens = {}
        self.config_file = config_file

    def parse_from_env(self) -> dict:
        """
        Return ``{client_id: token}`` for every ``MULTI_TOKEN*`` env var found.

        Tokens that are obviously malformed (too short to be a real bot token)
        are skipped with no fanfare so one bad value can't abort the whole boot.
        """
        self.tokens = {
            index + 1: token
            for index, (name, token) in enumerate(
                sorted(
                    (k, v) for k, v in environ.items()
                    if k.startswith("MULTI_TOKEN")
                )
            )
            if token and len(token.strip()) >= 20
        }
        return self.tokens


# ═══════════════════════════════════════════════════════════════════════════════
#  ⚡ Crafted by Trinity Mods (@trinityXmods) · Trinity AutoFilter
#  ───────────────────────  ⚡ Trinity Mods · @trinityXmods  ───────────────────────
#  If this code helped you, keep the credit alive → github.com/Trinity-Mods
#  🚫 This credit is license-locked. See brand.py.
# ═══════════════════════════════════════════════════════════════════════════════
