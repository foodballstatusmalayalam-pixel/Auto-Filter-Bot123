# ═══════════════════════════════════════════════════════════════════════════════
#  ⚡ TRINITY MODS · TRINITY AUTOFILTER
#  phrases.py — every user-facing string, in one place (was Script.py).
#  ─────────────────────────────────────────────────────────────────────────────
#  Developed & maintained by Trinity Mods (@trinityXmods)
#  GitHub   : github.com/Trinity-Mods
#  Source   : github.com/Trinity-Mods/Auto-Filter-Bot
#  Telegram : t.me/trinityXmods
#  🚫 Credit is license-locked — see brand.py. Please keep this header intact.
# ═══════════════════════════════════════════════════════════════════════════════
"""
All bot copy lives here so wording/branding changes never touch handler logic.

Conventions kept stable for the handlers that consume these strings:
  • Attribute NAMES are unchanged from the legacy module (so imports keep working).
  • ``{}`` positional and ``{named}`` placeholders are preserved EXACTLY — the
    handlers ``.format()`` these, so the placeholder count/order must not change.

Improvements: the version is pulled from version.py (no more v2.7.1/v4.2 drift),
and hardcoded per-deployer values (UPI id, channel handles) were replaced with
neutral, editable text.
"""

from version import PRETTY_VERSION, CODENAME


class Phrases:
    """Namespace of all user-facing strings."""

    # ── start / help ─────────────────────────────────────────────────────────
    START_TXT = """┏━━ ʜᴇʏ ᴛʜᴇʀᴇ 🥰 ━━┓
┃ <b>{}</b>
┃
┃ <b>
🍿 ɪ'ᴍ ʏᴏᴜʀ ᴘᴇʀsᴏɴᴀʟ ᴍᴏᴠɪᴇ & ᴡᴇʙ-sᴇʀɪᴇs ꜰɪɴᴅᴇʀ\n
🧞 ʟᴀᴛᴇsᴛ ʀᴇʟᴇᴀsᴇs, ʀɪɢʜᴛ ɪɴ ʏᴏᴜʀ ɢʀᴏᴜᴘ ᴏʀ ᴅᴍ!
</b>
┃
┃ <b>
🔓 ᴜɴʟᴏᴄᴋ ᴍʏ ꜰᴜʟʟ ᴘᴏᴡᴇʀ:\n
➕ ᴀᴅᴅ ᴍᴇ ᴛᴏ ʏᴏᴜʀ ɢʀᴏᴜᴘ(s)\n
🔐 <u>ᴍᴀᴋᴇ ᴍᴇ ᴀᴅᴍɪɴ ᴡɪᴛʜ ᴀʟʟ ᴘʀɪᴠɪʟᴇɢᴇs</u>
</b>
┗━━━━━━━━━━━━━━━━━━━━⚡
"""

    HELP_TXT = """┏━━━━━━━━━━━━━━━━━━━━━━━━━━⚙️
┃   <b><i>ʜᴇʏ {}</i></b> 🙌
┣━━━━━━━━━━━━━━━━━━━━━━━━━━💬
┃ <b>
ᴛᴏ ᴋᴇᴇᴘ ᴛʜɪɴɢs ᴛɪᴅʏ, ᴛʜᴇ ᴄᴏᴍᴍᴀɴᴅs ᴀʀᴇ ɢʀᴏᴜᴘᴇᴅ:\n
🔸 ꜰᴏʀ ɢʀᴏᴜᴘ ᴀᴅᴍɪɴs\n
🔹 ꜰᴏʀ ᴇᴠᴇʀʏᴅᴀʏ ᴜsᴇʀs
</b>
┗━━━━━━━━━━━━━━━━━━━━━━━━━━🧩
"""

    # Words stripped from result filenames (piracy tags / junk channels / noise).
    BLACKLIST = [
        'tamilblaster', 'filmyzilla', 'streamershub', 'xyz', 'cine', 'www', 'http', 'https',
        'cloudsmoviesstore', 'moviez2you', 'bkp', 'cinema', 'filmy', 'flix', 'cutemoviez',
        '4u', 'hub', 'movies', 'otthd', 'telegram', 'hoichoihok', '@', ']', '[', 'missqueenbotx',
        'films', 'join', 'club', 'apd', 'F-Press', 'GDTOT', 'mkv', 'NETFLIX_OFFICIAL',
        'backup', 'primeroom', 'theprofffesorr', 'premium', 'vip', '4wap', 'toonworld4all', 'mlwbd',
        'Telegram@alpacinodump', 'bollywood', 'AllNewEnglishMovie', '7MovieRulz', '1TamilMV',
        'Bazar', '_Corner20', 'CornersOfficial', 'support', 'iMediaShare', 'Uᴘʟᴏᴀᴅᴇᴅ', 'Bʏ', 'PFM',
        'alpacinodump', 'Us', 'boxoffice', 'Links', 'Linkz', 'Villa', 'Original', 'bob',
        'Files1', 'MW', 'LinkZ', '}', '{',
    ]

    # ── refer & earn ─────────────────────────────────────────────────────────
    REFFER_TXT = """┏━━━━━━━━━━━━━━━━━━━━━━━━━━🎁
┃   <b><i>ʀᴇꜰᴇʀ & ᴇᴀʀɴ ᴘʀᴇᴍɪᴜᴍ 🎉</i></b>
┣━━━━━━━━━━━━━━━━━━━━━━━━━━💸
┃ <b>
sʜᴀʀᴇ ᴛʜɪs ʙᴏᴛ ᴡɪᴛʜ ꜰʀɪᴇɴᴅs & ꜰᴀᴍɪʟʏ\n
ᴀɴᴅ ᴄᴏʟʟᴇᴄᴛ <u>ᴘᴏɪɴᴛs</u> ᴛᴏ ᴜɴʟᴏᴄᴋ ꜰʀᴇᴇ ᴘʀᴇᴍɪᴜᴍ! 🏆

🎀 <i>ᴇᴀᴄʜ sᴜᴄᴄᴇssꜰᴜʟ ʀᴇꜰᴇʀ ᴇᴀʀɴs ʏᴏᴜ ᴘᴏɪɴᴛs.</i>\n
🔗 ʏᴏᴜʀ ʀᴇꜰᴇʀʀᴀʟ ʟɪɴᴋ:\n
https://telegram.me/{}?start=reff_{}

━━━━━━━━━━━━━━━━━━━━━━━━━━
<u>💫 ᴘʀᴇᴍɪᴜᴍ ᴘᴇʀᴋs 💫</u>:\n
○ sᴇᴀʀᴄʜ ᴍᴏᴠɪᴇs ɪɴsɪᴅᴇ ᴛʜᴇ ʙᴏᴛ\n
○ ɴᴏ ꜰɪʟᴇ-sɪᴢᴇ ʟɪᴍɪᴛs\n
○ ᴜɴʟɪᴍɪᴛᴇᴅ ꜰɪʟᴇ ᴀᴄᴄᴇss\n
○ ɴᴏ "sᴇɴᴅ ᴀʟʟ" ʟɪᴍɪᴛs\n
○ ɴᴏ ʟɪɴᴋs ᴛᴏ ᴏᴘᴇɴ\n
○ ɴᴏ ᴠᴇʀɪꜰɪᴄᴀᴛɪᴏɴ\n
○ ᴅɪʀᴇᴄᴛ ꜰɪʟᴇ ᴅᴇʟɪᴠᴇʀʏ\n
○ ᴀᴅ-ꜰʀᴇᴇ ᴇxᴘᴇʀɪᴇɴᴄᴇ\n
○ ᴜɴʟɪᴍɪᴛᴇᴅ ᴍᴏᴠɪᴇs & sᴇʀɪᴇs
━━━━━━━━━━━━━━━━━━━━━━━━━━
💳 ʙᴜʏ ᴀ ᴘʀᴇᴍɪᴜᴍ ᴘʟᴀɴ: /plans
</b>
┗━━━━━━━━━━━━━━━━━━━━━━━━━━✨
"""

    # ── force-sub ────────────────────────────────────────────────────────────
    FSUB_TXT = """┏━━━━━━━━━━━━━━━━━━━━━━━━━━📢
┃ <b><i>👀 ᴏɴᴇ sᴍᴀʟʟ ꜰᴀᴠᴏᴜʀ…</i></b>
┣━━━━━━━━━━━━━━━━━━━━━━━━━━💫
┃ <i><b>
ʙᴇꜰᴏʀᴇ ʏᴏᴜ ɢʀᴀʙ ʏᴏᴜʀ ᴍᴏᴠɪᴇ ᴏʀ sᴇʀɪᴇs,\n
ᴘʟᴇᴀsᴇ sᴜᴘᴘᴏʀᴛ ᴜs ʙʏ ᴊᴏɪɴɪɴɢ ᴏᴜʀ ᴄʜᴀɴɴᴇʟ. 🙏\n\n
ᴛᴀᴘ <b>'ᴊᴏɪɴ ɴᴏᴡ'</b> ʙᴇʟᴏᴡ 👇
</b></i>
┗━━━━━━━━━━━━━━━━━━━━━━━━━━🎀
"""

    # ── verification (3 tiers) — names kept exactly, incl. legacy "THIRDT" ────
    VERIFICATION_TEXT = """┏━━━ 🔐 ᴠᴇʀɪꜰɪᴄᴀᴛɪᴏɴ ʀᴇǫᴜɪʀᴇᴅ ━━━┓
┃ <b>ʜᴇʏ {},</b> 🕵️
┃
┃ <b><u>❗ ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ᴠᴇʀɪꜰɪᴇᴅ ᴛᴏᴅᴀʏ</u></b>
┃
┃ ᴛᴀᴘ "<b>ᴠᴇʀɪꜰʏ</b>" ᴛᴏ ᴜɴʟᴏᴄᴋ ᴀᴄᴄᴇss
┃ ᴜɴᴛɪʟ ᴛʜᴇ ɴᴇxᴛ ᴄʏᴄʟᴇ 🔓
┃
┃ <b>🧾 #ᴠᴇʀɪꜰɪᴄᴀᴛɪᴏɴ: 1/3</b>
┃
┃ <b>💡 ᴛɪᴘ:</b> sᴋɪᴘ ᴅᴀɪʟʏ ᴄʜᴇᴄᴋs
┃ ᴡɪᴛʜ ᴘʀᴇᴍɪᴜᴍ ⏳  —  /plans
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛
"""

    SECOND_VERIFICATION_TEXT = """<b>👋 ʜᴇʏ {},</b>\n
<u><b>🚫 ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ᴠᴇʀɪꜰɪᴇᴅ ᴛᴏᴅᴀʏ</b></u>\n
➤ ᴛᴀᴘ ᴛʜᴇ <b>"ᴠᴇʀɪꜰʏ"</b> ʟɪɴᴋ ʙᴇʟᴏᴡ ᴛᴏ ᴜɴʟᴏᴄᴋ ᴀᴄᴄᴇss\n
ᴜɴᴛɪʟ ᴛʜᴇ ɴᴇxᴛ ᴠᴇʀɪꜰɪᴄᴀᴛɪᴏɴ 🔋\n\n
<b>📌 sᴛᴇᴘ: 2/3</b>\n\n
<b>💡 ᴛɪʀᴇᴅ ᴏꜰ ᴠᴇʀɪꜰʏɪɴɢ?</b>\n
➤ ɢᴇᴛ ɪɴsᴛᴀɴᴛ, ʀᴇsᴛʀɪᴄᴛɪᴏɴ-ꜰʀᴇᴇ ᴀᴄᴄᴇss ✨\n\n
💳 <b>ᴜᴘɢʀᴀᴅᴇ:</b> sᴇɴᴅ <code>/plans</code>
"""

    THIRDT_VERIFICATION_TEXT = """<b> ʜᴇʏ {}

📌 <u>ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ᴠᴇʀɪꜰɪᴇᴅ ᴛᴏᴅᴀʏ. ᴛᴀᴘ ᴛʜᴇ ᴠᴇʀɪꜰʏ ʟɪɴᴋ ꜰᴏʀ ᴜɴʟɪᴍɪᴛᴇᴅ ᴀᴄᴄᴇss ᴛʜᴇ ɴᴇxᴛ ꜰᴜʟʟ ᴅᴀʏ.</u>

#ᴠᴇʀɪꜰɪᴄᴀᴛɪᴏɴ:- 3/3

ᴡᴀɴᴛ ᴅɪʀᴇᴄᴛ ꜰɪʟᴇs, ɴᴏ ᴠᴇʀɪꜰɪᴄᴀᴛɪᴏɴ? ɢʀᴀʙ ᴀ sᴜʙsᴄʀɪᴘᴛɪᴏɴ. </b>"""

    VERIFY_COMPLETE_TEXT = """<b>ʜᴇʏ {},

ʏᴏᴜ ᴄᴏᴍᴘʟᴇᴛᴇᴅ ᴛʜᴇ 1sᴛ ᴠᴇʀɪꜰɪᴄᴀᴛɪᴏɴ ✅

ʏᴏᴜ ɴᴏᴡ ʜᴀᴠᴇ ᴀᴄᴄᴇss ᴜɴᴛɪʟ ᴛʜᴇ ɴᴇxᴛ ᴠᴇʀɪꜰɪᴄᴀᴛɪᴏɴ.

ᴡᴀɴᴛ ᴅɪʀᴇᴄᴛ ꜰɪʟᴇs ᴡɪᴛʜ ɴᴏ ᴠᴇʀɪꜰɪᴄᴀᴛɪᴏɴ? sᴇɴᴅ /plans</b>"""

    SECOND_COMPLETE_TEXT = """<b>ʜᴇʏ {},

ʏᴏᴜ ᴄᴏᴍᴘʟᴇᴛᴇᴅ ᴛʜᴇ sᴇᴄᴏɴᴅ ᴠᴇʀɪꜰɪᴄᴀᴛɪᴏɴ ✅

ʏᴏᴜ ɴᴏᴡ ʜᴀᴠᴇ ᴀᴄᴄᴇss ᴜɴᴛɪʟ ᴛʜᴇ ɴᴇxᴛ ᴠᴇʀɪꜰɪᴄᴀᴛɪᴏɴ.

ᴡᴀɴᴛ ᴅɪʀᴇᴄᴛ ꜰɪʟᴇs? sᴇɴᴅ /plans</b>"""

    THIRDT_COMPLETE_TEXT = """<b> ʜᴇʏ {},

ʏᴏᴜ ᴄᴏᴍᴘʟᴇᴛᴇᴅ ᴛʜᴇ 3ʀᴅ ᴠᴇʀɪꜰɪᴄᴀᴛɪᴏɴ ✅

ʏᴏᴜ ɴᴏᴡ ʜᴀᴠᴇ ᴀᴄᴄᴇss ꜰᴏʀ ᴛʜᴇ ɴᴇxᴛ ꜰᴜʟʟ ᴅᴀʏ. </b>"""

    VERIFIED_LOG_TEXT = """<b><u>☄ ᴜsᴇʀ ᴠᴇʀɪꜰɪᴇᴅ sᴜᴄᴄᴇssꜰᴜʟʟʏ ☄</u>

⚡️ ɴᴀᴍᴇ:- {} [ <code>{}</code> ]
📆 ᴅᴀᴛᴇ:- <code>{} </code></b>

#verified_{}_completed"""

    # ── limits ───────────────────────────────────────────────────────────────
    FILE_LIMIT = """
📁 ʏᴏᴜʀ ᴅᴀɪʟʏ ꜰɪʟᴇ ʟɪᴍɪᴛ ɪs ʀᴇᴀᴄʜᴇᴅ

ᴡᴀɴᴛ ᴜɴʟɪᴍɪᴛᴇᴅ ꜰɪʟᴇs? ɢʀᴀʙ ᴘʀᴇᴍɪᴜᴍ ✨

💲 ᴘʟᴀɴs: /plans

⌚ ʀᴇsᴇᴛ ᴛɪᴍᴇ = 11:59 ᴘᴍ
"""

    BUTTON_LIMIT = """
🎡 'sᴇɴᴅ ᴀʟʟ' ʙᴜᴛᴛᴏɴ ʟɪᴍɪᴛ ʀᴇᴀᴄʜᴇᴅ

ᴡᴀɴᴛ ɪᴛ ᴜɴʟɪᴍɪᴛᴇᴅ? ɢʀᴀʙ ᴘʀᴇᴍɪᴜᴍ

💲 ᴘʟᴀɴs: /plans

⌚ ʀᴇsᴇᴛ ᴛɪᴍᴇ = 11:59 ᴘᴍ
"""

    # ── about / features / status — build status pulled from version.py ──────
    ABOUT_TXT = f"""<b>
‣ ᴍʏ ɴᴀᴍᴇ : <a href=https://t.me/{{}}>{{}}</a>
‣ ᴄʀᴇᴀᴛᴏʀ : <a href=https://t.me/trinityXmods>ᴛʀɪɴɪᴛʏ ᴍᴏᴅs</a>
‣ ʟɪʙʀᴀʀʏ : <a href=https://docs.pyrogram.org/>ᴘʏʀᴏꜰᴏʀᴋ</a>
‣ ʟᴀɴɢᴜᴀɢᴇ : <a href=https://www.python.org/>ᴘʏᴛʜᴏɴ</a>
‣ ᴅᴀᴛᴀʙᴀsᴇ : <a href=https://www.mongodb.com/>ᴍᴏɴɢᴏ ᴅʙ</a>
‣ ᴘʀᴏᴊᴇᴄᴛ : {CODENAME}
‣ ʙᴜɪʟᴅ : {PRETTY_VERSION}</b>"""

    FEATURES = """✨ sᴘᴇᴄɪᴀʟ ꜰᴇᴀᴛᴜʀᴇs ɪɴ ᴛʜɪs ʙᴏᴛ ✨\n\n○ /font - ʀᴇsᴛʏʟᴇ ᴀɴʏ ᴛᴇxᴛ. ᴇxᴀᴍᴘʟᴇ: <code>/font I am smart</code>\n\n○ /telegraph - ᴄʀᴇᴀᴛᴇ ᴀ sʜᴀʀᴇᴀʙʟᴇ ʟɪɴᴋ ꜰᴏʀ ᴀɴ ɪᴍᴀɢᴇ/ᴠɪᴅᴇᴏ ᴜɴᴅᴇʀ 5 ᴍʙ.\n\nᴍᴏʀᴇ ꜰᴇᴀᴛᴜʀᴇs ᴀʀʀɪᴠɪɴɢ ᴡɪᴛʜ ꜰᴜᴛᴜʀᴇ ᴜᴘᴅᴀᴛᴇs!"""

    STATUS_TXT = """<b>
‣ ᴛᴏᴛᴀʟ ꜰɪʟᴇs : <code>{}</code>
‣ ᴛᴏᴛᴀʟ ᴜsᴇʀs : <code>{}</code>
‣ ᴛᴏᴛᴀʟ ɢʀᴏᴜᴘs : <code>{}</code>
‣ ᴜsᴇᴅ sᴛᴏʀᴀɢᴇ : <code>{}</code>
‣ ꜰʀᴇᴇ sᴛᴏʀᴀɢᴇ : <code>{}</code>
</b>"""

    # ── logging templates ────────────────────────────────────────────────────
    LOG_TEXT_G = """#NewGroup
BOT {}
Gʀᴏᴜᴘ = {}(<code>{}</code>)
Tᴏᴛᴀʟ Mᴇᴍʙᴇʀs = <code>{}</code>
Aᴅᴅᴇᴅ Bʏ - {}"""

    LOG_TEXT_P = """#NewUser
ID - <code>{}</code>
Nᴀᴍᴇ - {}
Bᴏᴛ {}"""

    ALRT_TXT = """{},
ᴛʜɪs ɪsɴ'ᴛ ʏᴏᴜʀ ʀᴇǫᴜᴇsᴛ —
sᴇɴᴅ ʏᴏᴜʀ ᴏᴡɴ sᴇᴀʀᴄʜ 😘"""

    # ── search feedback ──────────────────────────────────────────────────────
    CUDNT_FND = """<blockquote>ᴏʜ ɴᴏ! 😔</blockquote>

<i>ɪ ᴄᴏᴜʟᴅɴ'ᴛ ꜰɪɴᴅ ᴀɴʏᴛʜɪɴɢ ꜰᴏʀ '{}'
ᴅɪᴅ ʏᴏᴜ ᴍᴇᴀɴ ᴏɴᴇ ᴏꜰ ᴛʜᴇsᴇ?</i>"""

    I_CUDNT = """<i>sᴏʀʀʏ, ɴᴏ ꜰɪʟᴇs ꜰᴏᴜɴᴅ ꜰᴏʀ {} 😕

ᴄʜᴇᴄᴋ ᴛʜᴇ sᴘᴇʟʟɪɴɢ ᴏɴ ɢᴏᴏɢʟᴇ ᴀɴᴅ ᴛʀʏ ᴀɢᴀɪɴ 😃

sᴇᴀʀᴄʜ 🔍 ꜰᴏʀᴍᴀᴛ 👇

Pushpa 2021
Money heist S01E01

ᴊᴜsᴛ ᴛʜᴇ ɴᴀᴍᴇ (ᴀɴᴅ ʏᴇᴀʀ) — ɴᴏ ᴇxᴛʀᴀ ᴡᴏʀᴅs</i>"""

    I_CUD_NT = """<blockquote>ᴏʜ ɴᴏ! 😔</blockquote>

ɪ ᴄᴏᴜʟᴅɴ'ᴛ ꜰɪɴᴅ ᴀɴʏ ᴍᴏᴠɪᴇ ᴏʀ sᴇʀɪᴇs ꜰᴏʀ <i>'{}'</i>.
ᴘʟᴇᴀsᴇ ᴄʜᴇᴄᴋ ᴛʜᴇ sᴘᴇʟʟɪɴɢ ᴏɴ ɢᴏᴏɢʟᴇ ᴏʀ ɪᴍᴅʙ ⌛"""

    MVE_NT_FND = """<i>ɴᴏ ᴍᴏᴠɪᴇ ᴏʀ sᴇʀɪᴇs ꜰᴏᴜɴᴅ ᴡɪᴛʜ ᴛʜᴀᴛ ɴᴀᴍᴇ 🙅,

ʏᴏᴜʀ ʀᴇǫᴜᴇsᴛ ʜᴀs ʙᴇᴇɴ ꜰᴏʀᴡᴀʀᴅᴇᴅ ᴛᴏ ᴛʜᴇ ᴀᴅᴍɪɴ</i>..."""

    TOP_ALRT_MSG = """sᴇᴀʀᴄʜɪɴɢ…"""

    MELCOW_ENG = """<b>Hᴇʟʟᴏ {} 😍!\n\nWᴇʟᴄᴏᴍᴇ ᴛᴏ {} ❤️</b>"""

    NORSLTS = """
#NoResult
★ Gʀᴏᴜᴘ Nᴀᴍᴇ <b>: {}</b>(<code>{}</code>)
★ Tᴏᴛᴀʟ Usᴇʀs {}
★ Bᴏᴛ {}
★ Usᴇʀ <b>: {}</b>

★ Mᴇssᴀɢᴇ <code>{}</code>"""

    PMNORSLTS = """
#Pm_NoResult
★ Bᴏᴛ {}
★ Usᴇʀ <b>: {}</b>

★ Mᴇssᴀɢᴇ <code>{}</code>"""

    # ── file caption (named placeholders) ────────────────────────────────────
    CAPTION = """
<b>📂 ꜰɪʟᴇ ɴᴀᴍᴇ :</b> {file_name}
<b>🎡 ꜰɪʟᴇ sɪᴢᴇ :</b> {file_size}

<b>╔════ ᴊᴏɪɴ ᴡɪᴛʜ ᴜs ════╗
▫️ ᴀᴅᴅ ʏᴏᴜʀ ᴄʜᴀɴɴᴇʟ ʟɪɴᴋ ʜᴇʀᴇ ▫️
╚════ ᴊᴏɪɴ ᴡɪᴛʜ ᴜs ════╝</b>

💡 <u><b>ᴘʀᴏ ᴛɪᴘ:</b></u> <i>ꜰᴏʀᴡᴀʀᴅ ᴛʜᴇ ꜰɪʟᴇ ᴛᴏ ʏᴏᴜʀ sᴀᴠᴇᴅ ᴍᴇssᴀɢᴇs, ᴅᴏᴡɴʟᴏᴀᴅ ᴛʜᴇʀᴇ, ᴀɴᴅ ᴜsᴇ ᴠʟᴄ ᴛᴏ sᴡɪᴛᴄʜ ʟᴀɴɢᴜᴀɢᴇs & sᴜʙᴛɪᴛʟᴇs!</i>"""

    IMDB_TEMPLATE_TXT = """
<b>
🏷 Title: <a href={url}>{title}</a>
🎭 Genres: {genres}
📆 Year: <a href={url}/releaseinfo>{year}</a>
🌟 Rating: <a href={url}/ratings>{rating}</a> / 10</b>

⚡ ᴘᴏᴡᴇʀᴇᴅ ʙʏ Trinity AutoFilter"""

    CHANNELS = """
<b>ᴊᴏɪɴ ᴏᴜʀ ᴄʜᴀɴɴᴇʟs ꜰᴏʀ ᴜᴘᴅᴀᴛᴇs ᴏɴ ᴛʜᴇ ʟᴀᴛᴇsᴛ ᴍᴏᴠɪᴇs, sᴇʀɪᴇs ᴀɴᴅ ᴛʜᴇ ʙᴏᴛ!</b>"""

    DISCLAIMER_TXT = """
ᴘʟᴇᴀsᴇ ʀᴇᴠɪᴇᴡ ᴛʜᴇ ꜰᴏʟʟᴏᴡɪɴɢ ʙᴇꜰᴏʀᴇ ᴜsɪɴɢ ᴛʜɪs ʙᴏᴛ.

⚠️ ᴅɪsᴄʟᴀɪᴍᴇʀ — (ʀᴇᴘʟᴀᴄᴇ ᴡɪᴛʜ ʏᴏᴜʀ ᴏᴡɴ ᴅɪsᴄʟᴀɪᴍᴇʀ ʟɪɴᴋ)

⌛ ʙʏ ᴘʀᴏᴄᴇᴇᴅɪɴɢ, ʏᴏᴜ ᴀɢʀᴇᴇ ᴛᴏ ᴛʜᴇ ᴅɪsᴄʟᴀɪᴍᴇʀ sᴇᴛ ʙʏ ᴛʜᴇ ᴀᴅᴍɪɴs.

🌿 ᴍᴀɪɴᴛᴀɪɴᴇᴅ ʙʏ : <a href=https://t.me/trinityXmods>ᴛʀɪɴɪᴛʏ ᴍᴏᴅs</a>"""

    # ── command lists ────────────────────────────────────────────────────────
    USERS_TXT = """
👇 ᴄᴏᴍᴍᴀɴᴅs ꜰᴏʀ ᴜsᴇʀs 👇

• /id - ɢᴇᴛ ᴀ ᴜsᴇʀ's ɪᴅ.
• /info - ɢᴇᴛ ɪɴꜰᴏ ᴀʙᴏᴜᴛ ᴀ ᴜsᴇʀ.
• /imdb - ꜰɪʟᴍ ɪɴꜰᴏ ꜰʀᴏᴍ ɪᴍᴅʙ.
• /font - ʀᴇsᴛʏʟᴇ ᴀ ᴛᴇxᴛ.
• /search - ꜰɪʟᴍ ɪɴꜰᴏ ꜰʀᴏᴍ ᴠᴀʀɪᴏᴜs sᴏᴜʀᴄᴇs.
• /request - sᴇɴᴅ ᴀ ᴍᴏᴠɪᴇ/sᴇʀɪᴇs ʀᴇǫᴜᴇsᴛ.
• /plans - ᴠɪᴇᴡ ᴘʀᴇᴍɪᴜᴍ ᴘʟᴀɴs.
• /myplan - ᴄʜᴇᴄᴋ ʏᴏᴜʀ ᴘʟᴀɴ.
• /redeem - ʀᴇᴅᴇᴇᴍ ᴀ ᴘʀᴇᴍɪᴜᴍ ᴄᴏᴅᴇ.
• /sticker_id - ɢᴇᴛ ᴀ sᴛɪᴄᴋᴇʀ ɪᴅ.
• /trending - ᴛᴏᴘ sᴇᴀʀᴄʜᴇᴅ ᴛɪᴛʟᴇs.
• /ping - ᴄʜᴇᴄᴋ ʙᴏᴛ ʟᴀᴛᴇɴᴄʏ.
"""

    GROUP_TXT = """
👇 ᴄᴏᴍᴍᴀɴᴅs ꜰᴏʀ ɢʀᴏᴜᴘ ᴀᴅᴍɪɴs 👇

• /connect - ᴄᴏɴɴᴇᴄᴛ ᴀ ᴄʜᴀᴛ ᴛᴏ ʏᴏᴜʀ ᴘᴍ.
• /disconnect - ᴅɪsᴄᴏɴɴᴇᴄᴛ ᴀ ᴄʜᴀᴛ.
• /set_verify - sᴇᴛ 1sᴛ ᴠᴇʀɪꜰʏ ᴜʀʟ.
• /set_verify2 - sᴇᴛ 2ɴᴅ ᴠᴇʀɪꜰʏ ᴜʀʟ.
• /set_verify3 - sᴇᴛ 3ʀᴅ ᴠᴇʀɪꜰʏ ᴜʀʟ.
• /verify_gap - sᴇᴛ 2ɴᴅ ᴠᴇʀɪꜰʏ ɢᴀᴘ.
• /verify_gap2 - sᴇᴛ 3ʀᴅ ᴠᴇʀɪꜰʏ ɢᴀᴘ.
• /set_tutorial - sᴇᴛ 1sᴛ ᴛᴜᴛᴏʀɪᴀʟ ʟɪɴᴋ.
• /set_tutorial_2 - sᴇᴛ 2ɴᴅ ᴛᴜᴛᴏʀɪᴀʟ ʟɪɴᴋ.
• /set_tutorial_3 - sᴇᴛ 3ʀᴅ ᴛᴜᴛᴏʀɪᴀʟ ʟɪɴᴋ.
• /set_caption - ᴄʜᴀɴɢᴇ ꜰɪʟᴇ ᴄᴀᴘᴛɪᴏɴ.
• /set_fsub - sᴇᴛ ꜰᴏʀᴄᴇ-sᴜʙ ᴄʜᴀɴɴᴇʟ.
• /remove_fsub - ʀᴇᴍᴏᴠᴇ ꜰᴏʀᴄᴇ-sᴜʙ.
• /set_log - sᴇᴛ ʟᴏɢ ᴄʜᴀɴɴᴇʟ.
• /set_file_limit - sᴇᴛ ᴅᴀɪʟʏ ꜰɪʟᴇ ʟɪᴍɪᴛ.
• /set_send_limit - sᴇᴛ ᴅᴀɪʟʏ sᴇɴᴅ-ᴀʟʟ ʟɪᴍɪᴛ.
• /set_template - ᴄʜᴀɴɢᴇ ɪᴍᴅʙ ʀᴇsᴜʟᴛ ᴛᴇᴍᴘʟᴀᴛᴇ.
• /set_stream - ᴄʜᴀɴɢᴇ sᴛʀᴇᴀᴍ sʜᴏʀᴛ ʟɪɴᴋ.
• /connections - ʟɪsᴛ ʏᴏᴜʀ ᴄᴏɴɴᴇᴄᴛɪᴏɴs.
• /settings - ᴄʜᴀɴɢᴇ sᴇᴛᴛɪɴɢs.
• /details - ᴠɪᴇᴡ sᴀᴠᴇᴅ ᴠᴀʟᴜᴇs.
"""

    ADMIC_TXT = """
👇 ᴄᴏᴍᴍᴀɴᴅs ꜰᴏʀ ᴀᴅᴍɪɴs (1/2) 👇

• /add_premium - <code>ᴀᴅᴅ ᴀ ᴜsᴇʀ ᴛᴏ ᴘʀᴇᴍɪᴜᴍ.</code>
• /remove_premium - <code>ʀᴇᴍᴏᴠᴇ ᴀ ᴜsᴇʀ ꜰʀᴏᴍ ᴘʀᴇᴍɪᴜᴍ.</code>
• /premium_users - <code>ʟɪsᴛ ᴘʀᴇᴍɪᴜᴍ ᴜsᴇʀs.</code>
• /get_premium - <code>ɪɴꜰᴏ ᴏɴ ᴀ ᴘʀᴇᴍɪᴜᴍ ᴜsᴇʀ.</code>
• /restart - <code>ʀᴇsᴛᴀʀᴛ ᴛʜᴇ ʙᴏᴛ.</code>
• /code - ɢᴇɴᴇʀᴀᴛᴇ ᴀ ᴘʀᴇᴍɪᴜᴍ ᴄᴏᴅᴇ.
• /clearcodes - ᴅᴇʟᴇᴛᴇ ᴀʟʟ ᴄᴏᴅᴇs.
• /allcodes - ᴠɪᴇᴡ ᴀʟʟ ᴄᴏᴅᴇs.
• /grp_delete - ᴄʟᴇᴀʀ ᴛʜᴇ ɢʀᴏᴜᴘ ᴅᴀᴛᴀʙᴀsᴇ.
• /setlink - sᴇᴛ ꜰǫᴅɴ ᴜʀʟ.
• /set_value - sᴇᴛ ᴀ ɢʟᴏʙᴀʟ ᴛᴏɢɢʟᴇ (ᴛʀᴜᴇ/ꜰᴀʟsᴇ).
"""

    ADMIC_TEX2T = """
👇 ᴄᴏᴍᴍᴀɴᴅs ꜰᴏʀ ᴀᴅᴍɪɴs (2/2) 👇

• /logs - <code>ɢᴇᴛ ʀᴇᴄᴇɴᴛ ᴇʀʀᴏʀs.</code>
• /delete - <code>ᴅᴇʟᴇᴛᴇ ᴀ ꜰɪʟᴇ ꜰʀᴏᴍ ᴅʙ.</code>
• /users - <code>ʟɪsᴛ ᴜsᴇʀs.</code>
• /chats - <code>ʟɪsᴛ ᴄʜᴀᴛs.</code>
• /leave - <code>ʟᴇᴀᴠᴇ ᴀ ᴄʜᴀᴛ.</code>
• /disable - <code>ᴅɪsᴀʙʟᴇ ᴀ ᴄʜᴀᴛ.</code>
• /ban - <code>ʙᴀɴ ᴀ ᴜsᴇʀ.</code>
• /unban - <code>ᴜɴʙᴀɴ ᴀ ᴜsᴇʀ.</code>
• /channel - <code>ʟɪsᴛ ᴄᴏɴɴᴇᴄᴛᴇᴅ ɢʀᴏᴜᴘs.</code>
• /broadcast - <code>ʙʀᴏᴀᴅᴄᴀsᴛ ᴛᴏ ᴀʟʟ ᴜsᴇʀs.</code>
• /grp_broadcast - <code>ʙʀᴏᴀᴅᴄᴀsᴛ ᴛᴏ ᴀʟʟ ɢʀᴏᴜᴘs.</code>
• /deletefiles - <code>ᴅᴇʟᴇᴛᴇ ꜰɪʟᴇs ʙʏ ᴋᴇʏᴡᴏʀᴅ.</code>
• /deleteall - ᴅᴇʟᴇᴛᴇ ᴀʟʟ ɪɴᴅᴇxᴇᴅ ꜰɪʟᴇs.
• /send - <code>sᴇɴᴅ ᴀ ᴍᴇssᴀɢᴇ ᴛᴏ ᴀ ᴜsᴇʀ.</code>
"""

    # ── premium / payment (per-deployer values removed) ──────────────────────
    PREMIUM_CMD = """<b>
💵 <i>ᴘʀᴇᴍɪᴜᴍ ᴘʟᴀɴs</i>

1. 20₹ = 1 ᴍᴏɴᴛʜ
2. 38₹ = 2 ᴍᴏɴᴛʜs
3. 55₹ = 3 ᴍᴏɴᴛʜs
4. 110₹ = 6 ᴍᴏɴᴛʜs

==========================
🎁 <u>ᴘʀᴇᴍɪᴜᴍ ꜰᴇᴀᴛᴜʀᴇs</u> :

○ sᴇᴀʀᴄʜ ᴍᴏᴠɪᴇs ɪɴ ᴛʜᴇ ʙᴏᴛ
○ ɴᴏ ꜰɪʟᴇ ʟɪᴍɪᴛs
○ ᴜɴʟɪᴍɪᴛᴇᴅ ꜰɪʟᴇs
○ ɴᴏ "sᴇɴᴅ ᴀʟʟ" ʟɪᴍɪᴛs
○ ɴᴏ ʟɪɴᴋs ᴛᴏ ᴏᴘᴇɴ
○ ɴᴏ ᴠᴇʀɪꜰɪᴄᴀᴛɪᴏɴ
○ ᴅɪʀᴇᴄᴛ ꜰɪʟᴇs
○ ᴀᴅ-ꜰʀᴇᴇ
○ ᴜɴʟɪᴍɪᴛᴇᴅ ᴍᴏᴠɪᴇs & sᴇʀɪᴇs

==========================
➛ ᴄʜᴇᴄᴋ ʏᴏᴜʀ ᴘʟᴀɴ : /myplan

‼️ sᴇɴᴅ ᴀ sᴄʀᴇᴇɴsʜᴏᴛ ᴀꜰᴛᴇʀ ᴘᴀʏᴍᴇɴᴛ</b>"""

    UPI_TXT = """<b>
⚜️ ᴘᴀʏ ᴀᴄᴄᴏʀᴅɪɴɢ ᴛᴏ ʏᴏᴜʀ ᴘʟᴀɴ ᴀɴᴅ ᴇɴᴊᴏʏ ᴘʀᴇᴍɪᴜᴍ!

💵 ᴜᴘɪ ɪᴅ - <code>ᴄᴏɴᴛᴀᴄᴛ ᴀᴅᴍɪɴ ꜰᴏʀ ᴘᴀʏᴍᴇɴᴛ ᴅᴇᴛᴀɪʟs</code>

‼️ sᴇɴᴅ ᴀ sᴄʀᴇᴇɴsʜᴏᴛ ᴀꜰᴛᴇʀ ᴘᴀʏᴍᴇɴᴛ</b>"""

    QR_TXT = """<b>
⚜️ ᴘᴀʏ ᴀᴄᴄᴏʀᴅɪɴɢ ᴛᴏ ʏᴏᴜʀ ᴘʟᴀɴ ᴀɴᴅ ᴇɴᴊᴏʏ ᴘʀᴇᴍɪᴜᴍ!

‼️ sᴇɴᴅ ᴀ sᴄʀᴇᴇɴsʜᴏᴛ ᴀꜰᴛᴇʀ ᴘᴀʏᴍᴇɴᴛ</b>"""

    FREE_TXT = """<b>👋 ʜᴇʏ {},

🥳 ᴄᴏɴɢʀᴀᴛᴜʟᴀᴛɪᴏɴs!

🎉 ʏᴏᴜ ᴄᴀɴ ᴜsᴇ ᴀ ꜰʀᴇᴇ ᴘʀᴇᴍɪᴜᴍ ᴛʀɪᴀʟ.

<u>sᴇᴀʀᴄʜ ᴛʜᴇ ᴍᴏᴠɪᴇ ᴏʀ sᴇʀɪᴇs ᴀɢᴀɪɴ 🥰</u></b>"""

    # ── request feedback (each takes one {} = original feedback text) ─────────
    NOT_AVAILABLE_TXT = """{}

ʏᴏᴜʀ ʀᴇǫᴜᴇsᴛᴇᴅ ᴄᴏɴᴛᴇɴᴛ ɪs ɴᴏᴛ ᴀᴠᴀɪʟᴀʙʟᴇ."""

    SERIES_FORMAT_TXT = """{}

ʏᴏᴜʀ ʀᴇǫᴜᴇsᴛ ꜰᴏʀᴍᴀᴛ ɪs ᴡʀᴏɴɢ ❌
ꜰᴏʟʟᴏᴡ ᴛʜɪs ꜰᴏʀᴍᴀᴛ 👇

Money heist S01E01
Money heist S01"""

    UPLOADED_TXT = """{}

ʏᴏᴜʀ ʀᴇǫᴜᴇsᴛᴇᴅ ᴄᴏɴᴛᴇɴᴛ ɪs ᴜᴘʟᴏᴀᴅᴇᴅ ✅
sᴇᴀʀᴄʜ ᴀɢᴀɪɴ ᴀɴᴅ ᴇɴᴊᴏʏ 🥰"""

    NOT_RELEASE_TXT = """{}

ʏᴏᴜʀ ʀᴇǫᴜᴇsᴛᴇᴅ ᴄᴏɴᴛᴇɴᴛ ʜᴀsɴ'ᴛ ʀᴇʟᴇᴀsᴇᴅ ʏᴇᴛ.
ᴘʟᴇᴀsᴇ ᴡᴀɪᴛ ᴜɴᴛɪʟ ɪᴛ's ᴏᴜᴛ! 👀"""

    SPELL_TXT = """{}
ᴛʜᴇ ɴᴀᴍᴇ ʏᴏᴜ sᴇɴᴛ ᴅɪᴅɴ'ᴛ ᴍᴀᴛᴄʜ ᴀɴʏ ᴍᴏᴠɪᴇ ᴏʀ sᴇʀɪᴇs.

ᴘʟᴇᴀsᴇ ʀᴇǫᴜᴇsᴛ ᴜsɪɴɢ ᴛʜᴇ ᴄᴏʀʀᴇᴄᴛ ɴᴀᴍᴇ."""

    # ── broadcast / restart / banner ─────────────────────────────────────────
    BROADCAST = """<u>{}</u>

Total: `{}`
Remaining: `{}`
Success: `{}`
Failed: `{}`"""

    RESTART_TXT = f"""
<b>Bᴏᴛ Rᴇsᴛᴀʀᴛᴇᴅ !

🤖 Bᴏᴛ : <a href=https://t.me/{{}}>{{}}</a>
📅 Dᴀᴛᴇ : <code>{{}}</code>
⏰ Tɪᴍᴇ : <code>{{}}</code>
🛠️ Bᴜɪʟᴅ : <code>{PRETTY_VERSION}</code></b>"""

    LOGO = """
 ______  ____   ____  ____   ____  ______  __ __      ___ ___   ___   ___   _____
|      ||    \\ |    ||    \\ |    ||      ||  |  |    |   |   | /   \\ |   \\ / ___/
|      ||  D  ) |  | |  _  | |  | |      ||  |  |    | _   _ ||     ||    (   \\_
|_|  |_||    /  |  | |  |  | |  | |_|  |_||  ~  |    |  \\_/  ||  O  ||  D  \\__  |
  |  |  |    \\  |  | |  |  | |  |   |  |  |___, |    |   |   ||     ||     /  \\ |
  |__|  |__|\\_||____||__|__||____|  |__|  |____/     |___|___| \\___/ |_____|\\___|

⚡ TRINITY AUTOFILTER — STARTED SUCCESSFULLY ✅  (by @trinityXmods)"""


# ───────────────────────────  ⚡ Trinity Mods · @trinityXmods  ───────────────────────────

# The instance the rest of the project imports (`from phrases import phrases`).
phrases = Phrases()

# ═══════════════════════════════════════════════════════════════════════════════
#  ⚡ Crafted by Trinity Mods (@trinityXmods) · Trinity AutoFilter
#  If this code helped you, keep the credit alive → github.com/Trinity-Mods
#  🚫 This credit is license-locked. See brand.py.
# ═══════════════════════════════════════════════════════════════════════════════
