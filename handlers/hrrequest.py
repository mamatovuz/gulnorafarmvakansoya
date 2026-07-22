"""«📩 HR ga murojaat» — xodimning HR bo'limiga murojaat qilish bo'limi.

Xodim asosiy menyudagi tugmani bosganda 3 ta yo'nalish chiqadi:
  🕒 Ish soatini o'zgartirish — yangi ish vaqti yoziladi, HR tasdiqlaydi.
  💸 Maoshni oshirishni so'rash — avvalgidek ishlaydi (handlers/salaryraise.py).
  ✉️ Boshqa masalada — erkin matn HR/Adminlarga yuboriladi.

Ish vaqti tasdiqlangach xodim profilidagi `work_hours` yangilanadi — «📍 Ishga
keldim» / «🏁 Ishdan ketdim» kech qolish va erta ketishni aynan shu yangi
vaqtdan hisoblaydi.
"""
import re

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from database import queries as q
from database.db import ROLE_HR, ROLE_ADMIN, ROLE_CANDIDATE
from states import WorkHoursForm, HRMessageForm
import keyboards as kb
from utils import safe_send, broadcast_request, close_request_notices
from handlers.salaryraise import start_raise_flow

router = Router()

# «09:00 - 18:00», «9-18», «08:00-17:00» — faqat sonlar bilan yoziladi
HOURS_RE = re.compile(r"^\s*(\d{1,2})(?::(\d{2}))?\s*[-–—]\s*(\d{1,2})(?::(\d{2}))?\s*$")

HOURS_ASK = (
    "🕒 <b>Ish soatini o'zgartirish</b>\n\n"
    "Nechidan nechigacha ishlamoqchisiz? <b>Faqat sonlarda</b> yozing.\n"
    "Format: <b>soat - soat</b>\n"
    "Misol: <code>09:00 - 18:00</code> yoki <code>9-18</code>"
)


def parse_hours(text):
    """Matndan («09:00 - 18:00») (boshlanish, tugash) qaytaradi. Noto'g'ri — None."""
    m = HOURS_RE.match(text or "")
    if not m:
        return None
    h1, m1, h2, m2 = m.group(1), m.group(2) or "00", m.group(3), m.group(4) or "00"
    h1, m1, h2, m2 = int(h1), int(m1), int(h2), int(m2)
    if not (0 <= h1 <= 23 and 0 <= h2 <= 23 and 0 <= m1 <= 59 and 0 <= m2 <= 59):
        return None
    start, end = f"{h1:02d}:{m1:02d}", f"{h2:02d}:{m2:02d}"
    if start == end:
        return None
    return start, end


def merge_shift_prefix(old_hours, new_hours):
    """Eski qiymatdagi smena nomini («🌙 Kechki smena · 14:00 - 00:00») saqlaydi."""
    if old_hours and "·" in old_hours:
        prefix = old_hours.split("·")[0].strip()
        if prefix:
            return f"{prefix} · {new_hours}"
    return new_hours


async def _is_staff(tg_id):
    u = await q.get_user(tg_id)
    return u and u["role"] in (ROLE_HR, ROLE_ADMIN)


async def _notify_hr(bot: Bot, text, markup=None, ref_id=None):
    """HR/adminlarga xabar. `ref_id` berilsa — kimdir ko'rib chiqqach qolgan
    HR lardagi xabar avtomatik o'chirilishi uchun yozib boriladi."""
    hr_ids = await q.all_user_tg_ids(role=ROLE_HR)
    admin_ids = await q.all_user_tg_ids(role=ROLE_ADMIN)
    targets = set(hr_ids + admin_ids)
    if ref_id:
        await broadcast_request(bot, "work_hours", ref_id, targets, text,
                                reply_markup=markup)
        return
    for tid in targets:
        await safe_send(bot, tid, text, reply_markup=markup)


async def _main_menu(message: Message, tg_id):
    """Xodimga o'z roliga mos asosiy menyu (callback ichida from_user — bot)."""
    user = await q.get_user(tg_id)
    role = user["role"] if user else ROLE_CANDIDATE
    await message.answer("🏠 Asosiy menyu", reply_markup=kb.main_menu(role))


def _hr_request_text(req):
    return (
        "🕒 <b>Ish vaqtini o'zgartirish so'rovi</b>\n"
        f"№ {req['id']}\n"
        "━━━━━━━━━━━━\n"
        f"🏢 Filial: <b>{req.get('branch_name') or '-'}</b>\n"
        f"💼 Lavozim: <b>{req.get('position') or '-'}</b>\n"
        f"👤 Xodim: {req.get('full_name') or '-'}\n"
        "━━━━━━━━━━━━\n"
        f"🕓 Hozirgi ish vaqti: {req.get('current_hours') or 'belgilanmagan'}\n"
        f"🆕 Ishlamoqchi bo'lgan vaqti: <b>{req.get('requested_hours') or '-'}</b>\n\n"
        "Tasdiqlaysizmi yoki rad etasizmi?"
    )


# ================= XODIM: MUROJAAT MENYUSI =================
# Eski «💸 HR ga so'rov» tugmasi ham shu menyuni ochadi — foydalanuvchilarda
# klaviatura /start bosilgunicha eskiligicha qolishi mumkin.
@router.message(F.text.in_({kb.HR_REQUEST_BTN, "💸 HR ga so'rov"}))
async def hr_request_menu(message: Message, state: FSMContext):
    profile = await q.get_employee_profile_by_tg(message.from_user.id)
    if not profile:
        await message.answer("⛔ Bu bo'lim faqat tasdiqlangan xodimlar uchun.")
        return
    await state.clear()
    await message.answer(
        "📩 <b>HR ga murojaat</b>\n\nQaysi masalada murojaat qilmoqchisiz?",
        reply_markup=kb.hr_request_menu_kb(),
    )


@router.callback_query(F.data == "hrreq:salary")
async def hr_request_salary(call: CallbackQuery, state: FSMContext):
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await call.answer()
    await start_raise_flow(call.message, state, call.from_user.id)


# ---------------- 1) ISH SOATINI O'ZGARTIRISH ----------------
@router.callback_query(F.data == "hrreq:hours")
async def hr_request_hours(call: CallbackQuery, state: FSMContext):
    profile = await q.get_employee_profile_by_tg(call.from_user.id)
    if not profile:
        await call.answer("⛔ Xodim profili topilmadi.", show_alert=True)
        return
    pending = await q.get_pending_work_hour_for_user(profile["user_id"])
    if pending:
        await call.answer(
            "⏳ Sizda hali javob berilmagan ish vaqti so'rovi bor. HR javobini kuting.",
            show_alert=True,
        )
        return
    await state.clear()
    await state.set_state(WorkHoursForm.hours)
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await call.message.answer(
        f"🕓 Hozirgi ish vaqtingiz: <b>{profile.get('work_hours') or 'belgilanmagan'}</b>\n\n"
        + HOURS_ASK
    )
    await call.answer()


@router.message(WorkHoursForm.hours, F.text)
async def wh_hours_entered(message: Message, state: FSMContext):
    parsed = parse_hours(message.text)
    if not parsed:
        await message.answer(
            "❗️ Ish vaqti noto'g'ri yozildi.\n\n" + HOURS_ASK
        )
        return
    start, end = parsed
    hours = f"{start} - {end}"
    await state.update_data(wh_hours=hours, wh_start=start, wh_end=end)
    await state.set_state(None)  # vaqt FSM ma'lumotida, tugmalar kutilmoqda
    await message.answer(
        f"🕒 Siz soat <b>{start}</b> dan <b>{end}</b> gacha ishlamoqchisiz.\n\n"
        "Tasdiqlaysizmi?",
        reply_markup=kb.work_hours_confirm_kb(),
    )


@router.callback_query(F.data == "wh_edit")
async def wh_edit(call: CallbackQuery, state: FSMContext):
    await state.set_state(WorkHoursForm.hours)
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await call.message.answer("✏️ Ish vaqtini qayta yozing.\n\n" + HOURS_ASK)
    await call.answer()


@router.callback_query(F.data == "wh_cancel")
async def wh_cancel(call: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await call.message.answer("❌ Bekor qilindi.")
    await _main_menu(call.message, call.from_user.id)
    await call.answer()


@router.callback_query(F.data == "wh_ok")
async def wh_confirm(call: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    hours = data.get("wh_hours")
    if not hours:
        await state.clear()
        await call.answer("⏳ Sessiya tugagan. Qaytadan boshlang.", show_alert=True)
        return
    profile = await q.get_employee_profile_by_tg(call.from_user.id)
    if not profile:
        await state.clear()
        await call.answer("⛔ Xodim profili topilmadi.", show_alert=True)
        return
    await state.clear()
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    if await q.get_pending_work_hour_for_user(profile["user_id"]):
        await call.message.answer("⏳ Sizda allaqachon ochiq so'rov bor. HR javobini kuting.")
        await call.answer()
        return
    rid = await q.add_work_hour_request(
        user_id=profile["user_id"],
        branch_id=profile.get("branch_id"),
        position=profile.get("position"),
        current_hours=profile.get("work_hours"),
        requested_hours=hours,
    )
    me = await q.get_user(call.from_user.id)
    await q.add_log(
        call.from_user.id, me["full_name"] if me else "?",
        "ish_vaqti_sorovi", f"#{rid}: {hours}",
    )
    await call.message.answer(
        "📤 <b>So'rovingiz HR bo'limiga yuborildi!</b>\n\n"
        f"🕒 So'ralgan ish vaqti: <b>{hours}</b>\n"
        "HR javobini kuting."
    )
    await _main_menu(call.message, call.from_user.id)
    await call.answer("Yuborildi ✅")

    req = await q.get_work_hour_request(rid)
    await _notify_hr(bot, _hr_request_text(req),
                     markup=kb.hr_work_hours_actions_kb(rid), ref_id=rid)


# ---------------- 2) BOSHQA MASALADA ----------------
@router.callback_query(F.data == "hrreq:other")
async def hr_request_other(call: CallbackQuery, state: FSMContext):
    profile = await q.get_employee_profile_by_tg(call.from_user.id)
    if not profile:
        await call.answer("⛔ Xodim profili topilmadi.", show_alert=True)
        return
    await state.clear()
    await state.set_state(HRMessageForm.text)
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await call.message.answer(
        "✉️ HR bo'limiga yubormoqchi bo'lgan murojaatingizni yozing:"
    )
    await call.answer()


@router.message(HRMessageForm.text, F.text)
async def hr_request_other_send(message: Message, state: FSMContext, bot: Bot):
    text = message.text.strip()
    await state.clear()
    profile = await q.get_employee_profile_by_tg(message.from_user.id)
    user = await q.get_user(message.from_user.id)
    header = (
        "✉️ <b>Xodimdan murojaat</b>\n"
        "━━━━━━━━━━━━\n"
        f"👤 Xodim: {user.get('full_name') if user else '-'}\n"
        f"🏢 Filial: {(profile or {}).get('branch_name') or '-'}\n"
        f"💼 Lavozim: {(profile or {}).get('position') or '-'}\n"
        f"📱 Telefon: {(user or {}).get('phone') or '-'}\n"
        "━━━━━━━━━━━━\n"
    )
    await _notify_hr(bot, header + text)
    await q.add_log(message.from_user.id, message.from_user.full_name, "hr_murojaat", "")
    await message.answer("✅ Murojaatingiz HR bo'limiga yuborildi.")
    await _main_menu(message, message.from_user.id)


# ================= HR: ISH VAQTI SO'ROVLARI =================
@router.message(F.text == "🕒 Ish vaqti so'rovlari")
async def hr_work_hours_list(message: Message):
    if not await _is_staff(message.from_user.id):
        await message.answer("⛔ Sizda ruxsat yo'q.")
        return
    reqs = await q.list_pending_work_hour_requests(limit=30)
    if not reqs:
        await message.answer("🕒 Ochiq ish vaqti so'rovlari yo'q.")
        return
    await message.answer(
        f"🕒 <b>Ochiq ish vaqti so'rovlari</b>\n\nJami: <b>{len(reqs)}</b> ta\n"
        "Batafsil ko'rish uchun tanlang:",
        reply_markup=kb.work_hour_requests_list_kb(reqs),
    )


@router.callback_query(F.data.startswith("whview:"))
async def hr_work_hours_view(call: CallbackQuery):
    if not await _is_staff(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    rid = int(call.data.split(":")[1])
    req = await q.get_work_hour_request(rid)
    if not req:
        await call.answer("So'rov topilmadi.", show_alert=True)
        return
    markup = kb.hr_work_hours_actions_kb(rid) if req.get("status") == "pending" else None
    await call.message.answer(_hr_request_text(req), reply_markup=markup)
    await call.answer()


@router.callback_query(F.data.startswith("hrwh_ok:"))
async def hr_work_hours_approve(call: CallbackQuery, bot: Bot):
    if not await _is_staff(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    rid = int(call.data.split(":")[1])
    req = await q.get_work_hour_request(rid)
    if not req or req.get("status") != "pending":
        await call.answer("Bu so'rov allaqachon ko'rib chiqilgan.", show_alert=True)
        return
    me = await q.get_user(call.from_user.id)
    # ATOMIK — bir marta tasdiqlanadi
    if not await q.claim_request("work_hour_requests", rid, "approved",
                                 me["id"] if me else None, "pending"):
        try:
            await call.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        await call.answer("Bu so'rov allaqachon boshqa xodim tomonidan ko'rib chiqilgan.",
                          show_alert=True)
        return
    await close_request_notices(bot, "work_hours", rid, keep_chat_id=call.from_user.id)
    new_hours = merge_shift_prefix(req.get("current_hours"), req.get("requested_hours"))
    await q.update_work_hours(req["user_id"], new_hours)
    await q.close_work_hour_request(rid, "approved", handled_by=me["id"] if me else None)
    await q.add_log(
        call.from_user.id, me["full_name"] if me else "?",
        "ish_vaqti_tasdiq", f"#{rid}: {new_hours}",
    )
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await call.message.answer(
        f"✅ Ish vaqti so'rovi #{rid} tasdiqlandi.\n"
        f"👤 {req.get('full_name')} — yangi ish vaqti: <b>{new_hours}</b>"
    )
    await call.answer("Tasdiqlandi ✅")
    if req.get("user_tg"):
        await safe_send(
            bot, req["user_tg"],
            "✅ <b>Ish vaqtingiz o'zgartirildi!</b>\n\n"
            f"🕒 Yangi ish vaqtingiz: <b>{new_hours}</b>\n\n"
            "Endi «📍 Ishga keldim» va «🏁 Ishdan ketdim» aynan shu vaqtdan "
            "hisoblanadi.",
        )


@router.callback_query(F.data.startswith("hrwh_rej:"))
async def hr_work_hours_reject_start(call: CallbackQuery, state: FSMContext):
    if not await _is_staff(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    rid = int(call.data.split(":")[1])
    req = await q.get_work_hour_request(rid)
    if not req or req.get("status") != "pending":
        await call.answer("Bu so'rov allaqachon ko'rib chiqilgan.", show_alert=True)
        return
    await state.set_state(WorkHoursForm.reject_reason)
    await state.update_data(wh_rid=rid)
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await call.message.answer(
        f"✍️ <b>Rad etish sababini yozing</b> (so'rov #{rid}).\n"
        "Yozgan sababingiz xodimga yuboriladi."
    )
    await call.answer()


@router.message(WorkHoursForm.reject_reason, F.text)
async def hr_work_hours_reject_reason(message: Message, state: FSMContext, bot: Bot):
    if not await _is_staff(message.from_user.id):
        await state.clear()
        return
    reason = message.text.strip()
    data = await state.get_data()
    rid = data.get("wh_rid")
    await state.clear()
    req = await q.get_work_hour_request(rid)
    if not req or req.get("status") != "pending":
        await message.answer("Bu so'rov allaqachon yopilgan.")
        return
    me = await q.get_user(message.from_user.id)
    if not await q.claim_request("work_hour_requests", rid, "rejected",
                                 me["id"] if me else None, "pending"):
        await message.answer("Bu so'rov allaqachon boshqa xodim tomonidan ko'rib chiqilgan.")
        return
    await close_request_notices(bot, "work_hours", rid, keep_chat_id=message.from_user.id)
    await q.close_work_hour_request(rid, "rejected", reason=reason,
                                    handled_by=me["id"] if me else None)
    await q.add_log(
        message.from_user.id, me["full_name"] if me else "?",
        "ish_vaqti_rad", f"#{rid}",
    )
    await message.answer(f"❌ Ish vaqti so'rovi #{rid} rad etildi.\n✍️ Sabab: {reason}")
    if req.get("user_tg"):
        await safe_send(
            bot, req["user_tg"],
            "😔 <b>Ish vaqtini o'zgartirish so'rovi rad etildi.</b>\n\n"
            f"🕒 So'ragan vaqtingiz: {req.get('requested_hours')}\n"
            f"✍️ Sabab: {reason}",
        )
