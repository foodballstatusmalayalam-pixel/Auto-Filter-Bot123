# ═══════════════════════════════════════════════════════════════════════════════
#  ⚡ TRINITY MODS · TRINITY AUTOFILTER — container image.
#  Crafted by Trinity Mods (@trinityXmods) · github.com/Trinity-Mods/Auto-Filter-Bot
# ═══════════════════════════════════════════════════════════════════════════════
FROM python:3.10-slim

# git is needed to install cinemagoer from source.
RUN apt-get update && apt-get upgrade -y \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /trinity-autofilter

COPY requirements.txt .
RUN pip3 install --no-cache-dir -U pip && pip3 install --no-cache-dir -U -r requirements.txt

COPY . .

CMD ["python3", "launcher.py"]
# ⚡ Crafted by Trinity Mods (@trinityXmods). Keep the credit → github.com/Trinity-Mods
