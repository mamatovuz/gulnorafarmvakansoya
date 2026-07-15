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


async def post_application_to_channel(bot: Bot, chat_id, app, header=None):
    """Ariza matnini (va bo'lsa rezyumesini) maxfiy kanalga joylashtiradi."""
    chat_id = normalize_chat_id(chat_id)
    if not chat_id:
        return False
    text = application_text(app, full=True)
    if header:
        text = f"{header}\n\n{text}"
    try:
        await bot.send_message(chat_id, text)
        await send_application_resume(bot, chat_id, app)
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
