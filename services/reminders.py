"""Suhbat eslatmalarini yuboradigan background loop."""
import asyncio
import logging
from datetime import datetime, timedelta

from aiogram import Bot

from database import queries as q
from utils import safe_send

logger = logging.getLogger("hrbot.reminders")


def _parse_interview_datetime(date_text, time_text):
    date_text = (date_text or "").strip().replace("/", ".")
    time_text = (time_text or "").strip().replace(".", ":")
    for fmt in ("%d.%m.%Y %H:%M", "%d.%m.%y %H:%M"):
        try:
            return datetime.strptime(f"{date_text} {time_text}", fmt)
        except ValueError:
            continue
    return None


def _reminder_text(interview, title):
    return (
        f"{title}\n\n"
        f"👤 Nomzod: <b>{interview.get('full_name') or '-'}</b>\n"
        f"💼 Vakansiya: {interview.get('vacancy_title') or '-'}\n"
        f"📆 Sana: {interview.get('date') or '-'}\n"
        f"🕐 Vaqt: {interview.get('time') or '-'}\n"
        f"📍 Manzil: {interview.get('location') or '-'}\n\n"
        "Iltimos, suhbat vaqtini unutmang."
    )


async def _send_due_reminders(bot: Bot):
    now = datetime.now()
    interviews = await q.interviews_for_reminders()
    for interview in interviews:
        dt = _parse_interview_datetime(interview.get("date"), interview.get("time"))
        if not dt:
            continue
        delta = dt - now
        if delta <= timedelta(0):
            continue

        applicant_tg = interview.get("applicant_tg")
        if not applicant_tg:
            continue

        if not interview.get("reminder_2h_sent") and delta <= timedelta(hours=2):
            ok = await safe_send(
                bot,
                applicant_tg,
                _reminder_text(interview, "⏰ <b>Suhbatga 2 soatdan kam vaqt qoldi</b>"),
            )
            if ok:
                await q.mark_interview_reminder_sent(interview["id"], "2h")
            continue

        if (
            not interview.get("reminder_day_sent")
            and timedelta(hours=2) < delta <= timedelta(days=1)
        ):
            ok = await safe_send(
                bot,
                applicant_tg,
                _reminder_text(interview, "📅 <b>Suhbat eslatmasi</b>"),
            )
            if ok:
                await q.mark_interview_reminder_sent(interview["id"], "day")


async def interview_reminder_loop(bot: Bot, interval_seconds=60):
    while True:
        try:
            await _send_due_reminders(bot)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Suhbat eslatmalarini yuborishda xatolik")
        await asyncio.sleep(interval_seconds)
