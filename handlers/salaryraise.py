"""Xodim maosh oshirishni so'raydi — xodim ⇄ HR kelishuvi.

Xodim «📩 HR ga murojaat» → «💸 Maoshni oshirishni so'rash» orqali kiradi.
Hozirgi maoshini ko'radi, yangi summa taklif qiladi. So'rov HR bo'limiga boradi.
HR tasdiqlashi, o'z summasini taklif qilishi (qarshi taklif) yoki sabab bilan
rad etishi mumkin. Qarshi taklif xodimga qaytadi — u tasdiqlaydi yoki yana boshqa
summa taklif qiladi (aylanma). Kelishilgan summa xodim profiliga yoziladi.
"""
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from database import queries as q
from database.db import ROLE_HR, ROLE_ADMIN, ROLE_CANDIDATE
from states import SalaryRaiseForm
import keyboards as kb
from utils import safe_send

router = Router()


async def _is_staff(tg_id):
    u = await q.get_user(tg_id)
    return u and u["role"] in (ROLE_HR, ROLE_ADMIN)


async def _notify_hr(bot: Bot, text, markup=None):
    hr_ids = await q.all_user_tg_ids(role=ROLE_HR)
    admin_ids = await q.all_user_tg_ids(role=ROLE_ADMIN)
    for tid in set(hr_ids + admin_ids):
        await safe_send(bot, tid, text, reply_markup=markup)


async def _main_menu(message: Message, tg_id):
    """Xodimga o'z roliga mos asosiy menyuni qaytaradi.

    DIQQAT: callback ichida `call.message.from_user` — bot, foydalanuvchi emas.
    Shu sabab menyu tg_id (call.from_user.id) bo'yicha aniqlanadi.
    """
    user = await q.get_user(tg_id)
    role = user["role"] if user else ROLE_CANDIDATE
    has_applied = False
    if role == ROLE_CANDIDATE and user:
        has_applied = await q.count_applications(user["id"]) > 0
    await message.answer(
        "🏠 Asosiy menyu",
        reply_markup=kb.main_menu(role, has_applied),
    )


def _hr_request_text(req):
    return (
        "💸 <b>Maosh oshirish so'rovi</b>\n\n"
        f"🏢 Filial: <b>{req.get('branch_name') or '-'}</b>\n"
        f"💼 Lavozim: <b>{req.get('position') or '-'}</b>\n"
        f"👤 Xodim: {req.get('full_name') or '-'}\n\n"
        f"💰 Hozirgi maoshi: <b>{req.get('current_salary') or 'belgilanmagan'}</b>\n"
        f"📈 So'ralayotgan maosh: <b>{req.get('requested_amount') or '-'}</b>\n\n"
        "Tasdiqlaysizmi, o'z summangizni taklif qilasizmi yoki rad etasizmi?"
    )


# ================= XODIM: SO'ROV BOSHLASH =================
async def start_raise_flow(message: Message, state: FSMContext, tg_id):
    """Maosh oshirish so'rovini boshlaydi.

    «📩 HR ga murojaat» menyusidagi «💸 Maoshni oshirishni so'rash» tugmasidan
    chaqiriladi (handlers/hrrequest.py). Callback ichida `message.from_user` —
    bot bo'lgani uchun xodim tg_id alohida uzatiladi."""
    profile = await q.get_employee_profile_by_tg(tg_id)
    if not profile:
        await message.answer("⛔ Bu bo'lim faqat tasdiqlangan xodimlar uchun.")
        return
    pending = await q.get_pending_raise_for_user(profile["user_id"])
    if pending:
        await message.answer(
            "⏳ Sizda hali javob berilmagan maosh so'rovi bor. "
            "HR bo'limi javobini kuting yoki avvalgi so'rovga javob bering."
        )
        return
    await state.clear()
    cur = profile.get("monthly_salary") or "belgilanmagan"
    await state.update_data(raise_current=cur)
    await message.answer(
        "💸 <b>Maosh oshirish</b>\n\n"
        f"💰 Hozirgi maoshingiz: <b>{cur}</b>\n\n"
        "Maoshingizni oshirish uchun HR bo'limiga so'rov yubormoqchimisiz?",
        reply_markup=kb.raise_confirm_change_kb(),
    )


@router.callback_query(F.data == "raise_no")
async def raise_no(call: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await call.message.answer("❌ Bekor qilindi.")
    await _main_menu(call.message, call.from_user.id)
    await call.answer()


@router.callback_query(F.data == "raise_yes")
async def raise_yes(call: CallbackQuery, state: FSMContext):
    await state.set_state(SalaryRaiseForm.amount)
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await call.message.answer(
        "✏️ Oshirmoqchi bo'lgan (yangi) oyligingizni yozing.\n"
        "Misol: <b>5 300 000 so'm</b>"
    )
    await call.answer()


# Xodim summa kiritadi (dastlabki yoki qarshi taklif yoki tahrirlashdan keyin)
@router.message(SalaryRaiseForm.amount, F.text)
async def raise_amount_entered(message: Message, state: FSMContext):
    amount = message.text.strip()
    if not amount:
        await message.answer("❗️ Summa bo'sh bo'lmasligi kerak. Qayta yozing:")
        return
    await state.update_data(raise_amount=amount)
    await state.set_state(None)  # summa FSM ma'lumotida saqlanadi, tugmalar kutilmoqda
    await message.answer(
        f"📝 Siz kiritgan yangi maosh: <b>{amount}</b>\n\n"
        "Tasdiqlaysizmi?",
        reply_markup=kb.raise_amount_confirm_kb(),
    )


@router.callback_query(F.data == "raise_amt_edit")
async def raise_amt_edit(call: CallbackQuery, state: FSMContext):
    await state.set_state(SalaryRaiseForm.amount)
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await call.message.answer("✏️ Yangi summani qayta yozing:")
    await call.answer()


@router.callback_query(F.data == "raise_amt_cancel")
async def raise_amt_cancel(call: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await call.message.answer("❌ Bekor qilindi.")
    await _main_menu(call.message, call.from_user.id)
    await call.answer()


@router.callback_query(F.data == "raise_amt_ok")
async def raise_amt_ok(call: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    amount = data.get("raise_amount")
    rid = data.get("raise_rid")
    if not amount:
        await state.clear()
        await call.answer("⏳ Sessiya tugagan. Qaytadan boshlang.", show_alert=True)
        return
    profile = await q.get_employee_profile_by_tg(call.from_user.id)
    if not profile:
        await state.clear()
        await call.answer("⛔ Xodim profili topilmadi.", show_alert=True)
        return
    await state.clear()
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    if rid:
        # Mavjud so'rovga xodimning yangi (qarshi) taklifi
        req = await q.get_raise_request(rid)
        if not req or req.get("status") != "pending":
            await call.message.answer("Bu so'rov allaqachon yopilgan.")
            await call.answer()
            return
        await q.set_raise_offer(rid, amount, "employee")
    else:
        # Yangi so'rov
        pending = await q.get_pending_raise_for_user(profile["user_id"])
        if pending:
            await call.message.answer(
                "⏳ Sizda allaqachon ochiq maosh so'rovi bor. HR javobini kuting."
            )
            await call.answer()
            return
        rid = await q.add_raise_request(
            user_id=profile["user_id"],
            branch_id=profile.get("branch_id"),
            position=profile.get("position"),
            current_salary=profile.get("monthly_salary"),
            requested_amount=amount,
        )

    me = await q.get_user(call.from_user.id)
    await q.add_log(
        call.from_user.id, me["full_name"] if me else "?",
        "maosh_sorovi", f"#{rid}: {amount}",
    )
    await call.message.answer(
        "📤 <b>So'rovingiz HR bo'limiga yuborildi!</b>\n\n"
        f"📈 So'ralgan maosh: <b>{amount}</b>\n"
        "HR javobini kuting."
    )
    await _main_menu(call.message, call.from_user.id)
    await call.answer("Yuborildi ✅")

    req = await q.get_raise_request(rid)
    await _notify_hr(bot, _hr_request_text(req), markup=kb.hr_raise_actions_kb(rid))


# ================= HR: SO'ROVLAR RO'YXATI =================
@router.message(F.text == "💸 Maosh so'rovlari")
async def hr_raise_list(message: Message):
    if not await _is_staff(message.from_user.id):
        await message.answer("⛔ Sizda ruxsat yo'q.")
        return
    reqs = await q.list_pending_raise_requests(limit=30)
    if not reqs:
        await message.answer("💸 Ochiq maosh so'rovlari yo'q.")
        return
    await message.answer(
        f"💸 <b>Ochiq maosh so'rovlari</b>\n\nJami: <b>{len(reqs)}</b> ta\n"
        "Batafsil ko'rish uchun tanlang:",
        reply_markup=kb.raise_requests_list_kb(reqs),
    )


@router.callback_query(F.data.startswith("raiseview:"))
async def hr_raise_view(call: CallbackQuery):
    if not await _is_staff(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    rid = int(call.data.split(":")[1])
    req = await q.get_raise_request(rid)
    if not req:
        await call.answer("So'rov topilmadi.", show_alert=True)
        return
    markup = kb.hr_raise_actions_kb(rid) if req.get("status") == "pending" else None
    await call.message.answer(_hr_request_text(req), reply_markup=markup)
    await call.answer()


# HR xodim so'ragan summani tasdiqlaydi
@router.callback_query(F.data.startswith("hrraise_ok:"))
async def hr_raise_approve(call: CallbackQuery, bot: Bot):
    if not await _is_staff(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    rid = int(call.data.split(":")[1])
    req = await q.get_raise_request(rid)
    if not req or req.get("status") != "pending":
        await call.answer("Bu so'rov allaqachon ko'rib chiqilgan.", show_alert=True)
        return
    me = await q.get_user(call.from_user.id)
    # ATOMIK — bir marta tasdiqlanadi
    if not await q.claim_request("salary_raise_requests", rid, "agreed",
                                 me["id"] if me else None, "pending"):
        try:
            await call.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        await call.answer("Bu so'rov allaqachon boshqa xodim tomonidan ko'rib chiqilgan.",
                          show_alert=True)
        return
    final = req.get("requested_amount")
    await q.agree_raise(rid, final, handled_by=me["id"] if me else None)
    await q.update_monthly_salary(req["user_id"], final)
    await q.add_log(
        call.from_user.id, me["full_name"] if me else "?",
        "maosh_tasdiq", f"#{rid}: {final}",
    )
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await call.message.answer(
        f"✅ Maosh so'rovi #{rid} tasdiqlandi.\n"
        f"👤 {req.get('full_name')} — yangi maosh: <b>{final}</b>"
    )
    await call.answer("Tasdiqlandi ✅")
    if req.get("user_tg"):
        await safe_send(
            bot, req["user_tg"],
            "🎉 <b>Tabriklaymiz!</b>\n\n"
            "Maosh oshirish so'rovingiz HR bo'limi tomonidan tasdiqlandi.\n"
            f"💰 Yangi maoshingiz: <b>{final}</b>",
        )


# HR o'z summasini taklif qiladi (qarshi taklif)
@router.callback_query(F.data.startswith("hrraise_offer:"))
async def hr_raise_offer_start(call: CallbackQuery, state: FSMContext):
    if not await _is_staff(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    rid = int(call.data.split(":")[1])
    req = await q.get_raise_request(rid)
    if not req or req.get("status") != "pending":
        await call.answer("Bu so'rov allaqachon ko'rib chiqilgan.", show_alert=True)
        return
    await state.set_state(SalaryRaiseForm.hr_amount)
    await state.update_data(raise_rid=rid)
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await call.message.answer(
        f"💬 Ariza #{rid} — xodimga taklif qilinadigan maosh summasini yozing.\n"
        "Misol: <b>4 500 000 so'm</b>"
    )
    await call.answer()


@router.message(SalaryRaiseForm.hr_amount, F.text)
async def hr_raise_offer_entered(message: Message, state: FSMContext):
    if not await _is_staff(message.from_user.id):
        await state.clear()
        return
    amount = message.text.strip()
    if not amount:
        await message.answer("❗️ Summa bo'sh bo'lmasligi kerak. Qayta yozing:")
        return
    data = await state.get_data()
    rid = data.get("raise_rid")
    await state.update_data(raise_hr_amount=amount)
    await state.set_state(None)
    await message.answer(
        f"📝 Siz taklif qilmoqchi bo'lgan maosh: <b>{amount}</b>\n\nTasdiqlaysizmi?",
        reply_markup=kb.hr_raise_offer_confirm_kb(rid),
    )


@router.callback_query(F.data.startswith("hrraise_editoffer:"))
async def hr_raise_offer_edit(call: CallbackQuery, state: FSMContext):
    if not await _is_staff(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    rid = int(call.data.split(":")[1])
    await state.set_state(SalaryRaiseForm.hr_amount)
    await state.update_data(raise_rid=rid)
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await call.message.answer("✏️ Taklif summasini qayta yozing:")
    await call.answer()


@router.callback_query(F.data.startswith("hrraise_sendoffer:"))
async def hr_raise_offer_send(call: CallbackQuery, state: FSMContext, bot: Bot):
    if not await _is_staff(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    rid = int(call.data.split(":")[1])
    data = await state.get_data()
    amount = data.get("raise_hr_amount")
    if not amount:
        await call.answer("⏳ Sessiya tugagan. Qaytadan urinib ko'ring.", show_alert=True)
        await state.clear()
        return
    req = await q.get_raise_request(rid)
    if not req or req.get("status") != "pending":
        await state.clear()
        await call.answer("Bu so'rov allaqachon yopilgan.", show_alert=True)
        return
    await q.set_raise_offer(rid, amount, "hr")
    me = await q.get_user(call.from_user.id)
    await q.add_log(
        call.from_user.id, me["full_name"] if me else "?",
        "maosh_taklif", f"#{rid}: {amount}",
    )
    await state.clear()
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await call.message.answer(f"📤 Taklif xodimga yuborildi: <b>{amount}</b>")
    await call.answer("Yuborildi ✅")
    if req.get("user_tg"):
        await safe_send(
            bot, req["user_tg"],
            "💬 <b>Maosh bo'yicha taklif</b>\n\n"
            "Maosh oshirish so'rovingizdagi summa biroz to'g'ri kelmadi. "
            f"Biz sizga quyidagi maoshni taklif qila olamiz:\n\n"
            f"💰 <b>{amount}</b>\n\n"
            "Rozimisiz yoki o'z summangizni taklif qilasizmi?",
            reply_markup=kb.emp_raise_counter_kb(rid),
        )


# HR so'rovni rad etadi — sababini yozadi
@router.callback_query(F.data.startswith("hrraise_rej:"))
async def hr_raise_reject_start(call: CallbackQuery, state: FSMContext):
    if not await _is_staff(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    rid = int(call.data.split(":")[1])
    req = await q.get_raise_request(rid)
    if not req or req.get("status") != "pending":
        await call.answer("Bu so'rov allaqachon ko'rib chiqilgan.", show_alert=True)
        return
    await state.set_state(SalaryRaiseForm.reject_reason)
    await state.update_data(raise_rid=rid)
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await call.message.answer("✍️ Nima sababdan rad etyapsiz? Sababini yozing:")
    await call.answer()


@router.message(SalaryRaiseForm.reject_reason, F.text)
async def hr_raise_reject_reason(message: Message, state: FSMContext, bot: Bot):
    if not await _is_staff(message.from_user.id):
        await state.clear()
        return
    reason = message.text.strip()
    data = await state.get_data()
    rid = data.get("raise_rid")
    await state.clear()
    req = await q.get_raise_request(rid)
    if not req or req.get("status") != "pending":
        await message.answer("Bu so'rov allaqachon yopilgan.")
        return
    me = await q.get_user(message.from_user.id)
    if not await q.claim_request("salary_raise_requests", rid, "rejected",
                                 me["id"] if me else None, "pending"):
        await message.answer("Bu so'rov allaqachon boshqa xodim tomonidan ko'rib chiqilgan.")
        return
    await q.reject_raise(rid, reason, handled_by=me["id"] if me else None)
    await q.add_log(
        message.from_user.id, me["full_name"] if me else "?",
        "maosh_rad", f"#{rid}",
    )
    await message.answer(f"❌ Maosh so'rovi #{rid} rad etildi.")
    if req.get("user_tg"):
        await safe_send(
            bot, req["user_tg"],
            "😔 <b>Maosh o'zgartirish so'rovi rad etildi</b>\n\n"
            f"Sababi: {reason}",
        )


# ================= XODIM: HR TAKLIFIGA JAVOB =================
@router.callback_query(F.data.startswith("empraise_ok:"))
async def emp_raise_accept(call: CallbackQuery, bot: Bot):
    rid = int(call.data.split(":")[1])
    req = await q.get_raise_request(rid)
    user = await q.get_user(call.from_user.id)
    if not req or not user or req.get("user_id") != user["id"]:
        await call.answer("So'rov topilmadi.", show_alert=True)
        return
    if req.get("status") != "pending":
        await call.answer("Bu so'rov allaqachon yopilgan.", show_alert=True)
        return
    final = req.get("offered_amount")
    await q.agree_raise(rid, final)
    await q.update_monthly_salary(user["id"], final)
    await q.add_log(call.from_user.id, user["full_name"], "maosh_qabul", f"#{rid}: {final}")
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await call.message.answer(
        f"🎉 Tabriklaymiz! Yangi maoshingiz tasdiqlandi: <b>{final}</b>"
    )
    await _main_menu(call.message, call.from_user.id)
    await call.answer("Tasdiqlandi ✅")
    await _notify_hr(
        bot,
        f"✅ <b>Maosh kelishildi</b>\n\n"
        f"👤 {req.get('full_name')} (#{rid}) siz taklif qilgan maoshni qabul qildi: "
        f"<b>{final}</b>.",
    )


@router.callback_query(F.data.startswith("empraise_counter:"))
async def emp_raise_counter(call: CallbackQuery, state: FSMContext):
    rid = int(call.data.split(":")[1])
    req = await q.get_raise_request(rid)
    user = await q.get_user(call.from_user.id)
    if not req or not user or req.get("user_id") != user["id"]:
        await call.answer("So'rov topilmadi.", show_alert=True)
        return
    if req.get("status") != "pending":
        await call.answer("Bu so'rov allaqachon yopilgan.", show_alert=True)
        return
    await state.set_state(SalaryRaiseForm.amount)
    await state.update_data(raise_rid=rid)
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await call.message.answer(
        "✏️ O'zingiz xohlagan yangi maosh summasini yozing.\n"
        "Misol: <b>5 000 000 so'm</b>"
    )
    await call.answer()
