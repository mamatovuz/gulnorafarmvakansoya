"""Avans (oldindan to'lov) tizimi.

Oqim:
  1. Har oy belgilangan kuni (default 13) barcha xodimlarga so'rov boradi:
     «15-sanada avans olishni hohlaysizmi?» [Ha] [Yo'q]
  2. «Ha» → xodim karta raqamini yuboradi → ma'lumotlari chiqadi
     (ism-familiya, karta raqami) [Tasdiqlash] [Tahrirlash].
  3. «Tasdiqlash» → HR panelida «💵 Avans» tugmasi orqali Excel yig'iladi.
  4. HR Excel ostidagi «Buxgalterga yuborish» tugmasini bossa — buxgalter
     paneliga uzatiladi va u yerda «Avans oluvchilar» tugmasida ko'rinadi.
"""
import re

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from database import queries as q
from database.db import (
    ROLE_ADMIN, ROLE_HR, ROLE_ACCOUNTANT,
    ROLE_MANAGER, ROLE_PHARMACIST, ROLE_DIRECTOR, ROLE_EMPLOYEE,
)
from states import AdvanceForm
import keyboards as kb
from services.export import build_advance_xlsx
from utils import safe_send, now_tk

router = Router()

EMPLOYEE_ROLES = (
    ROLE_MANAGER, ROLE_PHARMACIST, ROLE_DIRECTOR, ROLE_EMPLOYEE, ROLE_ACCOUNTANT,
)


def _period_now():
    return now_tk().strftime("%Y-%m")


async def _pay_date_str(period):
    """period='YYYY-MM' + sozlamadagi to'lov kuni -> 'DD.MM.YYYY'."""
    try:
        day = int(await q.get_setting("avans_day", "15") or 15)
    except (TypeError, ValueError):
        day = 15
    year, month = period.split("-")
    return f"{day:02d}.{month}.{year}"


async def _is_hr(tg_id):
    u = await q.get_user(tg_id)
    return bool(u and u["role"] in (ROLE_HR, ROLE_ADMIN))


async def _is_accountant(tg_id):
    u = await q.get_user(tg_id)
    return bool(u and u["role"] in (ROLE_ACCOUNTANT, ROLE_ADMIN))


def _normalize_card(text):
    """Karta raqamini tozalab, faqat raqamlarni qaytaradi ('' agar noto'g'ri)."""
    digits = re.sub(r"\D", "", text or "")
    if 12 <= len(digits) <= 19:
        return digits
    return ""


def _pretty_card(digits):
    """16 xonali karta raqamini 4 tadan guruhlab ko'rsatadi."""
    return " ".join(digits[i:i + 4] for i in range(0, len(digits), 4))


# ==================== XODIM TOMONI ====================
@router.callback_query(F.data.startswith("avns_yes:"))
async def advance_yes(call: CallbackQuery, state: FSMContext):
    period = call.data.split(":", 1)[1]
    profile = await q.get_employee_profile_by_tg(call.from_user.id)
    if not profile:
        await call.answer("Bu funksiya faqat xodimlar uchun.", show_alert=True)
        return
    await state.set_state(AdvanceForm.card)
    await state.update_data(avns_period=period)
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await call.message.answer(
        "💳 Iltimos, avans o'tkaziladigan <b>karta raqamingizni</b> yuboring.\n"
        "<i>Masalan: 8600 1234 5678 9012</i>"
    )
    await call.answer()


@router.callback_query(F.data.startswith("avns_no:"))
async def advance_no(call: CallbackQuery, state: FSMContext):
    period = call.data.split(":", 1)[1]
    profile = await q.get_employee_profile_by_tg(call.from_user.id)
    if profile:
        await q.upsert_advance_request(
            profile["user_id"], period,
            profile.get("full_name"), None, "declined",
        )
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await call.message.answer(
        "✅ Tushunarli. Bu oy avans olishni istamadingiz.\n"
        "Fikringiz o'zgarsa, xabardagi «Ha» tugmasidan foydalanishingiz mumkin."
    )
    await call.answer()


@router.message(AdvanceForm.card, F.text)
async def advance_card(message: Message, state: FSMContext):
    card = _normalize_card(message.text)
    if not card:
        await message.answer(
            "❌ Karta raqami noto'g'ri ko'rinadi.\n"
            "Iltimos, 16 xonali karta raqamini yuboring.\n"
            "<i>Masalan: 8600 1234 5678 9012</i>"
        )
        return
    await state.update_data(avns_card=card)
    me = await q.get_user(message.from_user.id)
    full_name = (me or {}).get("full_name") or "-"
    await message.answer(
        "🧾 <b>Avans so'rovi — ma'lumotlaringizni tekshiring:</b>\n"
        "━━━━━━━━━━━━\n"
        f"👤 Ism-familiya: <b>{full_name}</b>\n"
        f"💳 Karta raqami: <b>{_pretty_card(card)}</b>\n"
        "━━━━━━━━━━━━\n"
        "Hammasi to'g'rimi?",
        reply_markup=kb.advance_confirm_kb(),
    )


@router.callback_query(F.data == "avns_confirm")
async def advance_confirm(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    period = data.get("avns_period") or _period_now()
    card = data.get("avns_card")
    await state.clear()
    if not card:
        await call.answer("Karta raqami topilmadi, qaytadan urinib ko'ring.", show_alert=True)
        return
    me = await q.get_user(call.from_user.id)
    if not me:
        await call.answer("Foydalanuvchi topilmadi.", show_alert=True)
        return
    await q.upsert_advance_request(
        me["id"], period, me.get("full_name"), card, "confirmed",
    )
    await q.add_log(
        call.from_user.id, me.get("full_name"), "avans_soradi", f"{period}"
    )
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await call.message.answer(
        "✅ <b>So'rovingiz qabul qilindi!</b>\n"
        f"💳 Karta: <b>{_pretty_card(card)}</b>\n\n"
        "Avans ro'yxati HR bo'limiga yuboriladi. Rahmat!"
    )
    await call.answer("Tasdiqlandi ✅")


@router.callback_query(F.data == "avns_edit")
async def advance_edit(call: CallbackQuery, state: FSMContext):
    cur = await state.get_state()
    if cur is None:
        # holat tugagan bo'lsa — davrni tiklaymiz
        await state.update_data(avns_period=_period_now())
    await state.set_state(AdvanceForm.card)
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await call.message.answer(
        "✏️ Yangi <b>karta raqamini</b> yuboring:\n"
        "<i>Masalan: 8600 1234 5678 9012</i>"
    )
    await call.answer()


# ==================== HR TOMONI ====================
@router.message(F.text == "💵 Avans")
async def hr_advance(message: Message):
    if not await _is_hr(message.from_user.id):
        return
    period = _period_now()
    rows = await q.list_advances(period, "confirmed")
    if not rows:
        await message.answer(
            "💵 <b>Avans</b>\n\n"
            f"Bu oy ({period}) uchun hali hech kim avans so'ramagan."
        )
        return
    pay_date = await _pay_date_str(period)
    doc = build_advance_xlsx(rows, period, pay_date)
    await message.answer_document(
        doc,
        caption=(
            "💵 <b>Avans oluvchilar ro'yxati</b>\n"
            f"📆 Davr: <b>{period}</b>\n"
            f"💳 To'lov sanasi: <b>{pay_date}</b>\n"
            f"👥 Jami: <b>{len(rows)}</b> nafar\n\n"
            "Ro'yxatni buxgalterga yuborish uchun quyidagi tugmani bosing 👇"
        ),
        reply_markup=kb.advance_send_acc_kb(period),
    )


@router.callback_query(F.data.startswith("avns_send:"))
async def hr_advance_send(call: CallbackQuery, bot: Bot):
    if not await _is_hr(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    period = call.data.split(":", 1)[1]
    cnt = await q.count_advances(period, "confirmed")
    if not cnt:
        await call.answer("Ro'yxat bo'sh.", show_alert=True)
        return
    await q.set_setting("avans_released_period", period)
    me = await q.get_user(call.from_user.id)
    await q.add_log(
        call.from_user.id, (me or {}).get("full_name"),
        "avans_buxgalterga", f"{period}: {cnt} ta",
    )
    # Buxgalterlarga (va adminlarga) xabar
    acc_ids = set(
        await q.all_user_tg_ids(role=ROLE_ACCOUNTANT)
    ) | set(await q.all_user_tg_ids(role=ROLE_ADMIN))
    for tid in acc_ids:
        await safe_send(
            bot, tid,
            "💵 <b>Yangi avans ro'yxati keldi!</b>\n"
            f"📆 Davr: <b>{period}</b>\n"
            f"👥 Jami: <b>{cnt}</b> nafar\n\n"
            "Buxgalter panelidagi «💵 Avans oluvchilar» tugmasi orqali "
            "Excel faylni yuklab oling.",
        )
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await call.message.answer(
        f"📤 Avans ro'yxati ({cnt} nafar) buxgalterga yuborildi ✅"
    )
    await call.answer("Yuborildi ✅")


# ==================== BUXGALTER TOMONI ====================
@router.message(F.text == "💵 Avans oluvchilar")
async def acc_advance(message: Message):
    if not await _is_accountant(message.from_user.id):
        await message.answer("⛔ Sizda ruxsat yo'q.")
        return
    period = await q.get_setting("avans_released_period", None)
    if not period:
        await message.answer(
            "💵 <b>Avans oluvchilar</b>\n\n"
            "Hozircha HR bo'limi avans ro'yxatini yubormagan."
        )
        return
    rows = await q.list_advances(period, "confirmed")
    if not rows:
        await message.answer(
            f"💵 Avans ro'yxati ({period}) bo'sh ko'rinadi."
        )
        return
    pay_date = await _pay_date_str(period)
    doc = build_advance_xlsx(rows, period, pay_date)
    await message.answer_document(
        doc,
        caption=(
            "💵 <b>Avans oluvchilar ro'yxati</b>\n"
            f"📆 Davr: <b>{period}</b>\n"
            f"💳 To'lov sanasi: <b>{pay_date}</b>\n"
            f"👥 Jami: <b>{len(rows)}</b> nafar"
        ),
    )
