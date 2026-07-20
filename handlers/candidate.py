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
from utils import (
    vacancy_text, application_text, application_summary, safe_send,
    send_application_resume, send_application_photo, best_vacancy_matches,
    recommendation_text, now_tk, post_application_channel,
)

router = Router()


# ---------------- VAKANSIYALARNI KO'RISH ----------------
@router.message(F.text == "💼 Vakansiyalar")
async def show_vacancies(message: Message):
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


def is_pharmacist(position):
    return "farm" in (position or "").lower()


def uniform_status_from_text(text):
    lower = (text or "").lower()
    if "yo'q" in lower or "kerak" in lower:
        return "no"
    if "ha" in lower or "bor" in lower:
        return "yes"
    return "unknown"


def position_extra_prompt(position):
    p = (position or "").lower()
    if "farm" in p:
        return (
            "<b>8-savol</b>\n💊 Farmatsevtlik bo'yicha hujjatingiz yoki "
            "sertifikatingiz holatini tanlang."
        )
    if "filial rahbari" in p:
        return (
            "<b>8-savol</b>\n🏢 Oldin nechta xodimdan iborat jamoani "
            "boshqargansiz?"
        )
    if "direktor" in p or "director" in p:
        return "<b>8-savol</b>\n👔 Direktor sifatida boshqaruv tajribangiz qancha?"
    return f"<b>8-savol</b>\n💼 «{position}» bo'yicha ish tajribangizni tanlang."


async def _start_apply(message: Message, state: FSMContext, vacancy=None):
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
    await message.answer(INTRO, reply_markup=kb.cancel_kb())


# Menyu tugmasi
@router.message(F.text == "📝 Ishga ariza topshirish")
async def apply_menu(message: Message, state: FSMContext):
    await _start_apply(message, state)


# Vakansiya ichidan "Ariza topshirish"
@router.callback_query(F.data.startswith("apply:"))
async def apply_from_vacancy(call: CallbackQuery, state: FSMContext):
    vid = int(call.data.split(":")[1])
    v = await q.get_vacancy(vid)
    if not v or not v["is_active"]:
        await call.answer("Vakansiya endi mavjud emas.", show_alert=True)
        return
    await call.answer()
    await _start_apply(call.message, state, vacancy=v)


# --- BEKOR QILISH (istalgan bosqichda) ---
@router.message(StateFilter(
    Apply.full_name, Apply.birth_date, Apply.city, Apply.district, Apply.address,
    Apply.branch, Apply.position, Apply.position_extra, Apply.uniform, Apply.shift,
    Apply.education, Apply.exp_years, Apply.prev_years, Apply.criminal,
    Apply.marital, Apply.children, Apply.prev_salary, Apply.expected_salary,
    Apply.word_level, Apply.excel_level, Apply.languages, Apply.work_intent,
    Apply.reason, Apply.phone, Apply.photo, Apply.resume, Apply.edit_field,
), F.text == kb.CANCEL_BTN)
async def apply_cancel(message: Message, state: FSMContext):
    await state.clear()
    user = await q.get_user(message.from_user.id)
    has_applied = bool(user) and await q.count_applications(user["id"]) > 0
    await message.answer(
        "❌ Ariza bekor qilindi.",
        reply_markup=kb.main_menu(user["role"] if user else "candidate", has_applied),
    )


# 1) Ism
@router.message(Apply.full_name, F.text)
async def a_name(message: Message, state: FSMContext):
    await state.update_data(full_name=message.text.strip())
    await state.set_state(Apply.birth_date)
    await message.answer(
        "<b>2-savol</b>\n📅 Tug'ilgan sanangizni kiriting.\n"
        "Format: <b>kun.oy.yil</b>\nMisol: <i>29.08.2009</i>",
        reply_markup=kb.cancel_kb(),
    )


# 2) Tug'ilgan sana
@router.message(Apply.birth_date, F.text)
async def a_birth(message: Message, state: FSMContext):
    normalized = parse_birthdate(message.text)
    if not normalized:
        await message.answer(
            "❗️ Sana noto'g'ri. Iltimos <b>kun.oy.yil</b> ko'rinishida kiriting.\n"
            "Misol: <i>29.08.2009</i>",
            reply_markup=kb.cancel_kb(),
        )
        return
    await state.update_data(birth_date=normalized)
    await state.set_state(Apply.city)
    await message.answer(
        "<b>3-savol</b>\n🌆 Qaysi shahar/viloyatda yashaysiz?",
        reply_markup=kb.apply_city_kb(),
    )


# 3) Shahar/viloyat
@router.message(Apply.city, F.text)
async def a_city(message: Message, state: FSMContext):
    city = message.text.strip()
    await state.update_data(city=city)
    await state.set_state(Apply.district)
    await message.answer(
        "<b>4-savol</b>\n📍 Tumaningizni tanlang.",
        reply_markup=kb.apply_district_kb(city),
    )


# 4) Tuman
@router.message(Apply.district, F.text)
async def a_district(message: Message, state: FSMContext):
    await state.update_data(district=message.text.strip())
    await state.set_state(Apply.address)
    await message.answer(
        "<b>5-savol</b>\n🏠 Aniq manzilingizni yuboring.\n"
        "Misol: <i>Xursandlik MFY, 37-uy</i>",
        reply_markup=kb.cancel_kb(),
    )


# 5) Aniq manzil
@router.message(Apply.address, F.text)
async def a_address(message: Message, state: FSMContext):
    await state.update_data(address=message.text.strip())
    data = await state.get_data()
    # Agar vakansiyadan kirilgan bo'lsa — filial va lavozim allaqachon bor
    if data.get("_from_vacancy"):
        await _ask_position_extra(message, state)
        return
    branches = await q.list_branches()
    await state.set_state(Apply.branch)
    if branches:
        await message.answer(
            "<b>6-savol</b>\n🏢 Ishlamoqchi bo'lgan filialni tanlang.",
            reply_markup=kb.apply_branch_kb(branches),
        )
    else:
        await message.answer(
            "<b>6-savol</b>\n🏢 Ishlamoqchi bo'lgan filial nomini yozing:",
            reply_markup=kb.cancel_kb(),
        )


# 4) Filial
@router.message(Apply.branch, F.text)
async def a_branch(message: Message, state: FSMContext):
    branches = await q.list_branches()
    name, bid = resolve_branch(message.text, branches)
    await state.update_data(branch=name, _branch_id=bid)
    await state.set_state(Apply.position)
    positions = await q.list_position_names()
    await message.answer(
        "<b>7-savol</b>\n💼 Qaysi yo'nalish bo'yicha ishga kirmoqchisiz?",
        reply_markup=kb.apply_position_kb(positions),
    )


# 7) Lavozim
@router.message(Apply.position, F.text)
async def a_position(message: Message, state: FSMContext):
    await state.update_data(position=message.text.strip())
    await _ask_position_extra(message, state)


async def _ask_position_extra(message: Message, state: FSMContext):
    data = await state.get_data()
    position = data.get("position")
    await state.set_state(Apply.position_extra)
    await message.answer(
        position_extra_prompt(position),
        reply_markup=kb.apply_position_extra_kb(position),
    )


@router.message(Apply.position_extra, F.text)
async def a_position_extra(message: Message, state: FSMContext):
    await state.update_data(position_extra=message.text.strip())
    # Forma savoli ishga arizada so'ralmaydi (u faqat «Gulnora Farm hodimi»da).
    await state.update_data(uniform_status="unknown")
    await _ask_shift(message, state)


async def _ask_shift(message: Message, state: FSMContext):
    await state.set_state(Apply.shift)
    await message.answer(
        "<b>9-savol</b>\n🕒 Qaysi smenada ishlay olasiz?",
        reply_markup=kb.apply_shift_kb(),
    )


# 6) Smena
@router.message(Apply.shift, F.text)
async def a_shift(message: Message, state: FSMContext):
    await state.update_data(shift=message.text.strip())
    await state.set_state(Apply.education)
    await message.answer(
        "<b>11-savol</b>\n🎓 Ma'lumot darajangizni tanlang.",
        reply_markup=kb.apply_education_kb(),
    )


# 7) Ma'lumot
@router.message(Apply.education, F.text)
async def a_education(message: Message, state: FSMContext):
    await state.update_data(education=message.text.strip())
    await state.set_state(Apply.exp_years)
    await message.answer(
        "<b>12-savol</b>\n💼 Umumiy ish tajribangiz qancha?",
        reply_markup=kb.apply_experience_kb(),
    )


# 8) Umumiy tajriba
@router.message(Apply.exp_years, F.text)
async def a_exp(message: Message, state: FSMContext):
    await state.update_data(exp_years=message.text.strip())
    await state.set_state(Apply.prev_years)
    await message.answer(
        "<b>13-savol</b>\n🏢 Oldingi ish joyingizda qancha ishlagansiz?",
        reply_markup=kb.apply_prev_years_kb(),
    )


# 9) Oldingi ish joyi yili
@router.message(Apply.prev_years, F.text)
async def a_prev(message: Message, state: FSMContext):
    await state.update_data(prev_years=message.text.strip())
    await state.set_state(Apply.criminal)
    await message.answer(
        "<b>14-savol</b>\n⚖️ Sudlanganmisiz?",
        reply_markup=kb.apply_criminal_kb(),
    )


# 10) Sudlanganlik
@router.message(Apply.criminal, F.text)
async def a_criminal(message: Message, state: FSMContext):
    await state.update_data(criminal=message.text.strip())
    await state.set_state(Apply.marital)
    await message.answer(
        "<b>15-savol</b>\n👨‍👩‍👧 Oilaviy holatingizni tanlang.",
        reply_markup=kb.apply_marital_kb(),
    )


# 11) Oilaviy holat
@router.message(Apply.marital, F.text)
async def a_marital(message: Message, state: FSMContext):
    await state.update_data(marital=message.text.strip())
    await state.set_state(Apply.children)
    await message.answer(
        "👶 Farzandlaringiz bormi?",
        reply_markup=kb.apply_children_kb(),
    )


# 11b) Farzandlar
@router.message(Apply.children, F.text)
async def a_children(message: Message, state: FSMContext):
    await state.update_data(children=message.text.strip())
    await state.set_state(Apply.prev_salary)
    await message.answer(
        "<b>16-savol</b>\n💰 Oxirgi ish joyingizdagi maoshingiz qancha edi?\n"
        "Misol: <i>2 000 000 so'm</i>",
        reply_markup=kb.cancel_kb(),
    )


# 12) Oldingi maosh
@router.message(Apply.prev_salary, F.text)
async def a_prevsalary(message: Message, state: FSMContext):
    await state.update_data(prev_salary=message.text.strip())
    await state.set_state(Apply.expected_salary)
    await message.answer(
        "<b>17-savol</b>\n💵 Qancha maoshga ishlashni xohlaysiz?\n"
        "Misol: <i>3 000 000 so'm</i>",
        reply_markup=kb.cancel_kb(),
    )


# 13) Kutilayotgan maosh
@router.message(Apply.expected_salary, F.text)
async def a_expsalary(message: Message, state: FSMContext):
    await state.update_data(expected_salary=message.text.strip())
    await state.set_state(Apply.word_level)
    await message.answer(
        "<b>18-savol</b>\n📝 Microsoft Word dasturini qay darajada bilasiz?",
        reply_markup=kb.apply_level_kb(),
    )


# 14) Word
@router.message(Apply.word_level, F.text)
async def a_word(message: Message, state: FSMContext):
    await state.update_data(word_level=message.text.strip())
    await state.set_state(Apply.excel_level)
    await message.answer(
        "<b>19-savol</b>\n📊 Microsoft Excel dasturini qay darajada bilasiz?",
        reply_markup=kb.apply_level_kb(),
    )


# 15) Excel
@router.message(Apply.excel_level, F.text)
async def a_excel(message: Message, state: FSMContext):
    await state.update_data(excel_level=message.text.strip())
    await state.set_state(Apply.languages)
    await message.answer(
        "<b>20-savol</b>\n🌍 Qaysi tillarni bilasiz?\n"
        "Misol: <i>O'zbek - A'lo, Rus - O'rtacha, Ingliz - Boshlang'ich</i>",
        reply_markup=kb.cancel_kb(),
    )


# 16) Tillar
@router.message(Apply.languages, F.text)
async def a_languages(message: Message, state: FSMContext):
    await state.update_data(languages=message.text.strip())
    await state.set_state(Apply.work_intent)
    await message.answer(
        "<b>21-savol</b>\n📅 «Gulnora Farm»da qancha muddat ishlash niyatingiz bor?",
        reply_markup=kb.apply_work_intent_kb(),
    )


# 17) Ishlash niyati
@router.message(Apply.work_intent, F.text)
async def a_intent(message: Message, state: FSMContext):
    await state.update_data(work_intent=message.text.strip())
    await state.set_state(Apply.reason)
    await message.answer(
        "<b>22-savol</b>\n✍️ Nima uchun aynan Gulnora Farmda ishlashni xohlaysiz?\n"
        "Misol: <i>Jamoasi yaxshi, rivojlanish imkoniyati bor.</i>",
        reply_markup=kb.cancel_kb(),
    )


# 18) Sabab
@router.message(Apply.reason, F.text)
async def a_reason(message: Message, state: FSMContext):
    await state.update_data(reason=message.text.strip())
    await state.set_state(Apply.phone)
    await message.answer(
        "<b>23-savol</b>\n📱 Telefon raqamingizni yuboring.",
        reply_markup=kb.apply_phone_kb(),
    )


# 19) Telefon (contact yoki matn)
@router.message(Apply.phone, F.contact)
async def a_phone_contact(message: Message, state: FSMContext):
    await state.update_data(phone=message.contact.phone_number)
    await _ask_photo(message, state)


@router.message(Apply.phone, F.text)
async def a_phone_text(message: Message, state: FSMContext):
    digits = "".join(c for c in message.text if c.isdigit())
    if len(digits) < 7:
        await message.answer(
            "❗️ Telefon raqam noto'g'ri. «📲 Telefon raqamni yuborish» tugmasidan "
            "foydalaning yoki to'g'ri raqam yozing.",
            reply_markup=kb.apply_phone_kb(),
        )
        return
    await state.update_data(phone=message.text.strip())
    await _ask_photo(message, state)


async def _ask_photo(message: Message, state: FSMContext):
    """Oxirgi 10 kunda tushgan rasm — majburiy."""
    await state.set_state(Apply.photo)
    await message.answer(
        "<b>24-savol</b>\n📸 Iltimos, <b>oxirgi 10 kun ichida tushgan</b> shaxsiy "
        "rasmingizni yuboring.\n\n"
        "<i>Rasm aniq va yaqinda olingan bo'lishi shart. Bu majburiy bosqich.</i>",
        reply_markup=kb.cancel_kb(),
    )


@router.message(Apply.photo, F.photo)
async def a_photo(message: Message, state: FSMContext):
    await state.update_data(photo_file_id=message.photo[-1].file_id)
    await _ask_resume(message, state)


@router.message(Apply.photo)
async def a_photo_invalid(message: Message):
    # Rasm o'rniga boshqa narsa yuborilsa — qayta so'raymiz (majburiy)
    await message.answer(
        "❗️ Iltimos, <b>rasm (foto)</b> yuboring — oxirgi 10 kun ichida tushgan "
        "shaxsiy rasmingiz. Faqat rasm qabul qilinadi.",
        reply_markup=kb.cancel_kb(),
    )


async def _ask_resume(message: Message, state: FSMContext):
    await state.set_state(Apply.resume)
    await message.answer(
        "<b>25-savol</b>\n📄 Rezyume (CV) yoki diplom rasmini yubormoqchimisiz?\n"
        "Faylni yuboring yoki «⏭️ O'tkazib yuborish» tugmasini bosing.",
        reply_markup=kb.apply_resume_kb(),
    )


# 20) Rezyume
@router.message(Apply.resume, F.document)
async def a_resume_doc(message: Message, state: FSMContext):
    await state.update_data(resume_file_id=message.document.file_id, resume_type="document")
    await _show_summary(message, state)


@router.message(Apply.resume, F.photo)
async def a_resume_photo(message: Message, state: FSMContext):
    await state.update_data(resume_file_id=message.photo[-1].file_id, resume_type="photo")
    await _show_summary(message, state)


@router.message(Apply.resume, F.text)
async def a_resume_skip(message: Message, state: FSMContext):
    # "⏭️ O'tkazib yuborish" yoki boshqa matn
    await _show_summary(message, state)


# --------- YAKUNIY TASDIQLASH ---------
async def _show_summary(message: Message, state: FSMContext):
    data = await state.get_data()
    await state.set_state(Apply.confirm)
    await message.answer("✅ Ma'lumotlar to'plandi.", reply_markup=kb.main_menu(
        (await q.get_user(message.from_user.id) or {}).get("role", "candidate")
    ))
    await message.answer(application_summary(data), reply_markup=kb.apply_confirm_kb())


@router.callback_query(F.data == "app_cancel")
async def app_cancel_cb(call: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await call.message.edit_text("❌ Ariza bekor qilindi.")
    except Exception:
        await call.message.answer("❌ Ariza bekor qilindi.")
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
    "word_level": kb.apply_level_kb,
    "excel_level": kb.apply_level_kb,
    "work_intent": kb.apply_work_intent_kb,
}


@router.callback_query(F.data.startswith("ef:"))
async def app_edit_field(call: CallbackQuery, state: FSMContext):
    field = call.data.split(":")[1]
    await state.update_data(_edit_key=field)
    await state.set_state(Apply.edit_field)
    if field == "branch":
        branches = await q.list_branches()
        markup = kb.apply_branch_kb(branches) if branches else kb.cancel_kb()
        await call.message.answer("🏢 Yangi filialni tanlang/yozing:", reply_markup=markup)
    elif field == "position":
        positions = await q.list_position_names()
        await call.message.answer(
            "💼 Yangi yo'nalishni tanlang:", reply_markup=kb.apply_position_kb(positions)
        )
    elif field == "district":
        data = await state.get_data()
        await call.message.answer(
            "📍 Yangi tumanni tanlang/yozing:",
            reply_markup=kb.apply_district_kb(data.get("city")),
        )
    elif field == "phone":
        await call.message.answer("📱 Yangi telefon raqam:", reply_markup=kb.apply_phone_kb())
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
    await state.update_data(phone=message.contact.phone_number)
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
    if field == "branch":
        branches = await q.list_branches()
        name, bid = resolve_branch(value, branches)
        await state.update_data(branch=name, _branch_id=bid)
    elif field == "uniform_status":
        await state.update_data(uniform_status=uniform_status_from_text(value))
    else:
        await state.update_data(**{field: value})
    await _back_to_summary(message, state)


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

    user = await q.get_user(call.from_user.id)
    db_fields = [
        "full_name", "birth_date", "city", "district", "address", "position",
        "position_extra", "uniform_status", "shift", "education", "exp_years",
        "prev_years", "criminal", "marital", "children", "prev_salary",
        "expected_salary", "word_level", "excel_level", "languages",
        "work_intent", "reason", "phone",
        "resume_file_id", "resume_type", "photo_file_id",
    ]
    app_data = {f: data.get(f) for f in db_fields}
    app_data["user_id"] = user["id"]
    app_data["vacancy_id"] = data.get("_vacancy_id")
    app_data["branch_id"] = data.get("_branch_id")
    aid = await q.add_application(app_data)
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
    text = "🔔 <b>Yangi ariza keldi!</b>\n\n" + application_text(app, full=True)
    if app.get("uniform_status") == "no":
        text = "👕 <b>Forma kerak!</b>\n\n" + text
    # Aynan vakansiyadan kelmagan bo'lsa — ochiq vakansiyalarga moslikni tekshirib,
    # HR ga avtomatik tavsiya beramiz (tasdiqlashidan oldin).
    if not app.get("vacancy_id"):
        try:
            threshold = int(await q.get_setting("match_threshold", "60") or "60")
        except (TypeError, ValueError):
            threshold = 60
        vacs = await q.list_vacancies(active_only=True)
        matches = best_vacancy_matches(app, vacs, threshold=threshold)
        rec = recommendation_text(matches)
        if rec:
            text += "\n" + rec
    for tid in set(hr_ids + admin_ids):
        await safe_send(bot, tid, text, reply_markup=kb.application_actions_kb(aid))
        # Oxirgi 10 kunda tushgan rasm
        await send_application_photo(bot, tid, app)
        # Rezyume fayli bo'lsa alohida yuboramiz
        await send_application_resume(bot, tid, app)

    # Nomzodlar (kutuvchilar) kanaliga avtomatik joylash (admin ulagan bo'lsa)
    candidate_channel = await q.get_setting("candidate_channel")
    if candidate_channel:
        chat_id, msg_id = await post_application_channel(bot, candidate_channel, app)
        if chat_id and msg_id:
            await q.set_application_channel(aid, chat_id, msg_id)


# ---------------- MENING ARIZALARIM ----------------
@router.message(F.text == "📄 Mening arizalarim")
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
    await call.message.answer(application_text(app, full=True))
    await send_application_photo(bot, call.message.chat.id, app)
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
