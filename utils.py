"""Yordamchi funksiyalar: obuna tekshirish, matn formatlash."""
from math import radians, sin, cos, asin, sqrt

from aiogram import Bot
from database import queries as q
from database.db import STATUS_LABELS


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
            f"📝 Word: {_v(a, 'word_level')}",
            f"📊 Excel: {_v(a, 'excel_level')}",
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
        f"📝 Word: {g('word_level')}\n"
        f"📊 Excel: {g('excel_level')}\n"
        f"🌍 Tillar: {g('languages')}\n"
        f"📅 Ishlash niyati: {g('work_intent')}\n"
        f"✍️ Sababi: {g('reason')}\n"
        f"📱 Telefon: {g('phone')}\n"
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
    parts.append(f"💰 Oylik: {_v(profile, 'monthly_salary')}")
    if profile.get("since"):
        parts.append(f"⏳ Ish staji: {profile['since']}")
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
    ]
    if reg.get("since"):
        parts.append(f"⏳ Staj: {reg['since']}")
    if reg.get("extra_info"):
        parts.append(f"🧩 Qo'shimcha: {reg['extra_info']}")
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
    kind = "➕ Xodim kerak" if req.get("kind") == "vacancy" else "🔧 Texnik nosozlik"
    return (
        f"📨 <b>So'rov #{req['id']}</b>\n"
        "━━━━━━━━━━━━\n"
        f"{kind}\n"
        f"🏢 Filial: {_v(req, 'branch_name')}\n"
        f"👤 Rahbar: {_v(req, 'manager_name')}\n"
        f"📌 Mavzu/lavozim: {_v(req, 'title')}\n"
        f"👥 Kerakli soni: {_v(req, 'staff_count')}\n"
        f"📝 Tafsilot: {_v(req, 'details')}\n"
        f"Holati: {_v(req, 'status')}\n"
        f"🕐 Sana: {_v(req, 'created_at')}"
    )


async def safe_send(bot: Bot, chat_id: int, text: str, **kwargs):
    try:
        await bot.send_message(chat_id, text, **kwargs)
        return True
    except Exception:
        return False


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
