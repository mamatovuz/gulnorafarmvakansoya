"""Gulnora Farm mavjud xodimi — o'zini ro'yxatdan o'tkazadi (self-registratsiya).

/start dagi «🏢 Gulnora Farm hodimi» tugmasi orqali kiriladi. Xodim ma'lumotlarini
kiritadi, so'ng ariza HR/Adminga tasdiq uchun yuboriladi. Tasdiqlangach xodimga
tegishli rol va davomat paneli ochiladi.
"""
from datetime import datetime

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter

from database import queries as q
from database.db import (
    ROLE_HR, ROLE_ADMIN, ROLE_MANAGER, ROLE_DIRECTOR, ROLE_PHARMACIST,
    ROLE_EMPLOYEE,
)
from states import StaffReg
import keyboards as kb
from utils import safe_send, staff_reg_text, uniform_label, now_tk

router = Router()

ROLE_LABELS = {
    ROLE_MANAGER: "🏢 Filial rahbari",
    ROLE_PHARMACIST: "💊 Farmatsevt",
    ROLE_DIRECTOR: "👔 Direktor",
    ROLE_EMPLOYEE: "👷 Xodim",
}


async def _is_staff(tg_id):
    u = await q.get_user(tg_id)
    return u and u["role"] in (ROLE_HR, ROLE_ADMIN)


# ---------------- Yordamchilar ----------------
def parse_birthdate(text):
    text = (text or "").strip()
    try:
        dt = datetime.strptime(text, "%d.%m.%Y")
    except ValueError:
        return None
    if not (1940 <= dt.year <= now_tk().year):
        return None
    return dt.strftime("%d.%m.%Y")


def resolve_branch(text, branches):
    clean = (text or "").replace("📍", "").strip()
    for br in branches:
        if br["name"].lower() == clean.lower():
            return br["name"], br["id"]
    return clean, None


def uniform_status_from_text(text):
    lower = (text or "").lower()
    if "yo'q" in lower or "yoq" in lower or "kerak" in lower:
        return "no"
    if "ha" in lower or "bor" in lower:
        return "yes"
    return "unknown"


def _needs_since(role):
    return role in (ROLE_MANAGER, ROLE_DIRECTOR)


def _extra_prompt(role, position):
    if role == ROLE_MANAGER:
        return "🧩 Nechta xodimdan iborat jamoani boshqarasiz? (masalan: <i>8 xodim</i>)"
    if role == ROLE_DIRECTOR:
        return "🧩 Nechta filialni boshqarasiz / mas'uliyat doirangiz qanday?"
    return None


def _reg_summary(d):
    def g(k):
        return d.get(k) or "-"
    lines = [
        "📋 <b>Ma'lumotlaringizni tekshiring:</b>",
        "",
        f"👤 Ism-familiya: {g('full_name')}",
        f"📅 Tug'ilgan sana: {g('birth_date')}",
        f"📱 Telefon: {g('phone')}",
        f"💼 Yo'nalish: {g('position')}",
        f"📍 Manzil: {g('address')}",
        f"🏢 Filial: {g('branch_name')}",
        f"🕒 Ish vaqti: {g('work_hours')}",
        f"💰 Oylik: {g('salary')}",
        f"🛌 Dam olish kuni: {g('rest_day')}",
        f"👕 Forma: {uniform_label(d.get('uniform_status'))}",
    ]
    if d.get("since"):
        lines.append(f"⏳ Staj: {d['since']}")
    if d.get("extra_info"):
        lines.append(f"🧩 Qo'shimcha: {d['extra_info']}")
    lines.append(f"🖼 Rasm: {'✅ biriktirilgan' if d.get('photo_file_id') else '— yo`q'}")
    return "\n".join(lines)


# ---------------- KIRISH ----------------
@router.message(F.text == "🏢 Gulnora Farm hodimi")
async def staff_reg_start(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(StaffReg.full_name)
    await message.answer(
        "🏢 <b>Gulnora Farm hodimi sifatida ro'yxatdan o'tish</b>\n\n"
        "Assalomu alaykum! Agar siz allaqachon Gulnora Farmda ishlayotgan bo'lsangiz, "
        "quyidagi savollarga javob bering. Ma'lumotlaringiz HR bo'limiga tasdiqlash uchun "
        "yuboriladi.\n"
        "Istalgan payt «❌ Bekor qilish» tugmasi bilan to'xtatishingiz mumkin.\n\n"
        "<b>1-savol</b>\n👤 Ism-familiyangizni yozing.\nMisol: <i>Ravshanova Robiya</i>",
        reply_markup=kb.staff_photo_kb(),  # faqat Bekor qilish tugmasi
    )


# ---------------- BEKOR QILISH ----------------
@router.message(StateFilter(
    StaffReg.full_name, StaffReg.birth_date, StaffReg.phone, StaffReg.role,
    StaffReg.address, StaffReg.branch, StaffReg.shift, StaffReg.work_hours,
    StaffReg.salary, StaffReg.rest_day, StaffReg.uniform, StaffReg.since,
    StaffReg.extra, StaffReg.photo,
), F.text == kb.CANCEL_BTN)
async def staff_reg_cancel(message: Message, state: FSMContext):
    await state.clear()
    user = await q.get_user(message.from_user.id)
    await message.answer(
        "❌ Ro'yxatdan o'tish bekor qilindi.",
        reply_markup=kb.main_menu(user["role"] if user else "candidate"),
    )


# 1) Ism-familiya
@router.message(StaffReg.full_name, F.text)
async def sr_name(message: Message, state: FSMContext):
    await state.update_data(full_name=message.text.strip())
    await state.set_state(StaffReg.birth_date)
    await message.answer(
        "<b>2-savol</b>\n📅 Tug'ilgan sanangizni kiriting.\n"
        "Format: <b>kun.oy.yil</b>\nMisol: <i>29.08.1995</i>",
        reply_markup=kb.staff_photo_kb(),
    )


# 2) Tug'ilgan sana
@router.message(StaffReg.birth_date, F.text)
async def sr_birth(message: Message, state: FSMContext):
    norm = parse_birthdate(message.text)
    if not norm:
        await message.answer(
            "❗️ Sana noto'g'ri. <b>kun.oy.yil</b> ko'rinishida kiriting. Misol: <i>29.08.1995</i>",
            reply_markup=kb.staff_photo_kb(),
        )
        return
    await state.update_data(birth_date=norm)
    await state.set_state(StaffReg.phone)
    await message.answer(
        "<b>3-savol</b>\n📱 Telefon raqamingizni <b>qo'lda yozing</b>.\n"
        "Misol: <code>+998932303410</code>",
        reply_markup=kb.staff_photo_kb(),
    )


# 3) Telefon raqam (qo'lda yoziladi)
@router.message(StaffReg.phone, F.text)
async def sr_phone(message: Message, state: FSMContext):
    text = message.text.strip()
    digits = "".join(c for c in text if c.isdigit())
    if len(digits) < 9:
        await message.answer(
            "❗️ Telefon raqam noto'g'ri. To'liq raqamni yozing.\n"
            "Misol: <code>+998932303410</code>",
            reply_markup=kb.staff_photo_kb(),
        )
        return
    await state.update_data(phone=text)
    await state.set_state(StaffReg.role)
    names = await q.list_position_names()
    await message.answer(
        "<b>4-savol</b>\n💼 Qaysi yo'nalishda ishlaysiz? Tanlang:",
        reply_markup=kb.staff_role_kb(names),
    )


# 4) Rol / yo'nalish
@router.message(StaffReg.role, F.text)
async def sr_role(message: Message, state: FSMContext):
    names = await q.list_position_names()
    mapping = {label: (role, pos) for label, role, pos in kb.staff_role_options(names)}
    got = mapping.get(message.text.strip())
    if not got:
        await message.answer(
            "❗️ Iltimos, quyidagi tugmalardan birini tanlang:",
            reply_markup=kb.staff_role_kb(names),
        )
        return
    role, position = got
    await state.update_data(role=role, position=position)
    await state.set_state(StaffReg.address)
    await message.answer(
        "<b>5-savol</b>\n🏠 Yashash manzilingizni yozing.\n"
        "Misol: <i>Chilonzor tumani, 12-kvartal</i>",
        reply_markup=kb.staff_photo_kb(),
    )


# 4) Manzil
@router.message(StaffReg.address, F.text)
async def sr_address(message: Message, state: FSMContext):
    await state.update_data(address=message.text.strip())
    branches = await q.list_branches()
    await state.set_state(StaffReg.branch)
    if branches:
        await message.answer(
            "<b>6-savol</b>\n🏢 Qaysi filialda ishlaysiz? Tanlang:",
            reply_markup=kb.apply_branch_kb(branches),
        )
    else:
        await message.answer(
            "<b>6-savol</b>\n🏢 Qaysi filialda ishlaysiz? Filial nomini yozing:",
            reply_markup=kb.staff_photo_kb(),
        )


# 5) Filial
@router.message(StaffReg.branch, F.text)
async def sr_branch(message: Message, state: FSMContext):
    branches = await q.list_branches()
    name, bid = resolve_branch(message.text, branches)
    await state.update_data(branch_name=name, branch_id=bid)
    await state.set_state(StaffReg.shift)
    await message.answer(
        "<b>7-savol</b>\n🔀 Qaysi smenada ishlaysiz? Tanlang:\n\n"
        f"{kb.STAFF_SHIFT_DAY} — odatda 08:00 - 17:00\n"
        f"{kb.STAFF_SHIFT_NIGHT} — odatda 14:00 - 00:00\n"
        f"{kb.STAFF_SHIFT_DOUBLE} — ikkala smena",
        reply_markup=kb.staff_shift_kb(),
    )


# 6) Smena
@router.message(StaffReg.shift, F.text)
async def sr_shift(message: Message, state: FSMContext):
    text = message.text.strip()
    valid = (kb.STAFF_SHIFT_DAY, kb.STAFF_SHIFT_NIGHT, kb.STAFF_SHIFT_DOUBLE)
    if text not in valid:
        await message.answer(
            "❗️ Iltimos, quyidagi tugmalardan birini tanlang:",
            reply_markup=kb.staff_shift_kb(),
        )
        return
    await state.update_data(shift=text)
    await state.set_state(StaffReg.work_hours)
    await message.answer(
        "<b>8-savol</b>\n🕒 Ish vaqtingiz nechidan nechigacha? Tayyor variantni tanlang "
        "yoki «✏️ Boshqa vaqt (custom)» orqali o'zingiz yozing (masalan <i>09:00 - 18:00</i>):",
        reply_markup=kb.staff_work_hours_kb(text),
    )


# 7) Ish vaqti
@router.message(StaffReg.work_hours, F.text)
async def sr_hours(message: Message, state: FSMContext):
    text = message.text.strip()
    data = await state.get_data()
    shift = data.get("shift")
    # «Boshqa vaqt» tugmasi bosilsa — foydalanuvchidan qo'lda yozishni so'raymiz
    if text == kb.STAFF_HOURS_CUSTOM:
        await message.answer(
            "✏️ Ish vaqtingizni <b>qo'lda yozing</b>.\nMisol: <i>09:00 - 18:00</i>",
            reply_markup=kb.staff_photo_kb(),
        )
        return
    hours = (text.replace("🕘", "").replace("🕗", "").replace("🕙", "")
             .replace("🕑", "").replace("🔄", "").strip())
    # Smena nomini ish vaqti bilan birga saqlaymiz (davomat vaqt regexiga ta'sir qilmaydi)
    shift_prefix = f"{shift} · " if shift else ""
    await state.update_data(work_hours=f"{shift_prefix}{hours}")
    await state.set_state(StaffReg.salary)
    await message.answer(
        "<b>9-savol</b>\n💰 Oyligingiz qancha?\nMisol: <i>4 000 000 so'm</i>",
        reply_markup=kb.staff_photo_kb(),
    )


# 7) Oylik
@router.message(StaffReg.salary, F.text)
async def sr_salary(message: Message, state: FSMContext):
    await state.update_data(salary=message.text.strip())
    await state.set_state(StaffReg.rest_day)
    await message.answer(
        "<b>10-savol</b>\n🛌 Haftaning qaysi kuni dam olasiz? Tanlang:",
        reply_markup=kb.staff_rest_day_kb(),
    )


# 8) Dam olish kuni
@router.message(StaffReg.rest_day, F.text)
async def sr_rest(message: Message, state: FSMContext):
    await state.update_data(rest_day=message.text.strip())
    await state.set_state(StaffReg.uniform)
    await message.answer(
        "<b>11-savol</b>\n👕 Ish formangiz bormi?",
        reply_markup=kb.apply_uniform_kb(),
    )


# 9) Forma
@router.message(StaffReg.uniform, F.text)
async def sr_uniform(message: Message, state: FSMContext):
    await state.update_data(uniform_status=uniform_status_from_text(message.text))
    data = await state.get_data()
    if _needs_since(data.get("role")):
        await state.set_state(StaffReg.since)
        role_word = "filial rahbari" if data.get("role") == ROLE_MANAGER else "direktor"
        await message.answer(
            f"<b>12-savol</b>\n⏳ Qachondan beri {role_word}siz?",
            reply_markup=kb.staff_since_kb(),
        )
    else:
        await _ask_photo(message, state)


# 10) Staj (faqat rahbar/direktor)
@router.message(StaffReg.since, F.text)
async def sr_since(message: Message, state: FSMContext):
    await state.update_data(since=message.text.replace("🟡", "").replace("🟠", "")
                            .replace("🟢", "").replace("🔵", "").strip())
    data = await state.get_data()
    prompt = _extra_prompt(data.get("role"), data.get("position"))
    if prompt:
        await state.set_state(StaffReg.extra)
        await message.answer("<b>13-savol</b>\n" + prompt, reply_markup=kb.staff_photo_kb())
    else:
        await _ask_photo(message, state)


# 11) Rolga oid qo'shimcha
@router.message(StaffReg.extra, F.text)
async def sr_extra(message: Message, state: FSMContext):
    await state.update_data(extra_info=message.text.strip())
    await _ask_photo(message, state)


async def _ask_photo(message: Message, state: FSMContext):
    await state.set_state(StaffReg.photo)
    await message.answer(
        "📸 <b>Oxirgi savol</b>\nOxirgi 10 kun ichida olingan rasmingizni yuboring "
        "(shaxsingiz aniq ko'rinadigan surat).",
        reply_markup=kb.staff_photo_kb(),
    )


# Rasm
@router.message(StaffReg.photo, F.photo)
async def sr_photo(message: Message, state: FSMContext):
    await state.update_data(photo_file_id=message.photo[-1].file_id)
    await _show_confirm(message, state)


@router.message(StaffReg.photo, F.text)
async def sr_photo_missing(message: Message):
    await message.answer(
        "❗️ Iltimos, rasm (surat) yuboring — matn emas. "
        "Oxirgi 10 kun ichidagi suratingizni yuboring.",
        reply_markup=kb.staff_photo_kb(),
    )


async def _show_confirm(message: Message, state: FSMContext):
    data = await state.get_data()
    await state.set_state(StaffReg.confirm)
    user = await q.get_user(message.from_user.id)
    await message.answer(
        "✅ Ma'lumotlar to'plandi.",
        reply_markup=kb.main_menu(user["role"] if user else "candidate"),
    )
    # Rasmni ko'rsatib, tagida tasdiqlash tugmalari
    await message.answer_photo(
        data.get("photo_file_id"),
        caption=_reg_summary(data),
        reply_markup=kb.staff_confirm_kb(),
    )


# ---------------- TASDIQLASH / BEKOR ----------------
@router.callback_query(F.data == "sreg_cancel")
async def sr_confirm_cancel(call: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await call.message.answer("❌ Ariza bekor qilindi.")
    await call.answer()


@router.callback_query(F.data == "sreg_confirm")
async def sr_confirm(call: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    if not data.get("full_name"):
        await call.answer(
            "⏳ Sessiya tugagan. «🏢 Gulnora Farm hodimi» orqali qaytadan boshlang.",
            show_alert=True,
        )
        await state.clear()
        return
    user = await q.get_user(call.from_user.id)
    reg = {
        "user_id": user["id"],
        "full_name": data.get("full_name"),
        "birth_date": data.get("birth_date"),
        "phone": data.get("phone"),
        "role": data.get("role"),
        "position": data.get("position"),
        "address": data.get("address"),
        "branch_id": data.get("branch_id"),
        "branch_name": data.get("branch_name"),
        "work_hours": data.get("work_hours"),
        "salary": data.get("salary"),
        "rest_day": data.get("rest_day"),
        "uniform_status": data.get("uniform_status") or "unknown",
        "photo_file_id": data.get("photo_file_id"),
        "since": data.get("since"),
        "extra_info": data.get("extra_info"),
    }
    rid = await q.add_staff_reg(reg)
    # Foydalanuvchi telefon raqamini ham yangilab qo'yamiz
    if data.get("phone"):
        await q.update_phone(call.from_user.id, data["phone"])
    await state.clear()
    await q.add_log(
        call.from_user.id, call.from_user.full_name,
        "hodim_arizasi", f"Xodim so'rovi #{rid} — {data.get('position')}"
    )
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await call.message.answer(
        f"✅ <b>So'rovingiz HR bo'limiga yuborildi!</b>\n\n"
        f"So'rov raqami: #{rid}\n\n"
        "HR bo'limi ma'lumotlaringizni tekshirib, tasdiqlaydi. Tasdiqlangach sizga "
        "«📍 Ishga keldim» davomat paneli ochiladi."
    )
    await call.answer("Yuborildi ✅")

    # HR va Adminlarga yuborish
    full = await q.get_staff_reg(rid)
    hr_ids = await q.all_user_tg_ids(role=ROLE_HR)
    admin_ids = await q.all_user_tg_ids(role=ROLE_ADMIN)
    header = "🔔 <b>Yangi xodim so'rovi (Gulnora Farm hodimi)!</b>\n\n"
    for tid in set(hr_ids + admin_ids):
        if full.get("photo_file_id"):
            try:
                await bot.send_photo(
                    tid, full["photo_file_id"],
                    caption=header + staff_reg_text(full),
                    reply_markup=kb.staff_reg_actions_kb(rid),
                )
                continue
            except Exception:
                pass
        await safe_send(
            bot, tid, header + staff_reg_text(full),
            reply_markup=kb.staff_reg_actions_kb(rid),
        )


# ================= HR / ADMIN: TASDIQLASH =================
@router.message(F.text == "🧾 Xodim so'rovlari")
async def hr_staff_regs(message: Message):
    if not await _is_staff(message.from_user.id):
        await message.answer("⛔ Sizda ruxsat yo'q.")
        return
    regs = await q.list_staff_regs(status="new", limit=30)
    if not regs:
        await message.answer("🧾 Yangi xodim so'rovlari yo'q.")
        return
    await message.answer(
        f"🧾 <b>Yangi xodim so'rovlari</b>\n\nJami: <b>{len(regs)}</b> ta\n"
        "Batafsil ko'rish uchun tanlang:",
        reply_markup=kb.staff_regs_list_kb(regs),
    )


@router.callback_query(F.data.startswith("srview:"))
async def sr_view(call: CallbackQuery, bot: Bot):
    if not await _is_staff(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    rid = int(call.data.split(":")[1])
    reg = await q.get_staff_reg(rid)
    if not reg:
        await call.answer("So'rov topilmadi.", show_alert=True)
        return
    markup = kb.staff_reg_actions_kb(rid) if reg.get("status") == "new" else None
    if reg.get("photo_file_id"):
        try:
            await call.message.answer_photo(
                reg["photo_file_id"], caption=staff_reg_text(reg), reply_markup=markup
            )
            await call.answer()
            return
        except Exception:
            pass
    await call.message.answer(staff_reg_text(reg), reply_markup=markup)
    await call.answer()


@router.callback_query(F.data.startswith("sracc:"))
async def sr_approve(call: CallbackQuery, bot: Bot):
    if not await _is_staff(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    rid = int(call.data.split(":")[1])
    reg = await q.get_staff_reg(rid)
    if not reg:
        await call.answer("So'rov topilmadi.", show_alert=True)
        return
    if reg.get("status") != "new":
        await call.answer("Bu so'rov allaqachon ko'rib chiqilgan.", show_alert=True)
        return
    me = await q.get_user(call.from_user.id)
    role = reg.get("role") or ROLE_EMPLOYEE
    # ATOMIK — bir marta tasdiqlanadi
    if not await q.claim_request("staff_regs", rid, "approved", me["id"], "new"):
        try:
            await call.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        await call.answer("Bu so'rov allaqachon boshqa xodim tomonidan ko'rib chiqilgan.",
                          show_alert=True)
        return
    await q.set_role(reg["user_tg"], role, reg.get("branch_id"))
    await q.upsert_employee_profile(
        user_id=reg["user_id"],
        application_id=None,
        role=role,
        position=reg.get("position"),
        branch_id=reg.get("branch_id"),
        uniform_status=reg.get("uniform_status") or "unknown",
        monthly_salary=reg.get("salary"),
        birth_date=reg.get("birth_date"),
        address=reg.get("address"),
        work_hours=reg.get("work_hours"),
        rest_day=reg.get("rest_day"),
        photo_file_id=reg.get("photo_file_id"),
        extra_info=reg.get("extra_info"),
        since=reg.get("since"),
    )
    await q.add_log(call.from_user.id, me["full_name"], "hodim_tasdiqlandi", f"#{rid}")
    # Kadrlar harakati (IT hisoboti): ishga kirdi
    await q.add_hr_event(
        "hired", user_id=reg["user_id"], full_name=reg.get("full_name"),
        branch_id=reg.get("branch_id"), details=f"hodim ro'yxati #{rid}",
        created_by=me["id"],
    )
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await call.message.answer(
        f"✅ Xodim so'rovi #{rid} tasdiqlandi.\n"
        f"👤 {reg.get('full_name')} — {ROLE_LABELS.get(role, role)}"
    )
    await call.answer("Tasdiqlandi ✅")
    await safe_send(
        bot, reg["user_tg"],
        "🎉 <b>Tabriklaymiz!</b>\n\n"
        "Siz <b>Gulnora Farm hodimi</b> sifatida tasdiqlandingiz.\n"
        f"Sizga <b>{ROLE_LABELS.get(role, role)}</b> paneli va «📍 Ishga keldim» "
        "davomat tugmasi ochildi.\n"
        "Yangilangan menyuni ko'rish uchun /start bosing.",
        reply_markup=kb.main_menu(role),
    )


@router.callback_query(F.data.startswith("srrej:"))
async def sr_reject(call: CallbackQuery, bot: Bot):
    if not await _is_staff(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    rid = int(call.data.split(":")[1])
    reg = await q.get_staff_reg(rid)
    if not reg:
        await call.answer("So'rov topilmadi.", show_alert=True)
        return
    if reg.get("status") != "new":
        await call.answer("Bu so'rov allaqachon ko'rib chiqilgan.", show_alert=True)
        return
    me = await q.get_user(call.from_user.id)
    await q.set_staff_reg_status(rid, "rejected", handled_by=me["id"])
    await q.add_log(call.from_user.id, me["full_name"], "hodim_rad", f"#{rid}")
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await call.message.answer(f"❌ Xodim so'rovi #{rid} rad etildi.")
    await call.answer("Rad etildi")
    await safe_send(
        bot, reg["user_tg"],
        "😔 Gulnora Farm hodimi sifatida yuborgan so'rovingiz tasdiqlanmadi.\n"
        "Savollar bo'lsa HR bo'limi bilan bog'laning.",
    )
