"""Ishga arizadagi yo'nalishlar (lavozimlar) ro'yxatini boshqarish.

Admin va HR panelida «🏷 Yo'nalishlar» tugmasi orqali qo'shish/o'chirish mumkin.
Bu ro'yxat ishga ariza topshirishda «Qaysi yo'nalish bo'yicha ishga kirmoqchisiz?»
savolida ko'rsatiladi.
"""
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from database import queries as q
from database.db import ROLE_ADMIN, ROLE_HR
from states import PositionForm
import keyboards as kb

router = Router()


async def _can_manage(tg_id):
    u = await q.get_user(tg_id)
    return u and u["role"] in (ROLE_ADMIN, ROLE_HR)


@router.message(F.text == "🏷 Yo'nalishlar")
async def positions_menu(message: Message):
    if not await _can_manage(message.from_user.id):
        await message.answer("⛔ Sizda ruxsat yo'q.")
        return
    positions = await q.list_positions()
    await message.answer(
        "🏷 <b>Ishga ariza yo'nalishlari</b>\n\n"
        "Bu ro'yxat ishga ariza topshirishda lavozim tanlashda ko'rinadi.\n"
        "➕ qo'shish yoki 🗑 o'chirish:",
        reply_markup=kb.positions_manage_kb(positions),
    )


@router.callback_query(F.data == "pos_add")
async def pos_add(call: CallbackQuery, state: FSMContext):
    if not await _can_manage(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    await state.set_state(PositionForm.name)
    await call.message.answer(
        "🏷 Yangi yo'nalish nomini yozing (emoji bilan bo'lsa ham bo'ladi).\n"
        "Misol: <i>💉 Hamshira</i>"
    )
    await call.answer()


@router.message(PositionForm.name, F.text)
async def pos_name(message: Message, state: FSMContext):
    await state.clear()
    name = message.text.strip()
    if not name:
        await message.answer("❗️ Nom bo'sh bo'lmasligi kerak.")
        return
    await q.add_position(name)
    me = await q.get_user(message.from_user.id)
    await q.add_log(message.from_user.id, me["full_name"] if me else "?", "yonalish_qoshildi", name)
    positions = await q.list_positions()
    await message.answer(
        f"✅ «{name}» yo'nalishi qo'shildi.",
        reply_markup=kb.positions_manage_kb(positions),
    )


@router.callback_query(F.data.startswith("pos_del:"))
async def pos_del(call: CallbackQuery):
    if not await _can_manage(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    pid = int(call.data.split(":")[1])
    await q.delete_position(pid)
    me = await q.get_user(call.from_user.id)
    await q.add_log(call.from_user.id, me["full_name"] if me else "?", "yonalish_ochirildi", f"#{pid}")
    positions = await q.list_positions()
    await call.message.edit_reply_markup(reply_markup=kb.positions_manage_kb(positions))
    await call.answer("O'chirildi")
