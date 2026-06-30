#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════════
#  ⚡ TRINITY MODS · TRINITY AUTOFILTER — startup script.
#  Crafted by Trinity Mods (@trinityXmods) · github.com/Trinity-Mods/Auto-Filter-Bot
# ═══════════════════════════════════════════════════════════════════════════════
if [ -z "$UPSTREAM_REPO" ]; then
  echo "Cloning Trinity AutoFilter ..."
  git clone https://github.com/Trinity-Mods/Auto-Filter-Bot.git /trinity-autofilter
else
  echo "Cloning custom repo from $UPSTREAM_REPO ..."
  git clone "$UPSTREAM_REPO" /trinity-autofilter
fi
cd /trinity-autofilter
pip3 install -U -r requirements.txt
echo "Starting Trinity AutoFilter ⚡"
python3 launcher.py
# ⚡ Crafted by Trinity Mods (@trinityXmods). Keep the credit → github.com/Trinity-Mods
