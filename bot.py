"""Gulnora Farm — HR / Ishga qabul qilish Telegram boti.

Ishga tushirish:
    1. python -m venv venv && venv\\Scripts\\activate   (Windows)
    2. pip install -r requirements.txt
    3. .env.example dan .env yarating va BOT_TOKEN, SUPER_ADMINS ni to'ldiring
    4. python bot.py
"""
import asyncio
import logging

from aiogram import Bot, Dispatcher, BaseMiddleware
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery

from config import BOT_TOKEN, SUPER_ADMINS
from database.db import init_db
from database import queries as q
from handlers import register_all
import keyboards as kb
from keyboards import MENU_ESCAPE_BUTTONS
from utils import PROFILE_UPDATE_NOTICE
from services.reminders import (
    interview_reminder_loop, probation_reminder_loop, location_check_loop,
    advance_prompt_loop, it_report_loop, dayoff_prompt_loop, dayoff_report_loop,
    director_report_loop,
)


class BlockMiddleware(BaseMiddleware):
    """Bloklangan foydalanuvchilarning barcha so'rovlarini to'xtatadi."""

    async def __call__(self, handler, event, data):
        user = data.get("event_from_user")
        if user and user.id not in SUPER_ADMINS:
            try:
                if await q.is_user_blocked(user.id):
                    return None
            except Exception:
                pass
        return await handler(event, data)

class ProfileUpdateMiddleware(BaseMiddleware):
    """Admin «🔄 Ma'lumotlarni yangilash» ni ishga tushirgan bo'lsa — xodim
    ma'lumotlarini yangilamaguncha botning boshqa bo'limlariga kirmaydi.

    Faqat «Gulnora Farm hodimi» anketasi (StaffReg) va yangilash tugmalari
    o'tkaziladi. Admin/HR/IT belgilanmaydi — ular kampaniyani boshqaradi."""

    ALLOWED_CALLBACKS = {"profupd_start", "sreg_confirm", "sreg_cancel"}

    async def __call__(self, handler, event, data):
        user = data.get("event_from_user")
        if not user:
            return await handler(event, data)
        try:
            if not await q.needs_profile_update(user.id):
                return await handler(event, data)
        except Exception:
            return await handler(event, data)

        state = data.get("state")
        current = await state.get_state() if state else None
        if current and current.startswith("StaffReg:"):
            return await handler(event, data)  # anketa to'ldirilmoqda
        if isinstance(event, CallbackQuery):
            if event.data in self.ALLOWED_CALLBACKS:
                return await handler(event, data)
            await event.answer(
                "🔄 Avval ma'lumotlaringizni yangilang.", show_alert=True
            )
            return None
        # Yarim qolgan boshqa oqim bo'lsa — tozalaymiz (aks holda qulflanib qoladi)
        if current and state:
            await state.clear()
        await event.answer(
            PROFILE_UPDATE_NOTICE, reply_markup=kb.profile_update_start_kb()
        )
        return None


class MenuEscapeMiddleware(BaseMiddleware):
    """Asosiy menyu tugmasi bosilsa — yarim qolgan anketani (FSM) bekor qiladi.

    Aks holda, masalan, xodim anketani tugatmay «⏸ Tanaffus» ni bossa, tugma
    matni ochiq savolga javob sifatida qabul qilinib, tugma ishlamay qolardi."""

    async def __call__(self, handler, event, data):
        text = getattr(event, "text", None)
        state = data.get("state")
        if text and text in MENU_ESCAPE_BUTTONS and state is not None:
            if await state.get_state() is not None:
                await state.clear()
        return await handler(event, data)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("hrbot")


async def main():
    await init_db()
    logger.info("Ma'lumotlar bazasi tayyor.")

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())
    dp.update.outer_middleware(BlockMiddleware())
    # Yangilash talabi menyu tugmalaridan oldin tekshiriladi
    dp.message.outer_middleware(ProfileUpdateMiddleware())
    dp.callback_query.outer_middleware(ProfileUpdateMiddleware())
    dp.message.outer_middleware(MenuEscapeMiddleware())
    register_all(dp)

    me = await bot.get_me()
    logger.info("Bot ishga tushdi: @%s", me.username)

    await bot.delete_webhook(drop_pending_updates=True)
    reminder_task = asyncio.create_task(interview_reminder_loop(bot))
    probation_task = asyncio.create_task(probation_reminder_loop(bot))
    location_task = asyncio.create_task(location_check_loop(bot))
    advance_task = asyncio.create_task(advance_prompt_loop(bot))
    it_report_task = asyncio.create_task(it_report_loop(bot))
    dayoff_prompt_task = asyncio.create_task(dayoff_prompt_loop(bot))
    dayoff_report_task = asyncio.create_task(dayoff_report_loop(bot))
    director_report_task = asyncio.create_task(director_report_loop(bot))
    try:
        await dp.start_polling(bot)
    finally:
        for task in (reminder_task, probation_task, location_task, advance_task,
                     it_report_task, dayoff_prompt_task, dayoff_report_task,
                     director_report_task):
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot to'xtatildi.")
