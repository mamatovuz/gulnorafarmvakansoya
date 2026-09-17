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


def weekday_uz(dt):
    return WEEKDAY_UZ[dt.weekday()]


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
        for i, it in enumerate(items, start=1):
            dot = "🟢" if it.get("day_status") == "work" else "🔴"
            header += f"{i}. {dot} {it.get('full_name') or '-'} — {it.get('position') or '-'}\n"
    else:
        header += "Bu filialda xodim yo'q.\n"
    off_n = sum(1 for it in items if it.get("day_status") == "off")
    work_n = len(items) - off_n
    header += (
        f"\n🟢 Ishga keladi: <b>{work_n}</b> · 🔴 Kelmaydi: <b>{off_n}</b> "
        f"({len(items)} nafar)\n"
        "\n👇 Kimningdir holati noto'g'ri bo'lsa — <b>ustiga bosing</b> (🟢⇄🔴). "
        "Hammasi to'g'ri bo'lsa <b>✅ Tasdiqlash</b>ni bosing."
    )
    return header


async def _report_already_sent(plan):
    """Rejani tahrirlab bo'lmaydigan holat: 08:30 HR hisoboti shu sana uchun
    yuborilgan, YOKI rejaning kuni allaqachon o'tган (eski xabar bosilgan)."""
    date_iso = plan.get("plan_date")
    if not date_iso:
        return False
    today = now_tk().strftime("%Y-%m-%d")
    if date_iso < today:
        # Kuni o'tган reja — endi tahrirlanmaydi (odatda eski so'rov xabari bosiladi)
        return True
    flag = await q.get_setting(f"dayoff_report_sent:{date_iso}", "0")
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
        # HR istalgan filial rejasini tahrirlashi mumkin — vaqt cheklovi yo'q.
        # Blok faqat hisobot yuborilгач (_report_already_sent) qo'yiladi.
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
    if await _report_already_sent(plan):
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
    if await _report_already_sent(plan):
        await call.answer(_locked_alert(plan), show_alert=True)
        return
    new_status = await q.toggle_dayoff_plan_item(item_id)
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
    if await _report_already_sent(plan):
        await call.answer(_locked_alert(plan), show_alert=True)
        return
    await q.set_dayoff_plan_status(plan_id, "confirmed", confirmed_by=user["id"])
    # Boshqa (eski so'rov/eslatma) xabarlardagi tugmalarni tozalaymiz — joriy
    # xabar summary ga aylantiriladi.
    await _clear_plan_notices(bot, plan_id,
                              keep_chat_id=call.from_user.id,
                              keep_msg_id=call.message.message_id)
    await q.add_log(call.from_user.id, user.get("full_name"),
                    "dam_olish_reja_tasdiq", f"plan#{plan_id}")
    items = await q.list_dayoff_plan_items(plan_id)
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
        lines.append(f"  🔴 {it.get('full_name')}")
    lines.append("\n✏️ Xato bo'lsa — hisobotgacha tahrirlashingiz mumkin.")
    edit_kb = kb.dayoff_plan_edit_again_kb(plan_id)
    try:
        await call.message.edit_text("\n".join(lines), reply_markup=edit_kb)
    except Exception:
        await call.message.answer("\n".join(lines), reply_markup=edit_kb)
    await call.answer("Tasdiqlandi ✅")


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
            if str(await q.get_setting(f"dayoff_report_sent:{d}", "0")) == "1":
                continue  # bu kun hisoboti ketgan — tahrirlanmaydi
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
    # Tasdiqlangan + tasdiqlanmagan rejalarni ham qo'shamiz — rahbar tasdiqlamay
    # qolsa ham o'sha filial xodimlari hisobotdan tushib qolmasligi uchun
    # (tasdiqlanmaganlari «⏳» bilan alohida belgilanadi).
    for plan in [*confirmed, *pending]:
        items = await q.list_dayoff_plan_items(plan["id"])
        name = plan.get("branch_name") or "Filialsiz"
        if plan.get("status") != "confirmed":
            name += " ⏳ (tasdiqlanmagan)"
        branches_data.append({
            "branch_name": name,
            "items": items,
        })
    if not branches_data:
        if note_empty:
            for tid in target_tg_ids:
                from utils import safe_send
                await safe_send(
                    bot, tid,
                    f"🛌 <b>{iso_to_display(date_iso)}</b> uchun tasdiqlangan dam olish "
                    "rejasi yo'q.\n"
                    + (f"⏳ Tasdiq kutilayotgan: {len(pending)} filial." if pending else ""),
                )
        return
    summary = _dayoff_summary_text(date_iso, branches_data, pending)
    xlsx = export.build_dayoff_xlsx(branches_data, iso_to_display(date_iso))
    for tid in target_tg_ids:
        try:
            await bot.send_document(tid, xlsx, caption=summary)
        except Exception:
            from utils import safe_send
            await safe_send(bot, tid, summary)
