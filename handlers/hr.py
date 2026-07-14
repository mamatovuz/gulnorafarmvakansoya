"""HR panel handlerlari."""
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from database import queries as q
from database.db import (
    ROLE_HR, ROLE_ADMIN, ROLE_MANAGER, ROLE_EMPLOYEE, ROLE_PHARMACIST,
    ROLE_DIRECTOR, ROLE_ACCOUNTANT, ROLE_CANDIDATE,
    ST_NEW, ST_INTERVIEW, ST_ACCEPTED, ST_REJECTED, STATUS_LABELS,
)
from states import (
    VacancyForm, InterviewForm, CommentForm, RejectForm, Broadcast, SearchForm,
    SalaryForm, FineForm, ApplicationFilterForm, CandidateMessageForm,
    ProbationForm, TerminationRejectForm,
)
import keyboards as kb
from utils import (
    vacancy_text, application_text, safe_send, broadcast, employee_profile_text,
    fine_text, manager_request_text, send_application_resume,
    post_application_to_channel, parse_date_input, add_days_iso,
    iso_to_display, probation_text,
)
from services import export

router = Router()


async def is_staff(tg_id):
    u = await q.get_user(tg_id)
    return u and u["role"] in (ROLE_HR, ROLE_ADMIN)


async def actor(tg_id):
    return await q.get_user(tg_id)


def role_from_position(position):
    p = (position or "").lower()
    if "filial rahbari" in p:
        return ROLE_MANAGER
    if "farm" in p:
        return ROLE_PHARMACIST
    if "direktor" in p or "director" in p:
        return ROLE_DIRECTOR
    if "buxgalter" in p or "bugalter" in p or "hisobchi" in p:
        return ROLE_ACCOUNTANT
    return ROLE_EMPLOYEE


ROLE_LABELS = {
    ROLE_MANAGER: "Filial rahbari",
    ROLE_PHARMACIST: "Farmatsevt",
    ROLE_DIRECTOR: "Direktor",
    ROLE_ACCOUNTANT: "Buxgalter",
    ROLE_EMPLOYEE: "Xodim",
}

STATUS_TITLES = {
    ST_NEW: "🆕 Yangi arizalar",
    ST_INTERVIEW: "📅 Suhbat bosqichi",
    ST_ACCEPTED: "✅ Qabul qilinganlar",
    ST_REJECTED: "❌ Rad etilganlar",
}

FILTER_LABELS = {
    "position": "lavozim",
    "city": "shahar/viloyat",
    "district": "tuman",
}


async def send_application_results(message, apps, title):
    if not apps:
        await message.answer(f"{title}\n\nHech narsa topilmadi.")
        return
    await message.answer(
        f"{title}\n\n📋 Topildi: <b>{len(apps)}</b> ta\n"
        "Batafsil ko'rish uchun arizani tanlang:",
        reply_markup=kb.applications_list_kb(apps, prefix="appview"),
    )


# ---------------- PANELGA KIRISH ----------------
@router.message(F.text == "👨‍💼 HR panel")
async def hr_panel(message: Message):
    if not await is_staff(message.from_user.id):
        await message.answer("⛔ Sizda ruxsat yo'q.")
        return
    await message.answer(
        "👨‍💼 <b>HR panel</b>\nKerakli bo'limni tanlang:",
        reply_markup=kb.hr_menu(),
    )


# ---------------- DAVOMAT SOZLAMALARI (periodik joylashuv tekshiruvi) ----------------
async def _att_settings_text():
    enabled = str(await q.get_setting("loc_check_enabled", "1")) == "1"
    interval = await q.get_setting("loc_check_interval_hours", "2") or "2"
    status = "🟢 Yoqilgan" if enabled else "🔴 O'chirilgan"
    return (
        "⚙️ <b>Davomat sozlamalari</b>\n"
        "━━━━━━━━━━━━\n"
        "Ish vaqti davomida bot xodimlardan belgilangan oraliqda joylashuv so'rab, "
        "ular haqiqatan ish joyida ekanini tekshiradi.\n\n"
        f"Holat: <b>{status}</b>\n"
        f"So'rov oralig'i: <b>{interval} soatda bir marta</b>\n\n"
        "Quyidan boshqaring:"
    ), enabled, interval


@router.message(F.text == "⚙️ Davomat sozlamalari")
async def att_settings(message: Message):
    if not await is_staff(message.from_user.id):
        await message.answer("⛔ Sizda ruxsat yo'q.")
        return
    text, enabled, interval = await _att_settings_text()
    await message.answer(text, reply_markup=kb.attendance_settings_kb(enabled, interval))


@router.callback_query(F.data == "attset:toggle")
async def att_settings_toggle(call: CallbackQuery):
    if not await is_staff(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    enabled = str(await q.get_setting("loc_check_enabled", "1")) == "1"
    await q.set_setting("loc_check_enabled", "0" if enabled else "1")
    text, en, interval = await _att_settings_text()
    try:
        await call.message.edit_text(text, reply_markup=kb.attendance_settings_kb(en, interval))
    except Exception:
        pass
    await call.answer("Saqlandi ✅")


@router.callback_query(F.data.startswith("attset:int:"))
async def att_settings_interval(call: CallbackQuery):
    if not await is_staff(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    hours = call.data.split(":")[2]
    await q.set_setting("loc_check_interval_hours", hours)
    text, en, interval = await _att_settings_text()
    try:
        await call.message.edit_text(text, reply_markup=kb.attendance_settings_kb(en, interval))
    except Exception:
        pass
    await call.answer(f"{hours} soatda bir marta ✅")


# ---------------- DASHBOARD ----------------
@router.message(F.text == "📊 Dashboard")
async def hr_dashboard(message: Message):
    if not await is_staff(message.from_user.id):
        return
    s = await q.stats_counts()
    uniform = await q.uniform_stats()
    branches = await q.stats_by_branch()
    vacs = await q.stats_by_vacancy()
    text = (
        "📊 <b>HR Dashboard</b>\n\n"
        f"📥 Bugungi arizalar: <b>{s['today']}</b>\n"
        f"📅 Haftalik: <b>{s['week']}</b>\n"
        f"🗓 Oylik: <b>{s['month']}</b>\n\n"
        f"🆕 Yangi: <b>{s['new']}</b>\n"
        f"📅 Suhbatga chaqirilgan: <b>{s['interview']}</b>\n"
        f"✅ Ishga qabul qilingan: <b>{s['accepted']}</b>\n"
        f"❌ Rad etilgan: <b>{s['rejected']}</b>\n"
        f"📋 Jami: <b>{s['total']}</b>\n"
        f"\n👕 <b>Forma:</b> bor {uniform.get('has_uniform') or 0} ta | "
        f"yo'q {uniform.get('no_uniform') or 0} ta | "
        f"noma'lum {uniform.get('unknown') or 0} ta\n"
    )
    if branches:
        text += "\n🏢 <b>Filiallar bo'yicha:</b>\n"
        for b in branches:
            text += f"  • {b['name'] or 'Nomsiz'}: {b['cnt']}\n"
    if vacs:
        text += "\n💼 <b>Vakansiyalar bo'yicha:</b>\n"
        for v in vacs[:10]:
            text += f"  • {v['name'] or 'Nomsiz'}: {v['cnt']}\n"
    await message.answer(text)


# ---------------- ARIZALAR ----------------
@router.message(F.text == "📥 Arizalar")
async def hr_applications(message: Message):
    if not await is_staff(message.from_user.id):
        return
    await message.answer(
        "📥 <b>Arizalar markazi</b>\n\n"
        "Statuslar bo'yicha tez ko'ring, Kanban orqali umumiy holatni kuzating "
        "yoki keng filterdan foydalaning.",
        reply_markup=kb.applications_filter_kb(),
    )


@router.callback_query(F.data.startswith("apps:"))
async def apps_filter(call: CallbackQuery):
    if not await is_staff(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    key = call.data.split(":")[1]
    if key == "kanban":
        counts = await q.application_status_counts()
        text = (
            "🧭 <b>Arizalar Kanban</b>\n\n"
            f"🆕 Yangi: <b>{counts.get(ST_NEW, 0)}</b>\n"
            f"📅 Suhbat: <b>{counts.get(ST_INTERVIEW, 0)}</b>\n"
            f"✅ Qabul: <b>{counts.get(ST_ACCEPTED, 0)}</b>\n"
            f"❌ Rad: <b>{counts.get(ST_REJECTED, 0)}</b>\n\n"
            "Kerakli ustunni oching:"
        )
        await call.message.answer(text, reply_markup=kb.kanban_kb())
        await call.answer()
        return
    if key == "filter":
        branches = await q.list_branches()
        await call.message.answer(
            "🔎 <b>Keng filter</b>\n\n"
            "Arizalarni status, filial, forma, lavozim, shahar yoki tuman bo'yicha ajrating.",
            reply_markup=kb.application_advanced_filter_kb(branches),
        )
        await call.answer()
        return
    status = None if key == "all" else key
    apps = await q.list_applications(status=status, limit=30)
    await call.answer()
    title = "📋 <b>Barcha arizalar</b>" if key == "all" else f"{STATUS_TITLES.get(status, status)}"
    await send_application_results(call.message, apps, title)


@router.callback_query(F.data.startswith("fltstatus:"))
async def app_filter_status(call: CallbackQuery):
    if not await is_staff(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    status = call.data.split(":")[1]
    apps = await q.filter_applications({"status": status})
    await send_application_results(call.message, apps, f"🔎 <b>Filter:</b> {STATUS_TITLES.get(status, status)}")
    await call.answer()


@router.callback_query(F.data.startswith("fltuniform:"))
async def app_filter_uniform(call: CallbackQuery):
    if not await is_staff(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    status = call.data.split(":")[1]
    labels = {"yes": "forma bor", "no": "forma yo'q", "unknown": "forma noma'lum"}
    apps = await q.filter_applications({"uniform_status": status})
    await send_application_results(call.message, apps, f"🔎 <b>Filter:</b> {labels.get(status, status)}")
    await call.answer()


@router.callback_query(F.data.startswith("fltbr:"))
async def app_filter_branch(call: CallbackQuery):
    if not await is_staff(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    bid = int(call.data.split(":")[1])
    branch = await q.get_branch(bid)
    apps = await q.filter_applications({"branch_id": bid})
    await send_application_results(
        call.message,
        apps,
        f"🔎 <b>Filter:</b> filial - {branch['name'] if branch else bid}",
    )
    await call.answer()


@router.callback_query(F.data.startswith("flttxt:"))
async def app_filter_text_start(call: CallbackQuery, state: FSMContext):
    if not await is_staff(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    field = call.data.split(":")[1]
    await state.update_data(app_filter_field=field)
    await state.set_state(ApplicationFilterForm.query)
    await call.message.answer(f"🔎 {FILTER_LABELS.get(field, field)} bo'yicha qidiruv so'zini yozing:")
    await call.answer()


@router.message(ApplicationFilterForm.query, F.text)
async def app_filter_text_finish(message: Message, state: FSMContext):
    data = await state.get_data()
    await state.clear()
    field = data.get("app_filter_field")
    if field not in FILTER_LABELS:
        await message.answer("Filter sessiyasi tugagan. Qaytadan urinib ko'ring.")
        return
    apps = await q.filter_applications({field: message.text.strip()})
    await send_application_results(
        message,
        apps,
        f"🔎 <b>Filter:</b> {FILTER_LABELS[field]} - {message.text.strip()}",
    )


@router.callback_query(F.data.startswith("appview:"))
async def app_view(call: CallbackQuery, bot: Bot):
    aid = int(call.data.split(":")[1])
    a = await q.get_application(aid)
    if not a:
        await call.answer("Topilmadi.", show_alert=True)
        return
    await call.message.answer(
        application_text(a, full=True),
        reply_markup=kb.application_actions_kb(aid, favorite=bool(a.get("favorite"))),
    )
    await send_application_resume(bot, call.message.chat.id, a)
    await call.answer()


# ------- Ishga qabul (sinov muddati bilan) -------
@router.callback_query(F.data.startswith("appacc:"))
async def app_accept(call: CallbackQuery, state: FSMContext):
    if not await is_staff(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    aid = int(call.data.split(":")[1])
    a = await q.get_application(aid)
    if not a:
        await call.answer("Ariza topilmadi.", show_alert=True)
        return
    await state.set_state(ProbationForm.branch)
    await state.update_data(prob_aid=aid, prob_suggest_branch=a.get("branch_id"))
    branches = await q.list_branches()
    hint = f"\n\nArizada ko'rsatilgan filial: <b>{a.get('branch_name') or '—'}</b>"
    await call.message.answer(
        f"✅ <b>Ishga qabul — sinov muddati</b>\n\n"
        f"👤 {a.get('full_name')} · {a.get('position') or a.get('vacancy_title')}\n"
        f"Xodim <b>qaysi filialga</b> chiqadi? Tanlang:{hint}",
        reply_markup=kb.branch_pick_kb(branches, prefix="probr"),
    )
    await call.answer()


@router.callback_query(ProbationForm.branch, F.data.startswith("probr:"))
async def app_accept_branch(call: CallbackQuery, state: FSMContext):
    if not await is_staff(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    bid = int(call.data.split(":")[1]) or None
    data = await state.get_data()
    if not bid:
        bid = data.get("prob_suggest_branch")
    await state.update_data(prob_branch_id=bid)
    await state.set_state(ProbationForm.start_date)
    await call.message.answer(
        "📅 Sinov muddati <b>qaysi kundan</b> boshlanadi?\n\n"
        "Sanani <b>kun.oy.yil</b> ko'rinishida yuboring (masalan: <b>15.07.2026</b>) "
        "yoki <b>bugun</b> / <b>ertaga</b> deb yozing.\n"
        "ℹ️ Sinov muddati 15 kun davom etadi."
    )
    await call.answer()


@router.message(ProbationForm.start_date, F.text)
async def app_accept_start_date(message: Message, state: FSMContext, bot: Bot):
    if not await is_staff(message.from_user.id):
        await state.clear()
        return
    parsed = parse_date_input(message.text)
    if not parsed:
        await message.answer(
            "❗️ Sana noto'g'ri. <b>kun.oy.yil</b> ko'rinishida yuboring "
            "(masalan: 15.07.2026) yoki <b>bugun</b> deb yozing."
        )
        return
    start_iso, start_disp = parsed
    data = await state.get_data()
    aid = data.get("prob_aid")
    branch_id = data.get("prob_branch_id")
    await state.clear()
    me = await actor(message.from_user.id)
    await _finalize_accept(bot, message, me, aid, branch_id, start_iso)


async def _finalize_accept(bot: Bot, message: Message, me, aid, branch_id, start_iso):
    """Arizani qabul qiladi, sinov muddatini yaratadi va xabarlarni yuboradi."""
    await q.set_application_status(aid, ST_ACCEPTED, handled_by=me["id"])
    a = await q.get_application(aid)
    if not a:
        await message.answer("Ariza topilmadi.")
        return
    if branch_id is None:
        branch_id = a.get("branch_id")
    new_role = role_from_position(a.get("position") or a.get("vacancy_title"))
    if a.get("applicant_tg"):
        await q.set_role(a["applicant_tg"], new_role, branch_id)
    await q.upsert_employee_profile(
        user_id=a["user_id"],
        application_id=aid,
        role=new_role,
        position=a.get("position") or a.get("vacancy_title"),
        branch_id=branch_id,
        uniform_status=a.get("uniform_status") or "unknown",
    )

    # Sinov muddati (15 kun)
    end_iso = add_days_iso(start_iso, 14)
    pid = await q.add_probation({
        "application_id": aid,
        "user_id": a["user_id"],
        "branch_id": branch_id,
        "full_name": a.get("full_name"),
        "position": a.get("position") or a.get("vacancy_title"),
        "start_date": start_iso,
        "end_date": end_iso,
        "days": 15,
        "created_by": me["id"],
    })
    await q.add_log(
        message.from_user.id, me["full_name"], "ariza_qabul",
        f"Ariza #{aid} · sinov #{pid}"
    )
    # Kadrlar harakati (IT hisoboti): ishga kirdi
    await q.add_hr_event(
        "hired", user_id=a["user_id"], full_name=a.get("full_name"),
        branch_id=branch_id, details=f"ariza #{aid}", created_by=me["id"],
    )

    branch = await q.get_branch(branch_id) if branch_id else None
    branch_name = branch["name"] if branch else "—"
    await message.answer(
        f"✅ Ariza #{aid} — <b>ishga qabul qilindi</b>.\n"
        f"🎯 Rol: <b>{ROLE_LABELS.get(new_role, new_role)}</b>\n"
        f"🏢 Filial: <b>{branch_name}</b>\n"
        f"🧪 Sinov muddati: <b>{iso_to_display(start_iso)} — {iso_to_display(end_iso)}</b> (15 kun)"
    )

    # Filial rahbariga xabar
    manager_ids = await q.branch_manager_tg_ids(branch_id)
    mgr_text = (
        "🧪 <b>Yangi xodim sinov muddatiga chiqadi</b>\n\n"
        f"👤 <b>{a.get('full_name')}</b>\n"
        f"💼 Lavozim: {a.get('position') or a.get('vacancy_title')}\n"
        f"🏢 Filial: {branch_name}\n"
        f"📅 Ishga chiqadi: <b>{iso_to_display(start_iso)}</b>\n"
        f"🏁 Sinov tugashi: {iso_to_display(end_iso)} (15 kun)\n"
        f"📱 Telefon: {a.get('phone') or '-'}\n\n"
        "Iltimos, shu kuni xodimni kutib oling."
    )
    for tid in manager_ids:
        await safe_send(bot, tid, mgr_text)
    if not manager_ids:
        await message.answer(
            "ℹ️ Bu filialga rahbar biriktirilmagani uchun xabar yuborilmadi."
        )

    # Maxfiy kanalga yuborish (admin panelda ulangan bo'lsa)
    secret_channel = await q.get_setting("secret_channel")
    if secret_channel:
        posted = await post_application_to_channel(
            bot, secret_channel, a,
            header=(
                f"✅ <b>Ishga qabul qilingan ariza</b>\n"
                f"👔 Qabul qildi: {me['full_name']}\n"
                f"🎯 Rol: {ROLE_LABELS.get(new_role, new_role)}\n"
                f"🧪 Sinov: {iso_to_display(start_iso)} — {iso_to_display(end_iso)}"
            ),
        )
        if not posted:
            await message.answer(
                "⚠️ Ariza maxfiy kanalga yuborilmadi. Bot kanalda administrator "
                "ekanini va kanal ID to'g'ri ulanganini tekshiring (⚙️ Sozlamalar)."
            )

    # Nomzodga xabar
    if a.get("applicant_tg"):
        await safe_send(
            bot, a["applicant_tg"],
            f"🎉 <b>Tabriklaymiz!</b>\n\n"
            f"«{a['vacancy_title']}» bo'yicha arizangiz ma'qullandi va siz "
            f"<b>ishga qabul qilindingiz</b>!\n"
            f"🏢 Filial: <b>{branch_name}</b>\n"
            f"📅 Ishga chiqasiz: <b>{iso_to_display(start_iso)}</b>\n"
            f"🧪 Sinov muddati: 15 kun ({iso_to_display(start_iso)} — {iso_to_display(end_iso)})\n"
            f"Sizga <b>{ROLE_LABELS.get(new_role, new_role)}</b> paneli ochildi.\n"
            f"Yangilangan menyuni ko'rish uchun /start bosing.",
            reply_markup=kb.main_menu(new_role),
        )


# ------- Sinov muddati paneli -------
@router.message(F.text == "🧪 Sinov muddati")
async def probation_panel(message: Message):
    if not await is_staff(message.from_user.id):
        return
    active = await q.list_active_probations()
    finished = await q.list_probations(status="finished", limit=10)
    if not active and not finished:
        await message.answer(
            "🧪 Hozircha sinov muddatidagi xodimlar yo'q.\n"
            "Ariza qabul qilinganda sinov muddati avtomatik ochiladi."
        )
        return
    if active:
        await message.answer(
            f"🧪 <b>Sinov muddatidagilar</b> (faol: {len(active)} ta)\n"
            "Batafsil va statistikani ko'rish uchun tanlang:",
            reply_markup=kb.probations_list_kb(active),
        )
    if finished:
        await message.answer(
            "🏁 <b>Yaqinda tugaganlar</b>:",
            reply_markup=kb.probations_list_kb(finished),
        )


@router.callback_query(F.data.startswith("probview:"))
async def probation_view(call: CallbackQuery):
    if not await is_staff(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    pid = int(call.data.split(":")[1])
    p = await q.get_probation(pid)
    if not p:
        await call.answer("Topilmadi.", show_alert=True)
        return
    stats = await q.probation_attendance_stats(
        p["user_id"], p.get("start_date"), p.get("end_date")
    )
    await call.message.answer(probation_text(p, stats=stats))
    await call.answer()


# ------- Rad etish -------
@router.callback_query(F.data.startswith("apprej:"))
async def app_reject_start(call: CallbackQuery, state: FSMContext):
    if not await is_staff(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    aid = int(call.data.split(":")[1])
    await state.update_data(reject_aid=aid)
    await state.set_state(RejectForm.reason)
    await call.message.answer(
        "❌ Rad etish sababini yozing (nomzodga yuboriladi). "
        "Sababsiz bo'lsa «-» deb yozing:"
    )
    await call.answer()


@router.message(RejectForm.reason, F.text)
async def app_reject_finish(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    aid = data.get("reject_aid")
    await state.clear()
    me = await actor(message.from_user.id)
    reason = message.text.strip()
    await q.set_application_status(aid, ST_REJECTED, handled_by=me["id"])
    if reason and reason != "-":
        await q.set_application_comment(aid, reason)
    a = await q.get_application(aid)
    await q.add_log(message.from_user.id, me["full_name"], "ariza_rad", f"Ariza #{aid}")
    await message.answer(f"❌ Ariza #{aid} — <b>rad etildi</b>.")
    if a.get("applicant_tg"):
        extra = f"\n\nSabab: {reason}" if reason and reason != "-" else ""
        await safe_send(
            bot, a["applicant_tg"],
            f"😔 «{a['vacancy_title']}» vakansiyasi bo'yicha arizangiz "
            f"bu safar ma'qullanmadi.{extra}\n\n"
            f"Boshqa vakansiyalarga ariza topshirishingiz mumkin. Omad tilaymiz!",
        )


# ------- Izoh qoldirish -------
@router.callback_query(F.data.startswith("appcom:"))
async def app_comment_start(call: CallbackQuery, state: FSMContext):
    if not await is_staff(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    aid = int(call.data.split(":")[1])
    await state.update_data(com_aid=aid)
    await state.set_state(CommentForm.text)
    await call.message.answer("📝 Izohingizni yozing (ichki, faqat HR ko'radi):")
    await call.answer()


@router.message(CommentForm.text, F.text)
async def app_comment_finish(message: Message, state: FSMContext):
    data = await state.get_data()
    aid = data.get("com_aid")
    await state.clear()
    await q.set_application_comment(aid, message.text.strip())
    me = await actor(message.from_user.id)
    await q.add_log(message.from_user.id, me["full_name"], "ariza_izoh", f"Ariza #{aid}")
    await message.answer(f"✅ Izoh saqlandi (Ariza #{aid}).")


# ---------------- FORMA NAZORATI ----------------
@router.message(F.text == "👕 Forma nazorati")
async def hr_uniform(message: Message):
    if not await is_staff(message.from_user.id):
        return
    s = await q.uniform_stats()
    text = (
        "👕 <b>Forma nazorati</b>\n\n"
        f"👥 Jami profil: <b>{s.get('total') or 0}</b>\n"
        f"✅ Formasi bor: <b>{s.get('has_uniform') or 0}</b>\n"
        f"❌ Formasi yo'q: <b>{s.get('no_uniform') or 0}</b>\n"
        f"➖ Noma'lum: <b>{s.get('unknown') or 0}</b>"
    )
    await message.answer(text)
    profiles = await q.list_employee_profiles(uniform_status="no")
    profiles += await q.list_employee_profiles(uniform_status="unknown")
    if not profiles:
        await message.answer("Forma bo'yicha muammo yo'q.")
        return
    await message.answer(
        "Forma kerak yoki noma'lum bo'lgan xodimlar:\n"
        "Batafsil ko'rish uchun xodimni tanlang:",
        reply_markup=kb.employee_profiles_list_kb(profiles[:30], prefix="empview"),
    )


@router.callback_query(F.data.startswith("empview:"))
async def employee_profile_view(call: CallbackQuery):
    if not await is_staff(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    uid = int(call.data.split(":")[1])
    profile = await q.get_employee_profile(uid)
    if not profile:
        await call.answer("Xodim topilmadi.", show_alert=True)
        return
    await call.message.answer(
        employee_profile_text(profile),
        reply_markup=kb.uniform_employee_kb(uid, profile.get("uniform_status")),
    )
    await call.answer()


@router.callback_query(F.data.startswith("ufset:"))
async def uniform_set(call: CallbackQuery, bot: Bot):
    if not await is_staff(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    _, uid, status = call.data.split(":")
    uid = int(uid)
    await q.update_uniform_status(uid, status)
    profile = await q.get_employee_profile(uid)
    me = await actor(call.from_user.id)
    await q.add_log(call.from_user.id, me["full_name"], "forma_yangilandi", f"{uid} -> {status}")
    await call.answer("Forma holati yangilandi ✅")
    if profile:
        status_text = "bor" if status == "yes" else "yo'q"
        await call.message.answer("✅ Yangilandi:\n\n" + employee_profile_text(profile))
        await safe_send(
            bot, profile["tg_id"],
            f"👕 Forma holatingiz yangilandi: <b>{status_text}</b>."
        )


# ---------------- FARMATSEVTLAR: OYLIK VA JARIMA ----------------
@router.message(F.text == "💊 Farmatsevtlar")
async def hr_pharmacists(message: Message):
    if not await is_staff(message.from_user.id):
        return
    profiles = await q.list_employee_profiles(role=ROLE_PHARMACIST)
    if not profiles:
        await message.answer("Hali farmatsevt profillari yo'q.")
        return
    await message.answer(
        f"💊 <b>Farmatsevtlar</b>\n\nJami: <b>{len(profiles)}</b> ta\n"
        "Boshqarish uchun farmatsevtni tanlang:",
        reply_markup=kb.employee_profiles_list_kb(profiles, prefix="phview"),
    )


@router.callback_query(F.data.startswith("phview:"))
async def pharmacist_view(call: CallbackQuery):
    if not await is_staff(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    uid = int(call.data.split(":")[1])
    profile = await q.get_employee_profile(uid)
    if not profile:
        await call.answer("Farmatsevt topilmadi.", show_alert=True)
        return
    await call.message.answer(
        employee_profile_text(profile),
        reply_markup=kb.pharmacist_manage_kb(uid, profile.get("uniform_status")),
    )
    await call.answer()


@router.callback_query(F.data.startswith("phsal:"))
async def salary_start(call: CallbackQuery, state: FSMContext):
    if not await is_staff(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    uid = int(call.data.split(":")[1])
    await state.update_data(salary_user_id=uid)
    await state.set_state(SalaryForm.value)
    await call.message.answer("💰 Oylik summasini kiriting. Masalan: <b>4 500 000 so'm</b>")
    await call.answer()


@router.message(SalaryForm.value, F.text)
async def salary_save(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    uid = data.get("salary_user_id")
    await state.clear()
    await q.update_monthly_salary(uid, message.text.strip())
    profile = await q.get_employee_profile(uid)
    me = await actor(message.from_user.id)
    await q.add_log(message.from_user.id, me["full_name"], "oylik_belgilandi", f"{uid}: {message.text.strip()}")
    await message.answer("✅ Oylik saqlandi.\n\n" + employee_profile_text(profile))
    await safe_send(
        bot, profile["tg_id"],
        f"💰 Sizning oyligingiz belgilandi: <b>{message.text.strip()}</b>."
    )


@router.callback_query(F.data.startswith("phfine:"))
async def fine_start(call: CallbackQuery, state: FSMContext):
    if not await is_staff(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    uid = int(call.data.split(":")[1])
    await state.update_data(fine_user_id=uid)
    await state.set_state(FineForm.amount)
    await call.message.answer("💸 Jarima summasini kiriting. Masalan: <b>100 000 so'm</b>")
    await call.answer()


@router.message(FineForm.amount, F.text)
async def fine_amount(message: Message, state: FSMContext):
    await state.update_data(fine_amount=message.text.strip())
    await state.set_state(FineForm.reason)
    await message.answer("✍️ Jarima sababini yozing:")


@router.message(FineForm.reason, F.text)
async def fine_save(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    uid = data.get("fine_user_id")
    amount = data.get("fine_amount")
    reason = message.text.strip()
    await state.clear()
    me = await actor(message.from_user.id)
    fid = await q.add_fine(uid, amount, reason, me["id"])
    profile = await q.get_employee_profile(uid)
    await q.add_log(message.from_user.id, me["full_name"], "jarima_yozildi", f"{uid}: {amount}")
    await message.answer(f"✅ Jarima saqlandi (#{fid}).")
    await safe_send(
        bot, profile["tg_id"],
        f"💸 Sizga jarima yozildi.\n\n💰 Summa: <b>{amount}</b>\n✍️ Sabab: {reason}"
    )


@router.callback_query(F.data.startswith("phfines:"))
async def pharmacist_fines(call: CallbackQuery):
    if not await is_staff(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    uid = int(call.data.split(":")[1])
    fines = await q.list_fines(uid)
    await call.answer()
    if not fines:
        await call.message.answer("Bu farmatsevtga jarima yozilmagan.")
        return
    await call.message.answer(
        f"💸 <b>Jarimalar</b>\n\nJami: <b>{len(fines)}</b> ta\n"
        "Batafsil ko'rish uchun jarimani tanlang:",
        reply_markup=kb.fines_list_kb(fines, prefix="fineview"),
    )


@router.callback_query(F.data.startswith("fineview:"))
async def fine_view(call: CallbackQuery):
    if not await is_staff(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    fid = int(call.data.split(":")[1])
    fine = await q.get_fine(fid)
    if not fine:
        await call.answer("Jarima topilmadi.", show_alert=True)
        return
    await call.message.answer(fine_text(fine))
    await call.answer()


# ---------------- FILIAL RAHBARI SO'ROVLARI ----------------
@router.message(F.text == "📨 Rahbar so'rovlari")
async def manager_requests(message: Message):
    if not await is_staff(message.from_user.id):
        return
    reqs = await q.list_manager_requests(status="new", limit=30)
    title = "📨 <b>Yangi so'rovlar</b>"
    if not reqs:
        reqs = await q.list_manager_requests(limit=10)
        if not reqs:
            await message.answer("Rahbarlardan hali so'rov kelmagan.")
            return
        title = "📨 <b>Oxirgi so'rovlar</b>"
    await message.answer(
        f"{title}\n\nJami: <b>{len(reqs)}</b> ta\n"
        "Batafsil ko'rish uchun so'rovni tanlang:",
        reply_markup=kb.manager_requests_list_kb(reqs, prefix="mrview"),
    )


@router.callback_query(F.data.startswith("mrview:"))
async def manager_request_view(call: CallbackQuery):
    if not await is_staff(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    rid = int(call.data.split(":")[1])
    req = await q.get_manager_request(rid)
    if not req:
        await call.answer("So'rov topilmadi.", show_alert=True)
        return
    markup = kb.manager_request_actions_kb(req["id"], req["kind"]) if req["status"] == "new" else None
    await call.message.answer(manager_request_text(req), reply_markup=markup)
    await call.answer()


@router.callback_query(F.data.startswith("mracc:"))
async def manager_request_accept(call: CallbackQuery, bot: Bot):
    if not await is_staff(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    rid = int(call.data.split(":")[1])
    req = await q.get_manager_request(rid)
    if not req:
        await call.answer("So'rov topilmadi.", show_alert=True)
        return
    me = await actor(call.from_user.id)
    extra = ""
    if req["kind"] == "vacancy":
        vid = await q.add_vacancy(
            {
                "title": req.get("title") or "Yangi xodim",
                "branch_id": req.get("branch_id"),
                "job_type": "Filial rahbari so'rovi",
                "shift": "Kelishiladi",
                "salary": "Kelishiladi",
                "work_time": "Kelishiladi",
                "requirements": (
                    f"Kerakli soni: {req.get('staff_count') or '-'}\n"
                    f"{req.get('details') or '-'}"
                ),
                "responsibilities": "HR suhbatida aniqlanadi.",
                "conditions": f"Rahbar so'rovi #{rid} asosida ochildi.",
                "is_active": True,
            },
            created_by=me["id"],
        )
        extra = f"\n💼 Vakansiya ochildi: #{vid}"
    await q.set_manager_request_status(rid, "accepted", handled_by=me["id"])
    await q.add_log(call.from_user.id, me["full_name"], "rahbar_sorovi_qabul", f"#{rid}")
    await call.message.answer(f"✅ So'rov #{rid} qabul qilindi.{extra}")
    await safe_send(
        bot, req["manager_tg"],
        f"✅ Siz yuborgan so'rov #{rid} HR tomonidan qabul qilindi.{extra}"
    )
    await call.answer("Qabul qilindi ✅")


@router.callback_query(F.data.startswith("mrclose:"))
async def manager_request_close(call: CallbackQuery, bot: Bot):
    if not await is_staff(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    rid = int(call.data.split(":")[1])
    req = await q.get_manager_request(rid)
    if not req:
        await call.answer("So'rov topilmadi.", show_alert=True)
        return
    me = await actor(call.from_user.id)
    await q.set_manager_request_status(rid, "closed", handled_by=me["id"])
    await q.add_log(call.from_user.id, me["full_name"], "rahbar_sorovi_yopildi", f"#{rid}")
    await call.message.answer(f"❌ So'rov #{rid} yopildi.")
    await safe_send(bot, req["manager_tg"], f"❌ Siz yuborgan so'rov #{rid} yopildi.")
    await call.answer("Yopildi")


# ------- Ishdan bo'shatish so'rovi (rahbar/direktor -> HR) -------
@router.callback_query(F.data.startswith("tacc:"))
async def termination_accept(call: CallbackQuery, bot: Bot):
    if not await is_staff(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    rid = int(call.data.split(":")[1])
    req = await q.get_termination_request(rid)
    if not req:
        await call.answer("So'rov topilmadi.", show_alert=True)
        return
    if req.get("status") != "new":
        await call.answer("Bu so'rov allaqachon ko'rib chiqilgan.", show_alert=True)
        return
    me = await actor(call.from_user.id)
    await q.set_termination_request_status(rid, "approved", handled_by=me["id"])
    # Kadrlar harakati (IT hisoboti): ishdan ketdi — profil o'chishidan oldin yozamiz
    await q.add_hr_event(
        "left", user_id=req["employee_user_id"], full_name=req.get("employee_name"),
        branch_id=req.get("branch_id"), details=f"so'rov #{rid}", created_by=me["id"],
    )
    # Xodimni ishdan bo'shatamiz (profil o'chadi, rol nomzodga qaytadi)
    await q.fire_employee(req["employee_user_id"])
    await q.add_log(
        call.from_user.id, me["full_name"], "ishdan_boshatish_tasdiq",
        f"#{rid} — {req.get('employee_name')}"
    )
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await call.message.answer(
        f"✅ Ishdan bo'shatish so'rovi #{rid} tasdiqlandi.\n"
        f"👤 {req.get('employee_name')} ishdan bo'shatildi."
    )
    await call.answer("Tasdiqlandi ✅")

    # Ishdan bo'shatilgan xodimga xabar (staj + sabab)
    since_phrase = req.get("employee_since") or "ishlagan davringiz davomida"
    await safe_send(
        bot, req["employee_tg"],
        f"😔 Hurmatli {req.get('employee_name')}!\n\n"
        f"Siz Gulnora Farmda <b>{since_phrase}</b> ishlaganingizdan mamnunmiz.\n"
        "Afsuski, siz quyidagi sabab bilan ishdan bo'shatildingiz:\n"
        f"✍️ <b>Sabab:</b> {req.get('reason') or '-'}\n\n"
        "Ko'rsatgan mehnatingiz uchun rahmat! 🙏",
        reply_markup=kb.main_menu(ROLE_CANDIDATE),
    )
    # So'rovchiga (rahbar/direktor) tasdiq haqida xabar
    await safe_send(
        bot, req["requester_tg"],
        f"✅ Siz yuborgan ishdan bo'shatish so'rovi (#{rid}) HR tomonidan tasdiqlandi.\n"
        f"👤 {req.get('employee_name')} ishdan bo'shatildi."
    )


@router.callback_query(F.data.startswith("trej:"))
async def termination_reject_start(call: CallbackQuery, state: FSMContext):
    if not await is_staff(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    rid = int(call.data.split(":")[1])
    req = await q.get_termination_request(rid)
    if not req:
        await call.answer("So'rov topilmadi.", show_alert=True)
        return
    if req.get("status") != "new":
        await call.answer("Bu so'rov allaqachon ko'rib chiqilgan.", show_alert=True)
        return
    await state.set_state(TerminationRejectForm.reason)
    await state.update_data(trej_rid=rid)
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await call.message.answer(
        "❌ Ishdan bo'shatish so'rovini <b>rad etyapsiz</b>.\n"
        "✍️ Rad etish sababini yozing (rahbarga yuboriladi):"
    )
    await call.answer()


@router.message(TerminationRejectForm.reason, F.text)
async def termination_reject_reason(message: Message, state: FSMContext, bot: Bot):
    if not await is_staff(message.from_user.id):
        await state.clear()
        return
    data = await state.get_data()
    await state.clear()
    rid = data.get("trej_rid")
    req = await q.get_termination_request(rid) if rid else None
    if not req:
        await message.answer("So'rov topilmadi.")
        return
    if req.get("status") != "new":
        await message.answer("Bu so'rov allaqachon ko'rib chiqilgan.")
        return
    me = await actor(message.from_user.id)
    reason = message.text.strip()
    await q.set_termination_request_status(rid, "rejected", handled_by=me["id"], comment=reason)
    await q.add_log(
        message.from_user.id, me["full_name"], "ishdan_boshatish_rad",
        f"#{rid} — {req.get('employee_name')}"
    )
    await message.answer(f"❌ Ishdan bo'shatish so'rovi #{rid} rad etildi.")
    await safe_send(
        bot, req["requester_tg"],
        f"❌ Siz yuborgan ishdan bo'shatish so'rovingiz (#{rid}) rad etildi.\n"
        f"👤 Xodim: {req.get('employee_name')}\n"
        f"✍️ <b>HR sababi:</b> {reason}"
    )


# ------- Suhbatga chaqirish -------
@router.callback_query(F.data.startswith("appint:"))
async def interview_start(call: CallbackQuery, state: FSMContext):
    if not await is_staff(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    aid = int(call.data.split(":")[1])
    await state.update_data(int_aid=aid)
    await state.set_state(InterviewForm.date)
    await call.message.answer("📅 Suhbat sanasini kiriting (masalan: 10.07.2026):")
    await call.answer()


@router.message(InterviewForm.date, F.text)
async def interview_date(message: Message, state: FSMContext):
    await state.update_data(int_date=message.text.strip())
    await state.set_state(InterviewForm.time)
    await message.answer("🕐 Vaqtni kiriting (masalan: 14:00):")


@router.message(InterviewForm.time, F.text)
async def interview_time(message: Message, state: FSMContext):
    await state.update_data(int_time=message.text.strip())
    await state.set_state(InterviewForm.location)
    await message.answer("📍 Manzilni kiriting:")


@router.message(InterviewForm.location, F.text)
async def interview_loc(message: Message, state: FSMContext):
    await state.update_data(int_loc=message.text.strip())
    await state.set_state(InterviewForm.comment)
    await message.answer("💬 Qo'shimcha izoh (yoki «-»):")


@router.message(InterviewForm.comment, F.text)
async def interview_finish(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    aid = data["int_aid"]
    me = await actor(message.from_user.id)
    comment = message.text.strip()
    iid = await q.add_interview(
        aid, data["int_date"], data["int_time"], data["int_loc"],
        comment, created_by=me["id"],
    )
    await q.set_application_status(aid, ST_INTERVIEW, handled_by=me["id"])
    await state.clear()
    a = await q.get_application(aid)
    await q.add_log(message.from_user.id, me["full_name"], "suhbat_belgilandi", f"Ariza #{aid}")
    await message.answer(f"✅ Suhbat belgilandi va nomzodga yuborildi (Ariza #{aid}).")

    if a.get("applicant_tg"):
        extra = f"\n💬 Izoh: {comment}" if comment and comment != "-" else ""
        await safe_send(
            bot, a["applicant_tg"],
            f"📅 <b>Sizni suhbatga taklif qilamiz!</b>\n\n"
            f"💼 Vakansiya: {a['vacancy_title']}\n"
            f"📆 Sana: {data['int_date']}\n"
            f"🕐 Vaqt: {data['int_time']}\n"
            f"📍 Manzil: {data['int_loc']}{extra}\n\n"
            f"Iltimos, tasdiqlang yoki boshqa vaqt taklif qiling:",
            reply_markup=kb.confirm_interview_kb(iid),
        )


# ---------------- VAKANSIYALAR (HR) ----------------
@router.message(F.text == "💼 Vakansiyalar (HR)")
async def hr_vacancies(message: Message):
    if not await is_staff(message.from_user.id):
        return
    await message.answer(
        "💼 <b>Vakansiyalarni boshqarish</b>",
        reply_markup=kb.hr_vacancies_kb(),
    )


@router.callback_query(F.data == "hrvac_list")
async def hr_vac_list(call: CallbackQuery):
    if not await is_staff(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    vacs = await q.list_vacancies(active_only=False)
    await call.answer()
    if not vacs:
        await call.message.answer("Hali vakansiyalar yo'q. ➕ tugmasidan yarating.")
        return
    await call.message.answer(
        f"💼 <b>Vakansiyalar</b>\n\nJami: <b>{len(vacs)}</b> ta\n"
        "Boshqarish uchun vakansiyani tanlang:",
        reply_markup=kb.vacancies_manage_list_kb(vacs),
    )


@router.callback_query(F.data.startswith("vman:"))
async def vac_manage(call: CallbackQuery):
    vid = int(call.data.split(":")[1])
    v = await q.get_vacancy(vid)
    if not v:
        await call.answer("Topilmadi.", show_alert=True)
        return
    await call.message.edit_text(
        vacancy_text(v), reply_markup=kb.vacancy_manage_kb(vid, v["is_active"])
    )
    await call.answer()


@router.callback_query(F.data.startswith("vclose:"))
async def vac_close(call: CallbackQuery):
    vid = int(call.data.split(":")[1])
    await q.update_vacancy_field(vid, "is_active", 0)
    me = await actor(call.from_user.id)
    await q.add_log(call.from_user.id, me["full_name"], "vakansiya_yopildi", f"#{vid}")
    v = await q.get_vacancy(vid)
    await call.message.edit_text(vacancy_text(v), reply_markup=kb.vacancy_manage_kb(vid, 0))
    await call.answer("Vakansiya yopildi ❌")


@router.callback_query(F.data.startswith("vopen:"))
async def vac_open(call: CallbackQuery):
    vid = int(call.data.split(":")[1])
    await q.update_vacancy_field(vid, "is_active", 1)
    me = await actor(call.from_user.id)
    await q.add_log(call.from_user.id, me["full_name"], "vakansiya_ochildi", f"#{vid}")
    v = await q.get_vacancy(vid)
    await call.message.edit_text(vacancy_text(v), reply_markup=kb.vacancy_manage_kb(vid, 1))
    await call.answer("Vakansiya qayta ochildi ♻️")


@router.callback_query(F.data.startswith("vdel:"))
async def vac_del(call: CallbackQuery):
    vid = int(call.data.split(":")[1])
    await q.delete_vacancy(vid)
    me = await actor(call.from_user.id)
    await q.add_log(call.from_user.id, me["full_name"], "vakansiya_ochirildi", f"#{vid}")
    await call.message.edit_text("🗑 Vakansiya o'chirildi.")
    await call.answer("O'chirildi")


# ------- Vakansiyani tahrirlash -------
@router.callback_query(F.data.startswith("vedit:"))
async def vac_edit(call: CallbackQuery):
    vid = int(call.data.split(":")[1])
    await call.message.answer(
        "✏️ Qaysi maydonni tahrirlaysiz?",
        reply_markup=kb.vacancy_edit_fields_kb(vid),
    )
    await call.answer()


@router.callback_query(F.data.startswith("vef:"))
async def vac_edit_field(call: CallbackQuery, state: FSMContext):
    _, vid, field = call.data.split(":")
    await state.update_data(edit_vid=int(vid), edit_field=field)
    await state.set_state(VacancyForm.edit_value)
    await call.message.answer("Yangi qiymatni kiriting:")
    await call.answer()


@router.message(VacancyForm.edit_value, F.text)
async def vac_edit_save(message: Message, state: FSMContext):
    data = await state.get_data()
    await q.update_vacancy_field(data["edit_vid"], data["edit_field"], message.text.strip())
    await state.clear()
    me = await actor(message.from_user.id)
    await q.add_log(message.from_user.id, me["full_name"], "vakansiya_tahrir", f"#{data['edit_vid']}")
    v = await q.get_vacancy(data["edit_vid"])
    await message.answer("✅ Yangilandi:\n\n" + vacancy_text(v),
                         reply_markup=kb.vacancy_manage_kb(v["id"], v["is_active"]))


# ------- Yangi vakansiya yaratish -------
@router.callback_query(F.data == "hrvac_new")
async def vac_new_start(call: CallbackQuery, state: FSMContext):
    if not await is_staff(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    await state.set_state(VacancyForm.title)
    await call.message.answer("➕ <b>Yangi vakansiya</b>\n\n1️⃣ Lavozim nomi (masalan: Farmatsevt):")
    await call.answer()


@router.message(VacancyForm.title, F.text)
async def vac_new_title(message: Message, state: FSMContext):
    await state.update_data(title=message.text.strip())
    branches = await q.list_branches()
    await state.set_state(VacancyForm.branch)
    if branches:
        await message.answer("2️⃣ Filialni tanlang:", reply_markup=kb.branch_pick_kb(branches, "vnbr"))
    else:
        await message.answer("2️⃣ Filial (matn bilan yozing, hali filiallar qo'shilmagan):")


@router.callback_query(VacancyForm.branch, F.data.startswith("vnbr:"))
async def vac_new_branch_cb(call: CallbackQuery, state: FSMContext):
    bid = int(call.data.split(":")[1])
    await state.update_data(branch_id=bid if bid else None)
    await state.set_state(VacancyForm.job_type)
    await call.message.answer("3️⃣ Ish turi (masalan: To'liq stavka / Yarim stavka):")
    await call.answer()


@router.message(VacancyForm.branch, F.text)
async def vac_new_branch_text(message: Message, state: FSMContext):
    await state.update_data(branch_id=None)
    await state.set_state(VacancyForm.job_type)
    await message.answer("3️⃣ Ish turi (masalan: To'liq stavka / Yarim stavka):")


@router.message(VacancyForm.job_type, F.text)
async def vac_new_jobtype(message: Message, state: FSMContext):
    await state.update_data(job_type=message.text.strip())
    await state.set_state(VacancyForm.shift)
    await message.answer("4️⃣ Smena (masalan: Ertalab / Kechqurun):")


@router.message(VacancyForm.shift, F.text)
async def vac_new_shift(message: Message, state: FSMContext):
    await state.update_data(shift=message.text.strip())
    await state.set_state(VacancyForm.salary)
    await message.answer("5️⃣ Oylik (masalan: 4 500 000 so'm):")


@router.message(VacancyForm.salary, F.text)
async def vac_new_salary(message: Message, state: FSMContext):
    await state.update_data(salary=message.text.strip())
    await state.set_state(VacancyForm.work_time)
    await message.answer("6️⃣ Ish vaqti (masalan: 08:00-16:00):")


@router.message(VacancyForm.work_time, F.text)
async def vac_new_worktime(message: Message, state: FSMContext):
    await state.update_data(work_time=message.text.strip())
    await state.set_state(VacancyForm.requirements)
    await message.answer("7️⃣ Talablar:")


@router.message(VacancyForm.requirements, F.text)
async def vac_new_req(message: Message, state: FSMContext):
    await state.update_data(requirements=message.text.strip())
    await state.set_state(VacancyForm.responsibilities)
    await message.answer("8️⃣ Mas'uliyatlar:")


@router.message(VacancyForm.responsibilities, F.text)
async def vac_new_resp(message: Message, state: FSMContext):
    await state.update_data(responsibilities=message.text.strip())
    await state.set_state(VacancyForm.conditions)
    await message.answer("9️⃣ Ish sharoiti:")


@router.message(VacancyForm.conditions, F.text)
async def vac_new_cond(message: Message, state: FSMContext):
    await state.update_data(conditions=message.text.strip())
    await message.answer("🔟 Holati:", reply_markup=kb.yes_no_active_kb())


@router.callback_query(F.data.startswith("vac_active:"))
async def vac_new_active(call: CallbackQuery, state: FSMContext):
    active = call.data.split(":")[1] == "1"
    data = await state.get_data()
    data["is_active"] = active
    me = await actor(call.from_user.id)
    vid = await q.add_vacancy(data, created_by=me["id"])
    await state.clear()
    await q.add_log(call.from_user.id, me["full_name"], "vakansiya_yaratildi", f"#{vid} {data.get('title')}")
    v = await q.get_vacancy(vid)
    await call.message.answer("✅ <b>Vakansiya yaratildi!</b>\n\n" + vacancy_text(v))
    await call.answer("Yaratildi ✅")


# ---------------- XABARNOMA ----------------
@router.message(F.text == "📢 Xabarnoma")
async def broadcast_start(message: Message, state: FSMContext):
    if not await is_staff(message.from_user.id):
        return
    await message.answer(
        "📢 <b>Xabarnoma</b>\nKimga yubormoqchisiz?",
        reply_markup=kb.broadcast_target_kb(),
    )


@router.callback_query(F.data.startswith("bc:"))
async def broadcast_target(call: CallbackQuery, state: FSMContext):
    if not await is_staff(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    target = call.data.split(":")[1]
    if target == "branch":
        branches = await q.list_branches()
        if not branches:
            await call.answer("Filiallar yo'q.", show_alert=True)
            return
        await call.message.answer("Filialni tanlang:", reply_markup=kb.branch_pick_kb(branches, "bcbr"))
        await call.answer()
        return
    await state.update_data(bc_target=target, bc_branch=None)
    await state.set_state(Broadcast.content)
    await call.message.answer("✍️ Yubormoqchi bo'lgan xabarni yuboring (matn, rasm, video, fayl):")
    await call.answer()


@router.callback_query(F.data.startswith("bcbr:"))
async def broadcast_branch(call: CallbackQuery, state: FSMContext):
    bid = int(call.data.split(":")[1])
    await state.update_data(bc_target="branch", bc_branch=bid if bid else None)
    await state.set_state(Broadcast.content)
    await call.message.answer("✍️ Yubormoqchi bo'lgan xabarni yuboring:")
    await call.answer()


@router.message(Broadcast.content)
async def broadcast_send(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    target = data.get("bc_target")
    branch = data.get("bc_branch")
    await state.clear()

    if target == "all":
        ids = await q.all_user_tg_ids()
    elif target == "branch":
        ids = await q.all_user_tg_ids(branch_id=branch)
    else:
        ids = await q.all_user_tg_ids(role=target)

    ids = list(set(ids))
    if not ids:
        await message.answer("Bu guruhda foydalanuvchilar yo'q.")
        return
    await message.answer(f"📤 Yuborilmoqda... ({len(ids)} ta)")
    ok, fail = await broadcast(bot, ids, message)
    me = await actor(message.from_user.id)
    await q.add_log(message.from_user.id, me["full_name"], "xabarnoma", f"{target}: {ok} ta")
    await message.answer(f"✅ Yuborildi: {ok} ta\n❌ Yuborilmadi: {fail} ta")


# ---------------- QIDIRUV ----------------
@router.message(F.text == "🔍 Qidiruv")
async def search_start(message: Message):
    if not await is_staff(message.from_user.id):
        return
    await message.answer("🔍 Nima bo'yicha qidiramiz?", reply_markup=kb.search_field_kb())


@router.callback_query(F.data.startswith("srch:"))
async def search_field(call: CallbackQuery, state: FSMContext):
    field = call.data.split(":")[1]
    await state.update_data(search_field=field)
    await state.set_state(SearchForm.query)
    labels = {"full_name": "ism", "phone": "telefon", "branch": "filial", "vacancy": "lavozim"}
    await call.message.answer(f"🔎 Qidiruv so'zini kiriting ({labels.get(field)}):")
    await call.answer()


@router.message(SearchForm.query, F.text)
async def search_run(message: Message, state: FSMContext):
    data = await state.get_data()
    field = data.get("search_field")
    await state.clear()
    results = await q.search_applications(field, message.text.strip())
    await send_application_results(
        message,
        results,
        f"🔍 <b>Qidiruv natijasi:</b> {message.text.strip()}",
    )


# ---------------- SUHBATLAR KALENDARI ----------------
INT_STATUS = {
    "pending": "⏳ Kutilmoqda",
    "confirmed": "✅ Tasdiqlangan",
    "reschedule": "🔄 Boshqa vaqt so'ralgan",
}


@router.message(F.text == "📅 Suhbatlar")
async def hr_interviews(message: Message):
    if not await is_staff(message.from_user.id):
        return
    interviews = await q.list_upcoming_interviews(limit=30)
    if not interviews:
        await message.answer("📅 Hozircha rejalashtirilgan suhbatlar yo'q.")
        return
    pending = sum(1 for i in interviews if i.get("status") == "pending")
    confirmed = sum(1 for i in interviews if i.get("status") == "confirmed")
    resc = sum(1 for i in interviews if i.get("status") == "reschedule")
    await message.answer(
        f"📅 <b>Suhbatlar</b>\n\n"
        f"⏳ Kutilmoqda: <b>{pending}</b> | ✅ Tasdiqlangan: <b>{confirmed}</b> | "
        f"🔄 Boshqa vaqt: <b>{resc}</b>\n\n"
        "Batafsil ko'rish uchun suhbatni tanlang:",
        reply_markup=kb.interviews_list_kb(interviews),
    )


@router.callback_query(F.data.startswith("intview:"))
async def interview_view(call: CallbackQuery):
    if not await is_staff(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    iid = int(call.data.split(":")[1])
    i = await q.get_interview(iid)
    if not i:
        await call.answer("Suhbat topilmadi.", show_alert=True)
        return
    a = await q.get_application(i["application_id"])
    text = (
        f"📅 <b>Suhbat #{i['id']}</b>\n"
        "━━━━━━━━━━━━\n"
        f"👤 Nomzod: {a.get('full_name') if a else '-'}\n"
        f"💼 Lavozim: {a.get('vacancy_title') if a else '-'}\n"
        f"📱 Telefon: {a.get('phone') if a else '-'}\n"
        f"📆 Sana: {i.get('date') or '-'}\n"
        f"🕐 Vaqt: {i.get('time') or '-'}\n"
        f"📍 Manzil: {i.get('location') or '-'}\n"
        f"💬 Izoh: {i.get('comment') or '-'}\n"
        f"🚦 Holat: {INT_STATUS.get(i.get('status'), i.get('status'))}"
    )
    markup = kb.application_actions_kb(a["id"], favorite=bool(a.get("favorite"))) if a else None
    await call.message.answer(text, reply_markup=markup)
    await call.answer()


# ---------------- SARALANGAN (SHORTLIST) ----------------
@router.message(F.text == "⭐ Saralanganlar")
async def hr_favorites(message: Message):
    if not await is_staff(message.from_user.id):
        return
    apps = await q.list_favorite_applications(limit=30)
    if not apps:
        await message.answer(
            "⭐ Saralangan nomzodlar yo'q.\n\n"
            "Arizani ochib «⭐ Saralashga qo'shish» tugmasini bosing."
        )
        return
    await message.answer(
        f"⭐ <b>Saralangan nomzodlar</b>\n\nJami: <b>{len(apps)}</b> ta\nTanlang:",
        reply_markup=kb.applications_list_kb(apps, prefix="appview"),
    )


@router.callback_query(F.data.startswith("appfav:"))
async def app_favorite_toggle(call: CallbackQuery):
    if not await is_staff(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    aid = int(call.data.split(":")[1])
    fav = await q.toggle_favorite(aid)
    try:
        await call.message.edit_reply_markup(
            reply_markup=kb.application_actions_kb(aid, favorite=fav)
        )
    except Exception:
        pass
    await call.answer("⭐ Saralanganlarga qo'shildi" if fav else "Saralanganlardan olindi")


# ---------------- NOMZODGA XABAR ----------------
@router.callback_query(F.data.startswith("appmsg:"))
async def app_message_start(call: CallbackQuery, state: FSMContext):
    if not await is_staff(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    aid = int(call.data.split(":")[1])
    a = await q.get_application(aid)
    if not a or not a.get("applicant_tg"):
        await call.answer("Nomzodning Telegram hisobi topilmadi.", show_alert=True)
        return
    await state.update_data(msg_aid=aid, msg_tg=a["applicant_tg"])
    await state.set_state(CandidateMessageForm.text)
    await call.message.answer(
        f"💬 Nomzod <b>{a.get('full_name')}</b> ga yubormoqchi bo'lgan xabaringizni yozing:"
    )
    await call.answer()


@router.message(CandidateMessageForm.text, F.text)
async def app_message_send(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    tg = data.get("msg_tg")
    aid = data.get("msg_aid")
    await state.clear()
    if not tg:
        await message.answer("Sessiya tugagan. Qaytadan urinib ko'ring.")
        return
    ok = await safe_send(
        bot, tg,
        f"✉️ <b>Gulnora Farm HR xabari</b> (ariza #{aid}):\n\n{message.text.strip()}",
    )
    me = await actor(message.from_user.id)
    await q.add_log(message.from_user.id, me["full_name"], "nomzodga_xabar", f"#{aid}")
    await message.answer(
        "✅ Xabar nomzodga yuborildi." if ok
        else "❌ Yuborib bo'lmadi (nomzod botni bloklagan bo'lishi mumkin)."
    )


# ---------------- EXCEL EKSPORT ----------------
@router.message(F.text == "📊 Excel eksport")
async def hr_export(message: Message):
    if not await is_staff(message.from_user.id):
        return
    await message.answer(
        "📊 <b>Excel eksport</b>\nQaysi ma'lumotni yuklab olasiz?",
        reply_markup=kb.export_kb("hr"),
    )


@router.callback_query(F.data.startswith("exp:"))
async def export_data(call: CallbackQuery, bot: Bot):
    user = await q.get_user(call.from_user.id)
    if not user or user["role"] not in (ROLE_HR, ROLE_ADMIN, ROLE_DIRECTOR):
        await call.answer("⛔", show_alert=True)
        return
    kind = call.data.split(":")[1]
    if kind == "users" and user["role"] != ROLE_ADMIN:
        await call.answer("⛔ Faqat admin.", show_alert=True)
        return
    await call.answer("⏳ Tayyorlanmoqda...")
    if kind == "apps":
        doc = export.build_applications_xlsx(await q.list_applications(limit=2000))
        caption = "📄 Arizalar ro'yxati (Excel)"
    elif kind == "users":
        doc = export.build_users_xlsx(await q.list_users(limit=5000))
        caption = "👥 Foydalanuvchilar (Excel)"
    else:
        stats = await q.stats_counts()
        branches = await q.stats_by_branch()
        vacs = await q.stats_by_vacancy()
        doc = export.build_report_xlsx(stats, branches, vacs)
        caption = "📊 Umumiy hisobot (Excel)"
    try:
        await bot.send_document(call.message.chat.id, doc, caption=caption)
    except Exception:
        await call.message.answer("❌ Faylni yuborib bo'lmadi.")
