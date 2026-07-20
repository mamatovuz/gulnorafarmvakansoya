"""Buxgalter (accountant) paneli: davomat (filial kesimida), oylik belgilash/oshirish,
oylik berildi/berilmadi, jarima yozish."""
from datetime import datetime

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from database import queries as q
from database.db import ROLE_ADMIN, ROLE_ACCOUNTANT
from states import AccForm
import keyboards as kb
from utils import employee_profile_text, fine_text, safe_send, now_tk

router = Router()


def _period_now():
    return now_tk().strftime("%Y-%m")


async def _is_accountant(tg_id):
    u = await q.get_user(tg_id)
    return u and u["role"] in (ROLE_ACCOUNTANT, ROLE_ADMIN)


@router.message(F.text == "🧮 Moliya bo'limi")
async def accountant_panel(message: Message):
    if not await _is_accountant(message.from_user.id):
        await message.answer("⛔ Sizda moliya bo'limi paneli uchun ruxsat yo'q.")
        return
    await message.answer(
        "🧮 <b>Moliya bo'limi paneli</b>\nKerakli bo'limni tanlang:",
        reply_markup=kb.accountant_menu(),
    )


# ---------------- FILIAL TANLAB KO'RISH ----------------
@router.message(F.text == "🏢 Filial tanlab ko'rish")
async def acc_pick_branch(message: Message):
    if not await _is_accountant(message.from_user.id):
        return
    branches = await q.list_branches()
    if not branches:
        await message.answer("Hali filiallar qo'shilmagan.")
        return
    await message.answer(
        "🏢 Qaysi filialni ko'rmoqchisiz?",
        reply_markup=kb.accountant_branch_kb(branches),
    )


@router.callback_query(F.data.startswith("accbr:"))
async def acc_branch_view(call: CallbackQuery):
    if not await _is_accountant(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    bid = int(call.data.split(":")[1])
    branch = await q.get_branch(bid)
    employees = await q.list_employee_profiles(branch_id=bid)
    present = await q.attendance_present_by_employee(period="day", branch_id=bid)
    absent = await q.attendance_absent_today(branch_id=bid)
    lines = [
        f"🏢 <b>{branch['name'] if branch else 'Filial'}</b>",
        "━━━━━━━━━━━━",
        f"👥 Xodimlar: <b>{len(employees)}</b>",
        f"✅ Bugun kelgan: <b>{len(present)}</b>",
        f"❌ Bugun kelmagan: <b>{len(absent)}</b>",
        "",
        "Xodimni tanlab oylik/jarima kiritishingiz mumkin 👇",
    ]
    await call.message.answer("\n".join(lines))
    if employees:
        await call.message.answer(
            "👥 Filial xodimlari:",
            reply_markup=kb.employee_profiles_list_kb(employees[:30], prefix="accemp"),
        )
    await call.answer()


# ---------------- XODIMLAR (OYLIK/JARIMA) ----------------
@router.message(F.text == "👥 Xodimlar (oylik/jarima)")
async def acc_employees(message: Message):
    if not await _is_accountant(message.from_user.id):
        return
    employees = await q.list_employee_profiles()
    if not employees:
        await message.answer("Hali xodim profillari yo'q.")
        return
    await message.answer(
        f"👥 <b>Xodimlar</b>\n\nJami: <b>{len(employees)}</b> ta\nTanlang:",
        reply_markup=kb.employee_profiles_list_kb(employees[:30], prefix="accemp"),
    )


@router.callback_query(F.data.startswith("accemp:"))
async def acc_employee_view(call: CallbackQuery):
    if not await _is_accountant(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    uid = int(call.data.split(":")[1])
    profile = await q.get_employee_profile(uid)
    if not profile:
        await call.answer("Xodim topilmadi.", show_alert=True)
        return
    text = employee_profile_text(profile)
    last = await q.latest_salary_payment(uid, _period_now())
    if last:
        mark = "✅ berilgan" if last.get("status") == "paid" else "❌ berilmagan"
        text += f"\n\n🧾 Shu oy ({_period_now()}) oyligi: {mark}"
    else:
        text += f"\n\n🧾 Shu oy ({_period_now()}) oyligi: ➖ belgilanmagan"
    await call.message.answer(text, reply_markup=kb.accountant_employee_kb(uid))
    await call.answer()


# ---- Oylik belgilash ----
@router.callback_query(F.data.startswith("accsal:"))
async def acc_salary_start(call: CallbackQuery, state: FSMContext):
    if not await _is_accountant(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    uid = int(call.data.split(":")[1])
    await state.update_data(acc_uid=uid, acc_action="set")
    await state.set_state(AccForm.salary)
    await call.message.answer("💰 Yangi oylik miqdorini yozing.\nMisol: <i>5 000 000</i>")
    await call.answer()


@router.callback_query(F.data.startswith("accraise:"))
async def acc_raise_start(call: CallbackQuery, state: FSMContext):
    if not await _is_accountant(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    uid = int(call.data.split(":")[1])
    profile = await q.get_employee_profile(uid)
    cur = (profile or {}).get("monthly_salary") or "belgilanmagan"
    await state.update_data(acc_uid=uid, acc_action="raise")
    await state.set_state(AccForm.salary)
    await call.message.answer(
        f"⬆️ Hozirgi oylik: <b>{cur}</b>\nYangi (oshirilgan) oylik miqdorini yozing:"
    )
    await call.answer()


@router.message(AccForm.salary, F.text)
async def acc_salary_save(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    uid = data.get("acc_uid")
    await state.clear()
    value = message.text.strip()
    await q.update_monthly_salary(uid, value)
    me = await q.get_user(message.from_user.id)
    action = "oylik_oshirdi" if data.get("acc_action") == "raise" else "oylik_belgiladi"
    await q.add_log(message.from_user.id, me["full_name"], action, f"user#{uid} -> {value}")
    await message.answer(f"✅ Oylik yangilandi: <b>{value}</b>")
    profile = await q.get_employee_profile(uid)
    if profile and profile.get("tg_id"):
        await safe_send(
            bot, profile["tg_id"],
            f"💰 Sizning oyligingiz yangilandi: <b>{value}</b>",
        )


# ---- Oylik berildi / berilmadi ----
@router.callback_query(F.data.startswith("accpaid:"))
async def acc_mark_paid(call: CallbackQuery, bot: Bot):
    if not await _is_accountant(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    _, uid, status = call.data.split(":")
    uid = int(uid)
    profile = await q.get_employee_profile(uid)
    me = await q.get_user(call.from_user.id)
    amount = (profile or {}).get("monthly_salary")
    await q.add_salary_payment(uid, _period_now(), amount, status, None, me["id"])
    await q.add_log(
        call.from_user.id, me["full_name"], "oylik_tolov",
        f"user#{uid} {_period_now()} -> {status}"
    )
    label = "✅ berildi" if status == "paid" else "❌ berilmadi deb belgilandi"
    await call.answer(f"Saqlandi: {label}", show_alert=True)
    await call.message.answer(
        f"🧾 {profile.get('full_name') if profile else uid} — "
        f"{_period_now()} oyligi: <b>{label}</b>"
    )
    if status == "paid" and profile and profile.get("tg_id"):
        await safe_send(
            bot, profile["tg_id"],
            f"💵 {_period_now()} oyligingiz to'landi." + (f" ({amount})" if amount else ""),
        )


@router.callback_query(F.data.startswith("accpayhist:"))
async def acc_pay_history(call: CallbackQuery):
    if not await _is_accountant(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    uid = int(call.data.split(":")[1])
    payments = await q.list_salary_payments(uid)
    if not payments:
        await call.answer("To'lovlar tarixi yo'q.", show_alert=True)
        return
    lines = ["🧾 <b>Oylik to'lovlari tarixi</b>", "━━━━━━━━━━━━"]
    for p in payments:
        mark = "✅" if p.get("status") == "paid" else "❌"
        lines.append(f"{mark} {p.get('period')} · {p.get('amount') or '-'} · {p.get('created_at')}")
    await call.message.answer("\n".join(lines))
    await call.answer()


# ---- Jarima ----
@router.callback_query(F.data.startswith("accfine:"))
async def acc_fine_start(call: CallbackQuery, state: FSMContext):
    if not await _is_accountant(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    uid = int(call.data.split(":")[1])
    await state.update_data(acc_uid=uid)
    await state.set_state(AccForm.fine_amount)
    await call.message.answer("💸 Jarima miqdorini yozing.\nMisol: <i>200 000</i>")
    await call.answer()


@router.message(AccForm.fine_amount, F.text)
async def acc_fine_amount(message: Message, state: FSMContext):
    await state.update_data(fine_amount=message.text.strip())
    await state.set_state(AccForm.fine_reason)
    await message.answer("✍️ Jarima sababini yozing:")


@router.message(AccForm.fine_reason, F.text)
async def acc_fine_save(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    uid = data.get("acc_uid")
    amount = data.get("fine_amount")
    reason = message.text.strip()
    await state.clear()
    me = await q.get_user(message.from_user.id)
    await q.add_fine(uid, amount, reason, me["id"])
    await q.add_log(message.from_user.id, me["full_name"], "jarima_yozdi", f"user#{uid} {amount}")
    await message.answer(f"✅ Jarima yozildi: <b>{amount}</b>\nSabab: {reason}")
    profile = await q.get_employee_profile(uid)
    if profile and profile.get("tg_id"):
        await safe_send(
            bot, profile["tg_id"],
            f"💸 Sizga jarima yozildi: <b>{amount}</b>\nSabab: {reason}",
        )


@router.callback_query(F.data.startswith("accfines:"))
async def acc_fines_list(call: CallbackQuery):
    if not await _is_accountant(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    uid = int(call.data.split(":")[1])
    fines = await q.list_fines(uid)
    if not fines:
        await call.answer("Jarimalar yo'q.", show_alert=True)
        return
    await call.message.answer(
        f"💸 <b>Jarimalar</b> ({len(fines)} ta):",
        reply_markup=kb.fines_list_kb(fines, prefix="accfv"),
    )
    await call.answer()


@router.callback_query(F.data.startswith("accfv:"))
async def acc_fine_view(call: CallbackQuery):
    if not await _is_accountant(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    fine = await q.get_fine(int(call.data.split(":")[1]))
    if not fine:
        await call.answer("Jarima topilmadi.", show_alert=True)
        return
    await call.message.answer(fine_text(fine))
    await call.answer()
