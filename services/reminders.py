"""Suhbat va sinov muddati eslatmalarini yuboradigan background loop."""
import asyncio
import logging
from datetime import datetime, timedelta

from aiogram import Bot

from database import queries as q
from database.db import ROLE_HR, ROLE_ADMIN, ROLE_IT
import keyboards as kb
from utils import safe_send, days_left_until, probation_text, iso_to_display, now_tk

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
    now = now_tk()
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

        noun = "O'rganish muddati" if p.get("kind") == "learner" else "Sinov muddati"
        # Tugashiga 3 kun (yoki kamroq) qolganda — bir marta HR ga xabar
        if 0 < left <= 3 and not p.get("hr_3day_sent"):
            text = (
                f"⏳ <b>{noun} tugashiga oz qoldi</b>\n\n"
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
            header = f"🏁 <b>{noun} tugadi</b>\n\n"
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


# ---------------- PERIODIK JOYLASHUV TEKSHIRUVI ----------------
async def _run_location_checks(bot: Bot):
    enabled = await q.get_setting("loc_check_enabled", "1")
    if str(enabled) != "1":
        return
    try:
        interval = float(await q.get_setting("loc_check_interval_hours", "2") or 2)
    except (TypeError, ValueError):
        interval = 2.0
    # Javobsiz qolgan eski tekshiruvlarni 'missed' qilamiz
    await q.mark_stale_location_checks(minutes=30)
    due = await q.attendance_due_for_check(interval)
    for row in due:
        tg_id = row.get("tg_id")
        if not tg_id:
            continue
        await q.add_location_check(row["id"], row["user_id"], row.get("branch_id"), kind="auto")
        await q.touch_attendance_prompt(row["id"])
        await safe_send(
            bot, tg_id,
            "📍 <b>Ish joyi tekshiruvi</b>\n\n"
            "Hozir siz ish joyingizda ekaningizni tasdiqlash uchun joriy "
            "<b>joylashuvingizni</b> yuboring.\n"
            "Pastdagi «📍 Joylashuvni yuborish» tugmasidan foydalaning.",
            reply_markup=kb.attendance_location_kb(),
        )


async def location_check_loop(bot: Bot, interval_seconds=60):
    while True:
        try:
            await _run_location_checks(bot)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Periodik joylashuv tekshiruvida xatolik")
        await asyncio.sleep(interval_seconds)


# ---------------- AVANS SO'ROVI (har oy belgilangan kunda) ----------------
async def _run_advance_prompt(bot: Bot):
    enabled = await q.get_setting("avans_enabled", "1")
    if str(enabled) != "1":
        return
    now = now_tk()
    try:
        prompt_day = int(await q.get_setting("avans_prompt_day", "13") or 13)
    except (TypeError, ValueError):
        prompt_day = 13
    if now.day != prompt_day:
        return

    period = now.strftime("%Y-%m")
    flag_key = f"avans_prompt_sent:{period}"
    if str(await q.get_setting(flag_key, "0")) == "1":
        return  # bu oy allaqachon yuborilgan

    try:
        pay_day = int(await q.get_setting("avans_day", "15") or 15)
    except (TypeError, ValueError):
        pay_day = 15

    ids = await q.advance_employee_tg_ids()
    text = (
        "💵 <b>Avans so'rovi</b>\n\n"
        "Assalomu alaykum! <b>Avans oluvchilar ro'yxatiga</b> qo'shilishni "
        "xohlaysizmi?\n"
        f"<i>Avans har oy {pay_day}-sanada kartangizga o'tkaziladi.</i>\n\n"
        "Quyidagi tugmalardan birini tanlang 👇"
    )
    for tid in ids:
        await safe_send(bot, tid, text, reply_markup=kb.advance_yes_no_kb(period))
    await q.set_setting(flag_key, "1")
    logger.info("Avans so'rovi %s ta xodimga yuborildi (%s)", len(ids), period)


# ---------------- IT KADRLAR HISOBOTI (har oy 14-sanada) ----------------
async def _run_it_report(bot: Bot):
    """Har oyning 14-sanasida tugagan davr (o'tgan 14 -> shu 14) bo'yicha
    kadrlar harakati hisobotini barcha IT xodim va adminlarga yuboradi."""
    now = now_tk()
    if now.day != 14:
        return
    period = now.strftime("%Y-%m")
    flag_key = f"it_report_sent:{period}"
    if str(await q.get_setting(flag_key, "0")) == "1":
        return  # bu oy allaqachon yuborilgan

    # Lazy import — servis handlerlarga bog'liq bo'lib qolmasligi uchun
    from handlers.it import (
        period_start_for, prev_period_start, build_report_text,
    )
    current_start = period_start_for(now)          # shu oy 14-sanasi
    start = prev_period_start(current_start)        # o'tgan oy 14-sanasi
    text = "🗓 <b>Oylik kadrlar hisoboti (14-sana)</b>\n\n" + \
        await build_report_text(start, end_dt=current_start)

    ids = set(await q.all_user_tg_ids(role=ROLE_IT))
    ids |= set(await q.all_user_tg_ids(role=ROLE_ADMIN))
    for tid in ids:
        await safe_send(bot, tid, text)
    await q.set_setting(flag_key, "1")
    logger.info("IT kadrlar hisoboti %s ta oluvchiga yuborildi (%s)", len(ids), period)


async def it_report_loop(bot: Bot, interval_seconds=3600):
    while True:
        try:
            await _run_it_report(bot)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("IT kadrlar hisobotini yuborishda xatolik")
        await asyncio.sleep(interval_seconds)


async def advance_prompt_loop(bot: Bot, interval_seconds=3600):
    while True:
        try:
            await _run_advance_prompt(bot)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Avans so'rovini yuborishda xatolik")
        await asyncio.sleep(interval_seconds)
