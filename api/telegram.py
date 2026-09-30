"""Bot token orqali Telegram ga xabar yuborish (API jarayonidan).

Polling bilan to'qnashmaydi: bu yerda faqat sendMessage / getFile chaqiriladi,
update lar olinmaydi. Testlarda `set_sender()` bilan almashtiriladi.
"""
import logging

from api import settings

logger = logging.getLogger("hrbot.api.telegram")

_bot = None
_custom_sender = None


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


async def send_text(chat_id, text, reply_markup=None):
    """(ok, message_id, error) qaytaradi. Xato matnida token bo'lmaydi."""
    if not settings.API_TELEGRAM_SEND_ENABLED and _custom_sender is None:
        return False, None, "telegram_send_disabled"
    try:
        if _custom_sender is not None:
            mid = await _custom_sender(chat_id, text, reply_markup)
            return True, mid, None
        msg = await _get_bot().send_message(chat_id, text, reply_markup=reply_markup)
        return True, msg.message_id, None
    except Exception as e:  # bloklagan / botni ishga tushirmagan / tarmoq
        return False, None, f"{type(e).__name__}: {str(e)[:300]}"


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
