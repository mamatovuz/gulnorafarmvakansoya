"""Avans (oldindan to'lov) tizimi.

Oqim:
  1. Har oy belgilangan kuni (default 13) barcha xodimlarga so'rov boradi:
     «Avans oluvchilar ro'yxatiga qo'shilishni hohlaysizmi?» [Ha] [Yo'q]
     (So'rov kuni va to'lov sanasi HR/Admin panelidan sozlanadi.)
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
from states import AdvanceForm, SettingsForm
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
            "Moliya bo'limi panelidagi «💵 Avans oluvchilar» tugmasi orqali "
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


# ==================== AVANS SOZLAMALARI (HR / ADMIN) ====================
async def _advance_settings_text():
    enabled = str(await q.get_setting("avans_enabled", "1")) == "1"
    prompt_day = await q.get_setting("avans_prompt_day", "13") or "13"
    pay_day = await q.get_setting("avans_day", "15") or "15"
    status = "🟢 Yoqilgan" if enabled else "🔴 O'chirilgan"
    text = (
        "💵 <b>Avans sozlamalari</b>\n"
        "━━━━━━━━━━━━\n"
        "Har oy belgilangan kunda barcha xodimlarga «Avans oluvchilar ro'yxatiga "
        "qo'shilishni xohlaysizmi?» degan so'rov yuboriladi.\n\n"
        f"Holat: <b>{status}</b>\n"
        f"📨 So'rov yuboriladigan kun: <b>har oy {prompt_day}-sana</b>\n"
        f"💳 Avans to'lov sanasi: <b>har oy {pay_day}-sana</b>\n\n"
        "Quyidan istalgan kunni o'zgartiring:"
    )
    return text, enabled, prompt_day, pay_day


@router.message(F.text == "💵 Avans sozlamalari")
async def advance_settings(message: Message):
    if not await _is_hr(message.from_user.id):
        return
    text, enabled, prompt_day, pay_day = await _advance_settings_text()
    await message.answer(
        text, reply_markup=kb.advance_settings_kb(prompt_day, pay_day, enabled)
    )


@router.callback_query(F.data == "avset:toggle")
async def advance_settings_toggle(call: CallbackQuery):
    if not await _is_hr(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    enabled = str(await q.get_setting("avans_enabled", "1")) == "1"
    await q.set_setting("avans_enabled", "0" if enabled else "1")
    me = await q.get_user(call.from_user.id)
    await q.add_log(
        call.from_user.id, (me or {}).get("full_name"),
        "sozlama_avans", "yoqildi" if not enabled else "o'chirildi",
    )
    text, en, prompt_day, pay_day = await _advance_settings_text()
    try:
        await call.message.edit_text(
            text, reply_markup=kb.advance_settings_kb(prompt_day, pay_day, en)
        )
    except Exception:
        pass
    await call.answer("Saqlandi ✅")


@router.callback_query(F.data == "avset:promptday")
async def advance_settings_promptday(call: CallbackQuery, state: FSMContext):
    if not await _is_hr(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    await state.set_state(SettingsForm.avans_prompt_day)
    await call.message.answer(
        "📨 Avans so'rovi <b>har oyning qaysi kunida</b> yuborilsin?\n"
        "1 dan 28 gacha son yuboring. Masalan: <b>13</b>"
    )
    await call.answer()


@router.callback_query(F.data == "avset:payday")
async def advance_settings_payday(call: CallbackQuery, state: FSMContext):
    if not await _is_hr(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    await state.set_state(SettingsForm.avans_pay_day)
    await call.message.answer(
        "💳 Avans <b>har oyning qaysi sanasida</b> to'lansin?\n"
        "1 dan 28 gacha son yuboring. Masalan: <b>15</b>"
    )
    await call.answer()


def _valid_day(text):
    """'1'..'28' oralig'idagi butun sonni qaytaradi, aks holda None."""
    val = (text or "").strip()
    if val.isdigit() and 1 <= int(val) <= 28:
        return int(val)
    return None


@router.message(SettingsForm.avans_prompt_day, F.text)
async def advance_settings_promptday_save(message: Message, state: FSMContext):
    if not await _is_hr(message.from_user.id):
        await state.clear()
        return
    day = _valid_day(message.text)
    if day is None:
        await message.answer("❗️ 1 dan 28 gacha butun son yuboring. Masalan: 13")
        return
    await state.clear()
    await q.set_setting("avans_prompt_day", str(day))
    me = await q.get_user(message.from_user.id)
    await q.add_log(
        message.from_user.id, (me or {}).get("full_name"),
        "sozlama_avans_kun", f"so'rov: {day}",
    )
    await message.answer(f"✅ So'rov endi har oy <b>{day}-sanada</b> yuboriladi.")
    text, enabled, prompt_day, pay_day = await _advance_settings_text()
    await message.answer(
        text, reply_markup=kb.advance_settings_kb(prompt_day, pay_day, enabled)
    )


@router.message(SettingsForm.avans_pay_day, F.text)
async def advance_settings_payday_save(message: Message, state: FSMContext):
    if not await _is_hr(message.from_user.id):
        await state.clear()
        return
    day = _valid_day(message.text)
    if day is None:
        await message.answer("❗️ 1 dan 28 gacha butun son yuboring. Masalan: 15")
        return
    await state.clear()
    await q.set_setting("avans_day", str(day))
    me = await q.get_user(message.from_user.id)
    await q.add_log(
        message.from_user.id, (me or {}).get("full_name"),
        "sozlama_avans_kun", f"to'lov: {day}",
    )
    await message.answer(f"✅ Avans endi har oy <b>{day}-sanada</b> to'lanadi.")
    text, enabled, prompt_day, pay_day = await _advance_settings_text()
    await message.answer(
        text, reply_markup=kb.advance_settings_kb(prompt_day, pay_day, enabled)
    )


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
