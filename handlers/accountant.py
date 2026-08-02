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
from utils import (
    employee_profile_text, fine_text, safe_send, now_tk, send_employee_profile,
    parse_money, fmt_money,
)

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
    last = await q.latest_salary_payment(uid, _period_now())
    if last:
        mark = "✅ berilgan" if last.get("status") == "paid" else "❌ berilmagan"
        extra = f"\n\n🧾 Shu oy ({_period_now()}) oyligi: {mark}"
    else:
        extra = f"\n\n🧾 Shu oy ({_period_now()}) oyligi: ➖ belgilanmagan"
    await send_employee_profile(
        call.message, profile, reply_markup=kb.accountant_employee_kb(uid), suffix=extra
    )
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


# ================= OYLIKDAN FOIZ KESISH =================
# Filial rahbaridan 10%, oddiy xodimdan 5%. Kesim faqat joriy oyga yoziladi.
@router.message(F.text == "✂️ Oylik kesish")
async def deduction_start(message: Message):
    if not await _is_accountant(message.from_user.id):
        await message.answer("⛔ Sizda moliya bo'limi paneli uchun ruxsat yo'q.")
        return
    await message.answer(
        "✂️ <b>Oylik kesish</b>\n\n"
        f"Kimning oyligidan kesamiz?\n\n"
        f"👨‍💼 Filial rahbaridan — <b>{kb.DEDUCTION_PERCENT['manager']}%</b>\n"
        f"👷 Xodimdan — <b>{kb.DEDUCTION_PERCENT['employee']}%</b>\n\n"
        f"<i>Kesim faqat joriy oyga ({_period_now()}) yoziladi.</i>",
        reply_markup=kb.deduction_target_kb(),
    )


@router.callback_query(F.data == "ded:back")
async def deduction_back(call: CallbackQuery):
    if not await _is_accountant(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    await call.message.answer(
        "✂️ <b>Oylik kesish</b>\n\nKimning oyligidan kesamiz?",
        reply_markup=kb.deduction_target_kb(),
    )
    await call.answer()


@router.callback_query(F.data.startswith("ded:"))
async def deduction_pick_kind(call: CallbackQuery):
    """Rahbardan yoki xodimdan — keyin filial tanlanadi."""
    if not await _is_accountant(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    kind = call.data.split(":")[1]
    if kind not in kb.DEDUCTION_PERCENT:
        await call.answer()
        return
    branches = await q.list_branches()
    if not branches:
        await call.message.answer("🏢 Hali filiallar qo'shilmagan.")
        await call.answer()
        return
    who = "filial rahbari" if kind == "manager" else "xodim"
    await call.message.answer(
        f"🏢 Qaysi filialning {who}sidan kesamiz?\n"
        f"Filialni tanlang:",
        reply_markup=kb.deduction_branch_kb(branches, kind),
    )
    await call.answer()


@router.callback_query(F.data.startswith("dedbr:"))
async def deduction_pick_branch(call: CallbackQuery):
    """Filial tanlandi — rahbar(lar) yoki xodimlar ro'yxati chiqadi."""
    if not await _is_accountant(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    _, kind, bid = call.data.split(":")
    bid = int(bid)
    branch = await q.get_branch(bid)
    bname = branch["name"] if branch else f"#{bid}"

    if kind == "manager":
        people = await q.branch_managers(bid)
        if not people:
            await call.message.answer(
                f"🏢 <b>{bname}</b> filialiga rahbar biriktirilmagan."
            )
            await call.answer()
            return
        # Rahbar bitta bo'lsa — darhol kartochkasini ko'rsatamiz
        if len(people) == 1:
            await _show_deduction_card(call.message, people[0], kind)
            await call.answer()
            return
        await call.message.answer(
            f"🏢 <b>{bname}</b> — <b>{len(people)}</b> ta rahbar. Kimni tanlaysiz?",
            reply_markup=kb.deduction_people_kb(people, kind),
        )
        await call.answer()
        return

    people = await q.search_employees(branch_id=bid)
    if not people:
        await call.message.answer(f"🏢 <b>{bname}</b> filialida xodim yo'q.")
        await call.answer()
        return
    await call.message.answer(
        f"🏢 <b>{bname}</b> — <b>{len(people)}</b> ta xodim.\n"
        "Oyligidan kesiladigan xodimni tanlang:",
        reply_markup=kb.deduction_people_kb(people[:40], kind),
    )
    await call.answer()


@router.callback_query(F.data.startswith("dedemp:"))
async def deduction_pick_person(call: CallbackQuery):
    if not await _is_accountant(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    _, kind, uid = call.data.split(":")
    profile = await q.get_employee_profile(int(uid))
    if not profile:
        await call.answer("Xodim topilmadi.", show_alert=True)
        return
    await _show_deduction_card(call.message, profile, kind)
    await call.answer()


async def _show_deduction_card(target, profile, kind):
    """Rasm + ma'lumot + «N% kesish» tugmasi."""
    period = _period_now()
    pct = kb.DEDUCTION_PERCENT.get(kind, 5)
    base = parse_money(profile.get("monthly_salary"))
    already, cnt = await q.deductions_total(profile["user_id"], period)

    if base is None:
        extra = (
            f"\n\n⚠️ <b>Oylik belgilanmagan</b> — kesish uchun avval "
            "«👥 Xodimlar (oylik/jarima)» bo'limidan oylik kiriting."
        )
        await send_employee_profile(target, profile, suffix=extra)
        return

    amount = round(base * pct / 100)
    remaining = max(0, base - already - amount)
    extra = (
        f"\n\n✂️ <b>Kesish oldidan hisob</b>\n"
        f"📅 Davr: <b>{period}</b>\n"
        f"💰 Oylik: <b>{fmt_money(base)}</b>\n"
    )
    if already:
        extra += f"➖ Shu oyda allaqachon kesilgan: <b>{fmt_money(already)}</b> ({cnt} marta)\n"
    extra += (
        f"➖ Hozir kesiladi ({pct}%): <b>{fmt_money(amount)}</b>\n"
        f"✅ Qoladigan oylik: <b>{fmt_money(remaining)}</b>"
    )
    await send_employee_profile(
        target, profile,
        reply_markup=kb.deduction_confirm_kb(profile["user_id"], kind),
        suffix=extra,
    )


@router.callback_query(F.data.startswith("dedgo:"))
async def deduction_apply(call: CallbackQuery, bot: Bot):
    """Kesimni amalga oshiradi va xodimga xabar yuboradi."""
    if not await _is_accountant(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    _, kind, uid = call.data.split(":")
    uid = int(uid)
    profile = await q.get_employee_profile(uid)
    if not profile:
        await call.answer("Xodim topilmadi.", show_alert=True)
        return

    base = parse_money(profile.get("monthly_salary"))
    if base is None:
        await call.answer("Bu xodimning oyligi belgilanmagan.", show_alert=True)
        return

    period = _period_now()
    pct = kb.DEDUCTION_PERCENT.get(kind, 5)
    amount = round(base * pct / 100)
    already, _cnt = await q.deductions_total(uid, period)
    remaining = max(0, base - already - amount)

    me = await q.get_user(call.from_user.id)
    await q.add_salary_deduction(
        employee_user_id=uid,
        period=period,
        kind=kind,
        percent=pct,
        base_salary=profile.get("monthly_salary"),
        base_amount=base,
        amount=amount,
        remaining=remaining,
        branch_id=profile.get("branch_id"),
        created_by=me["id"] if me else None,
    )
    await q.add_log(
        call.from_user.id, me["full_name"] if me else "?", "oylik_kesildi",
        f"user#{uid} {period} -{pct}% = {amount}",
    )
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    # Moliya xodimiga hisobot
    await call.message.answer(
        f"✅ <b>Oylikdan {pct}% kesildi</b>\n"
        "━━━━━━━━━━━━\n"
        f"👤 {profile.get('full_name') or '-'}\n"
        f"💼 {profile.get('position') or '-'} · 🏢 {profile.get('branch_name') or '-'}\n"
        f"📅 Davr: <b>{period}</b>\n"
        f"💰 Oylik: <b>{fmt_money(base)}</b>\n"
        f"➖ Kesildi: <b>{fmt_money(amount)}</b>\n"
        f"✅ Qoladigan oylik: <b>{fmt_money(remaining)}</b>"
    )
    await call.answer(f"{pct}% kesildi ✅")

    # Xodimning o'ziga xabar (rahbar ham, oddiy xodim ham bir xil ko'radi)
    if profile.get("tg_id"):
        await safe_send(
            bot, profile["tg_id"],
            f"✂️ <b>Oyligingizdan {pct}% kesildi</b>\n"
            "━━━━━━━━━━━━\n"
            f"📅 Davr: <b>{period}</b>\n"
            f"💰 Oyligingiz: <b>{fmt_money(base)}</b>\n"
            f"➖ Kesilgan summa: <b>{fmt_money(amount)}</b>\n"
            f"✅ Siz oladigan oylik: <b>{fmt_money(remaining)}</b>\n"
            "━━━━━━━━━━━━\n"
            "Kesim <b>moliya bo'limi</b> tomonidan amalga oshirildi va "
            f"faqat <b>{period}</b> oyiga tegishli.\n"
            "Savollaringiz bo'lsa moliya bo'limiga murojaat qiling.",
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
