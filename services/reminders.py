"""Suhbat va sinov muddati eslatmalarini yuboradigan background loop."""
import asyncio
import logging
from datetime import datetime, timedelta

from aiogram import Bot

from database import queries as q
from database.db import ROLE_HR, ROLE_ADMIN
from utils import safe_send, days_left_until, probation_text, iso_to_display

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


# ---------------- SINOV MUDDATI ESLATMALARI ----------------
async def _hr_admin_ids():
    hr = await q.all_user_tg_ids(role=ROLE_HR)
    admin = await q.all_user_tg_ids(role=ROLE_ADMIN)
    return set(hr + admin)


async def _check_probations(bot: Bot):
    probations = await q.list_active_probations()
    if not probations:
        return
    hr_ids = await _hr_admin_ids()
    for p in probations:
        left = days_left_until(p.get("end_date"))
        if left is None:
            continue

        # Tugashiga 3 kun (yoki kamroq) qolganda — bir marta HR ga xabar
        if 0 < left <= 3 and not p.get("hr_3day_sent"):
            text = (
                "⏳ <b>Sinov muddati tugashiga oz qoldi</b>\n\n"
                f"👤 <b>{p.get('full_name') or '-'}</b>\n"
                f"💼 Lavozim: {p.get('position') or '-'}\n"
                f"🏢 Filial: {p.get('branch_name') or '-'}\n"
                f"🏁 Tugash sanasi: <b>{iso_to_display(p.get('end_date'))}</b>\n"
                f"📆 Qolgan: <b>{left} kun</b>\n\n"
                "Sinov muddati tugashidan oldin xodim bo'yicha qaror qabul qiling."
            )
            for tid in hr_ids:
                await safe_send(bot, tid, text)
            await q.mark_probation_flag(p["id"], "hr_3day_sent")

        # Sinov muddati tugadi — HR ga statistika bilan xabar
        elif left <= 0 and not p.get("hr_end_sent"):
            stats = await q.probation_attendance_stats(
                p["user_id"], p.get("start_date"), p.get("end_date")
            )
            header = "🏁 <b>Sinov muddati tugadi</b>\n\n"
            body = probation_text({**p, "status": "finished"}, stats=stats)
            for tid in hr_ids:
                await safe_send(bot, tid, header + body)
            await q.mark_probation_flag(p["id"], "hr_end_sent")
            await q.set_probation_status(p["id"], "finished")


async def probation_reminder_loop(bot: Bot, interval_seconds=3600):
    while True:
        try:
            await _check_probations(bot)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Sinov muddati eslatmalarini yuborishda xatolik")
        await asyncio.sleep(interval_seconds)
