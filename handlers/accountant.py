"""Buxgalter (accountant) paneli: davomat (filial kesimida), oylik belgilash/oshirish,
oylik berildi/berilmadi, jarima yozish, dori yozish va yakuniy oylik hisoblash."""
from datetime import datetime, date
from calendar import monthrange

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
    lines = [
        f"🏢 <b>{branch['name'] if branch else 'Filial'}</b>",
        "━━━━━━━━━━━━",
        f"👥 Xodimlar: <b>{len(employees)}</b>",
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
    profile = await q.get_employee_profile(uid)
    await q.add_fine(
        uid, amount, reason, me["id"],
        branch_id=(profile or {}).get("branch_id"), source="finance",
    )
    await q.add_log(message.from_user.id, me["full_name"], "jarima_yozdi", f"user#{uid} {amount}")
    await message.answer(
        f"✅ Jarima yozildi: <b>{amount}</b>\nSabab: {reason}\n\n"
        "<i>Bu summa yakuniy oylikdan ayiriladi.</i>"
    )
    if profile and profile.get("tg_id"):
        await safe_send(
            bot, profile["tg_id"],
            f"💸 Sizga jarima yozildi: <b>{amount}</b>\nSabab: {reason}\n\n"
            "Bu summa oyligingizdan ayiriladi.",
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


# ---- Dori yozish (dorixonadan olingan dorilar) ----
@router.callback_query(F.data.startswith("accmed:"))
async def acc_med_start(call: CallbackQuery, state: FSMContext):
    if not await _is_accountant(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    uid = int(call.data.split(":")[1])
    await state.update_data(acc_uid=uid)
    await state.set_state(AccForm.med_amount)
    await call.message.answer(
        "💊 Dorixonadan olingan <b>dori qiymatini</b> yozing (so'm).\n"
        "Misol: <i>150 000</i>"
    )
    await call.answer()


@router.message(AccForm.med_amount, F.text)
async def acc_med_amount(message: Message, state: FSMContext):
    amount = parse_money(message.text)
    if not amount:
        await message.answer("❌ Summani raqam bilan yozing. Misol: <i>150 000</i>")
        return
    await state.update_data(med_amount=amount)
    await state.set_state(AccForm.med_reason)
    await message.answer("✍️ Qanday dori? Qisqa izoh yozing (yoki «-»):")


@router.message(AccForm.med_reason, F.text)
async def acc_med_save(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    uid = data.get("acc_uid")
    amount = data.get("med_amount")
    reason = message.text.strip()
    await state.clear()
    profile = await q.get_employee_profile(uid)
    me = await q.get_user(message.from_user.id)
    await q.add_medicine(
        uid, (profile or {}).get("branch_id"), _period_now(),
        amount, reason, me["id"],
    )
    await q.add_log(
        message.from_user.id, me["full_name"], "dori_yozdi",
        f"user#{uid} {amount}",
    )
    await message.answer(
        f"✅ Dori yozildi: <b>{fmt_money(amount)}</b>\n"
        f"💊 Izoh: {reason}\n\n"
        "Bu summa yakuniy oylikdan ayiriladi."
    )
    if profile and profile.get("tg_id"):
        await safe_send(
            bot, profile["tg_id"],
            f"💊 Dorixonadan olingan dori qiymati yozildi: <b>{fmt_money(amount)}</b>\n"
            f"Izoh: {reason}\n\nBu summa oyligingizdan ayiriladi.",
        )


@router.callback_query(F.data.startswith("accmeds:"))
async def acc_meds_list(call: CallbackQuery):
    if not await _is_accountant(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    uid = int(call.data.split(":")[1])
    meds = await q.list_medicines(uid)
    if not meds:
        await call.answer("Dori yozuvlari yo'q.", show_alert=True)
        return
    lines = [f"💊 <b>Dorilar</b> ({len(meds)} ta):", "━━━━━━━━━━━━"]
    for m in meds:
        d = (m.get("created_at") or "")[:10]
        reason = m.get("reason") or "-"
        lines.append(f"• {fmt_money(m.get('amount'))} · {reason} · {d}")
    await call.message.answer("\n".join(lines))
    await call.answer()


# ================= YAKUNIY OYLIK HISOBLASH =================
# Kunlik stavka = oylik ÷ 30. Kelmagan kun × kunlik, kechikkan kun × kunlik/2.
_REST_WEEKDAY = {
    "Dushanba": 0, "Seshanba": 1, "Chorshanba": 2, "Payshanba": 3,
    "Juma": 4, "Shanba": 5, "Yakshanba": 6,
}


def _rest_weekday(rest_day):
    """Kanonik dam olish kunini Python hafta kuniga (Dush=0..Yaksh=6) o'giradi.

    «🚫 yo'q» yoki noma'lum bo'lsa None — hech qanday kun dam deb hisoblanmaydi."""
    return _REST_WEEKDAY.get((rest_day or "").strip())


def _month_workdays(period, rest_wd, today, upto_today=True):
    """Oydagi ish kunlari soni — dam olish kunlaridan tashqari.

    upto_today=True  => faqat bugungacha (kutilgan davomat uchun).
    upto_today=False => butun oy bo'yicha (kunlik stavka mahraji uchun).
    """
    year, month = map(int, period.split("-"))
    last_day = monthrange(year, month)[1]
    if upto_today:
        if (year, month) > (today.year, today.month):
            return 0                  # kelajakdagi oy
        end_day = today.day if (today.year, today.month) == (year, month) else last_day
    else:
        end_day = last_day
    count = 0
    for d in range(1, end_day + 1):
        if rest_wd is None or date(year, month, d).weekday() != rest_wd:
            count += 1
    return count


def _workday_seconds(work_hours):
    """Ish kuni davomiyligi (sekund). «09:00-18:00» => 32400. Aniqlanmasa 8 soat."""
    import re
    times = re.findall(r"(\d{1,2}):(\d{2})", work_hours or "")
    if len(times) < 2:
        return 8 * 3600
    start = int(times[0][0]) * 3600 + int(times[0][1]) * 60
    end = int(times[1][0]) * 3600 + int(times[1][1]) * 60
    diff = end - start
    if diff <= 0:
        diff += 24 * 3600
    return diff or 8 * 3600


def _fmt_hms(seconds):
    """Sekundni «1 soat 5 daqiqa» ko'rinishida yozadi."""
    seconds = int(seconds or 0)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    parts = []
    if h:
        parts.append(f"{h} soat")
    if m:
        parts.append(f"{m} daqiqa")
    if s or not parts:
        parts.append(f"{s} soniya")
    return " ".join(parts)


async def _compute_final_salary(uid):
    """Yakuniy oylikni chegirmalar bilan hisoblaydi. Dict qaytaradi.

    Chegirmalar: jarimalar, olingan avans, dorilar va KPI kesish. Davomat
    (kelmagan kun / kechikish) tizimdan olib tashlangani uchun endi
    hisobga olinmaydi."""
    profile = await q.get_employee_profile(uid)
    period = _period_now()
    base = parse_money((profile or {}).get("monthly_salary")) or 0

    fines_sum = await q.fines_total(uid, period)
    advance_sum = await q.advance_total(uid, period)
    med_sum, med_cnt = await q.medicines_total(uid, period)
    kpi_sum, kpi_cnt = await q.deductions_total(uid, period)

    final = base - fines_sum - advance_sum - med_sum - kpi_sum
    return {
        "profile": profile, "period": period, "base": base,
        "fines_sum": fines_sum, "advance_sum": advance_sum,
        "med_sum": med_sum, "med_cnt": med_cnt,
        "kpi_sum": kpi_sum, "kpi_cnt": kpi_cnt,
        "final": max(0, round(final)),
    }


@router.callback_query(F.data.startswith("accfinal:"))
async def acc_final_salary(call: CallbackQuery):
    if not await _is_accountant(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    uid = int(call.data.split(":")[1])
    r = await _compute_final_salary(uid)
    profile = r["profile"]
    if not profile:
        await call.answer("Xodim topilmadi.", show_alert=True)
        return
    name = profile.get("full_name") or "-"
    if not r["base"]:
        await call.message.answer(
            f"🧮 <b>Yakuniy oylik — {name}</b>\n\n"
            "⚠️ <b>Oylik belgilanmagan.</b> Avval «💰 Oylik belgilash» "
            "orqali oylik kiriting."
        )
        await call.answer()
        return

    await call.message.answer(_final_salary_text(r, name))
    await call.answer()


def _final_salary_text(r, name, for_employee=False):
    """Yakuniy oylik hisobini chiroyli matn qilib qaytaradi.

    for_employee=True bo'lsa — xodimning o'ziga yuboriladigan variant."""
    def line(label, value):
        return f"➖ {label}: <b>{fmt_money(value)}</b>" if value else None

    head = "🧮 <b>Oylik hisobi</b>" if not for_employee else "🧾 <b>Oylik hisobotingiz</b>"
    parts = [
        head,
        f"👤 {name} · 📆 {r['period']}",
        "━━━━━━━━━━━━",
        f"💰 Asosiy oylik: <b>{fmt_money(r['base'])}</b>",
    ]
    ded_lines = [
        line("Jarimalar", r["fines_sum"]),
        line("Olingan avans", r["advance_sum"]),
        line("Dorilar", r["med_sum"]),
        line(f"KPI kesish ({r['kpi_cnt']} ta)", r["kpi_sum"]),
    ]
    ded_lines = [x for x in ded_lines if x]
    if ded_lines:
        parts.append("")
        parts.append("<b>Chegirmalar:</b>")
        parts += ded_lines
    else:
        parts.append("\n✅ Chegirmalar yo'q.")
    parts += [
        "━━━━━━━━━━━━",
        f"✅ <b>Qo'lga tegadigan oylik: {fmt_money(r['final'])}</b>",
    ]
    if for_employee:
        parts.append(
            "\n<i>Jarima, avans, dori va KPI kesish hisobga olindi. "
            "Savollar bo'lsa moliya bo'limiga murojaat qiling.</i>"
        )
    return "\n".join(parts)


# ---- Xodimga oylik hisobotini yuborish (oy oxirida yoki qo'lda) ----
@router.callback_query(F.data.startswith("accsendreport:"))
async def acc_send_report(call: CallbackQuery, bot: Bot):
    """Yakuniy oylik hisobotini xodimning o'ziga yuboradi."""
    if not await _is_accountant(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    uid = int(call.data.split(":")[1])
    r = await _compute_final_salary(uid)
    profile = r["profile"]
    if not profile or not r["base"]:
        await call.answer("Oylik belgilanmagan — hisobot yuborilmadi.", show_alert=True)
        return
    if not profile.get("tg_id"):
        await call.answer("Xodimning Telegram akkaunti ulanmagan.", show_alert=True)
        return
    text = _final_salary_text(r, profile.get("full_name") or "-", for_employee=True)
    ok = await safe_send(bot, profile["tg_id"], text)
    await call.answer("📨 Hisobot yuborildi ✅" if ok else "Yuborilmadi ❌",
                      show_alert=not ok)


# ================= JARIMANI BEKOR QILISH =================
# Moliya bo'limi jarimani bekor qiladi — oylikdan kesilgani avtomatik
# qaytariladi (yakuniy oylik cancelled=0 jarimalarnigina hisoblaydi) va
# xodimga xabar boradi.
async def _show_fine_cancel_list(target, rows, header=None):
    if not rows:
        await target.answer(
            "✅ Hozircha bekor qilinadigan (faol) jarimasi bor xodim yo'q."
        )
        return
    await target.answer(
        header or (
            f"🚫 <b>Jarimani bekor qilish</b>\n\n"
            f"Faol jarimasi bor xodimlar: <b>{len(rows)}</b> ta.\n"
            "Yuqoridagi 🔍 tugma orqali filial/ism/username/ID bo'yicha qidirishingiz "
            "mumkin. Xodimni tanlang:"
        ),
        reply_markup=kb.fine_cancel_people_kb(rows),
    )


@router.message(F.text == "🚫 Jarimani bekor qilish")
async def fine_cancel_start(message: Message, state: FSMContext):
    if not await _is_accountant(message.from_user.id):
        await message.answer("⛔ Sizda moliya bo'limi paneli uchun ruxsat yo'q.")
        return
    await state.clear()
    rows = await q.employees_with_fines(limit=60)
    await _show_fine_cancel_list(message, rows)


@router.callback_query(F.data == "fcfind")
async def fine_cancel_find(call: CallbackQuery, state: FSMContext):
    if not await _is_accountant(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    await state.set_state(AccForm.fine_cancel_search)
    await call.message.answer(
        "🔤 <b>Filial nomi</b>, <b>ism</b>, <b>username</b> yoki <b>ID</b> yozing:"
    )
    await call.answer()


@router.message(AccForm.fine_cancel_search, F.text)
async def fine_cancel_search_run(message: Message, state: FSMContext):
    if not await _is_accountant(message.from_user.id):
        await state.clear()
        return
    await state.clear()
    text = message.text.strip()
    # Avval filial nomiga mos kelsa — o'sha filialning jarimalilarini olamiz
    branch_id = None
    branches = await q.list_branches()
    for br in branches:
        if text.lower() in (br["name"] or "").lower():
            branch_id = br["id"]
            break
    if branch_id:
        rows = await q.employees_with_fines(branch_id=branch_id, limit=60)
    else:
        rows = await q.employees_with_fines(text=text, limit=60)
    if not rows:
        await message.answer(
            f"😔 «{text}» bo'yicha faol jarimasi bor xodim topilmadi."
        )
        return
    await _show_fine_cancel_list(
        message, rows,
        header=f"🔍 <b>Qidiruv:</b> {text} — <b>{len(rows)}</b> ta topildi\nTanlang:",
    )


@router.callback_query(F.data.startswith("fcperson:"))
async def fine_cancel_person(call: CallbackQuery):
    if not await _is_accountant(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    uid = int(call.data.split(":")[1])
    profile = await q.get_employee_profile(uid)
    fines = await q.list_fines(uid)
    if not fines:
        await call.answer("Bu xodimda faol jarima yo'q.", show_alert=True)
        return
    total = sum(q._digits_to_int(f.get("amount")) for f in fines)
    extra = (
        f"\n\n💸 <b>Faol jarimalar:</b> {len(fines)} ta · "
        f"jami <b>{fmt_money(total)}</b>\n"
        "Bekor qilish uchun kerakli jarimani tanlang 👇"
    )
    if profile:
        await send_employee_profile(
            call.message, profile,
            reply_markup=kb.fine_cancel_list_kb(fines, uid), suffix=extra,
        )
    else:
        await call.message.answer(
            "Xodim profili topilmadi." + extra,
            reply_markup=kb.fine_cancel_list_kb(fines, uid),
        )
    await call.answer()


@router.callback_query(F.data.startswith("fcancel:"))
async def fine_cancel_apply(call: CallbackQuery, bot: Bot):
    if not await _is_accountant(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    fid = int(call.data.split(":")[1])
    fine = await q.get_fine(fid)
    if not fine:
        await call.answer("Jarima topilmadi.", show_alert=True)
        return
    if fine.get("cancelled"):
        await call.answer("Bu jarima allaqachon bekor qilingan.", show_alert=True)
        return
    me = await q.get_user(call.from_user.id)
    ok = await q.cancel_fine(fid, me["id"] if me else None)
    if not ok:
        await call.answer("Bu jarima allaqachon bekor qilingan.", show_alert=True)
        return
    await q.add_log(
        call.from_user.id, me["full_name"] if me else "?", "jarima_bekor",
        f"fine#{fid} user#{fine.get('employee_user_id')} {fine.get('amount')}",
    )
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await call.message.answer(
        f"✅ <b>Jarima bekor qilindi</b>\n"
        f"👤 {fine.get('employee_name') or '-'}\n"
        f"💸 Summa: <b>{fine.get('amount')}</b>\n"
        f"✍️ Sabab (asl): {fine.get('reason') or '-'}\n\n"
        "Bu summa yakuniy oylikdan endi ayirilmaydi (oylikka qaytarildi)."
    )
    await call.answer("Bekor qilindi ✅")
    if fine.get("employee_tg"):
        await safe_send(
            bot, fine["employee_tg"],
            f"♻️ <b>Jarimangiz bekor qilindi</b>\n\n"
            f"💸 Summa: <b>{fine.get('amount')}</b>\n"
            f"✍️ Sabab (asl): {fine.get('reason') or '-'}\n\n"
            "Jarimangiz <b>moliya bo'limi</b> tomonidan bekor qilindi va "
            "oyligingizdan kesilgan summa qaytarildi.",
        )
