"""Kunlik dam olish rejasi.

Har kuni 17:00 da filial rahbariga «ertaga kim dam oladi» so'rovi boradi.
Rahbar tasdiqlaydi yoki tahrirlaydi (har bir xodimni «dam oladi ⇄ keladi» qilib
belgilaydi). Tasdiqlangach reja HR ga to'planadi va 08:30 da chiroyli Excel
hisobot bo'lib yuboriladi.
"""
from datetime import timedelta

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery

from database import queries as q
from database.db import ROLE_HR, ROLE_ADMIN, ROLE_MANAGER, ROLE_DIRECTOR
import keyboards as kb
from services import export
from utils import iso_to_display, now_tk

router = Router()

# Python weekday() -> o'zbekcha nom (Monday=0)
WEEKDAY_UZ = [
    "Dushanba", "Seshanba", "Chorshanba", "Payshanba",
    "Juma", "Shanba", "Yakshanba",
]

_WEEKDAY_ALIASES = {
    "Dushanba": ("dushanba", "душанба", "понедельник"),
    "Seshanba": ("seshanba", "сешанба", "вторник"),
    "Chorshanba": ("chorshanba", "чоршанба", "среда"),
    "Payshanba": ("payshanba", "пайшанба", "четверг"),
    "Juma": ("juma", "жума", "пятница"),
    # Uzunroq nom avval tekshiriladi: "yakshanba" ichida "shanba" bor.
    "Yakshanba": ("yakshanba", "якшанба", "воскресенье"),
    "Shanba": ("shanba", "шанба", "суббота"),
}


def weekday_uz(dt):
    return WEEKDAY_UZ[dt.weekday()]


def canonical_weekday(value):
    """Lotin, kirill yoki ruscha hafta kunini kanonik o'zbekcha nomga keltiradi."""
    text = str(value or "").strip().casefold()
    if not text:
        return None
    for canonical, aliases in _WEEKDAY_ALIASES.items():
        if any(alias in text for alias in aliases):
            return canonical
    return None


def expected_day_status(rest_day, plan_weekday):
    """Doimiy jadval bo'yicha shu kuni xodim dam olishi yoki ishlashini qaytaradi."""
    planned = canonical_weekday(plan_weekday)
    if not planned:
        return "work"
    return "off" if canonical_weekday(rest_day) == planned else "work"


def dayoff_plan_mismatches(plan, items):
    """Rahbar holati doimiy dam olish jadvalidan farq qilgan xodimlar."""
    weekday = plan.get("weekday")
    return [
        it for it in items
        if it.get("day_status") in ("off", "work")
        and it.get("day_status") != expected_day_status(it.get("rest_day"), weekday)
    ]


def plan_prompt_text(plan, items, *, reminder=False):
    header = ""
    if reminder:
        header += "⏰ <b>ESLATMA — ertangi dam olishni hali tasdiqlamadingiz!</b>\n\n"
    header += (
        "🛌 <b>Ertangi dam olishni tasdiqlang</b>\n"
        "━━━━━━━━━━━━\n"
        f"📆 Sana: <b>{iso_to_display(plan.get('plan_date'))}</b> ({plan.get('weekday')})\n"
        f"🏢 Filial: <b>{plan.get('branch_name') or '-'}</b>\n\n"
        "🟢 — ishga keladi   🔴 — kelmaydi (dam oladi)\n\n"
    )
    if items:
        mismatched_ids = {it.get("id") for it in dayoff_plan_mismatches(plan, items)}
        for i, it in enumerate(items, start=1):
            dot = "🟢" if it.get("day_status") == "work" else "🔴"
            warning = " ⚠️ JADVALDAN FARQ QILADI" if it.get("id") in mismatched_ids else ""
            rest_day = it.get("rest_day") or "belgilanmagan"
            header += (
                f"{i}. {dot} {it.get('full_name') or '-'} — {it.get('position') or '-'}"
                f"\n    Doimiy dam kuni: {rest_day}{warning}\n"
            )
    else:
        header += "Bu filialda xodim yo'q.\n"
    off_n = sum(1 for it in items if it.get("day_status") == "off")
    work_n = len(items) - off_n
    mismatch_n = len(dayoff_plan_mismatches(plan, items))
    header += (
        f"\n🟢 Ishga keladi: <b>{work_n}</b> · 🔴 Kelmaydi: <b>{off_n}</b> "
        f"({len(items)} nafar)\n"
    )
    if mismatch_n:
        header += f"⚠️ Doimiy jadvaldan farqli: <b>{mismatch_n}</b> nafar\n"
    header += (
        "\n👇 Kimningdir holati noto'g'ri bo'lsa — <b>ustiga bosing</b> (🟢⇄🔴). "
        "Hammasi to'g'ri bo'lsa <b>✅ Tasdiqlash</b>ni bosing."
    )
    return header


async def _editing_locked(user, plan):
    """Eski rejani hamma uchun, yuborilgan rejani rahbar uchun qulflaydi.

    HR/Admin bugungi xatoni tuzatib, yangilangan hisobotni qayta olishi mumkin.
    """
    date_iso = plan.get("plan_date")
    if not date_iso:
        return False
    today = now_tk().strftime("%Y-%m-%d")
    if date_iso < today:
        # Kuni o'tган reja — endi tahrirlanmaydi (odatda eski so'rov xabari bosiladi)
        return True
    flag = await q.get_setting(f"dayoff_report_sent:{date_iso}", "0")
    # HR/Admin bugungi hisobotdagi xatoni tuzatib, hisobotni qayta olishi mumkin.
    if user and user.get("role") in (ROLE_HR, ROLE_ADMIN):
        return False
    return str(flag) == "1"


def _locked_alert(plan):
    """Tahrir yopilganda ko'rsatiladigan aniq xabar (qaysi kun ekanini aytadi)."""
    d = iso_to_display(plan.get("plan_date"))
    return (
        f"⛔ {d} kunidagi dam olish rejasi allaqachon HR ga yuborilgan "
        "(yoki kuni o'tган) — endi tahrirlab bo'lmaydi."
    )


async def _can_manage(user, plan):
    if not user:
        return False
    if user["role"] == ROLE_ADMIN:
        return True
    if user["role"] == ROLE_HR:
        # HR istalgan filialning bugungi/ertangi rejasini tahrirlashi mumkin.
        return True
    if user["role"] == ROLE_MANAGER:
        # Rahbar faqat o'z filiali rejasini boshqaradi
        branch_id = user.get("branch_id")
        if not branch_id:
            profile = await q.get_employee_profile(user["id"])
            branch_id = profile.get("branch_id") if profile else None
        if not branch_id:
            # Filialga bog'lanmagan rahbar hech qaysi rejani boshqara olmaydi
            return False
        return plan.get("branch_id") == branch_id
    return False


# ---------------- RAHBAR: TAHRIRLASH ----------------
@router.callback_query(F.data.startswith("dopl_edit:"))
async def dayoff_plan_edit(call: CallbackQuery):
    user = await q.get_user(call.from_user.id)
    plan_id = int(call.data.split(":")[1])
    plan = await q.get_dayoff_plan(plan_id)
    if not plan:
        await call.answer("Reja topilmadi.", show_alert=True)
        return
    if not await _can_manage(user, plan):
        await call.answer("⛔", show_alert=True)
        return
    if await _editing_locked(user, plan):
        await call.answer(_locked_alert(plan), show_alert=True)
        return
    items = await q.list_dayoff_plan_items(plan_id)
    if not items:
        await call.answer("Bu rejada xodim yo'q.", show_alert=True)
        return
    # Yangi xabar sifatida ochamiz — HR filial ro'yxati buzilmasligi uchun
    await call.message.answer(
        plan_prompt_text(plan, items),
        reply_markup=kb.dayoff_plan_edit_kb(plan_id, items),
    )
    await call.answer()


@router.callback_query(F.data.startswith("dopl_tog:"))
async def dayoff_plan_toggle(call: CallbackQuery):
    user = await q.get_user(call.from_user.id)
    item_id = int(call.data.split(":")[1])
    item = await q.get_dayoff_plan_item(item_id)
    if not item:
        await call.answer("Topilmadi.", show_alert=True)
        return
    plan = await q.get_dayoff_plan(item["plan_id"])
    if not plan or not await _can_manage(user, plan):
        await call.answer("⛔", show_alert=True)
        return
    if await _editing_locked(user, plan):
        await call.answer(_locked_alert(plan), show_alert=True)
        return
    new_status = await q.toggle_dayoff_plan_item(item_id)
    # toggle query tasdiqni ham shu tranzaksiyada bekor qiladi. Aks holda tahrir
    # qayta tasdiqlanmasdan HR hisobotiga kirib ketishi mumkin edi.
    await q.add_log(
        call.from_user.id, user.get("full_name"), "dam_olish_reja_tahrir",
        f"plan#{item['plan_id']}, item#{item_id}, xodim#{item.get('user_id')}: "
        f"{item.get('day_status')} -> {new_status}",
    )
    items = await q.list_dayoff_plan_items(item["plan_id"])
    markup = kb.dayoff_plan_edit_kb(item["plan_id"], items)
    try:
        await call.message.edit_text(plan_prompt_text(plan, items), reply_markup=markup)
    except Exception:
        try:
            await call.message.edit_reply_markup(reply_markup=markup)
        except Exception:
            pass
    await call.answer("🟢 ishga keladi" if new_status == "work" else "🔴 kelmaydi")


async def _clear_plan_notices(bot: Bot, plan_id, keep_chat_id=None, keep_msg_id=None):
    """Reja bo'yicha yuborilgan barcha so'rov/eslatma xabarlaridagi tugmalarni
    olib tashlaydi (joriy xabardan tashqari). Tasdiqlangach eski xabarlarda
    «✅ Tasdiqlash» tugmasi qolib, chalkashtirmasligi uchun."""
    try:
        rows = await q.pop_request_notices("dayoff_plan", plan_id)
    except Exception:
        return
    for row in rows:
        chat_id, message_id = row["chat_id"], row["message_id"]
        if (keep_chat_id is not None and int(chat_id) == int(keep_chat_id)
                and keep_msg_id is not None and int(message_id) == int(keep_msg_id)):
            continue  # joriy xabar — uni handlerning o'zi yangilaydi
        try:
            await bot.edit_message_reply_markup(
                chat_id=chat_id, message_id=message_id, reply_markup=None
            )
        except Exception:
            try:
                await bot.delete_message(chat_id, message_id)
            except Exception:
                pass


def _override_warning_text(plan, mismatches):
    lines = [
        "⚠️ <b>Doimiy dam olish jadvalidan farq bor</b>",
        f"📆 {iso_to_display(plan.get('plan_date'))} ({plan.get('weekday')})",
        f"🏢 {plan.get('branch_name') or '-'}",
        "",
    ]
    for it in mismatches:
        actual = "DAM OLADI" if it.get("day_status") == "off" else "ISHGA KELADI"
        lines.append(
            f"• {it.get('full_name') or '-'}: doimiy dam kuni "
            f"<b>{it.get('rest_day') or 'belgilanmagan'}</b>, siz <b>{actual}</b> deb belgiladingiz."
        )
    lines.append("\nBu bir kunlik o'zgarish ataylab qilingan bo'lsa, yana tasdiqlang.")
    return "\n".join(lines)


async def _notify_hr_confirmed(bot, plan, items, confirmed_by, confirmed_by_tg):
    """Rahbar tasdig'ini HR/Adminlarga shu zahoti ko'rsatadi."""
    from utils import safe_send
    off = [it for it in items if it.get("day_status") == "off"]
    mismatches = dayoff_plan_mismatches(plan, items)
    lines = [
        "✅ <b>Filialning kunlik dam olish rejasi tasdiqlandi</b>",
        f"📆 {iso_to_display(plan.get('plan_date'))} ({plan.get('weekday')})",
        f"🏢 {plan.get('branch_name') or '-'}",
        f"👤 Tasdiqladi: {confirmed_by or '-'}",
        f"🛌 Dam oladi: <b>{len(off)}</b> nafar",
    ]
    for it in off:
        marker = " ⚠️ jadvaldan farqli" if it in mismatches else ""
        lines.append(f"  • {it.get('full_name') or '-'} — {it.get('rest_day') or 'dam kuni noma’lum'}{marker}")
    if mismatches:
        lines.append(f"\n⚠️ Doimiy jadvaldan farqli o'zgarish: <b>{len(mismatches)}</b> ta.")
    targets = set(await q.all_user_tg_ids(role=ROLE_HR))
    targets.update(await q.all_user_tg_ids(role=ROLE_ADMIN))
    targets.discard(confirmed_by_tg)
    for tid in targets:
        await safe_send(
            bot, tid, "\n".join(lines),
            reply_markup=kb.dayoff_plan_edit_again_kb(plan["id"]),
        )


async def _confirm_plan(call, bot, user, plan, *, force=False):
    items = await q.list_dayoff_plan_items(plan["id"])
    mismatches = dayoff_plan_mismatches(plan, items)
    if mismatches and not force:
        text = _override_warning_text(plan, mismatches)
        try:
            await call.message.edit_text(
                text, reply_markup=kb.dayoff_plan_override_confirm_kb(plan["id"])
            )
        except Exception:
            await call.message.answer(
                text, reply_markup=kb.dayoff_plan_override_confirm_kb(plan["id"])
            )
        await call.answer("Jadvaldan farqli holatlar bor", show_alert=True)
        return

    await q.set_dayoff_plan_status(plan["id"], "confirmed", confirmed_by=user["id"])
    await _clear_plan_notices(
        bot, plan["id"], keep_chat_id=call.from_user.id,
        keep_msg_id=call.message.message_id,
    )
    await q.add_log(call.from_user.id, user.get("full_name"),
                    "dam_olish_reja_tasdiq", f"plan#{plan['id']}")
    off = [it for it in items if it.get("day_status") == "off"]
    work_n = len(items) - len(off)
    lines = [
        "✅ <b>Tasdiqlandi. Rahmat!</b>",
        f"📆 {iso_to_display(plan.get('plan_date'))} ({plan.get('weekday')})",
        f"🏢 {plan.get('branch_name') or '-'}",
        f"🟢 Ishga keladi: <b>{work_n}</b> nafar",
        f"🔴 Kelmaydi (dam oladi): <b>{len(off)}</b> nafar",
    ]
    for it in off:
        marker = " ⚠️" if it in mismatches else ""
        lines.append(f"  🔴 {it.get('full_name')}{marker}")
    if mismatches:
        lines.append(f"\n⚠️ Jadvaldan farqli o'zgarishlar: <b>{len(mismatches)}</b> ta.")
    lines.append("\n✏️ Xato bo'lsa — HR hisobotigacha tahrirlashingiz mumkin.")
    edit_kb = kb.dayoff_plan_edit_again_kb(plan["id"])
    try:
        await call.message.edit_text("\n".join(lines), reply_markup=edit_kb)
    except Exception:
        await call.message.answer("\n".join(lines), reply_markup=edit_kb)
    await call.answer("Tasdiqlandi ✅")
    await _notify_hr_confirmed(
        bot, plan, items, user.get("full_name"), call.from_user.id
    )


@router.callback_query(F.data.startswith("dopl_ok:"))
async def dayoff_plan_confirm(call: CallbackQuery, bot: Bot):
    user = await q.get_user(call.from_user.id)
    plan_id = int(call.data.split(":")[1])
    plan = await q.get_dayoff_plan(plan_id)
    if not plan:
        await call.answer("Reja topilmadi.", show_alert=True)
        return
    if not await _can_manage(user, plan):
        await call.answer("⛔", show_alert=True)
        return
    if await _editing_locked(user, plan):
        await call.answer(_locked_alert(plan), show_alert=True)
        return
    await _confirm_plan(call, bot, user, plan)


@router.callback_query(F.data.startswith("dopl_force:"))
async def dayoff_plan_force_confirm(call: CallbackQuery, bot: Bot):
    user = await q.get_user(call.from_user.id)
    plan_id = int(call.data.split(":")[1])
    plan = await q.get_dayoff_plan(plan_id)
    if not plan:
        await call.answer("Reja topilmadi.", show_alert=True)
        return
    if not await _can_manage(user, plan):
        await call.answer("⛔", show_alert=True)
        return
    if await _editing_locked(user, plan):
        await call.answer(_locked_alert(plan), show_alert=True)
        return
    await _confirm_plan(call, bot, user, plan, force=True)


# ---------------- HR: KUNLIK DAM OLISH HISOBOTI (on-demand) ----------------
@router.message(F.text == "🛌 Kunlik dam olish")
async def hr_dayoff_report(message: Message, bot: Bot):
    user = await q.get_user(message.from_user.id)
    if not user or user["role"] not in (ROLE_HR, ROLE_ADMIN, ROLE_DIRECTOR):
        await message.answer("⛔ Ruxsat yo'q.")
        return
    today = now_tk().strftime("%Y-%m-%d")
    tomorrow = (now_tk() + timedelta(days=1)).strftime("%Y-%m-%d")
    await send_dayoff_report(bot, [message.from_user.id], today, note_empty=True)
    # HR/Admin — hisoboti hali yuborilmagan rejalarni tahrirlash imkoni.
    # Bugungi (08:30 hisobotgacha) + ertangi (17:00 da tayyorlangan yangi) reja.
    if user["role"] in (ROLE_HR, ROLE_ADMIN):
        editable = []
        for d in (today, tomorrow):
            editable.extend(await q.list_dayoff_plans_for_date(d))
        if not editable:
            return
        await message.answer(
            "✏️ <b>Filialni tanlab tahrirlang</b>\n"
            "Har bir xodim tugmasini bosib 🟢 <b>ishga keladi</b> ⇄ "
            "🔴 <b>kelmaydi</b> qilib belgilang.",
            reply_markup=kb.dayoff_plan_branch_pick_kb(editable),
        )


def _dayoff_summary_text(date_iso, branches_data, pending):
    total_off = sum(
        sum(1 for it in b["items"] if it.get("day_status") == "off")
        for b in branches_data
    )
    lines = [
        "🛌 <b>Kunlik dam olish hisoboti</b>",
        f"📆 Sana: <b>{iso_to_display(date_iso)}</b>",
        "━━━━━━━━━━━━",
        f"🏢 Filiallar: <b>{len(branches_data)}</b>",
        f"👤 Bugun dam oladi (kelmaydi): <b>{total_off}</b> nafar",
    ]
    for b in branches_data:
        off = [it for it in b["items"] if it.get("day_status") == "off"]
        lines.append(f"  • {b['branch_name']}: {len(off)} nafar")
    if pending:
        lines.append(
            f"\n⏳ Hali tasdiqlanmagan filiallar: <b>{len(pending)}</b> "
            f"({', '.join(p.get('branch_name') or '-' for p in pending[:10])})"
        )
    return "\n".join(lines)


async def send_dayoff_report(bot: Bot, target_tg_ids, date_iso, note_empty=False):
    """Berilgan sana bo'yicha tasdiqlangan dam olish rejalarini Excel bilan yuboradi."""
    confirmed = await q.list_dayoff_plans_for_date(date_iso, status="confirmed")
    pending = await q.list_dayoff_plans_for_date(date_iso, status="pending")
    branches_data = []
    # Rasmiy Excelga faqat rahbar/HR tasdiqlagan rejalar kiradi. Pending filiallar
    # captionda aniq ko'rsatiladi, lekin tasdiqlangandek hisobotga aralashtirilmaydi.
    for plan in confirmed:
        items = await q.list_dayoff_plan_items(plan["id"])
        name = plan.get("branch_name") or "Filialsiz"
        enriched = []
        for it in items:
            item = dict(it)
            item["scheduled_status"] = expected_day_status(
                item.get("rest_day"), plan.get("weekday")
            )
            item["is_override"] = item.get("day_status") != item["scheduled_status"]
            enriched.append(item)
        branches_data.append({
            "branch_name": name,
            "weekday": plan.get("weekday"),
            "items": enriched,
        })
    if not branches_data:
        sent = 0
        for tid in target_tg_ids:
            from utils import safe_send
            if await safe_send(
                bot, tid,
                f"🛌 <b>{iso_to_display(date_iso)}</b> uchun tasdiqlangan dam olish "
                "rejasi yo'q.\n"
                + (f"⏳ Tasdiq kutilayotgan: {len(pending)} filial." if pending else ""),
            ):
                sent += 1
        return sent
    summary = _dayoff_summary_text(date_iso, branches_data, pending)
    xlsx = export.build_dayoff_xlsx(branches_data, iso_to_display(date_iso))
    sent = 0
    for tid in target_tg_ids:
        try:
            await bot.send_document(tid, xlsx, caption=summary)
            sent += 1
        except Exception:
            from utils import safe_send
            if await safe_send(bot, tid, summary):
                sent += 1
    return sent
