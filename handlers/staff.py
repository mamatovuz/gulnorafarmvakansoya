"""Xodim panellari: filial rahbari, farmatsevt va direktor."""
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter

from database import queries as q
from database.db import (
    ROLE_ADMIN, ROLE_HR, ROLE_MANAGER, ROLE_PHARMACIST, ROLE_DIRECTOR,
    ROLE_EMPLOYEE, ROLE_ACCOUNTANT,
)
from states import (
    ManagerVacancyForm, TechIssueForm, CommentForm, ManagerMessageForm,
    TerminationForm,
)
import keyboards as kb
from utils import (
    safe_send, manager_request_text, employee_profile_text, fine_text,
    application_text, send_application_resume, send_application_photo,
    vacancy_channel_text, mark_vacancy_channel_filled, gender_label,
    broadcast_request,
)

router = Router()

ROLE_NAMES = {
    ROLE_ADMIN: "Admin",
    ROLE_HR: "HR",
    ROLE_MANAGER: "Filial rahbari",
    ROLE_PHARMACIST: "Farmatsevt",
    ROLE_DIRECTOR: "Direktor",
    ROLE_ACCOUNTANT: "Moliya bo'limi",
    ROLE_EMPLOYEE: "Oddiy xodim",
}


async def current_user(message: Message):
    return await q.get_user(message.from_user.id)


async def ensure_role(message: Message, *roles):
    user = await current_user(message)
    if not user or user["role"] not in roles:
        await message.answer("⛔ Sizda bu panel uchun ruxsat yo'q.")
        return None
    return user


async def notify_hr_admin(bot: Bot, text, reply_markup=None, kind=None, ref_id=None):
    """HR va adminlarga xabar yuboradi.

    `kind`/`ref_id` berilsa — yuborilgan xabarlar bazaga yoziladi va kimdir
    so'rovni ko'rib chiqqach qolganlaridan avtomatik o'chiriladi."""
    hr_ids = await q.all_user_tg_ids(role=ROLE_HR)
    admin_ids = await q.all_user_tg_ids(role=ROLE_ADMIN)
    targets = set(hr_ids + admin_ids)
    if kind and ref_id:
        await broadcast_request(bot, kind, ref_id, targets, text,
                                reply_markup=reply_markup)
        return
    for tid in targets:
        await safe_send(bot, tid, text, reply_markup=reply_markup)


# ---------------- FILIAL RAHBARI ----------------
@router.message(F.text == "🏢 Filial rahbari panel")
async def manager_panel(message: Message):
    user = await ensure_role(message, ROLE_MANAGER, ROLE_ADMIN)
    if not user:
        return
    profile = await q.get_employee_profile_by_tg(message.from_user.id)
    header = "🏢 <b>Filial rahbari paneli</b>"
    if profile:
        header += "\n\n" + employee_profile_text(profile)
    await message.answer(header, reply_markup=kb.manager_menu())


async def _manager_branch_id(user):
    if user.get("branch_id"):
        return user["branch_id"]
    profile = await q.get_employee_profile(user["id"])
    return profile.get("branch_id") if profile else None


def _mgr_vacancy_summary(data):
    return (
        "📋 <b>Vakansiya so'rovi</b>\n"
        "━━━━━━━━━━━━\n"
        f"💼 Yo'nalish: <b>{data.get('position') or '-'}</b>\n"
        f"👥 Kerakli soni: <b>{data.get('staff_count') or '-'}</b>\n"
        f"🚻 Kimlar kerak: <b>{gender_label(data.get('gender')) or '-'}</b>\n"
        f"🕒 Smena: {data.get('shift') or '-'}\n"
        f"📈 Tajriba: {data.get('experience') or '-'}\n"
        f"📝 Izoh: {data.get('details') or '—'}\n\n"
        "Hammasi to'g'rimi? Tasdiqlasangiz HR ga yuboriladi."
    )


@router.message(F.text == "➕ Xodim kerak")
async def manager_vacancy_start(message: Message, state: FSMContext):
    user = await ensure_role(message, ROLE_MANAGER, ROLE_ADMIN)
    if not user:
        return
    positions = await q.list_position_names()
    await state.set_state(ManagerVacancyForm.position)
    await message.answer(
        "➕ <b>Xodim kerak</b>\n\nQaysi yo'nalishga xodim kerak? Ro'yxatdan tanlang:",
        reply_markup=kb.manager_vacancy_position_kb(positions),
    )


@router.message(StateFilter(
    ManagerVacancyForm.position, ManagerVacancyForm.staff_count,
    ManagerVacancyForm.gender, ManagerVacancyForm.shift,
    ManagerVacancyForm.experience, ManagerVacancyForm.details,
), F.text == kb.CANCEL_BTN)
async def manager_vacancy_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Bekor qilindi.", reply_markup=kb.manager_menu())


@router.message(ManagerVacancyForm.position, F.text)
async def manager_vacancy_position(message: Message, state: FSMContext):
    await state.update_data(position=message.text.strip())
    await state.set_state(ManagerVacancyForm.staff_count)
    await message.answer(
        "👥 Nechta xodim kerak? Faqat son yozing. Masalan: <b>2</b>",
        reply_markup=kb.cancel_kb(),
    )


@router.message(ManagerVacancyForm.staff_count, F.text)
async def manager_vacancy_count(message: Message, state: FSMContext):
    await state.update_data(staff_count=message.text.strip())
    await state.set_state(ManagerVacancyForm.gender)
    await message.answer(
        "🚻 <b>Sizga qaysi turdagi odam kerak?</b>\n"
        "Quyidagi tugmalardan birini tanlang:",
        reply_markup=kb.manager_vacancy_gender_kb(),
    )


@router.message(ManagerVacancyForm.gender, F.text)
async def manager_vacancy_gender(message: Message, state: FSMContext):
    value = kb.MGR_GENDER_VALUES.get(message.text.strip())
    if not value:
        await message.answer(
            "❗️ Iltimos, quyidagi tugmalardan birini tanlang:",
            reply_markup=kb.manager_vacancy_gender_kb(),
        )
        return
    await state.update_data(gender=value)
    await state.set_state(ManagerVacancyForm.shift)
    await message.answer(
        "🕒 Qaysi smenaga xodim kerak? Tanlang:",
        reply_markup=kb.manager_vacancy_shift_kb(),
    )


@router.message(ManagerVacancyForm.shift, F.text)
async def manager_vacancy_shift(message: Message, state: FSMContext):
    await state.update_data(shift=message.text.strip())
    await state.set_state(ManagerVacancyForm.experience)
    await message.answer(
        "📈 Qanday tajriba talab qilinadi? Masalan: <b>kamida 1 yil</b> yoki "
        "<b>tajribasiz ham bo'ladi</b>.",
        reply_markup=kb.cancel_kb(),
    )


@router.message(ManagerVacancyForm.experience, F.text)
async def manager_vacancy_experience(message: Message, state: FSMContext):
    await state.update_data(experience=message.text.strip())
    await state.set_state(ManagerVacancyForm.details)
    await message.answer(
        "📝 Qo'shimcha talab yoki izoh bo'lsa yozing. Bo'lmasa «⏭️ O'tkazib yuborish».",
        reply_markup=kb.manager_vacancy_skip_kb(),
    )


@router.message(ManagerVacancyForm.details, F.text)
async def manager_vacancy_details(message: Message, state: FSMContext):
    text = message.text.strip()
    details = None if text == kb.MGR_VAC_SKIP else text
    await state.update_data(details=details)
    data = await state.get_data()
    await state.set_state(ManagerVacancyForm.confirm)
    await message.answer(
        "✅ Ma'lumot to'plandi.", reply_markup=kb.manager_menu()
    )
    await message.answer(
        _mgr_vacancy_summary(data), reply_markup=kb.manager_vacancy_confirm_kb()
    )


@router.callback_query(F.data == "mgrvac_cancel")
async def manager_vacancy_confirm_cancel(call: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await call.message.answer("❌ Vakansiya so'rovi bekor qilindi.")
    await call.answer()


@router.callback_query(F.data == "mgrvac_confirm")
async def manager_vacancy_confirm(call: CallbackQuery, state: FSMContext, bot: Bot):
    user = await q.get_user(call.from_user.id)
    if not user or user["role"] not in (ROLE_MANAGER, ROLE_ADMIN):
        await call.answer("⛔", show_alert=True)
        return
    data = await state.get_data()
    if not data.get("position"):
        await call.answer("⏳ Sessiya tugagan. Qaytadan «➕ Xodim kerak» ni bosing.",
                          show_alert=True)
        await state.clear()
        return
    await state.clear()
    rid = await q.add_manager_request({
        "manager_user_id": user["id"],
        "branch_id": user.get("branch_id"),
        "kind": "vacancy",
        "title": data.get("position"),
        "staff_count": data.get("staff_count"),
        "gender": data.get("gender"),
        "shift": data.get("shift"),
        "experience": data.get("experience"),
        "details": data.get("details"),
    })
    req = await q.get_manager_request(rid)
    await q.add_log(call.from_user.id, call.from_user.full_name,
                    "rahbar_vakansiya_soradi", f"#{rid}")
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await call.message.answer("✅ So'rovingiz HR ga yuborildi. HR tasdiqlagach "
                              "vakansiya kanalga joylanadi.")
    await call.answer("Yuborildi ✅")
    await notify_hr_admin(
        bot,
        "📨 <b>Filial rahbaridan yangi vakansiya so'rovi!</b>\n\n" + manager_request_text(req),
        reply_markup=kb.manager_request_actions_kb(rid, "vacancy"),
        kind="manager_request", ref_id=rid,
    )


@router.message(F.text == "🔧 Texnik nosozlik")
async def tech_issue_start(message: Message, state: FSMContext):
    user = await ensure_role(message, ROLE_MANAGER, ROLE_ADMIN)
    if not user:
        return
    await state.set_state(TechIssueForm.title)
    await message.answer("🔧 Nosozlik mavzusini yozing. Masalan: <b>Kassa ishlamayapti</b>")


@router.message(TechIssueForm.title, F.text)
async def tech_issue_title(message: Message, state: FSMContext):
    await state.update_data(title=message.text.strip())
    await state.set_state(TechIssueForm.details)
    await message.answer("📝 Nosozlik tafsilotini yozing:")


@router.message(TechIssueForm.details, F.text)
async def tech_issue_finish(message: Message, state: FSMContext, bot: Bot):
    user = await ensure_role(message, ROLE_MANAGER, ROLE_ADMIN)
    if not user:
        await state.clear()
        return
    data = await state.get_data()
    await state.clear()
    rid = await q.add_manager_request(
        {
            "manager_user_id": user["id"],
            "branch_id": user.get("branch_id"),
            "kind": "technical",
            "title": data.get("title"),
            "staff_count": None,
            "details": message.text.strip(),
        }
    )
    req = await q.get_manager_request(rid)
    await q.add_log(message.from_user.id, message.from_user.full_name, "texnik_nosozlik", f"#{rid}")
    await message.answer("✅ Texnik nosozlik HR ga yuborildi.")
    await notify_hr_admin(
        bot,
        "🔧 <b>Filial rahbaridan texnik nosozlik!</b>\n\n" + manager_request_text(req),
        reply_markup=kb.manager_request_actions_kb(rid, "technical"),
        kind="manager_request", ref_id=rid,
    )


@router.message(F.text == "📋 Mening so'rovlarim")
async def manager_my_requests(message: Message):
    user = await ensure_role(message, ROLE_MANAGER, ROLE_ADMIN)
    if not user:
        return
    reqs = await q.list_manager_requests(manager_user_id=user["id"], limit=20)
    if not reqs:
        await message.answer("Hali so'rov yubormagansiz.")
        return
    await message.answer(
        f"📋 <b>Mening so'rovlarim</b>\n\nJami: <b>{len(reqs)}</b> ta\n"
        "Batafsil ko'rish uchun so'rovni tanlang:",
        reply_markup=kb.manager_requests_list_kb(reqs, prefix="mgrreq"),
    )


@router.callback_query(F.data.startswith("mgrreq:"))
async def manager_my_request_view(call: CallbackQuery):
    user = await q.get_user(call.from_user.id)
    req = await q.get_manager_request(int(call.data.split(":")[1]))
    if not req or not user or (user["role"] != ROLE_ADMIN and req.get("manager_user_id") != user["id"]):
        await call.answer("So'rov topilmadi.", show_alert=True)
        return
    await call.message.answer(manager_request_text(req))
    await call.answer()


# ---------------- MENING VAKANSIYALARIM ----------------
@router.message(F.text == "📢 Mening vakansiyalarim")
async def manager_my_vacancies(message: Message):
    user = await ensure_role(message, ROLE_MANAGER, ROLE_ADMIN)
    if not user:
        return
    vacs = await q.list_vacancies_by_manager_request_creator(user["id"], limit=30)
    if not vacs:
        await message.answer(
            "📢 Hali tasdiqlangan vakansiyangiz yo'q.\n"
            "«➕ Xodim kerak» orqali so'rov yuboring — HR tasdiqlagach shu yerda ko'rinadi."
        )
        return
    await message.answer(
        f"📢 <b>Mening vakansiyalarim</b>\n\nJami: <b>{len(vacs)}</b> ta\n"
        "Batafsil ko'rish / yakunlash uchun tanlang:",
        reply_markup=kb.manager_my_vacancies_kb(vacs),
    )


@router.callback_query(F.data.startswith("mymgrvac:"))
async def manager_my_vacancy_view(call: CallbackQuery):
    user = await q.get_user(call.from_user.id)
    if not user or user["role"] not in (ROLE_MANAGER, ROLE_ADMIN):
        await call.answer("⛔", show_alert=True)
        return
    vid = int(call.data.split(":")[1])
    v = await q.get_vacancy(vid)
    if not v:
        await call.answer("Vakansiya topilmadi.", show_alert=True)
        return
    if v.get("filled"):
        status = "✅ Hodimlar soni to'ldi (yakunlangan)"
    elif v.get("is_active"):
        status = "🟢 Faol — nomzodlar qabul qilinmoqda"
    else:
        status = "🔴 Yopiq"
    text = vacancy_channel_text(v) + f"\n\n📌 Holati: <b>{status}</b>"
    markup = None if v.get("filled") else kb.manager_vacancy_finish_kb(vid)
    await call.message.answer(text, reply_markup=markup)
    await call.answer()


@router.callback_query(F.data.startswith("mgrvacfin:"))
async def manager_vacancy_finish_cb(call: CallbackQuery, bot: Bot):
    user = await q.get_user(call.from_user.id)
    if not user or user["role"] not in (ROLE_MANAGER, ROLE_ADMIN):
        await call.answer("⛔", show_alert=True)
        return
    vid = int(call.data.split(":")[1])
    v = await q.get_vacancy(vid)
    if not v:
        await call.answer("Vakansiya topilmadi.", show_alert=True)
        return
    if v.get("filled"):
        await call.answer("Bu vakansiya allaqachon yakunlangan.", show_alert=True)
        return
    await q.mark_vacancy_filled(vid)
    await q.add_log(call.from_user.id, user.get("full_name"), "vakansiya_yakunladi", f"#{vid}")
    # Kanaldagi postni yangilaymiz
    v = await q.get_vacancy(vid)
    channel_ok = await mark_vacancy_channel_filled(bot, v)
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    note = " Kanaldagi e'lon yangilandi." if channel_ok else ""
    await call.message.answer(
        f"✅ Vakansiya #{vid} yakunlandi — hodimlar soni to'ldi.{note}"
    )
    await call.answer("Yakunlandi ✅")
    # HR/Admin ga xabar
    await notify_hr_admin(
        bot,
        f"✅ <b>Vakansiya yakunlandi</b>\n\n"
        f"💼 {v.get('title')} · 🏢 {v.get('branch_name') or '-'}\n"
        f"Filial rahbari «{user.get('full_name')}» hodimlar soni to'lganini bildirdi.",
    )


@router.message(F.text == "👥 Filial xodimlari")
async def manager_branch_employees(message: Message):
    """Filial rahbari, direktor yoki admin o'z filialidagi xodimlarni ko'radi.
    Xodim ustiga bosilsa — ma'lumot va «Ishdan bo'shatish» tugmasi chiqadi."""
    user = await ensure_role(message, ROLE_MANAGER, ROLE_DIRECTOR, ROLE_ADMIN)
    if not user:
        return
    if user["role"] == ROLE_DIRECTOR:
        branch_id = await _director_branch_id(user)
        prefix = "diremp"
    else:
        branch_id = await _manager_branch_id(user)
        prefix = "mgremp"
    if not branch_id and user["role"] == ROLE_MANAGER:
        await message.answer("Sizga filial biriktirilmagan. HR yoki admin bilan bog'laning.")
        return
    branch = await q.get_branch(branch_id) if branch_id else None
    employees = await q.list_employee_profiles(branch_id=branch_id)
    branch_label = branch["name"] if branch else "Barcha filiallar"
    if not employees:
        await message.answer(
            f"👥 <b>{branch_label} xodimlari</b>\n\n"
            "Bu filialga hali xodim profili biriktirilmagan."
        )
        return

    pharmacists = [e for e in employees if e.get("role") == ROLE_PHARMACIST]
    no_uniform = [e for e in employees if e.get("uniform_status") == "no"]
    text = (
        f"👥 <b>{branch_label} xodimlari</b>\n\n"
        f"Jami: <b>{len(employees)}</b>\n"
        f"💊 Farmatsevtlar: <b>{len(pharmacists)}</b>\n"
        f"👕 Formasi yo'q: <b>{len(no_uniform)}</b>\n\n"
        "Ma'lumot va boshqarish uchun xodimni tanlang:"
    )
    await message.answer(
        text,
        reply_markup=kb.employee_profiles_list_kb(employees[:30], prefix=prefix),
    )


@router.callback_query(F.data.startswith("mgremp:"))
async def manager_employee_view(call: CallbackQuery):
    user = await q.get_user(call.from_user.id)
    if not user or user["role"] not in (ROLE_MANAGER, ROLE_ADMIN):
        await call.answer("⛔", show_alert=True)
        return
    profile = await q.get_employee_profile(int(call.data.split(":")[1]))
    branch_id = await _manager_branch_id(user)
    if not profile or (user["role"] != ROLE_ADMIN and profile.get("branch_id") != branch_id):
        await call.answer("Xodim topilmadi.", show_alert=True)
        return
    await call.message.answer(
        employee_profile_text(profile),
        reply_markup=kb.staff_fire_kb(profile["user_id"]),
    )
    await call.answer()


# ---------------- FILIAL STATISTIKASI ----------------
@router.message(F.text == "📊 Filial statistikasi")
async def manager_branch_stats(message: Message):
    user = await ensure_role(message, ROLE_MANAGER, ROLE_ADMIN)
    if not user:
        return
    branch_id = await _manager_branch_id(user)
    if not branch_id:
        await message.answer("Sizga filial biriktirilmagan. HR yoki admin bilan bog'laning.")
        return
    branch = await q.get_branch(branch_id)
    employees = await q.list_employee_profiles(branch_id=branch_id)
    apps = await q.filter_applications({"branch_id": branch_id}, limit=1000)
    pharmacists = sum(1 for e in employees if e.get("role") == ROLE_PHARMACIST)
    no_uniform = sum(1 for e in employees if e.get("uniform_status") == "no")
    st = {"new": 0, "interview": 0, "accepted": 0, "rejected": 0}
    for a in apps:
        st[a.get("status")] = st.get(a.get("status"), 0) + 1
    text = (
        f"📊 <b>{branch['name'] if branch else 'Filial'} statistikasi</b>\n"
        "━━━━━━━━━━━━\n"
        f"👥 Xodimlar: <b>{len(employees)}</b>\n"
        f"💊 Farmatsevtlar: <b>{pharmacists}</b>\n"
        f"👕 Formasi yo'q: <b>{no_uniform}</b>\n\n"
        "<b>📥 Filialga arizalar:</b>\n"
        f"🆕 Yangi: {st['new']} | 📅 Suhbat: {st['interview']}\n"
        f"✅ Qabul: {st['accepted']} | ❌ Rad: {st['rejected']}\n"
        f"📋 Jami: {len(apps)}"
    )
    await message.answer(text)


# ---------------- BUGUNGI DAVOMAT (rahbar) ----------------
@router.message(F.text == "📊 Bugungi davomat")
async def manager_today_attendance(message: Message):
    user = await ensure_role(message, ROLE_MANAGER, ROLE_ADMIN)
    if not user:
        return
    branch_id = await _manager_branch_id(user)
    if not branch_id:
        await message.answer("Sizga filial biriktirilmagan.")
        return
    branch = await q.get_branch(branch_id)
    employees = await q.list_employee_profiles(branch_id=branch_id)
    present = await q.attendance_detail(period="day", branch_id=branch_id, limit=200)
    absent = await q.attendance_absent_today(branch_id=branch_id)
    name = branch["name"] if branch else "Filial"
    lines = [
        f"📊 <b>{name} — bugungi davomat</b>",
        "━━━━━━━━━━━━",
        f"👥 Jami xodim: <b>{len(employees)}</b>",
        f"✅ Kelgan: <b>{len(present)}</b>",
        f"❌ Kelmagan: <b>{len(absent)}</b>",
    ]
    if present:
        lines.append("\n<b>✅ Kelganlar:</b>")
        for a in present:
            came = a.get("time") or "-"
            out = a.get("out_time")
            out_txt = f"ketdi {out}" if out else "hali ishda"
            marks = ""
            if a.get("late"):
                marks += " ⏰kech"
            if a.get("early"):
                marks += " 🏃erta"
            lines.append(f"• {a.get('full_name') or '-'} — keldi {came}, {out_txt}{marks}")
    if absent:
        lines.append("\n<b>❌ Kelmaganlar:</b>")
        for a in absent[:50]:
            lines.append(f"• {a.get('full_name') or '-'}")
    await message.answer("\n".join(lines))


# ---------------- FORMASI YO'Q XODIMLAR ----------------
@router.message(F.text == "👕 Formasi yo'q xodimlar")
async def manager_no_uniform(message: Message):
    user = await ensure_role(message, ROLE_MANAGER, ROLE_ADMIN)
    if not user:
        return
    branch_id = await _manager_branch_id(user)
    if not branch_id:
        await message.answer("Sizga filial biriktirilmagan.")
        return
    profiles = await q.list_employee_profiles(branch_id=branch_id, uniform_status="no")
    profiles += await q.list_employee_profiles(branch_id=branch_id, uniform_status="unknown")
    if not profiles:
        await message.answer("✅ Filialingizda formasi yo'q xodim yo'q.")
        return
    await message.answer(
        f"👕 <b>Formasi yo'q / noma'lum xodimlar</b>\n\nJami: <b>{len(profiles)}</b> ta\nTanlang:",
        reply_markup=kb.employee_profiles_list_kb(profiles[:30], prefix="mgremp"),
    )


# ---------------- FILIAL ARIZALARI ----------------
@router.message(F.text == "📋 Filial arizalari")
async def manager_branch_applications(message: Message):
    user = await ensure_role(message, ROLE_MANAGER, ROLE_ADMIN)
    if not user:
        return
    branch_id = await _manager_branch_id(user)
    if not branch_id:
        await message.answer("Sizga filial biriktirilmagan.")
        return
    apps = await q.filter_applications({"branch_id": branch_id}, limit=30)
    if not apps:
        await message.answer("Filialingizga hali ariza kelmagan.")
        return
    await message.answer(
        f"📋 <b>Filial arizalari</b>\n\nJami: <b>{len(apps)}</b> ta\nTanlang:",
        reply_markup=kb.applications_list_kb(apps, prefix="mgrapp"),
    )


@router.callback_query(F.data.startswith("mgrapp:"))
async def manager_application_view(call: CallbackQuery, bot: Bot):
    user = await q.get_user(call.from_user.id)
    if not user or user["role"] not in (ROLE_MANAGER, ROLE_ADMIN):
        await call.answer("⛔", show_alert=True)
        return
    app = await q.get_application(int(call.data.split(":")[1]))
    if not app:
        await call.answer("Ariza topilmadi.", show_alert=True)
        return
    branch_id = await _manager_branch_id(user)
    if user["role"] != ROLE_ADMIN and app.get("branch_id") != branch_id:
        await call.answer("Bu ariza sizning filialingizga tegishli emas.", show_alert=True)
        return
    await call.message.answer(application_text(app, full=True))
    await send_application_photo(bot, call.message.chat.id, app)
    await send_application_resume(bot, call.message.chat.id, app)
    await call.answer()


# ---------------- HR GA XABAR ----------------
@router.message(F.text == "💬 HR ga xabar")
async def manager_message_start(message: Message, state: FSMContext):
    user = await ensure_role(message, ROLE_MANAGER, ROLE_ADMIN)
    if not user:
        return
    await state.set_state(ManagerMessageForm.text)
    await message.answer("💬 HR ga yubormoqchi bo'lgan xabaringizni yozing:")


@router.message(ManagerMessageForm.text, F.text)
async def manager_message_send(message: Message, state: FSMContext, bot: Bot):
    user = await q.get_user(message.from_user.id)
    await state.clear()
    branch = await q.get_branch(user["branch_id"]) if user and user.get("branch_id") else None
    header = (
        "💬 <b>Filial rahbaridan xabar</b>\n"
        f"👤 {user.get('full_name') if user else '-'}\n"
        f"🏢 Filial: {branch['name'] if branch else '-'}\n"
        "━━━━━━━━━━━━\n"
    )
    await notify_hr_admin(bot, header + message.text.strip())
    await q.add_log(message.from_user.id, message.from_user.full_name, "rahbar_hr_xabar", "")
    await message.answer("✅ Xabaringiz HR ga yuborildi.")


# ---------------- FARMATSEVT ----------------
@router.message(F.text == "💊 Farmatsevt panel")
async def pharmacist_panel(message: Message):
    user = await ensure_role(message, ROLE_PHARMACIST, ROLE_ADMIN)
    if not user:
        return
    profile = await q.get_employee_profile_by_tg(message.from_user.id)
    text = "💊 <b>Farmatsevt paneli</b>"
    if profile:
        text += "\n\n" + employee_profile_text(profile)
    await message.answer(text, reply_markup=kb.pharmacist_menu())


@router.message(F.text == "📊 Mening profilim")
async def pharmacist_profile(message: Message):
    user = await ensure_role(message, ROLE_PHARMACIST, ROLE_ADMIN)
    if not user:
        return
    profile = await q.get_employee_profile_by_tg(message.from_user.id)
    if not profile:
        await message.answer("Profil topilmadi. HR bilan bog'laning.")
        return
    await message.answer(employee_profile_text(profile))


@router.message(F.text == "💸 Jarimalarim")
async def pharmacist_my_fines(message: Message):
    user = await ensure_role(message, ROLE_PHARMACIST, ROLE_ADMIN)
    if not user:
        return
    fines = await q.list_fines(user["id"])
    if not fines:
        await message.answer("Sizda jarimalar yo'q.")
        return
    await message.answer(
        f"💸 <b>Jarimalarim</b>\n\nJami: <b>{len(fines)}</b> ta\n"
        "Batafsil ko'rish uchun jarimani tanlang:",
        reply_markup=kb.fines_list_kb(fines, prefix="myfine"),
    )


@router.callback_query(F.data.startswith("myfine:"))
async def pharmacist_my_fine_view(call: CallbackQuery):
    user = await q.get_user(call.from_user.id)
    fine = await q.get_fine(int(call.data.split(":")[1]))
    if not fine or not user or fine.get("employee_user_id") != user["id"]:
        await call.answer("Jarima topilmadi.", show_alert=True)
        return
    await call.message.answer(fine_text(fine))
    await call.answer()


# ---------------- DIREKTOR ----------------
@router.message(F.text == "📈 Direktor panel")
async def director_panel(message: Message):
    user = await ensure_role(message, ROLE_DIRECTOR, ROLE_ADMIN)
    if not user:
        return
    await message.answer(
        "📈 <b>Direktor paneli</b>\nKerakli statistikani tanlang:",
        reply_markup=kb.director_menu(),
    )


async def _director_branch_id(user):
    """Direktorning filiali. Biriktirilmagan bo'lsa None (barcha filiallar)."""
    if user.get("branch_id"):
        return user["branch_id"]
    profile = await q.get_employee_profile(user["id"])
    return profile.get("branch_id") if profile else None


@router.callback_query(F.data.startswith("diremp:"))
async def director_employee_view(call: CallbackQuery):
    user = await q.get_user(call.from_user.id)
    if not user or user["role"] not in (ROLE_DIRECTOR, ROLE_ADMIN):
        await call.answer("⛔", show_alert=True)
        return
    profile = await q.get_employee_profile(int(call.data.split(":")[1]))
    if not profile:
        await call.answer("Xodim topilmadi.", show_alert=True)
        return
    if user["role"] == ROLE_DIRECTOR:
        branch_id = await _director_branch_id(user)
        if branch_id and profile.get("branch_id") != branch_id:
            await call.answer("Bu xodim sizning filialingizga tegishli emas.", show_alert=True)
            return
    await call.message.answer(
        employee_profile_text(profile),
        reply_markup=kb.staff_fire_kb(profile["user_id"]),
    )
    await call.answer()


# ---------------- ISHDAN BO'SHATISH (rahbar/direktor -> HR) ----------------
@router.callback_query(F.data.startswith("fire:"))
async def fire_start(call: CallbackQuery, state: FSMContext):
    user = await q.get_user(call.from_user.id)
    if not user or user["role"] not in (ROLE_MANAGER, ROLE_DIRECTOR, ROLE_ADMIN):
        await call.answer("⛔", show_alert=True)
        return
    emp_user_id = int(call.data.split(":")[1])
    profile = await q.get_employee_profile(emp_user_id)
    if not profile:
        await call.answer("Xodim topilmadi.", show_alert=True)
        return
    # O'zini bo'shata olmaydi
    if profile.get("user_id") == user["id"]:
        await call.answer("O'zingizni ishdan bo'shata olmaysiz.", show_alert=True)
        return
    # Filial cheklovi (admin uchun cheklov yo'q)
    if user["role"] == ROLE_MANAGER:
        branch_id = await _manager_branch_id(user)
        if branch_id and profile.get("branch_id") != branch_id:
            await call.answer("Bu xodim sizning filialingizga tegishli emas.", show_alert=True)
            return
    elif user["role"] == ROLE_DIRECTOR:
        branch_id = await _director_branch_id(user)
        if branch_id and profile.get("branch_id") != branch_id:
            await call.answer("Bu xodim sizning filialingizga tegishli emas.", show_alert=True)
            return
    await state.set_state(TerminationForm.reason)
    await state.update_data(fire_emp_user_id=emp_user_id)
    await call.message.answer(
        f"🚫 <b>{profile.get('full_name') or 'Xodim'}</b>ni ishdan bo'shatmoqchisiz.\n\n"
        "✍️ Ishdan bo'shatish <b>sababini yozing</b>. Sabab HR bo'limiga tasdiqlash uchun "
        "yuboriladi."
    )
    await call.answer()


@router.message(TerminationForm.reason, F.text)
async def fire_reason(message: Message, state: FSMContext, bot: Bot):
    user = await q.get_user(message.from_user.id)
    data = await state.get_data()
    await state.clear()
    emp_user_id = data.get("fire_emp_user_id")
    profile = await q.get_employee_profile(emp_user_id) if emp_user_id else None
    if not user or not profile:
        await message.answer("⛔ So'rov bekor qilindi (xodim topilmadi).")
        return
    branch_id = profile.get("branch_id")
    rid = await q.add_termination_request({
        "employee_user_id": emp_user_id,
        "requested_by": user["id"],
        "branch_id": branch_id,
        "reason": message.text.strip(),
    })
    await q.add_log(
        message.from_user.id, message.from_user.full_name,
        "ishdan_boshatish_sorovi", f"#{rid} — {profile.get('full_name')}"
    )
    await message.answer(
        "✅ Ishdan bo'shatish so'rovingiz HR bo'limiga yuborildi.\n"
        "HR tasdiqlagach xodim ishdan bo'shatiladi."
    )
    branch = await q.get_branch(branch_id) if branch_id else None
    role_word = "Direktor" if user["role"] == ROLE_DIRECTOR else "Filial rahbari"
    text = (
        "🚫 <b>Ishdan bo'shatish so'rovi!</b>\n"
        "━━━━━━━━━━━━\n"
        f"👤 Xodim: <b>{profile.get('full_name')}</b>\n"
        f"💼 Lavozim: {profile.get('position') or '-'}\n"
        f"🏢 Filial: {branch['name'] if branch else '-'}\n"
        f"🙋 So'rovchi: {user.get('full_name')} ({role_word})\n"
        f"✍️ Sabab: {message.text.strip()}\n\n"
        "Bu xodimni ishdan bo'shatishni tasdiqlaysizmi?"
    )
    await notify_hr_admin(bot, text, reply_markup=kb.termination_actions_kb(rid),
                          kind="termination", ref_id=rid)


@router.message(F.text == "📊 Direktor statistikasi")
async def director_stats(message: Message):
    user = await ensure_role(message, ROLE_DIRECTOR, ROLE_ADMIN)
    if not user:
        return
    s = await q.stats_counts()
    uniform = await q.uniform_stats()
    requests = await q.manager_request_counts()
    vacs = await q.list_vacancies()
    active_vacs = [v for v in vacs if v["is_active"]]
    text = (
        "📊 <b>Direktor statistikasi</b>\n\n"
        f"📥 Bugungi arizalar: <b>{s['today']}</b>\n"
        f"📅 Haftalik arizalar: <b>{s['week']}</b>\n"
        f"✅ Qabul qilinganlar: <b>{s['accepted']}</b>\n"
        f"📋 Jami arizalar: <b>{s['total']}</b>\n\n"
        f"💼 Vakansiyalar: <b>{len(vacs)}</b> (faol: {len(active_vacs)})\n"
        f"👕 Forma: bor {uniform.get('has_uniform') or 0}, "
        f"yo'q {uniform.get('no_uniform') or 0}, "
        f"noma'lum {uniform.get('unknown') or 0}\n"
        f"📨 Rahbar so'rovlari: yangi {requests.get('new', 0)}, "
        f"qabul {requests.get('accepted', 0)}, yopilgan {requests.get('closed', 0)}"
    )
    await message.answer(text)


@router.message(F.text == "👥 Xodimlar statistikasi")
async def director_employee_stats(message: Message):
    user = await ensure_role(message, ROLE_DIRECTOR, ROLE_ADMIN)
    if not user:
        return
    total = await q.count_users()
    hrs = await q.count_users(ROLE_HR)
    managers = await q.count_users(ROLE_MANAGER)
    pharmacists = await q.count_users(ROLE_PHARMACIST)
    employees = await q.count_users(ROLE_EMPLOYEE)
    directors = await q.count_users(ROLE_DIRECTOR)
    profiles = await q.list_employee_profiles()
    role_stats = await q.employee_stats_by_role()
    text = (
        "👥 <b>Xodimlar statistikasi</b>\n\n"
        f"Jami foydalanuvchilar: <b>{total}</b>\n"
        f"👔 Direktorlar: <b>{directors}</b>\n"
        f"🧑‍💼 HR: <b>{hrs}</b>\n"
        f"🏢 Filial rahbarlari: <b>{managers}</b>\n"
        f"💊 Farmatsevtlar: <b>{pharmacists}</b>\n"
        f"👷 Oddiy xodimlar: <b>{employees}</b>\n"
        f"📁 Xodim profillari: <b>{len(profiles)}</b>"
    )
    if role_stats:
        text += "\n\n<b>Profil rollari:</b>\n"
        for row in role_stats:
            text += f"  • {ROLE_NAMES.get(row['role'], row['role'] or 'Noma`lum')}: {row['cnt']}\n"
    await message.answer(text)


@router.message(F.text == "🏢 Filiallar kesimi")
async def director_branch_stats(message: Message):
    user = await ensure_role(message, ROLE_DIRECTOR, ROLE_ADMIN)
    if not user:
        return
    rows = await q.employee_stats_by_branch()
    if not rows:
        await message.answer("🏢 Filiallar bo'yicha xodim statistikasi hali yo'q.")
        return
    text = "🏢 <b>Filiallar kesimi</b>\n\n"
    for row in rows:
        text += (
            f"<b>{row['name']}</b>\n"
            f"  Jami: {row['total']} | Farmatsevt: {row['pharmacists'] or 0} | "
            f"Rahbar: {row['managers'] or 0}\n"
            f"  Forma bor: {row['has_uniform'] or 0} | Forma yo'q: {row['no_uniform'] or 0}\n\n"
        )
    await message.answer(text)


@router.message(F.text == "📥 Arizalar kesimi")
async def director_application_stats(message: Message):
    user = await ensure_role(message, ROLE_DIRECTOR, ROLE_ADMIN)
    if not user:
        return
    counts = await q.application_status_counts()
    branches = await q.stats_by_branch()
    vacancies = await q.stats_by_vacancy()
    text = (
        "📥 <b>Arizalar kesimi</b>\n\n"
        f"🆕 Yangi: <b>{counts.get('new', 0)}</b>\n"
        f"📅 Suhbat: <b>{counts.get('interview', 0)}</b>\n"
        f"✅ Qabul: <b>{counts.get('accepted', 0)}</b>\n"
        f"❌ Rad: <b>{counts.get('rejected', 0)}</b>\n"
    )
    if branches:
        text += "\n<b>Filiallar bo'yicha:</b>\n"
        for row in branches[:10]:
            text += f"  • {row['name'] or 'Nomsiz'}: {row['cnt']}\n"
    if vacancies:
        text += "\n<b>Lavozimlar bo'yicha:</b>\n"
        for row in vacancies[:10]:
            text += f"  • {row['name'] or 'Nomsiz'}: {row['cnt']}\n"
    text += "\nStatus bo'yicha arizalarni ko'rish uchun tanlang:"
    await message.answer(text, reply_markup=kb.director_application_status_kb())


@router.callback_query(F.data.startswith("dirapps:"))
async def director_application_list(call: CallbackQuery):
    user = await q.get_user(call.from_user.id)
    if not user or user["role"] not in (ROLE_DIRECTOR, ROLE_ADMIN):
        await call.answer("⛔", show_alert=True)
        return
    key = call.data.split(":")[1]
    status = None if key == "all" else key
    apps = await q.list_applications(status=status, limit=30)
    if not apps:
        await call.message.answer("Bu bo'limda arizalar yo'q.")
        await call.answer()
        return
    title = "📋 Barcha arizalar" if key == "all" else f"📥 {key}"
    await call.message.answer(
        f"{title}\n\nJami: <b>{len(apps)}</b> ta\n"
        "Batafsil ko'rish uchun arizani tanlang:",
        reply_markup=kb.applications_list_kb(apps, prefix="dirapp"),
    )
    await call.answer()


@router.callback_query(F.data.startswith("dirapp:"))
async def director_application_view(call: CallbackQuery, bot: Bot):
    user = await q.get_user(call.from_user.id)
    if not user or user["role"] not in (ROLE_DIRECTOR, ROLE_ADMIN):
        await call.answer("⛔", show_alert=True)
        return
    app = await q.get_application(int(call.data.split(":")[1]))
    if not app:
        await call.answer("Ariza topilmadi.", show_alert=True)
        return
    await call.message.answer(
        application_text(app, full=True),
        reply_markup=kb.director_app_actions_kb(app["id"]),
    )
    await send_application_photo(bot, call.message.chat.id, app)
    await send_application_resume(bot, call.message.chat.id, app)
    await call.answer()


@router.callback_query(F.data.startswith("dircom:"))
async def director_comment_start(call: CallbackQuery, state: FSMContext):
    user = await q.get_user(call.from_user.id)
    if not user or user["role"] not in (ROLE_DIRECTOR, ROLE_ADMIN):
        await call.answer("⛔", show_alert=True)
        return
    aid = int(call.data.split(":")[1])
    await state.update_data(com_aid=aid)
    await state.set_state(CommentForm.text)
    await call.message.answer("📝 Izohingizni yozing (ichki, HR/Admin ko'radi):")
    await call.answer()


# ---------------- FILIALLAR REYTINGI ----------------
@router.message(F.text == "🏆 Filiallar reytingi")
async def director_branch_ranking(message: Message):
    user = await ensure_role(message, ROLE_DIRECTOR, ROLE_ADMIN)
    if not user:
        return
    rows = await q.branch_ranking()
    if not rows:
        await message.answer("🏆 Reyting uchun hali ma'lumot yo'q.")
        return
    medals = ["🥇", "🥈", "🥉"]
    text = "🏆 <b>Filiallar reytingi</b> (arizalar bo'yicha)\n\n"
    for idx, row in enumerate(rows):
        mark = medals[idx] if idx < len(medals) else f"{idx + 1}."
        text += (
            f"{mark} <b>{row['name']}</b>\n"
            f"    📥 Arizalar: {row['total']} | ✅ Qabul: {row['accepted'] or 0} | "
            f"🆕 Yangi: {row['new_cnt'] or 0}\n"
        )
    await message.answer(text)


# ---------------- DAVRIY TAQQOSLASH ----------------
def _trend(now, prev):
    if now > prev:
        return f"📈 +{now - prev}"
    if now < prev:
        return f"📉 -{prev - now}"
    return "➖ o'zgarishsiz"


@router.message(F.text == "📈 Taqqoslash")
async def director_period_compare(message: Message):
    user = await ensure_role(message, ROLE_DIRECTOR, ROLE_ADMIN)
    if not user:
        return
    p = await q.stats_periods()
    text = (
        "📈 <b>Davriy taqqoslash</b>\n\n"
        "<b>🗓 Hafta (oxirgi 7 kun / oldingi 7 kun)</b>\n"
        f"📥 Arizalar: {p['week_now']} / {p['week_prev']}  {_trend(p['week_now'], p['week_prev'])}\n"
        f"✅ Qabul: {p['week_now_acc']} / {p['week_prev_acc']}  {_trend(p['week_now_acc'], p['week_prev_acc'])}\n\n"
        "<b>📆 Oy (oxirgi 30 kun / oldingi 30 kun)</b>\n"
        f"📥 Arizalar: {p['month_now']} / {p['month_prev']}  {_trend(p['month_now'], p['month_prev'])}\n"
        f"✅ Qabul: {p['month_now_acc']} / {p['month_prev_acc']}  {_trend(p['month_now_acc'], p['month_prev_acc'])}"
    )
    await message.answer(text)


# ---------------- DIREKTOR EXCEL HISOBOT ----------------
@router.message(F.text == "📑 Hisobot (Excel)")
async def director_export(message: Message):
    user = await ensure_role(message, ROLE_DIRECTOR, ROLE_ADMIN)
    if not user:
        return
    await message.answer(
        "📑 <b>Excel hisobot</b>\nQaysi ma'lumotni yuklab olasiz?",
        reply_markup=kb.export_kb("director"),
    )
