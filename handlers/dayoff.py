"""Dam olish kunini almashtirish so'rovi.

Xodim: masalan yakshanba o'rniga shanba dam olishni so'raydi. So'rov filial rahbari
va HR/Adminga boradi. Ular tasdiqlasa — xodimning dam olish kuni yangilanadi.
"""
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter

from database import queries as q
from database.db import ROLE_HR, ROLE_ADMIN, ROLE_MANAGER
from states import DayoffForm
import keyboards as kb
from utils import safe_send, broadcast_request, close_request_notices

router = Router()


def _req_text(r):
    return (
        f"🔄 <b>Dam olish kunini almashtirish #{r['id']}</b>\n"
        "━━━━━━━━━━━━\n"
        f"👤 Xodim: {r.get('full_name') or '-'}\n"
        f"🏢 Filial: {r.get('branch_name') or '-'}\n"
        f"📆 Hozirgi dam kuni: {r.get('from_day') or '-'}\n"
        f"📆 So'ralayotgan dam kuni: {r.get('to_day') or '-'}\n"
        f"✍️ Sabab: {r.get('reason') or '-'}\n"
        f"Holati: {r.get('status') or '-'}\n"
        f"🕐 Sana: {r.get('created_at') or '-'}"
    )


# ---------------- XODIM: SO'ROV YUBORISH ----------------
@router.message(F.text == "🔄 Dam olish kunini almashtirish")
async def dayoff_start(message: Message, state: FSMContext):
    profile = await q.get_employee_profile_by_tg(message.from_user.id)
    if not profile:
        await message.answer("⛔ Bu funksiya faqat tasdiqlangan xodimlar uchun.")
        return
    cur = profile.get("rest_day") or "belgilanmagan"
    await state.update_data(cur_rest=cur)
    await state.set_state(DayoffForm.from_day)
    await message.answer(
        "🔄 <b>Dam olish kunini almashtirish</b>\n\n"
        f"Hozirgi dam olish kuningiz: <b>{cur}</b>\n\n"
        "Qaysi dam olish kuningizni almashtirmoqchisiz? (hozirgi kun)",
        reply_markup=kb.dayoff_day_kb(),
    )


@router.message(StateFilter(DayoffForm.from_day, DayoffForm.to_day, DayoffForm.reason),
                F.text == kb.CANCEL_BTN)
async def dayoff_cancel(message: Message, state: FSMContext):
    await state.clear()
    user = await q.get_user(message.from_user.id)
    await message.answer(
        "❌ Bekor qilindi.",
        reply_markup=kb.main_menu(user["role"] if user else "candidate"),
    )


@router.message(DayoffForm.from_day, F.text)
async def dayoff_from(message: Message, state: FSMContext):
    await state.update_data(from_day=message.text.strip())
    await state.set_state(DayoffForm.to_day)
    await message.answer(
        "📆 Endi qaysi kunda dam olmoqchisiz? (yangi dam kuni)",
        reply_markup=kb.dayoff_day_kb(),
    )


@router.message(DayoffForm.to_day, F.text)
async def dayoff_to(message: Message, state: FSMContext):
    await state.update_data(to_day=message.text.strip())
    await state.set_state(DayoffForm.reason)
    await message.answer(
        "✍️ Sababini qisqacha yozing (masalan: <i>oilaviy tadbir</i>):",
        reply_markup=kb.cancel_kb(),
    )


@router.message(DayoffForm.reason, F.text)
async def dayoff_reason(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    await state.clear()
    user = await q.get_user(message.from_user.id)
    profile = await q.get_employee_profile_by_tg(message.from_user.id)
    branch_id = (user.get("branch_id")
                 or (profile.get("branch_id") if profile else None))
    rid = await q.add_dayoff_request(
        user["id"], branch_id, data.get("from_day"), data.get("to_day"),
        message.text.strip(),
    )
    await q.add_log(message.from_user.id, user.get("full_name"), "dam_olish_sorov", f"#{rid}")
    await message.answer(
        "✅ So'rovingiz filial rahbari va HR bo'limiga yuborildi. "
        "Tasdiqlangach sizga xabar beriladi.",
        reply_markup=kb.main_menu(user["role"] if user else "candidate"),
    )
    req = await q.get_dayoff_request(rid)
    # Filial rahbari + HR + Admin ga yuborish
    targets = set()
    if branch_id:
        targets.update(await q.all_user_tg_ids(role=ROLE_MANAGER, branch_id=branch_id))
    targets.update(await q.all_user_tg_ids(role=ROLE_HR))
    targets.update(await q.all_user_tg_ids(role=ROLE_ADMIN))
    targets.discard(message.from_user.id)
    # Kim birinchi ko'rib chiqsa — qolganlaridagi xabar avtomatik o'chadi
    await broadcast_request(
        bot, "dayoff", rid, targets,
        "🔔 <b>Yangi dam olish so'rovi!</b>\n\n" + _req_text(req),
        reply_markup=kb.dayoff_actions_kb(rid),
    )


# ---------------- KO'RISH (ro'yxat) ----------------
@router.message(F.text == "🛌 Dam olish so'rovlari")
async def dayoff_list(message: Message):
    user = await q.get_user(message.from_user.id)
    if not user or user["role"] not in (ROLE_HR, ROLE_ADMIN, ROLE_MANAGER, "accountant"):
        await message.answer("⛔ Ruxsat yo'q.")
        return
    branch_id = None
    if user["role"] == ROLE_MANAGER:
        profile = await q.get_employee_profile_by_tg(message.from_user.id)
        branch_id = user.get("branch_id") or (profile.get("branch_id") if profile else None)
    reqs = await q.list_dayoff_requests(status="new", branch_id=branch_id, limit=30)
    if not reqs:
        await message.answer("🛌 Yangi dam olish so'rovlari yo'q.")
        return
    await message.answer(
        f"🛌 <b>Dam olish so'rovlari</b>\n\nJami: <b>{len(reqs)}</b> ta\nTanlang:",
        reply_markup=kb.dayoff_list_kb(reqs),
    )


@router.callback_query(F.data.startswith("doview:"))
async def dayoff_view(call: CallbackQuery):
    user = await q.get_user(call.from_user.id)
    if not user or user["role"] not in (ROLE_HR, ROLE_ADMIN, ROLE_MANAGER, "accountant"):
        await call.answer("⛔", show_alert=True)
        return
    req = await q.get_dayoff_request(int(call.data.split(":")[1]))
    if not req:
        await call.answer("So'rov topilmadi.", show_alert=True)
        return
    markup = kb.dayoff_actions_kb(req["id"]) if req.get("status") == "new" else None
    await call.message.answer(_req_text(req), reply_markup=markup)
    await call.answer()


# ---------------- TASDIQLASH / RAD ----------------
async def _can_handle(user):
    return user and user["role"] in (ROLE_HR, ROLE_ADMIN, ROLE_MANAGER)


@router.callback_query(F.data.startswith("doacc:"))
async def dayoff_approve(call: CallbackQuery, bot: Bot):
    user = await q.get_user(call.from_user.id)
    if not await _can_handle(user):
        await call.answer("⛔", show_alert=True)
        return
    rid = int(call.data.split(":")[1])
    req = await q.get_dayoff_request(rid)
    if not req:
        await call.answer("So'rov topilmadi.", show_alert=True)
        return
    if req.get("status") != "new":
        await call.answer("Allaqachon ko'rib chiqilgan.", show_alert=True)
        return
    if not await q.claim_request("dayoff_requests", rid, "approved", user["id"], "new"):
        try:
            await call.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        await call.answer("Bu so'rov allaqachon boshqa xodim tomonidan ko'rib chiqilgan.",
                          show_alert=True)
        return
    await close_request_notices(bot, "dayoff", rid, keep_chat_id=call.from_user.id)
    # Yangi dam olish kunini profilga yozamiz
    if req.get("to_day"):
        await q.update_rest_day(req["user_id"], req["to_day"])
    await q.add_log(call.from_user.id, user["full_name"], "dam_olish_tasdiq", f"#{rid}")
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await call.message.answer(f"✅ Dam olish so'rovi #{rid} tasdiqlandi.")
    await call.answer("Tasdiqlandi ✅")
    if req.get("user_tg"):
        await safe_send(
            bot, req["user_tg"],
            f"✅ Dam olish kunini almashtirish so'rovingiz tasdiqlandi.\n"
            f"Yangi dam olish kuningiz: <b>{req.get('to_day')}</b>",
        )


@router.callback_query(F.data.startswith("dorej:"))
async def dayoff_reject(call: CallbackQuery, bot: Bot):
    user = await q.get_user(call.from_user.id)
    if not await _can_handle(user):
        await call.answer("⛔", show_alert=True)
        return
    rid = int(call.data.split(":")[1])
    req = await q.get_dayoff_request(rid)
    if not req:
        await call.answer("So'rov topilmadi.", show_alert=True)
        return
    if req.get("status") != "new":
        await call.answer("Allaqachon ko'rib chiqilgan.", show_alert=True)
        return
    if not await q.claim_request("dayoff_requests", rid, "rejected", user["id"], "new"):
        try:
            await call.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        await call.answer("Bu so'rov allaqachon boshqa xodim tomonidan ko'rib chiqilgan.",
                          show_alert=True)
        return
    await close_request_notices(bot, "dayoff", rid, keep_chat_id=call.from_user.id)
    await q.add_log(call.from_user.id, user["full_name"], "dam_olish_rad", f"#{rid}")
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await call.message.answer(f"❌ Dam olish so'rovi #{rid} rad etildi.")
    await call.answer("Rad etildi")
    if req.get("user_tg"):
        await safe_send(
            bot, req["user_tg"],
            "😔 Dam olish kunini almashtirish so'rovingiz rad etildi.",
        )
