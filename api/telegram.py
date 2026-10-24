"""Bot token orqali Telegram ga xabar yuborish (API jarayonidan).

Polling bilan to'qnashmaydi: bu yerda faqat sendMessage / getFile chaqiriladi,
update lar olinmaydi. Testlarda `set_sender()` bilan almashtiriladi.

Mustahkamlik:
  * 429 (flood) — Telegram aytgan `retry_after` soniya kutib qayta yuboradi;
  * HTML parse xatosi ("can't parse entities") — xabar oddiy matn sifatida qayta ketadi;
  * 4096 belgidan uzun xabar bo'laklarga bo'linadi (tugmalar oxirgi bo'lakda);
  * bloklagan / botni ishga tushirmagan / chat topilmagan — DOIMIY xato
    (`is_permanent(err)`), qayta urinilmaydi;
  * ketma-ket yuborishda kichik pauza (Telegram ~30 xabar/soniya limiti).
"""
import asyncio
import html
import logging
import re
import time

from api import settings

logger = logging.getLogger("hrbot.api.telegram")

MAX_LEN = 4096
SEND_INTERVAL = 0.05          # ~20 xabar/soniya — Telegram limitidan past
MAX_FLOOD_WAIT = 60           # bundan uzoq kutish kerak bo'lsa — keyingi siklga qoldiriladi

_bot = None
_custom_sender = None
_last_send = 0.0
_send_lock = None

PERMANENT_MARKERS = (
    "bot was blocked", "user is deactivated", "chat not found", "bot can't initiate",
    "have no rights", "peer_id_invalid", "bot was kicked", "forbidden", "no_chat",
)


def is_permanent(err):
    """Qayta urinish foydasiz bo'lgan xato (xodim botni bloklagan va h.k.)."""
    low = (err or "").lower()
    return any(m in low for m in PERMANENT_MARKERS)


def _get_bot():
    global _bot
    if _bot is None:
        from aiogram import Bot
        from aiogram.client.default import DefaultBotProperties
        from aiogram.enums import ParseMode
        from config import BOT_TOKEN
        _bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    return _bot


def set_sender(func):
    """Test/almashtirish uchun: async func(chat_id, text, reply_markup) -> message_id."""
    global _custom_sender
    _custom_sender = func


def split_text(text, limit=MAX_LEN):
    """Uzun matnni qator/bo'sh joy chegarasida bo'laklarga bo'ladi."""
    text = text or ""
    if len(text) <= limit:
        return [text]
    parts = []
    while len(text) > limit:
        cut = text.rfind("\n", 0, limit)
        if cut < limit // 2:
            cut = text.rfind(" ", 0, limit)
        if cut < limit // 2:
            cut = limit
        parts.append(text[:cut])
        text = text[cut:].lstrip("\n")
    if text:
        parts.append(text)
    return parts


def html_to_plain(text):
    return html.unescape(re.sub(r"<[^>]+>", "", text or ""))


async def _throttle():
    global _last_send, _send_lock
    if _send_lock is None:
        _send_lock = asyncio.Lock()
    async with _send_lock:
        wait = SEND_INTERVAL - (time.monotonic() - _last_send)
        if wait > 0:
            await asyncio.sleep(wait)
        _last_send = time.monotonic()


async def _raw_send(chat_id, text, reply_markup, plain):
    if _custom_sender is not None:
        return await _custom_sender(chat_id, text, reply_markup)
    kwargs = {"reply_markup": reply_markup, "disable_web_page_preview": True}
    if plain:
        kwargs["parse_mode"] = None
    msg = await _get_bot().send_message(chat_id, text, **kwargs)
    return msg.message_id


async def _send_chunk(chat_id, text, reply_markup):
    plain = False
    for _ in range(3):
        await _throttle()
        try:
            return await _raw_send(chat_id, text, reply_markup, plain)
        except Exception as e:
            retry_after = getattr(e, "retry_after", None)
            msg = str(e).lower()
            if retry_after is not None:
                if retry_after > MAX_FLOOD_WAIT:
                    raise
                logger.warning("Telegram flood limit: %ss kutilmoqda", retry_after)
                await asyncio.sleep(int(retry_after) + 1)
                continue
            if not plain and ("can't parse entities" in msg or "unsupported start tag" in msg
                              or "can't find end" in msg):
                text, plain = html_to_plain(text), True
                continue
            raise
    raise RuntimeError("Telegram: yuborish urinishlari tugadi")


async def send_text(chat_id, text, reply_markup=None):
    """(ok, message_id, error) qaytaradi. Xato matnida token bo'lmaydi.
    Uzun matn bir nechta xabar bo'lib ketadi; message_id — birinchisiniki."""
    if not settings.API_TELEGRAM_SEND_ENABLED and _custom_sender is None:
        return False, None, "telegram_send_disabled"
    if not chat_id:
        return False, None, "no_chat: xodimning Telegram ID si yo'q"
    chunks = split_text(text)
    first_id = None
    try:
        for i, chunk in enumerate(chunks):
            markup = reply_markup if i == len(chunks) - 1 else None
            mid = await _send_chunk(chat_id, chunk, markup)
            first_id = first_id or mid
        return True, first_id, None
    except Exception as e:  # bloklagan / botni ishga tushirmagan / tarmoq
        if first_id:  # bir qismi ketgan — yetkazilgan deb hisoblaymiz
            logger.warning("Xabarning bir qismi yuborilmadi (%s): %s", chat_id, e)
            return True, first_id, None
        err = f"{type(e).__name__}: {str(e)[:300]}"
        try:
            from config import BOT_TOKEN
            if BOT_TOKEN:
                err = err.replace(BOT_TOKEN, "***")
        except Exception:
            pass
        return False, None, err


async def download_file(file_id):
    """Telegram file_id bo'yicha faylni yuklab oladi -> (bytes, filename)."""
    import io
    bot = _get_bot()
    f = await bot.get_file(file_id)
    buf = io.BytesIO()
    await bot.download_file(f.file_path, destination=buf)
    name = (f.file_path or "file").rsplit("/", 1)[-1]
    return buf.getvalue(), name


async def close():
    global _bot
    if _bot is not None:
        try:
            await _bot.session.close()
        except Exception:
            pass
        _bot = None
