"""Jarimalar nazorati: moliya «✅ Ijro etildi» / «🚫 Bekor qilish» (sabab bilan),
HR / direktor / filial rahbari uchun «📋 Jarimalar holati» va filial rahbarining
o'z filiali xodimiga «💸 Jarima qo'llash» oqimi.

Jarima holatlari (`fines.status`):
  pending   — yozildi, moliya ijrosini kutmoqda (oylikdan ayiriladi)
  executed  — moliya «ijro etildi» deb tasdiqladi (oylikdan ayiriladi)
  cancelled — moliya sabab bilan bekor qildi (oylikdan ayirilmaydi)
"""
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from database import queries as q
from database.db import (
    ROLE_ADMIN, ROLE_HR, ROLE_DIRECTOR, ROLE_ACCOUNTANT, ROLE_MANAGER,
)
from states import FineDecisionForm, ManagerFineForm
import keyboards as kb
from utils import (
    fine_text, fine_status, safe_send, now_tk, fmt_money, FINE_SOURCE_LABELS,
)

router = Router()

PAGE_SIZE = 10
# Jarimalar holatini ko'ra oladigan rollar (rahbar — faqat o'z filialini)
_VIEW_ROLES = (ROLE_HR, ROLE_ADMIN, ROLE_DIRECTOR, ROLE_ACCOUNTANT, ROLE_MANAGER)


async def _user_with_role(tg_id, *roles):
    u = await q.get_user(tg_id)
    return u if u and u["role"] in roles else None


async def _is_finance(tg_id):
    return await _user_with_role(tg_id, ROLE_ACCOUNTANT, ROLE_ADMIN)


async def _manager_branch_id(user):
    if user.get("branch_id"):
        return user["branch_id"]
    profile = await q.get_employee_profile(user["id"])
    return profile.get("branch_id") if profile else None


async def _view_branch_scope(user):
    """Rahbar faqat o'z filialini ko'radi; qolganlar — hammasini (None).

    Rahbarga filial biriktirilmagan bo'lsa False qaytadi."""
    if user["role"] != ROLE_MANAGER:
        return None
    return await _manager_branch_id(user) or False


def _period_now():
    return now_tk().strftime("%Y-%m")


def _period_label(period):
    y, m = period.split("-")
    return f"{m}.{y}"


def _sum(fines):
    return sum(q._digits_to_int(f.get("amount")) for f in fines)


# ================= YANGI JARIMA → MOLIYAGA XABAR =================
async def notify_finance_new_fine(bot: Bot, fid, author_role_label):
    """Yangi jarima haqida barcha moliya xodimlariga «✅ Ijro etildi» /
    «🚫 Bekor qilish» tugmalari bilan xabar yuboradi."""
    fine = await q.get_fine(fid)
    if not fine:
        return
    text = (
        f"💸 <b>{author_role_label}dan yangi jarima</b>\n\n"
        + fine_text(fine)
        + "\n\nJarima yakuniy oylikdan ayiriladi. Ijro etilgach «✅ Ijro etildi» ni, "
        "noto'g'ri bo'lsa «🚫 Bekor qilish» ni bosing (sabab so'raladi)."
    )
    for tid in set(await q.all_user_tg_ids(role=ROLE_ACCOUNTANT)):
        await safe_send(bot, tid, text, reply_markup=kb.fine_decision_kb(fid))


async def _notify_decision(bot: Bot, fine, actor_tg, text_creator, text_employee=None):
    """Jarima yozgan shaxsga (o'zi bo'lmasa) va kerak bo'lsa xodimga xabar."""
    creator_tg = fine.get("created_by_tg")
    if creator_tg and creator_tg != actor_tg:
        await safe_send(bot, creator_tg, text_creator)
    if text_employee and fine.get("employee_tg"):
        await safe_send(bot, fine["employee_tg"], text_employee)


# ================= ✅ IJRO ETILDI =================
@router.callback_query(F.data.startswith("fexec:"))
async def fine_execute(call: CallbackQuery, bot: Bot):
    me = await _is_finance(call.from_user.id)
    if not me:
        await call.answer("⛔ Faqat moliya bo'limi uchun.", show_alert=True)
        return
    fid = int(call.data.split(":")[1])
    fine = await q.get_fine(fid)
    if not fine:
        await call.answer("Jarima topilmadi.", show_alert=True)
        return
    if not await q.execute_fine(fid, me["id"]):
        st = fine_status(fine)
        msg = ("Bu jarima allaqachon bekor qilingan." if st == "cancelled"
               else "Bu jarima allaqachon ijro etilgan.")
        await call.answer(msg, show_alert=True)
        return
    await q.add_log(call.from_user.id, me["full_name"], "jarima_ijro",
                    f"fine#{fid} user#{fine.get('employee_user_id')} {fine.get('amount')}")
    fine = await q.get_fine(fid)
    try:
        await call.message.edit_reply_markup(reply_markup=kb.fine_decision_kb(fid, "executed"))
    except Exception:
        pass
    await call.message.answer(
        "✅ <b>Jarima ijro etildi</b>\n\n" + fine_text(fine),
        reply_markup=kb.fine_decision_kb(fid, "executed"),
    )
    await call.answer("Ijro etildi ✅")
    await _notify_decision(
        bot, fine, call.from_user.id,
        "✅ <b>Siz yozgan jarima moliya tomonidan ijro etildi</b>\n\n" + fine_text(fine),
    )


# ================= 🚫 BEKOR QILISH (sabab bilan) =================
# «fcancel:» — eski xabarlardagi tugmalar uchun ham ishlaydi
@router.callback_query(F.data.startswith(("fcanc:", "fcancel:")))
async def fine_cancel_ask(call: CallbackQuery, state: FSMContext):
    if not await _is_finance(call.from_user.id):
        await call.answer("⛔ Faqat moliya bo'limi uchun.", show_alert=True)
        return
    fid = int(call.data.split(":")[1])
    fine = await q.get_fine(fid)
    if not fine:
        await call.answer("Jarima topilmadi.", show_alert=True)
        return
    if fine_status(fine) == "cancelled":
        await call.answer("Bu jarima allaqachon bekor qilingan.", show_alert=True)
        return
    await state.set_state(FineDecisionForm.cancel_reason)
    await state.update_data(
        fcancel_fid=fid,
        fcancel_chat=call.message.chat.id,
        fcancel_msg=call.message.message_id,
    )
    await call.message.answer(
        f"🚫 <b>Jarima #{fid}ni bekor qilish</b>\n"
        f"👤 {fine.get('employee_name') or '-'} · 💰 {fine.get('amount')}\n\n"
        "✍️ <b>Bekor qilish sababini yozing</b> (HR, direktor va jarima yozgan "
        "shaxs ko'radi):",
        reply_markup=kb.fine_cancel_abort_kb(),
    )
    await call.answer()


@router.callback_query(F.data == "fcx:abort")
async def fine_cancel_abort(call: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await call.message.edit_text("↩️ Bekor qilish to'xtatildi. Jarima o'zgarishsiz qoldi.")
    except Exception:
        pass
    await call.answer()


@router.message(FineDecisionForm.cancel_reason, F.text)
async def fine_cancel_reason(message: Message, state: FSMContext, bot: Bot):
    me = await _is_finance(message.from_user.id)
    if not me:
        await state.clear()
        return
    reason = message.text.strip()
    if len(reason) < 3:
        await message.answer(
            "❗️ Sabab juda qisqa. Iltimos, bekor qilish sababini aniqroq yozing:",
            reply_markup=kb.fine_cancel_abort_kb(),
        )
        return
    data = await state.get_data()
    await state.clear()
    fid = data.get("fcancel_fid")
    fine = await q.get_fine(fid) if fid else None
    if not fine:
        await message.answer("❗️ Jarima topilmadi.")
        return
    if not await q.cancel_fine(fid, me["id"], reason):
        await message.answer("ℹ️ Bu jarima allaqachon bekor qilingan.")
        return
    await q.add_log(message.from_user.id, me["full_name"], "jarima_bekor",
                    f"fine#{fid} user#{fine.get('employee_user_id')} "
                    f"{fine.get('amount')} — {reason}")
    # Asl xabardagi tugmalarni olib tashlaymiz
    if data.get("fcancel_chat") and data.get("fcancel_msg"):
        try:
            await bot.edit_message_reply_markup(
                chat_id=data["fcancel_chat"], message_id=data["fcancel_msg"],
                reply_markup=None,
            )
        except Exception:
            pass
    fine = await q.get_fine(fid)
    await message.answer(
        "🚫 <b>Jarima bekor qilindi</b>\n\n" + fine_text(fine)
        + "\n\n<i>Bu summa yakuniy oylikdan endi ayirilmaydi (oylikka qaytarildi).</i>"
    )
    await _notify_decision(
        bot, fine, message.from_user.id,
        "🚫 <b>Siz yozgan jarima moliya tomonidan bekor qilindi</b>\n\n" + fine_text(fine),
        "♻️ <b>Jarimangiz bekor qilindi</b>\n\n"
        f"💸 Summa: <b>{fine.get('amount')}</b>\n"
        f"✍️ Jarima sababi: {fine.get('reason') or '-'}\n"
        f"📝 Bekor qilish sababi: <i>{reason}</i>\n\n"
        "Oyligingizdan bu summa ayirilmaydi.",
    )


# ================= JARIMA TAFSILOTI =================
@router.callback_query(F.data.startswith("fsv:"))
async def fine_status_view(call: CallbackQuery):
    user = await _user_with_role(call.from_user.id, *_VIEW_ROLES)
    if not user:
        await call.answer("⛔", show_alert=True)
        return
    fine = await q.get_fine(int(call.data.split(":")[1]))
    if not fine:
        await call.answer("Jarima topilmadi.", show_alert=True)
        return
    scope = await _view_branch_scope(user)
    if scope is not None:
        prof = await q.get_employee_profile(fine["employee_user_id"]) or {}
        if (fine.get("branch_id") or prof.get("branch_id")) != scope:
            await call.answer("Jarima topilmadi.", show_alert=True)
            return
    markup = None
    st = fine_status(fine)
    if user["role"] in (ROLE_ACCOUNTANT, ROLE_ADMIN) and st != "cancelled":
        markup = kb.fine_decision_kb(fine["id"], st)
    await call.message.answer(fine_text(fine), reply_markup=markup)
    await call.answer()


# ================= 📋 JARIMALAR HOLATI / ⚖️ NAZORAT =================
async def _status_home_text(user, scope_kind):
    period = None if scope_kind == "all" else _period_now()
    counts = await q.fines_status_counts(period=period)
    branch_scope = await _view_branch_scope(user)
    if branch_scope:
        # Rahbar uchun hisobni o'z filiali bo'yicha qayta sanaymiz
        counts = {}
        for st, _label in kb.FINE_STATUS_TABS:
            rows = await q.list_fines_by_status(st, period=period,
                                                branch_id=branch_scope, limit=1000)
            counts[st] = (len(rows), _sum(rows))
    is_finance = user["role"] in (ROLE_ACCOUNTANT, ROLE_ADMIN)
    title = "⚖️ <b>Jarimalar nazorati</b>" if is_finance else "📋 <b>Jarimalar holati</b>"
    when = "barcha davr" if scope_kind == "all" else f"{_period_label(_period_now())} oyi"
    lines = [title, "━━━━━━━━━━━━", f"📅 Davr: <b>{when}</b>"]
    if branch_scope:
        br = await q.get_branch(branch_scope)
        lines.append(f"🏢 Filial: <b>{br['name'] if br else '-'}</b>")
    lines += [
        "",
        f"⏳ Ijro kutilmoqda: <b>{counts['pending'][0]}</b> ta · {fmt_money(counts['pending'][1])}",
        f"✅ Ijro etilgan: <b>{counts['executed'][0]}</b> ta · {fmt_money(counts['executed'][1])}",
        f"🚫 Bekor qilingan: <b>{counts['cancelled'][0]}</b> ta · {fmt_money(counts['cancelled'][1])}",
        "",
    ]
    if is_finance:
        lines.append("Jarimani ochib «✅ Ijro etildi» yoki «🚫 Bekor qilish» ni bosing.")
    else:
        lines.append("Bo'limni tanlang — har bir jarima sababi bilan ko'rsatiladi.")
    markup = kb.fines_status_home_kb(counts, scope_kind, with_search=is_finance)
    return "\n".join(lines), markup


@router.message(F.text.in_({kb.FINES_STATUS_BTN, kb.FINES_CONTROL_BTN,
                            "🚫 Jarimani bekor qilish"}))
async def fines_status_home(message: Message, state: FSMContext):
    user = await _user_with_role(message.from_user.id, *_VIEW_ROLES)
    if not user:
        await message.answer("⛔ Sizda ruxsat yo'q.")
        return
    await state.clear()
    if await _view_branch_scope(user) is False:
        await message.answer("Sizga filial biriktirilmagan. HR yoki admin bilan bog'laning.")
        return
    text, markup = await _status_home_text(user, "cur")
    await message.answer(text, reply_markup=markup)


@router.callback_query(F.data.startswith("fsth:"))
async def fines_status_home_cb(call: CallbackQuery, state: FSMContext):
    user = await _user_with_role(call.from_user.id, *_VIEW_ROLES)
    if not user:
        await call.answer("⛔", show_alert=True)
        return
    if await _view_branch_scope(user) is False:
        await call.answer("Sizga filial biriktirilmagan.", show_alert=True)
        return
    scope_kind = "all" if call.data.split(":")[1] == "all" else "cur"
    text, markup = await _status_home_text(user, scope_kind)
    try:
        await call.message.edit_text(text, reply_markup=markup)
    except Exception:
        await call.message.answer(text, reply_markup=markup)
    await call.answer()


def _fine_line(i, f):
    who = f.get("created_by_name") or "-"
    src = FINE_SOURCE_LABELS.get(f.get("source"))
    if src:
        who += f" ({src})"
    lines = [
        f"<b>{i}. {f.get('employee_name') or '-'}</b> · 🏢 {f.get('branch_name') or '-'}",
        f"   💰 {f.get('amount') or '-'} · 🕐 {(f.get('created_at') or '')[:16]}",
        f"   ✍️ Sabab: {f.get('reason') or '-'}",
        f"   🧑‍💼 Yozgan: {who}",
    ]
    st = fine_status(f)
    if st == "executed":
        lines.append(f"   ✅ Ijro: {f.get('executed_by_name') or '-'} · "
                     f"{(f.get('executed_at') or '')[:16]}")
    elif st == "cancelled":
        lines.append(f"   🚫 Bekor: {f.get('cancelled_by_name') or '-'} · "
                     f"{(f.get('cancelled_at') or '')[:16]}")
        lines.append(f"   📝 Bekor sababi: <i>{f.get('cancel_reason') or '— (ko‘rsatilmagan)'}</i>")
    return "\n".join(lines)


@router.callback_query(F.data.startswith("fst:"))
async def fines_status_list(call: CallbackQuery):
    user = await _user_with_role(call.from_user.id, *_VIEW_ROLES)
    if not user:
        await call.answer("⛔", show_alert=True)
        return
    _, status, scope_kind, page_s = call.data.split(":")
    if status not in dict(kb.FINE_STATUS_TABS):
        await call.answer()
        return
    page = max(int(page_s), 0)
    branch_scope = await _view_branch_scope(user)
    if branch_scope is False:
        await call.answer("Sizga filial biriktirilmagan.", show_alert=True)
        return
    period = None if scope_kind == "all" else _period_now()
    rows = await q.list_fines_by_status(
        status, period=period, branch_id=branch_scope,
        limit=PAGE_SIZE + 1, offset=page * PAGE_SIZE,
    )
    has_next = len(rows) > PAGE_SIZE
    rows = rows[:PAGE_SIZE]
    label = dict(kb.FINE_STATUS_TABS)[status]
    when = "barcha davr" if scope_kind == "all" else f"{_period_label(_period_now())} oyi"
    if not rows:
        await call.answer(f"{label}: {when} bo'yicha jarima yo'q.", show_alert=True)
        return
    start = page * PAGE_SIZE + 1
    blocks = [f"{label} — <b>{when}</b>\n━━━━━━━━━━━━"]
    blocks += [_fine_line(i, f) for i, f in enumerate(rows, start=start)]
    blocks.append("Batafsil ko'rish uchun jarimani tanlang 👇")
    await call.message.answer(
        "\n\n".join(blocks),
        reply_markup=kb.fines_status_list_kb(rows, status, scope_kind, page, has_next),
    )
    await call.answer()


@router.callback_query(F.data == "fcpeople")
async def fines_people_list(call: CallbackQuery, state: FSMContext):
    """Moliya: faol jarimasi bor xodimlar ro'yxati (qidiruv bilan)."""
    if not await _is_finance(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    await state.clear()
    rows = await q.employees_with_fines(limit=60)
    await call.answer()
    if not rows:
        await call.message.answer("✅ Hozircha faol jarimasi bor xodim yo'q.")
        return
    await call.message.answer(
        f"👥 Faol jarimasi bor xodimlar: <b>{len(rows)}</b> ta.\n"
        "🔍 tugma orqali filial/ism/username/ID bo'yicha qidirishingiz mumkin. "
        "Xodimni tanlang:",
        reply_markup=kb.fine_cancel_people_kb(rows),
    )


# ================= FILIAL RAHBARI: 💸 JARIMA QO'LLASH =================
async def manager_fine_menu(message: Message, user):
    """Rahbar o'z filiali xodimlari ro'yxatini ko'radi (jarima uchun)."""
    branch_id = await _manager_branch_id(user)
    if not branch_id:
        await message.answer("Sizga filial biriktirilmagan. HR yoki admin bilan bog'laning.")
        return
    employees = [
        e for e in await q.list_employee_profiles(branch_id=branch_id)
        if e.get("user_id") != user["id"]
    ]
    if not employees:
        await message.answer("Filialingizda hali xodim yo'q.")
        return
    await message.answer(
        "💸 <b>Jarima qo'llash</b>\n"
        "━━━━━━━━━━━━\n"
        "Jarima moliya bo'limiga yuboriladi; moliya uni ijro etadi yoki sabab "
        "bilan bekor qiladi.\n\nXodimni tanlang 👇",
        reply_markup=kb.employee_profiles_list_kb(
            employees[:40], prefix="mgrfine", with_search=False),
    )


@router.callback_query(F.data.startswith("mgrfine:"))
async def manager_fine_pick(call: CallbackQuery, state: FSMContext):
    user = await _user_with_role(call.from_user.id, ROLE_MANAGER, ROLE_ADMIN)
    if not user:
        await call.answer("⛔", show_alert=True)
        return
    uid = int(call.data.split(":")[1])
    profile = await q.get_employee_profile(uid)
    branch_id = await _manager_branch_id(user)
    if not profile or (user["role"] != ROLE_ADMIN and profile.get("branch_id") != branch_id):
        await call.answer("Xodim topilmadi.", show_alert=True)
        return
    await state.set_state(ManagerFineForm.amount)
    await state.update_data(mfine_uid=uid)
    await call.message.answer(
        f"👤 <b>{profile.get('full_name') or '-'}</b>\n\n"
        "💸 Jarima summasini kiriting. Masalan: <b>100 000</b>"
    )
    await call.answer()


@router.message(ManagerFineForm.amount, F.text)
async def manager_fine_amount(message: Message, state: FSMContext):
    amount = q._digits_to_int(message.text)
    if amount <= 0:
        await message.answer("❗️ Summani raqam bilan yozing. Masalan: <b>100 000</b>")
        return
    await state.update_data(mfine_amount=fmt_money(amount))
    await state.set_state(ManagerFineForm.reason)
    await message.answer("✍️ Jarima sababini yozing:")


@router.message(ManagerFineForm.reason, F.text)
async def manager_fine_save(message: Message, state: FSMContext, bot: Bot):
    user = await _user_with_role(message.from_user.id, ROLE_MANAGER, ROLE_ADMIN)
    data = await state.get_data()
    await state.clear()
    if not user:
        return
    uid, amount = data.get("mfine_uid"), data.get("mfine_amount")
    reason = message.text.strip()
    profile = await q.get_employee_profile(uid)
    if not profile:
        await message.answer("❗️ Xodim topilmadi.")
        return
    fid = await q.add_fine(uid, amount, reason, user["id"],
                           branch_id=profile.get("branch_id"), source="manager")
    await q.add_log(message.from_user.id, user["full_name"], "jarima_yozildi",
                    f"manager {uid}: {amount}")
    await message.answer(
        f"✅ Jarima saqlandi (#{fid}).\n\n"
        "<i>Jarima moliya bo'limiga yuborildi. Ijro etilsa yoki bekor qilinsa "
        "sizga xabar keladi.</i>"
    )
    if profile.get("tg_id"):
        await safe_send(
            bot, profile["tg_id"],
            f"💸 Sizga jarima yozildi.\n\n💰 Summa: <b>{amount}</b>\n✍️ Sabab: {reason}"
            "\n\nBu summa oyligingizdan ayiriladi."
        )
    await notify_finance_new_fine(bot, fid, "Filial rahbari")
    # HR ham xabardor bo'lsin
    fine = await q.get_fine(fid)
    for tid in set(await q.all_user_tg_ids(role=ROLE_HR)):
        await safe_send(bot, tid, "ℹ️ <b>Filial rahbari jarima yozdi</b>\n\n" + fine_text(fine))

