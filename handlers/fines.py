"""Jarimalar nazorati: moliya «✅ Ijro etildi» / «🚫 Bekor qilish» (sabab bilan),
HR / direktor / filial rahbari uchun «📋 Jarimalar holati» va filial rahbarining
o'z filiali xodimiga «💸 Jarima qo'llash» oqimi.

Jarima holatlari (`fines.status`):
  pending   — yozildi, moliya ijrosini kutmoqda (oylikdan ayiriladi)
  executed  — moliya «ijro etildi» deb tasdiqladi (oylikdan ayiriladi)
  cancelled — moliya sabab bilan bekor qildi (oylikdan ayirilmaydi)
"""
from datetime import timedelta
from html import escape

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
    decade_start, decade_end, decade_prev, decade_next, decade_tag,
    decade_from_tag, decade_label,
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
    ok, result = await _execute_one(bot, fid, me, call.from_user.id)
    if not ok:
        await call.answer(result, show_alert=True)
        return
    try:
        await call.message.edit_reply_markup(reply_markup=kb.fine_decision_kb(fid, "executed"))
    except Exception:
        pass
    await call.message.answer(
        "✅ <b>Jarima ijro etildi</b>\n\n" + fine_text(result),
        reply_markup=kb.fine_decision_kb(fid, "executed"),
    )
    await call.answer("Ijro etildi ✅")


async def _execute_one(bot: Bot, fid, me, actor_tg, employee_user_id=None):
    """Jarimani «ijro etildi / amalga oshirildi» qiladi (atomik).

    (True, yangilangan jarima) yoki (False, xato matni) qaytaradi. Jarima yozgan
    shaxsga xabar boradi."""
    fine = await q.get_fine(fid)
    if not fine or (employee_user_id and fine.get("employee_user_id") != employee_user_id):
        return False, "Jarima topilmadi."
    if not await q.execute_fine(fid, me["id"]):
        st = fine_status(fine)
        return False, ("Bu jarima allaqachon bekor qilingan." if st == "cancelled"
                       else "Bu jarima allaqachon amalga oshirilgan.")
    await q.add_log(actor_tg, me["full_name"], "jarima_ijro",
                    f"fine#{fid} user#{fine.get('employee_user_id')} {fine.get('amount')}")
    fine = await q.get_fine(fid)
    await _notify_decision(
        bot, fine, actor_tg,
        "✅ <b>Siz yozgan jarima moliya tomonidan ijro etildi</b>\n\n" + fine_text(fine),
    )
    return True, fine


# ================= 🚫 BEKOR QILISH (sabab bilan) =================
# «fcancel:» — eski xabarlardagi tugmalar uchun ham ishlaydi
@router.callback_query(F.data.startswith(("fcanc:", "fcancel:")))
async def fine_cancel_ask(call: CallbackQuery, state: FSMContext):
    if not await _is_finance(call.from_user.id):
        await call.answer("⛔ Faqat moliya bo'limi uchun.", show_alert=True)
        return
    await _ask_cancel(call, state, int(call.data.split(":")[1]))


async def _ask_cancel(call: CallbackQuery, state: FSMContext, fid, back=None,
                      employee_user_id=None):
    """Bekor qilish sababini so'raydi. back — 10 kunlik kartochka konteksti
    («davr:uid:sahifa»): sabab yozilgach kartochka o'sha xabarda yangilanadi."""
    fine = await q.get_fine(fid)
    if not fine or (employee_user_id and fine.get("employee_user_id") != employee_user_id):
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
        fcancel_back=back,
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
    back = data.get("fcancel_back")
    if back and data.get("fcancel_chat") and data.get("fcancel_msg"):
        # 10 kunlik ro'yxatdagi xodim kartochkasini o'sha xabarda yangilaymiz
        try:
            tag, uid, page = back.split(":")
            view = await _card_view(decade_from_tag(tag), int(uid), int(page))
            if view:
                await bot.edit_message_text(
                    view[0], chat_id=data["fcancel_chat"],
                    message_id=data["fcancel_msg"], reply_markup=view[1],
                )
        except Exception:
            pass
    elif data.get("fcancel_chat") and data.get("fcancel_msg"):
        # Asl xabardagi tugmalarni olib tashlaymiz
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



# ================= 🗓 10 KUNLIK JARIMALAR (moliya) =================
# Har 10 kunda (1–10, 11–20, 21–oy oxiri) moliyaga avtomatik ro'yxat keladi
# (services/reminders.py::finance_loop). Xodim tugmasi bosilsa — ma'lumotlari,
# jarima summasi va «✅ Amalga oshirildi» / «🚫 Bekor qilish» / «⬅️ Orqaga».
DIGEST_PAGE_SIZE = 20
_STATE_ORDER = {"pending": 0, "executed": 1, "cancelled": 2}


def _decade_range(start):
    """10 kunlik uchun [since, until) — 'YYYY-MM-DD'."""
    return start.isoformat(), (decade_end(start) + timedelta(days=1)).isoformat()


def digest_people(fines):
    """Jarimalarni xodim bo'yicha guruhlaydi: kutilayotganlar birinchi."""
    people = {}
    for f in fines:
        uid = f.get("employee_user_id")
        p = people.setdefault(uid, {
            "uid": uid, "name": f.get("employee_name") or "-",
            "branch": f.get("branch_name"), "fines": [],
        })
        p["fines"].append(f)
    for p in people.values():
        sts = [fine_status(f) for f in p["fines"]]
        p["state"] = ("pending" if "pending" in sts
                      else "executed" if "executed" in sts else "cancelled")
        p["active_sum"] = sum(q._digits_to_int(f.get("amount"))
                              for f, st in zip(p["fines"], sts) if st != "cancelled")
    return sorted(people.values(), key=lambda p: (
        _STATE_ORDER[p["state"]], (p["branch"] or "").lower(), p["name"].lower()))


def _status_totals(fines):
    out = {k: [0, 0] for k in _STATE_ORDER}
    for f in fines:
        t = out[fine_status(f)]
        t[0] += 1
        t[1] += q._digits_to_int(f.get("amount"))
    return out


def digest_text(start, fines, people, older=(0, 0), today=None):
    today = today or now_tk().date()
    in_progress = decade_start(today) == start
    t = _status_totals(fines)
    period = f"📅 Davr: <b>{decade_label(start)}</b>"
    if in_progress:
        period += " <i>(davom etmoqda)</i>"
    lines = ["🗓 <b>10 kunlik jarimalar</b>", "━━━━━━━━━━━━", period, ""]
    if not fines:
        lines.append("✅ Bu 10 kunlikda hech bir xodimga jarima qo'llanilmagan.")
    else:
        if t["pending"][0]:
            lines.append("❗️ <b>Ushbu xodimlarga jarima qo'llangan — ularni amalga "
                         "oshiring.</b>")
        else:
            lines.append("✅ Bu davrdagi barcha jarimalar ko'rib chiqilgan.")
        total = t["pending"][1] + t["executed"][1]
        lines += [
            "",
            f"👥 Xodimlar: <b>{len(people)}</b> nafar · 💸 Jarimalar: <b>{len(fines)}</b> ta",
            f"💰 Jami (bekor qilinganlarsiz): <b>{fmt_money(total)}</b>",
            "",
            f"⏳ Kutilmoqda: <b>{t['pending'][0]}</b> ta · {fmt_money(t['pending'][1])}",
            f"✅ Amalga oshirilgan: <b>{t['executed'][0]}</b> ta · "
            f"{fmt_money(t['executed'][1])}",
            f"🚫 Bekor qilingan: <b>{t['cancelled'][0]}</b> ta · "
            f"{fmt_money(t['cancelled'][1])}",
            "",
            "👇 Xodimni tanlang — ma'lumotlari va jarima summasi chiqadi.",
            "<i>⏳ kutilmoqda · ✅ amalga oshirilgan · 🚫 bekor qilingan</i>",
        ]
    if older[0]:
        lines += ["", f"⚠️ Oldingi davrlardan ijro kutilayotgan: <b>{older[0]}</b> ta · "
                      f"{fmt_money(older[1])}"]
    return "\n".join(lines)


async def _older_pending(start):
    rows = await q.list_fines_by_status("pending", limit=5000)
    rows = [f for f in rows if (f.get("created_at") or "") < start.isoformat()]
    return len(rows), _sum(rows)


async def digest_view(start, page=0, today=None):
    """10 kunlik ro'yxat matni va tugmalari."""
    today = today or now_tk().date()
    fines = await q.fines_between(*_decade_range(start))
    people = digest_people(fines)
    pages = max(1, -(-len(people) // DIGEST_PAGE_SIZE))
    page = min(max(page, 0), pages - 1)
    chunk = people[page * DIGEST_PAGE_SIZE:(page + 1) * DIGEST_PAGE_SIZE]
    older = await _older_pending(start)
    nxt = decade_next(start)
    markup = kb.fine_digest_kb(
        decade_tag(start), chunk, page, pages,
        prev_tag=decade_tag(decade_prev(start)),
        next_tag=decade_tag(nxt) if nxt <= today else None,
        older_pending=older[0],
    )
    return digest_text(start, fines, people, older, today), markup


def _h(value, limit=None):
    """Foydalanuvchi yozgan matn — HTML uchun xavfsiz (va kerak bo'lsa qisqartirilgan)."""
    s = str(value or "-").strip() or "-"
    if limit and len(s) > limit:
        s = s[:limit - 1].rstrip() + "…"
    return escape(s, quote=False)


def _fine_block(i, f):
    who = _h(f.get("created_by_name"))
    src = FINE_SOURCE_LABELS.get(f.get("source"))
    if src:
        who += f" ({src})"
    st = fine_status(f)
    mark = kb.FINE_DIGEST_MARKS[st]
    lines = [
        f"{i}) {mark} <b>{fmt_money(q._digits_to_int(f.get('amount')))}</b> · "
        f"🕐 {(f.get('created_at') or '')[:16]}",
        f"   ✍️ Sabab: {_h(f.get('reason'), 150)}",
        f"   🧑‍💼 Yozgan: {who}",
    ]
    if st == "executed":
        lines.append(f"   ✅ Amalga oshirildi: {_h(f.get('executed_by_name'))} · "
                     f"{(f.get('executed_at') or '')[:16]}")
    elif st == "cancelled":
        lines.append(f"   🚫 Bekor qilindi: {_h(f.get('cancelled_by_name'))} · "
                     f"{(f.get('cancelled_at') or '')[:16]}")
        lines.append(f"   📝 Sabab: <i>{_h(f.get('cancel_reason'), 150)}</i>")
    return "\n".join(lines)


CARD_MAX_FINES = 10      # kartochkada ko'rsatiladigan jarimalar (tugmalari bilan)
CARD_MAX_CHARS = 3800    # Telegram xabar chegarasi 4096 — zaxira bilan


async def _card_view(start, uid, page=0):
    """Xodim kartochkasi (shu 10 kunlikdagi jarimalari bilan) yoki None."""
    if not start:
        return None
    fines = await q.fines_between(*_decade_range(start), employee_user_id=uid)
    if not fines:
        return None
    prof = await q.get_employee_profile(uid) or {}
    user = await q.get_user_by_id(uid) or {}
    first = fines[0]
    name = prof.get("full_name") or user.get("full_name") or first.get("employee_name")
    t = _status_totals(fines)
    head = [
        f"👤 <b>{_h(name)}</b>",
        "━━━━━━━━━━━━",
        f"🏢 Filial: <b>{_h(prof.get('branch_name') or first.get('branch_name'))}</b>",
        f"💼 Lavozim: {_h(prof.get('position') or first.get('position'))}",
        f"📞 Telefon: {_h(prof.get('phone') or user.get('phone'))}",
        f"🆔 ID: <code>{uid}</code>",
        f"📅 Davr: {decade_label(start)}",
        "",
        f"💸 <b>Jarimalar — {len(fines)} ta</b>",
        "",
    ]
    foot = [
        "",
        "━━━━━━━━━━━━",
        f"💰 Jarima summasi: <b>{fmt_money(t['pending'][1] + t['executed'][1])}</b>",
    ]
    if t["pending"][0]:
        foot.append(f"⏳ Kutilmoqda: {fmt_money(t['pending'][1])}")
    if t["executed"][0]:
        foot.append(f"✅ Amalga oshirilgan: {fmt_money(t['executed'][1])}")
    if t["cancelled"][0]:
        foot.append(f"🚫 Bekor qilingan: {fmt_money(t['cancelled'][1])} "
                    "<i>(oylikdan ayirilmaydi)</i>")

    blocks = [_fine_block(i, f) for i, f in enumerate(fines[:CARD_MAX_FINES], start=1)]

    def assemble(n):
        body = "\n\n".join(blocks[:n])
        rest = len(fines) - n
        if rest > 0:
            body += (f"\n\n<i>… yana {rest} ta jarima — «⚖️ Jarimalar nazorati» "
                     "bo'limida.</i>")
        return "\n".join(head + [body] + foot)

    shown = len(blocks)
    text = assemble(shown)
    while len(text) > CARD_MAX_CHARS and shown > 1:
        shown -= 1
        text = assemble(shown)
    pending_total = sum(1 for f in fines if fine_status(f) == "pending")
    return text, kb.fine_digest_card_kb(decade_tag(start), uid, page, fines[:shown],
                                        pending_total=pending_total)


async def _edit_or_send(call: CallbackQuery, text, markup):
    try:
        await call.message.edit_text(text, reply_markup=markup)
    except Exception as e:
        if "not modified" not in str(e):
            await call.message.answer(text, reply_markup=markup)


async def send_fine_digest(bot: Bot, start, tg_ids=None):
    """10 kunlik ro'yxatni moliya xodimlariga yuboradi. Yuborilganlar soni."""
    text, markup = await digest_view(start)
    targets = tg_ids if tg_ids is not None else await q.all_user_tg_ids(role=ROLE_ACCOUNTANT)
    sent = 0
    for tid in set(targets):
        if await safe_send(bot, tid, text, reply_markup=markup):
            sent += 1
    return sent


@router.message(F.text == kb.FINE_DIGEST_BTN)
async def fine_digest_menu(message: Message, state: FSMContext):
    if not await _is_finance(message.from_user.id):
        await message.answer("⛔ Bu bo'lim faqat moliya bo'limi uchun.")
        return
    await state.clear()
    text, markup = await digest_view(decade_start(now_tk().date()))
    await message.answer(text, reply_markup=markup)


def _parse_tag(tag):
    if tag == "cur":
        return decade_start(now_tk().date())
    return decade_from_tag(tag)


@router.callback_query(F.data.startswith("fdl:"))
async def fine_digest_list(call: CallbackQuery):
    if not await _is_finance(call.from_user.id):
        await call.answer("⛔ Faqat moliya bo'limi uchun.", show_alert=True)
        return
    try:
        _, tag, page = call.data.split(":")
        start, page = _parse_tag(tag), int(page)
    except ValueError:
        start = None
    if not start:
        await call.answer("Noto'g'ri tugma.", show_alert=True)
        return
    if start > now_tk().date():
        await call.answer("Bu davr hali boshlanmagan.", show_alert=True)
        return
    text, markup = await digest_view(start, page)
    await _edit_or_send(call, text, markup)
    await call.answer()


def _parse_card_cb(data, with_fid):
    """«fdX:davr:uid[:fid]:sahifa» -> (start, uid, fid, page) yoki None."""
    parts = data.split(":")
    try:
        start = decade_from_tag(parts[1])
        uid = int(parts[2])
        fid = int(parts[3]) if with_fid else None
        page = int(parts[4 if with_fid else 3])
    except (IndexError, ValueError):
        return None
    return (start, uid, fid, page) if start else None


@router.callback_query(F.data.startswith("fdu:"))
async def fine_digest_card(call: CallbackQuery):
    if not await _is_finance(call.from_user.id):
        await call.answer("⛔ Faqat moliya bo'limi uchun.", show_alert=True)
        return
    parsed = _parse_card_cb(call.data, with_fid=False)
    view = await _card_view(parsed[0], parsed[1], parsed[3]) if parsed else None
    if not view:
        await call.answer("Bu xodimning shu davrda jarimasi topilmadi.", show_alert=True)
        return
    await _edit_or_send(call, *view)
    await call.answer()


@router.callback_query(F.data.startswith("fdx:"))
async def fine_digest_execute(call: CallbackQuery, bot: Bot):
    me = await _is_finance(call.from_user.id)
    if not me:
        await call.answer("⛔ Faqat moliya bo'limi uchun.", show_alert=True)
        return
    parsed = _parse_card_cb(call.data, with_fid=True)
    if not parsed:
        await call.answer("Noto'g'ri tugma.", show_alert=True)
        return
    start, uid, fid, page = parsed
    ok, result = await _execute_one(bot, fid, me, call.from_user.id, employee_user_id=uid)
    view = await _card_view(start, uid, page)
    if view:
        await _edit_or_send(call, *view)
    if ok:
        await call.answer("✅ Jarima amalga oshirildi")
    else:
        await call.answer(result, show_alert=True)


@router.callback_query(F.data.startswith("fdxa:"))
async def fine_digest_execute_all(call: CallbackQuery, bot: Bot):
    me = await _is_finance(call.from_user.id)
    if not me:
        await call.answer("⛔ Faqat moliya bo'limi uchun.", show_alert=True)
        return
    parsed = _parse_card_cb(call.data, with_fid=False)
    if not parsed:
        await call.answer("Noto'g'ri tugma.", show_alert=True)
        return
    start, uid, _, page = parsed
    fines = await q.fines_between(*_decade_range(start), employee_user_id=uid)
    done = 0
    for f in fines:
        if fine_status(f) == "pending":
            ok, _ = await _execute_one(bot, f["id"], me, call.from_user.id,
                                       employee_user_id=uid)
            done += int(ok)
    view = await _card_view(start, uid, page)
    if view:
        await _edit_or_send(call, *view)
    if done:
        await call.answer(f"✅ {done} ta jarima amalga oshirildi")
    else:
        await call.answer("Kutilayotgan jarima qolmagan.", show_alert=True)


@router.callback_query(F.data.startswith("fdc:"))
async def fine_digest_cancel(call: CallbackQuery, state: FSMContext):
    if not await _is_finance(call.from_user.id):
        await call.answer("⛔ Faqat moliya bo'limi uchun.", show_alert=True)
        return
    parsed = _parse_card_cb(call.data, with_fid=True)
    if not parsed:
        await call.answer("Noto'g'ri tugma.", show_alert=True)
        return
    start, uid, fid, page = parsed
    await _ask_cancel(call, state, fid, back=f"{decade_tag(start)}:{uid}:{page}",
                      employee_user_id=uid)
