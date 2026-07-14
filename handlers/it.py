"""IT xodim paneli: kadrlar harakati oylik hisoboti (har oyning 14-sanasidan),
xodim ism-familiyasini o'zgartirish va boshqa filialga ko'chirish.

Hisobot davri — har oyning 14-sanasidan keyingi 14-sanasigacha. Panelda joriy
davr ma'lumoti ko'rsatiladi, har oyning 14-sanasida esa tugagan davr bo'yicha
hisobot barcha IT xodimlarga avtomatik yuboriladi (services/reminders.py).
"""
from datetime import datetime

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from database import queries as q
from database.db import ROLE_ADMIN, ROLE_IT
from states import ITForm
import keyboards as kb
from utils import safe_send, now_tk, iso_to_display

router = Router()


# ---------------- HISOBOT DAVRI (14 -> 14) ----------------
def period_start_for(dt):
    """dt tegishli bo'lgan hisobot davrining boshlanish sanasi (14-sana, 00:00)."""
    if dt.day >= 14:
        return datetime(dt.year, dt.month, 14)
    if dt.month == 1:
        return datetime(dt.year - 1, 12, 14)
    return datetime(dt.year, dt.month - 1, 14)


def prev_period_start(period_start):
    """Berilgan davr boshidan bir oy oldingi 14-sana."""
    if period_start.month == 1:
        return datetime(period_start.year - 1, 12, 14)
    return datetime(period_start.year, period_start.month - 1, 14)


def _iso(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S")


async def build_report_text(start_dt, end_dt=None):
    """Kadrlar harakati hisobot matni. end_dt=None bo'lsa — hozirgacha."""
    start_iso = _iso(start_dt)
    end_iso = _iso(end_dt) if end_dt else None
    counts = await q.hr_event_counts(start_iso, end_iso)
    active_prob = await q.count_active_probations()

    if end_dt:
        period_line = (
            f"🗓 Davr: <b>{start_dt.strftime('%d.%m.%Y')} — "
            f"{end_dt.strftime('%d.%m.%Y')}</b>"
        )
    else:
        period_line = (
            f"🗓 Davr: <b>{start_dt.strftime('%d.%m.%Y')} — hozirgacha</b>"
        )

    lines = [
        "📊 <b>Kadrlar harakati hisoboti</b>",
        period_line,
        "━━━━━━━━━━━━",
        f"🟢 Ishga kirdi: <b>{counts['hired']}</b>",
        f"🔴 Ishdan ketdi: <b>{counts['left']}</b>",
        f"🔄 Boshqa filialga ko'chirildi: <b>{counts['transferred']}</b>",
        f"🧪 Sinovdagi xodimlar (hozirda): <b>{active_prob}</b>",
        f"✏️ Ism o'zgartirishlar: <b>{counts['name_changed']}</b>",
    ]
    return "\n".join(lines)


async def notify_it_users(bot: Bot, text: str):
    """Barcha IT xodim va adminlarga xabar yuboradi (takrorsiz)."""
    ids = set(await q.all_user_tg_ids(role=ROLE_IT))
    ids |= set(await q.all_user_tg_ids(role=ROLE_ADMIN))
    for tid in ids:
        await safe_send(bot, tid, text)


async def _is_it(tg_id):
    u = await q.get_user(tg_id)
    return u and u["role"] in (ROLE_IT, ROLE_ADMIN)


# ---------------- PANEL ----------------
@router.message(F.text == "🖥 IT xodim panel")
async def it_panel(message: Message, state: FSMContext):
    if not await _is_it(message.from_user.id):
        await message.answer("⛔ Sizda IT xodim paneli uchun ruxsat yo'q.")
        return
    await state.clear()
    await message.answer(
        "🖥 <b>IT xodim paneli</b>\nKerakli bo'limni tanlang:",
        reply_markup=kb.it_menu(),
    )


@router.message(F.text == "📊 Oylik hisobot (14-sana)")
async def it_report(message: Message):
    if not await _is_it(message.from_user.id):
        return
    start = period_start_for(now_tk())
    text = await build_report_text(start, end_dt=None)
    await message.answer(text)


# ---------------- XODIMLAR (ism / filial) ----------------
@router.message(F.text == "👥 Xodimlar")
async def it_employees(message: Message):
    if not await _is_it(message.from_user.id):
        return
    employees = await q.list_employee_profiles()
    if not employees:
        await message.answer("Hali xodim profillari yo'q.")
        return
    await message.answer(
        f"👥 <b>Xodimlar</b>\n\nJami: <b>{len(employees)}</b> ta\n"
        "Ism yoki filialni o'zgartirish uchun xodimni tanlang:",
        reply_markup=kb.employee_profiles_list_kb(employees[:30], prefix="itemp"),
    )


@router.callback_query(F.data.startswith("itemp:"))
async def it_employee_view(call: CallbackQuery):
    if not await _is_it(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    uid = int(call.data.split(":")[1])
    profile = await q.get_employee_profile(uid)
    if not profile:
        await call.answer("Xodim topilmadi.", show_alert=True)
        return
    text = (
        f"👤 <b>{profile.get('full_name') or '-'}</b>\n"
        f"💼 Lavozim: {profile.get('position') or '-'}\n"
        f"🏢 Filial: {profile.get('branch_name') or '—'}"
    )
    await call.message.answer(text, reply_markup=kb.it_employee_kb(uid))
    await call.answer()


# ---- Ismni o'zgartirish ----
@router.callback_query(F.data.startswith("itren:"))
async def it_rename_start(call: CallbackQuery, state: FSMContext):
    if not await _is_it(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    uid = int(call.data.split(":")[1])
    profile = await q.get_employee_profile(uid)
    if not profile:
        await call.answer("Xodim topilmadi.", show_alert=True)
        return
    await state.update_data(it_uid=uid)
    await state.set_state(ITForm.rename)
    await call.message.answer(
        f"✏️ <b>{profile.get('full_name') or 'Xodim'}</b> uchun yangi ism-familiyani yozing:"
    )
    await call.answer()


@router.message(ITForm.rename, F.text)
async def it_rename_save(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    uid = data.get("it_uid")
    await state.clear()
    new_name = message.text.strip()
    if len(new_name) < 3:
        await message.answer("❗️ Ism juda qisqa. Qayta urinib ko'ring.")
        return
    me = await q.get_user(message.from_user.id)
    old_name = await q.rename_user(uid, new_name)
    await q.add_hr_event(
        "name_changed", user_id=uid, full_name=new_name,
        old_value=old_name, new_value=new_name, created_by=me["id"] if me else None,
    )
    await q.add_log(
        message.from_user.id, me["full_name"] if me else "?",
        "ism_ozgartirdi", f"user#{uid}: {old_name} -> {new_name}",
    )
    await message.answer(
        f"✅ Ism o'zgartirildi:\n<s>{old_name or '-'}</s> → <b>{new_name}</b>"
    )
    # IT paneliga (barcha IT xodim/adminlarga) yangi ism haqida xabar
    await notify_it_users(
        bot,
        "✏️ <b>Xodim ism-familiyasi o'zgardi</b>\n"
        f"Eski: {old_name or '-'}\n"
        f"Yangi: <b>{new_name}</b>\n"
        f"O'zgartirdi: {me['full_name'] if me else '-'}",
    )
    # Xodimning o'ziga ham xabar
    profile = await q.get_employee_profile(uid)
    if profile and profile.get("tg_id"):
        await safe_send(
            bot, profile["tg_id"],
            f"ℹ️ Sizning ism-familiyangiz yangilandi: <b>{new_name}</b>",
        )


# ---- Boshqa filialga ko'chirish ----
@router.callback_query(F.data.startswith("itmove:"))
async def it_move_start(call: CallbackQuery):
    if not await _is_it(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    uid = int(call.data.split(":")[1])
    branches = await q.list_branches()
    if not branches:
        await call.answer("Filiallar yo'q.", show_alert=True)
        return
    await call.message.answer(
        "🔄 Xodim <b>qaysi filialga</b> ko'chiriladi?",
        reply_markup=kb.it_branch_pick_kb(branches, uid),
    )
    await call.answer()


@router.callback_query(F.data.startswith("itmovebr:"))
async def it_move_save(call: CallbackQuery, bot: Bot):
    if not await _is_it(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    _, uid, bid = call.data.split(":")
    uid, bid = int(uid), int(bid)
    profile = await q.get_employee_profile(uid)
    if not profile:
        await call.answer("Xodim topilmadi.", show_alert=True)
        return
    old_branch_id = profile.get("branch_id")
    old_branch = await q.get_branch(old_branch_id) if old_branch_id else None
    new_branch = await q.get_branch(bid)
    if old_branch_id == bid:
        await call.answer("Xodim allaqachon shu filialda.", show_alert=True)
        return
    me = await q.get_user(call.from_user.id)
    await q.set_employee_branch(uid, bid)
    old_name = old_branch["name"] if old_branch else "—"
    new_name = new_branch["name"] if new_branch else "—"
    await q.add_hr_event(
        "transferred", user_id=uid, full_name=profile.get("full_name"),
        old_value=old_name, new_value=new_name, branch_id=bid,
        created_by=me["id"] if me else None,
    )
    await q.add_log(
        call.from_user.id, me["full_name"] if me else "?",
        "filial_kochirdi", f"user#{uid}: {old_name} -> {new_name}",
    )
    await call.message.answer(
        f"✅ <b>{profile.get('full_name') or 'Xodim'}</b> ko'chirildi:\n"
        f"{old_name} → <b>{new_name}</b>"
    )
    await call.answer("Ko'chirildi ✅")
    if profile.get("tg_id"):
        await safe_send(
            bot, profile["tg_id"],
            f"🔄 Siz <b>{new_name}</b> filialiga ko'chirildingiz.",
        )


# ---------------- ISM O'ZGARTIRISHLAR TARIXI ----------------
@router.message(F.text == "✏️ Ism o'zgartirishlar")
async def it_name_changes(message: Message):
    if not await _is_it(message.from_user.id):
        return
    start = period_start_for(now_tk())
    events = await q.list_hr_events("name_changed", _iso(start), limit=50)
    if not events:
        await message.answer(
            "✏️ <b>Ism o'zgartirishlar</b>\n\nJoriy davrda o'zgartirishlar yo'q."
        )
        return
    lines = ["✏️ <b>Ism o'zgartirishlar (joriy davr)</b>", "━━━━━━━━━━━━"]
    for e in events:
        lines.append(
            f"• {e.get('old_value') or '-'} → <b>{e.get('new_value') or '-'}</b>"
            f"  ({(e.get('created_at') or '')[:16]})"
        )
    await message.answer("\n".join(lines))
