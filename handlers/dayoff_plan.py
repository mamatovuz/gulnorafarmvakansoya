"""Kunlik dam olish rejasi.

Har kuni 17:00 da filial rahbariga «ertaga kim dam oladi» so'rovi boradi.
Rahbar tasdiqlaydi yoki tahrirlaydi (har bir xodimni «dam oladi ⇄ keladi» qilib
belgilaydi). Tasdiqlangach reja HR ga to'planadi va 08:30 da chiroyli Excel
hisobot bo'lib yuboriladi.
"""
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


def plan_prompt_text(plan, off_items):
    header = (
        "🛌 <b>Ertangi dam olishni tasdiqlang</b>\n"
        "━━━━━━━━━━━━\n"
        f"📆 Sana: <b>{iso_to_display(plan.get('plan_date'))}</b> ({plan.get('weekday')})\n"
        f"🏢 Filial: <b>{plan.get('branch_name') or '-'}</b>\n\n"
    )
    if off_items:
        header += "Ertaga quyidagi xodimlar <b>dam oladi</b>:\n"
        for i, it in enumerate(off_items, start=1):
            header += f"{i}. {it.get('full_name') or '-'} — {it.get('position') or '-'}\n"
    else:
        header += "Ertaga dam oluvchi xodim yo'q.\n"
    header += (
        "\nHammasi to'g'rimi? <b>Tasdiqlash</b>ni bosing. Kimdir aslida "
        "<b>ishga keladi</b> bo'lsa — <b>Tahrirlash</b>dan uni belgilang."
    )
    return header


async def _can_manage(user, plan):
    if not user:
        return False
    if user["role"] in (ROLE_ADMIN, ROLE_HR):
        return True
    if user["role"] == ROLE_MANAGER:
        # Rahbar o'z filiali rejasini boshqaradi
        branch_id = user.get("branch_id")
        if not branch_id:
            profile = await q.get_employee_profile(user["id"])
            branch_id = profile.get("branch_id") if profile else None
        return plan.get("branch_id") == branch_id or branch_id is None
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
    if plan.get("status") == "confirmed":
        await call.answer("Bu reja allaqachon tasdiqlangan.", show_alert=True)
        return
    items = await q.list_dayoff_plan_items(plan_id)
    if not items:
        await call.answer("Bu rejada xodim yo'q.", show_alert=True)
        return
    try:
        await call.message.edit_text(
            "✏️ <b>Tahrirlash</b>\n\n"
            "Har bir xodim tugmasini bosib holatini almashtiring:\n"
            "🛌 <b>dam oladi</b> ⇄ ✅ <b>keladi</b>\n\n"
            "Tugatgach «✅ Tasdiqlash» ni bosing.",
            reply_markup=kb.dayoff_plan_edit_kb(plan_id, items),
        )
    except Exception:
        await call.message.answer(
            "✏️ Har bir xodim holatini almashtiring, so'ng «✅ Tasdiqlash»:",
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
    if plan.get("status") == "confirmed":
        await call.answer("Reja tasdiqlangan, o'zgartirib bo'lmaydi.", show_alert=True)
        return
    new_status = await q.toggle_dayoff_plan_item(item_id)
    items = await q.list_dayoff_plan_items(item["plan_id"])
    try:
        await call.message.edit_reply_markup(
            reply_markup=kb.dayoff_plan_edit_kb(item["plan_id"], items)
        )
    except Exception:
        pass
    await call.answer("✅ keladi" if new_status == "work" else "🛌 dam oladi")


@router.callback_query(F.data.startswith("dopl_ok:"))
async def dayoff_plan_confirm(call: CallbackQuery):
    user = await q.get_user(call.from_user.id)
    plan_id = int(call.data.split(":")[1])
    plan = await q.get_dayoff_plan(plan_id)
    if not plan:
        await call.answer("Reja topilmadi.", show_alert=True)
        return
    if not await _can_manage(user, plan):
        await call.answer("⛔", show_alert=True)
        return
    if plan.get("status") == "confirmed":
        await call.answer("Allaqachon tasdiqlangan.", show_alert=True)
        return
    await q.set_dayoff_plan_status(plan_id, "confirmed", confirmed_by=user["id"])
    await q.add_log(call.from_user.id, user.get("full_name"),
                    "dam_olish_reja_tasdiq", f"plan#{plan_id}")
    items = await q.list_dayoff_plan_items(plan_id)
    off = [it for it in items if it.get("day_status") == "off"]
    lines = [
        "✅ <b>Tasdiqlandi. Rahmat!</b>",
        f"📆 {iso_to_display(plan.get('plan_date'))} ({plan.get('weekday')})",
        f"🏢 {plan.get('branch_name') or '-'}",
        f"🛌 Dam oladi: <b>{len(off)}</b> nafar",
    ]
    for it in off:
        lines.append(f"  • {it.get('full_name')}")
    try:
        await call.message.edit_text("\n".join(lines), reply_markup=None)
    except Exception:
        await call.message.answer("\n".join(lines))
    await call.answer("Tasdiqlandi ✅")


# ---------------- HR: KUNLIK DAM OLISH HISOBOTI (on-demand) ----------------
@router.message(F.text == "🛌 Kunlik dam olish")
async def hr_dayoff_report(message: Message, bot: Bot):
    user = await q.get_user(message.from_user.id)
    if not user or user["role"] not in (ROLE_HR, ROLE_ADMIN, ROLE_DIRECTOR):
        await message.answer("⛔ Ruxsat yo'q.")
        return
    today = now_tk().strftime("%Y-%m-%d")
    await send_dayoff_report(bot, [message.from_user.id], today, note_empty=True)


def _dayoff_summary_text(date_iso, branches_data, pending):
    total_off = sum(
        sum(1 for it in b["items"] if it.get("day_status") == "off")
        for b in branches_data
    )
    lines = [
        "🛌 <b>Kunlik dam olish hisoboti</b>",
        f"📆 Sana: <b>{iso_to_display(date_iso)}</b>",
        "━━━━━━━━━━━━",
        f"🏢 Tasdiqlangan filiallar: <b>{len(branches_data)}</b>",
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
    for plan in confirmed:
        items = await q.list_dayoff_plan_items(plan["id"])
        branches_data.append({
            "branch_name": plan.get("branch_name") or "Filialsiz",
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
