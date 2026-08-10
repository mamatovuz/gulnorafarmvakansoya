"""Nomzod handlerlari: vakansiyalar, ariza topshirish, suhbat tasdiqlash."""
from datetime import datetime

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter

from database import queries as q
from database.db import ROLE_HR, ROLE_ADMIN, ST_NEW
from states import Apply, RescheduleForm, SalaryNegoForm
import keyboards as kb
from i18n import t, tf, canon, norm_lang
from utils import (
    vacancy_text, application_text, application_summary, safe_send,
    send_application_resume, send_application_photo, best_vacancy_matches,
    recommendation_text, now_tk, post_application_channel, send_application_card,
    normalize_phone, phone_from_contact, PHONE_HINT, update_interview_channel,
    missing_application_fields,
)

router = Router()

PHONE_ASK = (
    "📱 Telefon raqamingizni yozing.\n"
    "Faqat <b>bitta</b> raqam, <b>+998</b> bilan va orada bo'sh joysiz.\n"
    "Misol: <code>+998932303410</code>"
)


# ---------------- VAKANSIYALARNI KO'RISH ----------------
@router.message(tf("btn.vacancies"))
async def show_vacancies(message: Message):
    user = await q.get_user(message.from_user.id)
    # HR/Admin uchun shu tugma boshqaruv ro'yxatini ochadi — tahrirlash, yopish, o'chirish
    if user and user["role"] in (ROLE_HR, ROLE_ADMIN):
        vacs = await q.list_vacancies(active_only=False)
        if not vacs:
            await message.answer("Hali vakansiyalar yo'q.")
            return
        await message.answer(
            f"💼 <b>Vakansiyalar</b>\n\nJami: <b>{len(vacs)}</b> ta "
            "(filial rahbarlari yaratganlari ham shu yerda)\n"
            "Boshqarish uchun tanlang — tahrirlash, yopish yoki 🗑 o'chirish:",
            reply_markup=kb.vacancies_manage_list_kb(vacs),
        )
        return
    vacs = await q.list_vacancies(active_only=True)
    if not vacs:
        await message.answer("😔 Hozircha faol vakansiyalar yo'q. Keyinroq urinib ko'ring.")
        return
    await message.answer(
        "💼 <b>Bo'sh ish o'rinlari:</b>\nTanlash uchun bosing 👇",
        reply_markup=kb.vacancies_list_kb(vacs),
    )


@router.callback_query(F.data.startswith("vac:"))
async def vacancy_detail(call: CallbackQuery):
    vid = int(call.data.split(":")[1])
    v = await q.get_vacancy(vid)
    if not v or not v["is_active"]:
        await call.answer("Vakansiya topilmadi yoki yopilgan.", show_alert=True)
        return
    await call.message.edit_text(
        vacancy_text(v), reply_markup=kb.vacancy_detail_kb(vid)
    )
    await call.answer()


@router.callback_query(F.data == "vac_back")
async def vacancy_back(call: CallbackQuery):
    vacs = await q.list_vacancies(active_only=True)
    if not vacs:
        await call.message.edit_text("😔 Hozircha faol vakansiyalar yo'q.")
        return
    await call.message.edit_text(
        "💼 <b>Bo'sh ish o'rinlari:</b>\nTanlash uchun bosing 👇",
        reply_markup=kb.vacancies_list_kb(vacs),
    )
    await call.answer()


# ================= ISHGA ARIZA TOPSHIRISH (20 savol) =================
INTRO = (
    "📝 <b>Ishga ariza topshirish</b>\n\n"
    "Assalomu alaykum! Ishga ariza topshirish uchun quyidagi savollarga "
    "ketma-ket javob bering.\n"
    "Istalgan payt «❌ Bekor qilish» tugmasi bilan to'xtatishingiz mumkin.\n\n"
    "<b>1-savol</b>\n👤 Ism-sharifingizni kiriting.\nMisol: <i>Ravshanova Robiya</i>"
)


def parse_birthdate(text):
    """kun.oy.yil formatini tekshiradi. To'g'ri bo'lsa normal ko'rinishini qaytaradi."""
    text = text.strip()
    try:
        dt = datetime.strptime(text, "%d.%m.%Y")
    except ValueError:
        return None
    if not (1940 <= dt.year <= now_tk().year):
        return None
    return dt.strftime("%d.%m.%Y")


def resolve_branch(text, branches):
    """Tugma matnidan filial nomi va id sini aniqlaydi."""
    clean = text.replace("📍", "").strip()
    for br in branches:
        if br["name"].lower() == clean.lower():
            return br["name"], br["id"]
    return clean, None


def normalize_choice(text):
    return text.replace("✅", "").replace("❌", "").strip()


def gender_from_text(text):
    """«👨 Erkak» / «👩 Ayol» tugmasidan male/female ni aniqlaydi."""
    lower = (text or "").lower()
    if "erkak" in lower or "👨" in lower:
        return "male"
    if "ayol" in lower or "👩" in lower:
        return "female"
    return None


def is_pharmacist(position):
    return "farm" in (position or "").lower()


def uniform_status_from_text(text):
    lower = (text or "").lower()
    if "yo'q" in lower or "kerak" in lower:
        return "no"
    if "ha" in lower or "bor" in lower:
        return "yes"
    return "unknown"


def q_head(n, lang=None):
    """«N-savol» / «Вопрос N» sarlavhasi."""
    return t("apply.q_num", lang, n=n)


def position_extra_prompt(position, lang=None):
    head = q_head(9, lang)
    p = (position or "").lower()
    ru = norm_lang(lang) == "ru"
    if "farm" in p:
        body = ("💊 Выберите статус вашего фармацевтического документа или "
                "сертификата." if ru else
                "💊 Farmatsevtlik bo'yicha hujjatingiz yoki sertifikatingiz "
                "holatini tanlang.")
    elif "filial rahbari" in p:
        body = ("🏢 Командой из скольких сотрудников вы руководили ранее?" if ru else
                "🏢 Oldin nechta xodimdan iborat jamoani boshqargansiz?")
    elif "direktor" in p or "director" in p:
        body = ("👔 Каков ваш управленческий опыт в должности директора?" if ru else
                "👔 Direktor sifatida boshqaruv tajribangiz qancha?")
    else:
        body = (f"💼 Выберите ваш опыт работы по направлению «{position}»." if ru else
                f"💼 «{position}» bo'yicha ish tajribangizni tanlang.")
    return f"{head}\n{body}"


async def _start_apply(message: Message, state: FSMContext, vacancy=None, lang=None):
    await state.clear()
    if vacancy:
        # Vakansiyadan kirilganda filial va lavozim oldindan to'ldiriladi
        await state.update_data(
            _vacancy_id=vacancy["id"],
            _branch_id=vacancy.get("branch_id"),
            branch=vacancy.get("branch_name") or "-",
            position=vacancy["title"],
            _from_vacancy=True,
        )
    else:
        await state.update_data(_vacancy_id=None, _from_vacancy=False)
    await state.set_state(Apply.full_name)
    await message.answer(t("apply.intro", lang), reply_markup=kb.cancel_kb(lang))


# Menyu tugmasi
@router.message(tf("btn.apply"))
async def apply_menu(message: Message, state: FSMContext, lang: str = None):
    await _start_apply(message, state, lang=lang)


async def start_apply_from_deeplink(message: Message, state: FSMContext, payload,
                                    lang=None):
    """Kanaldagi «📝 Ishga ariza yuborish» tugmasidan kelingan `/start vac_<id>`.

    Anketa o'sha vakansiya uchun (filial va lavozim to'ldirilgan holda)
    boshlanadi. Anketa boshlangan bo'lsa True qaytadi."""
    try:
        vid = int(str(payload).replace("vac_", "", 1))
    except (TypeError, ValueError):
        return False
    v = await q.get_vacancy(vid)
    if not v:
        return False
    if v.get("filled") or not v.get("is_active"):
        await message.answer(
            "⏳ <b>Bu vakansiya yopilgan</b> — hodimlar soni to'lgan.\n"
            "Boshqa bo'sh ish o'rinlarini «💼 Vakansiyalar» bo'limidan ko'ring."
        )
        return False
    await message.answer(
        f"💼 <b>{v['title']}</b> — {v.get('branch_name') or 'filial'}\n"
        "Ariza topshirish uchun quyidagi savollarga javob bering."
    )
    await _start_apply(message, state, vacancy=v, lang=lang)
    return True


# Vakansiya ichidan "Ariza topshirish"
@router.callback_query(F.data.startswith("apply:"))
async def apply_from_vacancy(call: CallbackQuery, state: FSMContext, lang: str = None):
    vid = int(call.data.split(":")[1])
    v = await q.get_vacancy(vid)
    if not v or not v["is_active"]:
        await call.answer("Vakansiya endi mavjud emas.", show_alert=True)
        return
    await call.answer()
    await _start_apply(call.message, state, vacancy=v, lang=lang)


# --- BEKOR QILISH (istalgan bosqichda) ---
@router.message(StateFilter(
    Apply.full_name, Apply.birth_date, Apply.gender, Apply.city, Apply.district,
    Apply.address,
    Apply.branch, Apply.position, Apply.position_extra, Apply.uniform, Apply.shift,
    Apply.education, Apply.exp_years, Apply.prev_years, Apply.criminal,
    Apply.marital, Apply.children, Apply.prev_salary, Apply.expected_salary,
    Apply.computer_level, Apply.languages, Apply.work_intent,
    Apply.reason, Apply.phone, Apply.photo, Apply.resume, Apply.edit_field,
    Apply.edit_photo,
), F.text.in_(kb.CANCEL_BUTTONS))
async def apply_cancel(message: Message, state: FSMContext, lang: str = None):
    await state.clear()
    user = await q.get_user(message.from_user.id)
    has_applied = bool(user) and await q.count_applications(user["id"]) > 0
    await message.answer(
        t("apply.cancelled", lang),
        reply_markup=kb.main_menu(user["role"] if user else "candidate",
                                  has_applied, lang),
    )


# 1) Ism
@router.message(Apply.full_name, F.text)
async def a_name(message: Message, state: FSMContext, lang: str = None):
    await state.update_data(full_name=message.text.strip())
    await state.set_state(Apply.birth_date)
    await message.answer(
        f"{q_head(2, lang)}\n{t('apply.birth', lang)}",
        reply_markup=kb.cancel_kb(lang),
    )


# 2) Tug'ilgan sana
@router.message(Apply.birth_date, F.text)
async def a_birth(message: Message, state: FSMContext, lang: str = None):
    normalized = parse_birthdate(message.text)
    if not normalized:
        await message.answer(
            t("apply.birth_bad", lang), reply_markup=kb.cancel_kb(lang)
        )
        return
    await state.update_data(birth_date=normalized)
    await state.set_state(Apply.gender)
    await message.answer(
        f"{q_head(3, lang)}\n{t('apply.gender', lang)}",
        reply_markup=kb.apply_gender_kb(lang),
    )


# 3) Jins — vakansiyaga moslikni aniqlashda ishlatiladi
@router.message(Apply.gender, F.text)
async def a_gender(message: Message, state: FSMContext, lang: str = None):
    gender = gender_from_text(message.text)
    if not gender:
        await message.answer(
            t("apply.gender_bad", lang), reply_markup=kb.apply_gender_kb(lang)
        )
        return
    await state.update_data(gender=gender)
    await state.set_state(Apply.city)
    await message.answer(
        f"{q_head(4, lang)}\n{t('apply.city', lang)}",
        reply_markup=kb.apply_city_kb(),
    )


# 4) Shahar/viloyat
@router.message(Apply.city, F.text)
async def a_city(message: Message, state: FSMContext, lang: str = None):
    city = message.text.strip()
    if len(city) < 3:
        await message.answer(
            t("apply.city_bad", lang), reply_markup=kb.apply_city_kb()
        )
        return
    await state.update_data(city=city)
    await state.set_state(Apply.district)
    await message.answer(
        f"{q_head(5, lang)}\n{t('apply.district', lang)}",
        reply_markup=kb.apply_district_kb(city),
    )


# 5) Tuman
@router.message(Apply.district, F.text)
async def a_district(message: Message, state: FSMContext, lang: str = None):
    district = message.text.strip()
    if len(district) < 3:
        data = await state.get_data()
        await message.answer(
            t("apply.district_bad", lang),
            reply_markup=kb.apply_district_kb(data.get("city")),
        )
        return
    await state.update_data(district=district)
    await state.set_state(Apply.address)
    await message.answer(
        f"{q_head(6, lang)}\n{t('apply.address', lang)}",
        reply_markup=kb.cancel_kb(lang),
    )


# 6) Aniq manzil
@router.message(Apply.address, F.text)
async def a_address(message: Message, state: FSMContext, lang: str = None):
    address = message.text.strip()
    if len(address) < 5:
        await message.answer(
            t("apply.address_bad", lang), reply_markup=kb.cancel_kb(lang)
        )
        return
    await state.update_data(address=address)
    data = await state.get_data()
    # Vakansiyadan kirilgan bo'lsa filial allaqachon bor — lekin faqat
    # vakansiyada filial ko'rsatilgan bo'lsa. Aks holda filial so'raladi.
    if data.get("_from_vacancy") and data.get("_branch_id"):
        await _ask_position_extra(message, state, lang)
        return
    await _ask_branch(message, state, lang)


async def _ask_branch(message: Message, state: FSMContext, lang=None):
    branches = await q.list_branches()
    await state.set_state(Apply.branch)
    if branches:
        await message.answer(
            f"{q_head(7, lang)}\n{t('apply.branch', lang)}",
            reply_markup=kb.apply_branch_kb(branches),
        )
    else:
        await message.answer(
            f"{q_head(7, lang)}\n{t('apply.branch_write', lang)}",
            reply_markup=kb.cancel_kb(lang),
        )


# 7) Filial
@router.message(Apply.branch, F.text)
async def a_branch(message: Message, state: FSMContext, lang: str = None):
    branches = await q.list_branches()
    name, bid = resolve_branch(message.text, branches)
    # Filial ro'yxatdagi filialga to'g'ri kelmasa — qayta so'raymiz.
    # (Aks holda ariza filialsiz ketib, moslik filtri ishlamay qolardi.)
    if branches and not bid:
        await message.answer(
            t("apply.branch_bad", lang),
            reply_markup=kb.apply_branch_kb(branches),
        )
        return
    if not branches and len(name) < 3:
        await message.answer(
            t("apply.branch_bad", lang), reply_markup=kb.cancel_kb(lang)
        )
        return
    await state.update_data(branch=name, _branch_id=bid)
    await state.set_state(Apply.position)
    positions = await q.list_position_names()
    await message.answer(
        f"{q_head(8, lang)}\n{t('apply.position', lang)}",
        reply_markup=kb.apply_position_kb(positions),
    )


# 8) Lavozim
@router.message(Apply.position, F.text)
async def a_position(message: Message, state: FSMContext, lang: str = None):
    await state.update_data(position=message.text.strip())
    await _ask_position_extra(message, state, lang)


async def _ask_position_extra(message: Message, state: FSMContext, lang=None):
    data = await state.get_data()
    position = data.get("position")
    await state.set_state(Apply.position_extra)
    await message.answer(
        position_extra_prompt(position, lang),
        reply_markup=kb.apply_position_extra_kb(position, lang),
    )


# 9) Lavozim savoli
@router.message(Apply.position_extra, F.text)
async def a_position_extra(message: Message, state: FSMContext, lang: str = None):
    # Ma'lumot ro'yxatidan tanlangan bo'lsa — kanonik (uz) qiymatga qaytaramiz
    await state.update_data(position_extra=canon("education", message.text))
    # Forma savoli ishga arizada so'ralmaydi (u faqat «Gulnora Farm hodimi»da).
    await state.update_data(uniform_status="unknown")
    await _ask_shift(message, state, lang)


async def _ask_shift(message: Message, state: FSMContext, lang=None):
    await state.set_state(Apply.shift)
    await message.answer(
        f"{q_head(10, lang)}\n{t('apply.shift', lang)}",
        reply_markup=kb.apply_shift_kb(lang),
    )


# 10) Smena
@router.message(Apply.shift, F.text)
async def a_shift(message: Message, state: FSMContext, lang: str = None):
    await state.update_data(shift=canon("shift", message.text))
    await state.set_state(Apply.education)
    await message.answer(
        f"{q_head(11, lang)}\n{t('apply.education', lang)}",
        reply_markup=kb.apply_education_kb(lang),
    )


# 11) Ma'lumot
@router.message(Apply.education, F.text)
async def a_education(message: Message, state: FSMContext, lang: str = None):
    await state.update_data(education=canon("education", message.text))
    await state.set_state(Apply.exp_years)
    await message.answer(
        f"{q_head(12, lang)}\n{t('apply.exp', lang)}",
        reply_markup=kb.apply_experience_kb(lang),
    )


# 12) Umumiy tajriba
@router.message(Apply.exp_years, F.text)
async def a_exp(message: Message, state: FSMContext, lang: str = None):
    await state.update_data(exp_years=canon("experience", message.text))
    await state.set_state(Apply.prev_years)
    await message.answer(
        f"{q_head(13, lang)}\n{t('apply.prev_years', lang)}",
        reply_markup=kb.apply_prev_years_kb(lang),
    )


# 13) Oldingi ish joyi yili
@router.message(Apply.prev_years, F.text)
async def a_prev(message: Message, state: FSMContext, lang: str = None):
    await state.update_data(prev_years=canon("prev_years", message.text))
    await state.set_state(Apply.criminal)
    await message.answer(
        f"{q_head(14, lang)}\n{t('apply.criminal', lang)}",
        reply_markup=kb.apply_criminal_kb(lang),
    )


# 14) Sudlanganlik
@router.message(Apply.criminal, F.text)
async def a_criminal(message: Message, state: FSMContext, lang: str = None):
    await state.update_data(criminal=canon("criminal", message.text))
    await state.set_state(Apply.marital)
    await message.answer(
        f"{q_head(15, lang)}\n{t('apply.marital', lang)}",
        reply_markup=kb.apply_marital_kb(lang),
    )


# 15) Oilaviy holat
@router.message(Apply.marital, F.text)
async def a_marital(message: Message, state: FSMContext, lang: str = None):
    await state.update_data(marital=canon("marital", message.text))
    await state.set_state(Apply.children)
    await message.answer(
        t("apply.children", lang), reply_markup=kb.apply_children_kb(lang)
    )


# 15b) Farzandlar
@router.message(Apply.children, F.text)
async def a_children(message: Message, state: FSMContext, lang: str = None):
    await state.update_data(children=canon("children", message.text))
    await state.set_state(Apply.prev_salary)
    await message.answer(
        f"{q_head(16, lang)}\n{t('apply.prev_salary', lang)}",
        reply_markup=kb.cancel_kb(lang),
    )


# 16) Oldingi maosh
@router.message(Apply.prev_salary, F.text)
async def a_prevsalary(message: Message, state: FSMContext, lang: str = None):
    await state.update_data(prev_salary=message.text.strip())
    await state.set_state(Apply.expected_salary)
    await message.answer(
        f"{q_head(17, lang)}\n{t('apply.expected_salary', lang)}",
        reply_markup=kb.cancel_kb(lang),
    )


# 17) Kutilayotgan maosh
@router.message(Apply.expected_salary, F.text)
async def a_expsalary(message: Message, state: FSMContext, lang: str = None):
    await state.update_data(expected_salary=message.text.strip())
    await state.set_state(Apply.computer_level)
    await message.answer(
        f"{q_head(18, lang)}\n{t('apply.computer', lang)}",
        reply_markup=kb.apply_computer_kb(lang),
    )


# 18) Kompyuter savodxonligi (Word va Excel savollari o'rniga bitta savol)
@router.message(Apply.computer_level, F.text)
async def a_computer(message: Message, state: FSMContext, lang: str = None):
    value = canon("computer", message.text)
    if value not in kb.COMPUTER_LEVELS:
        await message.answer(
            t("common.pick_buttons", lang),
            reply_markup=kb.apply_computer_kb(lang),
        )
        return
    await state.update_data(computer_level=value)
    await state.set_state(Apply.languages)
    await message.answer(
        f"{q_head(19, lang)}\n{t('apply.languages', lang)}",
        reply_markup=kb.cancel_kb(lang),
    )


# 19) Tillar
@router.message(Apply.languages, F.text)
async def a_languages(message: Message, state: FSMContext, lang: str = None):
    await state.update_data(languages=message.text.strip())
    await state.set_state(Apply.work_intent)
    await message.answer(
        f"{q_head(20, lang)}\n{t('apply.work_intent', lang)}",
        reply_markup=kb.apply_work_intent_kb(lang),
    )


# 20) Ishlash niyati
@router.message(Apply.work_intent, F.text)
async def a_intent(message: Message, state: FSMContext, lang: str = None):
    await state.update_data(work_intent=canon("work_intent", message.text))
    await state.set_state(Apply.reason)
    await message.answer(
        f"{q_head(21, lang)}\n{t('apply.reason', lang)}",
        reply_markup=kb.cancel_kb(lang),
    )


# 21) Sabab
@router.message(Apply.reason, F.text)
async def a_reason(message: Message, state: FSMContext, lang: str = None):
    await state.update_data(reason=message.text.strip())
    await state.set_state(Apply.phone)
    await message.answer(
        f"{q_head(22, lang)}\n{t('apply.phone', lang)}",
        reply_markup=kb.apply_phone_kb(lang),
    )


# 22) Telefon — faqat +998XXXXXXXXX (bo'sh joysiz, bitta raqam)
@router.message(Apply.phone, F.contact)
async def a_phone_contact(message: Message, state: FSMContext, lang: str = None):
    phone = phone_from_contact(message.contact.phone_number)
    if not phone:
        await message.answer(
            t("apply.phone_bad", lang), reply_markup=kb.apply_phone_kb(lang)
        )
        return
    await state.update_data(phone=phone)
    await _ask_photo(message, state, lang)


@router.message(Apply.phone, F.text)
async def a_phone_text(message: Message, state: FSMContext, lang: str = None):
    phone = normalize_phone(message.text)
    if not phone:
        await message.answer(
            t("apply.phone_bad", lang), reply_markup=kb.apply_phone_kb(lang)
        )
        return
    await state.update_data(phone=phone)
    await _ask_photo(message, state, lang)


async def _ask_photo(message: Message, state: FSMContext, lang=None):
    """Oxirgi 10 kunda tushgan rasm — majburiy."""
    await state.set_state(Apply.photo)
    await message.answer(
        f"{q_head(23, lang)}\n{t('apply.photo', lang)}",
        reply_markup=kb.cancel_kb(lang),
    )


@router.message(Apply.photo, F.photo)
async def a_photo(message: Message, state: FSMContext, lang: str = None):
    await state.update_data(photo_file_id=message.photo[-1].file_id)
    await _ask_resume(message, state, lang)


@router.message(Apply.photo)
async def a_photo_invalid(message: Message, lang: str = None):
    # Rasm o'rniga boshqa narsa yuborilsa — qayta so'raymiz (majburiy)
    await message.answer(
        t("apply.photo_bad", lang), reply_markup=kb.cancel_kb(lang)
    )


async def _ask_resume(message: Message, state: FSMContext, lang=None):
    await state.set_state(Apply.resume)
    await message.answer(
        f"{q_head(24, lang)}\n{t('apply.resume', lang)}",
        reply_markup=kb.apply_resume_kb(lang),
    )


# 24) Rezyume (ixtiyoriy)
@router.message(Apply.resume, F.document)
async def a_resume_doc(message: Message, state: FSMContext, lang: str = None):
    await state.update_data(resume_file_id=message.document.file_id, resume_type="document")
    await _show_summary(message, state, lang)


@router.message(Apply.resume, F.photo)
async def a_resume_photo(message: Message, state: FSMContext, lang: str = None):
    await state.update_data(resume_file_id=message.photo[-1].file_id, resume_type="photo")
    await _show_summary(message, state, lang)


@router.message(Apply.resume, F.text)
async def a_resume_skip(message: Message, state: FSMContext, lang: str = None):
    # "⏭️ O'tkazib yuborish" yoki boshqa matn
    await _show_summary(message, state, lang)


# --------- YAKUNIY TASDIQLASH ---------
async def _show_summary(message: Message, state: FSMContext, lang=None):
    data = await state.get_data()
    await state.set_state(Apply.confirm)
    role = (await q.get_user(message.from_user.id) or {}).get("role", "candidate")
    await message.answer(
        t("apply.collected", lang), reply_markup=kb.main_menu(role, lang=lang)
    )
    await message.answer(application_summary(data), reply_markup=kb.apply_confirm_kb())


@router.callback_query(F.data == "app_cancel")
async def app_cancel_cb(call: CallbackQuery, state: FSMContext, lang: str = None):
    await state.clear()
    text = t("apply.cancelled", lang)
    try:
        await call.message.edit_text(text)
    except Exception:
        await call.message.answer(text)
    await call.answer()


@router.callback_query(F.data == "app_edit")
async def app_edit_cb(call: CallbackQuery):
    await call.message.answer(
        "✏️ Qaysi maydonni tahrirlaysiz?",
        reply_markup=kb.apply_edit_fields_kb(),
    )
    await call.answer()


@router.callback_query(F.data == "ef_back")
async def app_edit_back(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await call.message.answer(
        application_summary(data), reply_markup=kb.apply_confirm_kb()
    )
    await call.answer()


# Bitta maydonni tahrirlash uchun qayta so'rov
EDIT_PROMPTS = {
    "full_name": "👤 Yangi ism-sharif:",
    "birth_date": "📅 Yangi tug'ilgan sana (kun.oy.yil):",
    "address": "🏠 Yangi aniq manzil:",
    "position_extra": "🧩 Lavozim bo'yicha yangi javob:",
    "exp_years": "💼 Umumiy tajriba (yil):",
    "prev_years": "🏢 Oldingi ish joyida (yil):",
    "prev_salary": "💰 Oldingi maosh:",
    "expected_salary": "💵 Kutilayotgan maosh:",
    "languages": "🌍 Tillar:",
    "work_intent": "📅 Ishlash niyati:",
    "reason": "✍️ Sabab:",
}
EDIT_KEYBOARDS = {
    "city": kb.apply_city_kb,
    "shift": kb.apply_shift_kb,
    "education": kb.apply_education_kb,
    "criminal": kb.apply_criminal_kb,
    "marital": kb.apply_marital_kb,
    "children": kb.apply_children_kb,
    "exp_years": kb.apply_experience_kb,
    "prev_years": kb.apply_prev_years_kb,
    "computer_level": kb.apply_computer_kb,
    "work_intent": kb.apply_work_intent_kb,
}


@router.callback_query(F.data.startswith("ef:"))
async def app_edit_field(call: CallbackQuery, state: FSMContext):
    field = call.data.split(":")[1]
    await state.update_data(_edit_key=field)
    if field == "photo":
        # Rasm alohida holatda so'raladi (matn emas, foto kutiladi)
        await state.set_state(Apply.edit_photo)
        await call.message.answer(
            "📸 <b>Oxirgi 10 kun ichida tushgan</b> shaxsiy rasmingizni yuboring.\n"
            "<i>Faqat rasm qabul qilinadi.</i>",
            reply_markup=kb.cancel_kb(),
        )
        await call.answer()
        return
    await state.set_state(Apply.edit_field)
    if field == "branch":
        branches = await q.list_branches()
        markup = kb.apply_branch_kb(branches) if branches else kb.cancel_kb()
        await call.message.answer("🏢 Yangi filialni tanlang/yozing:", reply_markup=markup)
    elif field == "position":
        positions = await q.list_position_names()
        await call.message.answer(
            "💼 Yangi lavozimni tanlang:", reply_markup=kb.apply_position_kb(positions)
        )
    elif field == "district":
        data = await state.get_data()
        await call.message.answer(
            "📍 Yangi tumanni tanlang/yozing:",
            reply_markup=kb.apply_district_kb(data.get("city")),
        )
    elif field == "phone":
        await call.message.answer("✏️ Yangi telefon raqam.\n" + PHONE_HINT,
                                  reply_markup=kb.apply_phone_kb())
    elif field == "position_extra":
        data = await state.get_data()
        await call.message.answer(
            "🧩 Yangi qiymatni tanlang/yozing:",
            reply_markup=kb.apply_position_extra_kb(data.get("position")),
        )
    elif field in EDIT_KEYBOARDS:
        await call.message.answer("Yangi qiymatni tanlang:", reply_markup=EDIT_KEYBOARDS[field]())
    else:
        prompt = EDIT_PROMPTS.get(field, "Yangi qiymatni kiriting:")
        await call.message.answer(prompt, reply_markup=kb.cancel_kb())
    await call.answer()


@router.message(Apply.edit_field, F.contact)
async def app_edit_contact(message: Message, state: FSMContext):
    phone = phone_from_contact(message.contact.phone_number)
    if not phone:
        await message.answer("❗️ " + PHONE_HINT, reply_markup=kb.apply_phone_kb())
        return
    await state.update_data(phone=phone)
    await _back_to_summary(message, state)


@router.message(Apply.edit_field, F.text)
async def app_edit_save(message: Message, state: FSMContext):
    data = await state.get_data()
    field = data.get("_edit_key")
    value = message.text.strip()
    if field == "birth_date":
        norm = parse_birthdate(value)
        if not norm:
            await message.answer("❗️ Sana noto'g'ri (kun.oy.yil). Qaytadan kiriting:")
            return
        value = norm
    if field == "phone":
        norm = normalize_phone(value)
        if not norm:
            await message.answer("❗️ Telefon raqam noto'g'ri.\n" + PHONE_HINT)
            return
        value = norm
    # Manzil bo'laklari bo'sh yoki juda qisqa qolmasin
    MIN_LEN = {"city": 3, "district": 3, "address": 5, "full_name": 3}
    if field in MIN_LEN and len(value) < MIN_LEN[field]:
        await message.answer(
            f"❗️ Bu maydon majburiy — kamida {MIN_LEN[field]} ta belgi kiriting."
        )
        return
    if field == "branch":
        branches = await q.list_branches()
        name, bid = resolve_branch(value, branches)
        if branches and not bid:
            await message.answer(
                "❗️ Bunday filial topilmadi. Tugmalardan birini tanlang:",
                reply_markup=kb.apply_branch_kb(branches),
            )
            return
        await state.update_data(branch=name, _branch_id=bid)
    elif field == "uniform_status":
        await state.update_data(uniform_status=uniform_status_from_text(value))
    else:
        await state.update_data(**{field: value})
    await _back_to_summary(message, state)


@router.message(Apply.edit_photo, F.photo)
async def app_edit_photo(message: Message, state: FSMContext):
    await state.update_data(photo_file_id=message.photo[-1].file_id)
    await _back_to_summary(message, state)


@router.message(Apply.edit_photo)
async def app_edit_photo_invalid(message: Message):
    if message.text == kb.CANCEL_BTN:
        return  # bekor qilish handleri ishlaydi
    await message.answer(
        "❗️ Iltimos, <b>rasm (foto)</b> yuboring — oxirgi 10 kun ichida tushgan "
        "shaxsiy rasmingiz.",
        reply_markup=kb.cancel_kb(),
    )


async def _back_to_summary(message: Message, state: FSMContext):
    await state.set_state(Apply.confirm)
    data = await state.get_data()
    await message.answer("✅ O'zgartirildi.", reply_markup=kb.main_menu(
        (await q.get_user(message.from_user.id) or {}).get("role", "candidate")
    ))
    await message.answer(application_summary(data), reply_markup=kb.apply_confirm_kb())


@router.callback_query(F.data == "app_confirm")
async def app_confirm_cb(call: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    # Ma'lumot yo'q bo'lsa (sessiya tugagan / bot qayta ishga tushgan)
    if not data.get("full_name"):
        await call.answer(
            "⏳ Sessiya tugagan. Iltimos, «📝 Ishga ariza topshirish» orqali qaytadan boshlang.",
            show_alert=True,
        )
        await state.clear()
        try:
            await call.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        return

    # MAJBURIY maydonlar tekshiruvi — biror savol javobsiz qolsa ariza
    # yuborilmaydi (ilgari yarim to'ldirilgan arizalar ham o'tib ketardi).
    missing = missing_application_fields(data)
    if missing:
        await call.answer(
            f"⚠️ {len(missing)} ta savol to'ldirilmagan.", show_alert=True
        )
        try:
            await call.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        await call.message.answer(
            "⚠️ <b>Ariza yuborilmadi</b>\n\n"
            "Quyidagi savollarga javob berilmagan:\n"
            + "\n".join(f"  • {label}" for _, label in missing)
            + "\n\nUlarni to'ldirish uchun tugmani bosing 👇",
            reply_markup=kb.apply_missing_fields_kb(missing),
        )
        return

    user = await q.get_user(call.from_user.id)
    db_fields = [
        "full_name", "birth_date", "gender", "city", "district", "address", "position",
        "position_extra", "uniform_status", "shift", "education", "exp_years",
        "prev_years", "criminal", "marital", "children", "prev_salary",
        "expected_salary", "computer_level", "languages",
        "work_intent", "reason", "phone",
        "resume_file_id", "resume_type", "photo_file_id",
    ]
    app_data = {f: data.get(f) for f in db_fields}
    app_data["user_id"] = user["id"]
    app_data["vacancy_id"] = data.get("_vacancy_id")
    app_data["branch_id"] = data.get("_branch_id")
    aid = await q.add_application(app_data)
    # Panellarda Telegram nomi emas, anketada kiritilgan ism ko'rinsin
    await q.set_real_name(tg_id=call.from_user.id, full_name=app_data.get("full_name"))
    await state.clear()
    await q.add_log(
        call.from_user.id, call.from_user.full_name,
        "ariza_topshirdi", f"Ariza #{aid} — {data.get('position')}"
    )

    done_text = (
        f"✅ <b>Arizangiz muvaffaqiyatli qabul qilindi!</b>\n\n"
        f"Ariza raqami: #{aid}\n\n"
        f"HR bo'limi arizangizni ko'rib chiqadi va tez orada siz bilan bog'lanadi."
    )
    try:
        await call.message.edit_text(done_text)
    except Exception:
        await call.message.answer(done_text)
    await call.answer("Ariza yuborildi ✅")
    # Ariza topshirilgach to'liq menyuni ochamiz
    await call.message.answer(
        "🏠 Menyu yangilandi.",
        reply_markup=kb.main_menu(user["role"], has_applied=True),
    )

    # HR va Adminlarga yuborish
    app = await q.get_application(aid)
    hr_ids = await q.all_user_tg_ids(role=ROLE_HR)
    admin_ids = await q.all_user_tg_ids(role=ROLE_ADMIN)
    header = "🔔 <b>Yangi ariza keldi!</b>"
    if app.get("uniform_status") == "no":
        header = "👕 <b>Forma kerak!</b>\n" + header
    # Aynan vakansiyadan kelmagan bo'lsa — ochiq vakansiyalarga moslikni tekshirib,
    # HR ga avtomatik tavsiya beramiz (tasdiqlashidan oldin).
    rec = None
    if not app.get("vacancy_id"):
        try:
            threshold = int(await q.get_setting("match_threshold", "60") or "60")
        except (TypeError, ValueError):
            threshold = 60
        vacs = await q.list_vacancies(active_only=True)
        matches = best_vacancy_matches(app, vacs, threshold=threshold)
        rec = recommendation_text(matches, app)
    for tid in set(hr_ids + admin_ids):
        # Rasm + captionda ma'lumot + tugmalar — hammasi BITTA xabarda
        await send_application_card(
            bot, tid, app,
            reply_markup=kb.application_actions_kb(aid),
            header=header,
        )
        # Rezyume fayli bo'lsa alohida (hujjatni rasm bilan qo'shib bo'lmaydi)
        await send_application_resume(bot, tid, app)
        if rec:
            await safe_send(bot, tid, rec)

    # Nomzodlar (kutuvchilar) kanaliga avtomatik joylash (admin ulagan bo'lsa)
    candidate_channel = await q.get_setting("candidate_channel")
    if candidate_channel:
        chat_id, msg_id = await post_application_channel(bot, candidate_channel, app)
        if chat_id and msg_id:
            await q.set_application_channel(aid, chat_id, msg_id)


# ---------------- MENING ARIZALARIM ----------------
@router.message(tf("btn.my_apps"))
async def my_applications(message: Message):
    user = await q.get_user(message.from_user.id)
    apps = await q.user_applications(user["id"])
    if not apps:
        await message.answer("Sizda hali arizalar yo'q. «💼 Vakansiyalar» dan tanlang.")
        return
    await message.answer(
        f"📄 <b>Mening arizalarim</b>\n\nJami: <b>{len(apps)}</b> ta\n"
        "Batafsil ko'rish uchun arizani tanlang:",
        reply_markup=kb.applications_list_kb(apps, prefix="myapp"),
    )


@router.callback_query(F.data.startswith("myapp:"))
async def my_application_view(call: CallbackQuery, bot: Bot):
    aid = int(call.data.split(":")[1])
    user = await q.get_user(call.from_user.id)
    app = await q.get_application(aid)
    if not app or app.get("user_id") != user["id"]:
        await call.answer("Ariza topilmadi.", show_alert=True)
        return
    await send_application_card(bot, call.message.chat.id, app)
    await send_application_resume(bot, call.message.chat.id, app)
    await call.answer()


# ---------------- SUHBATNI TASDIQLASH / BOSHQA VAQT ----------------
@router.callback_query(F.data.startswith("iok:"))
async def interview_confirm(call: CallbackQuery, bot: Bot):
    iid = int(call.data.split(":")[1])
    interview = await q.get_interview(iid)
    if not interview:
        await call.answer("Suhbat topilmadi.", show_alert=True)
        return
    await q.set_interview_status(iid, "confirmed")
    await call.message.edit_text(
        call.message.html_text + "\n\n✅ <b>Siz suhbatni tasdiqladingiz!</b>"
    )
    await call.answer("Tasdiqlandi ✅")
    # HRga xabar
    app = await q.get_application(interview["application_id"])
    # Suhbat kanalidagi postni yangilaymiz (nomzod javobi = tasdiqladi)
    fresh = await q.get_interview(iid)
    if app and fresh:
        await update_interview_channel(bot, fresh, app)
    if interview.get("created_by"):
        creator = await q.get_user_by_id(interview["created_by"])
        if creator:
            await safe_send(
                bot, creator["tg_id"],
                f"✅ Nomzod <b>{app['full_name']}</b> (ariza #{app['id']}) "
                f"suhbatni tasdiqladi.\n📅 {interview['date']} {interview['time']}, "
                f"{interview['location']}",
            )


@router.callback_query(F.data.startswith("ire:"))
async def interview_reschedule_start(call: CallbackQuery, state: FSMContext):
    iid = int(call.data.split(":")[1])
    await state.update_data(interview_id=iid)
    await state.set_state(RescheduleForm.text)
    await call.message.answer(
        "🔄 Sizga qulay bo'lgan sana va vaqtni yozing (HR ga yetkaziladi):"
    )
    await call.answer()


@router.message(RescheduleForm.text, F.text)
async def interview_reschedule_send(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    iid = data.get("interview_id")
    await state.clear()
    interview = await q.get_interview(iid)
    if not interview:
        await message.answer("Suhbat topilmadi.")
        return
    await q.set_interview_status(iid, "reschedule")
    app = await q.get_application(interview["application_id"])
    # Suhbat kanalidagi postni yangilaymiz (nomzod javobi = boshqa vaqt)
    fresh = await q.get_interview(iid)
    if app and fresh:
        await update_interview_channel(bot, fresh, app)
    await message.answer("✅ Taklifingiz HR ga yuborildi. Ular siz bilan bog'lanadi.")
    if interview.get("created_by"):
        creator = await q.get_user_by_id(interview["created_by"])
        if creator:
            await safe_send(
                bot, creator["tg_id"],
                f"🔄 Nomzod <b>{app['full_name']}</b> (ariza #{app['id']}) "
                f"boshqa vaqt taklif qildi:\n\n«{message.text.strip()}»",
            )


# ---------------- OYLIK KELISHUVI (nomzod tomoni) ----------------
async def _notify_hr(bot: Bot, text, reply_markup=None):
    hr_ids = await q.all_user_tg_ids(role=ROLE_HR)
    admin_ids = await q.all_user_tg_ids(role=ROLE_ADMIN)
    for tid in set(hr_ids + admin_ids):
        await safe_send(bot, tid, text, reply_markup=reply_markup)


@router.callback_query(F.data.startswith("candsal_ok:"))
async def candidate_salary_agree(call: CallbackQuery, bot: Bot):
    """Nomzod HR taklif qilgan oylikni tasdiqlaydi."""
    aid = int(call.data.split(":")[1])
    app = await q.get_application(aid)
    user = await q.get_user(call.from_user.id)
    if not app or not user or app.get("user_id") != user["id"]:
        await call.answer("Ariza topilmadi.", show_alert=True)
        return
    amount = await q.agree_salary(aid)
    # Profil mavjud bo'lsa — darhol oylikni yozamiz
    profile = await q.get_employee_profile(user["id"])
    if profile:
        await q.update_monthly_salary(user["id"], amount)
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await call.message.answer(
        f"✅ Rahmat! Siz <b>{amount}</b> oylikni tasdiqladingiz. "
        "HR bo'limi tez orada siz bilan bog'lanadi."
    )
    await call.answer("Tasdiqlandi ✅")
    await _notify_hr(
        bot,
        f"✅ <b>Oylik kelishildi</b>\n\n"
        f"👤 {app.get('full_name')} (ariza #{aid}) siz taklif qilgan oylikni "
        f"tasdiqladi: <b>{amount}</b>.",
    )


@router.callback_query(F.data.startswith("candsal_other:"))
async def candidate_salary_counter_start(call: CallbackQuery, state: FSMContext):
    """Nomzod boshqa summa taklif qilmoqchi."""
    aid = int(call.data.split(":")[1])
    app = await q.get_application(aid)
    user = await q.get_user(call.from_user.id)
    if not app or not user or app.get("user_id") != user["id"]:
        await call.answer("Ariza topilmadi.", show_alert=True)
        return
    await state.set_state(SalaryNegoForm.candidate_amount)
    await state.update_data(sal_aid=aid)
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await call.message.answer(
        "✏️ O'zingiz xohlagan oylik summasini yozing (masalan: <b>5 000 000 so'm</b>):"
    )
    await call.answer()


@router.message(SalaryNegoForm.candidate_amount, F.text)
async def candidate_salary_counter_send(message: Message, state: FSMContext, bot: Bot):
    amount = message.text.strip()
    data = await state.get_data()
    aid = data.get("sal_aid")
    await state.clear()
    app = await q.get_application(aid)
    if not app:
        await message.answer("Ariza topilmadi.")
        return
    await q.set_salary_offer(aid, amount, "candidate")
    await message.answer(
        f"📤 Taklifingiz HR bo'limiga yuborildi: <b>{amount}</b>.\n"
        "Ular tasdiqlashi yoki boshqa summa taklif qilishi mumkin."
    )
    await _notify_hr(
        bot,
        f"💰 <b>Nomzoddan oylik taklifi</b>\n\n"
        f"👤 {app.get('full_name')} (ariza #{aid}) o'zi xohlagan oylikni "
        f"taklif qilmoqda: <b>{amount}</b>.\n\n"
        "Tasdiqlaysizmi yoki boshqa summa taklif qilasizmi?",
        reply_markup=kb.hr_salary_offer_kb(aid),
    )
