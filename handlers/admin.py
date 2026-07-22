"""Administrator panel handlerlari."""
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from database import queries as q
from database.db import (
    ROLE_ADMIN, ROLE_HR, ROLE_MANAGER, ROLE_EMPLOYEE, ROLE_PHARMACIST,
    ROLE_DIRECTOR, ROLE_ACCOUNTANT, ROLE_IT, ROLE_CANDIDATE,
)
from states import (
    BranchForm, ChannelForm, RoleForm, UserManageForm, SettingsForm,
)
import keyboards as kb
from utils import vacancy_text, safe_send, PROFILE_UPDATE_NOTICE

router = Router()

ROLE_NAMES = {
    ROLE_ADMIN: "👑 Administrator",
    ROLE_HR: "🧑‍💼 HR",
    ROLE_DIRECTOR: "👔 Direktor",
    ROLE_ACCOUNTANT: "🧮 Moliya bo'limi",
    ROLE_IT: "🖥 IT xodim",
    ROLE_MANAGER: "🏢 Filial rahbari",
    ROLE_PHARMACIST: "💊 Farmatsevt",
    ROLE_EMPLOYEE: "👷 Oddiy xodim",
    ROLE_CANDIDATE: "🧑 Nomzod",
}


async def is_admin(tg_id):
    u = await q.get_user(tg_id)
    return u and u["role"] == ROLE_ADMIN


async def actor(tg_id):
    return await q.get_user(tg_id)


@router.message(F.text == "👑 Admin panel")
async def admin_panel(message: Message):
    if not await is_admin(message.from_user.id):
        await message.answer("⛔ Sizda administrator huquqi yo'q.")
        return
    await message.answer(
        "👑 <b>Administrator paneli</b>\nKerakli bo'limni tanlang:",
        reply_markup=kb.admin_menu(),
    )


# ---------------- MA'LUMOTLARNI YANGILASH KAMPANIYASI ----------------
@router.message(F.text == kb.PROFILE_UPDATE_BTN)
async def profile_update_ask(message: Message):
    """Barcha xodimlardan ma'lumotlarini yangilashni so'rash — avval tasdiqlash."""
    if not await is_admin(message.from_user.id):
        await message.answer("⛔ Sizda administrator huquqi yo'q.")
        return
    done, waiting = await q.profile_update_progress()
    note = f"\n\n⏳ Hozir yangilashi kutilayotganlar: <b>{waiting}</b> ta" if waiting else ""
    await message.answer(
        "🔄 <b>Ma'lumotlarni yangilash</b>\n\n"
        "Siz ma'lumotlarni haqiqatdan yangilamoqchimisiz?\n\n"
        "«Ha» desangiz — <b>barcha Gulnora Farm xodimlariga</b> ma'lumotlarini "
        "yangilash haqida xabar boradi va ular yangilamaguncha botning boshqa "
        "bo'limlaridan foydalana olmaydi.\n"
        "<i>Ishga ariza yuborgan nomzodlarga bu tegishli emas.</i>"
        + note,
        reply_markup=kb.profile_update_confirm_kb(),
    )


@router.callback_query(F.data == "profupd_no")
async def profile_update_no(call: CallbackQuery):
    if not await is_admin(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await call.message.answer("❌ Bekor qilindi. Hech kimga xabar yuborilmadi.")
    await call.answer()


@router.callback_query(F.data == "profupd_yes")
async def profile_update_yes(call: CallbackQuery, bot: Bot):
    if not await is_admin(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    total, tg_ids = await q.request_profile_update_all()
    await call.answer("Yuborilmoqda…")
    sent = 0
    for tid in tg_ids:
        if await safe_send(bot, tid, PROFILE_UPDATE_NOTICE,
                           reply_markup=kb.profile_update_start_kb()):
            sent += 1
    me = await actor(call.from_user.id)
    await q.add_log(
        call.from_user.id, me["full_name"] if me else "?",
        "malumot_yangilash_sorovi", f"{sent}/{total} xodimga yuborildi",
    )
    await call.message.answer(
        "✅ <b>So'rov yuborildi!</b>\n\n"
        f"👥 Xodimlar: <b>{total}</b> ta\n"
        f"📨 Xabar yetkazildi: <b>{sent}</b> ta\n\n"
        "Ular ma'lumotlarini yangilamaguncha botning boshqa bo'limlaridan "
        "foydalana olmaydi. Holatni shu tugma orqali kuzatib borishingiz mumkin."
    )


# ---------------- STATISTIKA ----------------
@router.message(F.text == "📊 Statistika")
async def admin_stats(message: Message):
    if not await is_admin(message.from_user.id):
        return
    s = await q.stats_counts()
    total_users = await q.count_users()
    hrs = await q.count_users(ROLE_HR)
    admins = await q.count_users(ROLE_ADMIN)
    directors = await q.count_users(ROLE_DIRECTOR)
    managers = await q.count_users(ROLE_MANAGER)
    pharmacists = await q.count_users(ROLE_PHARMACIST)
    employees = await q.count_users(ROLE_EMPLOYEE)
    vacs = await q.list_vacancies()
    active_vacs = [v for v in vacs if v["is_active"]]
    branches = await q.stats_by_branch()
    by_vac = await q.stats_by_vacancy()
    top = await q.top_hr()

    text = (
        "📊 <b>Umumiy statistika</b>\n\n"
        f"👥 Jami foydalanuvchilar: <b>{total_users}</b>\n"
        f"👷 Xodimlar: <b>{employees}</b>\n"
        f"💊 Farmatsevtlar: <b>{pharmacists}</b>\n"
        f"🏢 Filial rahbarlari: <b>{managers}</b>\n"
        f"👔 Direktorlar: <b>{directors}</b>\n"
        f"🧑‍💼 HR xodimlari: <b>{hrs}</b>\n"
        f"👑 Administratorlar: <b>{admins}</b>\n\n"
        f"💼 Vakansiyalar: <b>{len(vacs)}</b> (faol: {len(active_vacs)})\n\n"
        "📥 <b>Arizalar:</b>\n"
        f"  • Bugun: {s['today']} | Hafta: {s['week']} | Oy: {s['month']}\n"
        f"  • ✅ Qabul: {s['accepted']} | ❌ Rad: {s['rejected']} | 📅 Suhbat: {s['interview']}\n"
        f"  • 📋 Jami: {s['total']}\n"
    )
    if branches:
        text += "\n🏢 <b>Filiallar bo'yicha:</b>\n"
        for b in branches:
            text += f"  • {b['name'] or 'Nomsiz'}: {b['cnt']}\n"
    if by_vac:
        text += "\n💼 <b>Eng ko'p ariza (lavozimlar):</b>\n"
        for v in by_vac[:10]:
            text += f"  • {v['name'] or 'Nomsiz'}: {v['cnt']}\n"
    if top:
        text += "\n⭐ <b>Eng faol HR xodimlari:</b>\n"
        for t in top:
            text += f"  • {t['name'] or 'Nomsiz'}: {t['cnt']} ta\n"
    await message.answer(text)


# ---------------- FILIALLAR ----------------
@router.message(F.text == "🏢 Filiallar")
async def admin_branches(message: Message):
    if not await is_admin(message.from_user.id):
        return
    branches = await q.list_branches()
    await message.answer(
        "🏢 <b>Filiallar</b>", reply_markup=kb.branches_manage_kb(branches)
    )


@router.callback_query(F.data == "br_add")
async def br_add(call: CallbackQuery, state: FSMContext):
    await state.set_state(BranchForm.name)
    await call.message.answer("🏢 Filial nomini kiriting:")
    await call.answer()


@router.message(BranchForm.name, F.text)
async def br_name(message: Message, state: FSMContext):
    await state.update_data(br_name=message.text.strip())
    await state.set_state(BranchForm.address)
    await message.answer("📍 Manzilini kiriting (yoki «-»):")


@router.message(BranchForm.address, F.text)
async def br_addr(message: Message, state: FSMContext):
    await state.update_data(br_address=message.text.strip())
    await state.set_state(BranchForm.location)
    await message.answer(
        "📍 <b>Filial joylashuvi (GPS)</b>\n\n"
        "Davomat (Ishga keldim) shu koordinata bo'yicha tekshiriladi.\n"
        "Filial binosida turib «📍 Filial joylashuvini yuborish» tugmasini bosing "
        "yoki kesh koordinatani <code>lat,lon</code> ko'rinishida yozing "
        "(masalan <code>41.311081,69.240562</code>).\n"
        "Hozircha bo'lmasa «⏭️ O'tkazib yuborish».",
        reply_markup=kb.branch_location_request_kb(),
    )


async def _finish_branch(message, state, lat, lon):
    data = await state.get_data()
    await q.add_branch(data["br_name"], data.get("br_address", "-"), lat, lon)
    await state.clear()
    me = await actor(message.from_user.id)
    await q.add_log(message.from_user.id, me["full_name"], "filial_qoshildi", data["br_name"])
    branches = await q.list_branches()
    geo = "📍 koordinatasi bilan" if lat is not None else "(koordinata keyin qo'shiladi)"
    await message.answer(
        f"✅ Filial qo'shildi {geo}.", reply_markup=kb.branches_manage_kb(branches)
    )


@router.message(BranchForm.location, F.location)
async def br_addr_location(message: Message, state: FSMContext):
    await _finish_branch(message, state, message.location.latitude, message.location.longitude)


@router.message(BranchForm.location, F.text)
async def br_addr_location_text(message: Message, state: FSMContext):
    text = message.text.strip()
    if text == "⏭️ O'tkazib yuborish":
        await _finish_branch(message, state, None, None)
        return
    coords = _parse_coords(text)
    if not coords:
        await message.answer(
            "❗️ Koordinata noto'g'ri. <code>lat,lon</code> ko'rinishida yozing yoki "
            "tugma orqali joylashuv yuboring.",
            reply_markup=kb.branch_location_request_kb(),
        )
        return
    await _finish_branch(message, state, coords[0], coords[1])


def _parse_coords(text):
    parts = text.replace(" ", "").split(",")
    if len(parts) != 2:
        return None
    try:
        lat, lon = float(parts[0]), float(parts[1])
    except ValueError:
        return None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    return lat, lon


@router.callback_query(F.data.startswith("br_edit:"))
async def br_edit(call: CallbackQuery, state: FSMContext):
    bid = int(call.data.split(":")[1])
    await state.update_data(edit_bid=bid)
    await state.set_state(BranchForm.edit_name)
    br = await q.get_branch(bid)
    await call.message.answer(f"✏️ Yangi nom (hozirgi: {br['name']}):")
    await call.answer()


@router.message(BranchForm.edit_name, F.text)
async def br_edit_name(message: Message, state: FSMContext):
    await state.update_data(new_name=message.text.strip())
    await state.set_state(BranchForm.edit_address)
    await message.answer("📍 Yangi manzil (yoki «-»):")


@router.message(BranchForm.edit_address, F.text)
async def br_edit_addr(message: Message, state: FSMContext):
    data = await state.get_data()
    await q.update_branch(data["edit_bid"], data["new_name"], message.text.strip())
    await state.clear()
    branches = await q.list_branches()
    await message.answer("✅ Filial yangilandi.", reply_markup=kb.branches_manage_kb(branches))


@router.callback_query(F.data == "br_locmenu")
async def br_locmenu(call: CallbackQuery):
    if not await is_admin(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    branches = await q.list_branches()
    if not branches:
        await call.answer("Avval filial qo'shing.", show_alert=True)
        return
    await call.message.answer(
        "📍 <b>Koordinatalarni sozlash</b>\n"
        "✅ — koordinatasi bor, ➖ — yo'q. Filialni tanlang:",
        reply_markup=kb.branch_setloc_kb(branches),
    )
    await call.answer()


@router.callback_query(F.data.startswith("br_loc:"))
async def br_loc_start(call: CallbackQuery, state: FSMContext):
    if not await is_admin(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    bid = int(call.data.split(":")[1])
    await state.update_data(loc_bid=bid)
    await state.set_state(BranchForm.set_location)
    br = await q.get_branch(bid)
    await call.message.answer(
        f"📍 «{br['name']}» uchun joylashuvni yuboring "
        "(tugma orqali yoki <code>lat,lon</code> matn bilan):",
        reply_markup=kb.branch_location_request_kb(),
    )
    await call.answer()


async def _save_branch_loc(message, state, lat, lon):
    data = await state.get_data()
    bid = data.get("loc_bid")
    await state.clear()
    await q.set_branch_location(bid, lat, lon)
    me = await actor(message.from_user.id)
    await q.add_log(message.from_user.id, me["full_name"], "filial_koordinata", f"#{bid}")
    branches = await q.list_branches()
    await message.answer(
        "✅ Filial koordinatasi saqlandi.", reply_markup=kb.branches_manage_kb(branches)
    )


@router.message(BranchForm.set_location, F.location)
async def br_loc_location(message: Message, state: FSMContext):
    await _save_branch_loc(message, state, message.location.latitude, message.location.longitude)


@router.message(BranchForm.set_location, F.text)
async def br_loc_text(message: Message, state: FSMContext):
    text = message.text.strip()
    if text == "⏭️ O'tkazib yuborish":
        await state.clear()
        await message.answer("O'tkazib yuborildi.")
        return
    coords = _parse_coords(text)
    if not coords:
        await message.answer(
            "❗️ Koordinata noto'g'ri. <code>lat,lon</code> yoki tugma orqali yuboring.",
            reply_markup=kb.branch_location_request_kb(),
        )
        return
    await _save_branch_loc(message, state, coords[0], coords[1])


@router.callback_query(F.data.startswith("br_del:"))
async def br_del(call: CallbackQuery):
    bid = int(call.data.split(":")[1])
    await q.delete_branch(bid)
    me = await actor(call.from_user.id)
    await q.add_log(call.from_user.id, me["full_name"], "filial_ochirildi", f"#{bid}")
    branches = await q.list_branches()
    await call.message.edit_text("🏢 <b>Filiallar</b>", reply_markup=kb.branches_manage_kb(branches))
    await call.answer("O'chirildi")


# ---------------- KANALLAR (majburiy obuna) ----------------
@router.message(F.text == "📢 Kanallar")
async def admin_channels(message: Message):
    if not await is_admin(message.from_user.id):
        return
    channels = await q.list_channels()
    await message.answer(
        "📢 <b>Majburiy obuna kanallari</b>\n\n"
        "Muhim: bot kanalda <b>administrator</b> bo'lishi kerak, "
        "aks holda obunani tekshira olmaydi.\n"
        "🟢 - faol, 🔴 - nofaol. «almashtirish» — holatini o'zgartiradi.",
        reply_markup=kb.channels_manage_kb(channels),
    )


@router.callback_query(F.data == "ch_add")
async def ch_add(call: CallbackQuery, state: FSMContext):
    await state.set_state(ChannelForm.chat_id)
    await call.message.answer(
        "📢 Kanal ID sini kiriting.\n"
        "Ommaviy kanal uchun: <code>@kanal_username</code>\n"
        "Yopiq kanal uchun: <code>-1001234567890</code> ko'rinishida."
    )
    await call.answer()


@router.message(ChannelForm.chat_id, F.text)
async def ch_chatid(message: Message, state: FSMContext):
    await state.update_data(chat_id=message.text.strip())
    await state.set_state(ChannelForm.title)
    await message.answer("📝 Kanal nomini kiriting (tugmada ko'rinadi):")


@router.message(ChannelForm.title, F.text)
async def ch_title(message: Message, state: FSMContext):
    await state.update_data(title=message.text.strip())
    await state.set_state(ChannelForm.url)
    await message.answer(
        "🔗 Kanal havolasini kiriting (masalan https://t.me/kanal) yoki «-»:"
    )


@router.message(ChannelForm.url, F.text)
async def ch_url(message: Message, state: FSMContext):
    data = await state.get_data()
    url = message.text.strip()
    if url == "-":
        cid = data["chat_id"]
        url = f"https://t.me/{cid.lstrip('@')}" if cid.startswith("@") else ""
    await q.add_channel(data["chat_id"], data["title"], url)
    await state.clear()
    me = await actor(message.from_user.id)
    await q.add_log(message.from_user.id, me["full_name"], "kanal_qoshildi", data["title"])
    channels = await q.list_channels()
    await message.answer("✅ Kanal qo'shildi.", reply_markup=kb.channels_manage_kb(channels))


@router.callback_query(F.data.startswith("ch_tog:"))
async def ch_toggle(call: CallbackQuery):
    cid = int(call.data.split(":")[1])
    await q.toggle_channel(cid)
    channels = await q.list_channels()
    await call.message.edit_reply_markup(reply_markup=kb.channels_manage_kb(channels))
    await call.answer("Holat o'zgartirildi")


@router.callback_query(F.data.startswith("ch_del:"))
async def ch_delete(call: CallbackQuery):
    cid = int(call.data.split(":")[1])
    await q.delete_channel(cid)
    me = await actor(call.from_user.id)
    await q.add_log(call.from_user.id, me["full_name"], "kanal_ochirildi", f"#{cid}")
    channels = await q.list_channels()
    await call.message.edit_reply_markup(reply_markup=kb.channels_manage_kb(channels))
    await call.answer("O'chirildi")


# ---------------- ADMINLAR ----------------
@router.message(F.text == "👥 Adminlar")
async def admin_admins(message: Message):
    if not await is_admin(message.from_user.id):
        return
    admins = await q.list_users_by_role(ROLE_ADMIN)
    await message.answer(
        "👥 <b>Administratorlar</b>\nQo'shish uchun tugmani bosing, "
        "o'chirish uchun ismni bosing.",
        reply_markup=kb.admins_manage_kb(admins),
    )


@router.callback_query(F.data == "adm_add")
async def adm_add(call: CallbackQuery, state: FSMContext):
    await state.update_data(grant_role=ROLE_ADMIN)
    await state.set_state(RoleForm.tg_id)
    await call.message.answer(
        "👤 Yangi administratorning Telegram ID sini kiriting.\n"
        "(Foydalanuvchi avval botga /start bosgan bo'lishi kerak. "
        "ID ni @userinfobot dan bilib olish mumkin.)"
    )
    await call.answer()


@router.callback_query(F.data.startswith("adm_del:"))
async def adm_del(call: CallbackQuery):
    tg_id = int(call.data.split(":")[1])
    from config import SUPER_ADMINS
    if tg_id in SUPER_ADMINS:
        await call.answer("Bosh adminni o'chirib bo'lmaydi.", show_alert=True)
        return
    await q.set_role(tg_id, ROLE_CANDIDATE)
    me = await actor(call.from_user.id)
    await q.add_log(call.from_user.id, me["full_name"], "admin_ochirildi", str(tg_id))
    admins = await q.list_users_by_role(ROLE_ADMIN)
    await call.message.edit_reply_markup(reply_markup=kb.admins_manage_kb(admins))
    await call.answer("Admin huquqi olib tashlandi")


# ---------------- HR XODIMLARI ----------------
@router.message(F.text == "🧑‍💼 HR xodimlari")
async def admin_hrs(message: Message):
    if not await is_admin(message.from_user.id):
        return
    hrs = await q.list_users_by_role(ROLE_HR)
    await message.answer(
        "🧑‍💼 <b>HR xodimlari</b>", reply_markup=kb.hrs_manage_kb(hrs)
    )


@router.callback_query(F.data == "hr_add")
async def hr_add(call: CallbackQuery, state: FSMContext):
    await state.update_data(grant_role=ROLE_HR)
    await state.set_state(RoleForm.tg_id)
    await call.message.answer(
        "👤 Yangi HR xodimining Telegram ID sini kiriting.\n"
        "(Foydalanuvchi avval botga /start bosgan bo'lishi kerak.)"
    )
    await call.answer()


@router.callback_query(F.data.startswith("hr_del:"))
async def hr_del(call: CallbackQuery):
    tg_id = int(call.data.split(":")[1])
    await q.set_role(tg_id, ROLE_CANDIDATE)
    me = await actor(call.from_user.id)
    await q.add_log(call.from_user.id, me["full_name"], "hr_ochirildi", str(tg_id))
    hrs = await q.list_users_by_role(ROLE_HR)
    await call.message.edit_reply_markup(reply_markup=kb.hrs_manage_kb(hrs))
    await call.answer("HR huquqi olib tashlandi")


# ---------------- ROLLAR ----------------
@router.message(F.text == "🎭 Rollar")
async def admin_roles(message: Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        return
    await state.set_state(RoleForm.tg_id)
    await state.update_data(grant_role=None)
    await message.answer(
        "🎭 <b>Rol berish</b>\n\n"
        "Foydalanuvchining Telegram ID sini kiriting:"
    )


@router.message(RoleForm.tg_id, F.text)
async def role_tg_id(message: Message, state: FSMContext, bot: Bot):
    text = message.text.strip()
    if not text.lstrip("-").isdigit():
        await message.answer("❗️ Faqat raqamli ID kiriting. Qayta urinib ko'ring:")
        return
    tg_id = int(text)
    target = await q.get_user(tg_id)
    if not target:
        await message.answer(
            "❗️ Bunday foydalanuvchi topilmadi. "
            "U avval botga /start bosgan bo'lishi kerak. Qayta ID kiriting yoki /start:"
        )
        return
    await state.update_data(target_tg=tg_id)
    data = await state.get_data()
    grant_role = data.get("grant_role")

    if grant_role:
        # to'g'ridan-to'g'ri admin/hr qo'shish
        await _apply_role(message, state, bot, tg_id, grant_role)
        return

    await message.answer(
        f"Foydalanuvchi: <b>{target['full_name'] or tg_id}</b>\n"
        f"Hozirgi roli: {ROLE_NAMES.get(target['role'], target['role'])}\n\n"
        "Yangi rolni tanlang:",
        reply_markup=kb.roles_pick_kb(),
    )


@router.callback_query(F.data.startswith("setrole:"))
async def role_set(call: CallbackQuery, state: FSMContext, bot: Bot):
    role = call.data.split(":")[1]
    data = await state.get_data()
    tg_id = data.get("target_tg")
    if not tg_id:
        await call.answer("Sessiya tugagan. Qayta boshlang.", show_alert=True)
        await state.clear()
        return
    await _apply_role(call.message, state, bot, tg_id, role, call=call)


EMPLOYEE_ROLES = (
    ROLE_MANAGER, ROLE_PHARMACIST, ROLE_DIRECTOR, ROLE_EMPLOYEE, ROLE_ACCOUNTANT,
)


async def _apply_role(message, state, bot, tg_id, role, call=None):
    target = await q.get_user(tg_id)
    branch_id = target.get("branch_id") if target else None
    prev_role = target.get("role") if target else None
    await q.set_role(tg_id, role, branch_id)
    if role in EMPLOYEE_ROLES:
        await q.upsert_employee_profile(
            user_id=target["id"],
            application_id=None,
            role=role,
            position=ROLE_NAMES.get(role, role),
            branch_id=branch_id,
            uniform_status="unknown",
        )
        # Nomzoddan xodimga o'tkazilsa — bu "ishga kirdi" voqeasi (IT hisoboti uchun)
        if prev_role == ROLE_CANDIDATE and target:
            await q.add_hr_event(
                "hired", user_id=target["id"], full_name=target.get("full_name"),
                branch_id=branch_id, details="admin rol berdi",
            )
    await state.clear()
    me = await q.get_user(message.chat.id if call is None else call.from_user.id)
    actor_name = me["full_name"] if me else "?"
    actor_tg = me["tg_id"] if me else 0
    await q.add_log(actor_tg, actor_name, "rol_berildi", f"{tg_id} -> {role}")
    await message.answer(
        f"✅ <b>{target['full_name'] or tg_id}</b> ga "
        f"«{ROLE_NAMES.get(role, role)}» roli berildi."
    )
    await safe_send(
        bot, tg_id,
        f"ℹ️ Sizga yangi rol berildi: <b>{ROLE_NAMES.get(role, role)}</b>.\n"
        f"O'zgarishlar kuchga kirishi uchun /start bosing.",
    )
    if call:
        await call.answer("Rol berildi ✅")


# ---------------- VAKANSIYALAR (Admin) ----------------
@router.message(F.text == "💼 Vakansiyalar (Admin)")
async def admin_vacancies(message: Message):
    if not await is_admin(message.from_user.id):
        return
    vacs = await q.list_vacancies()
    if not vacs:
        await message.answer("Hali vakansiyalar yo'q.")
        return
    await message.answer(
        f"💼 <b>Vakansiyalar</b>\n\nJami: <b>{len(vacs)}</b> ta\n"
        "Boshqarish uchun vakansiyani tanlang:",
        reply_markup=kb.vacancies_manage_list_kb(vacs),
    )


# ---------------- FOYDALANUVCHILAR BOSHQARUVI ----------------
@router.message(F.text == "👤 Foydalanuvchilar")
async def admin_users(message: Message):
    if not await is_admin(message.from_user.id):
        return
    users = await q.list_users(limit=30)
    total = await q.count_users()
    blocked = await q.count_blocked()
    await message.answer(
        f"👤 <b>Foydalanuvchilar</b>\n\n"
        f"Jami: <b>{total}</b> | Bloklangan: <b>{blocked}</b>\n"
        f"Oxirgi {len(users)} ta ko'rsatilmoqda. Boshqarish uchun tanlang:",
        reply_markup=kb.users_list_kb(users),
    )
    await message.answer(
        "🔎 Muayyan foydalanuvchini topish uchun tugmani bosing:",
        reply_markup=_user_search_kb(),
    )


def _user_search_kb():
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    b = InlineKeyboardBuilder()
    b.button(text="🔎 Ism / telefon / ID bo'yicha qidirish", callback_data="usrsearch")
    return b.as_markup()


@router.callback_query(F.data == "usrsearch")
async def user_search_start(call: CallbackQuery, state: FSMContext):
    if not await is_admin(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    await state.set_state(UserManageForm.search)
    await call.message.answer("🔎 Qidiruv so'zini kiriting (ism, username, telefon yoki TG ID):")
    await call.answer()


@router.message(UserManageForm.search, F.text)
async def user_search_run(message: Message, state: FSMContext):
    await state.clear()
    query = message.text.strip()
    users = await q.list_users(search=query, limit=30)
    if not users:
        await message.answer(f"«{query}» bo'yicha foydalanuvchi topilmadi.")
        return
    await message.answer(
        f"🔎 <b>Natija:</b> «{query}» — {len(users)} ta\nTanlang:",
        reply_markup=kb.users_list_kb(users),
    )


@router.callback_query(F.data.startswith("usrview:"))
async def user_view(call: CallbackQuery):
    if not await is_admin(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    tg_id = int(call.data.split(":")[1])
    u = await q.get_user(tg_id)
    if not u:
        await call.answer("Topilmadi.", show_alert=True)
        return
    branch = await q.get_branch(u["branch_id"]) if u.get("branch_id") else None
    text = (
        f"👤 <b>{u.get('full_name') or u.get('tg_id')}</b>\n"
        "━━━━━━━━━━━━\n"
        f"🆔 TG ID: <code>{u['tg_id']}</code>\n"
        f"🔗 Username: {('@' + u['username']) if u.get('username') else '-'}\n"
        f"📱 Telefon: {u.get('phone') or '-'}\n"
        f"🎭 Rol: {ROLE_NAMES.get(u.get('role'), u.get('role'))}\n"
        f"🏢 Filial: {branch['name'] if branch else '-'}\n"
        f"🚦 Holat: {'🚫 Bloklangan' if u.get('blocked') else '✅ Faol'}\n"
        f"🗓 Ro'yxatdan o'tgan: {u.get('created_at') or '-'}"
    )
    await call.message.answer(text, reply_markup=kb.user_manage_kb(tg_id, bool(u.get("blocked"))))
    await call.answer()


@router.callback_query(F.data.startswith("usrblock:"))
async def user_block(call: CallbackQuery, bot: Bot):
    if not await is_admin(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    tg_id = int(call.data.split(":")[1])
    from config import SUPER_ADMINS
    if tg_id in SUPER_ADMINS:
        await call.answer("Bosh adminni bloklab bo'lmaydi.", show_alert=True)
        return
    await q.set_user_blocked(tg_id, True)
    me = await actor(call.from_user.id)
    await q.add_log(call.from_user.id, me["full_name"], "user_bloklandi", str(tg_id))
    u = await q.get_user(tg_id)
    await call.message.edit_reply_markup(reply_markup=kb.user_manage_kb(tg_id, True))
    await call.answer("🚫 Bloklandi")
    await safe_send(bot, tg_id, "⛔ Siz administrator tomonidan botdan bloklandingiz.")


@router.callback_query(F.data.startswith("usrunblock:"))
async def user_unblock(call: CallbackQuery, bot: Bot):
    if not await is_admin(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    tg_id = int(call.data.split(":")[1])
    await q.set_user_blocked(tg_id, False)
    me = await actor(call.from_user.id)
    await q.add_log(call.from_user.id, me["full_name"], "user_blokdan_chiqdi", str(tg_id))
    await call.message.edit_reply_markup(reply_markup=kb.user_manage_kb(tg_id, False))
    await call.answer("✅ Blokdan chiqarildi")
    await safe_send(bot, tg_id, "✅ Sizga bot yana ochildi. /start bosing.")


@router.callback_query(F.data.startswith("usrrole:"))
async def user_role_start(call: CallbackQuery, state: FSMContext):
    if not await is_admin(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    tg_id = int(call.data.split(":")[1])
    target = await q.get_user(tg_id)
    if not target:
        await call.answer("Foydalanuvchi topilmadi.", show_alert=True)
        return
    await state.update_data(target_tg=tg_id, grant_role=None)
    await call.message.answer(
        f"🎭 <b>{target.get('full_name') or tg_id}</b> uchun yangi rolni tanlang:",
        reply_markup=kb.roles_pick_kb(),
    )
    await call.answer()


# ---------------- SOZLAMALAR ----------------
@router.message(F.text == "⚙️ Sozlamalar")
async def admin_settings(message: Message):
    if not await is_admin(message.from_user.id):
        return
    require_sub = (await q.get_setting("require_subscription", "1")) != "0"
    secret_channel = await q.get_setting("secret_channel")
    vacancy_channel = await q.get_setting("vacancy_channel")
    candidate_channel = await q.get_setting("candidate_channel")
    threshold = await q.get_setting("match_threshold", "60")
    chan_line = (
        f"🔒 <b>Maxfiy kanal</b> — hozir: <code>{secret_channel}</code>"
        if secret_channel
        else "🔒 <b>Maxfiy kanal</b> — hali ulanmagan"
    )
    vac_line = (
        f"📣 <b>Vakansiya kanali</b> — hozir: <code>{vacancy_channel}</code>"
        if vacancy_channel
        else "📣 <b>Vakansiya kanali</b> — hali ulanmagan"
    )
    cand_line = (
        f"📇 <b>Nomzodlar kanali</b> — hozir: <code>{candidate_channel}</code>"
        if candidate_channel
        else "📇 <b>Nomzodlar kanali</b> — hali ulanmagan"
    )
    await message.answer(
        "⚙️ <b>Bot sozlamalari</b>\n\n"
        "📢 <b>Majburiy obuna</b> — yoqilsa, foydalanuvchi kanallarga obuna bo'lmaguncha "
        "botdan foydalana olmaydi.\n"
        "✍️ <b>Xush kelibsiz matni</b> — /start bosganda chiqadigan matn.\n"
        f"{chan_line} — HR ishga qabul qilgan arizalar shu kanalga tushadi.\n"
        f"{vac_line} — HR tasdiqlagan vakansiyalar shu kanalga joylanadi (ochiq yoki maxfiy).\n"
        f"{cand_line} — nomzod ariza tasdiqlashi bilan shu maxfiy kanalga tushadi, "
        "holati (kutuvda/tasdiqlangan/rad etilgan) avtomatik yangilanadi.\n"
        f"🎯 <b>Moslik chegarasi</b> — {threshold}%. Oddiy ariza shu foizdan yuqori mos "
        "kelsa, HR ga avtomatik tavsiya beriladi.",
        reply_markup=kb.admin_settings_kb(require_sub, secret_channel, threshold,
                                          vacancy_channel, candidate_channel),
    )


@router.callback_query(F.data.startswith("setsub:"))
async def toggle_subscription(call: CallbackQuery):
    if not await is_admin(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    action = call.data.split(":")[1]
    await q.set_setting("require_subscription", "1" if action == "on" else "0")
    me = await actor(call.from_user.id)
    await q.add_log(call.from_user.id, me["full_name"], "sozlama_obuna", action)
    require_sub = action == "on"
    secret_channel = await q.get_setting("secret_channel")
    vacancy_channel = await q.get_setting("vacancy_channel")
    candidate_channel = await q.get_setting("candidate_channel")
    threshold = await q.get_setting("match_threshold", "60")
    await call.message.edit_reply_markup(
        reply_markup=kb.admin_settings_kb(require_sub, secret_channel, threshold,
                                          vacancy_channel, candidate_channel)
    )
    await call.answer("✅ Yangilandi")


@router.callback_query(F.data == "setwelcome")
async def welcome_edit_start(call: CallbackQuery, state: FSMContext):
    if not await is_admin(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    await state.set_state(SettingsForm.welcome)
    await call.message.answer(
        "✍️ Yangi xush kelibsiz matnini yuboring.\n"
        "(HTML teglaridan foydalanishingiz mumkin: &lt;b&gt;qalin&lt;/b&gt;)"
    )
    await call.answer()


@router.message(SettingsForm.welcome, F.text)
async def welcome_edit_save(message: Message, state: FSMContext):
    await state.clear()
    await q.set_setting("welcome_text", message.text)
    me = await actor(message.from_user.id)
    await q.add_log(message.from_user.id, me["full_name"], "sozlama_welcome", "yangilandi")
    await message.answer("✅ Xush kelibsiz matni yangilandi.\n\nNamuna:\n\n" + message.text)


@router.callback_query(F.data == "setwelcome_reset")
async def welcome_reset(call: CallbackQuery):
    if not await is_admin(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    await q.set_setting("welcome_text", "")
    await call.answer("♻️ Standart matn tiklandi", show_alert=True)


# ---------------- MAXFIY KANAL ----------------
@router.callback_query(F.data == "setsecret")
async def secret_channel_start(call: CallbackQuery, state: FSMContext):
    if not await is_admin(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    await state.set_state(SettingsForm.secret_channel)
    await call.message.answer(
        "🔒 <b>Maxfiy kanalni ulash</b>\n\n"
        "Shu kanalga tushadi:\n"
        "• HR ishga qabul qilgan arizalar\n"
        "• HR tasdiqlagan <b>Gulnora Farm hodimi</b> ma'lumotlari (rasmi bilan)\n\n"
        "1️⃣ Botni o'sha kanalga <b>administrator</b> qilib qo'shing.\n"
        "2️⃣ Kanal ID sini yuboring:\n"
        "   • Yopiq kanal: <code>-1001234567890</code> ko'rinishida\n"
        "   • Ochiq kanal: <code>@kanal_username</code> ko'rinishida\n\n"
        "Bekor qilish uchun <b>-</b> yuboring."
    )
    await call.answer()


@router.message(SettingsForm.secret_channel, F.text)
async def secret_channel_save(message: Message, state: FSMContext, bot: Bot):
    await state.clear()
    value = message.text.strip()
    if value == "-":
        await message.answer("Bekor qilindi.")
        return
    # Kanalni tekshiramiz — bot a'zomi va nomini olamiz
    title = None
    try:
        chat = await bot.get_chat(value)
        title = chat.title or chat.full_name
    except Exception:
        await message.answer(
            "❗️ Kanalni tekshira olmadim. Bot o'sha kanalda administrator ekaniga "
            "va ID/username to'g'ri ekaniga ishonch hosil qiling, so'ng qaytadan urinib ko'ring.\n"
            "Baribir saqlab qo'yishni xohlasangiz, ID ni qayta yuboring."
        )
        # Baribir saqlaymiz — ba'zan get_chat ishlamasligi mumkin
    await q.set_setting("secret_channel", value)
    me = await actor(message.from_user.id)
    await q.add_log(message.from_user.id, me["full_name"], "sozlama_maxfiy_kanal", value)
    suffix = f"\n📛 Nomi: <b>{title}</b>" if title else ""
    await message.answer(
        f"✅ Maxfiy kanal ulandi: <code>{value}</code>{suffix}\n\n"
        "Endi HR qabul qilgan har bir ariza va tasdiqlangan xodim ma'lumotlari "
        "shu kanalga yuboriladi."
    )


@router.callback_query(F.data == "setsecret_clear")
async def secret_channel_clear(call: CallbackQuery):
    if not await is_admin(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    await q.set_setting("secret_channel", "")
    me = await actor(call.from_user.id)
    await q.add_log(call.from_user.id, me["full_name"], "sozlama_maxfiy_kanal", "uzildi")
    require_sub = (await q.get_setting("require_subscription", "1")) != "0"
    threshold = await q.get_setting("match_threshold", "60")
    vacancy_channel = await q.get_setting("vacancy_channel")
    candidate_channel = await q.get_setting("candidate_channel")
    await call.message.edit_reply_markup(
        reply_markup=kb.admin_settings_kb(require_sub, None, threshold, vacancy_channel,
                                          candidate_channel)
    )
    await call.answer("🗑 Maxfiy kanal uzildi", show_alert=True)


# ---------------- VAKANSIYA KANALI ----------------
@router.callback_query(F.data == "setvac")
async def vacancy_channel_start(call: CallbackQuery, state: FSMContext):
    if not await is_admin(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    await state.set_state(SettingsForm.vacancy_channel)
    await call.message.answer(
        "📣 <b>Vakansiya kanalini ulash</b>\n\n"
        "HR tasdiqlagan vakansiyalar shu kanalga joylanadi. Kanal <b>ochiq</b> "
        "yoki <b>maxfiy</b> bo'lishi mumkin.\n\n"
        "1️⃣ Botni o'sha kanalga <b>administrator</b> qilib qo'shing.\n"
        "2️⃣ Kanal ID sini yuboring:\n"
        "   • Yopiq kanal: <code>-1001234567890</code> ko'rinishida\n"
        "   • Ochiq kanal: <code>@kanal_username</code> ko'rinishida\n\n"
        "Bekor qilish uchun <b>-</b> yuboring."
    )
    await call.answer()


@router.message(SettingsForm.vacancy_channel, F.text)
async def vacancy_channel_save(message: Message, state: FSMContext, bot: Bot):
    await state.clear()
    value = message.text.strip()
    if value == "-":
        await message.answer("Bekor qilindi.")
        return
    title = None
    try:
        chat = await bot.get_chat(value)
        title = chat.title or chat.full_name
    except Exception:
        await message.answer(
            "❗️ Kanalni tekshira olmadim. Bot o'sha kanalda administrator ekaniga "
            "va ID/username to'g'ri ekaniga ishonch hosil qiling. Baribir saqlayapman."
        )
    await q.set_setting("vacancy_channel", value)
    me = await actor(message.from_user.id)
    await q.add_log(message.from_user.id, me["full_name"], "sozlama_vakansiya_kanal", value)
    suffix = f"\n📛 Nomi: <b>{title}</b>" if title else ""
    await message.answer(
        f"✅ Vakansiya kanali ulandi: <code>{value}</code>{suffix}\n\n"
        "Endi HR tasdiqlagan har bir vakansiya shu kanalga joylanadi — e'lon "
        "tagida «📝 Ishga ariza yuborish» tugmasi bo'ladi, uni bosgan odam "
        "to'g'ridan-to'g'ri botdagi anketaga tushadi."
    )


@router.callback_query(F.data == "setvac_clear")
async def vacancy_channel_clear(call: CallbackQuery):
    if not await is_admin(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    await q.set_setting("vacancy_channel", "")
    me = await actor(call.from_user.id)
    await q.add_log(call.from_user.id, me["full_name"], "sozlama_vakansiya_kanal", "uzildi")
    require_sub = (await q.get_setting("require_subscription", "1")) != "0"
    secret_channel = await q.get_setting("secret_channel")
    threshold = await q.get_setting("match_threshold", "60")
    candidate_channel = await q.get_setting("candidate_channel")
    await call.message.edit_reply_markup(
        reply_markup=kb.admin_settings_kb(require_sub, secret_channel, threshold, None,
                                          candidate_channel)
    )
    await call.answer("🗑 Vakansiya kanali uzildi", show_alert=True)


# ---------------- NOMZODLAR (KUTUVCHILAR) KANALI ----------------
@router.callback_query(F.data == "setcand")
async def candidate_channel_start(call: CallbackQuery, state: FSMContext):
    if not await is_admin(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    await state.set_state(SettingsForm.candidate_channel)
    await call.message.answer(
        "📇 <b>Nomzodlar kanalini ulash</b>\n\n"
        "Nomzod ariza tasdiqlashi bilan uning ma'lumotlari shu <b>maxfiy</b> kanalga "
        "tushadi. Holati (⏳ kutuvda / ✅ tasdiqlangan / ❌ rad etilgan) avtomatik "
        "yangilanadi.\n\n"
        "1️⃣ Botni o'sha kanalga <b>administrator</b> qilib qo'shing.\n"
        "2️⃣ Kanal ID sini yuboring:\n"
        "   • Yopiq kanal: <code>-1001234567890</code> ko'rinishida\n"
        "   • Ochiq kanal: <code>@kanal_username</code> ko'rinishida\n\n"
        "Bekor qilish uchun <b>-</b> yuboring."
    )
    await call.answer()


@router.message(SettingsForm.candidate_channel, F.text)
async def candidate_channel_save(message: Message, state: FSMContext, bot: Bot):
    await state.clear()
    value = message.text.strip()
    if value == "-":
        await message.answer("Bekor qilindi.")
        return
    title = None
    try:
        chat = await bot.get_chat(value)
        title = chat.title or chat.full_name
    except Exception:
        await message.answer(
            "❗️ Kanalni tekshira olmadim. Bot o'sha kanalda administrator ekaniga "
            "va ID/username to'g'ri ekaniga ishonch hosil qiling. Baribir saqlayapman."
        )
    await q.set_setting("candidate_channel", value)
    me = await actor(message.from_user.id)
    await q.add_log(message.from_user.id, me["full_name"], "sozlama_nomzod_kanal", value)
    suffix = f"\n📛 Nomi: <b>{title}</b>" if title else ""
    await message.answer(
        f"✅ Nomzodlar kanali ulandi: <code>{value}</code>{suffix}\n\n"
        "Endi nomzod tasdiqlagan har bir ariza shu kanalga joylanadi."
    )


@router.callback_query(F.data == "setcand_clear")
async def candidate_channel_clear(call: CallbackQuery):
    if not await is_admin(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    await q.set_setting("candidate_channel", "")
    me = await actor(call.from_user.id)
    await q.add_log(call.from_user.id, me["full_name"], "sozlama_nomzod_kanal", "uzildi")
    require_sub = (await q.get_setting("require_subscription", "1")) != "0"
    secret_channel = await q.get_setting("secret_channel")
    threshold = await q.get_setting("match_threshold", "60")
    vacancy_channel = await q.get_setting("vacancy_channel")
    await call.message.edit_reply_markup(
        reply_markup=kb.admin_settings_kb(require_sub, secret_channel, threshold,
                                          vacancy_channel, None)
    )
    await call.answer("🗑 Nomzodlar kanali uzildi", show_alert=True)


# ---------------- MOSLIK CHEGARASI ----------------
@router.callback_query(F.data == "setmatch")
async def match_threshold_start(call: CallbackQuery, state: FSMContext):
    if not await is_admin(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    await state.set_state(SettingsForm.match_threshold)
    current = await q.get_setting("match_threshold", "60")
    await call.message.answer(
        f"🎯 <b>Moslik chegarasi</b>\n\nHozirgi qiymat: <b>{current}%</b>\n\n"
        "Oddiy (vakansiyasiz) ariza kelganda, agar u ochiq vakansiyaga shu foizdan "
        "yuqori mos kelsa, HR ga avtomatik tavsiya beriladi.\n\n"
        "Yangi foizni yuboring (0–100 oralig'ida). Masalan: <b>60</b>"
    )
    await call.answer()


@router.message(SettingsForm.match_threshold, F.text)
async def match_threshold_save(message: Message, state: FSMContext):
    value = message.text.strip().replace("%", "")
    if not value.isdigit() or not (0 <= int(value) <= 100):
        await message.answer("❗️ 0 dan 100 gacha butun son yuboring. Masalan: 60")
        return
    await state.clear()
    await q.set_setting("match_threshold", str(int(value)))
    me = await actor(message.from_user.id)
    await q.add_log(message.from_user.id, me["full_name"], "sozlama_moslik", value)
    await message.answer(f"✅ Moslik chegarasi <b>{int(value)}%</b> qilib belgilandi.")


# ---------------- EKSPORT ----------------
@router.message(F.text == "📤 Eksport")
async def admin_export(message: Message):
    if not await is_admin(message.from_user.id):
        return
    await message.answer(
        "📤 <b>Excel eksport</b>\nQaysi ma'lumotni yuklab olasiz?",
        reply_markup=kb.export_kb("admin"),
    )


# ---------------- AUDIT LOG ----------------
@router.message(F.text == "🧾 Audit log")
async def admin_audit(message: Message):
    if not await is_admin(message.from_user.id):
        return
    logs = await q.list_logs(limit=30)
    if not logs:
        await message.answer("Log yozuvlari yo'q.")
        return
    text = "🧾 <b>Oxirgi 30 ta harakat:</b>\n\n"
    for l in logs:
        text += (
            f"🕐 {l['created_at']}\n"
            f"👤 {l['actor_name'] or l['tg_id']} — <b>{l['action']}</b>\n"
            f"   {l['details']}\n\n"
        )
    # uzun bo'lsa bo'lib yuboramiz
    for chunk in _split(text):
        await message.answer(chunk)


def _split(text, size=3800):
    return [text[i:i + size] for i in range(0, len(text), size)]
