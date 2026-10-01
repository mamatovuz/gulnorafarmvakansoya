"""Excel hisobotlar: direktor «📑 Hisobotlar» va moliya «📊 Hisobot olish».

Davr: 📅 1/2/3 oylik (joriy oy bilan) yoki 🗓 sana bo'yicha (kundan — kungacha).
Direktor barcha hisobotlarni, moliya bo'limi esa faqat jarimalar hisobotini oladi.
Oy oxirida avtomatik yuborish — services/reminders.py::monthly_reports_loop.
"""
from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message

import keyboards as kb
from database import queries as q
from database.db import ROLE_ACCOUNTANT, ROLE_ADMIN, ROLE_DIRECTOR
from services.reports import (
    DIRECTOR_REPORTS, REPORT_NEEDS_PERIOD, REPORT_TITLES, DateRange, make_report,
    month_range, parse_date,
)
from states import ReportRangeForm
from utils import now_tk

router = Router()

MAX_RANGE_DAYS = 366


async def _role(tg_id):
    u = await q.get_user(tg_id)
    return u["role"] if u else None


def _allowed(role, kind):
    if role in (ROLE_DIRECTOR, ROLE_ADMIN):
        return True
    return role == ROLE_ACCOUNTANT and kind == "fines"


async def send_report(bot: Bot, chat_id, kind, rng):
    """Bitta hisobotni tayyorlab yuboradi. True — yuborildi."""
    doc, summary = await make_report(kind, rng)
    try:
        await bot.send_document(
            chat_id, doc,
            caption=f"{REPORT_TITLES.get(kind, '📑 Hisobot')}\n\n{summary}",
        )
        return True
    except Exception:
        return False


async def send_reports(bot: Bot, chat_id, kinds, rng):
    for kind in kinds:
        await send_report(bot, chat_id, kind, rng)


async def _log(tg_id, kind, rng):
    me = await q.get_user(tg_id)
    await q.add_log(tg_id, (me or {}).get("full_name") or "?", "excel_hisobot",
                    f"{kind}: {rng.since}..{rng.end:%Y-%m-%d}")


def _period_prompt(kind):
    return (
        f"{REPORT_TITLES.get(kind, '📦 Barcha hisobotlar')}\n\n"
        "Qaysi davr uchun Excel hisobot kerak?\n"
        "• <b>📅 1 oylik</b> — joriy oy (1-sanadan bugungacha)\n"
        "• <b>📅 2 / 3 oylik</b> — joriy oy bilan birga oldingi oylar\n"
        "• <b>🗓 Sana bo'yicha</b> — o'zingiz qaysi kundan qaysi kungacha "
        "ekanini yozasiz"
    )


# ---------------- KIRISH TUGMALARI ----------------
@router.message(F.text.in_({kb.DIRECTOR_REPORTS_BTN, "📑 Hisobot (Excel)"}))
async def director_reports_menu(message: Message, state: FSMContext):
    if await _role(message.from_user.id) not in (ROLE_DIRECTOR, ROLE_ADMIN):
        await message.answer("⛔ Bu bo'lim faqat direktor uchun.")
        return
    await state.clear()
    await message.answer(
        "📑 <b>Hisobotlar</b>\n\n"
        "Kerakli hisobotni tanlang — keyin davrni (1/2/3 oylik yoki sana bo'yicha) "
        "tanlaysiz va bot chiroyli Excel fayl tayyorlab beradi.\n\n"
        "<i>Har oy oxirida (oyning oxirgi kunidan bir kun oldin, 06:00 da) barcha "
        "hisobotlar avtomatik yuboriladi.</i>",
        reply_markup=kb.reports_menu_kb(),
    )


@router.message(F.text == kb.FINES_REPORT_BTN)
async def finance_fines_report(message: Message, state: FSMContext):
    if not _allowed(await _role(message.from_user.id), "fines"):
        await message.answer("⛔ Sizda moliya bo'limi paneli uchun ruxsat yo'q.")
        return
    await state.clear()
    await message.answer(_period_prompt("fines"),
                         reply_markup=kb.report_period_kb("fines", back=False))


# ---------------- HISOBOT TURI ----------------
@router.callback_query(F.data.startswith("rep:"))
async def report_pick(call: CallbackQuery, bot: Bot):
    kind = call.data.split(":", 1)[1]
    role = await _role(call.from_user.id)
    if role not in (ROLE_DIRECTOR, ROLE_ADMIN):
        await call.answer("⛔", show_alert=True)
        return
    if kind == "menu":
        try:
            await call.message.edit_text(
                "📑 <b>Hisobotlar</b>\n\nKerakli hisobotni tanlang:",
                reply_markup=kb.reports_menu_kb(),
            )
        except Exception:
            pass
        await call.answer()
        return
    if kind != "all" and kind not in REPORT_TITLES:
        await call.answer("Noma'lum hisobot.", show_alert=True)
        return
    if kind != "all" and not REPORT_NEEDS_PERIOD[kind]:
        # Davr kerak emas (joriy holat) — darhol tayyorlaymiz
        await call.answer("⏳ Tayyorlanmoqda...")
        rng = month_range(1)
        await send_report(bot, call.message.chat.id, kind, rng)
        await _log(call.from_user.id, kind, rng)
        return
    await call.message.answer(_period_prompt(kind), reply_markup=kb.report_period_kb(kind))
    await call.answer()


# ---------------- DAVR: 1/2/3 OYLIK ----------------
@router.callback_query(F.data.startswith("repp:"))
async def report_by_months(call: CallbackQuery, bot: Bot):
    try:
        _, kind, n = call.data.split(":")
        n = int(n)
    except ValueError:
        await call.answer("Noto'g'ri tugma.", show_alert=True)
        return
    if not _allowed(await _role(call.from_user.id), kind) or n not in kb.REPORT_MONTHS:
        await call.answer("⛔", show_alert=True)
        return
    await call.answer("⏳ Hisobot tayyorlanmoqda...")
    await _generate(bot, call.message.chat.id, call.from_user.id, kind, month_range(n))


async def _generate(bot, chat_id, tg_id, kind, rng):
    if kind == "all":
        await bot.send_message(chat_id, f"⏳ Barcha hisobotlar tayyorlanmoqda...\n📅 {rng.text}")
        await send_reports(bot, chat_id, [k for k, _, _ in DIRECTOR_REPORTS], rng)
    else:
        await send_report(bot, chat_id, kind, rng)
    await _log(tg_id, kind, rng)


# ---------------- DAVR: SANA BO'YICHA ----------------
@router.callback_query(F.data.startswith("repd:"))
async def report_by_dates_start(call: CallbackQuery, state: FSMContext):
    kind = call.data.split(":", 1)[1]
    if not _allowed(await _role(call.from_user.id), kind):
        await call.answer("⛔", show_alert=True)
        return
    await state.set_state(ReportRangeForm.start)
    await state.update_data(rep_kind=kind)
    today = now_tk()
    await call.message.answer(
        "🗓 <b>Boshlanish sanasini</b> yozing (qaysi kundan):\n"
        f"Format: <code>kk.oo.yyyy</code> — masalan <code>01.{today:%m.%Y}</code>",
        reply_markup=kb.report_cancel_kb(),
    )
    await call.answer()


@router.callback_query(F.data == "repcancel")
async def report_by_dates_cancel(call: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await call.message.answer("❌ Bekor qilindi.")
    await call.answer()


@router.message(ReportRangeForm.start, F.text)
async def report_by_dates_from(message: Message, state: FSMContext):
    start = parse_date(message.text)
    today = now_tk().date()
    if not start:
        await message.answer("❗ Sana noto'g'ri. Masalan: <code>01.09.2026</code>",
                             reply_markup=kb.report_cancel_kb())
        return
    if start > today:
        await message.answer("❗ Boshlanish sanasi kelajakda bo'lishi mumkin emas.",
                             reply_markup=kb.report_cancel_kb())
        return
    await state.update_data(rep_start=start.isoformat())
    await state.set_state(ReportRangeForm.end)
    await message.answer(
        f"✅ Boshlanish: <b>{start:%d.%m.%Y}</b>\n\n"
        "🗓 Endi <b>tugash sanasini</b> yozing (qaysi kungacha):\n"
        f"Masalan: <code>{today:%d.%m.%Y}</code> (bugun)",
        reply_markup=kb.report_cancel_kb(),
    )


@router.message(ReportRangeForm.end, F.text)
async def report_by_dates_to(message: Message, state: FSMContext, bot: Bot):
    from datetime import date
    end = parse_date(message.text)
    if not end:
        await message.answer("❗ Sana noto'g'ri. Masalan: <code>30.09.2026</code>",
                             reply_markup=kb.report_cancel_kb())
        return
    data = await state.get_data()
    start = date.fromisoformat(data["rep_start"])
    if end < start:
        await message.answer(
            f"❗ Tugash sanasi boshlanishdan (<b>{start:%d.%m.%Y}</b>) oldin bo'lmasin.",
            reply_markup=kb.report_cancel_kb())
        return
    end = min(end, now_tk().date())
    if (end - start).days + 1 > MAX_RANGE_DAYS:
        await message.answer(f"❗ Davr {MAX_RANGE_DAYS} kundan oshmasin.",
                             reply_markup=kb.report_cancel_kb())
        return
    kind = data.get("rep_kind")
    await state.clear()
    if not _allowed(await _role(message.from_user.id), kind):
        await message.answer("⛔")
        return
    rng = DateRange(start, end)
    await message.answer(f"⏳ Hisobot tayyorlanmoqda...\n📅 {rng.text}")
    await _generate(bot, message.chat.id, message.from_user.id, kind, rng)


# ---------------- OY OXIRI AVTOMATIK YUBORISH ----------------
async def send_monthly_reports(bot: Bot):
    """Direktorlarga barcha hisobotlar, moliya bo'limiga jarimalar (joriy oy).

    Har bir fayl bir marta tayyorlanadi va barcha oluvchilarga yuboriladi."""
    rng = month_range(1)
    directors = await q.all_user_tg_ids(role=ROLE_DIRECTOR)
    accountants = await q.all_user_tg_ids(role=ROLE_ACCOUNTANT)
    sent = 0
    for kind, title, _ in DIRECTOR_REPORTS:
        targets = list(directors)
        if kind == "fines":
            targets += [t for t in accountants if t not in targets]
        if not targets:
            continue
        doc, summary = await make_report(kind, rng)
        caption = f"🗓 <b>Oylik hisobot</b> · {title}\n\n{summary}"
        for tid in targets:
            try:
                await bot.send_document(
                    tid, BufferedInputFile(doc.data, filename=doc.filename),
                    caption=caption,
                )
                sent += 1
            except Exception:
                pass
    return sent
