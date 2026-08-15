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

from database import queries as q
from database.db import ROLE_TECH, ROLE_ADMIN, ROLE_HR, ROLE_MANAGER
import keyboards as kb
from utils import safe_send, tech_task_text, close_request_notices

router = Router()


async def _is_tech(tg_id):
    u = await q.get_user(tg_id)
    return u and u["role"] in (ROLE_TECH, ROLE_ADMIN)


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
        reply_markup=kb.tech_tasks_list_kb(tasks),
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
        reply_markup=kb.tech_tasks_list_kb(tasks),
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
        reply_markup=kb.tech_tasks_list_kb(tasks),
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
    # Qolgan texniklardagi shu topshiriq xabarini o'chiramiz (o'zimnikini qoldiramiz)
    await close_request_notices(bot, "tech_task", tid, keep_chat_id=call.from_user.id)
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
        await close_request_notices(bot, "tech_task", tid, keep_chat_id=call.from_user.id)
    else:
        # 2) allaqachon o'zimnikida (ertaga) bo'lsa — boshlashga o'tkazamiz
        ok = await q.set_tech_task_status(
            tid, "in_progress", expected="tomorrow", tech_user_id=me["id"]
        )
        if not ok:
            await _task_taken(call)
            return
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
async def tech_task_done(call: CallbackQuery, bot: Bot):
    """✅ Tugatdim — ish yakunlanadi, rahbardan baho so'raladi."""
    if not await _is_tech(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    tid = int(call.data.split(":")[1])
    me = await q.get_user(call.from_user.id)
    if not await q.set_tech_task_status(
        tid, "done", expected="in_progress", tech_user_id=me["id"]
    ):
        await call.answer(
            "Buni bajarib bo'lmadi (ish holati o'zgargan yoki sizniki emas).",
            show_alert=True,
        )
        return
    task = await q.get_tech_task(tid)
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await call.message.answer(
        f"✅ Topshiriq #{tid} <b>bajarildi</b> deb belgilandi.\n"
        "Filial rahbariga ishingizni baholash so'rovi yuborildi. Rahmat!"
    )
    await call.answer("Tugatildi ✅")

    # Filial rahbariga — texnik xodimni baholash so'rovi (1..5 yulduz)
    branch = task.get("branch_name") or "-"
    if task.get("manager_tg"):
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
    # HR ga — ish bajarilgani haqida xabar
    await _notify_hr_admin(
        bot,
        f"✅ <b>Texnik ish bajarildi</b>\n"
        f"🔧 Topshiriq: #{tid}\n"
        f"🏢 Filial: {branch}\n"
        f"👷 Texnik xodim: {me.get('full_name') or '-'}\n"
        "⭐ Filial rahbari bahosi kutilmoqda."
    )


async def _notify_task_progress(bot: Bot, task, me, text):
    """Ish holatidagi o'zgarishni filial rahbari va HR ga yetkazadi."""
    if task and task.get("manager_tg"):
        await safe_send(bot, task["manager_tg"], text)
    await _notify_hr_admin(bot, text)


# ==================== FILIAL RAHBARI BAHOLASHI ====================
@router.callback_query(F.data.startswith("ttrate:"))
async def tech_task_rate(call: CallbackQuery, bot: Bot):
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
    await call.message.answer(
        f"✅ Rahmat! Siz texnik xodimni <b>{'⭐' * stars}</b> ({stars}/5) bilan "
        "baholadingiz."
    )
    await call.answer("Baholandi ✅")

    tech_name = task.get("tech_name") or "-"
    branch = task.get("branch_name") or "-"
    # HR ga — yakuniy natija
    await _notify_hr_admin(
        bot,
        "⭐ <b>Texnik ish yakunlandi va baholandi</b>\n"
        "━━━━━━━━━━━━\n"
        f"🔧 Topshiriq: #{tid}\n"
        f"🏢 Filial: {branch}\n"
        f"👷 Texnik xodim: {tech_name}\n"
        f"👤 Baholadi (rahbar): {task.get('manager_name') or '-'}\n"
        f"⭐ Baho: {'⭐' * stars} ({stars}/5)"
    )
    # Texnik xodimga — bahodan xabardor qilamiz
    if task.get("tech_tg"):
        await safe_send(
            bot, task["tech_tg"],
            f"⭐ Siz bajargan topshiriq #{tid} filial rahbari tomonidan "
            f"<b>{'⭐' * stars}</b> ({stars}/5) bilan baholandi. Rahmat!"
        )
