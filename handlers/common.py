"""Umumiy handlerlar: /start, majburiy obuna, yordam, asosiy menyu."""
from aiogram import Router, F, Bot
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from database import queries as q
from database.db import ROLE_CANDIDATE
from states import Reg
import keyboards as kb
from utils import check_subscription, get_welcome_text

router = Router()


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


async def send_main_menu(message: Message, user):
    has_applied = False
    if user.get("role") == ROLE_CANDIDATE:
        has_applied = await q.count_applications(user["id"]) > 0
    await message.answer(
        "🏠 Asosiy menyu",
        reply_markup=kb.main_menu(user["role"], has_applied),
    )


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, bot: Bot):
    await state.clear()
    user = await q.get_or_create_user(
        message.from_user.id,
        message.from_user.full_name,
        message.from_user.username,
    )
    await q.add_log(message.from_user.id, message.from_user.full_name, "start", "Botga kirdi")

    # Bloklangan foydalanuvchi
    if user.get("blocked"):
        await message.answer("⛔ Kechirasiz, siz botdan foydalana olmaysiz.")
        return

    # Majburiy obuna
    not_joined = await check_subscription(bot, message.from_user.id)
    if not_joined:
        await show_subscription(message)
        return

    # Telefon boshida so'ralmaydi — u ariza yoki hodim ro'yxatida yig'iladi.
    # /start darhol 2 ta tugmali menyuni ko'rsatadi.
    has_applied = (
        user.get("role") == ROLE_CANDIDATE
        and await q.count_applications(user["id"]) > 0
    )
    await message.answer(
        await get_welcome_text(),
        reply_markup=kb.main_menu(user["role"], has_applied),
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


@router.message(F.text == "🏠 Asosiy menyu")
async def to_main(message: Message, state: FSMContext):
    await state.clear()
    user = await q.get_user(message.from_user.id)
    await send_main_menu(message, user)


@router.message(F.text == "ℹ️ Yordam")
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
        "Rolingizga qarab Farmatsevt, Filial rahbari, Direktor, Buxgalter, HR yoki "
        "Admin paneli menyuda ko'rinadi.\n\n"
        "Savollar bo'lsa administrator bilan bog'laning."
    )
