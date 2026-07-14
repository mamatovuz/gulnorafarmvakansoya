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

from config import BOT_TOKEN, SUPER_ADMINS
from database.db import init_db
from database import queries as q
from handlers import register_all
from services.reminders import (
    interview_reminder_loop, probation_reminder_loop, location_check_loop,
    advance_prompt_loop, it_report_loop,
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
    register_all(dp)

    me = await bot.get_me()
    logger.info("Bot ishga tushdi: @%s", me.username)

    await bot.delete_webhook(drop_pending_updates=True)
    reminder_task = asyncio.create_task(interview_reminder_loop(bot))
    probation_task = asyncio.create_task(probation_reminder_loop(bot))
    location_task = asyncio.create_task(location_check_loop(bot))
    advance_task = asyncio.create_task(advance_prompt_loop(bot))
    it_report_task = asyncio.create_task(it_report_loop(bot))
    try:
        await dp.start_polling(bot)
    finally:
        for task in (reminder_task, probation_task, location_task, advance_task,
                     it_report_task):
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
