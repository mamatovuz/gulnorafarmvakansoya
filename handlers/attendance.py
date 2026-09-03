"""Davomat (attendance): «📍 Ishga keldim» / «🏁 Ishdan ketdim» — GPS orqali
ofisda ekanini tekshirish va HR/Direktor/Filial rahbari/Buxgalter uchun
davomat hisobotlari (kelgan/ketgan vaqt, kech qolgan/erta ketgan)."""
import re
from datetime import timedelta

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter

from database import queries as q
from database.db import (
    ROLE_ADMIN, ROLE_HR, ROLE_MANAGER, ROLE_DIRECTOR, ROLE_PHARMACIST,
    ROLE_EMPLOYEE, ROLE_ACCOUNTANT, ROLE_TECH,
)
from states import AttendanceForm, AttendanceEditForm
from services import export
import keyboards as kb
from i18n import t, tf
from utils import (
    haversine_m, employee_profile_text, safe_send, now_tk_hm, fmt_duration,
    send_employee_profile, now_tk, fmt_date,
)

router = Router()


def _fmt_hms(seconds):
    """Sekundni «1 soat 5 daqiqa 10 soniya» ko'rinishida chiroyli yozadi."""
    seconds = int(seconds or 0)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    parts = []
    if h:
        parts.append(f"{h} soat")
    if m:
        parts.append(f"{m} daqiqa")
    if s or not parts:
        parts.append(f"{s} soniya")
    return " ".join(parts)

PERIOD_TITLES = {
    "day": "📅 Bugun",
    "yesterday": "📅 Kecha",
    "week": "🗓 Oxirgi 7 kun",
    "month": "📆 Oxirgi 30 kun",
}


def _is_mobile_worker(user, profile=None):
    """HR, texnik xodim va haydovchilar «harakatdagi» xodimlar — ular istalgan
    filial/lokatsiyada ishga kelib-ketishi mumkin (ofisdan masofa tekshirilmaydi)."""
    role = (user or {}).get("role") if isinstance(user, dict) else None
    if role in (ROLE_HR, ROLE_TECH):
        return True
    pos = ((profile or {}).get("position") or "").lower()
    return "haydovchi" in pos or "driver" in pos


async def _detect_branch(lat, lon):
    """Yuborilgan lokatsiyaga qaysi filial mos kelishini aniqlaydi.

    HR/haydovchi istalgan filialdan lokatsiya yuborsa — koordinatasi bor
    filiallar ichidan eng yaqinini topamiz. Agar filial radiusi ichida
    bo'lsa «shu filialga keldi» deb aniq belgilaymiz, aks holda eng yaqin
    filialni taxminiy joylashuv sifatida qaytaramiz.

    (branch, dist_m, inside) qaytaradi. Koordinatali filial yo'q bo'lsa
    (None, None, False)."""
    best = None  # (dist, inside, branch)
    for br in await q.list_branches():
        if br.get("latitude") is None or br.get("longitude") is None:
            continue
        d = haversine_m(br["latitude"], br["longitude"], lat, lon)
        inside = d <= ((br.get("radius") or 150))
        cand = (d, not inside, br)  # radius ichidagilar oldinroq saralanadi
        if best is None or cand[:2] < best[:2]:
            best = cand
    if not best:
        return None, None, False
    dist, not_inside, branch = best
    return branch, round(dist), (not not_inside)


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


def _hm_to_seconds(hm):
    """«HH:MM» yoki «HH:MM:SS» ni yarim tundan boshlab sekundga o'giradi."""
    parts = [int(x) for x in str(hm).split(":")]
    while len(parts) < 3:
        parts.append(0)
    h, m, s = parts[:3]
    return h * 3600 + m * 60 + s


def _is_late(work_hours, now_hm):
    start, _ = _parse_work_hours(work_hours)
    if not start:
        return False
    return now_hm > start


def _late_seconds(work_hours, now_hms):
    """Ish boshlanishidan qancha sekund kech kelinganini qaytaradi (0 => kech emas)."""
    start, _ = _parse_work_hours(work_hours)
    if not start:
        return 0
    diff = _hm_to_seconds(now_hms) - _hm_to_seconds(start)
    return diff if diff > 0 else 0


def _is_early(work_hours, now_hm):
    _, end = _parse_work_hours(work_hours)
    if not end:
        return False
    return now_hm < end


def _early_seconds(work_hours, now_hms):
    """Ish tugashidan qancha sekund erta ketilganini qaytaradi (0 => erta emas)."""
    _, end = _parse_work_hours(work_hours)
    if not end:
        return 0
    diff = _hm_to_seconds(end) - _hm_to_seconds(now_hms)
    return diff if diff > 0 else 0


def workday_seconds(work_hours):
    """Ish kunining davomiyligi (sekund). Aniqlanmasa 0.

    Tungi smena (end < start) uchun 24 soatdan oshirib hisoblanadi."""
    start, end = _parse_work_hours(work_hours)
    if not start or not end:
        return 0
    diff = _hm_to_seconds(end) - _hm_to_seconds(start)
    if diff <= 0:
        diff += 24 * 3600
    return diff


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
@router.message(tf("btn.checkin"))
async def checkin_start(message: Message, state: FSMContext):
    profile = await q.get_employee_profile_by_tg(message.from_user.id)
    user = await q.get_user(message.from_user.id)
    if not profile and not _is_mobile_worker(user, profile):
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
    mobile = _is_mobile_worker(user, profile)

    branch = await q.get_branch(profile["branch_id"]) if profile and profile.get("branch_id") else None
    # Harakatdagi xodim (HR/haydovchi) emas — filial va joylashuv majburiy
    if not mobile:
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
    dist = None
    detected_inside = False
    # Harakatdagi xodim (HR/haydovchi) — yuborgan lokatsiyasiga eng yaqin filialni
    # aniqlaymiz va «shu filialga keldi» deb belgilaymiz
    if mobile:
        det_branch, det_dist, detected_inside = await _detect_branch(lat, lon)
        if det_branch:
            branch = det_branch
            dist = det_dist
    if branch and branch.get("latitude") is not None and branch.get("longitude") is not None and dist is None:
        dist = haversine_m(branch["latitude"], branch["longitude"], lat, lon)
    radius = (branch.get("radius") if branch else None) or 150

    # Harakatdagi xodim uchun masofa tekshirilmaydi — istalgan joyda qabul qilinadi
    accepted = mobile or (dist is not None and dist <= radius)

    if accepted:
        now_hms = now_tk().strftime("%H:%M:%S")
        late_sec = _late_seconds((profile or {}).get("work_hours"), now_hms)
        late = late_sec > 0
        await q.add_attendance(
            user["id"], branch["id"] if branch else None, lat, lon, dist,
            status="present", late=late, late_seconds=late_sec,
        )
        row = await q.get_attendance_today(message.from_user.id)
        late_note = (
            f"\n⚠️ <b>Kech keldingiz:</b> {_fmt_hms(late_sec)}." if late else ""
        )
        if mobile:
            if branch and detected_inside:
                loc_line = f"📍 Lokatsiya: <b>{branch['name']}</b> filialidan qabul qilindi"
            elif branch:
                loc_line = (f"📍 Lokatsiya: eng yaqin filial — <b>{branch['name']}</b> "
                            f"(~{dist} m)")
            else:
                loc_line = "📍 Lokatsiya: qabul qilindi (istalgan filialdan)"
        else:
            loc_line = f"📏 Ofisgacha masofa: ~{dist} m"
        arrive_line = (
            f"\n✅ Siz <b>{branch['name']}</b> filialiga keldingiz." if mobile and branch else ""
        )
        await message.answer(
            "✅ <b>Keldingiz belgilandi!</b>\n\n"
            f"🏢 Filial: {branch['name'] if branch else '— (harakatda)'}\n"
            f"🕐 Kelgan vaqt: {row.get('time') if row else '-'}\n"
            f"{loc_line}"
            f"{arrive_line}"
            f"{late_note}\n\n"
            "Ish tugagach «🏁 Ishdan ketdim» tugmasini bosishni unutmang.",
            reply_markup=menu,
        )
        await q.add_log(
            message.from_user.id, user.get("full_name") if user else "?",
            "ishga_keldi",
            f"{branch['name'] if branch else 'harakatda'} · "
            f"{dist if dist is not None else '—'}m{' · kech' if late else ''}"
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
@router.message(tf("btn.checkout"))
async def checkout_start(message: Message, state: FSMContext):
    profile = await q.get_employee_profile_by_tg(message.from_user.id)
    user = await q.get_user(message.from_user.id)
    if not profile and not _is_mobile_worker(user, profile):
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
    mobile = _is_mobile_worker(user, profile)
    branch = await q.get_branch(profile["branch_id"]) if profile and profile.get("branch_id") else None
    lat = message.location.latitude
    lon = message.location.longitude
    dist = None
    detected_inside = False
    # Harakatdagi xodim — ketishda ham lokatsiyaga eng yaqin filialni aniqlaymiz
    if mobile:
        det_branch, det_dist, detected_inside = await _detect_branch(lat, lon)
        if det_branch:
            branch = det_branch
            dist = det_dist
    if branch and branch.get("latitude") is not None and dist is None:
        dist = haversine_m(branch["latitude"], branch["longitude"], lat, lon)
    now_hm = now_tk_hm()
    now_hms = now_tk().strftime("%H:%M:%S")
    early_sec = _early_seconds((profile or {}).get("work_hours"), now_hms)
    early = early_sec > 0
    await q.set_attendance_checkout(
        today["id"], lat, lon, dist, early=early, early_seconds=early_sec,
    )
    early_note = (
        f"\n⚠️ <b>Erta ketdingiz:</b> {_fmt_hms(early_sec)}." if early else ""
    )
    finish_line = ""
    if mobile and branch:
        if detected_inside:
            finish_line = f"\n🏢 Siz <b>{branch['name']}</b> filialidan ishni yakunladingiz."
        else:
            finish_line = (f"\n🏢 Ishni yakunladingiz · eng yaqin filial — "
                           f"<b>{branch['name']}</b> (~{dist} m).")
    await message.answer(
        "🏁 <b>Ketganingiz belgilandi!</b>\n\n"
        f"🕐 Kelgan vaqt: {today.get('time') or '-'}\n"
        f"🕐 Ketgan vaqt: {now_hm}"
        f"{finish_line}"
        f"{early_note}",
        reply_markup=menu,
    )
    await q.add_log(
        message.from_user.id, user.get("full_name") if user else "?",
        "ishdan_ketdi",
        f"{branch['name'] + ' · ' if mobile and branch else ''}"
        f"{now_hm}{' · erta' if early else ''}"
    )


@router.message(AttendanceForm.checkout, F.text)
async def checkout_need_location(message: Message):
    await message.answer(
        "❗️ Matn emas — <b>joylashuv</b> yuboring.",
        reply_markup=kb.attendance_location_kb(),
    )


# ================= TANAFFUS (BREAK) =================
@router.message(tf("btn.break"))
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


@router.message(tf("btn.resume"))
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
@router.message(tf("btn.profile"))
async def my_profile(message: Message):
    profile = await q.get_employee_profile_by_tg(message.from_user.id)
    if not profile:
        await message.answer("Profil topilmadi. HR bilan bog'laning.")
        return
    extra = ""
    today = await q.get_attendance_today(message.from_user.id)
    if today and today.get("status") == "present":
        extra += f"\n\n📍 Bugun: ✅ Kelgan ({today.get('time') or '-'})"
        if today.get("on_break"):
            extra += "\n⏸ Hozir tanaffusdasiz"
        if today.get("break_seconds"):
            extra += f"\n⏸ Bugungi tanaffus: {fmt_duration(today.get('break_seconds'))}"
    else:
        extra += "\n\n📍 Bugun: ⏳ Hali belgilanmagan"
    # oxirgi kelishlar
    history = await q.attendance_history(profile["user_id"], limit=7)
    if history:
        extra += "\n\n<b>Oxirgi kelishlar:</b>\n"
        for h in history:
            extra += f"  • {fmt_date(h.get('date'))} {h.get('time') or ''}\n"
    # Profil rasmi bo'lsa — rasm bilan birga chiqadi
    await send_employee_profile(message, profile, suffix=extra)


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
    show_branch = scope != "mgr"

    title = PERIOD_TITLES.get(period, period)
    absent_cnt = max(total_emp - len(present), 0)
    lines = [
        f"📍 <b>DAVOMAT HISOBOTI</b> · {title}",
        f"🏢 {branch_label}",
        "━━━━━━━━━━━━━━━━━━",
        f"👥 Jami xodim: <b>{total_emp}</b>",
        f"✅ Kelgan: <b>{len(present)}</b>   ❌ Kelmagan: <b>{absent_cnt}</b>",
        "",
    ]
    if present:
        lines.append(f"✅ <b>KELGANLAR</b> — {len(present)} ta")
        lines.append("━━━━━━━━━━━━━━━━━━")
        for i, p in enumerate(present[:60], 1):
            name = p.get("full_name") or p.get("tg_id")
            meta = []
            if show_branch and p.get("branch_name"):
                meta.append(f"🏢 {p['branch_name']}")
            meta.append(f"📆 {p['days']} kun")
            if p.get("lates"):
                meta.append(f"⏰ kech {p['lates']}")
            if p.get("earlies"):
                meta.append(f"🏃 erta {p['earlies']}")
            lines.append(f"<b>{i}.</b> {name}")
            lines.append(f"     {' · '.join(meta)}")
    else:
        lines.append("Bu davrda hech kim kelmagan.")

    # Kunlik ko'rinishda: kelgan/ketgan vaqtlar
    if period == "day":
        detail = await q.attendance_detail(period="day", branch_id=branch_id)
        if detail:
            lines.append("")
            lines.append("🕐 <b>BUGUNGI KIRISH / CHIQISH</b>")
            lines.append("━━━━━━━━━━━━━━━━━━")
            for i, d in enumerate(detail[:60], 1):
                out = d.get("out_time") or "…"
                marks = ""
                if d.get("late"):
                    marks += " ⏰"
                if d.get("early"):
                    marks += " 🏃"
                lines.append(
                    f"<b>{i}.</b> {d.get('full_name')}\n"
                    f"     🟢 {d.get('time') or '-'} → 🔴 {out}{marks}"
                )
        absent = await q.attendance_absent_today(branch_id=branch_id)
        lines.append("")
        lines.append(f"❌ <b>BUGUN KELMAGANLAR</b> — {len(absent)} ta")
        lines.append("━━━━━━━━━━━━━━━━━━")
        if absent:
            for i, a in enumerate(absent[:60], 1):
                name = a.get("full_name") or a.get("tg_id")
                br = (f" · 🏢 {a['branch_name']}"
                      if show_branch and a.get("branch_name") else "")
                lines.append(f"<b>{i}.</b> {name}{br}")
        else:
            lines.append("🎉 Hamma kelgan!")

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
    lines = [
        f"⏰ <b>KECH / ERTA HISOBOT</b> · {title}",
        "━━━━━━━━━━━━━━━━━━",
    ]
    if rows:
        late_cnt = sum(1 for r in rows if r.get("late"))
        early_cnt = sum(1 for r in rows if r.get("early"))
        lines.append(
            f"⏰ Kech kelgan: <b>{late_cnt}</b>   🏃 Erta ketgan: <b>{early_cnt}</b>"
        )
        lines.append("")
        for i, r in enumerate(rows, 1):
            tag = []
            if r.get("late"):
                tag.append("⏰ kech kelgan")
            if r.get("early"):
                tag.append("🏃 erta ketgan")
            br = f" · 🏢 {r['branch_name']}" if r.get("branch_name") else ""
            lines.append(f"<b>{i}.</b> {r.get('full_name')}{br}")
            lines.append(
                f"     📅 {fmt_date(r.get('date'))} · "
                f"🟢 {r.get('time') or '-'} → 🔴 {r.get('out_time') or '…'}"
            )
            lines.append(f"     {' · '.join(tag)}")
    else:
        lines.append("✅ Bu davrda kech/erta holatlar yo'q. 👍")
    for chunk in _split("\n".join(lines)):
        await call.message.answer(chunk)
    await call.answer()


# ================= FILIAL / BITTA XODIM BO'YICHA DAVOMAT (HR) =================
def _att_pick_allowed(user):
    """Faqat HR/admin/buxgalter bu bo'limni ko'ra oladi."""
    return _scope_for_user(user) == "hr"


def _att_marks(d):
    """Kech/erta belgilarini ro'yxat qilib qaytaradi (emoji bilan)."""
    marks = []
    if d.get("late"):
        marks.append(
            f"⏰ kech {_fmt_hms(d.get('late_seconds'))}" if d.get("late_seconds")
            else "⏰ kech keldi"
        )
    if d.get("early"):
        marks.append(
            f"🏃 erta {_fmt_hms(d.get('early_seconds'))}" if d.get("early_seconds")
            else "🏃 erta ketdi"
        )
    return marks


def _one_day_lines(d, show_date=False):
    """Bitta kun davomatini o'qib bo'ladigan qilib chizadi:
    kelgan / ketgan vaqt, tanaffus, kech/erta."""
    out = d.get("out_time") or "⏳ ishda"
    ls = []
    if show_date:
        ls.append(f"   📅 <b>{fmt_date(d.get('date'))}</b>")
    ls.append(f"   🟢 Keldi: <b>{d.get('time') or '-'}</b>   "
              f"🔴 Ketdi: <b>{out}</b>")
    if d.get("break_seconds"):
        ls.append(f"   ⏸ Tanaffus: {_fmt_hms(d.get('break_seconds'))}")
    marks = _att_marks(d)
    if marks:
        ls.append("   " + " · ".join(marks))
    return ls


async def _send_chunks(target, text, markup=None):
    """Uzun matnni bo'lib yuboradi; tugmalarni oxirgi bo'lakka biriktiradi."""
    chunks = _split(text)
    for i, chunk in enumerate(chunks):
        await target.answer(
            chunk, reply_markup=markup if i == len(chunks) - 1 else None
        )


def _group_by_user(rows):
    """Yozuvlarni xodim bo'yicha guruhlaydi (tartibni saqlab)."""
    groups, order = {}, []
    for r in rows:
        uid = r.get("user_id")
        if uid not in groups:
            groups[uid] = []
            order.append(uid)
        groups[uid].append(r)
    return [(uid, groups[uid]) for uid in order]


# ---- «🏢 Filial davomati»: filial → davr → hisobot ----
@router.message(F.text == "🏢 Filial davomati")
async def branch_att_menu(message: Message):
    user = await q.get_user(message.from_user.id)
    if not _att_pick_allowed(user):
        await message.answer("⛔ Sizda bu bo'limni ko'rish huquqi yo'q.")
        return
    branches = await q.list_branches()
    if not branches:
        await message.answer("🏢 Hozircha filiallar mavjud emas.")
        return
    await message.answer(
        "🏢 <b>Filial bo'yicha davomat</b>\nQaysi filialni ko'rasiz?",
        reply_markup=kb.att_pick_branches_kb(branches, "hbatt"),
    )


@router.callback_query(F.data.startswith("hbatt:"))
async def branch_att_cb(call: CallbackQuery):
    user = await q.get_user(call.from_user.id)
    if not _att_pick_allowed(user):
        await call.answer("⛔", show_alert=True)
        return
    parts = call.data.split(":")
    action = parts[1]

    if action == "back":
        branches = await q.list_branches()
        await call.message.edit_text(
            "🏢 <b>Filial bo'yicha davomat</b>\nQaysi filialni ko'rasiz?",
            reply_markup=kb.att_pick_branches_kb(branches, "hbatt"),
        )
        await call.answer()
        return

    if action == "br":
        branch = await q.get_branch(int(parts[2]))
        if not branch:
            await call.answer("Filial topilmadi", show_alert=True)
            return
        await call.message.edit_text(
            f"🏢 <b>{branch['name']}</b>\nDavrni tanlang:",
            reply_markup=kb.att_branch_period_pick_kb(branch["id"]),
        )
        await call.answer()
        return

    if action == "p":
        branch = await q.get_branch(int(parts[2]))
        period = parts[3]
        if not branch:
            await call.answer("Filial topilmadi", show_alert=True)
            return
        await _render_branch_attendance(call.message, branch, period)
        await call.answer()
        return

    if action == "xl":
        branch = await q.get_branch(int(parts[2]))
        period = parts[3]
        if not branch:
            await call.answer("Filial topilmadi", show_alert=True)
            return
        await call.answer("📊 Excel tayyorlanmoqda…")
        await _send_branch_excel(call, branch, period)


async def _render_branch_attendance(target, branch, period):
    detail = await q.attendance_detail(period=period, branch_id=branch["id"], limit=300)
    title = PERIOD_TITLES.get(period, period)
    show_date = period != "day"
    groups = _group_by_user(detail)

    absent = []
    if period == "day":
        absent = await q.attendance_absent_today(branch_id=branch["id"])

    lines = [
        f"🏢 <b>{branch['name']}</b>",
        f"📊 Davomat hisoboti · {title}",
        "━━━━━━━━━━━━━━━━━━━━━",
        f"👥 Kelgan: <b>{len(groups)}</b>"
        + (f"    ❌ Kelmagan: <b>{len(absent)}</b>" if period == "day" else ""),
        "",
    ]
    if not groups:
        lines.append("😴 Bu davrda hech kim kelmagan.")
    else:
        for i, (_uid, recs) in enumerate(groups, 1):
            name = recs[0].get("full_name") or recs[0].get("tg_id")
            lines.append(f"<b>{i}.</b> 👤 <b>{name}</b>")
            for d in recs:
                lines += _one_day_lines(d, show_date=show_date)
            lines.append("")

    if period == "day":
        lines.append("━━━━━━━━━━━━━━━━━━━━━")
        lines.append(f"❌ <b>Kelmaganlar</b> ({len(absent)})")
        if absent:
            for a in absent:
                lines.append(f"   • {a.get('full_name') or a.get('tg_id')}")
        else:
            lines.append("   🎉 Hamma kelgan!")

    await _send_chunks(
        target, "\n".join(lines),
        markup=kb.att_branch_report_kb(branch["id"], period),
    )


def _branch_excel_rows(groups, show_date):
    """attendance_detail guruhlaridan Excel qatorlarini tayyorlaydi."""
    rows_data = []
    for gi, (_uid, recs) in enumerate(groups, 1):
        name = recs[0].get("full_name") or recs[0].get("tg_id") or "-"
        for j, d in enumerate(recs):
            rows_data.append({
                "no": gi if j == 0 else "",
                "grp": gi,
                "name": name if j == 0 else "",
                "date": fmt_date(d.get("date")),
                "came": d.get("time") or "-",
                "out": d.get("out_time") or "…",
                "brk": _fmt_hms(d.get("break_seconds")) if d.get("break_seconds") else "-",
                "note": " · ".join(_att_marks(d)) or "-",
            })
    return rows_data


async def _send_branch_excel(call, branch, period):
    detail = await q.attendance_detail(period=period, branch_id=branch["id"], limit=300)
    groups = _group_by_user(detail)
    rows_data = _branch_excel_rows(groups, period != "day")
    absent_names = None
    if period == "day":
        absent = await q.attendance_absent_today(branch_id=branch["id"])
        absent_names = [a.get("full_name") or a.get("tg_id") for a in absent]
    title = PERIOD_TITLES.get(period, period)
    doc = export.build_branch_attendance_xlsx(
        branch["name"], title, rows_data, absent_names,
    )
    await call.message.answer_document(
        doc,
        caption=(f"📊 <b>{branch['name']}</b> davomati\n"
                 f"🗓 {title} · 👥 {len(groups)} xodim"),
    )


# ---- «👤 Xodim davomati»: filial → xodim → davr → hisobot ----
@router.message(F.text == "👤 Xodim davomati")
async def emp_att_menu(message: Message):
    user = await q.get_user(message.from_user.id)
    if not _att_pick_allowed(user):
        await message.answer("⛔ Sizda bu bo'limni ko'rish huquqi yo'q.")
        return
    branches = await q.list_branches()
    if not branches:
        await message.answer("🏢 Hozircha filiallar mavjud emas.")
        return
    await message.answer(
        "👤 <b>Bitta xodim davomati</b>\nAvval filialni tanlang:",
        reply_markup=kb.att_pick_branches_kb(branches, "heatt"),
    )


async def _show_emp_list(target, branch_id, edit=False):
    branch = await q.get_branch(branch_id)
    emps = await q.list_employee_profiles(branch_id=branch_id)
    if not emps:
        text = f"🏢 <b>{branch['name'] if branch else '—'}</b>\nBu filialda xodim yo'q."
        if edit:
            await target.edit_text(text)
        else:
            await target.answer(text)
        return
    text = (f"🏢 <b>{branch['name'] if branch else '—'}</b>\n"
            "Xodimni tanlang:")
    markup = kb.att_emp_list_kb(emps, branch_id)
    if edit:
        await target.edit_text(text, reply_markup=markup)
    else:
        await target.answer(text, reply_markup=markup)


@router.callback_query(F.data.startswith("heatt:"))
async def emp_att_cb(call: CallbackQuery):
    user = await q.get_user(call.from_user.id)
    if not _att_pick_allowed(user):
        await call.answer("⛔", show_alert=True)
        return
    parts = call.data.split(":")
    action = parts[1]

    if action == "back":
        branches = await q.list_branches()
        await call.message.edit_text(
            "👤 <b>Bitta xodim davomati</b>\nAvval filialni tanlang:",
            reply_markup=kb.att_pick_branches_kb(branches, "heatt"),
        )
        await call.answer()
        return

    if action == "br":
        await _show_emp_list(call.message, int(parts[2]), edit=True)
        await call.answer()
        return

    if action == "eback":
        prof = await q.get_employee_profile(int(parts[2]))
        if prof and prof.get("branch_id"):
            await _show_emp_list(call.message, prof["branch_id"], edit=True)
        else:
            branches = await q.list_branches()
            await call.message.edit_text(
                "👤 <b>Bitta xodim davomati</b>\nAvval filialni tanlang:",
                reply_markup=kb.att_pick_branches_kb(branches, "heatt"),
            )
        await call.answer()
        return

    if action == "emp":
        prof = await q.get_employee_profile(int(parts[2]))
        if not prof:
            await call.answer("Xodim topilmadi", show_alert=True)
            return
        await call.message.edit_text(
            f"👤 <b>{prof.get('full_name')}</b>\n"
            f"🏢 {prof.get('branch_name') or '—'}\n"
            "Davrni tanlang:",
            reply_markup=kb.att_emp_period_pick_kb(prof["user_id"]),
        )
        await call.answer()
        return

    if action == "p":
        prof = await q.get_employee_profile(int(parts[2]))
        period = parts[3]
        if not prof:
            await call.answer("Xodim topilmadi", show_alert=True)
            return
        await _render_employee_attendance(call.message, prof, period)
        await call.answer()
        return

    if action == "xl":
        prof = await q.get_employee_profile(int(parts[2]))
        period = parts[3]
        if not prof:
            await call.answer("Xodim topilmadi", show_alert=True)
            return
        await call.answer("📊 Excel tayyorlanmoqda…")
        await _send_employee_excel(call, prof, period)


def _emp_summary(rows):
    return {
        "days": len(rows),
        "lates": sum(1 for r in rows if r.get("late")),
        "earlies": sum(1 for r in rows if r.get("early")),
        "total_break_sec": sum(int(r.get("break_seconds") or 0) for r in rows),
    }


async def _render_employee_attendance(target, prof, period):
    rows = await q.attendance_for_user(prof["user_id"], period=period)
    title = PERIOD_TITLES.get(period, period)
    s = _emp_summary(rows)
    pos = f" · 💼 {prof.get('position')}" if prof.get("position") else ""
    lines = [
        f"👤 <b>{prof.get('full_name')}</b>",
        f"🏢 {prof.get('branch_name') or '—'}{pos}",
        f"📊 Davomat · {title}",
        "━━━━━━━━━━━━━━━━━━━━━",
        f"✅ Kelgan kunlar: <b>{s['days']}</b>",
        f"⏰ Kech: <b>{s['lates']}</b>    🏃 Erta: <b>{s['earlies']}</b>",
    ]
    if s["total_break_sec"]:
        lines.append(f"⏸ Umumiy tanaffus: <b>{_fmt_hms(s['total_break_sec'])}</b>")
    lines.append("━━━━━━━━━━━━━━━━━━━━━")
    lines.append("")
    if not rows:
        lines.append("😴 Bu davrda davomat yozuvi yo'q.")
    else:
        show_date = period != "day"
        for i, d in enumerate(rows, 1):
            head = f"<b>{i}.</b> 📅 <b>{fmt_date(d.get('date'))}</b>" if show_date else f"<b>{i}.</b>"
            lines.append(head)
            lines += _one_day_lines(d, show_date=False)
            lines.append("")

    await _send_chunks(
        target, "\n".join(lines),
        markup=kb.att_emp_report_kb(prof["user_id"], period),
    )


async def _send_employee_excel(call, prof, period):
    rows = await q.attendance_for_user(prof["user_id"], period=period)
    s = _emp_summary(rows)
    title = PERIOD_TITLES.get(period, period)
    rows_data = [{
        "date": fmt_date(d.get("date")),
        "came": d.get("time") or "-",
        "out": d.get("out_time") or "…",
        "brk": _fmt_hms(d.get("break_seconds")) if d.get("break_seconds") else "-",
        "note": " · ".join(_att_marks(d)) or "-",
    } for d in rows]
    summary = {
        "days": s["days"], "lates": s["lates"], "earlies": s["earlies"],
        "total_break": _fmt_hms(s["total_break_sec"]) if s["total_break_sec"] else None,
    }
    doc = export.build_employee_attendance_xlsx(
        prof.get("full_name") or "Xodim", prof.get("branch_name"),
        prof.get("position"), title, summary, rows_data,
    )
    await call.message.answer_document(
        doc,
        caption=(f"📊 <b>{prof.get('full_name')}</b> davomati\n"
                 f"🗓 {title} · ✅ {s['days']} kun"),
    )


# ================= DAVOMATNI TAHRIRLASH (HR) =================
def _parse_hhmm(text):
    """Kiritilgan vaqtni 'HH:MM:00' ko'rinishiga keltiradi. Xato bo'lsa None.
    Qabul qiladi: 9:00, 09:00, 9.00, 9-00, 0900, 9."""
    t = (text or "").strip()
    m = re.match(r"^(\d{1,2})[:.\-\s]?(\d{2})$", t)
    if m:
        h, mi = int(m.group(1)), int(m.group(2))
    else:
        m2 = re.match(r"^(\d{1,2})$", t)
        if not m2:
            return None
        h, mi = int(m2.group(1)), 0
    if h > 23 or mi > 59:
        return None
    return f"{h:02d}:{mi:02d}:00"


def _period_dates(period):
    """Hafta/oy uchun ISO sanalar ro'yxati (bugundan orqaga)."""
    today = now_tk().date()
    n = 7 if period == "week" else 30
    return [(today - timedelta(days=i)).isoformat() for i in range(n)]


@router.message(F.text == "✏️ Davomatni tahrirlash")
async def att_edit_menu(message: Message, state: FSMContext):
    await state.clear()
    user = await q.get_user(message.from_user.id)
    if not _att_pick_allowed(user):
        await message.answer("⛔ Sizda bu bo'limni ko'rish huquqi yo'q.")
        return
    branches = await q.list_branches()
    if not branches:
        await message.answer("🏢 Hozircha filiallar mavjud emas.")
        return
    await message.answer(
        "✏️ <b>Davomatni tahrirlash</b>\nAvval filialni tanlang:",
        reply_markup=kb.att_pick_branches_kb(branches, "hedit"),
    )


async def _edit_show_emps(target, branch_id, edit=False):
    branch = await q.get_branch(branch_id)
    emps = await q.list_employee_profiles(branch_id=branch_id)
    send = target.edit_text if edit else target.answer
    if not emps:
        await send(f"🏢 <b>{branch['name'] if branch else '—'}</b>\n"
                   "Bu filialda xodim yo'q.")
        return
    await send(
        f"🏢 <b>{branch['name'] if branch else '—'}</b>\n"
        "Tahrirlash uchun xodimni tanlang:",
        reply_markup=kb.att_edit_emp_list_kb(emps, branch_id),
    )


async def _edit_show_period(target, prof, edit=True):
    send = target.edit_text if edit else target.answer
    await send(
        f"✏️ <b>{prof.get('full_name')}</b>\n"
        f"🏢 {prof.get('branch_name') or '—'}\n"
        "Qaysi davr davomatini tahrirlaysiz?",
        reply_markup=kb.att_edit_period_kb(prof["user_id"]),
    )


async def _edit_show_day(target, prof, period, iso, edit=True):
    rec = await q.get_attendance_by_date(prof["user_id"], iso)
    came = (rec or {}).get("time") or "— belgilanmagan"
    out = (rec or {}).get("out_time") or "— belgilanmagan"
    send = target.edit_text if edit else target.answer
    await send(
        f"✏️ <b>{prof.get('full_name')}</b>\n"
        f"📅 Sana: <b>{fmt_date(iso)}</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"🟢 Kelgan vaqt: <b>{came}</b>\n"
        f"🔴 Ketgan vaqt: <b>{out}</b>\n\n"
        "Qaysi vaqtni o'zgartirasiz?",
        reply_markup=kb.att_edit_day_kb(prof["user_id"], period, iso),
    )


@router.callback_query(F.data.startswith("hedit:"))
async def att_edit_cb(call: CallbackQuery, state: FSMContext):
    user = await q.get_user(call.from_user.id)
    if not _att_pick_allowed(user):
        await call.answer("⛔", show_alert=True)
        return
    parts = call.data.split(":")
    action = parts[1]

    if action == "back":
        await state.clear()
        branches = await q.list_branches()
        await call.message.edit_text(
            "✏️ <b>Davomatni tahrirlash</b>\nAvval filialni tanlang:",
            reply_markup=kb.att_pick_branches_kb(branches, "hedit"),
        )
        await call.answer()
        return

    if action == "br":
        await _edit_show_emps(call.message, int(parts[2]), edit=True)
        await call.answer()
        return

    if action == "eback":
        prof = await q.get_employee_profile(int(parts[2]))
        if prof and prof.get("branch_id"):
            await _edit_show_emps(call.message, prof["branch_id"], edit=True)
        else:
            branches = await q.list_branches()
            await call.message.edit_text(
                "✏️ <b>Davomatni tahrirlash</b>\nAvval filialni tanlang:",
                reply_markup=kb.att_pick_branches_kb(branches, "hedit"),
            )
        await call.answer()
        return

    if action == "emp":
        prof = await q.get_employee_profile(int(parts[2]))
        if not prof:
            await call.answer("Xodim topilmadi", show_alert=True)
            return
        await _edit_show_period(call.message, prof)
        await call.answer()
        return

    if action == "pd":
        uid = int(parts[2])
        period = parts[3]
        prof = await q.get_employee_profile(uid)
        if not prof:
            await call.answer("Xodim topilmadi", show_alert=True)
            return
        if period in ("day", "yesterday"):
            day = now_tk().date()
            if period == "yesterday":
                day = day - timedelta(days=1)
            await _edit_show_day(call.message, prof, period, day.isoformat())
        else:
            recs = await q.attendance_for_user(uid, period=period)
            have = {r.get("date") for r in recs}
            days = [(iso, fmt_date(iso), iso in have) for iso in _period_dates(period)]
            title = "1 hafta" if period == "week" else "1 oy"
            await call.message.edit_text(
                f"✏️ <b>{prof.get('full_name')}</b> · {title}\n"
                "Tahrirlash uchun kunni tanlang:\n"
                "✅ — davomat bor · ▫️ — bo'sh",
                reply_markup=kb.att_edit_days_kb(uid, period, days),
            )
        await call.answer()
        return

    if action == "day":
        uid = int(parts[2])
        period = parts[3]
        iso = parts[4]
        prof = await q.get_employee_profile(uid)
        if not prof:
            await call.answer("Xodim topilmadi", show_alert=True)
            return
        await _edit_show_day(call.message, prof, period, iso)
        await call.answer()
        return

    if action == "set":
        uid = int(parts[2])
        period = parts[3]
        iso = parts[4]
        which = parts[5]
        prof = await q.get_employee_profile(uid)
        if not prof:
            await call.answer("Xodim topilmadi", show_alert=True)
            return
        field = "time" if which == "in" else "out_time"
        await state.set_state(AttendanceEditForm.value)
        await state.update_data(
            edit_uid=uid, edit_period=period, edit_iso=iso,
            edit_field=field, edit_branch=prof.get("branch_id"),
        )
        label = "🟢 kelgan" if which == "in" else "🔴 ketgan"
        await call.message.answer(
            f"✏️ <b>{prof.get('full_name')}</b> · 📅 {fmt_date(iso)}\n\n"
            f"{label} vaqtni kiriting. Masalan: <b>09:00</b>"
        )
        await call.answer()
        return


@router.message(AttendanceEditForm.value, F.text)
async def att_edit_value(message: Message, state: FSMContext):
    data = await state.get_data()
    hhmm = _parse_hhmm(message.text)
    if not hhmm:
        await message.answer(
            "❗️ Vaqt formati noto'g'ri. Masalan: <b>09:00</b>. Qayta kiriting:"
        )
        return
    uid = data["edit_uid"]
    iso = data["edit_iso"]
    field = data["edit_field"]
    period = data.get("edit_period", "day")
    await q.upsert_attendance_time(
        uid, iso, field, hhmm, branch_id=data.get("edit_branch")
    )
    await state.clear()
    prof = await q.get_employee_profile(uid)
    label = "🟢 Kelgan" if field == "time" else "🔴 Ketgan"
    await message.answer(
        f"✅ {label} vaqt saqlandi: <b>{hhmm}</b>\n"
        f"👤 {prof.get('full_name') if prof else uid} · 📅 {fmt_date(iso)}"
    )
    if prof:
        await _edit_show_day(message, prof, period, iso, edit=False)
