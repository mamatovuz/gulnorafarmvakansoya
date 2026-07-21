"""Davomat (attendance): «📍 Ishga keldim» / «🏁 Ishdan ketdim» — GPS orqali
ofisda ekanini tekshirish va HR/Direktor/Filial rahbari/Buxgalter uchun
davomat hisobotlari (kelgan/ketgan vaqt, kech qolgan/erta ketgan)."""
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter

from database import queries as q
from database.db import (
    ROLE_ADMIN, ROLE_HR, ROLE_MANAGER, ROLE_DIRECTOR, ROLE_PHARMACIST,
    ROLE_EMPLOYEE, ROLE_ACCOUNTANT,
)
from states import AttendanceForm
import keyboards as kb
from utils import (
    haversine_m, employee_profile_text, safe_send, now_tk_hm, fmt_duration,
)

router = Router()

PERIOD_TITLES = {"day": "📅 Bugun", "week": "🗓 Oxirgi 7 kun", "month": "📆 Oxirgi 30 kun"}


def _parse_work_hours(work_hours):
    """«09:00 - 18:00» dan (start_time, end_time) qaytaradi. Aniqlanmasa (None, None)."""
    if not work_hours:
        return None, None
    import re
    times = re.findall(r"(\d{1,2}):(\d{2})", work_hours)
    if len(times) < 2:
        return None, None
    start = f"{int(times[0][0]):02d}:{times[0][1]}"
    end = f"{int(times[1][0]):02d}:{times[1][1]}"
    return start, end


def _is_late(work_hours, now_hm):
    start, _ = _parse_work_hours(work_hours)
    if not start:
        return False
    return now_hm > start


def _is_early(work_hours, now_hm):
    _, end = _parse_work_hours(work_hours)
    if not end:
        return False
    return now_hm < end


async def _open_shift(tg_id):
    """Xodimning hali yakunlanmagan ish kuni yozuvi.

    Tanaffus va ishdan ketish shu yozuv ustida ishlaydi. Tungi smenada soat
    00:00 dan o'tib ketsa ham kechagi ochiq yozuv topiladi — shuning uchun
    «avval ishga keling» xabari noto'g'ri chiqmaydi."""
    return await q.get_open_attendance(tg_id)


async def _no_open_shift_reason(tg_id):
    """Ochiq yozuv bo'lmasa — sababini tushuntiruvchi matn."""
    last = await q.get_attendance_today(tg_id)
    if last and last.get("out_time"):
        return (
            "🏁 Siz bugun <b>ishdan ketganingizni</b> allaqachon belgilagansiz "
            f"(🕐 {last['out_time']}).\nIsh kuni yakunlangan."
        )
    return (
        "❗️ Bugun <b>«📍 Ishga keldim»</b> belgilanmagan.\n"
        "Avval «📍 Ishga keldim» tugmasini bosib, joylashuvingizni yuboring."
    )


# ================= ISHGA KELDIM (CHECK-IN) =================
@router.message(F.text == "📍 Ishga keldim")
async def checkin_start(message: Message, state: FSMContext):
    profile = await q.get_employee_profile_by_tg(message.from_user.id)
    if not profile:
        await message.answer(
            "⛔ Bu funksiya faqat tasdiqlangan xodimlar uchun. "
            "«🏢 Gulnora Farm hodimi» orqali ro'yxatdan o'ting."
        )
        return
    already = await q.get_attendance_today(message.from_user.id)
    if already and already.get("status") == "present":
        await message.answer(
            f"✅ Siz bugun allaqachon ishga kelganingizni belgilagansiz.\n"
            f"🕐 Vaqt: {already.get('time') or '-'}"
        )
        return
    await state.set_state(AttendanceForm.location)
    await message.answer(
        "📍 <b>Ishga keldim</b>\n\n"
        "Ofisda ekaningizni tasdiqlash uchun joriy <b>GPS joylashuvingizni</b> yuboring.\n"
        "Pastdagi «📍 Joylashuvni yuborish» tugmasini bosing.",
        reply_markup=kb.attendance_location_kb(),
    )


@router.message(AttendanceForm.location, F.text == kb.CANCEL_BTN)
async def checkin_cancel(message: Message, state: FSMContext):
    await state.clear()
    user = await q.get_user(message.from_user.id)
    await message.answer(
        "❌ Bekor qilindi.",
        reply_markup=kb.main_menu(user["role"] if user else "candidate"),
    )


@router.message(AttendanceForm.location, F.location)
async def checkin_location(message: Message, state: FSMContext, bot: Bot):
    await state.clear()
    user = await q.get_user(message.from_user.id)
    profile = await q.get_employee_profile_by_tg(message.from_user.id)
    menu = kb.main_menu(user["role"] if user else "candidate")

    branch = await q.get_branch(profile["branch_id"]) if profile and profile.get("branch_id") else None
    if not branch:
        await message.answer(
            "⛔ Sizga filial biriktirilmagan. HR yoki administrator bilan bog'laning.",
            reply_markup=menu,
        )
        return
    if branch.get("latitude") is None or branch.get("longitude") is None:
        await message.answer(
            f"⛔ «{branch['name']}» filiali joylashuvi hali sozlanmagan.\n"
            "Administrator filial koordinatasini kiritgach qayta urinib ko'ring.",
            reply_markup=menu,
        )
        return

    lat = message.location.latitude
    lon = message.location.longitude
    dist = haversine_m(branch["latitude"], branch["longitude"], lat, lon)
    radius = branch.get("radius") or 150

    if dist is not None and dist <= radius:
        now_hm = now_tk_hm()
        late = _is_late(profile.get("work_hours"), now_hm)
        await q.add_attendance(
            user["id"], branch["id"], lat, lon, dist, status="present", late=late
        )
        row = await q.get_attendance_today(message.from_user.id)
        late_note = "\n⚠️ <b>Kech keldingiz.</b>" if late else ""
        await message.answer(
            "✅ <b>Keldingiz belgilandi!</b>\n\n"
            f"🏢 Filial: {branch['name']}\n"
            f"🕐 Kelgan vaqt: {row.get('time') if row else '-'}\n"
            f"📏 Ofisgacha masofa: ~{dist} m"
            f"{late_note}\n\n"
            "Ish tugagach «🏁 Ishdan ketdim» tugmasini bosishni unutmang.",
            reply_markup=menu,
        )
        await q.add_log(
            message.from_user.id, user.get("full_name") if user else "?",
            "ishga_keldi", f"{branch['name']} · {dist}m{' · kech' if late else ''}"
        )
    else:
        await message.answer(
            "❌ <b>Siz ofisda emassiz.</b>\n\n"
            f"🏢 Filial: {branch['name']}\n"
            f"📏 Ofisdan masofa: ~{dist} m (ruxsat: {radius} m)\n\n"
            "Ofisga yaqinlashib, qaytadan «📍 Ishga keldim» tugmasini bosing.",
            reply_markup=menu,
        )


@router.message(AttendanceForm.location, F.text)
async def checkin_need_location(message: Message):
    await message.answer(
        "❗️ Matn emas — <b>joylashuv</b> yuboring. "
        "«📍 Joylashuvni yuborish» tugmasidan foydalaning.",
        reply_markup=kb.attendance_location_kb(),
    )


# ================= ISHDAN KETDIM (CHECK-OUT) =================
@router.message(F.text == "🏁 Ishdan ketdim")
async def checkout_start(message: Message, state: FSMContext):
    profile = await q.get_employee_profile_by_tg(message.from_user.id)
    if not profile:
        await message.answer("⛔ Bu funksiya faqat tasdiqlangan xodimlar uchun.")
        return
    today = await _open_shift(message.from_user.id)
    if not today:
        await message.answer(await _no_open_shift_reason(message.from_user.id))
        return
    await state.set_state(AttendanceForm.checkout)
    await message.answer(
        "🏁 <b>Ishdan ketdim</b>\n\n"
        "Ketayotganingizni tasdiqlash uchun joriy <b>GPS joylashuvingizni</b> yuboring.",
        reply_markup=kb.attendance_location_kb(),
    )


@router.message(AttendanceForm.checkout, F.text == kb.CANCEL_BTN)
async def checkout_cancel(message: Message, state: FSMContext):
    await state.clear()
    user = await q.get_user(message.from_user.id)
    await message.answer(
        "❌ Bekor qilindi.",
        reply_markup=kb.main_menu(user["role"] if user else "candidate"),
    )


@router.message(AttendanceForm.checkout, F.location)
async def checkout_location(message: Message, state: FSMContext):
    await state.clear()
    user = await q.get_user(message.from_user.id)
    profile = await q.get_employee_profile_by_tg(message.from_user.id)
    menu = kb.main_menu(user["role"] if user else "candidate")
    today = await _open_shift(message.from_user.id)
    if not today:
        await message.answer(
            await _no_open_shift_reason(message.from_user.id), reply_markup=menu
        )
        return
    # Tanaffusda bo'lsa — avval tanaffusni yopamiz (vaqti hisobga olinadi)
    if today.get("on_break"):
        await q.end_break(today["id"])
    branch = await q.get_branch(profile["branch_id"]) if profile and profile.get("branch_id") else None
    lat = message.location.latitude
    lon = message.location.longitude
    dist = None
    if branch and branch.get("latitude") is not None:
        dist = haversine_m(branch["latitude"], branch["longitude"], lat, lon)
    now_hm = now_tk_hm()
    early = _is_early(profile.get("work_hours"), now_hm)
    await q.set_attendance_checkout(today["id"], lat, lon, dist, early=early)
    early_note = "\n⚠️ <b>Erta ketdingiz.</b>" if early else ""
    await message.answer(
        "🏁 <b>Ketganingiz belgilandi!</b>\n\n"
        f"🕐 Kelgan vaqt: {today.get('time') or '-'}\n"
        f"🕐 Ketgan vaqt: {now_hm}"
        f"{early_note}",
        reply_markup=menu,
    )
    await q.add_log(
        message.from_user.id, user.get("full_name") if user else "?",
        "ishdan_ketdi", f"{now_hm}{' · erta' if early else ''}"
    )


@router.message(AttendanceForm.checkout, F.text)
async def checkout_need_location(message: Message):
    await message.answer(
        "❗️ Matn emas — <b>joylashuv</b> yuboring.",
        reply_markup=kb.attendance_location_kb(),
    )


# ================= TANAFFUS (BREAK) =================
@router.message(F.text == "⏸ Tanaffus")
async def break_start(message: Message, state: FSMContext):
    # Yarim qolgan boshqa oqim tanaffusga xalaqit qilmasin
    await state.clear()
    profile = await q.get_employee_profile_by_tg(message.from_user.id)
    if not profile:
        await message.answer("⛔ Bu funksiya faqat tasdiqlangan xodimlar uchun.")
        return
    today = await _open_shift(message.from_user.id)
    if not today:
        await message.answer(await _no_open_shift_reason(message.from_user.id))
        return
    if today.get("on_break"):
        await message.answer("⏸ Siz allaqachon tanaffusdasiz. Ishni davom ettirish uchun "
                             "«▶️ Ishni davom ettirish» tugmasini bosing.")
        return
    await q.start_break(today["id"])
    await q.add_log(message.from_user.id, message.from_user.full_name, "tanaffus_boshladi", "")
    await message.answer(
        "⏸ <b>Tanaffus boshlandi.</b>\n"
        "Tanaffus tugagach «▶️ Ishni davom ettirish» tugmasini bosing — "
        "ish joyingizni tasdiqlash uchun joylashuv so'raladi."
    )


@router.message(F.text == "▶️ Ishni davom ettirish")
async def break_end(message: Message, state: FSMContext):
    await state.clear()
    profile = await q.get_employee_profile_by_tg(message.from_user.id)
    if not profile:
        await message.answer("⛔ Bu funksiya faqat tasdiqlangan xodimlar uchun.")
        return
    today = await _open_shift(message.from_user.id)
    if not today or not today.get("on_break"):
        await message.answer(
            "❗️ Siz hozir tanaffusda emassiz. Tanaffus olish uchun "
            "«⏸ Tanaffus» tugmasini bosing."
        )
        return
    await q.end_break(today["id"])
    await q.add_log(message.from_user.id, message.from_user.full_name, "tanaffus_tugadi", "")
    # Ishga qaytishni tasdiqlash uchun joylashuv so'raymiz (resume tekshiruvi)
    await q.add_location_check(today["id"], today["user_id"], today.get("branch_id"), kind="resume")
    await message.answer(
        "▶️ <b>Tanaffus tugadi.</b>\n\n"
        "Ish joyingizga qaytganingizni tasdiqlash uchun joriy <b>joylashuvingizni</b> yuboring.",
        reply_markup=kb.attendance_location_kb(),
    )


# ================= PERIODIK / RESUME JOYLASHUV TEKSHIRUVI =================
@router.message(StateFilter(None), F.location)
async def periodic_location_response(message: Message):
    """FSM holatidan tashqarida kelgan joylashuv — periodik yoki tanaffusdan keyingi
    tekshiruv javobi sifatida qabul qilinadi."""
    check = await q.latest_pending_location_check(message.from_user.id)
    if not check:
        return  # kutilayotgan tekshiruv yo'q — e'tiborsiz qoldiramiz
    profile = await q.get_employee_profile_by_tg(message.from_user.id)
    user = await q.get_user(message.from_user.id)
    menu = kb.main_menu(user["role"] if user else "candidate")
    branch = await q.get_branch(profile["branch_id"]) if profile and profile.get("branch_id") else None
    if not branch or branch.get("latitude") is None:
        await q.resolve_location_check(check["id"], "present", None)
        await message.answer("✅ Qabul qilindi.", reply_markup=menu)
        return
    lat, lon = message.location.latitude, message.location.longitude
    dist = haversine_m(branch["latitude"], branch["longitude"], lat, lon)
    radius = branch.get("radius") or 150
    if dist is not None and dist <= radius:
        await q.resolve_location_check(check["id"], "present", dist)
        await message.answer(
            "✅ <b>Rahmat!</b> Ish joyingizda ekaningiz tasdiqlandi.\n"
            f"📏 Ofisgacha masofa: ~{dist} m",
            reply_markup=menu,
        )
    else:
        await q.resolve_location_check(check["id"], "away", dist)
        await message.answer(
            "⚠️ <b>Siz ish joyingizda emassiz.</b>\n"
            f"📏 Ofisdan masofa: ~{dist} m (ruxsat: {radius} m)\n"
            "Bu holat rahbaringiz hisobotida qayd etiladi.",
            reply_markup=menu,
        )


# ================= TANAFFUS / TEKSHIRUV HISOBOTI (rahbar/direktor) =================
async def _break_scope_branch(user):
    """(scope, branch_id) qaytaradi. mgr — o'z filiali, dir — o'z filiali (bo'lsa)."""
    role = user["role"] if user else None
    profile = await q.get_employee_profile_by_tg(user["tg_id"]) if user else None
    branch_id = user.get("branch_id") or (profile.get("branch_id") if profile else None)
    if role in (ROLE_MANAGER,):
        return "mgr", branch_id
    if role == ROLE_DIRECTOR:
        return "dir", branch_id
    if role in (ROLE_HR, ROLE_ADMIN):
        return "hr", None
    return None, None


@router.message(F.text == "⏸ Tanaffus hisoboti")
async def break_report_menu(message: Message):
    user = await q.get_user(message.from_user.id)
    scope, _ = await _break_scope_branch(user)
    if not scope:
        await message.answer("⛔ Sizda bu hisobotni ko'rish huquqi yo'q.")
        return
    await message.answer(
        "⏸ <b>Tanaffus va ish joyi tekshiruvi hisoboti</b>\nDavrni tanlang:",
        reply_markup=kb.break_stats_kb(scope),
    )


@router.callback_query(F.data.startswith("brk:"))
async def break_report_cb(call: CallbackQuery):
    user = await q.get_user(call.from_user.id)
    scope, branch_id = await _break_scope_branch(user)
    if not scope:
        await call.answer("⛔", show_alert=True)
        return
    period = call.data.split(":")[2]
    rows = await q.break_and_check_stats(period=period, branch_id=branch_id)
    title = PERIOD_TITLES.get(period, period)
    lines = [
        f"⏸ <b>Tanaffus hisoboti</b> — {title}",
        ("🏢 O'z filialingiz" if branch_id else "🏢 Barcha filiallar"),
        "━━━━━━━━━━━━",
    ]
    if not rows:
        lines.append("Bu davrda ma'lumot yo'q.")
    for r in rows[:40]:
        checks = ""
        if r.get("away_cnt") or r.get("missed_cnt"):
            checks = (f" · ⚠️ tashqarida {r['away_cnt']}"
                      if r.get("away_cnt") else "")
            checks += (f" · ❌ javobsiz {r['missed_cnt']}"
                       if r.get("missed_cnt") else "")
        lines.append(
            f"• <b>{r.get('full_name') or r.get('tg_id')}</b>"
            + (f" · {r['branch_name']}" if scope == 'hr' and r.get('branch_name') else "")
            + f"\n   ⏸ Jami tanaffus: <b>{fmt_duration(r.get('break_seconds'))}</b>"
            + f" ({r.get('days')} kun)"
            + (f" · ✅ tekshiruv {r['ok_cnt']}" if r.get('ok_cnt') else "")
            + checks
        )
    for chunk in _split("\n".join(lines)):
        await call.message.answer(chunk)
    await call.answer()


# ================= MENING PROFILIM (xodim) =================
@router.message(F.text == "👤 Mening profilim")
async def my_profile(message: Message):
    profile = await q.get_employee_profile_by_tg(message.from_user.id)
    if not profile:
        await message.answer("Profil topilmadi. HR bilan bog'laning.")
        return
    text = employee_profile_text(profile)
    today = await q.get_attendance_today(message.from_user.id)
    if today and today.get("status") == "present":
        text += f"\n\n📍 Bugun: ✅ Kelgan ({today.get('time') or '-'})"
        if today.get("on_break"):
            text += "\n⏸ Hozir tanaffusdasiz"
        if today.get("break_seconds"):
            text += f"\n⏸ Bugungi tanaffus: {fmt_duration(today.get('break_seconds'))}"
    else:
        text += "\n\n📍 Bugun: ⏳ Hali belgilanmagan"
    # oxirgi kelishlar
    history = await q.attendance_history(profile["user_id"], limit=7)
    if history:
        text += "\n\n<b>Oxirgi kelishlar:</b>\n"
        for h in history:
            text += f"  • {h.get('date')} {h.get('time') or ''}\n"
    await message.answer(text)


# ================= DAVOMAT HISOBOTLARI =================
def _scope_for_user(user):
    role = user["role"] if user else None
    if role in (ROLE_HR, ROLE_ADMIN, ROLE_ACCOUNTANT):
        return "hr"
    if role == ROLE_DIRECTOR:
        return "dir"
    if role == ROLE_MANAGER:
        return "mgr"
    return None


async def _render_report(target, user, scope, period):
    """Davr bo'yicha davomat hisobotini chiqaradi. mgr uchun faqat o'z filiali."""
    branch_id = None
    branch_label = "Barcha filiallar"
    if scope == "mgr":
        profile = await q.get_employee_profile_by_tg(user["tg_id"])
        branch_id = (user.get("branch_id")
                     or (profile.get("branch_id") if profile else None))
        if not branch_id:
            await target.answer("Sizga filial biriktirilmagan.")
            return
        branch = await q.get_branch(branch_id)
        branch_label = branch["name"] if branch else "Filial"

    present = await q.attendance_present_by_employee(period=period, branch_id=branch_id)
    total_emp = await q.count_active_employees(branch_id=branch_id)

    title = PERIOD_TITLES.get(period, period)
    lines = [
        f"📍 <b>Davomat hisoboti</b> — {title}",
        f"🏢 {branch_label}",
        "━━━━━━━━━━━━",
        f"👥 Jami xodimlar: <b>{total_emp}</b>",
        f"✅ Davrda kelganlar: <b>{len(present)}</b>",
        "",
    ]
    if present:
        lines.append("<b>Kelganlar (kunlar soni):</b>")
        for p in present[:40]:
            flags = ""
            if p.get("lates"):
                flags += f" · ⏰ kech {p['lates']}"
            if p.get("earlies"):
                flags += f" · 🏃 erta {p['earlies']}"
            lines.append(
                f"  • {p.get('full_name') or p.get('tg_id')}"
                + (f" · {p['branch_name']}" if scope != 'mgr' and p.get('branch_name') else "")
                + f" — {p['days']} kun{flags}"
            )
    else:
        lines.append("Bu davrda hech kim kelmagan.")

    # Kunlik ko'rinishda: kelgan/ketgan vaqtlar
    if period == "day":
        detail = await q.attendance_detail(period="day", branch_id=branch_id)
        if detail:
            lines.append("")
            lines.append("<b>🕐 Bugungi kelgan/ketgan vaqt:</b>")
            for d in detail[:40]:
                out = d.get("out_time") or "…"
                marks = ""
                if d.get("late"):
                    marks += " ⏰"
                if d.get("early"):
                    marks += " 🏃"
                lines.append(
                    f"  • {d.get('full_name')}: {d.get('time') or '-'} → {out}{marks}"
                )
        absent = await q.attendance_absent_today(branch_id=branch_id)
        lines.append("")
        lines.append(f"<b>❌ Bugun kelmaganlar:</b> {len(absent)} ta")
        for a in absent[:40]:
            lines.append(
                f"  • {a.get('full_name') or a.get('tg_id')}"
                + (f" · {a['branch_name']}" if scope != 'mgr' and a.get('branch_name') else "")
            )

    text = "\n".join(lines)
    for chunk in _split(text):
        await target.answer(chunk)


def _split(text, size=3800):
    return [text[i:i + size] for i in range(0, len(text), size)]


async def _open_report_menu(message, user):
    scope = _scope_for_user(user)
    if not scope:
        await message.answer("⛔ Sizda davomat hisobotini ko'rish huquqi yo'q.")
        return
    await message.answer(
        "📍 <b>Davomat</b>\nDavrni tanlang:",
        reply_markup=kb.attendance_report_kb(scope),
    )


# HR panel «📍 Davomat»
@router.message(F.text == "📍 Davomat")
async def attendance_menu(message: Message):
    user = await q.get_user(message.from_user.id)
    await _open_report_menu(message, user)


@router.callback_query(F.data.startswith("att:"))
async def attendance_report_cb(call: CallbackQuery):
    user = await q.get_user(call.from_user.id)
    _, scope, period = call.data.split(":")
    real_scope = _scope_for_user(user)
    if not real_scope:
        await call.answer("⛔", show_alert=True)
        return
    # Foydalanuvchi haqiqiy huquqidan yuqori scope so'ramasin
    await _render_report(call.message, user, real_scope, period)
    await call.answer()


@router.callback_query(F.data.startswith("attbr:"))
async def attendance_branch_report_cb(call: CallbackQuery):
    user = await q.get_user(call.from_user.id)
    _, scope, period = call.data.split(":")
    real_scope = _scope_for_user(user)
    if real_scope not in ("hr", "dir"):
        await call.answer("⛔", show_alert=True)
        return
    rows = await q.attendance_branch_summary(period=period)
    title = PERIOD_TITLES.get(period, period)
    lines = [f"🏢 <b>Filiallar kesimida davomat</b> — {title}", "━━━━━━━━━━━━"]
    if rows:
        for r in rows:
            lines.append(
                f"• <b>{r['name']}</b>: {r['check_ins']} ta kelish · "
                f"{r['employees']} xodim"
            )
    else:
        lines.append("Bu davrda ma'lumot yo'q.")
    lines.append("")
    lines.append("Davrni almashtirish:")
    await call.message.answer(
        "\n".join(lines),
        reply_markup=kb.attendance_branch_period_kb(real_scope),
    )
    await call.answer()


# ================= KECH / ERTA HISOBOT =================
@router.message(F.text == "⏰ Kech/erta hisobot")
async def late_early_menu(message: Message):
    user = await q.get_user(message.from_user.id)
    scope = _scope_for_user(user)
    if not scope:
        await message.answer("⛔ Sizda huquq yo'q.")
        return
    await message.answer(
        "⏰ <b>Kech qolgan / erta ketganlar</b>\nDavrni tanlang:",
        reply_markup=kb.late_early_kb(),
    )


@router.callback_query(F.data.startswith("le:"))
async def late_early_report(call: CallbackQuery):
    user = await q.get_user(call.from_user.id)
    scope = _scope_for_user(user)
    if not scope:
        await call.answer("⛔", show_alert=True)
        return
    period = call.data.split(":")[1]
    branch_id = None
    if scope == "mgr":
        profile = await q.get_employee_profile_by_tg(call.from_user.id)
        branch_id = user.get("branch_id") or (profile.get("branch_id") if profile else None)
    rows = await q.attendance_late_early(period=period, branch_id=branch_id)
    title = PERIOD_TITLES.get(period, period)
    lines = [f"⏰ <b>Kech/erta hisobot</b> — {title}", "━━━━━━━━━━━━"]
    if rows:
        for r in rows:
            tag = []
            if r.get("late"):
                tag.append("⏰ kech kelgan")
            if r.get("early"):
                tag.append("🏃 erta ketgan")
            lines.append(
                f"• {r.get('date')} · {r.get('full_name')}"
                + (f" · {r['branch_name']}" if r.get('branch_name') else "")
                + f" · {r.get('time') or '-'}→{r.get('out_time') or '…'} · {', '.join(tag)}"
            )
    else:
        lines.append("Bu davrda kech/erta holatlar yo'q. 👍")
    for chunk in _split("\n".join(lines)):
        await call.message.answer(chunk)
    await call.answer()
