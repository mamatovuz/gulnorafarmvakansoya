"""Umumiy handlerlar: /start, majburiy obuna, yordam, asosiy menyu."""
from aiogram import Router, F, Bot
from aiogram.filters import CommandStart, Command, CommandObject
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from database import queries as q
from database.db import (
    ROLE_CANDIDATE, ROLE_HR, ROLE_ADMIN, ROLE_ACCOUNTANT, ROLE_DIRECTOR,
    ROLE_MANAGER, ROLE_IT, ROLE_PHARMACIST,
)
from states import Reg, GenericEmpSearch
import keyboards as kb
from i18n import t, tf, norm_lang
from utils import check_subscription, get_welcome_text

router = Router()

# Xodim qidiruvidan foydalana oladigan panel rollari
PANEL_ROLES = {
    ROLE_HR, ROLE_ADMIN, ROLE_ACCOUNTANT, ROLE_DIRECTOR, ROLE_MANAGER,
    ROLE_IT, ROLE_PHARMACIST,
}


# ---------------- UMUMIY XODIM QIDIRUVI (ism bo'yicha, panelga mos) ----------------
@router.callback_query(F.data.startswith("empfind:"))
async def emp_find_start(call: CallbackQuery, state: FSMContext):
    """«🔍 Xodim qidirish» — moliya/IT/rahbar/direktor panellari uchun.

    Natija tugmalari qaysi panel chaqirganiga qarab (prefix) ochiladi."""
    user = await q.get_user(call.from_user.id)
    if not user or user.get("role") not in PANEL_ROLES:
        await call.answer("⛔", show_alert=True)
        return
    prefix = call.data.split(":")[1]
    await state.set_state(GenericEmpSearch.query)
    await state.update_data(emp_find_prefix=prefix)
    await call.message.answer(
        "🔤 Xodimning <b>ismi</b>, <b>@username</b>, <b>telefoni</b> yoki "
        "<b>ID</b> sini yozing.\n"
        "<i>To'liq yozish shart emas — bir qismi ham yetadi.</i>"
    )
    await call.answer()


@router.message(GenericEmpSearch.query, F.text)
async def emp_find_run(message: Message, state: FSMContext):
    data = await state.get_data()
    prefix = data.get("emp_find_prefix", "empview")
    await state.clear()
    user = await q.get_user(message.from_user.id)
    if not user or user.get("role") not in PANEL_ROLES:
        return
    # Filial rahbari faqat o'z filiali xodimlarini qidiradi
    branch_id = user.get("branch_id") if user.get("role") == ROLE_MANAGER else None
    text = message.text.strip()
    profiles = await q.search_employees(text=text, branch_id=branch_id)
    if not profiles:
        await message.answer(
            f"😔 «{text}» bo'yicha xodim topilmadi. Boshqa so'z bilan urinib ko'ring."
        )
        return
    await message.answer(
        f"🔍 <b>Qidiruv:</b> {text} — <b>{len(profiles)}</b> ta topildi\nTanlang:",
        reply_markup=kb.employee_profiles_list_kb(
            profiles[:30], prefix=prefix, with_search=False
        ),
    )


# Hujjatlarni (pasport/ID, diplom) ko'ra oladigan rollar
DOCS_ROLES = {ROLE_HR, ROLE_ADMIN, ROLE_MANAGER, ROLE_DIRECTOR}


async def _send_doc(call: CallbackQuery, file_id, caption):
    """file_id rasm yoki hujjat bo'lishi mumkin — avval rasm, bo'lmasa hujjat sifatida."""
    try:
        await call.message.answer_photo(file_id, caption=caption)
        return
    except Exception:
        pass
    try:
        await call.message.answer_document(file_id, caption=caption)
    except Exception:
        await call.message.answer(f"⚠️ {caption} — faylni ko'rsatib bo'lmadi (eskirgan).")


@router.callback_query(F.data.startswith("empdocs:"))
async def emp_docs_view(call: CallbackQuery):
    """«🪪 Hujjatlar» — xodimning pasport/ID oldi-orqa va diplom rasmini ko'rsatadi.
    Faqat HR / admin / filial rahbari / direktor uchun (maxfiy — kanalga chiqmaydi)."""
    user = await q.get_user(call.from_user.id)
    if not user or user.get("role") not in DOCS_ROLES:
        await call.answer("⛔ Ruxsat yo'q.", show_alert=True)
        return
    uid = int(call.data.split(":")[1])
    profile = await q.get_employee_profile(uid)
    if not profile:
        await call.answer("Xodim topilmadi.", show_alert=True)
        return
    # Filial rahbari faqat o'z filiali xodimini ko'radi
    if user.get("role") == ROLE_MANAGER and profile.get("branch_id") != user.get("branch_id"):
        await call.answer("⛔ Bu xodim sizning filialingizga tegishli emas.",
                          show_alert=True)
        return
    name = profile.get("full_name") or "Xodim"
    front = profile.get("passport_front")
    back = profile.get("passport_back")
    diploma = profile.get("diploma_file")
    if not (front or back or diploma):
        await call.answer("Bu xodimda saqlangan hujjat yo'q.", show_alert=True)
        return
    await call.answer()
    await call.message.answer(f"🪪 <b>{name}</b> — hujjatlari (maxfiy):")
    if front:
        await _send_doc(call, front, "🪪 Pasport / ID karta — oldi tomoni")
    if back:
        await _send_doc(call, back, "🪪 Pasport / ID karta — orqa tomoni")
    if diploma:
        await _send_doc(call, diploma, "🎓 Diplom")


async def show_subscription(message: Message):
    channels = await q.list_channels(active_only=True)
    if not channels:
        return False
    await message.answer(
        "📢 <b>Botdan foydalanish uchun quyidagi kanal(lar)ga obuna bo'ling:</b>\n\n"
        "Obuna bo'lgach «✅ Tekshirish» tugmasini bosing.",
        reply_markup=kb.subscription_kb(channels),
    )
    return True


async def send_main_menu(message: Message, user, lang=None):
    has_applied = False
    if user.get("role") == ROLE_CANDIDATE:
        has_applied = await q.count_applications(user["id"]) > 0
    lang = lang or user.get("lang")
    await message.answer(
        t("menu.main", lang),
        reply_markup=kb.main_menu(user["role"], has_applied, lang),
    )


# ---------------- TIL TANLASH ----------------
@router.message(tf("btn.lang"))
async def change_lang(message: Message, state: FSMContext, lang: str = None):
    """«🌐 Til» tugmasi — istalgan paytda tilni almashtirish."""
    await state.clear()
    await message.answer(t("lang.ask", lang), reply_markup=kb.lang_pick_kb())


@router.callback_query(F.data.startswith("setlang:"))
async def set_lang(call: CallbackQuery, state: FSMContext, bot: Bot):
    """Til tanlandi — saqlaymiz va menyuni yangi tilda qayta chiqaramiz."""
    new_lang = norm_lang(call.data.split(":")[1])
    await q.get_or_create_user(
        call.from_user.id, call.from_user.full_name, call.from_user.username,
    )
    await q.set_user_lang(call.from_user.id, new_lang)
    await state.clear()
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await call.message.answer(t("lang.changed", new_lang))

    user = await q.get_user(call.from_user.id)
    # Majburiy obuna tekshiruvi tildan keyin
    not_joined = await check_subscription(bot, call.from_user.id)
    if not_joined:
        await show_subscription(call.message)
        await call.answer()
        return
    has_applied = (
        user.get("role") == ROLE_CANDIDATE
        and await q.count_applications(user["id"]) > 0
    )
    await call.message.answer(
        t("start.welcome", new_lang),
        reply_markup=kb.main_menu(user["role"], has_applied, new_lang),
    )
    await call.answer()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, bot: Bot,
                    command: CommandObject = None, lang: str = None,
                    lang_chosen: bool = False):
    await state.clear()
    user = await q.get_or_create_user(
        message.from_user.id,
        message.from_user.full_name,
        message.from_user.username,
    )
    await q.add_log(message.from_user.id, message.from_user.full_name, "start", "Botga kirdi")

    # Bloklangan foydalanuvchi
    if user.get("blocked"):
        await message.answer(t("start.blocked", lang))
        return

    # Til hali tanlanmagan (yangi odam) — avval tilni so'raymiz.
    # Til tanlangach `set_lang` menyuni o'zi chiqaradi.
    if not lang_chosen:
        await message.answer(t("lang.ask", lang), reply_markup=kb.lang_pick_kb())
        return

    # Majburiy obuna
    not_joined = await check_subscription(bot, message.from_user.id)
    if not_joined:
        await show_subscription(message)
        return

    # Kanaldagi vakansiya tagidagi «📝 Ishga ariza yuborish» tugmasi botni
    # `/start vac_<id>` deep-link bilan ochadi — anketa darhol boshlanadi.
    payload = (command.args if command else None) or ""
    if payload.strip().startswith("vac_"):
        from handlers.candidate import start_apply_from_deeplink

        if await start_apply_from_deeplink(message, state, payload.strip()):
            return

    # Rolga qarab turli xil xabarni ko'rsatish
    role = user.get("role", ROLE_CANDIDATE)

    # Agar hodim (employee, pharmacist, manager, director, accountant, it, admin, hr)
    # yoki HR tomonidan tasdiqlangan nomzod => asosiy menyu
    if role != ROLE_CANDIDATE:
        await send_main_menu(message, user, lang)
        return

    # Agar nomzod => arizalarining holati tekshiriladi
    applications = await q.user_applications(user["id"])

    if not applications:
        # Birinchi marta — xush kelibsiz xabari
        await message.answer(
            t("start.welcome", lang),
            reply_markup=kb.main_menu(ROLE_CANDIDATE, False, lang),
        )
    else:
        # Arizalar bor — oxirgi arizaning holati tekshiriladi
        latest_app = applications[0]  # eng yangi ariza
        if latest_app.get("status") == "accepted":
            # Tasdiqlangan — hodim paneli ko'rsatiladi
            await send_main_menu(message, user, lang)
        else:
            # Tasdiqlanmagan (new/interview/waiting) — kutish xabari
            await message.answer(
                t("start.pending", lang),
                reply_markup=kb.main_menu(ROLE_CANDIDATE, True, lang),
            )


@router.message(Reg.phone, F.contact)
async def reg_phone_contact(message: Message, state: FSMContext, bot: Bot):
    await q.update_phone(message.from_user.id, message.contact.phone_number)
    await state.clear()
    await message.answer("✅ Rahmat! Ma'lumotlaringiz saqlandi.")
    not_joined = await check_subscription(bot, message.from_user.id)
    if not_joined:
        await show_subscription(message)
        return
    user = await q.get_user(message.from_user.id)
    await send_main_menu(message, user)


@router.message(Reg.phone, F.text)
async def reg_phone_text(message: Message, state: FSMContext, bot: Bot):
    text = message.text.strip()
    # oddiy tekshiruv
    digits = "".join(c for c in text if c.isdigit())
    if len(digits) < 7:
        await message.answer(
            "❗️ Iltimos, «📱 Telefon raqamni yuborish» tugmasidan foydalaning "
            "yoki to'g'ri raqam kiriting.",
            reply_markup=kb.phone_kb(),
        )
        return
    await q.update_phone(message.from_user.id, text)
    await state.clear()
    await message.answer("✅ Rahmat! Ma'lumotlaringiz saqlandi.")
    not_joined = await check_subscription(bot, message.from_user.id)
    if not_joined:
        await show_subscription(message)
        return
    user = await q.get_user(message.from_user.id)
    await send_main_menu(message, user)


@router.callback_query(F.data == "check_sub")
async def check_sub_cb(call: CallbackQuery, bot: Bot):
    not_joined = await check_subscription(bot, call.from_user.id)
    if not_joined:
        await call.answer("❌ Siz hali barcha kanallarga obuna bo'lmadingiz!", show_alert=True)
        return
    await call.message.delete()
    user = await q.get_user(call.from_user.id)
    await call.message.answer("✅ Obuna tasdiqlandi!")
    await send_main_menu(call.message, user)
    await call.answer()


@router.message(tf("btn.main_menu"))
async def to_main(message: Message, state: FSMContext, lang: str = None):
    await state.clear()
    user = await q.get_user(message.from_user.id)
    await send_main_menu(message, user, lang)


@router.message(tf("btn.help"))
@router.message(Command("help"))
async def help_cmd(message: Message):
    await message.answer(
        "ℹ️ <b>Yordam</b>\n\n"
        "📝 <b>Ishga ariza topshirish</b> — yangi nomzod uchun to'liq anketa.\n"
        "🏢 <b>Gulnora Farm hodimi</b> — allaqachon ishlayotgan xodim o'zini ro'yxatdan "
        "o'tkazadi (ism, sana, yo'nalish, filial, ish vaqti, oylik, dam kuni, forma, rasm). "
        "So'rov HR tomonidan tasdiqlanadi.\n"
        "💼 <b>Vakansiyalar</b> — bo'sh ish o'rinlari.\n"
        "📄 <b>Mening arizalarim</b> — arizalaringiz holati.\n\n"
        "<b>Tasdiqlangan xodimlar uchun:</b>\n"
        "📍 <b>Ishga keldim</b> — GPS orqali ofisda ekaningizni tasdiqlash.\n"
        "🏁 <b>Ishdan ketdim</b> — ketish vaqtini belgilash (GPS).\n"
        "🔄 <b>Dam olish kunini almashtirish</b> — filial rahbari/HR tasdiqlaydi.\n"
        "👤 <b>Mening profilim</b> — ma'lumot va davomat tarixi.\n\n"
        "Rolingizga qarab Farmatsevt, Filial rahbari, Direktor, Moliya bo'limi, HR yoki "
        "Admin paneli menyuda ko'rinadi.\n\n"
        "Savollar bo'lsa administrator bilan bog'laning."
    )
