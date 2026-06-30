# ═══════════════════════════════════════════════════════════════════════════════
#  ⚡ TRINITY MODS · TRINITY AUTOFILTER
#  /font stylish-text tool — paginated unicode style picker with copy-to-clipboard.
#  ─────────────────────────────────────────────────────────────────────────────
#  Developed & maintained by Trinity Mods (@trinityXmods)
#  GitHub   : github.com/Trinity-Mods
#  Source   : github.com/Trinity-Mods/Auto-Filter-Bot
#  Telegram : t.me/trinityXmods
#  🚫 Credit is license-locked — see brand.py. Please keep this header intact.
# ═══════════════════════════════════════════════════════════════════════════════

import logging

from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

# Relative import — the unicode style tables live next door in fonts_data.py.
from .fonts_data import Fonts

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
#  STYLE REGISTRY
#  Maps the callback-data style key (the part after "style+") to the matching
#  Fonts converter method. This replaces the original giant if/elif chain:
#  one O(1) dict lookup instead of ~38 sequential comparisons, and adding a new
#  style is now a single line. Callback-data keys are kept byte-for-byte identical
#  to the original so existing inline buttons keep working.
# ─────────────────────────────────────────────────────────────────────────────
STYLE_MAP = {
    "typewriter":   Fonts.typewriter,
    "outline":      Fonts.outline,
    "serif":        Fonts.serief,        # note: data method is spelled "serief"
    "bold_cool":    Fonts.bold_cool,
    "cool":         Fonts.cool,
    "small_cap":    Fonts.smallcap,
    "script":       Fonts.script,
    "script_bolt":  Fonts.bold_script,
    "tiny":         Fonts.tiny,
    "comic":        Fonts.comic,
    "sans":         Fonts.san,
    "slant_sans":   Fonts.slant_san,
    "slant":        Fonts.slant,
    "sim":          Fonts.sim,
    "circles":      Fonts.circles,
    "circle_dark":  Fonts.dark_circle,
    "gothic":       Fonts.gothic,
    "gothic_bolt":  Fonts.bold_gothic,
    "cloud":        Fonts.cloud,
    "happy":        Fonts.happy,
    "sad":          Fonts.sad,
    "special":      Fonts.special,
    "squares":      Fonts.square,
    "squares_bold": Fonts.dark_square,
    "andalucia":    Fonts.andalucia,
    "manga":        Fonts.manga,
    "stinky":       Fonts.stinky,
    "bubbles":      Fonts.bubbles,
    "underline":    Fonts.underline,
    "ladybug":      Fonts.ladybug,
    "rays":         Fonts.rays,
    "birds":        Fonts.birds,
    "slash":        Fonts.slash,
    "stop":         Fonts.stop,
    "skyline":      Fonts.skyline,
    "arrows":       Fonts.arrows,
    "qvnes":        Fonts.rvnes,          # note: data method is spelled "rvnes"
    "strike":       Fonts.strike,
    "frozen":       Fonts.frozen,
}


def _page_one_keyboard() -> InlineKeyboardMarkup:
    """First page of style buttons (shown by /font and by the 'Back' button)."""
    rows = [
        [
            InlineKeyboardButton('𝚃𝚢𝚙𝚎𝚠𝚛𝚒𝚝𝚎𝚛', callback_data='style+typewriter'),
            InlineKeyboardButton('𝕆𝕦𝕥𝕝𝕚𝕟𝕖', callback_data='style+outline'),
            InlineKeyboardButton('𝐒𝐞𝐫𝐢𝐟', callback_data='style+serif'),
        ],
        [
            InlineKeyboardButton('𝑺𝒆𝒓𝒊𝒇', callback_data='style+bold_cool'),
            InlineKeyboardButton('𝑆𝑒𝑟𝑖𝑓', callback_data='style+cool'),
            InlineKeyboardButton('Sᴍᴀʟʟ Cᴀᴘs', callback_data='style+small_cap'),
        ],
        [
            InlineKeyboardButton('𝓈𝒸𝓇𝒾𝓅𝓉', callback_data='style+script'),
            InlineKeyboardButton('𝓼𝓬𝓻𝓲𝓹𝓽', callback_data='style+script_bolt'),
            InlineKeyboardButton('ᵗⁱⁿʸ', callback_data='style+tiny'),
        ],
        [
            InlineKeyboardButton('ᑕOᗰIᑕ', callback_data='style+comic'),
            InlineKeyboardButton('𝗦𝗮𝗻𝘀', callback_data='style+sans'),
            InlineKeyboardButton('𝙎𝙖𝙣𝙨', callback_data='style+slant_sans'),
        ],
        [
            InlineKeyboardButton('𝘚𝘢𝘯𝘴', callback_data='style+slant'),
            InlineKeyboardButton('𝖲𝖺𝗇𝗌', callback_data='style+sim'),
            InlineKeyboardButton('Ⓒ︎Ⓘ︎Ⓡ︎Ⓒ︎Ⓛ︎Ⓔ︎Ⓢ︎', callback_data='style+circles'),
        ],
        [
            InlineKeyboardButton('🅒︎🅘︎🅡︎🅒︎🅛︎🅔︎🅢︎', callback_data='style+circle_dark'),
            InlineKeyboardButton('𝔊𝔬𝔱𝔥𝔦𝔠', callback_data='style+gothic'),
            InlineKeyboardButton('𝕲𝖔𝖙𝖍𝖎𝖈', callback_data='style+gothic_bolt'),
        ],
        [
            InlineKeyboardButton('C͜͡l͜͡o͜͡u͜͡d͜͡s͜͡', callback_data='style+cloud'),
            InlineKeyboardButton('H̆̈ă̈p̆̈p̆̈y̆̈', callback_data='style+happy'),
            InlineKeyboardButton('S̑̈ȃ̈d̑̈', callback_data='style+sad'),
        ],
        [
            InlineKeyboardButton('Next ➡️', callback_data="nxt"),
        ],
    ]
    return InlineKeyboardMarkup(rows)


def _page_two_keyboard() -> InlineKeyboardMarkup:
    """Second page of style buttons (shown by the 'Next' button)."""
    rows = [
        [
            InlineKeyboardButton('🇸 🇵 🇪 🇨 🇮 🇦 🇱 ', callback_data='style+special'),
            InlineKeyboardButton('🅂🅀🅄🄰🅁🄴🅂', callback_data='style+squares'),
            InlineKeyboardButton('🆂︎🆀︎🆄︎🅰︎🆁︎🅴︎🆂︎', callback_data='style+squares_bold'),
        ],
        [
            InlineKeyboardButton('ꪖꪀᦔꪖꪶꪊᥴ𝓲ꪖ', callback_data='style+andalucia'),
            InlineKeyboardButton('爪卂几ᘜ卂', callback_data='style+manga'),
            InlineKeyboardButton('S̾t̾i̾n̾k̾y̾', callback_data='style+stinky'),
        ],
        [
            InlineKeyboardButton('B̥ͦu̥ͦb̥ͦb̥ͦl̥ͦe̥ͦs̥ͦ', callback_data='style+bubbles'),
            InlineKeyboardButton('U͟n͟d͟e͟r͟l͟i͟n͟e͟', callback_data='style+underline'),
            InlineKeyboardButton('꒒ꍏꀷꌩꌃꀎꁅ', callback_data='style+ladybug'),
        ],
        [
            InlineKeyboardButton('R҉a҉y҉s҉', callback_data='style+rays'),
            InlineKeyboardButton('B҈i҈r҈d҈s҈', callback_data='style+birds'),
            InlineKeyboardButton('S̸l̸a̸s̸h̸', callback_data='style+slash'),
        ],
        [
            InlineKeyboardButton('s⃠t⃠o⃠p⃠', callback_data='style+stop'),
            InlineKeyboardButton('S̺͆k̺͆y̺͆l̺͆i̺͆n̺͆e̺͆', callback_data='style+skyline'),
            InlineKeyboardButton('A͎r͎r͎o͎w͎s͎', callback_data='style+arrows'),
        ],
        [
            InlineKeyboardButton('ዪሀክቿነ', callback_data='style+qvnes'),
            InlineKeyboardButton('S̶t̶r̶i̶k̶e̶', callback_data='style+strike'),
            InlineKeyboardButton('F༙r༙o༙z༙e༙n༙', callback_data='style+frozen'),
        ],
        [
            InlineKeyboardButton('⬅️ Back', callback_data='nxt+0'),
        ],
    ]
    return InlineKeyboardMarkup(rows)


# ─────────────────────────────────────────────────────────────────────────────
#  /font  — entry point. Usage: `/font some text`.
#  The original used a `cb` flag so the callback layer could re-render page one;
#  we keep that contract but pull the keyboard out into _page_one_keyboard().
# ─────────────────────────────────────────────────────────────────────────────
@Client.on_message(filters.private & filters.command(["font"]))
async def style_buttons(client, message, cb=False):
    keyboard = _page_one_keyboard()

    if not cb:
        # Fresh /font command from the user.
        if ' ' in message.text:
            title = message.text.split(" ", 1)[1]
            await message.reply_text(
                title,
                reply_markup=keyboard,
                reply_to_message_id=message.id,
            )
        else:
            # No text supplied — show usage hint.
            await message.reply_text(text="Ente Any Text Eg:- `/font [text]`")
    else:
        # Invoked from the 'Back' callback (message is a CallbackQuery here).
        await message.answer()
        await message.message.edit_reply_markup(keyboard)


# ───────────────────────────  ⚡ Trinity Mods · @trinityXmods  ───────────────────────────


# ─────────────────────────────────────────────────────────────────────────────
#  Pagination callback. "nxt" → show page two; "nxt+0" (Back) → re-render page one
#  via style_buttons(cb=True).
# ─────────────────────────────────────────────────────────────────────────────
@Client.on_callback_query(filters.regex('^nxt'))
async def nxt(client, query):
    if query.data == "nxt":
        # Advance to the second page of styles.
        await query.answer()
        await query.message.edit_reply_markup(_page_two_keyboard())
    else:
        # Any other 'nxt+...' payload (the Back button) returns to page one.
        await style_buttons(client, query, cb=True)


# ─────────────────────────────────────────────────────────────────────────────
#  Style apply callback. callback_data shape: "style+<key>".
#  Converts the text from the replied-to message and edits the styled result in,
#  keeping the existing keyboard so the user can keep trying other styles.
# ─────────────────────────────────────────────────────────────────────────────
@Client.on_callback_query(filters.regex('^style'))
async def style(client, query):
    await query.answer()

    # callback_data is "style+<key>"; split once to be safe against odd payloads.
    _, _, style_key = query.data.partition('+')

    converter = STYLE_MAP.get(style_key)
    if converter is None:
        # Unknown style key — should not happen with our own buttons, but guard it.
        logger.warning("Received unknown font style key: %r", style_key)
        await query.answer("Unknown style.", show_alert=True)
        return

    # The original text lives in the message this picker was attached to.
    source = query.message.reply_to_message
    if source is None or not source.text:
        # Guard: the replied-to message may have been deleted or carries no text.
        logger.info("Font style requested but reply_to_message/text is missing.")
        await query.answer(
            "The original text is no longer available.", show_alert=True
        )
        return

    # Drop the leading "/font" token, keep the rest as the text to stylise.
    parts = source.text.split(None, 1)
    if len(parts) < 2:
        # Only the command was present — nothing to convert.
        await query.answer("No text to style.", show_alert=True)
        return
    original_text = parts[1]

    styled = converter(original_text)
    try:
        # Wrap in backticks so Telegram renders a tap-to-copy block.
        await query.message.edit_text(
            f"`{styled}`\n\n👆 Click To Copy",
            reply_markup=query.message.reply_markup,
        )
    except Exception as err:
        # Most commonly MessageNotModified when the same style is tapped twice.
        logger.exception("Failed to edit message with styled text: %s", err)


# ═══════════════════════════════════════════════════════════════════════════════
#  ⚡ Crafted by Trinity Mods (@trinityXmods) · Trinity AutoFilter
#  If this code helped you, keep the credit alive → github.com/Trinity-Mods
#  🚫 This credit is license-locked. See brand.py.
# ═══════════════════════════════════════════════════════════════════════════════
