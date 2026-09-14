"""Texnik xodim paneli va texnik topshiriqlar oqimi.

Oqim:
  1. Filial rahbari «🔧 Texnik nosozlik» + muddat yuboradi (handlers/staff.py).
  2. HR tasdiqlaydi — topshiriq barcha texnik xodimlarga tushadi (handlers/hr.py).
  3. Texnik xodim «🕗 Ertaga boshlayman / ▶️ Ishni boshladim / ✅ Tugatdim»
     tugmalari bilan holatni yangilaydi (shu fayl).
  4. Tugagach filial rahbariga «texnik xodimni baholang» so'rovi 1..5 yulduz
     bilan boradi; baho HR ga yetkaziladi.
"""
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from database import queries as q
from database.db import (
    ROLE_TECH, ROLE_ADMIN, ROLE_HR, ROLE_DIRECTOR, ROLE_ACCOUNTANT,
    TECH_CATEGORIES, TECH_RECUR_PERIODS,
)
import keyboards as kb
from states import (
    TechReplyForm, TechCancelForm, TechRatingForm, TechDoneForm,
    TechRecurringForm,
)
from utils import (
    safe_send, tech_task_text, close_request_notices,
    mark_request_notices_taken,
    update_tech_channel_card, reply_tech_channel_rating,
    post_tech_result_to_channel, send_tech_result_media, now_tk,
    iso_to_display, _fmt_sum,
)

router = Router()


async def _is_tech(tg_id):
    u = await q.get_user(tg_id)
    return u and u["role"] in (ROLE_TECH, ROLE_ADMIN)


async def _is_tech_admin(tg_id):
    """HR / Direktor / Admin — «🔧 Texnik ishlar» panelini ko'ra oladi."""
    u = await q.get_user(tg_id)
    return u and u["role"] in (ROLE_HR, ROLE_DIRECTOR, ROLE_ADMIN)


async def _notify_hr_admin(bot: Bot, text):
    ids = set(await q.all_user_tg_ids(role=ROLE_HR))
    ids |= set(await q.all_user_tg_ids(role=ROLE_ADMIN))
    for tid in ids:
        await safe_send(bot, tid, text)


# ==================== PANEL ====================
@router.message(F.text == "🔧 Texnik xodim panel")
async def tech_panel(message: Message):
    if not await _is_tech(message.from_user.id):
        await message.answer("⛔ Sizda texnik xodim paneli uchun ruxsat yo'q.")
        return
    me = await q.get_user(message.from_user.id)
    counts = await q.tech_task_counts(tech_user_id=me["id"])
    await message.answer(
        "🔧 <b>Texnik xodim paneli</b>\n"
        "━━━━━━━━━━━━\n"
        f"🆕 Yangi topshiriqlar: <b>{counts['new']}</b> ta\n"
        f"🔧 Jarayondagi ishlar: <b>{counts['active']}</b> ta\n"
        f"✅ Bajarilganlar: <b>{counts['done']}</b> ta\n"
        "━━━━━━━━━━━━\n"
        "Kerakli bo'limni tanlang:",
        reply_markup=kb.tech_menu(),
    )


@router.message(F.text == kb.TECH_MENU_NEW)
async def tech_new_tasks(message: Message):
    if not await _is_tech(message.from_user.id):
        return
    tasks = await q.list_tech_tasks(statuses=["assigned"], limit=30)
    if not tasks:
        await message.answer("🆕 Hozircha yangi (egallanmagan) topshiriq yo'q.")
        return
    await message.answer(
        f"🆕 <b>Yangi topshiriqlar</b>\n\nJami: <b>{len(tasks)}</b> ta\n"
        "Batafsil ko'rish va olish uchun tanlang:",
        reply_markup=kb.tech_tasks_list_kb(tasks, for_tech=True),
    )


@router.message(F.text == kb.TECH_MENU_ACTIVE)
async def tech_active_tasks(message: Message):
    if not await _is_tech(message.from_user.id):
        return
    me = await q.get_user(message.from_user.id)
    tasks = await q.list_tech_tasks(
        tech_user_id=me["id"], statuses=["tomorrow", "in_progress"], limit=30
    )
    if not tasks:
        await message.answer("🔧 Jarayondagi ishingiz yo'q.")
        return
    await message.answer(
        f"🔧 <b>Jarayondagi ishlar</b>\n\nJami: <b>{len(tasks)}</b> ta",
        reply_markup=kb.tech_tasks_list_kb(tasks, for_tech=True),
    )


@router.message(F.text == kb.TECH_MENU_DONE)
async def tech_done_tasks(message: Message):
    if not await _is_tech(message.from_user.id):
        return
    me = await q.get_user(message.from_user.id)
    tasks = await q.list_tech_tasks(
        tech_user_id=me["id"], statuses=["done", "rated"], limit=30
    )
    if not tasks:
        await message.answer("✅ Hali bajarilgan ishingiz yo'q.")
        return
    await message.answer(
        f"✅ <b>Bajarilgan ishlar</b>\n\nJami: <b>{len(tasks)}</b> ta",
        reply_markup=kb.tech_tasks_list_kb(tasks, for_tech=True),
    )


@router.callback_query(F.data.startswith("ttview:"))
async def tech_task_view(call: CallbackQuery):
    if not await _is_tech(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    tid = int(call.data.split(":")[1])
    task = await q.get_tech_task(tid)
    if not task:
        await call.answer("Topshiriq topilmadi.", show_alert=True)
        return
    markup = kb.tech_task_actions_kb(tid, task.get("status"))
    await call.message.answer(tech_task_text(task, for_tech=True), reply_markup=markup)
    # Media bo'lsa — asl xabarni ko'rsatamiz
    if task.get("src_chat_id") and task.get("src_message_id"):
        try:
            await call.bot.copy_message(
                chat_id=call.from_user.id,
                from_chat_id=task["src_chat_id"],
                message_id=task["src_message_id"],
            )
        except Exception:
            pass
    await call.answer()


# ==================== TEXNIK XODIM TUGMALARI ====================
async def _task_taken(call: CallbackQuery):
    """Topshiriq allaqachon boshqa texnik xodim tomonidan olingan."""
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await call.answer(
        "Bu topshiriqni allaqachon boshqa texnik xodim oldi.", show_alert=True
    )


async def _on_task_taken(bot: Bot, tid, me, keep_chat_id):
    """Topshiriq egallangach: qolgan texniklardagi xabarni «boshqa oldi» matniga
    almashtiradi va kanaldagi ochiq kartochkani (kim olgani) yangilaydi."""
    taken_text = (
        f"🔧 <b>Texnik topshiriq #{tid}</b>\n\n"
        f"ℹ️ Bu ishni <b>{me.get('full_name') or '-'}</b> oldi."
    )
    await mark_request_notices_taken(
        bot, "tech_task", tid, taken_text, keep_chat_id=keep_chat_id
    )
    await update_tech_channel_card(bot, tid)


@router.callback_query(F.data.startswith("ttaccept:"))
async def tech_task_accept(call: CallbackQuery, bot: Bot):
    """✅ Qabul qilish — topshiriqni ATOMIK egallaydi (assigned -> accepted)."""
    if not await _is_tech(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    tid = int(call.data.split(":")[1])
    me = await q.get_user(call.from_user.id)
    if not await q.accept_tech_task(tid, me["id"]):
        await _task_taken(call)
        return
    # Qolgan texniklardagi xabar «boshqa oldi» ga o'zgaradi + kanal kartochkasi yangilanadi
    await _on_task_taken(bot, tid, me, keep_chat_id=call.from_user.id)
    try:
        await call.message.edit_reply_markup(
            reply_markup=kb.tech_task_actions_kb(tid, "accepted")
        )
    except Exception:
        pass
    await call.answer("Qabul qilindi ✅")
    task = await q.get_tech_task(tid)
    await _notify_task_progress(
        bot, task, me,
        f"🤝 Texnik xodim <b>{me.get('full_name') or '-'}</b> topshiriq #{tid} ni "
        "<b>qabul qildi</b>."
    )


async def _dismiss_for_me(call: CallbackQuery, toast: str):
    """Topshiriqni FAQAT shu texnik xodimdan olib tashlaydi (umumiy topshiriqqa
    tegmaydi — boshqa texniklarga qoladi)."""
    if not await _is_tech(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    tid = int(call.data.split(":")[1])
    try:
        await q.delete_request_notice("tech_task", tid, call.from_user.id)
    except Exception:
        pass
    try:
        await call.message.delete()
    except Exception:
        try:
            await call.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
    await call.answer(toast, show_alert=True)


@router.callback_query(F.data.startswith("ttbusy:"))
async def tech_task_busy(call: CallbackQuery):
    """🙅 Men bandman — topshiriq shu xodimdan olib tashlanadi."""
    await _dismiss_for_me(call, "Band ekaningiz belgilandi — topshiriq sizdan olib tashlandi.")


@router.callback_query(F.data.startswith("ttignore:"))
async def tech_task_ignore(call: CallbackQuery):
    """🙈 E'tiborsiz qoldirish — topshiriq shu xodimdan olib tashlanadi."""
    await _dismiss_for_me(call, "E'tiborsiz qoldirildi — topshiriq sizdan olib tashlandi.")


@router.callback_query(F.data.startswith("tttom:"))
async def tech_task_tomorrow(call: CallbackQuery, bot: Bot):
    """🕗 Ertaga boshlayman — topshiriqni egallaydi, boshlashni ertaga rejalaydi."""
    if not await _is_tech(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    tid = int(call.data.split(":")[1])
    me = await q.get_user(call.from_user.id)
    if not await q.claim_tech_task(tid, me["id"], "tomorrow"):
        await _task_taken(call)
        return
    # Qolgan texniklardagi xabar «boshqa oldi» ga o'zgaradi + kanal kartochkasi yangilanadi
    await _on_task_taken(bot, tid, me, keep_chat_id=call.from_user.id)
    task = await q.get_tech_task(tid)
    try:
        await call.message.edit_reply_markup(
            reply_markup=kb.tech_task_actions_kb(tid, "tomorrow")
        )
    except Exception:
        pass
    await call.answer("Ertaga boshlash rejalandi ✅")
    await _notify_task_progress(
        bot, task, me,
        f"🕗 Texnik xodim <b>{me.get('full_name') or '-'}</b> topshiriq #{tid} ni "
        "<b>ertaga</b> boshlashini bildirdi."
    )


@router.callback_query(F.data.startswith("ttstart:"))
async def tech_task_start(call: CallbackQuery, bot: Bot):
    """▶️ Ishni boshladim — assigned (egallash) yoki tomorrow (o'z ishi) dan."""
    if not await _is_tech(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    tid = int(call.data.split(":")[1])
    me = await q.get_user(call.from_user.id)
    # 1) hali egasiz bo'lsa — egallab boshlaymiz
    claimed = await q.claim_tech_task(tid, me["id"], "in_progress")
    if claimed:
        await _on_task_taken(bot, tid, me, keep_chat_id=call.from_user.id)
    else:
        # 2) allaqachon o'zimnikida (qabul qilingan / ertaga) bo'lsa — boshlashga o'tkazamiz
        ok = await q.set_tech_task_status(
            tid, "in_progress", expected="accepted", tech_user_id=me["id"]
        ) or await q.set_tech_task_status(
            tid, "in_progress", expected="tomorrow", tech_user_id=me["id"]
        )
        if not ok:
            await _task_taken(call)
            return
        await update_tech_channel_card(bot, tid)
    task = await q.get_tech_task(tid)
    try:
        await call.message.edit_reply_markup(
            reply_markup=kb.tech_task_actions_kb(tid, "in_progress")
        )
    except Exception:
        pass
    await call.answer("Ish boshlandi ▶️")
    await _notify_task_progress(
        bot, task, me,
        f"▶️ Texnik xodim <b>{me.get('full_name') or '-'}</b> topshiriq #{tid} "
        "bo'yicha <b>ishni boshladi</b>."
    )


@router.callback_query(F.data.startswith("ttdone:"))
async def tech_task_done(call: CallbackQuery, state: FSMContext):
    """✅ Tugatdim — avval natija rasmi (ixtiyoriy), so'ng xarajat so'raladi."""
    if not await _is_tech(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    tid = int(call.data.split(":")[1])
    me = await q.get_user(call.from_user.id)
    task = await q.get_tech_task(tid)
    if not task or task.get("status") != "in_progress" or task.get("tech_user_id") != me["id"]:
        await call.answer(
            "Buni bajarib bo'lmadi (ish holati o'zgargan yoki sizniki emas).",
            show_alert=True,
        )
        return
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await state.set_state(TechDoneForm.photo)
    await state.update_data(done_tid=tid)
    await call.message.answer(
        f"📸 <b>Natija rasmi</b> — topshiriq #{tid}\n\n"
        "Bajarilgan ishning <b>rasm/video</b>sini yuboring (isbot uchun).\n"
        "Rasm bo'lmasa — quyidagi tugmani bosing.",
        reply_markup=kb.tech_done_skip_photo_kb(tid),
    )
    await call.answer()


def _extract_media(message: Message):
    """Yuborilgan xabardan (rasm/video/...) file_id va turini ajratadi."""
    if message.photo:
        return message.photo[-1].file_id, "photo"
    if message.video:
        return message.video.file_id, "video"
    if message.video_note:
        return message.video_note.file_id, "video_note"
    if message.document:
        return message.document.file_id, "document"
    return None, None


@router.message(TechDoneForm.photo)
async def tech_done_photo(message: Message, state: FSMContext):
    if not await _is_tech(message.from_user.id):
        return
    fid, ftype = _extract_media(message)
    if not fid:
        await message.answer(
            "❗️ Iltimos, <b>rasm yoki video</b> yuboring — yoki tugma bilan o'tkazib yuboring."
        )
        return
    data = await state.get_data()
    tid = data.get("done_tid")
    await state.update_data(done_photo_id=fid, done_photo_type=ftype)
    await state.set_state(TechDoneForm.cost)
    await message.answer(
        "💸 <b>Xarajat</b>\n\n"
        "Ushbu ishga sarflangan xarajatni (ehtiyot qism/material) <b>so'mda</b> yozing.\n"
        "Masalan: <i>150000</i>\n"
        "Xarajat bo'lmasa — quyidagi tugmani bosing.",
        reply_markup=kb.tech_done_skip_cost_kb(tid),
    )


@router.callback_query(TechDoneForm.photo, F.data.startswith("ttdnp:"))
async def tech_done_skip_photo(call: CallbackQuery, state: FSMContext):
    tid = int(call.data.split(":")[1])
    await state.update_data(done_photo_id=None, done_photo_type=None)
    await state.set_state(TechDoneForm.cost)
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await call.message.answer(
        "💸 <b>Xarajat</b>\n\n"
        "Ushbu ishga sarflangan xarajatni <b>so'mda</b> yozing (masalan: <i>150000</i>).\n"
        "Xarajat bo'lmasa — quyidagi tugmani bosing.",
        reply_markup=kb.tech_done_skip_cost_kb(tid),
    )
    await call.answer()


def _parse_cost(text):
    """«150 000 so'm» kabi matndan raqamni ajratadi. None — aniqlanmadi."""
    digits = "".join(ch for ch in (text or "") if ch.isdigit())
    if not digits:
        return None
    try:
        return int(digits)
    except ValueError:
        return None


@router.message(TechDoneForm.cost, F.text)
async def tech_done_cost(message: Message, state: FSMContext, bot: Bot):
    if not await _is_tech(message.from_user.id):
        return
    cost = _parse_cost(message.text)
    if cost is None:
        await message.answer(
            "❗️ Faqat son yozing (masalan: <b>150000</b>) — yoki tugma bilan o'tkazib yuboring."
        )
        return
    await _finalize_done(message, state, bot, cost=cost)


@router.callback_query(TechDoneForm.cost, F.data.startswith("ttdnc:"))
async def tech_done_skip_cost(call: CallbackQuery, state: FSMContext, bot: Bot):
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await _finalize_done(call.message, state, bot, cost=None,
                         actor_id=call.from_user.id)
    await call.answer()


async def _finalize_done(message: Message, state: FSMContext, bot: Bot,
                         cost=None, actor_id=None):
    """Yakuniy: in_progress -> done (natija+xarajat), rahbardan baho + HR/moliya xabar."""
    data = await state.get_data()
    await state.clear()
    tid = data.get("done_tid")
    photo_id = data.get("done_photo_id")
    photo_type = data.get("done_photo_type")
    me = await q.get_user(actor_id or message.chat.id)
    if not tid or not me:
        return
    if not await q.finish_tech_task(
        tid, me["id"], result_file_id=photo_id, result_file_type=photo_type,
        cost=cost,
    ):
        await message.answer(
            "⚠️ Yakunlab bo'lmadi (ish holati o'zgargan yoki sizniki emas)."
        )
        return
    task = await q.get_tech_task(tid)
    await update_tech_channel_card(bot, tid)
    await post_tech_result_to_channel(bot, tid)
    extra = []
    if photo_id:
        extra.append("📸 natija rasmi")
    if cost:
        extra.append(f"💸 {_fmt_sum(cost)}")
    extra_line = ("\n" + " · ".join(extra)) if extra else ""
    await message.answer(
        f"✅ Topshiriq #{tid} <b>bajarildi</b> deb belgilandi.{extra_line}\n"
        "Filial rahbariga ishingizni baholash so'rovi yuborildi. Rahmat!"
    )

    branch = task.get("branch_name") or "-"
    # Filial rahbariga — baholash so'rovi (agar rahbari bor bo'lsa)
    if task.get("manager_tg"):
        if photo_id:
            await send_tech_result_media(
                bot, task["manager_tg"], task,
                caption=f"📸 #{tid} — bajarilgan ish natijasi",
            )
        await safe_send(
            bot, task["manager_tg"],
            f"⭐ <b>Texnik ish bajarildi — baholang</b>\n"
            "━━━━━━━━━━━━\n"
            f"🔧 Topshiriq: #{tid}\n"
            f"🏢 Filial: {branch}\n"
            f"👷 Texnik xodim: <b>{me.get('full_name') or '-'}</b>\n"
            f"📝 Muammo: {task.get('details') or '-'}\n\n"
            "Texnik xodimning ishini <b>1 dan 5 yulduzgacha</b> baholang:",
            reply_markup=kb.tech_rating_kb(tid),
        )
    cost_line = f"\n💸 Xarajat: {_fmt_sum(cost)}" if cost else ""
    await _notify_hr_admin(
        bot,
        f"✅ <b>Texnik ish bajarildi</b>\n"
        f"🔧 Topshiriq: #{tid}\n"
        f"🏢 Filial: {branch}\n"
        f"👷 Texnik xodim: {me.get('full_name') or '-'}"
        f"{cost_line}\n"
        "⭐ Filial rahbari bahosi kutilmoqda."
    )
    # Moliya bo'limiga — xarajat qayd etilgan bo'lsa
    if cost:
        for tid_acc in set(await q.all_user_tg_ids(role=ROLE_ACCOUNTANT)):
            await safe_send(
                bot, tid_acc,
                f"💸 <b>Texnik ish xarajati</b>\n"
                f"🔧 Topshiriq: #{tid}\n"
                f"🏢 Filial: {branch}\n"
                f"🏷 Kategoriya: {task.get('category') or '-'}\n"
                f"👷 Texnik xodim: {me.get('full_name') or '-'}\n"
                f"💰 Summa: <b>{_fmt_sum(cost)}</b>",
            )


async def _notify_task_progress(bot: Bot, task, me, text):
    """Ish holatidagi o'zgarishni filial rahbari va HR ga yetkazadi."""
    if task and task.get("manager_tg"):
        await safe_send(bot, task["manager_tg"], text)
    await _notify_hr_admin(bot, text)


# ==================== TEXNIK XODIM → RAHBARGA JAVOB ====================
@router.callback_query(F.data.startswith("ttreply:"))
async def tech_task_reply_start(call: CallbackQuery, state: FSMContext):
    """💬 Javob berish — texnik xodim filial rahbariga xabar yozadi."""
    if not await _is_tech(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    tid = int(call.data.split(":")[1])
    task = await q.get_tech_task(tid)
    if not task:
        await call.answer("Topshiriq topilmadi.", show_alert=True)
        return
    await state.set_state(TechReplyForm.text)
    await state.update_data(reply_tid=tid)
    await call.message.answer(
        f"💬 <b>Topshiriq #{tid} bo'yicha javob</b>\n\n"
        "Filial rahbariga yubormoqchi bo'lgan xabaringizni yozing:"
    )
    await call.answer()


@router.message(TechReplyForm.text, F.text)
async def tech_task_reply_send(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    await state.clear()
    tid = data.get("reply_tid")
    text = (message.text or "").strip()
    if not tid or not text:
        await message.answer("❗️ Javob bo'sh bo'lishi mumkin emas.")
        return
    me = await q.get_user(message.from_user.id)
    task = await q.get_tech_task(tid)
    if not task:
        await message.answer("Topshiriq topilmadi.")
        return
    await q.add_tech_reply(tid, "tech", me["id"], me.get("full_name") or "-", text)
    # Filial rahbariga yetkazamiz
    delivered = False
    if task.get("manager_tg"):
        delivered = await safe_send(
            bot, task["manager_tg"],
            f"💬 <b>Texnik xodimdan javob — topshiriq #{tid}</b>\n"
            "━━━━━━━━━━━━\n"
            f"👷 Texnik xodim: <b>{me.get('full_name') or '-'}</b>\n"
            f"🏢 Filial: {task.get('branch_name') or '-'}\n\n"
            f"{text}"
        )
    if delivered:
        await message.answer("✅ Javobingiz filial rahbariga yuborildi.")
    else:
        await message.answer(
            "⚠️ Javob saqlandi, lekin filial rahbariga yetkazib bo'lmadi."
        )


# ==================== TEXNIK XODIM BEKOR QILISHI (SABAB BILAN) ==========
@router.callback_query(F.data.startswith("ttcancel:"))
async def tech_task_cancel_start(call: CallbackQuery, state: FSMContext):
    """🚫 Bekor qilish — texnik xodimdan sabab so'raladi."""
    if not await _is_tech(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    tid = int(call.data.split(":")[1])
    task = await q.get_tech_task(tid)
    if not task:
        await call.answer("Topshiriq topilmadi.", show_alert=True)
        return
    if task.get("status") not in ("assigned", "accepted", "tomorrow", "in_progress"):
        await call.answer("Bu topshiriqni bekor qilib bo'lmaydi.", show_alert=True)
        return
    await state.set_state(TechCancelForm.reason)
    await state.update_data(cancel_tid=tid)
    await call.message.answer(
        f"🚫 <b>Topshiriq #{tid} ni bekor qilish</b>\n\n"
        "Iltimos, <b>bekor qilish sababini</b> yozing:"
    )
    await call.answer()


@router.message(TechCancelForm.reason, F.text)
async def tech_task_cancel_finish(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    await state.clear()
    tid = data.get("cancel_tid")
    reason = (message.text or "").strip()
    if not tid or not reason:
        await message.answer("❗️ Bekor qilish sababi bo'sh bo'lishi mumkin emas.")
        return
    me = await q.get_user(message.from_user.id)
    # assigned (hali egasiz) bo'lsa — cheklovsiz; egasi bor bo'lsa faqat o'zi
    task = await q.get_tech_task(tid)
    only_owner = None if (task and task.get("status") == "assigned") else me["id"]
    if not await q.cancel_tech_task(tid, me["id"], reason, tech_user_id=only_owner):
        await message.answer(
            "⚠️ Bekor qilib bo'lmadi (holati o'zgargan yoki sizniki emas)."
        )
        return
    await close_request_notices(bot, "tech_task", tid)
    await message.answer(f"🚫 Topshiriq #{tid} bekor qilindi.")
    task = await q.get_tech_task(tid)
    branch = task.get("branch_name") or "-"
    notice = (
        "🚫 <b>Texnik topshiriq bekor qilindi</b>\n"
        "━━━━━━━━━━━━\n"
        f"🔧 Topshiriq: #{tid}\n"
        f"🏢 Filial: {branch}\n"
        f"👷 Texnik xodim: {me.get('full_name') or '-'}\n"
        f"📝 Sabab: {reason}"
    )
    if task.get("manager_tg"):
        await safe_send(bot, task["manager_tg"], notice)
    await _notify_hr_admin(bot, notice)


# ==================== ISHNI BOSHQA TEXNIKKA O'TKAZISH ====================
@router.callback_query(F.data.startswith("ttxfer:"))
async def tech_task_transfer_start(call: CallbackQuery):
    """🔁 Boshqaga o'tkazish — ega texnik boshqa texnik xodimni tanlaydi."""
    if not await _is_tech(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    tid = int(call.data.split(":")[1])
    me = await q.get_user(call.from_user.id)
    task = await q.get_tech_task(tid)
    if not task or task.get("tech_user_id") != me["id"]:
        await call.answer("Bu topshiriq sizniki emas.", show_alert=True)
        return
    if task.get("status") not in ("accepted", "tomorrow", "in_progress"):
        await call.answer("Bu bosqichda o'tkazib bo'lmaydi.", show_alert=True)
        return
    techs = [u for u in await q.list_users_by_role(ROLE_TECH) if u["id"] != me["id"]]
    if not techs:
        await call.answer("Boshqa texnik xodim yo'q.", show_alert=True)
        return
    await call.message.answer(
        f"🔁 <b>Topshiriq #{tid} ni boshqa texnik xodimga o'tkazish</b>\n\n"
        "Kimga o'tkazmoqchisiz? Tanlang:",
        reply_markup=kb.tech_transfer_list_kb(tid, techs),
    )
    await call.answer()


@router.callback_query(F.data.startswith("ttxfercancel:"))
async def tech_task_transfer_cancel(call: CallbackQuery):
    try:
        await call.message.delete()
    except Exception:
        pass
    await call.answer("O'tkazish bekor qilindi.")


@router.callback_query(F.data.startswith("ttxferto:"))
async def tech_task_transfer_to(call: CallbackQuery, bot: Bot):
    """Ega texnik qabul qiluvchini tanladi — taklif yuboriladi."""
    if not await _is_tech(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    parts = call.data.split(":")
    tid, to_id = int(parts[1]), int(parts[2])
    me = await q.get_user(call.from_user.id)
    task = await q.get_tech_task(tid)
    if not task or task.get("tech_user_id") != me["id"]:
        await call.answer("Bu topshiriq sizniki emas.", show_alert=True)
        return
    if not await q.set_tech_transfer(tid, me["id"], to_id):
        await call.answer("O'tkazib bo'lmadi (holat o'zgargan).", show_alert=True)
        return
    target = await q.get_user_by_id(to_id)
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    sent = False
    if target and target.get("tg_id"):
        sent = await safe_send(
            bot, target["tg_id"],
            f"🔁 <b>Sizga texnik ish o'tkazilmoqda</b>\n"
            "━━━━━━━━━━━━\n"
            f"👷 O'tkazayotgan xodim: <b>{me.get('full_name') or '-'}</b>\n\n"
            + tech_task_text(task, for_tech=True) +
            "\n\n❓ Bu ishni qabul qilasizmi? Tasdiqlasangiz — ishni siz bajarasiz.",
            reply_markup=kb.tech_transfer_confirm_kb(tid),
        )
    if sent:
        await call.message.answer(
            f"✅ Taklif <b>{target.get('full_name') or '-'}</b> ga yuborildi. "
            "U tasdiqlaguncha ish sizda qoladi."
        )
    else:
        await q.clear_tech_transfer(tid)
        await call.message.answer(
            "⚠️ Qabul qiluvchiga yuborib bo'lmadi (u botni ishga tushirmagan bo'lishi mumkin)."
        )
    await call.answer()


@router.callback_query(F.data.startswith("ttxferok:"))
async def tech_task_transfer_ok(call: CallbackQuery, bot: Bot):
    """Qabul qiluvchi texnik o'tkazishni tasdiqladi — egalik unga o'tadi."""
    if not await _is_tech(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    tid = int(call.data.split(":")[1])
    me = await q.get_user(call.from_user.id)
    task = await q.get_tech_task(tid)
    if not task:
        await call.answer("Topshiriq topilmadi.", show_alert=True)
        return
    if task.get("pending_transfer_to") != me["id"]:
        try:
            await call.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        await call.answer("Bu taklif endi mavjud emas.", show_alert=True)
        return
    prev_name = task.get("tech_name") or "-"
    prev_tg = task.get("tech_tg")
    if not await q.apply_tech_transfer(tid, me["id"], prev_name):
        await call.answer("O'tkazib bo'lmadi (holat o'zgargan).", show_alert=True)
        return
    task = await q.get_tech_task(tid)
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await call.message.answer(
        f"✅ Siz topshiriq #{tid} ni qabul qildingiz. Endi bu ishni siz bajarasiz.",
        reply_markup=kb.tech_task_actions_kb(tid, task.get("status")),
    )
    # Muammo media
    if task.get("src_chat_id") and task.get("src_message_id"):
        try:
            await bot.copy_message(
                chat_id=call.from_user.id,
                from_chat_id=task["src_chat_id"],
                message_id=task["src_message_id"],
            )
        except Exception:
            pass
    await update_tech_channel_card(bot, tid)
    if prev_tg:
        await safe_send(
            bot, prev_tg,
            f"✅ <b>{me.get('full_name') or '-'}</b> topshiriq #{tid} ni qabul qildi — "
            "ish unga o'tkazildi."
        )
    await _notify_hr_admin(
        bot,
        f"🔁 <b>Texnik ish o'tkazildi</b>\n"
        f"🔧 Topshiriq: #{tid}\n"
        f"🏢 Filial: {task.get('branch_name') or '-'}\n"
        f"👷 {prev_name} → <b>{me.get('full_name') or '-'}</b>"
    )
    await call.answer("Qabul qilindi ✅")


@router.callback_query(F.data.startswith("ttxferno:"))
async def tech_task_transfer_no(call: CallbackQuery, bot: Bot):
    """Qabul qiluvchi texnik o'tkazishni rad etdi — ish boshlang'ich egada qoladi."""
    if not await _is_tech(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    tid = int(call.data.split(":")[1])
    me = await q.get_user(call.from_user.id)
    task = await q.get_tech_task(tid)
    if not task or task.get("pending_transfer_to") != me["id"]:
        try:
            await call.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        await call.answer("Bu taklif endi mavjud emas.", show_alert=True)
        return
    await q.clear_tech_transfer(tid)
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await call.message.answer(f"❌ Siz topshiriq #{tid} ni rad etdingiz.")
    if task.get("tech_tg"):
        await safe_send(
            bot, task["tech_tg"],
            f"❌ <b>{me.get('full_name') or '-'}</b> topshiriq #{tid} ni rad etdi. "
            "Ish sizda qoladi — o'zingiz bajarasiz yoki boshqa xodimga o'tkazasiz."
        )
    await call.answer("Rad etildi")


# ==================== FILIAL RAHBARI BAHOLASHI ====================
@router.callback_query(F.data.startswith("ttrate:"))
async def tech_task_rate(call: CallbackQuery, bot: Bot, state: FSMContext):
    parts = call.data.split(":")
    tid, stars = int(parts[1]), int(parts[2])
    user = await q.get_user(call.from_user.id)
    task = await q.get_tech_task(tid)
    if not task or not user:
        await call.answer("Topshiriq topilmadi.", show_alert=True)
        return
    # Faqat so'rovni yuborgan rahbar (yoki admin) baholay oladi
    if user["role"] != ROLE_ADMIN and task.get("manager_user_id") != user["id"]:
        await call.answer("⛔ Bu topshiriqni faqat so'rovchi rahbar baholaydi.",
                          show_alert=True)
        return
    if not (1 <= stars <= 5):
        await call.answer("Noto'g'ri baho.", show_alert=True)
        return
    # done -> rated (ATOMIK, bir marta)
    if not await q.rate_tech_task(tid, stars):
        try:
            await call.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        await call.answer("Bu topshiriq allaqachon baholangan.", show_alert=True)
        return
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await q.add_log(call.from_user.id, user.get("full_name") or "?",
                    "texnik_baho", f"#{tid}: {stars}⭐")
    # Baho qo'yildi — endi ixtiyoriy otziv (izoh) so'raymiz
    await state.set_state(TechRatingForm.review)
    await state.update_data(rate_tid=tid, rate_stars=stars)
    await call.message.answer(
        f"✅ Siz texnik xodimni <b>{'⭐' * stars}</b> ({stars}/5) bilan baholadingiz.\n\n"
        "Xohlasangiz, qo'shimcha <b>otziv (izoh)</b> yozing yoki quyidagi tugmani bosing:",
        reply_markup=kb.tech_review_skip_kb(tid),
    )
    await call.answer("Baholandi ✅")


async def _finalize_rating(bot: Bot, tid, review=None):
    """Baho (va ixtiyoriy otziv) yakunlangach — FAQAT HR/Direktor/Adminga xabar,
    hamda yakunlangan ishni to'liq statistikasi bilan texnik ishlar kanaliga joylaydi.

    DIQQAT: baho va otziv texnik xodimga UMUMAN yuborilmaydi/ko'rsatilmaydi —
    ular «kam yulduz qo'ydingiz» kabi nizolarga sabab bo'lmasin."""
    task = await q.get_tech_task(tid)
    if not task:
        return
    stars = int(task.get("rating") or 0)
    tech_name = task.get("tech_name") or "-"
    branch = task.get("branch_name") or "-"
    review_line = f"\n💬 Otziv: {review}" if review else ""
    await _notify_hr_admin(
        bot,
        "⭐ <b>Texnik ish yakunlandi va baholandi</b>\n"
        "━━━━━━━━━━━━\n"
        f"🔧 Topshiriq: #{tid}\n"
        f"🏢 Filial: {branch}\n"
        f"👷 Texnik xodim: {tech_name}\n"
        f"👤 Baholadi (rahbar): {task.get('manager_name') or '-'}\n"
        f"⭐ Baho: {'⭐' * stars} ({stars}/5)" + review_line
    )
    # Texnik ishlar kanali: ochiq kartochka bo'lsa — uni yakunlangan holatga
    # yangilaymiz va AYNAN shu murojaatga REPLY qilib baho + sharhni joylaymiz.
    # Eski (kartochkasiz) topshiriqlar uchun — to'liq statistikali post (zaxira).
    if task.get("channel_message_id"):
        await update_tech_channel_card(bot, tid)
        await reply_tech_channel_rating(bot, tid, review=review)
    else:
        await _post_task_to_channel(bot, tid)


async def _post_task_to_channel(bot: Bot, tid):
    """Yakunlangan texnik ishni to'liq statistikasi bilan texnik ishlar kanaliga
    joylaydi (admin sozlamalarida ulangan bo'lsa)."""
    channel = await q.get_setting("tech_channel")
    if not channel:
        return
    task = await q.get_tech_task(tid)
    if not task:
        return
    text = "✅ <b>Texnik ish yakunlandi</b>\n\n" + tech_task_text(task, for_admin=True)
    replies = await q.list_tech_replies(tid)
    if replies:
        text += "\n\n💬 <b>Yozishmalar</b>"
        for r in replies:
            who = "👷" if r.get("from_role") == "tech" else "👤"
            text += f"\n{who} {r.get('from_name') or '-'}: {r.get('text') or ''}"
    posted = await safe_send(bot, channel, text)
    # Murojaat rasmi/mazmuni (media) — asl xabarni ham kanalga ko'chiramiz
    if posted and task.get("src_chat_id") and task.get("src_message_id"):
        try:
            await bot.copy_message(
                chat_id=channel,
                from_chat_id=task["src_chat_id"],
                message_id=task["src_message_id"],
            )
        except Exception:
            pass


@router.callback_query(F.data.startswith("ttrevskip:"))
async def tech_review_skip(call: CallbackQuery, bot: Bot, state: FSMContext):
    """Otzivsiz yakunlash."""
    tid = int(call.data.split(":")[1])
    await state.clear()
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await _finalize_rating(bot, tid)
    await call.message.answer("✅ Baho yakunlandi. Rahmat!")
    await call.answer()


@router.message(TechRatingForm.review, F.text)
async def tech_review_text(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    await state.clear()
    tid = data.get("rate_tid")
    review = (message.text or "").strip()
    if not tid:
        return
    if review:
        await q.set_tech_review(tid, review)
    await _finalize_rating(bot, tid, review=review or None)
    await message.answer("✅ Otzivingiz saqlandi. Rahmat!")


# ==================== HR / DIREKTOR «🔧 Texnik ishlar» PANELI ==========
_TECH_ADMIN_BUCKETS = {
    "new": (["assigned"], "🆕 Yangi (hali qabul qilinmagan)"),
    "active": (["accepted", "tomorrow", "in_progress"], "🔧 Bajarilmoqda"),
    "done": (["done", "rated"], "✅ Tugatilgan"),
    "cancelled": (["cancelled"], "🚫 Bekor qilingan"),
}


@router.message(F.text == "🔧 Texnik ishlar")
async def tech_admin_panel(message: Message):
    if not await _is_tech_admin(message.from_user.id):
        await message.answer("⛔ Sizda bu bo'lim uchun ruxsat yo'q.")
        return
    counts = await q.tech_task_admin_counts()
    await message.answer(
        "🔧 <b>Texnik ishlar</b>\n"
        "━━━━━━━━━━━━\n"
        f"🆕 Yangi (qabul qilinmagan): <b>{counts['new']}</b> ta\n"
        f"🔧 Bajarilmoqda: <b>{counts['active']}</b> ta\n"
        f"✅ Tugatilgan: <b>{counts['done']}</b> ta\n"
        f"🚫 Bekor qilingan: <b>{counts['cancelled']}</b> ta\n"
        "━━━━━━━━━━━━\n"
        "Batafsil ko'rish uchun holatni tanlang:",
        reply_markup=kb.tech_admin_menu_kb(counts),
    )


@router.callback_query(F.data.startswith("techadm:"))
async def tech_admin_list(call: CallbackQuery):
    if not await _is_tech_admin(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    bucket = call.data.split(":")[1]
    conf = _TECH_ADMIN_BUCKETS.get(bucket)
    if not conf:
        await call.answer()
        return
    statuses, label = conf
    tasks = await q.list_tech_tasks(statuses=statuses, limit=30)
    if not tasks:
        await call.message.answer(f"{label}: hozircha topshiriq yo'q.")
        await call.answer()
        return
    await call.message.answer(
        f"{label}\n\nJami: <b>{len(tasks)}</b> ta. Birini tanlang:",
        reply_markup=kb.tech_tasks_list_kb(tasks, prefix="techadmview"),
    )
    await call.answer()


@router.callback_query(F.data.startswith("techadmview:"))
async def tech_admin_view(call: CallbackQuery):
    if not await _is_tech_admin(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    tid = int(call.data.split(":")[1])
    task = await q.get_tech_task(tid)
    if not task:
        await call.answer("Topshiriq topilmadi.", show_alert=True)
        return
    text = tech_task_text(task, for_admin=True)
    # Yozishmalar (texnik xodim javoblari)
    replies = await q.list_tech_replies(tid)
    if replies:
        text += "\n\n💬 <b>Yozishmalar</b>"
        for r in replies:
            who = "👷" if r.get("from_role") == "tech" else "👤"
            text += f"\n{who} {r.get('from_name') or '-'}: {r.get('text') or ''}"
    await call.message.answer(text)
    # Murojaat rasmi/mazmuni (media) — asl xabarni ko'rsatamiz
    if task.get("src_chat_id") and task.get("src_message_id"):
        try:
            await call.bot.copy_message(
                chat_id=call.from_user.id,
                from_chat_id=task["src_chat_id"],
                message_id=task["src_message_id"],
            )
        except Exception:
            pass
    # Yakuniy natija rasmi/videosi (texnik biriktirgan)
    if task.get("result_file_id"):
        await send_tech_result_media(
            call.bot, call.from_user.id, task,
            caption=f"📸 #{tid} — bajarilgan ish natijasi",
        )
    await call.answer()


# ==================== TEXNIK STATISTIKA (HR/Direktor) ====================
def _fmt_hours(h):
    if h is None:
        return "-"
    try:
        h = float(h)
    except (TypeError, ValueError):
        return "-"
    if h < 1:
        return f"{int(round(h * 60))} daqiqa"
    d, rem = divmod(h, 24)
    if d >= 1:
        return f"{int(d)} kun {rem:.1f} soat"
    return f"{h:.1f} soat"


def _tech_stats_text(period_label, ov, by_tech, by_cat, by_branch):
    total = ov.get("total", 0) or 0
    done = ov.get("done", 0) or 0
    avg_rating = ov.get("avg_rating")
    lines = [
        "📊 <b>Texnik ishlar statistikasi</b>",
        f"📅 Davr: <b>{period_label}</b>",
        "━━━━━━━━━━━━",
        f"📦 Jami topshiriqlar: <b>{total}</b>",
        f"✅ Yakunlangan: <b>{done}</b>",
        f"🔧 Jarayonda: <b>{ov.get('active', 0) or 0}</b>",
        f"🚫 Bekor: <b>{ov.get('cancelled', 0) or 0}</b>",
        f"🚨 Shoshilinch: <b>{ov.get('urgent', 0) or 0}</b>",
        f"⭐ O'rtacha baho: <b>{avg_rating:.2f}</b>" if avg_rating
        else "⭐ O'rtacha baho: <b>-</b>",
        f"⏱ O'rtacha bajarish: <b>{_fmt_hours(ov.get('avg_hours'))}</b>",
        f"💸 Umumiy xarajat: <b>{_fmt_sum(ov.get('total_cost') or 0)}</b>",
    ]
    if by_tech:
        lines.append("\n👷 <b>Xodimlar kesimi</b>")
        for r in by_tech[:10]:
            rt = f"{r['avg_rating']:.1f}⭐" if r.get("avg_rating") else "—"
            lines.append(
                f"• {r.get('name') or '-'}: {r.get('done', 0)} ta · {rt} · "
                f"{_fmt_hours(r.get('avg_hours'))}"
            )
    if by_cat:
        lines.append("\n🏷 <b>Kategoriya kesimi</b>")
        for r in by_cat[:10]:
            cost = f" · {_fmt_sum(r['total_cost'])}" if r.get("total_cost") else ""
            lines.append(f"• {r.get('cat') or '-'}: {r.get('total', 0)} ta{cost}")
    if by_branch:
        lines.append("\n🏢 <b>Filiallar kesimi</b>")
        for r in by_branch[:12]:
            lines.append(
                f"• {r.get('branch') or '-'}: {r.get('total', 0)} ta "
                f"(✅ {r.get('done', 0)})"
            )
    return "\n".join(lines)


@router.callback_query(F.data == "techstats:open")
async def tech_stats_open(call: CallbackQuery):
    if not await _is_tech_admin(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    await call.message.answer(
        "📊 <b>Texnik ishlar statistikasi</b>\n\nDavrni tanlang:",
        reply_markup=kb.tech_stats_menu_kb(),
    )
    await call.answer()


async def _gather_tech_stats(period):
    ov = await q.tech_stats_overall(period)
    by_tech = await q.tech_stats_by_tech(period)
    by_cat = await q.tech_stats_by_category(period)
    by_branch = await q.tech_stats_by_branch(period)
    return ov, by_tech, by_cat, by_branch


@router.callback_query(F.data.in_({"techstats:month", "techstats:all"}))
async def tech_stats_show(call: CallbackQuery):
    if not await _is_tech_admin(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    if call.data == "techstats:month":
        period = now_tk().strftime("%Y-%m")
        label = period
    else:
        period = None
        label = "Butun davr"
    ov, by_tech, by_cat, by_branch = await _gather_tech_stats(period)
    await call.message.answer(
        _tech_stats_text(label, ov, by_tech, by_cat, by_branch)
    )
    await call.answer()


@router.callback_query(F.data == "techstats:xlsx")
async def tech_stats_xlsx(call: CallbackQuery, bot: Bot):
    if not await _is_tech_admin(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    period = now_tk().strftime("%Y-%m")
    ov, by_tech, by_cat, by_branch = await _gather_tech_stats(period)
    from services import export
    xlsx = export.build_tech_stats_xlsx(period, ov, by_tech, by_cat, by_branch)
    try:
        await bot.send_document(
            call.from_user.id, xlsx,
            caption=f"📥 Texnik ishlar statistikasi — {period}",
        )
    except Exception:
        await call.message.answer("⚠️ Excel yuborib bo'lmadi.")
    await call.answer("Tayyor ✅")


# ==================== REJALI (TAKRORLANUVCHI) TEXNIK XIZMAT ============
async def _is_recur_admin(tg_id):
    """Rejali ishlarni faqat HR / Admin boshqaradi."""
    u = await q.get_user(tg_id)
    return u and u["role"] in (ROLE_HR, ROLE_ADMIN)


def _recur_item_text(rec):
    branch = rec.get("branch_name") or "🏢 Barcha filiallar"
    period = next((lbl for lbl, d in TECH_RECUR_PERIODS
                   if d == rec.get("every_days")), f"{rec.get('every_days')} kun")
    st = "🟢 Faol" if rec.get("active") else "⚪️ To'xtatilgan"
    lines = [
        f"🔁 <b>Rejali texnik xizmat #{rec['id']}</b>",
        "━━━━━━━━━━━━",
        f"📌 Nomi: <b>{rec.get('title') or '-'}</b>",
        f"🏷 Kategoriya: {rec.get('category') or '-'}",
        f"🏢 Filial: {branch}",
        f"🔁 Davri: <b>{period}</b>",
        f"📆 Keyingi: <b>{iso_to_display(rec.get('next_date'))}</b>",
        f"📊 Holati: {st}",
    ]
    if rec.get("last_run"):
        lines.append(f"🕐 Oxirgi yaratilgan: {iso_to_display(rec['last_run'])}")
    return "\n".join(lines)


@router.callback_query(F.data == "techrecur:open")
async def tech_recur_open(call: CallbackQuery, state: FSMContext):
    if not await _is_tech_admin(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    await state.clear()
    items = await q.list_tech_recurring()
    txt = (
        "🔁 <b>Rejali texnik xizmatlar</b>\n\n"
        "Takrorlanuvchi ishlar (masalan konditsioner tozalash) belgilangan "
        "davrda avtomatik topshiriq bo'lib texnik xodimlarga tushadi.\n"
    )
    if not items:
        txt += "\nHozircha rejali ish yo'q."
    await call.message.answer(txt, reply_markup=kb.tech_recurring_menu_kb(items))
    await call.answer()


@router.callback_query(F.data.startswith("techrecur:view:"))
async def tech_recur_view(call: CallbackQuery):
    if not await _is_tech_admin(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    rec = await q.get_tech_recurring(int(call.data.split(":")[2]))
    if not rec:
        await call.answer("Topilmadi.", show_alert=True)
        return
    can_edit = await _is_recur_admin(call.from_user.id)
    await call.message.answer(
        _recur_item_text(rec),
        reply_markup=kb.tech_recurring_item_kb(rec) if can_edit else None,
    )
    await call.answer()


@router.callback_query(F.data.startswith("techrecur:toggle:"))
async def tech_recur_toggle(call: CallbackQuery):
    if not await _is_recur_admin(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    rec_id = int(call.data.split(":")[2])
    rec = await q.get_tech_recurring(rec_id)
    if not rec:
        await call.answer("Topilmadi.", show_alert=True)
        return
    await q.set_tech_recurring_active(rec_id, not rec.get("active"))
    rec = await q.get_tech_recurring(rec_id)
    try:
        await call.message.edit_text(
            _recur_item_text(rec), reply_markup=kb.tech_recurring_item_kb(rec)
        )
    except Exception:
        pass
    await call.answer("Yangilandi ✅")


@router.callback_query(F.data.startswith("techrecur:del:"))
async def tech_recur_del(call: CallbackQuery):
    if not await _is_recur_admin(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    rec_id = int(call.data.split(":")[2])
    await q.delete_tech_recurring(rec_id)
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await call.message.answer(f"🗑 Rejali ish #{rec_id} o'chirildi.")
    await call.answer("O'chirildi")


# ---- Yangi rejali ish yaratish ----
@router.callback_query(F.data == "techrecur:add")
async def tech_recur_add(call: CallbackQuery, state: FSMContext):
    if not await _is_recur_admin(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    branches = await q.list_branches()
    await state.set_state(TechRecurringForm.branch)
    await call.message.answer(
        "🔁 <b>Yangi rejali ish</b>\n\n1️⃣ Qaysi filial uchun?",
        reply_markup=kb.tech_recur_branch_kb(branches),
    )
    await call.answer()


@router.callback_query(TechRecurringForm.branch, F.data.startswith("trecbr:"))
async def tech_recur_branch(call: CallbackQuery, state: FSMContext):
    val = call.data.split(":")[1]
    branch_id = None if val == "all" else int(val)
    await state.update_data(rec_branch_id=branch_id)
    await state.set_state(TechRecurringForm.category)
    await call.message.answer(
        "2️⃣ Muammo turi (kategoriya)?",
        reply_markup=kb.tech_recur_category_kb(),
    )
    await call.answer()


@router.callback_query(TechRecurringForm.category, F.data.startswith("treccat:"))
async def tech_recur_category(call: CallbackQuery, state: FSMContext):
    idx = int(call.data.split(":")[1])
    try:
        category = TECH_CATEGORIES[idx]
    except IndexError:
        await call.answer("Xato tanlov.", show_alert=True)
        return
    await state.update_data(rec_category=category)
    await state.set_state(TechRecurringForm.title)
    await call.message.answer(
        "3️⃣ Ish nomi/tavsifini yozing.\n"
        "Masalan: <i>Konditsionerlarni tozalash</i>"
    )
    await call.answer()


@router.message(TechRecurringForm.title, F.text)
async def tech_recur_title(message: Message, state: FSMContext):
    title = (message.text or "").strip()
    if not title:
        await message.answer("❗️ Nom bo'sh bo'lishi mumkin emas.")
        return
    await state.update_data(rec_title=title)
    await state.set_state(TechRecurringForm.period)
    await message.answer(
        "4️⃣ Qanchalik tez-tez takrorlansin?",
        reply_markup=kb.tech_recur_period_kb(),
    )


@router.callback_query(TechRecurringForm.period, F.data.startswith("trecper:"))
async def tech_recur_period(call: CallbackQuery, state: FSMContext):
    if not await _is_recur_admin(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    idx = int(call.data.split(":")[1])
    try:
        label, every_days = TECH_RECUR_PERIODS[idx]
    except IndexError:
        await call.answer("Xato tanlov.", show_alert=True)
        return
    data = await state.get_data()
    await state.clear()
    me = await q.get_user(call.from_user.id)
    from datetime import timedelta
    next_date = (now_tk().date() + timedelta(days=every_days)).strftime("%Y-%m-%d")
    rec_id = await q.add_tech_recurring({
        "branch_id": data.get("rec_branch_id"),
        "title": data.get("rec_title"),
        "category": data.get("rec_category"),
        "details": data.get("rec_title"),
        "every_days": every_days,
        "next_date": next_date,
        "created_by": me["id"] if me else None,
    })
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    rec = await q.get_tech_recurring(rec_id)
    await call.message.answer(
        "✅ <b>Rejali ish yaratildi!</b>\n\n" + _recur_item_text(rec)
    )
    await call.answer("Yaratildi ✅")
