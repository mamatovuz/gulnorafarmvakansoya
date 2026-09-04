"""Xodim profili: «👤 Mening profilim».

Eslatma: kunlik davomat (ishga keldim/ketdim, tanaffus, joylashuv tekshiruvi va
davomat hisobotlari) tizimdan butunlay olib tashlangan. Bu modulda faqat xodimning
o'z profilini ko'rish funksiyasi qoldi."""
from aiogram import Router
from aiogram.types import Message

from database import queries as q
from i18n import tf
from utils import send_employee_profile

router = Router()


# ================= MENING PROFILIM (xodim) =================
@router.message(tf("btn.profile"))
async def my_profile(message: Message):
    profile = await q.get_employee_profile_by_tg(message.from_user.id)
    if not profile:
        await message.answer("Profil topilmadi. HR bilan bog'laning.")
        return
    # Profil rasmi bo'lsa — rasm bilan birga chiqadi
    await send_employee_profile(message, profile)
