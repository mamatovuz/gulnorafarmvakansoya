"""Gulnora Farm mavjud xodimi — o'zini ro'yxatdan o'tkazadi (self-registratsiya).

/start dagi «🏢 Gulnora Farm hodimi» tugmasi orqali kiriladi. Xodim ma'lumotlarini
kiritadi, so'ng ariza HR/Adminga tasdiq uchun yuboriladi. Tasdiqlangach xodimga
tegishli rol va davomat paneli ochiladi.
"""
import logging
from datetime import datetime

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter

from database import queries as q
from database.db import (
    ROLE_HR, ROLE_ADMIN, ROLE_MANAGER, ROLE_DIRECTOR, ROLE_PHARMACIST,
    ROLE_EMPLOYEE, ROLE_TECH,
)
from states import StaffReg, StaffRegRejectForm
import keyboards as kb
from i18n import t, tf, canon
from utils import (
    safe_send, staff_reg_text, uniform_label, now_tk, normalize_phone, PHONE_HINT,
    post_staff_reg_to_channel, PROFILE_UPDATE_NOTICE, broadcast_request,
    close_request_notices, handled_by_text, handled_alert_text, employee_state,
)

router = Router()
logger = logging.getLogger("hrbot.staffreg")

ROLE_LABELS = {
    ROLE_MANAGER: "🏢 Filial rahbari",
    ROLE_PHARMACIST: "💊 Farmatsevt",
    ROLE_DIRECTOR: "👔 Direktor",
    ROLE_TECH: "🔧 Texnik xodim",
    ROLE_EMPLOYEE: "👷 Xodim",
}


async def _is_staff(tg_id):
    u = await q.get_user(tg_id)
    return u and u["role"] in (ROLE_HR, ROLE_ADMIN)


# ---------------- Yordamchilar ----------------
def parse_birthdate(text):
    text = (text or "").strip()
    try:
        dt = datetime.strptime(text, "%d.%m.%Y")
    except ValueError:
        return None
    if not (1940 <= dt.year <= now_tk().year):
        return None
    return dt.strftime("%d.%m.%Y")


def resolve_branch(text, branches):
    clean = (text or "").replace("📍", "").strip()
    for br in branches:
        if br["name"].lower() == clean.lower():
            return br["name"], br["id"]
    return clean, None


def uniform_status_from_text(text):
    lower = (text or "").lower()
    if "yo'q" in lower or "yoq" in lower or "kerak" in lower:
        return "no"
    if "ha" in lower or "bor" in lower:
        return "yes"
    return "unknown"


def _extra_prompt(role, position):
    if role == ROLE_MANAGER:
        return "🧩 Nechta xodimdan iborat jamoani boshqarasiz? (masalan: <i>8 xodim</i>)"
    if role == ROLE_DIRECTOR:
        return "🧩 Nechta filialni boshqarasiz / mas'uliyat doirangiz qanday?"
    return None


def _reg_summary(d):
    def g(k):
        return d.get(k) or "-"
    lines = [
        "📋 <b>Ma'lumotlaringizni tekshiring:</b>",
        "",
        f"👤 Ism-familiya: {g('full_name')}",
        f"📅 Tug'ilgan sana: {g('birth_date')}",
        f"📱 Telefon: {g('phone')}",
        f"👪 Ota/ona telefoni: {g('parent_phone')}",
        f"💼 Lavozim: {g('position')}",
        f"📍 Manzil: {g('address')}",
        f"🏢 Filial: {g('branch_name')}",
        f"🕒 Ish vaqti: {g('work_hours')}",
        f"💰 Oylik: {g('salary')}",
        f"🛌 Dam olish kuni: {g('rest_day')}",
        f"👕 Forma: {uniform_label(d.get('uniform_status'))}",
        f"🎓 Ma'lumoti: {g('education')}",
    ]
    if d.get("since"):
        lines.append(f"⏳ Gulnora Farmda: {d['since']}")
    if d.get("extra_info"):
        lines.append(f"🧩 Qo'shimcha: {d['extra_info']}")
    lines.append(f"🖼 Rasm: {'✅ biriktirilgan' if d.get('photo_file_id') else '— yo`q'}")
    pf = d.get("passport_files") or []
    lines.append(f"🪪 Pasport/ID: {'✅ ' + str(len(pf)) + ' ta rasm' if pf else '— yo`q'}")
    lines.append(f"🎓 Diplom: {'✅ biriktirilgan' if d.get('diploma_file') else '— yo`q'}")
    return "\n".join(lines)


# ---------------- KIRISH ----------------
FIRST_QUESTION = (
    "<b>1-savol</b>\n👤 Ism-familiyangizni yozing.\nMisol: <i>Ravshanova Robiya</i>"
)

REG_INTRO = (
    "🏢 <b>Gulnora Farm hodimi sifatida ro'yxatdan o'tish</b>\n\n"
    "Assalomu alaykum! Agar siz allaqachon Gulnora Farmda ishlayotgan bo'lsangiz, "
    "quyidagi savollarga javob bering. Ma'lumotlaringiz HR bo'limiga tasdiqlash uchun "
    "yuboriladi.\n"
    "Istalgan payt «❌ Bekor qilish» tugmasi bilan to'xtatishingiz mumkin.\n\n"
    + FIRST_QUESTION
)

UPDATE_INTRO = (
    "🔄 <b>Ma'lumotlarni yangilash</b>\n\n"
    "Savollarga <b>boshidan</b> javob bering — hozirgi holatingizni yozing.\n"
    "Eski ma'lumotlaringiz o'chmaydi: siz anketani yakunlab tasdiqlaganingizdan "
    "keyingina ular yangilanadi.\n\n"
    + FIRST_QUESTION
)


async def _begin_staff_form(message: Message, state: FSMContext, update_mode=False,
                            lang=None):
    await state.clear()
    await state.update_data(_update_mode=update_mode)
    await state.set_state(StaffReg.full_name)
    await message.answer(
        UPDATE_INTRO if update_mode else t("sreg.intro", lang),
        reply_markup=kb.staff_photo_kb(lang),  # faqat Bekor qilish tugmasi
    )


@router.message(tf("btn.staffreg"))
async def staff_reg_start(message: Message, state: FSMContext, lang: str = None):
    await _begin_staff_form(message, state, update_mode=False, lang=lang)


@router.callback_query(F.data == "profupd_start")
async def staff_update_start(call: CallbackQuery, state: FSMContext):
    """Admin so'ragan «ma'lumotlarni yangilash» — anketa boshidan boshlanadi."""
    profile = await q.get_employee_profile_by_tg(call.from_user.id)
    if not profile:
        await call.answer("⛔ Xodim profili topilmadi.", show_alert=True)
        return
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await call.answer()
    await _begin_staff_form(call.message, state, update_mode=True)


# ---------------- BEKOR QILISH ----------------
@router.message(StateFilter(
    StaffReg.full_name, StaffReg.birth_date, StaffReg.phone, StaffReg.parent_phone,
    StaffReg.role, StaffReg.address, StaffReg.branch, StaffReg.shift,
    StaffReg.work_hours, StaffReg.salary, StaffReg.rest_day, StaffReg.uniform,
    StaffReg.education, StaffReg.since, StaffReg.extra, StaffReg.photo,
    StaffReg.passport, StaffReg.diploma,
), F.text.in_(kb.CANCEL_BUTTONS))
async def staff_reg_cancel(message: Message, state: FSMContext, lang: str = None):
    data = await state.get_data()
    update_mode = bool(data.get("_update_mode"))
    await state.clear()
    if update_mode:
        # Yangilash majburiy — bekor qilinsa eslatma qaytadan chiqadi
        await message.answer(
            PROFILE_UPDATE_NOTICE, reply_markup=kb.profile_update_start_kb()
        )
        return
    user = await q.get_user(message.from_user.id)
    await message.answer(
        t("sreg.cancelled", lang),
        reply_markup=kb.main_menu(user["role"] if user else "candidate", lang=lang),
    )


# 1) Ism-familiya
@router.message(StaffReg.full_name, F.text)
async def sr_name(message: Message, state: FSMContext, lang: str = None):
    await state.update_data(full_name=message.text.strip())
    await state.set_state(StaffReg.birth_date)
    await message.answer(
        f"{t('apply.q_num', lang, n=2)}\n{t('sreg.birth', lang)}",
        reply_markup=kb.staff_photo_kb(lang),
    )


# 2) Tug'ilgan sana
@router.message(StaffReg.birth_date, F.text)
async def sr_birth(message: Message, state: FSMContext, lang: str = None):
    norm = parse_birthdate(message.text)
    if not norm:
        await message.answer(
            t("apply.birth_bad", lang),
            reply_markup=kb.staff_photo_kb(lang),
        )
        return
    await state.update_data(birth_date=norm)
    await state.set_state(StaffReg.phone)
    await message.answer(
        f"{t('apply.q_num', lang, n=3)}\n{t('sreg.phone', lang)}",
        reply_markup=kb.staff_photo_kb(lang),
    )


# 3) Telefon raqam (qo'lda yoziladi) — faqat +998XXXXXXXXX
@router.message(StaffReg.phone, F.text)
async def sr_phone(message: Message, state: FSMContext, lang: str = None):
    phone = normalize_phone(message.text)
    if not phone:
        await message.answer(
            t("apply.phone_bad", lang),
            reply_markup=kb.staff_photo_kb(lang),
        )
        return
    await state.update_data(phone=phone)
    await state.set_state(StaffReg.parent_phone)
    await message.answer(
        "<b>3b-savol</b>\n👪 <b>Ota yoki onangizning telefon raqamini</b> yozing.\n"
        f"Misol: <i>+998901234567</i>\n\n{PHONE_HINT}",
        reply_markup=kb.staff_photo_kb(lang),
    )


# 3b) Ota/ona telefon raqami
@router.message(StaffReg.parent_phone, F.text)
async def sr_parent_phone(message: Message, state: FSMContext, lang: str = None):
    phone = normalize_phone(message.text)
    if not phone:
        await message.answer(
            "❗️ Telefon raqamini to'g'ri kiriting.\n" + PHONE_HINT,
            reply_markup=kb.staff_photo_kb(lang),
        )
        return
    await state.update_data(parent_phone=phone)
    await state.set_state(StaffReg.role)
    names = await q.list_position_names()
    await message.answer(
        f"{t('apply.q_num', lang, n=4)}\n{t('sreg.role', lang)}",
        reply_markup=kb.staff_role_kb(names),
    )


# 4) Rol / yo'nalish
@router.message(StaffReg.role, F.text)
async def sr_role(message: Message, state: FSMContext, lang: str = None):
    names = await q.list_position_names()
    mapping = {label: (role, pos) for label, role, pos in kb.staff_role_options(names)}
    got = mapping.get(message.text.strip())
    if not got:
        await message.answer(
            t("common.pick_buttons", lang),
            reply_markup=kb.staff_role_kb(names),
        )
        return
    role, position = got
    await state.update_data(role=role, position=position)
    await state.set_state(StaffReg.address)
    await message.answer(
        f"{t('apply.q_num', lang, n=5)}\n{t('sreg.address', lang)}",
        reply_markup=kb.staff_photo_kb(lang),
    )


# 4) Manzil
@router.message(StaffReg.address, F.text)
async def sr_address(message: Message, state: FSMContext, lang: str = None):
    await state.update_data(address=message.text.strip())
    branches = await q.list_branches()
    await state.set_state(StaffReg.branch)
    if branches:
        await message.answer(
            f"{t('apply.q_num', lang, n=6)}\n{t('sreg.branch', lang)}",
            reply_markup=kb.apply_branch_kb(branches),
        )
    else:
        await message.answer(
            f"{t('apply.q_num', lang, n=6)}\n{t('sreg.branch_write', lang)}",
            reply_markup=kb.staff_photo_kb(lang),
        )


# 5) Filial
@router.message(StaffReg.branch, F.text)
async def sr_branch(message: Message, state: FSMContext, lang: str = None):
    branches = await q.list_branches()
    name, bid = resolve_branch(message.text, branches)
    await state.update_data(branch_name=name, branch_id=bid)
    await state.set_state(StaffReg.shift)
    await message.answer(
        f"{t('apply.q_num', lang, n=7)}\n{t('sreg.shift', lang)}\n\n"
        f"{kb.STAFF_SHIFT_DAY} — odatda 08:00 - 17:00\n"
        f"{kb.STAFF_SHIFT_NIGHT} — odatda 14:00 - 00:00\n"
        f"{kb.STAFF_SHIFT_DOUBLE} — ikkala smena",
        reply_markup=kb.staff_shift_kb(),
    )


# 6) Smena
@router.message(StaffReg.shift, F.text)
async def sr_shift(message: Message, state: FSMContext, lang: str = None):
    text = message.text.strip()
    valid = (kb.STAFF_SHIFT_DAY, kb.STAFF_SHIFT_NIGHT, kb.STAFF_SHIFT_DOUBLE)
    if text not in valid:
        await message.answer(
            t("common.pick_buttons", lang),
            reply_markup=kb.staff_shift_kb(),
        )
        return
    await state.update_data(shift=text)
    await state.set_state(StaffReg.work_hours)
    await message.answer(
        f"{t('apply.q_num', lang, n=8)}\n{t('sreg.work_hours', lang)}",
        reply_markup=kb.staff_work_hours_kb(text),
    )


# 7) Ish vaqti
@router.message(StaffReg.work_hours, F.text)
async def sr_hours(message: Message, state: FSMContext, lang: str = None):
    text = message.text.strip()
    data = await state.get_data()
    shift = data.get("shift")
    # «Boshqa vaqt» tugmasi bosilsa — foydalanuvchidan qo'lda yozishni so'raymiz
    if text == kb.STAFF_HOURS_CUSTOM:
        await message.answer(
            t("sreg.work_hours", lang),
            reply_markup=kb.staff_photo_kb(lang),
        )
        return
    hours = (text.replace("🕘", "").replace("🕗", "").replace("🕙", "")
             .replace("🕑", "").replace("🔄", "").strip())
    # Smena nomini ish vaqti bilan birga saqlaymiz (davomat vaqt regexiga ta'sir qilmaydi)
    shift_prefix = f"{shift} · " if shift else ""
    await state.update_data(work_hours=f"{shift_prefix}{hours}")
    await state.set_state(StaffReg.salary)
    await message.answer(
        f"{t('apply.q_num', lang, n=9)}\n{t('sreg.salary', lang)}",
        reply_markup=kb.staff_photo_kb(lang),
    )


# 7) Oylik
@router.message(StaffReg.salary, F.text)
async def sr_salary(message: Message, state: FSMContext, lang: str = None):
    await state.update_data(salary=message.text.strip())
    await state.set_state(StaffReg.rest_day)
    await message.answer(
        f"{t('apply.q_num', lang, n=10)}\n{t('sreg.rest_day', lang)}",
        reply_markup=kb.staff_rest_day_kb(lang),
    )


# 8) Dam olish kuni
@router.message(StaffReg.rest_day, F.text)
async def sr_rest(message: Message, state: FSMContext, lang: str = None):
    await state.update_data(rest_day=canon("rest_day", message.text))
    await state.set_state(StaffReg.uniform)
    await message.answer(
        f"{t('apply.q_num', lang, n=11)}\n{t('sreg.uniform', lang)}",
        reply_markup=kb.apply_uniform_kb(lang),
    )


# 9) Forma
@router.message(StaffReg.uniform, F.text)
async def sr_uniform(message: Message, state: FSMContext, lang: str = None):
    await state.update_data(uniform_status=uniform_status_from_text(message.text))
    await state.set_state(StaffReg.education)
    await message.answer(
        f"{t('apply.q_num', lang, n=12)}\n{t('sreg.education', lang)}",
        reply_markup=kb.staff_education_kb(lang),
    )


# 9b) Ma'lumoti / diplomi
@router.message(StaffReg.education, F.text)
async def sr_education(message: Message, state: FSMContext, lang: str = None):
    text = canon("education", message.text)
    if text not in kb.STAFF_EDUCATION:
        await message.answer(
            t("common.pick_buttons", lang),
            reply_markup=kb.staff_education_kb(lang),
        )
        return
    await state.update_data(education=text)
    await state.set_state(StaffReg.since)
    await message.answer(
        f"{t('apply.q_num', lang, n=13)}\n{t('sreg.since', lang)}",
        reply_markup=kb.staff_since_kb(lang),
    )


# 10) Necha yildan beri Gulnora Farmda ishlaydi (barcha yo'nalishlar uchun)
@router.message(StaffReg.since, F.text)
async def sr_since(message: Message, state: FSMContext):
    await state.update_data(since=message.text.replace("🟡", "").replace("🟠", "")
                            .replace("🟢", "").replace("🔵", "").strip())
    data = await state.get_data()
    prompt = _extra_prompt(data.get("role"), data.get("position"))
    if prompt:
        await state.set_state(StaffReg.extra)
        await message.answer("<b>14-savol</b>\n" + prompt, reply_markup=kb.staff_photo_kb())
    else:
        await _ask_photo(message, state)


# 11) Rolga oid qo'shimcha
@router.message(StaffReg.extra, F.text)
async def sr_extra(message: Message, state: FSMContext):
    await state.update_data(extra_info=message.text.strip())
    await _ask_photo(message, state)


async def _ask_photo(message: Message, state: FSMContext):
    await state.set_state(StaffReg.photo)
    await message.answer(
        "📸 <b>Oxirgi savol</b>\nOxirgi 10 kun ichida olingan rasmingizni yuboring "
        "(shaxsingiz aniq ko'rinadigan surat).",
        reply_markup=kb.staff_photo_kb(),
    )


# Rasm
@router.message(StaffReg.photo, F.photo)
async def sr_photo(message: Message, state: FSMContext):
    await state.update_data(photo_file_id=message.photo[-1].file_id)
    await _ask_passport(message, state)


@router.message(StaffReg.photo, F.text)
async def sr_photo_missing(message: Message):
    await message.answer(
        "❗️ Iltimos, rasm (surat) yuboring — matn emas. "
        "Oxirgi 10 kun ichidagi suratingizni yuboring.",
        reply_markup=kb.staff_photo_kb(),
    )


# ---------------- PASPORT / ID KARTA (maxfiy — kanalga chiqmaydi) ----------------
async def _ask_passport(message: Message, state: FSMContext):
    await state.update_data(passport_files=[])
    await state.set_state(StaffReg.passport)
    await message.answer(
        "🪪 <b>Pasport yoki ID karta rasmi</b>\n"
        "━━━━━━━━━━━━━\n"
        "Hujjatingizning <b>oldi</b> va <b>orqa</b> tomonini yuboring.\n"
        "• Ikkalasini <b>birdaniga (albom qilib)</b> yoki\n"
        "• <b>alohida</b> — avval oldi, keyin orqa tomonini yuborishingiz mumkin.\n\n"
        "🔒 Bu rasm faqat HR/rahbar panelida saqlanadi — <b>kanalga chiqmaydi</b>.\n"
        "Ikkala rasmni yuborib bo'lgach «✅ Tayyor» tugmasini bosing.",
        reply_markup=kb.staff_passport_kb(),
    )


def _doc_file_id(message: Message):
    """Xabardan rasm yoki hujjat file_id sini oladi (pasport rasm yoki fayl bo'lishi mumkin)."""
    if message.photo:
        return message.photo[-1].file_id
    if message.document:
        return message.document.file_id
    return None


@router.message(StaffReg.passport, F.photo | F.document)
async def sr_passport_file(message: Message, state: FSMContext):
    file_id = _doc_file_id(message)
    if not file_id:
        return
    data = await state.get_data()
    files = list(data.get("passport_files") or [])
    files.append(file_id)
    files = files[:2]  # faqat oldi va orqa
    await state.update_data(passport_files=files)
    if len(files) >= 2:
        # Oldi + orqa yig'ildi — diplomga o'tamiz
        await _ask_diploma(message, state)
    else:
        await message.answer(
            "✅ 1-rasm (oldi tomoni) qabul qilindi.\n"
            "Endi hujjatning <b>orqa</b> tomonini yuboring. "
            "Agar bitta rasm yetarli bo'lsa «✅ Tayyor» tugmasini bosing.",
            reply_markup=kb.staff_passport_kb(),
        )


@router.message(StaffReg.passport, F.text == kb.STAFF_DOCS_DONE)
async def sr_passport_done(message: Message, state: FSMContext):
    data = await state.get_data()
    files = list(data.get("passport_files") or [])
    if not files:
        await message.answer(
            "❗️ Avval pasport yoki ID karta rasmini yuboring.",
            reply_markup=kb.staff_passport_kb(),
        )
        return
    await _ask_diploma(message, state)


@router.message(StaffReg.passport, F.text)
async def sr_passport_hint(message: Message):
    await message.answer(
        "❗️ Iltimos, pasport yoki ID karta <b>rasmini</b> yuboring (matn emas). "
        "Tugatgach «✅ Tayyor» tugmasini bosing.",
        reply_markup=kb.staff_passport_kb(),
    )


# ---------------- DIPLOM (maxfiy — kanalga chiqmaydi) ----------------
async def _ask_diploma(message: Message, state: FSMContext):
    await state.set_state(StaffReg.diploma)
    await message.answer(
        "🎓 <b>Diplom rasmi / hujjati</b>\n"
        "━━━━━━━━━━━━━\n"
        "Diplomingiz rasmini yoki fayl ko'rinishida yuboring.\n"
        "🔒 Bu ham faqat HR/rahbar panelida saqlanadi.\n\n"
        "Agar diplomingiz bo'lmasa «⏭ Diplomsiz davom etish» tugmasini bosing.",
        reply_markup=kb.staff_diploma_kb(),
    )


@router.message(StaffReg.diploma, F.photo | F.document)
async def sr_diploma_file(message: Message, state: FSMContext):
    file_id = _doc_file_id(message)
    if not file_id:
        return
    await state.update_data(diploma_file=file_id)
    await _show_confirm(message, state)


@router.message(StaffReg.diploma, F.text == kb.STAFF_DIPLOMA_SKIP)
async def sr_diploma_skip(message: Message, state: FSMContext):
    await _show_confirm(message, state)


@router.message(StaffReg.diploma, F.text)
async def sr_diploma_hint(message: Message):
    await message.answer(
        "❗️ Diplom <b>rasmini</b> yuboring yoki «⏭ Diplomsiz davom etish» tugmasini bosing.",
        reply_markup=kb.staff_diploma_kb(),
    )


async def _show_confirm(message: Message, state: FSMContext):
    data = await state.get_data()
    update_mode = bool(data.get("_update_mode"))
    await state.set_state(StaffReg.confirm)
    user = await q.get_user(message.from_user.id)
    await message.answer(
        "✅ Ma'lumotlar to'plandi.",
        reply_markup=kb.main_menu(user["role"] if user else "candidate"),
    )
    # Rasmni ko'rsatib, tagida tasdiqlash tugmalari
    await message.answer_photo(
        data.get("photo_file_id"),
        caption=_reg_summary(data),
        reply_markup=kb.staff_confirm_kb(update_mode=update_mode),
    )


# ---------------- TASDIQLASH / BEKOR ----------------
@router.callback_query(F.data == "sreg_cancel")
async def sr_confirm_cancel(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    update_mode = bool(data.get("_update_mode"))
    await state.clear()
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    if update_mode:
        await call.message.answer(
            PROFILE_UPDATE_NOTICE, reply_markup=kb.profile_update_start_kb()
        )
    else:
        await call.message.answer("❌ Ariza bekor qilindi.")
    await call.answer()


@router.callback_query(F.data == "sreg_confirm")
async def sr_confirm(call: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    if not data.get("full_name"):
        await call.answer(
            "⏳ Sessiya tugagan. «🏢 Gulnora Farm hodimi» orqali qaytadan boshlang.",
            show_alert=True,
        )
        await state.clear()
        return
    user = await q.get_user(call.from_user.id)
    passport_files = data.get("passport_files") or []
    reg = {
        "user_id": user["id"],
        "full_name": data.get("full_name"),
        "birth_date": data.get("birth_date"),
        "phone": data.get("phone"),
        "role": data.get("role"),
        "position": data.get("position"),
        "address": data.get("address"),
        "branch_id": data.get("branch_id"),
        "branch_name": data.get("branch_name"),
        "work_hours": data.get("work_hours"),
        "salary": data.get("salary"),
        "rest_day": data.get("rest_day"),
        "uniform_status": data.get("uniform_status") or "unknown",
        "photo_file_id": data.get("photo_file_id"),
        "since": data.get("since"),
        "extra_info": data.get("extra_info"),
        "education": data.get("education"),
        "parent_phone": data.get("parent_phone"),
        "passport_front": passport_files[0] if len(passport_files) >= 1 else None,
        "passport_back": passport_files[1] if len(passport_files) >= 2 else None,
        "diploma_file": data.get("diploma_file"),
    }
    rid = await q.add_staff_reg(reg)
    # Panellarda Telegram nomi emas, anketada kiritilgan ism ko'rinsin
    await q.set_real_name(tg_id=call.from_user.id, full_name=reg.get("full_name"))
    # Foydalanuvchi telefon raqamini ham yangilab qo'yamiz
    if data.get("phone"):
        await q.update_phone(call.from_user.id, data["phone"])
    if data.get("_update_mode"):
        await _finish_update(call, state, bot, rid, reg, user)
        return
    await state.clear()
    await q.add_log(
        call.from_user.id, call.from_user.full_name,
        "hodim_arizasi", f"Xodim so'rovi #{rid} — {data.get('position')}"
    )
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await call.message.answer(
        f"✅ <b>So'rovingiz HR bo'limiga yuborildi!</b>\n\n"
        f"So'rov raqami: #{rid}\n\n"
        "HR bo'limi ma'lumotlaringizni tekshirib, tasdiqlaydi. Tasdiqlangach sizga "
        "xodim menyusi ochiladi."
    )
    await call.answer("Yuborildi ✅")

    # HR va Adminlarga yuborish. Yuborilgan xabarlar bazaga yoziladi — HR lardan
    # biri tasdiqlaganda/rad etganda qolganlaridagi xabar avtomatik o'chiriladi.
    full = await q.get_staff_reg(rid)
    hr_ids = await q.all_user_tg_ids(role=ROLE_HR)
    admin_ids = await q.all_user_tg_ids(role=ROLE_ADMIN)
    header = "🔔 <b>Yangi xodim so'rovi (Gulnora Farm hodimi)!</b>\n\n"
    await broadcast_request(
        bot, "staff_reg", rid, set(hr_ids + admin_ids),
        header + staff_reg_text(full),
        reply_markup=kb.staff_reg_actions_kb(rid),
        photo=full.get("photo_file_id"),
    )


async def _finish_update(call: CallbackQuery, state: FSMContext, bot: Bot,
                         rid, reg, user):
    """Ma'lumotlarni yangilash rejimi — HR tasdig'isiz darhol profilga yoziladi.

    DIQQAT: xodimning ROLI o'zgartirilmaydi (o'zi o'ziga yuqori rol bera olmasin).
    Yo'nalish o'zgargan bo'lsa HR ga xabar beriladi — rolni HR o'zgartiradi."""
    old_profile = await q.get_employee_profile(user["id"]) or {}
    await state.clear()
    await q.set_staff_reg_status(rid, "updated", handled_by=user["id"])
    # Yangilangan anketadagi ism panellarda ko'rinsin
    await q.set_real_name(user_id=user["id"], full_name=reg.get("full_name"))
    await q.upsert_employee_profile(
        user_id=user["id"],
        application_id=old_profile.get("application_id"),
        role=old_profile.get("role") or user["role"],   # rol o'zgarmaydi
        position=reg.get("position"),
        branch_id=reg.get("branch_id"),
        uniform_status=reg.get("uniform_status") or "unknown",
        monthly_salary=reg.get("salary"),
        birth_date=reg.get("birth_date"),
        address=reg.get("address"),
        work_hours=reg.get("work_hours"),
        rest_day=reg.get("rest_day"),
        photo_file_id=reg.get("photo_file_id"),
        extra_info=reg.get("extra_info"),
        since=reg.get("since"),
        education=reg.get("education"),
        parent_phone=reg.get("parent_phone"),
        passport_front=reg.get("passport_front"),
        passport_back=reg.get("passport_back"),
        diploma_file=reg.get("diploma_file"),
    )
    await q.clear_profile_update(user["id"])
    await q.add_log(
        call.from_user.id, user["full_name"],
        "malumot_yangilandi", f"#{rid} — {reg.get('position')}"
    )
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await call.message.answer(
        "✅ <b>Ma'lumotlaringiz yangilandi. Rahmat!</b>\n\n"
        "Endi botdan avvalgidek foydalanishingiz mumkin.",
        reply_markup=kb.main_menu(old_profile.get("role") or user["role"]),
    )
    await call.answer("Yangilandi ✅")

    full = await q.get_staff_reg(rid)
    changed = ""
    if old_profile.get("position") and old_profile["position"] != reg.get("position"):
        changed = (
            f"\n⚠️ Lavozim o'zgargan: <b>{old_profile['position']}</b> → "
            f"<b>{reg.get('position')}</b> (rolni HR o'zgartirishi kerak)"
        )
    # DIQQAT: yangilangan ma'lumot HECH QANDAY kanalga joylanmaydi —
    # faqat HR va Adminlarga (panelga) boradi.
    header = f"🔄 <b>Xodim ma'lumotlarini yangiladi</b>{changed}\n"
    hr_ids = await q.all_user_tg_ids(role=ROLE_HR)
    admin_ids = await q.all_user_tg_ids(role=ROLE_ADMIN)
    for tid in set(hr_ids + admin_ids):
        if full.get("photo_file_id"):
            try:
                await bot.send_photo(
                    tid, full["photo_file_id"],
                    caption=header + staff_reg_text(full),
                )
                continue
            except Exception:
                pass
        await safe_send(bot, tid, header + staff_reg_text(full))


# ================= HR / ADMIN: TASDIQLASH =================
@router.message(F.text == "🧾 Xodim so'rovlari")
async def hr_staff_regs(message: Message):
    if not await _is_staff(message.from_user.id):
        await message.answer("⛔ Sizda ruxsat yo'q.")
        return
    regs = await q.list_staff_regs(status="new", limit=30)
    missing = await q.list_staff_regs_missing_profile(limit=30)
    if regs:
        await message.answer(
            f"🧾 <b>Yangi xodim so'rovlari</b>\n\nJami: <b>{len(regs)}</b> ta\n"
            "Batafsil ko'rish uchun tanlang:",
            reply_markup=kb.staff_regs_list_kb(regs),
        )
    else:
        await message.answer(
            "🧾 Yangi xodim so'rovlari yo'q.",
            reply_markup=kb.staff_regs_overview_kb(),
        )
    if missing:
        await message.answer(
            f"⚠️ <b>Tasdiqlangan, lekin xodimlar ro'yxatida yo'q</b> — {len(missing)} ta\n"
            "Bu so'rovlar «✅ Tasdiqlangan» bo'lib qolgan, ammo xodim ro'yxatga "
            "tushmagan. Ochib, «🔄 Boshidan tasdiqlash» ni bosing:",
            reply_markup=kb.staff_regs_list_kb(missing),
        )
    if regs:
        await message.answer(
            "🗂 Avval ko'rib chiqilgan so'rovlarni ham ochishingiz mumkin:",
            reply_markup=kb.staff_regs_overview_kb(),
        )


@router.callback_query(F.data.startswith("srlist:"))
async def hr_staff_regs_list(call: CallbackQuery):
    if not await _is_staff(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    what = call.data.split(":")[1]
    if what == "missing":
        regs = await q.list_staff_regs_missing_profile(limit=30)
        title = "⚠️ <b>Tasdiqlangan, lekin ro'yxatda yo'q</b>"
    else:
        regs = await q.list_staff_regs(statuses=("approved", "rejected"), limit=20)
        title = "🗂 <b>Ko'rib chiqilgan xodim so'rovlari</b> (oxirgi 20)"
    await call.answer()
    if not regs:
        await call.message.answer(f"{title}\n\nHech narsa yo'q.")
        return
    await call.message.answer(
        f"{title}\n\nTanlang — kartochkada kim ko'rib chiqqani va «🔄 Boshidan "
        "tasdiqlash» tugmasi bor:",
        reply_markup=kb.staff_regs_list_kb(regs),
    )


async def _reg_state(reg):
    """(holat kaliti, matn qatorlari) — kim ko'rib chiqqan + xodim hozir qayerda."""
    lines = [handled_by_text(reg.get("status"), reg.get("handled_by_name"),
                             reg.get("handled_at"))]
    pres = await q.employee_presence(reg["user_id"])
    key, state_line = employee_state(pres)
    if reg.get("status") == "rejected" and key == "missing":
        state_line = "ℹ️ Xodim ro'yxatda yo'q (so'rov rad etilgan)."
        key = "rejected"
    lines.append(state_line)
    return key, lines, pres


async def _send_reg_card(message: Message, reg, markup=None, extra=None):
    """Xodim so'rovi kartochkasi (rasm bo'lsa — rasm bilan)."""
    text = staff_reg_text(reg)
    if extra:
        text += "\n━━━━━━━━━━━━\n" + extra
    if reg.get("photo_file_id"):
        try:
            if len(text) <= 1024:
                await message.answer_photo(reg["photo_file_id"], caption=text,
                                           reply_markup=markup)
                return
            await message.answer_photo(reg["photo_file_id"])
        except Exception:
            pass
    await message.answer(text, reply_markup=markup)


async def _send_handled_reg(message: Message, reg):
    """Ko'rib chiqilgan so'rov: kim/qachon + xodim holati + «🔄 Boshidan tasdiqlash»."""
    _, lines, _ = await _reg_state(reg)
    can_again = reg.get("status") in ("approved", "rejected")
    await _send_reg_card(
        message, reg, markup=kb.staff_reg_handled_kb(reg["id"], can_reapprove=can_again),
        extra="\n".join(lines),
    )


@router.callback_query(F.data.startswith("srview:"))
async def sr_view(call: CallbackQuery, bot: Bot):
    if not await _is_staff(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    rid = int(call.data.split(":")[1])
    reg = await q.get_staff_reg(rid)
    if not reg:
        await call.answer("So'rov topilmadi.", show_alert=True)
        return
    if reg.get("status") == "new":
        await _send_reg_card(call.message, reg, markup=kb.staff_reg_actions_kb(rid))
    else:
        await _send_handled_reg(call.message, reg)
    await call.answer()


async def _send_staff_reg_file(bot, chat_id, file_id, caption):
    """Turini alohida saqlamaydigan ID/diplom faylini xavfsiz yuboradi."""
    if not file_id:
        return False
    try:
        await bot.send_photo(chat_id, file_id, caption=caption)
        return True
    except Exception:
        pass
    try:
        await bot.send_document(chat_id, file_id, caption=caption)
        return True
    except Exception:
        return False


@router.callback_query(F.data.startswith("srdocs:"))
async def sr_documents(call: CallbackQuery, bot: Bot):
    """Xodim so'rovidagi maxfiy ID/pasport va diplom fayllarini HR ga ko'rsatadi."""
    if not await _is_staff(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    rid = int(call.data.split(":")[1])
    reg = await q.get_staff_reg(rid)
    if not reg:
        await call.answer("So'rov topilmadi.", show_alert=True)
        return
    name = reg.get("full_name") or f"So'rov #{rid}"
    files = (
        (reg.get("passport_front"), f"🪪 {name} — pasport/ID old tomoni"),
        (reg.get("passport_back"), f"🪪 {name} — pasport/ID orqa tomoni"),
        (reg.get("diploma_file"), f"🎓 {name} — diplom"),
    )
    sent = 0
    for file_id, caption in files:
        if await _send_staff_reg_file(bot, call.message.chat.id, file_id, caption):
            sent += 1
    if not sent:
        await call.answer("Bu arizaga hujjat biriktirilmagan.", show_alert=True)
        return
    await call.answer(f"{sent} ta hujjat yuborildi ✅")


async def _reg_already_handled(call: CallbackQuery, rid):
    """So'rov allaqachon ko'rib chiqilgan: alertda KIM ko'rib chiqqani, keyin
    kartochka — xodim holati va «🔄 Boshidan tasdiqlash» tugmasi bilan."""
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    info = await q.request_handler_info("staff_regs", rid)
    await call.answer(handled_alert_text(info), show_alert=True)
    reg = await q.get_staff_reg(rid)
    if reg:
        await _send_handled_reg(call.message, reg)


async def _after_staff_approve(bot: Bot, chat: Message, me, rid, res, again=False):
    """Tasdiqdan keyingi xabarlar: HR ga natija, xodimga panel, kanalga post."""
    reg, role = res["reg"], res["role"]
    if res["created"]:
        state = "👥 Xodimlar ro'yxatiga <b>qo'shildi</b>."
    else:
        state = "👥 Xodim ro'yxatda edi — ma'lumotlari so'rovdagi bilan yangilandi."
    head = "🔄 Boshidan tasdiqlandi" if again else "✅ Tasdiqlandi"
    await chat.answer(
        f"{head}: xodim so'rovi #{rid}\n"
        f"👤 {reg.get('full_name')} — {ROLE_LABELS.get(role, role)}\n{state}"
    )
    if again and not res["created"]:
        employee_text = (
            "ℹ️ <b>Ma'lumotlaringiz HR tomonidan qayta tasdiqlandi.</b>\n"
            f"Panel: <b>{ROLE_LABELS.get(role, role)}</b>. Menyuni yangilash uchun /start bosing."
        )
    else:
        employee_text = (
            "🎉 <b>Tabriklaymiz!</b>\n\n"
            "Siz <b>Gulnora Farm hodimi</b> sifatida tasdiqlandingiz.\n"
            f"Sizga <b>{ROLE_LABELS.get(role, role)}</b> paneli ochildi.\n"
            "Yangilangan menyuni ko'rish uchun /start bosing."
        )
    await safe_send(bot, reg["user_tg"], employee_text, reply_markup=kb.main_menu(role))

    # Ma'lumotlarni kanalga joylash (admin «⚙️ Sozlamalar»da maxfiy kanalni ulagan
    # bo'lsa). Boshidan tasdiqlashda faqat avval rad etilgan bo'lsa joylanadi —
    # aks holda kanalda shu xodim ikki marta chiqib qolardi.
    if again and res["prev_status"] != "rejected":
        return
    full = await q.get_staff_reg(rid)
    posted = await post_staff_reg_to_channel(
        bot,
        await q.get_setting("secret_channel"),
        full,
        header=(
            "🏢 <b>YANGI XODIM — TASDIQLANDI</b>\n"
            f"🎯 Rol: {ROLE_LABELS.get(role, role)}\n"
            f"👔 Tasdiqladi: {me['full_name']}"
        ),
    )
    if posted is False:
        await chat.answer(
            "⚠️ Xodim ma'lumotlari kanalga joylanmadi. Bot kanalda administrator "
            "ekanini va kanal ID to'g'ri ulanganini tekshiring (⚙️ Sozlamalar)."
        )


@router.callback_query(F.data.startswith("sracc:"))
async def sr_approve(call: CallbackQuery, bot: Bot):
    if not await _is_staff(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    rid = int(call.data.split(":")[1])
    reg = await q.get_staff_reg(rid)
    if not reg:
        await call.answer("So'rov topilmadi.", show_alert=True)
        return
    if reg.get("status") != "new":
        await _reg_already_handled(call, rid)
        return
    me = await q.get_user(call.from_user.id)
    # ATOMIK — status, rol, profil va kadrlar harakati BITTA tranzaksiyada.
    # Avval status alohida yozilardi va profil yaratishda xato bo'lsa so'rov
    # «tasdiqlangan» bo'lib qolib, xodim ro'yxatga tushmasdi.
    try:
        res = await q.approve_staff_reg(rid, me["id"], allowed=("new",))
    except Exception:
        logger.exception("Xodim so'rovi #%s ni tasdiqlashda xatolik", rid)
        await call.answer(
            "⚠️ Tasdiqlashda xatolik yuz berdi — hech narsa o'zgarmadi. "
            "Bir ozdan keyin qayta bosing.", show_alert=True,
        )
        return
    if not res:
        await _reg_already_handled(call, rid)
        return
    # Bitta HR tasdiqladi — qolgan HR/adminlardagi so'rov xabari o'chiriladi
    await close_request_notices(bot, "staff_reg", rid, keep_chat_id=call.from_user.id)
    await q.add_log(call.from_user.id, me["full_name"], "hodim_tasdiqlandi", f"#{rid}")
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await call.answer("Tasdiqlandi ✅")
    await _after_staff_approve(bot, call.message, me, rid, res)


# ------- «🔄 Boshidan tasdiqlash» (tasdiqlangan / rad etilgan so'rov) -------
_REAPPROVE_HINTS = {
    "in_list": (
        "Xodim hozir ro'yxatda. Boshidan tasdiqlasangiz u ro'yxatdan chiqmaydi, "
        "lekin <b>profili so'rovdagi ma'lumotlar bilan yangilanadi</b> (rol, lavozim, "
        "filial, oylik, ish vaqti...). Keyinchalik qo'lda o'zgartirilgan qiymatlar "
        "ustidan yoziladi."
    ),
    "dismissed": (
        "Xodim ishdan bo'shatilgan. Boshidan tasdiqlasangiz u <b>ishga qayta "
        "olinadi</b> va «Ishdan bo'shaganlar» arxividan chiqadi."
    ),
    "missing": (
        "So'rov tasdiqlangan, lekin xodim ro'yxatga tushmay qolgan. Boshidan "
        "tasdiqlasangiz — xodim <b>ro'yxatga qo'shiladi</b> va unga panel ochiladi."
    ),
    "rejected": (
        "So'rov avval rad etilgan. Boshidan tasdiqlasangiz — xodim <b>ro'yxatga "
        "qo'shiladi</b>, unga panel ochiladi va xabar boradi."
    ),
    "awaiting": (
        "Xodim sinov muddatiga qabul qilingan va rahbar «Ishga keldi» ni kutmoqda. "
        "Boshidan tasdiqlasangiz — xodim darhol ro'yxatga qo'shiladi."
    ),
    "no_show": (
        "Rahbar «Ishga kelmadi» deb belgilagan. Boshidan tasdiqlasangiz — xodim "
        "ro'yxatga qo'shiladi."
    ),
}


@router.callback_query(F.data.startswith("sragain:"))
async def sr_reapprove_ask(call: CallbackQuery):
    if not await _is_staff(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    rid = int(call.data.split(":")[1])
    reg = await q.get_staff_reg(rid)
    if not reg:
        await call.answer("So'rov topilmadi.", show_alert=True)
        return
    if reg.get("status") not in ("approved", "rejected"):
        await call.answer(
            "Bu so'rovni boshidan tasdiqlab bo'lmaydi (holati: "
            f"{reg.get('status')}).", show_alert=True,
        )
        return
    key, lines, pres = await _reg_state(reg)
    role = reg.get("role") or ROLE_EMPLOYEE
    cur_role = (pres.get("user") or {}).get("role")
    role_line = ""
    if key == "in_list" and cur_role and cur_role != role:
        role_line = (
            f"\n⚠️ Rol o'zgaradi: hozirgi <b>{cur_role}</b> → so'rovdagi "
            f"<b>{ROLE_LABELS.get(role, role)}</b>"
        )
    await call.message.answer(
        f"🔄 <b>Boshidan tasdiqlash — so'rov #{rid}</b>\n"
        f"👤 {reg.get('full_name') or '-'} · {reg.get('position') or '-'}\n"
        "━━━━━━━━━━━━\n" + "\n".join(lines) + "\n\n"
        f"ℹ️ {_REAPPROVE_HINTS.get(key, _REAPPROVE_HINTS['missing'])}{role_line}\n\n"
        "Davom etamizmi?",
        reply_markup=kb.staff_reg_reapprove_confirm_kb(rid),
    )
    await call.answer()


@router.callback_query(F.data.startswith("sragno:"))
async def sr_reapprove_cancel(call: CallbackQuery):
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await call.answer("Bekor qilindi")


@router.callback_query(F.data.startswith("sragok:"))
async def sr_reapprove_do(call: CallbackQuery, bot: Bot):
    if not await _is_staff(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    rid = int(call.data.split(":")[1])
    me = await q.get_user(call.from_user.id)
    try:
        res = await q.approve_staff_reg(rid, me["id"], allowed=("approved", "rejected"))
    except Exception:
        logger.exception("Xodim so'rovi #%s ni boshidan tasdiqlashda xatolik", rid)
        await call.answer(
            "⚠️ Xatolik yuz berdi — hech narsa o'zgarmadi. Qayta urinib ko'ring.",
            show_alert=True,
        )
        return
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    if not res:
        await call.answer("So'rov holati o'zgargan — qaytadan oching.", show_alert=True)
        return
    # Rad etilgan so'rov xabarlari hali HR larda turgan bo'lishi mumkin
    await close_request_notices(bot, "staff_reg", rid, keep_chat_id=call.from_user.id)
    await q.add_log(call.from_user.id, me["full_name"], "hodim_qayta_tasdiqlandi",
                    f"#{rid} (avval: {res['prev_status']})")
    await call.answer("Boshidan tasdiqlandi ✅")
    await _after_staff_approve(bot, call.message, me, rid, res, again=True)


@router.callback_query(F.data.startswith("srrej:"))
async def sr_reject_start(call: CallbackQuery, state: FSMContext):
    """Rad etish — avval HR dan sabab so'raladi, keyingina so'rov yopiladi."""
    if not await _is_staff(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    rid = int(call.data.split(":")[1])
    reg = await q.get_staff_reg(rid)
    if not reg:
        await call.answer("So'rov topilmadi.", show_alert=True)
        return
    if reg.get("status") != "new":
        await _reg_already_handled(call, rid)
        return
    await state.set_state(StaffRegRejectForm.reason)
    await state.update_data(sreg_rid=rid)
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await call.message.answer(
        f"✍️ <b>Rad etish sababini yozing</b> (so'rov #{rid}).\n"
        "Yozgan sababingiz xodimga yuboriladi."
    )
    await call.answer()


@router.message(StaffRegRejectForm.reason, F.text)
async def sr_reject_reason(message: Message, state: FSMContext, bot: Bot):
    if not await _is_staff(message.from_user.id):
        await state.clear()
        return
    reason = message.text.strip()
    data = await state.get_data()
    rid = data.get("sreg_rid")
    await state.clear()
    reg = await q.get_staff_reg(rid)
    if not reg:
        await message.answer("So'rov topilmadi.")
        return
    me = await q.get_user(message.from_user.id)
    # ATOMIK — bir marta rad etiladi
    if not await q.claim_request("staff_regs", rid, "rejected", me["id"], "new"):
        info = await q.request_handler_info("staff_regs", rid)
        await message.answer("⚠️ " + handled_alert_text(info))
        return
    # Bitta HR rad etdi — qolgan HR/adminlardagi so'rov xabari o'chiriladi
    await close_request_notices(bot, "staff_reg", rid, keep_chat_id=message.from_user.id)
    await q.set_staff_reg_status(rid, "rejected", handled_by=me["id"], reject_reason=reason)
    await q.add_log(message.from_user.id, me["full_name"], "hodim_rad", f"#{rid}: {reason}")
    await message.answer(
        f"❌ Xodim so'rovi #{rid} rad etildi.\n✍️ Sabab: {reason}"
    )
    await safe_send(
        bot, reg["user_tg"],
        f"😔 <b>Sizning #{rid} raqamli arizangiz rad etildi.</b>\n\n"
        f"✍️ Sabab: {reason}\n\n"
        "Savollar bo'lsa HR bo'limi bilan bog'laning.",
    )
