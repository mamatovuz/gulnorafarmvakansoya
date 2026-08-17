"""Xodim ma'lumotlarini o'zgartirish (admin/HR).

Bitta umumiy oqim ikki joydan ochiladi:
  • Admin/HR panel → «🛠 Ma'lumotlarni o'zgartirish»
  • Admin panel → «🏢 Filiallar» → «👥 Filial xodimlari bo'yicha ko'rish»

Oqim: qidiruv usuli → (filial/ism) → xodim → profil kartochkasi →
rolni / filialni / maqomni (o'rganuvchi·sinov) almashtirish.
"""
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from database import queries as q
from database.db import (
    ROLE_ADMIN, ROLE_HR, ROLE_MANAGER, ROLE_EMPLOYEE, ROLE_PHARMACIST,
    ROLE_DIRECTOR, ROLE_ACCOUNTANT, ROLE_IT, ROLE_CANDIDATE,
    EMP_STATUS_LABELS, ES_REGULAR,
)
from states import EmpManageForm, EmpEditForm, BranchChangeForm
import keyboards as kb
from utils import (
    send_employee_profile, safe_send, PROFILE_UPDATE_NOTICE, employee_profile_text,
)

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


async def _is_staff(tg_id):
    u = await q.get_user(tg_id)
    return u and u["role"] in (ROLE_HR, ROLE_ADMIN)


async def _is_admin(tg_id):
    u = await q.get_user(tg_id)
    return u and u["role"] == ROLE_ADMIN


# ---------------- KIRISH ----------------
@router.message(F.text == kb.EMP_MANAGE_BTN)
async def emp_manage_home(message: Message, state: FSMContext):
    if not await _is_staff(message.from_user.id):
        return
    await state.clear()
    await message.answer(
        "🛠 <b>Ma'lumotlarni o'zgartirish</b>\n"
        "━━━━━━━━━━━━\n"
        "Xodimni qanday topamiz? Tanlangach uning kartochkasidan "
        "<b>rol</b>, <b>filial</b> yoki <b>maqomini</b> o'zgartirasiz.",
        reply_markup=kb.emp_manage_entry_kb(),
    )


@router.callback_query(F.data == "emm:home")
async def emp_manage_back_home(call: CallbackQuery, state: FSMContext):
    if not await _is_staff(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    await state.clear()
    await call.message.answer(
        "🛠 <b>Ma'lumotlarni o'zgartirish</b>\nXodimni qanday topamiz?",
        reply_markup=kb.emp_manage_entry_kb(),
    )
    await call.answer()


@router.callback_query(F.data == "emm:branch")
async def emp_manage_by_branch(call: CallbackQuery, state: FSMContext):
    if not await _is_staff(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    await state.clear()
    branches = await q.list_branches()
    if not branches:
        await call.answer("Filiallar ro'yxati bo'sh.", show_alert=True)
        return
    await call.message.answer(
        "🏢 Qaysi filial xodimlarini ko'rmoqchisiz?",
        reply_markup=kb.emp_manage_branch_kb(branches),
    )
    await call.answer()


@router.callback_query(F.data == "emm:nobranch")
async def emp_manage_no_branch(call: CallbackQuery, state: FSMContext):
    """Filiali biriktirilmagan xodimlar — topib, kartochkasidan filial beriladi."""
    if not await _is_staff(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    await state.clear()
    profiles = await q.search_employees(no_branch=True)
    await _send_list(
        call.message, profiles,
        "⚠️ <b>Filialsiz xodimlar</b>\n"
        "Har birini tanlab, kartochkasidan «🏢 Filialni almashtirish» orqali "
        "filial biriktiring.",
    )
    await call.answer()


# ---- Butun filialga maqom belgilash (barcha xodimlar) ----
@router.callback_query(F.data == "emm:allstatus")
async def emp_manage_allstatus_branches(call: CallbackQuery, state: FSMContext):
    if not await _is_staff(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    await state.clear()
    branches = await q.list_branches()
    if not branches:
        await call.answer("Filiallar ro'yxati bo'sh.", show_alert=True)
        return
    await call.message.answer(
        "👥 <b>Butun filialga maqom belgilash</b>\n\n"
        "Qaysi filial xodimlariga qo'llaymiz? Filialni tanlang:",
        reply_markup=kb.emp_manage_allstatus_branch_kb(branches),
    )
    await call.answer()


@router.callback_query(F.data.startswith("emmallst:"))
async def emp_manage_allstatus_pick(call: CallbackQuery):
    if not await _is_staff(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    bid = int(call.data.split(":")[1])
    branch = await q.get_branch(bid)
    bname = branch["name"] if branch else f"#{bid}"
    profiles = await q.list_employee_profiles(branch_id=bid)
    if not profiles:
        await call.message.answer(f"🏢 <b>{bname}</b> filialida xodim yo'q.")
        await call.answer()
        return
    await call.message.answer(
        f"🏢 <b>{bname}</b> — <b>{len(profiles)}</b> ta xodim.\n\n"
        "Hammasiga qaysi maqom belgilansin?",
        reply_markup=kb.emp_manage_allstatus_kb(bid),
    )
    await call.answer()


@router.callback_query(F.data.startswith("emmallsts:"))
async def emp_manage_allstatus_apply(call: CallbackQuery, bot: Bot):
    if not await _is_staff(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    _, bid_s, status = call.data.split(":")
    bid = int(bid_s)
    branch = await q.get_branch(bid)
    bname = branch["name"] if branch else f"#{bid}"
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await call.answer("Qo'llanmoqda…")
    rows = await q.set_status_all_in_branch(bid, status)
    label = EMP_STATUS_LABELS.get(status, status)
    me = await q.get_user(call.from_user.id)
    await q.add_log(
        call.from_user.id, me["full_name"] if me else "?",
        "butun_filial_maqom", f"{bname}: {len(rows)} ta -> {status}",
    )
    if status != ES_REGULAR:
        for r in rows:
            if r.get("tg_id"):
                await safe_send(
                    bot, r["tg_id"],
                    f"ℹ️ Sizning maqomingiz yangilandi: <b>{label}</b>.",
                )
    await call.message.answer(
        f"✅ <b>{bname}</b> filialidagi <b>{len(rows)}</b> ta xodimga "
        f"<b>{label}</b> maqomi belgilandi."
    )


@router.callback_query(F.data == "emm:text")
async def emp_manage_by_text(call: CallbackQuery, state: FSMContext):
    if not await _is_staff(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    await state.set_state(EmpManageForm.query)
    await call.message.answer(
        "🔤 Xodimning <b>ismi</b>, <b>@username</b>, <b>telefoni</b> yoki "
        "<b>ID</b> sini yozing.\n"
        "<i>To'liq yozish shart emas — bir qismi ham yetadi.</i>"
    )
    await call.answer()


@router.callback_query(F.data.startswith("emmbr:"))
async def emp_manage_branch_pick(call: CallbackQuery):
    if not await _is_staff(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    bid = int(call.data.split(":")[1])
    branch = await q.get_branch(bid)
    profiles = await q.search_employees(branch_id=bid)
    title = f"🏢 <b>{branch['name'] if branch else 'Filial'}</b> xodimlari"
    await _send_list(call.message, profiles, title)
    await call.answer()


@router.message(EmpManageForm.query, F.text)
async def emp_manage_text_run(message: Message, state: FSMContext):
    if not await _is_staff(message.from_user.id):
        await state.clear()
        return
    await state.clear()
    text = message.text.strip()
    profiles = await q.search_employees(text=text)
    await _send_list(message, profiles, f"🔍 <b>Qidiruv:</b> {text}")


async def _send_list(target, profiles, title):
    if not profiles:
        await target.answer(
            f"{title}\n\n😔 Hech kim topilmadi.",
            reply_markup=kb.emp_manage_entry_kb(),
        )
        return
    await target.answer(
        f"{title}\n\n👥 Topildi: <b>{len(profiles)}</b> ta\n"
        "👑 — filial rahbari · 👔 — direktor · 👤 — xodim\n"
        "Tahrirlash uchun xodimni tanlang:",
        reply_markup=kb.emp_manage_list_kb(profiles[:40]),
    )


# ---------------- BITTA XODIM KARTOCHKASI ----------------
async def _show_card(target, uid, prefix=""):
    profile = await q.get_employee_profile(uid)
    if not profile:
        await target.answer("❗️ Xodim topilmadi yoki profili yo'q.")
        return
    role = profile.get("role")
    status = profile.get("emp_status") or ES_REGULAR
    suffix = (
        f"\n\n🎭 Rol: <b>{ROLE_NAMES.get(role, role or '-')}</b>"
        f"\n🏷 Maqom: <b>{EMP_STATUS_LABELS.get(status, status)}</b>"
    )
    await send_employee_profile(
        target, profile,
        reply_markup=kb.emp_manage_edit_kb(uid),
        prefix=prefix, suffix=suffix,
    )


@router.callback_query(F.data.startswith("emmemp:"))
async def emp_manage_view(call: CallbackQuery, state: FSMContext):
    if not await _is_staff(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    await state.clear()
    uid = int(call.data.split(":")[1])
    await _show_card(call.message, uid)
    await call.answer()


# ---------------- MAYDONMA-MAYDON TAHRIRLASH ----------------
@router.callback_query(F.data.startswith("emmedit:"))
async def emp_manage_edit_menu(call: CallbackQuery):
    if not await _is_staff(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    uid = int(call.data.split(":")[1])
    profile = await q.get_employee_profile(uid)
    if not profile:
        await call.answer("Xodim topilmadi.", show_alert=True)
        return
    await call.message.answer(
        f"✏️ <b>{profile.get('full_name') or '-'}</b> — nimani tahrirlaymiz?\n"
        "Kerakli maydonni bosing, so'ng yangi qiymatni yuboring:",
        reply_markup=kb.emp_manage_field_kb(uid),
    )
    await call.answer()


@router.callback_query(F.data.startswith("emmf:"))
async def emp_manage_field_ask(call: CallbackQuery, state: FSMContext):
    if not await _is_staff(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    _, uid_s, field = call.data.split(":")
    uid = int(uid_s)
    prompt = kb.EMP_EDIT_PROMPTS.get(field)
    if not prompt:
        await call.answer("Noma'lum maydon.", show_alert=True)
        return
    # Ma'lumot (education) — qo'lda yozish o'rniga tugmalardan tanlanadi
    if field == "education":
        await state.clear()
        await call.message.answer(
            "🎓 <b>Ma'lumotini tanlang:</b>",
            reply_markup=kb.emp_manage_education_kb(uid),
        )
        await call.answer()
        return
    await state.set_state(EmpEditForm.value)
    await state.update_data(edit_uid=uid, edit_field=field)
    await call.message.answer(prompt)
    await call.answer()


@router.callback_query(F.data.startswith("emmedu:"))
async def emp_manage_set_education(call: CallbackQuery, state: FSMContext):
    if not await _is_staff(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    await state.clear()
    _, uid_s, idx_s = call.data.split(":")
    uid = int(uid_s)
    idx = int(idx_s)
    if not (0 <= idx < len(kb.EDUCATION_OPTIONS)):
        await call.answer("Noma'lum tanlov.", show_alert=True)
        return
    value = kb.EDUCATION_OPTIONS[idx]
    profile = await q.get_employee_profile(uid)
    if not profile:
        await call.answer("Xodim topilmadi.", show_alert=True)
        return
    await q.update_employee_field(uid, "education", value)
    await _log_edit(call, uid, "🎓 Ma'lumoti")
    await call.answer("Saqlandi ✅")
    await _show_card(call.message, uid, prefix=f"✅ Ma'lumoti yangilandi: <b>{value}</b>")


@router.message(EmpEditForm.value, F.photo)
async def emp_manage_field_photo(message: Message, state: FSMContext):
    if not await _is_staff(message.from_user.id):
        await state.clear()
        return
    data = await state.get_data()
    uid, field = data.get("edit_uid"), data.get("edit_field")
    if field != "photo":
        await message.answer("❗️ Bu maydon uchun rasm emas, matn yuboring.")
        return
    file_id = message.photo[-1].file_id
    await q.update_employee_field(uid, "photo_file_id", file_id)
    await state.clear()
    await _log_edit(message, uid, "rasm")
    await _show_card(message, uid, prefix="✅ Rasm yangilandi")


@router.message(EmpEditForm.value, F.text)
async def emp_manage_field_value(message: Message, state: FSMContext, bot: Bot):
    if not await _is_staff(message.from_user.id):
        await state.clear()
        return
    data = await state.get_data()
    uid, field = data.get("edit_uid"), data.get("edit_field")
    value = message.text.strip()
    if field == "photo":
        await message.answer("❗️ Iltimos, matn emas, rasm yuboring.")
        return
    profile = await q.get_employee_profile(uid)
    if not profile:
        await state.clear()
        await message.answer("❗️ Xodim topilmadi.")
        return

    label = dict((k, l) for k, l, _p in kb.EMP_EDIT_FIELDS).get(field, field)
    if field == "name":
        await q.set_real_name(user_id=uid, full_name=value)
    elif field == "phone":
        tg_id = profile.get("tg_id")
        if tg_id:
            await q.update_phone(tg_id, value)
    else:
        await q.update_employee_field(uid, field, value)
    await state.clear()
    await _log_edit(message, uid, label)
    await _show_card(message, uid, prefix=f"✅ {label} yangilandi")


async def _log_edit(message, uid, label):
    me = await q.get_user(message.from_user.id)
    profile = await q.get_employee_profile(uid)
    await q.add_log(
        message.from_user.id, me["full_name"] if me else "?",
        "xodim_malumot_tahrir",
        f"{profile.get('full_name') if profile else uid}: {label}",
    )


# ---------------- XODIMDAN O'ZI YANGILASHNI SO'RASH ----------------
@router.callback_query(F.data.startswith("emmreqfresh:"))
async def emp_manage_request_fresh(call: CallbackQuery, bot: Bot):
    if not await _is_staff(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    uid = int(call.data.split(":")[1])
    profile = await q.get_employee_profile(uid)
    if not profile:
        await call.answer("Xodim topilmadi.", show_alert=True)
        return
    total, tg_ids = await q.request_profile_update_all(user_id=uid)
    sent = 0
    for tid in tg_ids:
        if await safe_send(bot, tid, PROFILE_UPDATE_NOTICE,
                           reply_markup=kb.profile_update_start_kb()):
            sent += 1
    me = await q.get_user(call.from_user.id)
    await q.add_log(
        call.from_user.id, me["full_name"] if me else "?",
        "malumot_yangilash_sorovi",
        f"👤 {profile.get('full_name')} — {sent}/{total}",
    )
    if not total:
        await call.answer("Bu xodimdan so'rab bo'lmaydi.", show_alert=True)
        return
    await call.answer("So'rov yuborildi ✅")
    await call.message.answer(
        f"🔄 <b>{profile.get('full_name') or '-'}</b> ga ma'lumotini yangilash "
        f"so'rovi yuborildi.\n"
        "U ma'lumotlarini yangilamaguncha botning boshqa bo'limlaridan "
        "foydalana olmaydi."
    )


# ---------------- ROL ALMASHTIRISH ----------------
@router.callback_query(F.data.startswith("emmrole:"))
async def emp_manage_role_menu(call: CallbackQuery):
    if not await _is_staff(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    uid = int(call.data.split(":")[1])
    profile = await q.get_employee_profile(uid)
    if not profile:
        await call.answer("Xodim topilmadi.", show_alert=True)
        return
    cur = ROLE_NAMES.get(profile.get("role"), profile.get("role") or "-")
    await call.message.answer(
        f"🎭 <b>{profile.get('full_name') or '-'}</b>\n"
        f"Hozirgi rol: <b>{cur}</b>\n\nYangi rolni tanlang:",
        reply_markup=kb.emp_manage_role_kb(uid),
    )
    await call.answer()


@router.callback_query(F.data.startswith("emmsetrole:"))
async def emp_manage_set_role(call: CallbackQuery, bot: Bot):
    if not await _is_staff(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    _, uid_s, role = call.data.split(":")
    uid = int(uid_s)
    profile = await q.get_employee_profile(uid)
    if not profile:
        await call.answer("Xodim topilmadi.", show_alert=True)
        return
    position = ROLE_NAMES.get(role, role).split(" ", 1)[-1]
    old_role = await q.set_employee_role(uid, role, position=position)
    me = await q.get_user(call.from_user.id)
    await q.add_log(
        call.from_user.id, me["full_name"] if me else "?",
        "xodim_rol_ozgartirildi",
        f"{profile.get('full_name')}: {old_role} -> {role}",
    )
    tg_id = profile.get("tg_id")
    if tg_id:
        await safe_send(
            bot, tg_id,
            f"ℹ️ Sizga yangi rol berildi: <b>{ROLE_NAMES.get(role, role)}</b>.\n"
            "O'zgarish kuchga kirishi uchun /start bosing.",
        )
    await call.answer("Rol o'zgartirildi ✅")
    await _show_card(
        call.message, uid,
        prefix=f"✅ Rol o'zgartirildi: <b>{ROLE_NAMES.get(role, role)}</b>",
    )


# ---------------- MAQOM (o'rganuvchi / sinov) ----------------
@router.callback_query(F.data.startswith("emmstatus:"))
async def emp_manage_status_menu(call: CallbackQuery):
    if not await _is_staff(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    uid = int(call.data.split(":")[1])
    profile = await q.get_employee_profile(uid)
    if not profile:
        await call.answer("Xodim topilmadi.", show_alert=True)
        return
    cur = profile.get("emp_status") or ES_REGULAR
    await call.message.answer(
        f"🏷 <b>{profile.get('full_name') or '-'}</b>\n"
        f"Hozirgi maqom: <b>{EMP_STATUS_LABELS.get(cur, cur)}</b>\n\n"
        "Yangi maqomni tanlang:",
        reply_markup=kb.emp_manage_status_kb(uid),
    )
    await call.answer()


@router.callback_query(F.data.startswith("emmsetstatus:"))
async def emp_manage_set_status(call: CallbackQuery, bot: Bot):
    if not await _is_staff(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    _, uid_s, status = call.data.split(":")
    uid = int(uid_s)
    profile = await q.get_employee_profile(uid)
    if not profile:
        await call.answer("Xodim topilmadi.", show_alert=True)
        return
    await q.set_employee_status(uid, status)
    me = await q.get_user(call.from_user.id)
    await q.add_log(
        call.from_user.id, me["full_name"] if me else "?",
        "xodim_maqom_ozgartirildi",
        f"{profile.get('full_name')}: -> {status}",
    )
    label = EMP_STATUS_LABELS.get(status, status)
    tg_id = profile.get("tg_id")
    if tg_id and status != ES_REGULAR:
        await safe_send(
            bot, tg_id, f"ℹ️ Sizning maqomingiz yangilandi: <b>{label}</b>."
        )
    await call.answer("Maqom yangilandi ✅")
    await _show_card(call.message, uid, prefix=f"✅ Maqom yangilandi: <b>{label}</b>")


# ---------------- FILIAL ALMASHTIRISH ----------------
@router.callback_query(F.data.startswith("emmbranch:"))
async def emp_manage_branch_menu(call: CallbackQuery):
    if not await _is_staff(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    uid = int(call.data.split(":")[1])
    profile = await q.get_employee_profile(uid)
    if not profile:
        await call.answer("Xodim topilmadi.", show_alert=True)
        return
    branches = await q.list_branches()
    if not branches:
        await call.answer("Filiallar ro'yxati bo'sh.", show_alert=True)
        return
    await call.message.answer(
        f"🏢 <b>{profile.get('full_name') or '-'}</b>\n"
        f"Hozirgi filial: <b>{profile.get('branch_name') or '—'}</b>\n\n"
        "Yangi filialni tanlang:",
        reply_markup=kb.emp_manage_branch_pick_kb(uid, branches),
    )
    await call.answer()


@router.callback_query(F.data.startswith("emmsetbr:"))
async def emp_manage_set_branch(call: CallbackQuery, bot: Bot):
    if not await _is_staff(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    _, uid_s, bid_s = call.data.split(":")
    uid, bid = int(uid_s), int(bid_s)
    profile = await q.get_employee_profile(uid)
    if not profile:
        await call.answer("Xodim topilmadi.", show_alert=True)
        return
    old_branch = await q.set_employee_branch(uid, bid)
    branch = await q.get_branch(bid)
    bname = branch["name"] if branch else f"#{bid}"
    me = await q.get_user(call.from_user.id)
    await q.add_log(
        call.from_user.id, me["full_name"] if me else "?",
        "xodim_filial_ozgartirildi",
        f"{profile.get('full_name')}: {old_branch} -> {bid}",
    )
    tg_id = profile.get("tg_id")
    if tg_id:
        await safe_send(
            bot, tg_id,
            f"ℹ️ Siz endi <b>{bname}</b> filialiga biriktirildingiz.",
        )
    await call.answer("Filial o'zgartirildi ✅")
    await _show_card(call.message, uid, prefix=f"✅ Yangi filial: <b>{bname}</b>")


# ================= ADMIN «🏢 FILIALLAR» IKKI YO'NALISHI =================
@router.callback_query(F.data == "brroot:edit")
async def branches_root_edit(call: CallbackQuery):
    if not await _is_admin(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    branches = await q.list_branches()
    await call.message.answer(
        "✏️ <b>Filiallarni tahrirlash</b>", reply_markup=kb.branches_manage_kb(branches)
    )
    await call.answer()


@router.callback_query(F.data == "brroot:staff")
async def branches_root_staff(call: CallbackQuery, state: FSMContext):
    if not await _is_admin(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    await state.clear()
    branches = await q.list_branches()
    if not branches:
        await call.answer("Filiallar ro'yxati bo'sh.", show_alert=True)
        return
    await call.message.answer(
        "👥 <b>Filial xodimlari</b>\nQaysi filialni ochamiz?",
        reply_markup=kb.emp_manage_branch_kb(branches),
    )
    await call.answer()


# ================= 🔀 FILIAL ALMASHTIRISH (admin/HR) =================
# Xodimni boshqa filialga o'tkazish: filial/ism bo'yicha topiladi → kartochka →
# yangi filial → «Ha/Yo'q» tasdiq → o'zgaradi va ikkala filial rahbariga xabar.

@router.message(F.text == "🔀 Filial almashtirish")
async def branch_change_home(message: Message, state: FSMContext):
    if not await _is_staff(message.from_user.id):
        return
    await state.clear()
    await message.answer(
        "🔀 <b>Filial almashtirish</b>\n"
        "━━━━━━━━━━━━\n"
        "Xodimni boshqa filialga o'tkazish uchun avval uni toping:",
        reply_markup=kb.branch_change_entry_kb(),
    )


@router.callback_query(F.data == "bch:home")
async def branch_change_back_home(call: CallbackQuery, state: FSMContext):
    if not await _is_staff(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    await state.clear()
    await call.message.answer(
        "🔀 <b>Filial almashtirish</b>\nXodimni qanday topamiz?",
        reply_markup=kb.branch_change_entry_kb(),
    )
    await call.answer()


@router.callback_query(F.data == "bch:find")
async def branch_change_find(call: CallbackQuery, state: FSMContext):
    if not await _is_staff(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    await state.set_state(BranchChangeForm.query)
    await call.message.answer(
        "🔤 Xodimning <b>ismi</b>, <b>@username</b>, <b>telefoni</b> yoki "
        "<b>ID</b> sini yozing:"
    )
    await call.answer()


@router.callback_query(F.data == "bch:branch")
async def branch_change_by_branch(call: CallbackQuery, state: FSMContext):
    if not await _is_staff(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    await state.clear()
    branches = await q.list_branches()
    if not branches:
        await call.answer("Filiallar ro'yxati bo'sh.", show_alert=True)
        return
    await call.message.answer(
        "🏢 Qaysi filial xodimini o'tkazamiz? Filialni tanlang:",
        reply_markup=kb.branch_change_branches_kb(branches),
    )
    await call.answer()


# ---- Butun filialni ko'chirish (barcha xodimlar) ----
@router.callback_query(F.data == "bch:allsrc")
async def branch_change_all_source(call: CallbackQuery, state: FSMContext):
    if not await _is_staff(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    await state.clear()
    branches = await q.list_branches()
    if not branches:
        await call.answer("Filiallar ro'yxati bo'sh.", show_alert=True)
        return
    await call.message.answer(
        "👥 <b>Butun filialni ko'chirish</b>\n\n"
        "Qaysi filial xodimlarini ko'chiramiz? <b>Manba</b> filialni tanlang:",
        reply_markup=kb.branch_change_branches_kb(branches, prefix="bchallsrc"),
    )
    await call.answer()


@router.callback_query(F.data.startswith("bchallsrc:"))
async def branch_change_all_pick_target(call: CallbackQuery):
    if not await _is_staff(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    from_bid = int(call.data.split(":")[1])
    branch = await q.get_branch(from_bid)
    bname = branch["name"] if branch else f"#{from_bid}"
    profiles = await q.list_employee_profiles(branch_id=from_bid)
    if not profiles:
        await call.message.answer(f"🏢 <b>{bname}</b> filialida xodim yo'q.")
        await call.answer()
        return
    branches = await q.list_branches()
    await call.message.answer(
        f"🏢 Manba: <b>{bname}</b> — <b>{len(profiles)}</b> ta xodim.\n\n"
        "Ular <b>qaysi filialga</b> ko'chirilsin?",
        reply_markup=kb.branch_change_all_target_kb(from_bid, branches),
    )
    await call.answer()


@router.callback_query(F.data.startswith("bchallto:"))
async def branch_change_all_confirm_ask(call: CallbackQuery):
    if not await _is_staff(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    _, from_s, to_s = call.data.split(":")
    from_bid, to_bid = int(from_s), int(to_s)
    src = await q.get_branch(from_bid)
    dst = await q.get_branch(to_bid)
    sname = src["name"] if src else f"#{from_bid}"
    dname = dst["name"] if dst else f"#{to_bid}"
    profiles = await q.list_employee_profiles(branch_id=from_bid)
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await call.message.answer(
        "⚠️ <b>Butun filialni ko'chirishni tasdiqlaysizmi?</b>\n"
        "━━━━━━━━━━━━\n"
        f"🏢 <b>{sname}</b> → <b>{dname}</b>\n"
        f"👥 Ko'chiriladigan xodimlar: <b>{len(profiles)}</b> ta",
        reply_markup=kb.branch_change_all_confirm_kb(from_bid, to_bid),
    )
    await call.answer()


@router.callback_query(F.data.startswith("bchallgo:"))
async def branch_change_all_go(call: CallbackQuery, bot: Bot):
    if not await _is_staff(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    _, from_s, to_s = call.data.split(":")
    from_bid, to_bid = int(from_s), int(to_s)
    dst = await q.get_branch(to_bid)
    src = await q.get_branch(from_bid)
    dname = dst["name"] if dst else f"#{to_bid}"
    sname = src["name"] if src else f"#{from_bid}"
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await call.answer("Ko'chirilmoqda…")
    moved = await q.move_all_in_branch(from_bid, to_bid)
    me = await q.get_user(call.from_user.id)
    await q.add_log(
        call.from_user.id, me["full_name"] if me else "?",
        "butun_filial_kochirildi", f"{sname} -> {dname}: {len(moved)} ta",
    )
    for m in moved:
        if m.get("tg_id"):
            await safe_send(
                bot, m["tg_id"],
                f"ℹ️ Siz endi <b>{dname}</b> filialiga biriktirildingiz.",
            )
    await call.message.answer(
        f"✅ <b>{sname}</b> → <b>{dname}</b>: <b>{len(moved)}</b> ta xodim ko'chirildi."
    )


@router.callback_query(F.data.startswith("bchbr:"))
async def branch_change_branch_pick(call: CallbackQuery):
    if not await _is_staff(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    bid = int(call.data.split(":")[1])
    branch = await q.get_branch(bid)
    profiles = await q.search_employees(branch_id=bid)
    bname = branch["name"] if branch else "Filial"
    if not profiles:
        await call.message.answer(f"🏢 <b>{bname}</b> filialida xodim yo'q.")
        await call.answer()
        return
    await call.message.answer(
        f"🏢 <b>{bname}</b> — <b>{len(profiles)}</b> ta xodim.\n"
        "O'tkaziladigan xodimni tanlang:",
        reply_markup=kb.branch_change_people_kb(profiles[:40]),
    )
    await call.answer()


@router.message(BranchChangeForm.query, F.text)
async def branch_change_search_run(message: Message, state: FSMContext):
    if not await _is_staff(message.from_user.id):
        await state.clear()
        return
    await state.clear()
    text = message.text.strip()
    profiles = await q.search_employees(text=text)
    if not profiles:
        await message.answer(
            f"😔 «{text}» bo'yicha xodim topilmadi. Boshqa so'z bilan urinib ko'ring.",
            reply_markup=kb.branch_change_entry_kb(),
        )
        return
    await message.answer(
        f"🔍 <b>Qidiruv:</b> {text} — <b>{len(profiles)}</b> ta topildi\nTanlang:",
        reply_markup=kb.branch_change_people_kb(profiles[:40]),
    )


async def _branch_change_card(target, uid):
    profile = await q.get_employee_profile(uid)
    if not profile:
        await target.answer("❗️ Xodim topilmadi yoki profili yo'q.")
        return
    suffix = (
        f"\n\n🏢 Joriy filial: <b>{profile.get('branch_name') or '—'}</b>\n"
        "Boshqa filialga o'tkazish uchun quyidagi tugmani bosing 👇"
    )
    await send_employee_profile(
        target, profile,
        reply_markup=kb.branch_change_card_kb(uid), suffix=suffix,
    )


@router.callback_query(F.data.startswith("bchemp:"))
async def branch_change_emp(call: CallbackQuery, state: FSMContext):
    if not await _is_staff(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    await state.clear()
    uid = int(call.data.split(":")[1])
    await _branch_change_card(call.message, uid)
    await call.answer()


@router.callback_query(F.data.startswith("bchmove:"))
async def branch_change_pick_target(call: CallbackQuery):
    if not await _is_staff(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    uid = int(call.data.split(":")[1])
    profile = await q.get_employee_profile(uid)
    if not profile:
        await call.answer("Xodim topilmadi.", show_alert=True)
        return
    branches = await q.list_branches()
    if not branches:
        await call.answer("Filiallar ro'yxati bo'sh.", show_alert=True)
        return
    await call.message.answer(
        f"🔀 <b>{profile.get('full_name') or '-'}</b> ni qaysi filialga "
        "o'tkazamiz? Yangi filialni tanlang:",
        reply_markup=kb.branch_change_target_kb(uid, branches, profile.get("branch_id")),
    )
    await call.answer()


@router.callback_query(F.data.startswith("bchto:"))
async def branch_change_confirm(call: CallbackQuery):
    if not await _is_staff(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    _, uid_s, bid_s = call.data.split(":")
    uid, bid = int(uid_s), int(bid_s)
    profile = await q.get_employee_profile(uid)
    branch = await q.get_branch(bid)
    if not profile or not branch:
        await call.answer("Ma'lumot topilmadi.", show_alert=True)
        return
    await call.message.answer(
        f"❓ <b>{profile.get('full_name') or '-'}</b> ni "
        f"<b>{profile.get('branch_name') or '—'}</b> filialidan "
        f"<b>{branch['name']}</b> filialiga o'tkazmoqchimisiz?",
        reply_markup=kb.branch_change_confirm_kb(uid, bid),
    )
    await call.answer()


async def _notify_manager(bot, tid, text, profile):
    """Filial rahbariga xabar — rasm bo'lsa caption bilan, aks holda oddiy matn."""
    photo = profile.get("photo_file_id")
    if photo:
        try:
            await bot.send_photo(tid, photo, caption=text[:1024])
            return
        except Exception:
            pass
    await safe_send(bot, tid, text)


@router.callback_query(F.data.startswith("bchgo:"))
async def branch_change_apply(call: CallbackQuery, bot: Bot):
    if not await _is_staff(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    _, uid_s, bid_s = call.data.split(":")
    uid, bid = int(uid_s), int(bid_s)
    profile = await q.get_employee_profile(uid)
    new_branch = await q.get_branch(bid)
    if not profile or not new_branch:
        await call.answer("Ma'lumot topilmadi.", show_alert=True)
        return
    if profile.get("branch_id") == bid:
        await call.answer("Xodim allaqachon shu filialda.", show_alert=True)
        return

    old_branch_id = await q.set_employee_branch(uid, bid)
    old_branch = await q.get_branch(old_branch_id) if old_branch_id else None
    old_bname = old_branch["name"] if old_branch else "—"
    new_bname = new_branch["name"]
    name = profile.get("full_name") or "-"

    me = await q.get_user(call.from_user.id)
    await q.add_log(
        call.from_user.id, me["full_name"] if me else "?",
        "xodim_filial_almashtirildi", f"{name}: {old_branch_id} -> {bid}",
    )
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await call.message.answer(
        f"✅ <b>{name}</b> <b>{old_bname}</b> → <b>{new_bname}</b> filialiga o'tkazildi."
    )
    await call.answer("O'tkazildi ✅")

    # Xodimning o'ziga xabar
    if profile.get("tg_id"):
        await safe_send(
            bot, profile["tg_id"],
            f"ℹ️ Siz endi <b>{new_bname}</b> filialiga biriktirildingiz "
            f"(oldingi filial: {old_bname}).",
        )

    info = employee_profile_text({**profile, "branch_name": new_bname})

    # Eski filial rahbari(lari)ga xabar
    if old_branch_id:
        old_text = (
            "🔀 <b>Xodim boshqa filialga ko'chirildi</b>\n"
            "━━━━━━━━━━━━\n"
            f"👤 <b>{name}</b>\n"
            f"➡️ Sizning <b>{old_bname}</b> filialingizdan <b>{new_bname}</b> "
            "filialiga o'tkazildi.\n\n" + info
        )
        for tid in set(await q.branch_manager_tg_ids(old_branch_id)):
            await _notify_manager(bot, tid, old_text, profile)

    # Yangi filial rahbari(lari)ga xabar (rasm bilan)
    new_text = (
        "🔀 <b>Filialingizga yangi xodim o'tdi</b>\n"
        "━━━━━━━━━━━━\n"
        f"👤 <b>{name}</b>\n"
        f"⬅️ <b>{old_bname}</b> filialidan sizning <b>{new_bname}</b> "
        "filialingizga o'tkazildi.\n\n" + info
    )
    for tid in set(await q.branch_manager_tg_ids(bid)):
        await _notify_manager(bot, tid, new_text, profile)
