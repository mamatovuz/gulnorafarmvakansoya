"""Yordamchi funksiyalar: obuna tekshirish, matn formatlash."""
import re
from math import radians, sin, cos, asin, sqrt
from difflib import SequenceMatcher
from datetime import datetime, timedelta, date

from aiogram import Bot
from database import queries as q
from database.db import STATUS_LABELS


# O'zbekiston vaqti — UTC+5, yozgi/qishki almashuvsiz (doimiy).
TASHKENT_OFFSET = timedelta(hours=5)


def now_tk():
    """Hozirgi Toshkent vaqti (naive datetime). Server vaqt mintaqasiga bog'liq emas."""
    return datetime.utcnow() + TASHKENT_OFFSET


def now_tk_hm():
    """Hozirgi Toshkent vaqti 'HH:MM' ko'rinishida."""
    return now_tk().strftime("%H:%M")


# ---------------- TELEFON RAQAM ----------------
# Majburiy format: +998 va 9 ta raqam, orada bo'sh joysiz, faqat BITTA raqam.
PHONE_RE = re.compile(r"^\+998\d{9}$")
PHONE_HINT = (
    "📱 Telefon raqamni <b>+998</b> bilan, bo'sh joysiz va bitta raqam qilib yozing.\n"
    "Misol: <code>+998932303410</code>"
)


def normalize_phone(text):
    """Qo'lda yozilgan raqamni tekshiradi (QAT'IY).

    Faqat `+998XXXXXXXXX` ko'rinishi — orada bo'sh joy yo'q, bitta raqam.
    To'g'ri bo'lsa o'zini, aks holda None qaytaradi."""
    t = (text or "").strip()
    return t if PHONE_RE.match(t) else None


def phone_from_contact(number):
    """Telegram contact raqamini `+998XXXXXXXXX` ko'rinishiga keltiradi.

    Contact raqamini foydalanuvchi yozmaydi — Telegram beradi, shuning uchun
    formatlashga yo'l qo'yiladi. O'zbek raqami bo'lmasa None."""
    digits = "".join(c for c in str(number or "") if c.isdigit())
    if len(digits) == 9:
        digits = "998" + digits
    if len(digits) == 12 and digits.startswith("998"):
        return "+" + digits
    return None


def fmt_duration(seconds):
    """Sekundlarni 'X soat Y daqiqa' ko'rinishiga o'giradi."""
    seconds = int(seconds or 0)
    h, m = seconds // 3600, (seconds % 3600) // 60
    if h and m:
        return f"{h} soat {m} daqiqa"
    if h:
        return f"{h} soat"
    return f"{m} daqiqa"


def haversine_m(lat1, lon1, lat2, lon2):
    """Ikki koordinata orasidagi masofani metrda qaytaradi."""
    if None in (lat1, lon1, lat2, lon2):
        return None
    r = 6371000  # Yer radiusi (metr)
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = (
        sin(dlat / 2) ** 2
        + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    )
    return int(2 * r * asin(sqrt(a)))


DEFAULT_WELCOME = (
    "🌿 <b>Assalomu alaykum!</b>\n\n"
    "Bu — <b>Gulnora Farm</b> botiga xush kelibsiz.\n"
    "Bu yerda siz bo'sh ish o'rniga <b>ariza topshirishingiz</b> yoki "
    "<b>Gulnora Farm hodimi</b> sifatida ro'yxatdan o'tishingiz mumkin.\n\n"
    "Quyidagi tugmalardan birini tanlang 👇"
)


# Admin «🔄 Ma'lumotlarni yangilash» ni ishga tushirganda xodimlarga boradigan xabar
PROFILE_UPDATE_NOTICE = (
    "🔄 <b>Ma'lumotlaringizni yangilang</b>\n\n"
    "Hurmatli xodim! Biz sizning ma'lumotlaringiz eskirganini sezib qoldik.\n"
    "Iltimos, ma'lumotlaringizni yangilang — savollarga boshidan javob berasiz, "
    "bu bir necha daqiqa vaqt oladi.\n\n"
    "⚠️ Ma'lumotlaringizni yangilamaguningizcha botning boshqa bo'limlaridan "
    "foydalana olmaysiz.\n\n"
    "Quyidagi «🔄 Yangilash» tugmasini bosing 👇"
)


async def get_welcome_text():
    text = await q.get_setting("welcome_text")
    return text if text else DEFAULT_WELCOME


async def check_subscription(bot: Bot, tg_id: int):
    """Foydalanuvchi barcha faol kanallarga obuna bo'lganmi?
    Obuna bo'lmagan kanallar ro'yxatini qaytaradi (bo'sh bo'lsa - hammasi ok)."""
    # Admin majburiy obunani o'chirib qo'ygan bo'lsa - tekshirmaymiz
    if (await q.get_setting("require_subscription", "1")) == "0":
        return []
    channels = await q.list_channels(active_only=True)
    if not channels:
        return []
    not_joined = []
    for ch in channels:
        try:
            member = await bot.get_chat_member(ch["chat_id"], tg_id)
            if member.status in ("left", "kicked"):
                not_joined.append(ch)
        except Exception:
            # Bot kanalda admin bo'lmasa yoki chat_id noto'g'ri bo'lsa - o'tkazib yuboramiz
            # (aks holda foydalanuvchi qamalib qoladi)
            continue
    return not_joined


def vacancy_text(v):
    parts = [f"💼 <b>{v['title']}</b>"]
    if v.get("branch_name"):
        parts.append(f"🏢 Filial: {v['branch_name']}")
    if v.get("job_type"):
        parts.append(f"📋 Ish turi: {v['job_type']}")
    if v.get("shift"):
        parts.append(f"🕐 Smena: {v['shift']}")
    if v.get("work_time"):
        parts.append(f"⏰ Ish vaqti: {v['work_time']}")
    if v.get("salary"):
        parts.append(f"💰 Oylik: {v['salary']}")
    if v.get("requirements"):
        parts.append(f"\n📌 <b>Talablar:</b>\n{v['requirements']}")
    if v.get("responsibilities"):
        parts.append(f"\n🎯 <b>Mas'uliyatlar:</b>\n{v['responsibilities']}")
    if v.get("conditions"):
        parts.append(f"\n🏷 <b>Ish sharoiti:</b>\n{v['conditions']}")
    status = "🟢 Faol" if v.get("is_active") else "🔴 Nofaol"
    parts.append(f"\nHolati: {status}")
    return "\n".join(parts)


def _v(a, key):
    return a.get(key) or "-"


def uniform_label(status):
    return {
        "yes": "✅ Bor",
        "no": "❌ Yo'q",
        "unknown": "➖ Noma'lum",
        None: "➖ Noma'lum",
    }.get(status, status or "➖ Noma'lum")


def computer_level_label(a):
    """Kompyuter savodxonligi. Eski arizalarda Word/Excel alohida yozilgan —
    ular ham ko'rinsin (yangi ustun bo'sh bo'lsa)."""
    level = a.get("computer_level")
    if level:
        return level
    old = [x for x in (a.get("word_level"), a.get("excel_level")) if x]
    return " · ".join(old) if old else "-"


def application_text(a, full=False):
    status = STATUS_LABELS.get(a["status"], a["status"])
    parts = [
        f"📄 <b>Ariza #{a['id']}</b>  |  {status}",
        "━━━━━━━━━━━━",
        f"👤 Ism: {_v(a, 'full_name')}",
        f"💼 Lavozim: {_v(a, 'vacancy_title')}",
        f"🏢 Filial: {_v(a, 'branch_name')}",
        f"📱 Telefon: {_v(a, 'phone')}",
    ]
    if full:
        parts += [
            "\n<b>Shaxsiy ma'lumotlar</b>",
            f"📅 Tug'ilgan sana: {_v(a, 'birth_date')}",
            f"🌆 Shahar/viloyat: {_v(a, 'city')}",
            f"📍 Tuman: {_v(a, 'district')}",
            f"📍 Manzil: {_v(a, 'address')}",
            "\n<b>Ish bo'yicha</b>",
            f"🧩 Lavozim savoli: {_v(a, 'position_extra')}",
            f"🕒 Smena: {_v(a, 'shift')}",
            f"🎓 Ma'lumoti: {_v(a, 'education')}",
            f"💼 Umumiy tajriba: {_v(a, 'exp_years')}",
            f"🏢 Oldingi ish joyida: {_v(a, 'prev_years')}",
            "\n<b>Qo'shimcha</b>",
            f"⚖️ Sudlanganligi: {_v(a, 'criminal')}",
            f"👨‍👩‍👧 Oilaviy holati: {_v(a, 'marital')}",
            f"👶 Farzandlari: {_v(a, 'children')}",
            f"💰 Oldingi maosh: {_v(a, 'prev_salary')}",
            f"💵 Kutilayotgan maosh: {_v(a, 'expected_salary')}",
            f"💻 Kompyuter savodxonligi: {computer_level_label(a)}",
            f"🌍 Tillar: {_v(a, 'languages')}",
            f"📅 Ishlash niyati: {_v(a, 'work_intent')}",
            f"✍️ Sababi: {_v(a, 'reason')}",
        ]
        if a.get("hr_comment"):
            parts.append(f"🗒 HR izohi: {a['hr_comment']}")
    parts.append(f"\n🗓 Yuborilgan: {_v(a, 'created_at')}")
    return "\n".join(parts)


def application_summary(d):
    """FSM data asosida yakuniy tasdiqlash matni."""
    def g(k):
        return d.get(k) or "-"
    return (
        "📋 <b>Arizangizni tekshiring:</b>\n\n"
        f"👤 Ism: {g('full_name')}\n"
        f"📅 Tug'ilgan sana: {g('birth_date')}\n"
        f"🌆 Shahar/viloyat: {g('city')}\n"
        f"📍 Tuman: {g('district')}\n"
        f"🏠 Aniq manzil: {g('address')}\n"
        f"🏢 Filial: {g('branch')}\n"
        f"💼 Lavozim: {g('position')}\n"
        f"🧩 Lavozim savoli: {g('position_extra')}\n"
        f"🕒 Smena: {g('shift')}\n"
        f"🎓 Ma'lumoti: {g('education')}\n"
        f"💼 Umumiy tajriba: {g('exp_years')}\n"
        f"🏢 Oldingi ish joyida: {g('prev_years')}\n"
        f"⚖️ Sudlanganligi: {g('criminal')}\n"
        f"👨‍👩‍👧 Oilaviy holati: {g('marital')}\n"
        f"👶 Farzandlari: {g('children')}\n"
        f"💰 Oldingi maosh: {g('prev_salary')}\n"
        f"💵 Kutilayotgan maosh: {g('expected_salary')}\n"
        f"💻 Kompyuter savodxonligi: {g('computer_level')}\n"
        f"🌍 Tillar: {g('languages')}\n"
        f"📅 Ishlash niyati: {g('work_intent')}\n"
        f"✍️ Sababi: {g('reason')}\n"
        f"📱 Telefon: {g('phone')}\n"
        f"📸 Rasm (oxirgi 10 kun): {'✅ biriktirilgan' if d.get('photo_file_id') else '— yo`q'}\n"
        f"📄 Rezyume: {'✅ biriktirilgan' if d.get('resume_file_id') else '— yo`q'}"
    )


def employee_profile_text(profile):
    parts = [
        f"👤 <b>{_v(profile, 'full_name')}</b>",
        "━━━━━━━━━━━━",
        f"💼 Lavozim: {_v(profile, 'position')}",
        f"🏢 Filial: {_v(profile, 'branch_name')}",
        f"📱 Telefon: {_v(profile, 'phone')}",
    ]
    if profile.get("birth_date"):
        parts.append(f"📅 Tug'ilgan sana: {profile['birth_date']}")
    if profile.get("address"):
        parts.append(f"📍 Manzil: {profile['address']}")
    if profile.get("work_hours"):
        parts.append(f"🕒 Ish vaqti: {profile['work_hours']}")
    if profile.get("rest_day"):
        parts.append(f"🛌 Dam olish kuni: {profile['rest_day']}")
    parts.append(f"👕 Forma: {uniform_label(profile.get('uniform_status'))}")
    if profile.get("education"):
        parts.append(f"🎓 Ma'lumoti: {profile['education']}")
    parts.append(f"💰 Oylik: {_v(profile, 'monthly_salary')}")
    if profile.get("since"):
        parts.append(f"⏳ Gulnora Farmda: {profile['since']}")
    if profile.get("extra_info"):
        parts.append(f"🧩 Qo'shimcha: {profile['extra_info']}")
    return "\n".join(parts)


def staff_reg_text(reg):
    """Gulnora Farm hodimi self-registratsiyasi matni (HR uchun)."""
    parts = [
        f"🧾 <b>Xodim so'rovi #{reg['id']}</b>  |  {reg.get('status') or '-'}",
        "━━━━━━━━━━━━",
        f"👤 Ism-familiya: {_v(reg, 'full_name')}",
        f"📅 Tug'ilgan sana: {_v(reg, 'birth_date')}",
        f"📱 Telefon: {_v(reg, 'phone')}",
        f"💼 Yo'nalish: {_v(reg, 'position')}",
        f"📍 Manzil: {_v(reg, 'address')}",
        f"🏢 Filial: {_v(reg, 'branch_name')}",
        f"🕒 Ish vaqti: {_v(reg, 'work_hours')}",
        f"💰 Oylik: {_v(reg, 'salary')}",
        f"🛌 Dam olish kuni: {_v(reg, 'rest_day')}",
        f"👕 Forma: {uniform_label(reg.get('uniform_status'))}",
        f"🎓 Ma'lumoti: {_v(reg, 'education')}",
    ]
    if reg.get("since"):
        parts.append(f"⏳ Gulnora Farmda: {reg['since']}")
    if reg.get("extra_info"):
        parts.append(f"🧩 Qo'shimcha: {reg['extra_info']}")
    if reg.get("reject_reason"):
        parts.append(f"✍️ Rad etish sababi: {reg['reject_reason']}")
    parts.append(f"\n🗓 Yuborilgan: {_v(reg, 'created_at')}")
    return "\n".join(parts)


def attendance_status_text(status, distance=None, radius=None):
    if status == "present":
        return "✅ Ofisda"
    return "❌ Ofisdan uzoqda"


def fine_text(fine):
    return (
        f"💸 <b>Jarima #{fine['id']}</b>\n"
        "━━━━━━━━━━━━\n"
        f"💰 Summa: {fine['amount']}\n"
        f"✍️ Sabab: {_v(fine, 'reason')}\n"
        f"🧑‍💼 Yozgan: {_v(fine, 'created_by_name')}\n"
        f"🕐 Sana: {_v(fine, 'created_at')}"
    )


def manager_request_text(req):
    is_vacancy = req.get("kind") == "vacancy"
    kind = "➕ Xodim kerak" if is_vacancy else "🔧 Texnik nosozlik"
    lines = [
        f"📨 <b>So'rov #{req['id']}</b>",
        "━━━━━━━━━━━━",
        kind,
        f"🏢 Filial: {_v(req, 'branch_name')}",
        f"👤 Rahbar: {_v(req, 'manager_name')}",
        f"📌 {'Yo`nalish' if is_vacancy else 'Mavzu'}: {_v(req, 'title')}",
    ]
    if is_vacancy:
        lines.append(f"👥 Kerakli soni: {_v(req, 'staff_count')}")
        if gender_label(req.get("gender")):
            lines.append(f"🚻 Kimlar kerak: {gender_label(req['gender'])}")
        if req.get("shift"):
            lines.append(f"🕒 Smena: {req['shift']}")
        if req.get("experience"):
            lines.append(f"📈 Tajriba: {req['experience']}")
    lines += [
        f"📝 Tafsilot: {_v(req, 'details')}",
        f"Holati: {_v(req, 'status')}",
        f"🕐 Sana: {_v(req, 'created_at')}",
    ]
    return "\n".join(lines)


async def safe_send(bot: Bot, chat_id: int, text: str, **kwargs):
    try:
        await bot.send_message(chat_id, text, **kwargs)
        return True
    except Exception:
        return False


# ---------------- BIR NECHTA HR GA YUBORILGAN SO'ROV ----------------
# Bir so'rov barcha HR/adminlarga boradi. Kimdir birinchi bo'lib tasdiqlasa/rad
# etsa — qolganlaridagi xabar keraksiz bo'lib qoladi va ular ham bosishga urinadi.
# Shu sabab yuborilgan xabarlar bazaga yozib boriladi va so'rov ko'rib chiqilgach
# qolganlaridan avtomatik o'chiriladi.
async def broadcast_request(bot: Bot, kind, ref_id, tg_ids, text,
                            reply_markup=None, photo=None):
    """So'rov kartochkasini bir nechta xodimga yuboradi va xabar id larini yozadi.

    Yuborilgan xabarlar soni qaytadi."""
    sent = 0
    for tid in tg_ids:
        msg = None
        if photo:
            try:
                msg = await bot.send_photo(
                    tid, photo, caption=text, reply_markup=reply_markup
                )
            except Exception:
                msg = None  # file_id eskirgan / caption uzun — matn bilan urinamiz
        if msg is None:
            try:
                msg = await bot.send_message(tid, text, reply_markup=reply_markup)
            except Exception:
                continue  # bloklagan yoki botni ishga tushirmagan
        sent += 1
        try:
            await q.add_request_notice(kind, ref_id, tid, msg.message_id)
        except Exception:
            pass
    return sent


async def close_request_notices(bot: Bot, kind, ref_id, keep_chat_id=None):
    """So'rov ko'rib chiqilgach qolgan xodimlardagi xabarni o'chiradi.

    `keep_chat_id` — so'rovni ko'rib chiqqan xodim (uning xabari qoladi, unga
    handlerning o'zi natijani yozadi). O'chirib bo'lmasa (Telegram 48 soatdan
    eski xabarni o'chirtirmaydi) — hech bo'lmasa tugmalar olib tashlanadi."""
    try:
        rows = await q.pop_request_notices(kind, ref_id)
    except Exception:
        return 0
    removed = 0
    for row in rows:
        chat_id, message_id = row["chat_id"], row["message_id"]
        if keep_chat_id is not None and int(chat_id) == int(keep_chat_id):
            continue
        try:
            await bot.delete_message(chat_id, message_id)
            removed += 1
            continue
        except Exception:
            pass
        try:
            await bot.edit_message_reply_markup(
                chat_id=chat_id, message_id=message_id, reply_markup=None
            )
        except Exception:
            pass
    return removed


async def send_application_resume(bot: Bot, chat_id: int, app):
    """Ariza rezyume (CV/diplom) fayli bo'lsa yuboradi."""
    file_id = app.get("resume_file_id")
    if not file_id:
        return False
    caption = f"📄 Ariza #{app['id']} rezyumesi"
    try:
        if app.get("resume_type") == "photo":
            await bot.send_photo(chat_id, file_id, caption=caption)
        else:
            await bot.send_document(chat_id, file_id, caption=caption)
        return True
    except Exception:
        return False


async def send_application_photo(bot: Bot, chat_id: int, app):
    """Arizadagi oxirgi 10 kunda tushgan rasmni yuboradi (bo'lsa)."""
    file_id = app.get("photo_file_id")
    if not file_id:
        return False
    try:
        await bot.send_photo(
            chat_id, file_id, caption=f"📸 Ariza #{app['id']} — nomzod rasmi (oxirgi 10 kun)"
        )
        return True
    except Exception:
        return False


async def broadcast(bot: Bot, tg_ids, message):
    """message - kelgan Message obyekti. copy_message orqali yuboramiz."""
    ok = 0
    fail = 0
    for tid in tg_ids:
        try:
            await message.copy_to(chat_id=tid)
            ok += 1
        except Exception:
            fail += 1
    return ok, fail


# ---------------- MAXFIY KANAL ----------------
def normalize_chat_id(val):
    """Kanal ID sini to'g'ri turga keltiradi: @username -> str, raqam -> int."""
    if val is None:
        return None
    val = str(val).strip()
    if not val:
        return None
    if val.startswith("@"):
        return val
    try:
        return int(val)
    except ValueError:
        return val


# ---------------- KERAKLI XODIM JINSI ----------------
GENDER_LABELS = {
    "male": "👨 Erkak",
    "female": "👩 Ayol",
    "any": "👥 Erkak va ayol (farqi yo'q)",
}


def gender_label(value):
    """Bazadagi male/female/any qiymatini o'qiladigan matnga aylantiradi."""
    return GENDER_LABELS.get((value or "").strip().lower())


def vacancy_channel_text(v):
    """Kanalga joylash uchun chiroyli vakansiya matni."""
    lines = [
        "🆕 <b>YANGI VAKANSIYA</b>",
        "━━━━━━━━━━━━",
        f"💼 <b>Lavozim:</b> {_v(v, 'title')}",
        f"🏢 <b>Filial:</b> {_v(v, 'branch_name')}",
    ]
    if v.get("staff_count"):
        lines.append(f"👥 <b>Kerakli xodim:</b> {v['staff_count']} nafar")
    if gender_label(v.get("gender")):
        lines.append(f"🚻 <b>Kimlar uchun:</b> {gender_label(v['gender'])}")
    if v.get("shift"):
        lines.append(f"🕒 <b>Smena:</b> {v['shift']}")
    if v.get("work_time") and v.get("work_time") != v.get("shift"):
        lines.append(f"⏰ <b>Ish vaqti:</b> {v['work_time']}")
    if v.get("experience"):
        lines.append(f"📈 <b>Tajriba:</b> {v['experience']}")
    if v.get("salary"):
        lines.append(f"💰 <b>Maosh:</b> {v['salary']}")
    if v.get("requirements"):
        lines.append(f"\n📋 <b>Talablar:</b>\n{v['requirements']}")
    if v.get("responsibilities") and v["responsibilities"] != "HR suhbatida aniqlanadi.":
        lines.append(f"\n🎯 <b>Vazifalar:</b>\n{v['responsibilities']}")
    lines.append("\n📩 <b>Ariza berish:</b> quyidagi tugmani bosing — bot ochiladi va "
                 "«📝 Ishga ariza topshirish» anketasi boshlanadi.")
    return "\n".join(lines)


# Bot username i o'zgarmaydi — bir marta so'rab keshlaymiz (deep-link uchun kerak).
_bot_username = None


async def get_bot_username(bot: Bot):
    global _bot_username
    if _bot_username is None:
        try:
            me = await bot.get_me()
            _bot_username = me.username
        except Exception:
            return None
    return _bot_username


async def vacancy_apply_kb(bot: Bot, vacancy_id):
    """Kanaldagi e'lon tagidagi «Ishga ariza yuborish» tugmasi.

    Tugma botni `/start vac_<id>` deep-link bilan ochadi — anketa o'sha
    vakansiya uchun (filial va lavozim to'ldirilgan holda) boshlanadi."""
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    username = await get_bot_username(bot)
    if not username:
        return None
    b = InlineKeyboardBuilder()
    b.button(
        text="📝 Ishga ariza yuborish",
        url=f"https://t.me/{username}?start=vac_{vacancy_id}",
    )
    return b.as_markup()


async def post_vacancy_to_channel(bot: Bot, chat_id, vacancy):
    """Vakansiyani kanalga joylaydi. (chat_id, message_id) yoki (None, None) qaytaradi."""
    chat_id = normalize_chat_id(chat_id)
    if not chat_id:
        return None, None
    markup = await vacancy_apply_kb(bot, vacancy["id"])
    try:
        msg = await bot.send_message(
            chat_id, vacancy_channel_text(vacancy), reply_markup=markup
        )
        return chat_id, msg.message_id
    except Exception:
        return None, None


async def mark_vacancy_channel_filled(bot: Bot, vacancy):
    """Kanaldagi vakansiya postini «hodimlar soni to'ldi» holatiga yangilaydi.

    Ariza tugmasi ham olib tashlanadi — yopilgan vakansiyaga ariza kelmasin."""
    chat_id = vacancy.get("channel_chat_id")
    msg_id = vacancy.get("channel_message_id")
    if not chat_id or not msg_id:
        return False
    chat_id = normalize_chat_id(chat_id)
    text = (
        vacancy_channel_text(vacancy)
        + "\n\n✅ <b>HODIMLAR SONI TO'LDI — vakansiya yopildi.</b>"
    )
    try:
        await bot.edit_message_text(
            text, chat_id=chat_id, message_id=int(msg_id), reply_markup=None
        )
        return True
    except Exception:
        return False


async def post_application_to_channel(bot: Bot, chat_id, app, header=None):
    """Arizani maxfiy kanalga joylashtiradi — rasm + captionda ma'lumot (bitta post)."""
    chat_id = normalize_chat_id(chat_id)
    if not chat_id:
        return False
    msg = await send_application_card(bot, chat_id, app, header=header)
    if not msg:
        return False
    await send_application_resume(bot, chat_id, app)
    return True


# ---------------- ARIZA KARTOCHKASI (rasm + caption, BITTA xabar) ----------------
CAPTION_LIMIT = 1024          # Telegram rasm captioni chegarasi
CANDIDATE_HEADER = "📇 <b>NOMZOD — ISH QIDIRUVCHI</b>"


def _tg_len(text):
    """Telegram belgilarni UTF-16 birligida sanaydi (ko'p emoji = 2 birlik)."""
    return len(text.encode("utf-16-le")) // 2


def _fit_caption(text, limit=CAPTION_LIMIT):
    """Matnni caption chegarasiga sig'diradi — oxirgi qatorlarni olib tashlaydi."""
    if _tg_len(text) <= limit:
        return text
    lines = text.split("\n")
    while lines and _tg_len("\n".join(lines) + "\n…") > limit:
        lines.pop()
    return "\n".join(lines) + "\n…"


SEP = "━━━━━━━━━━"


def _clip(text, limit=140):
    """Uzun erkin matnni qisqartiradi (kartochka tartibi buzilmasligi uchun)."""
    text = " ".join(str(text or "").split())
    if not text:
        return "-"
    return text if len(text) <= limit else text[:limit].rstrip() + "…"


def application_caption(a, header=None):
    """Rasm captioni uchun TARTIBLI ariza kartochkasi.

    Har bir ma'lumot alohida qatorda, bloklarga ajratilgan — kanaldagi post
    o'qish uchun qulay bo'lsin. To'liq matn «👁 Batafsil» da."""
    status = STATUS_LABELS.get(a.get("status"), a.get("status") or "-")
    lines = [
        f"📄 <b>Ariza #{a['id']}</b> · {status}",
        SEP,
        f"👤 <b>{_v(a, 'full_name')}</b>",
        f"🎂 Tug'ilgan: {_v(a, 'birth_date')}",
        f"📱 Telefon: {_v(a, 'phone')}",
        f"📍 Manzil: {_v(a, 'city')}, {_v(a, 'district')}, {_v(a, 'address')}",
        SEP,
        f"💼 Lavozim: {_v(a, 'vacancy_title')}",
        f"🏢 Filial: {_v(a, 'branch_name')}",
        f"🕒 Smena: {_v(a, 'shift')}",
        f"🧩 Hujjat/tajriba: {_v(a, 'position_extra')}",
        SEP,
        f"🎓 Ma'lumoti: {_v(a, 'education')}",
        f"💼 Umumiy tajriba: {_v(a, 'exp_years')}",
        f"🏢 Oldingi ish joyida: {_v(a, 'prev_years')}",
        f"💻 Kompyuter savodxonligi: {computer_level_label(a)}",
        f"🌍 Tillar: {_clip(a.get('languages'), 90)}",
        SEP,
        f"⚖️ Sudlanganligi: {_v(a, 'criminal')}",
        f"👨‍👩‍👧 Oilaviy holati: {_v(a, 'marital')}",
        f"👶 Farzandlari: {_v(a, 'children')}",
        SEP,
        f"💰 Oldingi maosh: {_v(a, 'prev_salary')}",
        f"💵 Kutayotgan maosh: {_v(a, 'expected_salary')}",
        f"📅 Ishlash niyati: {_v(a, 'work_intent')}",
        f"✍️ Sababi: {_clip(a.get('reason'))}",
    ]
    if a.get("hr_comment"):
        lines.append(f"🗒 HR izohi: {_clip(a.get('hr_comment'))}")
    if a.get("resume_file_id"):
        lines.append("📎 Rezyume biriktirilgan")
    lines += [SEP, f"🗓 {_v(a, 'created_at')}"]
    text = "\n".join(lines)
    if header:
        text = f"{header}\n{text}"
    return _fit_caption(text)


async def send_application_card(bot: Bot, chat_id, app, reply_markup=None, header=None):
    """Arizani BITTA xabarda yuboradi: rasm + captionda ma'lumot + tugmalar.
    Rasm bo'lmasa oddiy matn yuboradi. Yuborilgan Message (yoki None) qaytadi."""
    caption = application_caption(app, header=header)
    file_id = app.get("photo_file_id")
    if file_id:
        try:
            return await bot.send_photo(
                chat_id, file_id, caption=caption, reply_markup=reply_markup
            )
        except Exception:
            pass  # file_id eskirgan bo'lishi mumkin — matn bilan urinamiz
    try:
        return await bot.send_message(chat_id, caption, reply_markup=reply_markup)
    except Exception:
        return None


# ---------------- KANDIDATLAR (KUTUVCHILAR) KANALI ----------------
async def post_application_channel(bot: Bot, chat_id, app):
    """Arizani kandidatlar kanaliga BITTA post qilib joylaydi.
    (chat_id, message_id) yoki (None, None) qaytaradi — keyin status yangilash uchun."""
    chat_id = normalize_chat_id(chat_id)
    if not chat_id:
        return None, None
    msg = await send_application_card(bot, chat_id, app, header=CANDIDATE_HEADER)
    if not msg:
        return None, None
    # Rezyume fayl — Telegram uni rasm bilan bitta xabarga qo'sha olmaydi
    await send_application_resume(bot, chat_id, app)
    return chat_id, msg.message_id


async def update_application_channel(bot: Bot, app):
    """Kanaldagi ariza postining status matnini yangilaydi (post tahrirlanadi)."""
    chat_id = app.get("channel_chat_id")
    msg_id = app.get("channel_message_id")
    if not chat_id or not msg_id:
        return False
    chat_id = normalize_chat_id(chat_id)
    caption = application_caption(app, header=CANDIDATE_HEADER)
    try:
        await bot.edit_message_caption(
            chat_id=chat_id, message_id=int(msg_id), caption=caption
        )
        return True
    except Exception:
        pass
    # Post rasmsiz (oddiy matn) bo'lsa — matnni tahrirlaymiz
    try:
        await bot.edit_message_text(caption, chat_id=chat_id, message_id=int(msg_id))
        return True
    except Exception:
        return False


# ---------------- SUHBAT KANALI ----------------
INTERVIEW_CONFIRM_LABELS = {
    "pending": "🟡 Kutilmoqda",
    "confirmed": "✅ Nomzod tasdiqladi",
    "reschedule": "🔄 Boshqa vaqt so'radi",
}
INTERVIEW_ATTENDANCE_LABELS = {
    None: "⏳ Belgilanmagan",
    "": "⏳ Belgilanmagan",
    "came": "✅ Keldi",
    "absent": "❌ Kelmadi",
}


def interview_confirm_label(interview):
    return INTERVIEW_CONFIRM_LABELS.get(interview.get("status"), interview.get("status") or "-")


def interview_attendance_label(interview):
    return INTERVIEW_ATTENDANCE_LABELS.get(interview.get("attendance") or None, "⏳ Belgilanmagan")


def interview_channel_header(interview):
    """Suhbat kartochkasi tepasidagi sarlavha: sana/vaqt/manzil + holatlar."""
    lines = [
        "🗣 <b>SUHBATGA CHAQIRILDI</b>",
        f"📆 Sana: {interview.get('date') or '-'}   🕐 Vaqt: {interview.get('time') or '-'}",
        f"📍 Manzil: {interview.get('location') or '-'}",
    ]
    if interview.get("comment") and interview["comment"] != "-":
        lines.append(f"💬 Izoh: {interview['comment']}")
    lines.append(f"📩 Nomzod javobi: {interview_confirm_label(interview)}")
    lines.append(f"🚦 Kelish holati: {interview_attendance_label(interview)}")
    return "\n".join(lines)


async def post_interview_to_channel(bot: Bot, chat_id, interview, app):
    """Suhbat kartochkasini (to'liq ariza + rasm) suhbat kanaliga joylaydi.

    (chat_id, message_id) yoki (None, None) qaytaradi. Kanal ulanmagan bo'lsa
    ham (None, None) — bu xato emas."""
    chat_id = normalize_chat_id(chat_id)
    if not chat_id:
        return None, None
    header = interview_channel_header(interview)
    msg = await send_application_card(bot, chat_id, app, header=header)
    if not msg:
        return None, None
    return chat_id, msg.message_id


async def update_interview_channel(bot: Bot, interview, app):
    """Kanaldagi suhbat postini yangilaydi (holat o'zgarganda tahrirlanadi)."""
    chat_id = interview.get("channel_chat_id")
    msg_id = interview.get("channel_message_id")
    if not chat_id or not msg_id:
        return False
    chat_id = normalize_chat_id(chat_id)
    caption = application_caption(app, header=interview_channel_header(interview))
    try:
        await bot.edit_message_caption(
            chat_id=chat_id, message_id=int(msg_id), caption=caption
        )
        return True
    except Exception:
        pass
    # Rasmsiz (oddiy matn) post bo'lsa — matnni tahrirlaymiz
    try:
        await bot.edit_message_text(caption, chat_id=chat_id, message_id=int(msg_id))
        return True
    except Exception:
        return False


async def post_staff_reg_to_channel(bot: Bot, chat_id, reg, header=None):
    """Tasdiqlangan «Gulnora Farm hodimi» ma'lumotlarini kanalga joylaydi.

    Rasm bo'lsa — rasm + caption bitta post. Kanal ulanmagan bo'lsa None
    (xato emas), yuborib bo'lmasa False qaytadi."""
    chat_id = normalize_chat_id(chat_id)
    if not chat_id:
        return None
    text = staff_reg_text(reg)
    if header:
        text = f"{header}\n{text}"
    file_id = reg.get("photo_file_id")
    if file_id:
        try:
            await bot.send_photo(chat_id, file_id, caption=_fit_caption(text))
            return True
        except Exception:
            pass  # file_id eskirgan yoki caption uzun — matn bilan urinamiz
    try:
        await bot.send_message(chat_id, text)
        return True
    except Exception:
        return False


# ---------------- ARIZA ↔ VAKANSIYA MOSLIGI ----------------
_NORM_RE = re.compile(r"[^\w\s']", flags=re.UNICODE)


def _norm(text):
    """Emoji/tinish belgilarni olib tashlab, kichik harfga keltiradi."""
    if not text:
        return ""
    text = _NORM_RE.sub(" ", str(text).lower())
    return " ".join(text.split())


def text_similarity(a, b):
    """0..1 — ikki matnning o'xshashligi (belgi va so'z darajasida)."""
    na, nb = _norm(a), _norm(b)
    if not na or not nb:
        return 0.0
    seq = SequenceMatcher(None, na, nb).ratio()
    ta, tb = set(na.split()), set(nb.split())
    union = ta | tb
    jac = len(ta & tb) / len(union) if union else 0.0
    return max(seq, jac)


def match_score(app, vacancy):
    """0..100 — nomzod arizasi vakansiyaga qanchalik mos kelishi (foizda)."""
    pos_sim = text_similarity(
        app.get("position") or app.get("vacancy_title"),
        vacancy.get("title"),
    )
    same_branch = (
        1.0
        if app.get("branch_id") and app.get("branch_id") == vacancy.get("branch_id")
        else 0.0
    )
    same_shift = (
        1.0
        if _norm(app.get("shift")) and _norm(app.get("shift")) == _norm(vacancy.get("shift"))
        else 0.0
    )
    score = 0.65 * pos_sim + 0.25 * same_branch + 0.10 * same_shift
    return round(score * 100)


def best_vacancy_matches(app, vacancies, threshold=60, limit=3):
    """Chegaradan yuqori mos vakansiyalar ro'yxati [(vacancy, score), ...]."""
    scored = []
    for v in vacancies or []:
        s = match_score(app, v)
        if s >= threshold:
            scored.append((v, s))
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:limit]


# ---------------- SINOV MUDDATI (PROBATION) ----------------
def parse_date_input(text):
    """'kun.oy.yil' yoki 'bugun' -> (iso 'YYYY-MM-DD', display 'dd.mm.yyyy') yoki None."""
    text = (text or "").strip().lower()
    if text in ("bugun", "today", "hozir", "shu kun"):
        d = date.today()
        return d.isoformat(), d.strftime("%d.%m.%Y")
    if text in ("erta", "ertaga", "tomorrow"):
        d = date.today() + timedelta(days=1)
        return d.isoformat(), d.strftime("%d.%m.%Y")
    t = text.replace("/", ".").replace("-", ".")
    for fmt in ("%d.%m.%Y", "%d.%m.%y"):
        try:
            d = datetime.strptime(t, fmt).date()
            return d.isoformat(), d.strftime("%d.%m.%Y")
        except ValueError:
            continue
    return None


def iso_to_display(iso):
    try:
        return date.fromisoformat(iso).strftime("%d.%m.%Y")
    except (ValueError, TypeError):
        return iso or "-"


def add_days_iso(iso, days):
    """ISO sanaga kun qo'shadi -> yangi ISO."""
    return (date.fromisoformat(iso) + timedelta(days=days)).isoformat()


def days_left_until(iso):
    """Bugundan berilgan ISO sanagacha necha kun qolganini qaytaradi."""
    try:
        return (date.fromisoformat(iso) - date.today()).days
    except (ValueError, TypeError):
        return None


def probation_text(p, stats=None):
    """Sinov / o'rganuvchi muddati kartochkasi (ixtiyoriy davomat statistikasi bilan)."""
    left = days_left_until(p.get("end_date"))
    if p.get("status") == "finished" or (left is not None and left < 0):
        state = "🏁 Tugagan"
    elif left == 0:
        state = "⏳ Bugun tugaydi"
    else:
        state = f"🟢 Davom etmoqda ({left} kun qoldi)" if left is not None else "🟢 Davom etmoqda"
    if p.get("kind") == "learner":
        title = f"🎓 <b>O'rganuvchi #{p['id']}</b>"
    else:
        title = f"🧪 <b>Sinov muddati #{p['id']}</b>"
    lines = [
        f"{title} — {state}",
        "━━━━━━━━━━━━",
        f"👤 Xodim: <b>{p.get('full_name') or '-'}</b>",
        f"💼 Lavozim: {p.get('position') or '-'}",
        f"🏢 Filial: {p.get('branch_name') or '-'}",
        f"📅 Boshlanishi: {iso_to_display(p.get('start_date'))}",
        f"🏁 Tugashi: {iso_to_display(p.get('end_date'))} ({p.get('days', 15)} kun)",
    ]
    if stats is not None:
        present = stats.get("present_days", 0) or 0
        total = p.get("days", 15) or 15
        # o'tgan kunlar (bugungacha), sinov davridan oshib ketmasin
        elapsed = total
        dl = days_left_until(p.get("end_date"))
        if dl is not None and dl > 0:
            elapsed = max(0, total - dl)
        absent = max(0, elapsed - present)
        lines += [
            "\n📊 <b>Davomat statistikasi</b>",
            f"✅ Kelgan kunlari: <b>{present}</b>",
            f"❌ Kelmagan kunlari: <b>{absent}</b>",
            f"⏰ Kechikkan: {stats.get('lates', 0) or 0} marta · 🏃 Erta ketgan: {stats.get('earlies', 0) or 0} marta",
        ]
    return "\n".join(lines)


def recommendation_text(matches):
    """HR uchun avtomatik tavsiya bloki."""
    if not matches:
        return ""
    lines = [
        "",
        "⭐ <b>Avtomatik tavsiya</b>",
        "Bu nomzod quyidagi ochiq vakansiya(lar)ga mos keladi:",
    ]
    for v, sc in matches:
        branch = v.get("branch_name") or "filial ko'rsatilmagan"
        lines.append(f"• <b>{v['title']}</b> — {branch} — <b>{sc}%</b> mos (vak #{v['id']})")
    lines.append("👉 Mos kelsa, nomzodni shu vakansiyaga taklif qiling.")
    return "\n".join(lines)
