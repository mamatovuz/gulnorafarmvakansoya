"""«🏢 Boshqa filialga ko'chirish» — xodim boshqa filialga o'tishni so'raydi.

Oqim:
  Xodim: «📩 HR ga murojaat» → «🏢 Boshqa filialga ko'chirish»
    → «Rostan ham so'rov yubormoqchimisiz?» (Ha / Yo'q)
    → filiallar ro'yxatidan birini tanlaydi
    → «Rostan ham shu filialga o'tmoqchimisiz?» (Ha / Tahrirlash)
    → so'rov HR bo'limiga boradi.
  HR: tasdiqlaydi / bekor qiladi / xodimga xabar yozadi.
      Xabar yozilsa — xodim javob bera oladi, HR yana yozishi mumkin (aylanma).
      Tasdiqlangach xodimning filiali (users va profil) o'zgaradi.
"""
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from database import queries as q
from database.db import ROLE_HR, ROLE_ADMIN, ROLE_CANDIDATE
from states import BranchTransferForm
import keyboards as kb
from utils import safe_send, broadcast_request, close_request_notices

router = Router()

NOTICE_KIND = "transfer"   # request_notices dagi tur nomi


async def _is_staff(tg_id):
    u = await q.get_user(tg_id)
    return u and u["role"] in (ROLE_HR, ROLE_ADMIN)


async def _hr_targets():
    hr_ids = await q.all_user_tg_ids(role=ROLE_HR)
    admin_ids = await q.all_user_tg_ids(role=ROLE_ADMIN)
    return set(hr_ids + admin_ids)


async def _notify_hr(bot: Bot, text, markup=None, ref_id=None):
    """HR/adminlarga xabar. `ref_id` berilsa — kimdir ko'rib chiqqach qolgan
    HR lardagi xabar avtomatik o'chirilishi uchun yozib boriladi."""
    targets = await _hr_targets()
    if ref_id:
        await broadcast_request(bot, NOTICE_KIND, ref_id, targets, text,
                                reply_markup=markup)
        return
    for tid in targets:
        await safe_send(bot, tid, text, reply_markup=markup)


async def _main_menu(message: Message, tg_id):
    """Xodimga o'z roliga mos asosiy menyu.

    DIQQAT: callback ichida `call.message.from_user` — bot, foydalanuvchi emas.
    Shu sabab menyu tg_id (call.from_user.id) bo'yicha aniqlanadi."""
    user = await q.get_user(tg_id)
    role = user["role"] if user else ROLE_CANDIDATE
    await message.answer("🏠 Asosiy menyu", reply_markup=kb.main_menu(role))


def _hr_request_text(req):
    return (
        "🏢 <b>Filialni o'zgartirish so'rovi</b>\n"
        f"№ {req['id']}\n"
        "━━━━━━━━━━━━\n"
        f"👤 Xodim: <b>{req.get('full_name') or '-'}</b>\n"
        f"💼 Lavozim: <b>{req.get('position') or '-'}</b>\n"
        f"📱 Telefon: {req.get('phone') or '-'}\n"
        "━━━━━━━━━━━━\n"
        f"🏢 Hozirgi filiali: <b>{req.get('from_branch_name') or 'belgilanmagan'}</b>\n"
        f"➡️ O'tmoqchi bo'lgan filiali: <b>{req.get('to_branch_name') or '-'}</b>\n\n"
        "Shu xodimning boshqa filialga o'tishini tasdiqlaysizmi?"
    )


async def _ask_branch(message: Message, tg_id, profile, edit=False):
    """Filiallar ro'yxatini chiqaradi (xodimning hozirgi filiali ro'yxatda yo'q)."""
    branches = await q.list_branches()
    current_id = profile.get("branch_id")
    options = [b for b in branches if b["id"] != current_id]
    if not options:
        await message.answer(
            "🏢 Hozircha o'tish mumkin bo'lgan boshqa filial yo'q."
        )
        await _main_menu(message, tg_id)
        return False
    head = "✏️ <b>Filialni qayta tanlang</b>" if edit else "🏢 <b>Filialni tanlang</b>"
    await message.answer(
        f"{head}\n\n"
        f"Hozirgi filialingiz: <b>{profile.get('branch_name') or 'belgilanmagan'}</b>\n"
        "Qaysi filialga o'tmoqchisiz?",
        reply_markup=kb.transfer_branch_pick_kb(options),
    )
    return True


# ================= XODIM: SO'ROV BOSHLASH =================
@router.callback_query(F.data == "hrreq:branch")
async def transfer_start(call: CallbackQuery, state: FSMContext):
    profile = await q.get_employee_profile_by_tg(call.from_user.id)
    if not profile:
        await call.answer("⛔ Xodim profili topilmadi.", show_alert=True)
        return
    if await q.get_pending_transfer_for_user(profile["user_id"]):
        await call.answer(
            "⏳ Sizda hali javob berilmagan filial o'zgartirish so'rovi bor. "
            "HR javobini kuting.",
            show_alert=True,
        )
        return
    await state.clear()
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await call.message.answer(
        "🏢 <b>Boshqa filialga ko'chirish</b>\n\n"
        f"Hozirgi filialingiz: <b>{profile.get('branch_name') or 'belgilanmagan'}</b>\n\n"
        "Siz rostan ham boshqa filialga o'tish so'rovini yubormoqchimisiz?",
        reply_markup=kb.transfer_start_confirm_kb(),
    )
    await call.answer()


@router.callback_query(F.data == "btr_no")
async def transfer_cancel(call: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await call.message.answer("❌ Bekor qilindi.")
    await _main_menu(call.message, call.from_user.id)
    await call.answer()


@router.callback_query(F.data == "btr_yes")
async def transfer_pick_branch(call: CallbackQuery, state: FSMContext):
    profile = await q.get_employee_profile_by_tg(call.from_user.id)
    if not profile:
        await call.answer("⛔ Xodim profili topilmadi.", show_alert=True)
        return
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await _ask_branch(call.message, call.from_user.id, profile)
    await call.answer()


@router.callback_query(F.data.startswith("btrbr:"))
async def transfer_branch_chosen(call: CallbackQuery, state: FSMContext):
    bid = int(call.data.split(":")[1])
    branch = await q.get_branch(bid)
    if not branch:
        await call.answer("Filial topilmadi.", show_alert=True)
        return
    await state.update_data(btr_branch_id=bid, btr_branch_name=branch["name"])
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await call.message.answer(
        f"🏢 Siz rostan ham <b>{branch['name']}</b> filialiga o'tishni xohlaysizmi?",
        reply_markup=kb.transfer_final_confirm_kb(),
    )
    await call.answer()


@router.callback_query(F.data == "btr_edit")
async def transfer_edit_branch(call: CallbackQuery, state: FSMContext):
    profile = await q.get_employee_profile_by_tg(call.from_user.id)
    if not profile:
        await call.answer("⛔ Xodim profili topilmadi.", show_alert=True)
        return
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await _ask_branch(call.message, call.from_user.id, profile, edit=True)
    await call.answer()


@router.callback_query(F.data == "btr_ok")
async def transfer_send(call: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    bid = data.get("btr_branch_id")
    if not bid:
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
    if await q.get_pending_transfer_for_user(profile["user_id"]):
        await call.message.answer(
            "⏳ Sizda allaqachon ochiq so'rov bor. HR javobini kuting."
        )
        await call.answer()
        return
    rid = await q.add_branch_transfer_request(
        user_id=profile["user_id"],
        from_branch_id=profile.get("branch_id"),
        to_branch_id=bid,
        position=profile.get("position"),
    )
    me = await q.get_user(call.from_user.id)
    await q.add_log(
        call.from_user.id, me["full_name"] if me else "?",
        "filial_sorovi", f"#{rid}: {data.get('btr_branch_name')}",
    )
    await call.message.answer(
        "📤 <b>So'rovingiz HR bo'limiga yuborildi!</b>\n\n"
        f"🏢 So'ralgan filial: <b>{data.get('btr_branch_name')}</b>\n"
        "HR javobini kuting."
    )
    await _main_menu(call.message, call.from_user.id)
    await call.answer("Yuborildi ✅")

    req = await q.get_branch_transfer_request(rid)
    await _notify_hr(bot, _hr_request_text(req),
                     markup=kb.hr_transfer_actions_kb(rid), ref_id=rid)


# ================= HR: SO'ROVLAR RO'YXATI =================
@router.message(F.text == "🏢 Filial o'zgartirish so'rovlari")
async def hr_transfer_list(message: Message):
    if not await _is_staff(message.from_user.id):
        await message.answer("⛔ Sizda ruxsat yo'q.")
        return
    reqs = await q.list_pending_branch_transfer_requests(limit=30)
    if not reqs:
        await message.answer("🏢 Ochiq filial o'zgartirish so'rovlari yo'q.")
        return
    await message.answer(
        f"🏢 <b>Ochiq filial o'zgartirish so'rovlari</b>\n\nJami: <b>{len(reqs)}</b> ta\n"
        "Batafsil ko'rish uchun tanlang:",
        reply_markup=kb.branch_transfer_requests_list_kb(reqs),
    )


@router.callback_query(F.data.startswith("btrview:"))
async def hr_transfer_view(call: CallbackQuery):
    if not await _is_staff(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    rid = int(call.data.split(":")[1])
    req = await q.get_branch_transfer_request(rid)
    if not req:
        await call.answer("So'rov topilmadi.", show_alert=True)
        return
    markup = kb.hr_transfer_actions_kb(rid) if req.get("status") == "pending" else None
    await call.message.answer(_hr_request_text(req), reply_markup=markup)
    await call.answer()


# ---------------- HR: TASDIQLASH ----------------
@router.callback_query(F.data.startswith("hrbtr_ok:"))
async def hr_transfer_approve(call: CallbackQuery, bot: Bot):
    if not await _is_staff(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    rid = int(call.data.split(":")[1])
    req = await q.get_branch_transfer_request(rid)
    if not req or req.get("status") != "pending":
        await call.answer("Bu so'rov allaqachon ko'rib chiqilgan.", show_alert=True)
        return
    me = await q.get_user(call.from_user.id)
    # ATOMIK — bir so'rov faqat bir marta tasdiqlanadi
    if not await q.claim_request("branch_transfer_requests", rid, "approved",
                                 me["id"] if me else None, "pending"):
        try:
            await call.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        await call.answer("Bu so'rov allaqachon boshqa xodim tomonidan ko'rib chiqilgan.",
                          show_alert=True)
        return
    await close_request_notices(bot, NOTICE_KIND, rid, keep_chat_id=call.from_user.id)
    await q.set_employee_branch(req["user_id"], req["to_branch_id"])
    await q.close_branch_transfer_request(rid, "approved",
                                          handled_by=me["id"] if me else None)
    # Kadrlar harakati (IT hisoboti): filial o'zgardi
    await q.add_hr_event(
        "transferred", user_id=req["user_id"], full_name=req.get("full_name"),
        old_value=req.get("from_branch_name"), new_value=req.get("to_branch_name"),
        branch_id=req.get("to_branch_id"), details=f"filial so'rovi #{rid}",
        created_by=me["id"] if me else None,
    )
    await q.add_log(
        call.from_user.id, me["full_name"] if me else "?",
        "filial_tasdiq", f"#{rid}: {req.get('to_branch_name')}",
    )
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await call.message.answer(
        f"✅ Filial o'zgartirish so'rovi #{rid} tasdiqlandi.\n"
        f"👤 {req.get('full_name')} — yangi filiali: <b>{req.get('to_branch_name')}</b>"
    )
    await call.answer("Tasdiqlandi ✅")
    if req.get("user_tg"):
        await safe_send(
            bot, req["user_tg"],
            "✅ <b>Filialingiz o'zgartirildi!</b>\n\n"
            f"🏢 Yangi filialingiz: <b>{req.get('to_branch_name')}</b>\n\n"
            "Endi davomat (kelish-ketish) shu filial manzili bo'yicha hisoblanadi.",
        )


# ---------------- HR: BEKOR QILISH ----------------
@router.callback_query(F.data.startswith("hrbtr_no:"))
async def hr_transfer_reject(call: CallbackQuery, bot: Bot):
    if not await _is_staff(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    rid = int(call.data.split(":")[1])
    req = await q.get_branch_transfer_request(rid)
    if not req or req.get("status") != "pending":
        await call.answer("Bu so'rov allaqachon ko'rib chiqilgan.", show_alert=True)
        return
    me = await q.get_user(call.from_user.id)
    if not await q.claim_request("branch_transfer_requests", rid, "rejected",
                                 me["id"] if me else None, "pending"):
        try:
            await call.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        await call.answer("Bu so'rov allaqachon boshqa xodim tomonidan ko'rib chiqilgan.",
                          show_alert=True)
        return
    await close_request_notices(bot, NOTICE_KIND, rid, keep_chat_id=call.from_user.id)
    await q.close_branch_transfer_request(rid, "rejected",
                                          handled_by=me["id"] if me else None)
    await q.add_log(
        call.from_user.id, me["full_name"] if me else "?",
        "filial_bekor", f"#{rid}",
    )
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await call.message.answer(f"❌ Filial o'zgartirish so'rovi #{rid} bekor qilindi.")
    await call.answer("Bekor qilindi")
    if req.get("user_tg"):
        await safe_send(
            bot, req["user_tg"],
            "😔 <b>Filialni o'zgartirish so'rovingiz bekor qilindi.</b>\n\n"
            f"🏢 So'ragan filialingiz: {req.get('to_branch_name')}\n"
            "Savollaringiz bo'lsa HR bo'limiga murojaat qiling.",
        )


# ---------------- HR ⇄ XODIM YOZISHMASI ----------------
@router.callback_query(F.data.startswith("hrbtr_msg:"))
async def hr_transfer_message_start(call: CallbackQuery, state: FSMContext):
    if not await _is_staff(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    rid = int(call.data.split(":")[1])
    req = await q.get_branch_transfer_request(rid)
    if not req or req.get("status") != "pending":
        await call.answer("Bu so'rov allaqachon ko'rib chiqilgan.", show_alert=True)
        return
    await state.set_state(BranchTransferForm.hr_message)
    await state.update_data(btr_rid=rid)
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await call.message.answer(
        f"✉️ So'rov #{rid} — <b>{req.get('full_name')}</b> ga yubormoqchi bo'lgan "
        "xabaringizni yozing:"
    )
    await call.answer()


@router.message(BranchTransferForm.hr_message, F.text)
async def hr_transfer_message_send(message: Message, state: FSMContext, bot: Bot):
    if not await _is_staff(message.from_user.id):
        await state.clear()
        return
    text = message.text.strip()
    data = await state.get_data()
    rid = data.get("btr_rid")
    await state.clear()
    req = await q.get_branch_transfer_request(rid)
    if not req or req.get("status") != "pending":
        await message.answer("Bu so'rov allaqachon yopilgan.")
        return
    me = await q.get_user(message.from_user.id)
    # Yozishmani shu HR o'z qo'liga oladi — xodimning javobi aynan unga boradi
    await q.set_transfer_handler(rid, me["id"] if me else None)
    await close_request_notices(bot, NOTICE_KIND, rid, keep_chat_id=message.from_user.id)
    if req.get("user_tg"):
        await safe_send(
            bot, req["user_tg"],
            "✉️ <b>HR bo'limidan xabar</b>\n"
            f"(filial o'zgartirish so'rovi #{rid} bo'yicha)\n"
            "━━━━━━━━━━━━\n"
            f"{text}",
            reply_markup=kb.emp_transfer_reply_kb(rid),
        )
    await message.answer(
        f"📤 Xabar xodimga yuborildi.\n\nSo'rov #{rid} hali ochiq — javobini "
        "kutib, keyin tasdiqlashingiz yoki bekor qilishingiz mumkin.",
        reply_markup=kb.hr_transfer_actions_kb(rid),
    )


@router.callback_query(F.data.startswith("btr_reply:"))
async def emp_transfer_reply_start(call: CallbackQuery, state: FSMContext):
    rid = int(call.data.split(":")[1])
    req = await q.get_branch_transfer_request(rid)
    user = await q.get_user(call.from_user.id)
    if not req or not user or req.get("user_id") != user["id"]:
        await call.answer("So'rov topilmadi.", show_alert=True)
        return
    if req.get("status") != "pending":
        await call.answer("Bu so'rov allaqachon yopilgan.", show_alert=True)
        return
    await state.set_state(BranchTransferForm.reply_text)
    await state.update_data(btr_rid=rid)
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await call.message.answer("✍️ HR bo'limiga javobingizni yozing:")
    await call.answer()


@router.message(BranchTransferForm.reply_text, F.text)
async def emp_transfer_reply_send(message: Message, state: FSMContext, bot: Bot):
    text = message.text.strip()
    data = await state.get_data()
    rid = data.get("btr_rid")
    await state.clear()
    req = await q.get_branch_transfer_request(rid)
    user = await q.get_user(message.from_user.id)
    if not req or not user or req.get("user_id") != user["id"]:
        await message.answer("So'rov topilmadi.")
        return
    if req.get("status") != "pending":
        await message.answer("Bu so'rov allaqachon yopilgan.")
        return
    body = (
        "💬 <b>Xodimdan javob</b>\n"
        f"(filial o'zgartirish so'rovi #{rid})\n"
        "━━━━━━━━━━━━\n"
        f"👤 {req.get('full_name')}\n"
        f"🏢 {req.get('from_branch_name') or '-'} ➡️ {req.get('to_branch_name') or '-'}\n"
        "━━━━━━━━━━━━\n"
        f"{text}"
    )
    markup = kb.hr_transfer_actions_kb(rid)
    # Yozishmani boshlagan HR ga yuboriladi; u topilmasa — barcha HR/adminlarga
    if req.get("handler_tg"):
        await safe_send(bot, req["handler_tg"], body, reply_markup=markup)
    else:
        await _notify_hr(bot, body, markup=markup)
    await q.add_log(message.from_user.id, user["full_name"], "filial_javob", f"#{rid}")
    await message.answer("📤 Javobingiz HR bo'limiga yuborildi.")
    await _main_menu(message, message.from_user.id)
