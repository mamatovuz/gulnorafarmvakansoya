"""Barcha klaviaturalar (reply va inline)."""
from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from i18n import t, choices as i18n_choices, LANG_NAMES, LANGS
from database.db import (
    ROLE_ADMIN, ROLE_HR, ROLE_MANAGER, ROLE_EMPLOYEE, ROLE_PHARMACIST,
    ROLE_DIRECTOR, ROLE_ACCOUNTANT, ROLE_IT, ROLE_CANDIDATE,
    ST_NEW, ST_INTERVIEW, ST_ACCEPTED, ST_REJECTED,
)


def phone_kb():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Telefon raqamni yuborish", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


EMPLOYEE_ROLES = (
    ROLE_MANAGER, ROLE_PHARMACIST, ROLE_DIRECTOR, ROLE_EMPLOYEE, ROLE_ACCOUNTANT,
)

# Xodim menyusidagi «HR ga murojaat» tugmasi (ish vaqti / maosh / boshqa masala)
HR_REQUEST_BTN = "📩 HR ga murojaat"

# Admin panelidagi «Ma'lumotlarni yangilash» kampaniyasi tugmasi
PROFILE_UPDATE_BTN = "🔄 Ma'lumotlarni yangilash"

# Admin/HR panelidagi «Ma'lumotlarni o'zgartirish» — xodim rol/filialini
# to'g'ridan-to'g'ri tahrirlash oqimi (empmanage.py)
EMP_MANAGE_BTN = "🛠 Ma'lumotlarni o'zgartirish"

# Asosiy menyu tugmalari — bosilganda yarim qolgan FSM oqimi bekor qilinadi
# (aks holda tugma matni ochiq anketa savoliga javob sifatida ketib qoladi).
MENU_ESCAPE_BUTTONS = {
    "📍 Ishga keldim", "🏁 Ishdan ketdim", "⏸ Tanaffus", "▶️ Ishni davom ettirish",
    "👤 Mening profilim", "🔄 Dam olish kunini almashtirish", HR_REQUEST_BTN,
    "💸 HR ga so'rov",  # eski nomdagi tugma (kesh qolgan klaviaturalar uchun)
    "💼 Vakansiyalar", "📄 Mening arizalarim", "🏠 Asosiy menyu",
    "👨‍💼 HR panel", "👑 Admin panel", "📈 Direktor panel", "🧮 Moliya bo'limi",
    "❌ Rad etilgan murojaatlar", "👥 Xodimlar",
    "🔐 Ishonch xabari", "📊 Bildirishnoma statistika",
    "🖥 IT xodim panel", "🏢 Filial rahbari panel", "💊 Farmatsevt panel",
    EMP_MANAGE_BTN, "🔀 Filial almashtirish",
}


def main_menu(role, has_applied=False, lang=None):
    """Rolga qarab asosiy menyu (foydalanuvchi tilida).

    Yangi foydalanuvchi (nomzod, hali ariza topshirmagan) uchun faqat 2 ta tugma
    ko'rinadi. Ariza topshirgach yoki rol berilgach to'liq menyu chiqadi.
    """
    b = ReplyKeyboardBuilder()
    # «Ishga ariza topshirish» va «Gulnora Farm hodimi» tugmalari faqat nomzodga
    # ko'rinadi. Xodim sifatida tasdiqlangach (rol berilgach) ular olib tashlanadi.
    if role == ROLE_CANDIDATE:
        b.button(text=t("btn.apply", lang))
        b.button(text=t("btn.staffreg", lang))
        # Nomzod hali ariza topshirmagan bo'lsa — shu 2 ta tugma + til
        if not has_applied:
            b.button(text=t("btn.lang", lang))
            b.adjust(1)
            return b.as_markup(resize_keyboard=True)
    b.button(text=t("btn.vacancies", lang))
    # Ro'yxatdan o'tgan (tasdiqlangan) xodimlar uchun davomat
    if role in EMPLOYEE_ROLES:
        b.button(text=t("btn.checkin", lang))
        b.button(text=t("btn.checkout", lang))
        b.button(text=t("btn.break", lang))
        b.button(text=t("btn.resume", lang))
        b.button(text=t("btn.profile", lang))
        b.button(text=t("btn.dayoff", lang))
        b.button(text=t("btn.hr_request", lang))
        b.button(text=t("btn.lang", lang))
    if role == ROLE_MANAGER:
        b.button(text="🏢 Filial rahbari panel")
    if role == ROLE_PHARMACIST:
        b.button(text="💊 Farmatsevt panel")
    if role == ROLE_DIRECTOR:
        b.button(text="📈 Direktor panel")
    if role == ROLE_ACCOUNTANT:
        b.button(text="🧮 Moliya bo'limi")
    if role == ROLE_IT:
        b.button(text="🖥 IT xodim panel")
    if role == ROLE_HR:
        b.button(text="👨‍💼 HR panel")
    if role == ROLE_ADMIN:
        b.button(text="👨‍💼 HR panel")
        b.button(text="👑 Admin panel")
        b.button(text="📈 Direktor panel")
        b.button(text="🧮 Moliya bo'limi")
        b.button(text="🖥 IT xodim panel")
        b.button(text="🏢 Filial rahbari panel")
    b.adjust(2, 2, 2, 2, 2, 2)
    return b.as_markup(resize_keyboard=True)


# ---------------- ARIZA klaviaturalari ----------------
CANCEL_BTN = "❌ Bekor qilish"          # kanonik (o'zbekcha) variant
# Bekor qilish tugmasining barcha tildagi ko'rinishlari — filtrlar uchun
CANCEL_BUTTONS = {CANCEL_BTN, "❌ Отмена"}


def cancel_text(lang=None):
    return t("btn.cancel", lang)


def _choices(options, row=2, lang=None):
    b = ReplyKeyboardBuilder()
    for o in options:
        b.button(text=o)
    b.button(text=cancel_text(lang))
    b.adjust(row)
    return b.as_markup(resize_keyboard=True, one_time_keyboard=True)


def _group_kb(group, row=2, lang=None):
    """i18n tanlov guruhi bo'yicha klaviatura (foydalanuvchi tilida)."""
    return _choices(i18n_choices(group, lang), row=row, lang=lang)


def cancel_kb(lang=None):
    b = ReplyKeyboardBuilder()
    b.button(text=cancel_text(lang))
    return b.as_markup(resize_keyboard=True, one_time_keyboard=True)


def lang_pick_kb():
    """Til tanlash (inline) — /start da va «🌐 Til» tugmasida."""
    b = InlineKeyboardBuilder()
    for code in LANGS:
        b.button(text=LANG_NAMES[code], callback_data=f"setlang:{code}")
    b.adjust(1)
    return b.as_markup()


REGION_DISTRICTS = {
    "Toshkent shahri": [
        "Bektemir", "Chilonzor", "Mirobod", "Mirzo Ulug'bek", "Olmazor",
        "Sergeli", "Shayxontohur", "Uchtepa", "Yakkasaroy", "Yashnobod",
        "Yunusobod", "Yangihayot",
    ],
    "Toshkent viloyati": [
        "Angren", "Bekobod", "Bo'ka", "Bo'stonliq", "Chinoz", "Chirchiq",
        "Ohangaron", "Olmaliq", "Oqqo'rg'on", "Parkent", "Piskent",
        "Qibray", "Quyichirchiq", "Toshkent tumani", "Yangiyo'l",
        "Yuqorichirchiq", "Zangiota",
    ],
    "Andijon": [
        "Andijon shahri", "Andijon tumani", "Asaka", "Baliqchi", "Bo'ston",
        "Buloqboshi", "Izboskan", "Jalaquduq", "Marhamat", "Oltinko'l",
        "Paxtaobod", "Qo'rg'ontepa", "Shahrixon", "Ulug'nor", "Xo'jaobod",
    ],
    "Farg'ona": [
        "Farg'ona shahri", "Beshariq", "Bog'dod", "Buvayda", "Dang'ara",
        "Furqat", "Marg'ilon", "Oltiariq", "Qo'qon", "Quva", "Rishton",
        "So'x", "Toshloq", "Uchko'prik", "Yozyovon",
    ],
    "Namangan": [
        "Namangan shahri", "Chortoq", "Chust", "Kosonsoy", "Mingbuloq",
        "Norin", "Pop", "To'raqo'rg'on", "Uchqo'rg'on", "Uychi",
        "Yangiqo'rg'on",
    ],
    "Samarqand": [
        "Samarqand shahri", "Bulung'ur", "Ishtixon", "Jomboy", "Kattaqo'rg'on",
        "Narpay", "Nurobod", "Oqdaryo", "Paxtachi", "Pastdarg'om",
        "Payariq", "Qo'shrabot", "Toyloq", "Urgut",
    ],
    "Buxoro": [
        "Buxoro shahri", "Buxoro tumani", "G'ijduvon", "Jondor", "Kogon",
        "Olot", "Peshku", "Qorako'l", "Qorovulbozor", "Romitan",
        "Shofirkon", "Vobkent",
    ],
    "Jizzax": [
        "Jizzax shahri", "Arnasoy", "Baxmal", "Do'stlik", "Forish",
        "G'allaorol", "Mirzacho'l", "Paxtakor", "Yangiobod", "Zafarobod",
        "Zarbdor", "Zomin",
    ],
    "Sirdaryo": [
        "Guliston", "Boyovut", "Mirzaobod", "Oqoltin", "Sardoba",
        "Sayxunobod", "Sirdaryo", "Xovos", "Yangiyer", "Shirin",
    ],
    "Qashqadaryo": [
        "Qarshi", "Chiroqchi", "Dehqonobod", "G'uzor", "Kasbi", "Kitob",
        "Koson", "Mirishkor", "Muborak", "Nishon", "Qamashi", "Shahrisabz",
        "Yakkabog'",
    ],
    "Surxondaryo": [
        "Termiz", "Angor", "Bandixon", "Boysun", "Denov", "Jarqo'rg'on",
        "Muzrabot", "Oltinsoy", "Qiziriq", "Qumqo'rg'on", "Sariosiyo",
        "Sherobod", "Sho'rchi", "Uzun",
    ],
    "Navoiy": [
        "Navoiy shahri", "Karmana", "Konimex", "Navbahor", "Nurota",
        "Qiziltepa", "Tomdi", "Uchquduq", "Xatirchi", "Zarafshon",
    ],
    "Xorazm": [
        "Urganch", "Bog'ot", "Gurlan", "Hazorasp", "Xiva", "Qo'shko'pir",
        "Shovot", "Tuproqqal'a", "Xonqa", "Yangiariq", "Yangibozor",
    ],
    "Qoraqalpog'iston": [
        "Nukus", "Amudaryo", "Beruniy", "Chimboy", "Ellikqal'a", "Kegeyli",
        "Mo'ynoq", "Qanliko'l", "Qo'ng'irot", "Qorao'zak", "Shumanay",
        "Taxtako'pir", "To'rtko'l", "Xo'jayli",
    ],
}


def apply_city_kb():
    return _choices(list(REGION_DISTRICTS.keys()), row=2)


def apply_district_kb(region):
    districts = REGION_DISTRICTS.get(region, [])
    return _choices(districts or ["Tuman ro'yxatda yo'q"], row=2)


def apply_branch_kb(branches):
    b = ReplyKeyboardBuilder()
    for br in branches:
        b.button(text=f"📍 {br['name']}")
    b.button(text=CANCEL_BTN)
    b.adjust(2)
    return b.as_markup(resize_keyboard=True, one_time_keyboard=True)


POSITIONS = [
    "💊 Farmatsevt", "👨‍💼 Filial rahbari", "👔 Direktor", "🧮 Moliya bo'limi",
    "🧹 Tozalik xodimi", "📦 Omborchi", "🚚 Haydovchi",
]


def apply_position_kb(names=None):
    """names — bazadagi yo'nalishlar; bo'sh bo'lsa standart ro'yxat."""
    return _choices(list(names) if names else POSITIONS, row=2)


def positions_manage_kb(positions):
    b = InlineKeyboardBuilder()
    b.button(text="➕ Lavozim qo'shish", callback_data="pos_add")
    for p in positions:
        b.button(text=f"🗑 {p['name']}", callback_data=f"pos_del:{p['id']}")
    b.adjust(1)
    return b.as_markup()


def apply_shift_kb(lang=None):
    return _group_kb("shift", row=1, lang=lang)


# Sinov/ishga qabulda smena tanlash (inline)
PROBATION_SHIFTS = ["🌞 Ertalabgi smena", "🌙 Kechki smena", "🔄 Farqi yo'q"]


def tech_issue_confirm_kb():
    """Texnik nosozlikni HR ga yuborishdan oldin tasdiqlash."""
    b = InlineKeyboardBuilder()
    b.button(text="✅ Ha, HR ga yuborilsin", callback_data="techissue:send")
    b.button(text="❌ Yo'q, bekor qilish", callback_data="techissue:cancel")
    b.adjust(1)
    return b.as_markup()


def probation_shift_kb():
    b = InlineKeyboardBuilder()
    for i, s in enumerate(PROBATION_SHIFTS):
        b.button(text=s, callback_data=f"probshift:{i}")
    b.adjust(1)
    return b.as_markup()


def apply_gender_kb(lang=None):
    return _group_kb("gender", row=2, lang=lang)


def apply_criminal_kb(lang=None):
    return _group_kb("criminal", row=2, lang=lang)


def apply_marital_kb(lang=None):
    return _group_kb("marital", row=1, lang=lang)


def apply_children_kb(lang=None):
    return _group_kb("children", row=2, lang=lang)


def apply_level_kb(lang=None):
    return _choices(["❌ Bilmayman", "🟡 Bazaviy", "🟠 O'rtacha", "🟢 Yaxshi"],
                    row=2, lang=lang)


# Kompyuter savodxonligi — Word/Excel savollari o'rniga bitta savol
COMPUTER_LEVELS = ["✅ Ha", "🟠 O'rtacha", "❌ Yo'q"]


def apply_computer_kb(lang=None):
    return _group_kb("computer", row=3, lang=lang)


def apply_experience_kb(lang=None):
    return _group_kb("experience", row=2, lang=lang)


def apply_prev_years_kb(lang=None):
    return _group_kb("prev_years", row=2, lang=lang)


def apply_work_intent_kb(lang=None):
    return _group_kb("work_intent", row=2, lang=lang)


def apply_uniform_kb(lang=None):
    return _group_kb("uniform", row=1, lang=lang)


def apply_position_extra_kb(position, lang=None):
    p = (position or "").lower()
    if "farm" in p:
        # Ma'lumot ro'yxati bilan bir xil + sertifikat varianti
        extra = "✅ Sertifikatim bor" if (lang or "uz") == "uz" else "✅ Есть сертификат"
        return _choices(i18n_choices("education", lang) + [extra], row=1, lang=lang)
    if "filial rahbari" in p:
        return _choices(["🚫 Tajribam yo'q", "👥 1-5 xodim", "👥 6-15 xodim",
                         "👥 15+ xodim"], row=2, lang=lang)
    if "direktor" in p or "director" in p:
        return _choices(["🟡 1-3 yil", "🟠 3-5 yil", "🟢 5+ yil", "🚫 Tajribam yo'q"],
                        row=2, lang=lang)
    return _group_kb("experience", row=2, lang=lang)


def apply_phone_kb(lang=None):
    b = ReplyKeyboardBuilder()
    share = ("📲 Отправить номер телефона" if (lang or "uz") == "ru"
             else "📲 Telefon raqamni yuborish")
    b.button(text=share, request_contact=True)
    b.button(text=cancel_text(lang))
    b.adjust(1)
    return b.as_markup(resize_keyboard=True, one_time_keyboard=True)


def apply_resume_kb(lang=None):
    b = ReplyKeyboardBuilder()
    b.button(text=t("btn.skip", lang))
    b.button(text=cancel_text(lang))
    b.adjust(1)
    return b.as_markup(resize_keyboard=True, one_time_keyboard=True)


def apply_confirm_kb():
    b = InlineKeyboardBuilder()
    b.button(text="✅ Tasdiqlash", callback_data="app_confirm")
    b.button(text="✏️ Tahrirlash", callback_data="app_edit")
    b.button(text="❌ Bekor qilish", callback_data="app_cancel")
    b.adjust(1)
    return b.as_markup()


# Tahrirlash uchun maydonlar ro'yxati
EDIT_FIELDS = [
    ("full_name", "👤 Ism-sharif"),
    ("birth_date", "📅 Tug'ilgan sana"),
    ("city", "🌆 Shahar/viloyat"),
    ("district", "📍 Tuman"),
    ("address", "🏠 Aniq manzil"),
    ("branch", "🏢 Filial"),
    ("position", "💼 Lavozim"),
    ("position_extra", "🧩 Lavozim savoli"),
    ("shift", "🕒 Smena"),
    ("education", "🎓 Ma'lumot"),
    ("exp_years", "💼 Umumiy tajriba"),
    ("prev_years", "🏢 Oldingi ish yili"),
    ("criminal", "⚖️ Sudlanganlik"),
    ("marital", "👨‍👩‍👧 Oilaviy holat"),
    ("children", "👶 Farzand"),
    ("prev_salary", "💰 Oldingi maosh"),
    ("expected_salary", "💵 Kutilayotgan maosh"),
    ("computer_level", "💻 Kompyuter savodxonligi"),
    ("languages", "🌍 Tillar"),
    ("work_intent", "📅 Ishlash niyati"),
    ("reason", "✍️ Sabab"),
    ("phone", "📱 Telefon"),
]


def apply_edit_fields_kb():
    b = InlineKeyboardBuilder()
    for key, label in EDIT_FIELDS:
        b.button(text=label, callback_data=f"ef:{key}")
    b.button(text="📸 Rasm", callback_data="ef:photo")
    b.button(text="⬅️ Orqaga", callback_data="ef_back")
    b.adjust(2)
    return b.as_markup()


def reject_reason_kb(aid):
    """Arizani rad etishda: tayyor javoblar ro'yxati yoki o'z matni."""
    b = InlineKeyboardBuilder()
    b.button(text="📋 Tayyor javoblar", callback_data=f"apprejlist:{aid}")
    b.button(text="🔤 Umumiy (lotincha)", callback_data=f"apprejt:{aid}:lat")
    b.button(text="🔡 Умумий (кириллча)", callback_data=f"apprejt:{aid}:cyr")
    b.button(text="✍️ O'zim yozaman", callback_data=f"apprejw:{aid}")
    b.button(text="✏️ Umumiy javobni tahrirlash", callback_data="rejtpl:menu")
    b.adjust(1)
    return b.as_markup()


def reject_templates_kb(aid):
    """Bir nechta tayyor rad javoblari ro'yxati — bittasini tanlab yuboriladi."""
    from utils import REJECT_REASON_TEMPLATES
    b = InlineKeyboardBuilder()
    for key, (label, _text) in REJECT_REASON_TEMPLATES.items():
        b.button(text=label, callback_data=f"apprejpick:{aid}:{key}")
    b.button(text="⬅️ Orqaga", callback_data=f"apprejback:{aid}")
    b.adjust(1)
    return b.as_markup()


def reject_template_menu_kb():
    """Tayyor javob matnini tahrirlash — qaysi tildagi matn tahrirlanadi."""
    b = InlineKeyboardBuilder()
    b.button(text="🔤 Lotincha matnni tahrirlash", callback_data="rejtpl:edit:lat")
    b.button(text="🔡 Кириллча matnni tahrirlash", callback_data="rejtpl:edit:cyr")
    b.button(text="♻️ Standart matnni tiklash", callback_data="rejtpl:reset")
    b.adjust(1)
    return b.as_markup()


def reject_template_reset_kb():
    """Standart matnni tiklashda til tanlash."""
    b = InlineKeyboardBuilder()
    b.button(text="🔤 Lotincha", callback_data="rejtpl:resetdo:lat")
    b.button(text="🔡 Кириллча", callback_data="rejtpl:resetdo:cyr")
    b.button(text="⬅️ Orqaga", callback_data="rejtpl:menu")
    b.adjust(2, 1)
    return b.as_markup()


def apply_missing_fields_kb(missing):
    """To'ldirilmagan majburiy maydonlar uchun tugmalar.

    missing — [(tahrir_kaliti, nomi), ...]"""
    b = InlineKeyboardBuilder()
    for key, label in missing:
        b.button(text=f"✏️ {label}", callback_data=f"ef:{key}")
    b.adjust(1)
    return b.as_markup()


def subscription_kb(channels):
    b = InlineKeyboardBuilder()
    for ch in channels:
        url = ch.get("url") or (f"https://t.me/{ch['chat_id'].lstrip('@')}" if ch.get("chat_id", "").startswith("@") else "https://t.me/")
        b.button(text=f"📢 {ch.get('title') or 'Kanal'}", url=url)
    b.button(text="✅ Tekshirish", callback_data="check_sub")
    b.adjust(1)
    return b.as_markup()


# ---------------- NOMZOD ----------------
def vacancies_list_kb(vacancies, prefix="vac"):
    b = InlineKeyboardBuilder()
    for v in vacancies:
        branch = f" · {v['branch_name']}" if v.get("branch_name") else ""
        b.button(text=f"💼 {v['title']}{branch}", callback_data=f"{prefix}:{v['id']}")
    b.adjust(1)
    return b.as_markup()


def applications_list_kb(apps, prefix="appview"):
    b = InlineKeyboardBuilder()
    for a in apps:
        title = a.get("vacancy_title") or a.get("position") or "Ariza"
        status = a.get("status") or "-"
        b.button(
            text=f"#{a['id']} · {title} · {status}",
            callback_data=f"{prefix}:{a['id']}",
        )
    b.adjust(1)
    return b.as_markup()


def waiters_list_kb(apps, page=0, per_page=10):
    """Kutuvchi nomzodlar ro'yxati. 10 tadan ko'p bo'lsa ◀️▶️ paginatsiya chiqadi."""
    b = InlineKeyboardBuilder()
    pages = max(1, (len(apps) + per_page - 1) // per_page)
    page = max(0, min(page, pages - 1))
    for a in apps[page * per_page:(page + 1) * per_page]:
        name = a.get("full_name") or "Nomzod"
        pos = a.get("vacancy_title") or a.get("position") or "-"
        b.row(InlineKeyboardButton(
            text=f"⏳ {name} · {pos}", callback_data=f"appview:{a['id']}"
        ))
    if pages > 1:
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton(
                text="◀️ Oldingi", callback_data=f"waitpage:{page - 1}"))
        nav.append(InlineKeyboardButton(
            text=f"{page + 1}/{pages}", callback_data="waitnoop"))
        if page < pages - 1:
            nav.append(InlineKeyboardButton(
                text="Keyingi ▶️", callback_data=f"waitpage:{page + 1}"))
        b.row(*nav)
    return b.as_markup()


def vacancy_detail_kb(vid):
    b = InlineKeyboardBuilder()
    b.button(text="📝 Ariza topshirish", callback_data=f"apply:{vid}")
    b.button(text="⬅️ Orqaga", callback_data="vac_back")
    b.adjust(1)
    return b.as_markup()


def confirm_interview_kb(interview_id):
    b = InlineKeyboardBuilder()
    b.button(text="✅ Tasdiqlash", callback_data=f"iok:{interview_id}")
    b.button(text="🔄 Boshqa vaqt taklif qilish", callback_data=f"ire:{interview_id}")
    b.adjust(1)
    return b.as_markup()


# ---------------- HR PANEL ----------------
def hr_menu():
    b = ReplyKeyboardBuilder()
    b.button(text="📊 Dashboard")
    b.button(text="📥 Arizalar")
    b.button(text="⏳ Kutuvchilar")
    b.button(text="📅 Suhbatlar")
    b.button(text="⭐ Saralanganlar")
    b.button(text="💼 Vakansiyalar (HR)")
    b.button(text="🏷 Lavozimlar")
    b.button(text="👕 Forma nazorati")
    b.button(text="🎓 Diplom statistikasi")
    b.button(text="💊 Farmatsevtlar")
    b.button(text="📨 Rahbar so'rovlari")
    b.button(text="🧾 Xodim so'rovlari")
    b.button(text="❌ Rad etilgan murojaatlar")
    b.button(text="👥 Xodimlar")
    b.button(text=EMP_MANAGE_BTN)
    b.button(text="🔀 Filial almashtirish")
    b.button(text="🚫 Ishdan bo'shatish")
    b.button(text="📍 Davomat")
    b.button(text="🛌 Kunlik dam olish")
    b.button(text="⚙️ Davomat sozlamalari")
    b.button(text="🧪 Sinov muddati")
    b.button(text="💵 Avans")
    b.button(text="💵 Avans sozlamalari")
    b.button(text="💸 Maosh so'rovlari")
    b.button(text="🕒 Ish vaqti so'rovlari")
    b.button(text="🏢 Filial o'zgartirish so'rovlari")
    b.button(text="📢 Xabarnoma")
    b.button(text="🔐 Ishonch xabari")
    b.button(text="📊 Bildirishnoma statistika")
    b.button(text="🔍 Qidiruv")
    b.button(text="📊 Excel eksport")
    b.button(text="🏠 Asosiy menyu")
    b.adjust(2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2)
    return b.as_markup(resize_keyboard=True)


def rejected_requests_kb(apps, regs):
    """Rad etilgan arizalar va xodim so'rovlari — bitta inline ro'yxatda."""
    b = InlineKeyboardBuilder()
    for a in apps:
        name = a.get("full_name") or "Nomzod"
        pos = a.get("vacancy_title") or a.get("position") or "-"
        b.button(text=f"📄 #{a['id']} {name} · {pos}", callback_data=f"appview:{a['id']}")
    for r in regs:
        name = r.get("full_name") or "Xodim"
        pos = r.get("position") or "-"
        b.button(text=f"🧾 #{r['id']} {name} · {pos}", callback_data=f"rejreg:{r['id']}")
    b.adjust(1)
    return b.as_markup()


def probations_list_kb(probations, prefix="probview"):
    b = InlineKeyboardBuilder()
    for p in probations:
        mark = "🏁" if p.get("status") == "finished" else "🟢"
        b.button(
            text=f"{mark} {p.get('full_name') or '-'} · {p.get('branch_name') or '-'}",
            callback_data=f"{prefix}:{p['id']}",
        )
    b.adjust(1)
    return b.as_markup()


def applications_filter_kb():
    b = InlineKeyboardBuilder()
    b.button(text="🧭 Kanban", callback_data="apps:kanban")
    b.button(text="🔎 Keng filter", callback_data="apps:filter")
    b.button(text="🆕 Yangi", callback_data="apps:new")
    b.button(text="📅 Suhbatga", callback_data="apps:interview")
    b.button(text="✅ Qabul", callback_data="apps:accepted")
    b.button(text="❌ Rad", callback_data="apps:rejected")
    b.button(text="📋 Barchasi", callback_data="apps:all")
    b.adjust(2, 2, 2, 1)
    return b.as_markup()


def kanban_kb():
    b = InlineKeyboardBuilder()
    b.button(text="🆕 Yangi arizalar", callback_data="apps:new")
    b.button(text="📅 Suhbatdagilar", callback_data="apps:interview")
    b.button(text="✅ Qabul qilinganlar", callback_data="apps:accepted")
    b.button(text="❌ Rad etilganlar", callback_data="apps:rejected")
    b.button(text="🔎 Keng filter", callback_data="apps:filter")
    b.adjust(2, 2, 1)
    return b.as_markup()


def application_advanced_filter_kb(branches):
    b = InlineKeyboardBuilder()
    b.button(text="🆕 Status: yangi", callback_data="fltstatus:new")
    b.button(text="📅 Status: suhbat", callback_data="fltstatus:interview")
    b.button(text="✅ Status: qabul", callback_data="fltstatus:accepted")
    b.button(text="❌ Status: rad", callback_data="fltstatus:rejected")
    b.button(text="👕 Forma bor", callback_data="fltuniform:yes")
    b.button(text="👕 Forma yo'q", callback_data="fltuniform:no")
    b.button(text="➖ Forma noma'lum", callback_data="fltuniform:unknown")
    b.button(text="💼 Lavozim yozish", callback_data="flttxt:position")
    b.button(text="🌆 Shahar yozish", callback_data="flttxt:city")
    b.button(text="📍 Tuman yozish", callback_data="flttxt:district")
    for br in branches:
        b.button(text=f"🏢 {br['name']}", callback_data=f"fltbr:{br['id']}")
    b.adjust(2)
    return b.as_markup()


def application_actions_kb(aid, favorite=False):
    b = InlineKeyboardBuilder()
    b.button(text="👁 Batafsil", callback_data=f"appview:{aid}")
    b.button(text="📅 Suhbatga chaqirish", callback_data=f"appint:{aid}")
    b.button(text="✅ Ishga qabul", callback_data=f"apphire:{aid}")
    b.button(text="🧪 Sinovga qabul", callback_data=f"apptrial:{aid}")
    b.button(text="🎓 O'rganuvchi qilib qabul", callback_data=f"applearn:{aid}")
    b.button(text="💰 Oylik taklif qilish", callback_data=f"appsal:{aid}")
    b.button(text="⏳ Kutish (bazaga qo'shish)", callback_data=f"appwait:{aid}")
    b.button(text="❌ Rad etish", callback_data=f"apprej:{aid}")
    b.button(text="📝 Izoh qoldirish", callback_data=f"appcom:{aid}")
    b.button(text="💬 Nomzodga xabar", callback_data=f"appmsg:{aid}")
    fav_label = "⭐ Saralangan ✓" if favorite else "⭐ Saralashga qo'shish"
    b.button(text=fav_label, callback_data=f"appfav:{aid}")
    b.adjust(1, 2, 2, 2, 2, 2)
    return b.as_markup()


def candidate_salary_offer_kb(aid):
    """Nomzodga: HR taklif qilgan oylikni tasdiqlash yoki boshqa summa taklif qilish."""
    b = InlineKeyboardBuilder()
    b.button(text="✅ Tasdiqlash", callback_data=f"candsal_ok:{aid}")
    b.button(text="✏️ Boshqa summa", callback_data=f"candsal_other:{aid}")
    b.adjust(2)
    return b.as_markup()


def hr_salary_offer_kb(aid):
    """HR ga: nomzod taklif qilgan boshqa summani tasdiqlash yoki qarshi taklif berish."""
    b = InlineKeyboardBuilder()
    b.button(text="✅ Tasdiqlash", callback_data=f"hrsal_ok:{aid}")
    b.button(text="✏️ Boshqa summa", callback_data=f"hrsal_other:{aid}")
    b.adjust(2)
    return b.as_markup()


# ---------------- MA'LUMOTLARNI YANGILASH (admin kampaniyasi) ----------------
def profile_update_scope_kb():
    """Kimdan ma'lumot yangilash so'ralsin: hammadan / filialdan / bitta xodimdan."""
    b = InlineKeyboardBuilder()
    b.button(text="👥 Barcha xodimlardan", callback_data="profupd_scope:all")
    b.button(text="🏢 Filial bo'yicha", callback_data="profupd_scope:branch")
    b.button(text="👤 Bitta xodimdan", callback_data="profupd_scope:one")
    b.button(text="❌ Bekor qilish", callback_data="profupd_no")
    b.adjust(1)
    return b.as_markup()


def profile_update_branch_kb(branches):
    """Qaysi filial xodimlaridan yangilash so'ralsin?"""
    b = InlineKeyboardBuilder()
    for br in branches:
        b.button(text=f"🏢 {br['name']}", callback_data=f"profupd_br:{br['id']}")
    b.button(text="❌ Bekor qilish", callback_data="profupd_no")
    b.adjust(1)
    return b.as_markup()


def profile_update_employee_kb(profiles):
    """Aynan qaysi xodimdan yangilash so'ralsin?"""
    b = InlineKeyboardBuilder()
    for p in profiles:
        name = p.get("full_name") or "Nomsiz"
        branch = p.get("branch_name") or "filialsiz"
        b.button(text=f"👤 {name} · {branch}", callback_data=f"profupd_emp:{p['user_id']}")
    b.button(text="❌ Bekor qilish", callback_data="profupd_no")
    b.adjust(1)
    return b.as_markup()


def profile_update_confirm_kb(scope="all", ref_id=None):
    """Adminga: tanlangan qamrovda ma'lumot yangilashni so'raymizmi?"""
    b = InlineKeyboardBuilder()
    payload = f"profupd_yes:{scope}" + (f":{ref_id}" if ref_id else "")
    b.button(text="✅ Ha", callback_data=payload)
    b.button(text="❌ Yo'q", callback_data="profupd_no")
    b.adjust(2)
    return b.as_markup()


def profile_update_start_kb():
    """Xodimga keladigan xabar ostidagi «Yangilash» tugmasi."""
    b = InlineKeyboardBuilder()
    b.button(text="🔄 Yangilash", callback_data="profupd_start")
    b.adjust(1)
    return b.as_markup()


# ---------------- HR GA MUROJAAT (xodim) ----------------
def hr_request_menu_kb():
    """Xodim «📩 HR ga murojaat» tugmasini bosganda chiqadigan yo'nalishlar."""
    b = InlineKeyboardBuilder()
    b.button(text="🕒 Ish soatini o'zgartirish", callback_data="hrreq:hours")
    b.button(text="💸 Maoshni oshirishni so'rash", callback_data="hrreq:salary")
    b.button(text="🏢 Boshqa filialga ko'chirish", callback_data="hrreq:branch")
    b.button(text="✉️ Boshqa masalada", callback_data="hrreq:other")
    b.adjust(1)
    return b.as_markup()


# ---------------- BOSHQA FILIALGA O'TISH SO'ROVI (xodim ⇄ HR) ----------------
def transfer_start_confirm_kb():
    """Xodimga: rostan ham boshqa filialga o'tish so'rovini yubormoqchimisiz?"""
    b = InlineKeyboardBuilder()
    b.button(text="✅ Ha", callback_data="btr_yes")
    b.button(text="❌ Yo'q", callback_data="btr_no")
    b.adjust(2)
    return b.as_markup()


def transfer_branch_pick_kb(branches):
    """Xodimga: o'tmoqchi bo'lgan filialni tanlash (hozirgisi ro'yxatda bo'lmaydi)."""
    b = InlineKeyboardBuilder()
    for br in branches:
        b.button(text=f"🏢 {br['name']}", callback_data=f"btrbr:{br['id']}")
    b.button(text="❌ Bekor qilish", callback_data="btr_no")
    b.adjust(1)
    return b.as_markup()


def transfer_final_confirm_kb():
    """Xodimga: tanlangan filialni tasdiqlash yoki qayta tanlash."""
    b = InlineKeyboardBuilder()
    b.button(text="✅ Ha", callback_data="btr_ok")
    b.button(text="✏️ Tahrirlash", callback_data="btr_edit")
    b.adjust(2)
    return b.as_markup()


def hr_transfer_actions_kb(rid):
    """HR ga: filial o'zgartirish so'rovini tasdiqlash / bekor qilish / xabar yozish."""
    b = InlineKeyboardBuilder()
    b.button(text="✅ Tasdiqlash", callback_data=f"hrbtr_ok:{rid}")
    b.button(text="❌ Bekor qilish", callback_data=f"hrbtr_no:{rid}")
    b.button(text="✉️ Xodimga xabar yozish", callback_data=f"hrbtr_msg:{rid}")
    b.adjust(2, 1)
    return b.as_markup()


def emp_transfer_reply_kb(rid):
    """Xodimga: HR xabariga javob yozish."""
    b = InlineKeyboardBuilder()
    b.button(text="✍️ Javob yozish", callback_data=f"btr_reply:{rid}")
    b.adjust(1)
    return b.as_markup()


def branch_transfer_requests_list_kb(requests, prefix="btrview"):
    """HR paneli: ochiq filial o'zgartirish so'rovlari ro'yxati."""
    b = InlineKeyboardBuilder()
    for r in requests:
        b.button(
            text=(f"🏢 {r.get('full_name') or '-'} · "
                  f"{r.get('from_branch_name') or '-'} → {r.get('to_branch_name') or '-'}"),
            callback_data=f"{prefix}:{r['id']}",
        )
    b.adjust(1)
    return b.as_markup()


# ---------------- ISH VAQTINI O'ZGARTIRISH SO'ROVI (xodim ⇄ HR) ----------------
def work_hours_confirm_kb():
    """Xodim yozgan ish vaqtini: tasdiqlash / tahrirlash / bekor qilish."""
    b = InlineKeyboardBuilder()
    b.button(text="✅ Tasdiqlash", callback_data="wh_ok")
    b.button(text="✏️ Tahrirlash", callback_data="wh_edit")
    b.button(text="❌ Bekor qilish", callback_data="wh_cancel")
    b.adjust(2, 1)
    return b.as_markup()


def hr_work_hours_actions_kb(rid):
    """HR ga: ish vaqti so'rovini tasdiqlash / rad etish."""
    b = InlineKeyboardBuilder()
    b.button(text="✅ Tasdiqlash", callback_data=f"hrwh_ok:{rid}")
    b.button(text="❌ Rad etish", callback_data=f"hrwh_rej:{rid}")
    b.adjust(2)
    return b.as_markup()


def work_hour_requests_list_kb(requests, prefix="whview"):
    """HR paneli: ochiq ish vaqti so'rovlari ro'yxati."""
    b = InlineKeyboardBuilder()
    for r in requests:
        b.button(
            text=f"🕒 {r.get('full_name') or '-'} · {r.get('requested_hours') or '-'}",
            callback_data=f"{prefix}:{r['id']}",
        )
    b.adjust(1)
    return b.as_markup()


# ---------------- MAOSH OSHIRISH SO'ROVI (xodim ⇄ HR) ----------------
def raise_confirm_change_kb():
    """Xodimga: hozirgi maoshni o'zgartirishni xohlaysizmi?"""
    b = InlineKeyboardBuilder()
    b.button(text="✅ Ha", callback_data="raise_yes")
    b.button(text="❌ Yo'q", callback_data="raise_no")
    b.adjust(2)
    return b.as_markup()


def raise_amount_confirm_kb():
    """Xodim kiritgan summani: tasdiqlash / tahrirlash / bekor qilish.
    Summa FSM holatida saqlanadi (so'rov hali yaratilmagan bo'lishi mumkin)."""
    b = InlineKeyboardBuilder()
    b.button(text="✅ Tasdiqlash", callback_data="raise_amt_ok")
    b.button(text="✏️ Tahrirlash", callback_data="raise_amt_edit")
    b.button(text="❌ Bekor qilish", callback_data="raise_amt_cancel")
    b.adjust(2, 1)
    return b.as_markup()


def hr_raise_actions_kb(rid):
    """HR ga: xodim so'rovini tasdiqlash / taklif berish / rad etish."""
    b = InlineKeyboardBuilder()
    b.button(text="✅ Tasdiqlash", callback_data=f"hrraise_ok:{rid}")
    b.button(text="💬 Taklif berish", callback_data=f"hrraise_offer:{rid}")
    b.button(text="❌ Rad etish", callback_data=f"hrraise_rej:{rid}")
    b.adjust(2, 1)
    return b.as_markup()


def hr_raise_offer_confirm_kb(rid):
    """HR taklif summasini: tasdiqlash / tahrirlash / rad etish."""
    b = InlineKeyboardBuilder()
    b.button(text="✅ Tasdiqlash", callback_data=f"hrraise_sendoffer:{rid}")
    b.button(text="✏️ Tahrirlash", callback_data=f"hrraise_editoffer:{rid}")
    b.button(text="❌ Rad etish", callback_data=f"hrraise_rej:{rid}")
    b.adjust(2, 1)
    return b.as_markup()


def emp_raise_counter_kb(rid):
    """Xodimga: HR qarshi taklifini tasdiqlash yoki yangi summa taklif qilish."""
    b = InlineKeyboardBuilder()
    b.button(text="✅ Tasdiqlash", callback_data=f"empraise_ok:{rid}")
    b.button(text="💬 Taklif berish", callback_data=f"empraise_counter:{rid}")
    b.adjust(2)
    return b.as_markup()


def raise_requests_list_kb(requests):
    """HR paneli: ochiq maosh so'rovlari ro'yxati."""
    b = InlineKeyboardBuilder()
    for r in requests:
        b.button(
            text=f"💸 {r.get('full_name') or '-'} · {r.get('branch_name') or '-'}",
            callback_data=f"raiseview:{r['id']}",
        )
    b.adjust(1)
    return b.as_markup()


def hr_vacancies_kb():
    b = InlineKeyboardBuilder()
    b.button(text="➕ Vakansiya yaratish", callback_data="hrvac_new")
    b.button(text="📋 Ro'yxat / boshqarish", callback_data="hrvac_list")
    b.adjust(1)
    return b.as_markup()


def vacancy_manage_kb(vid, is_active):
    b = InlineKeyboardBuilder()
    b.button(text="✏️ Tahrirlash", callback_data=f"vedit:{vid}")
    if is_active:
        b.button(text="❌ Yopish", callback_data=f"vclose:{vid}")
    else:
        b.button(text="♻️ Qayta ochish", callback_data=f"vopen:{vid}")
    b.button(text="🗑 O'chirish", callback_data=f"vdel:{vid}")
    b.button(text="⬅️ Orqaga", callback_data="hrvac_list")
    b.adjust(2, 1, 1)
    return b.as_markup()


def vacancy_delete_confirm_kb(vid):
    b = InlineKeyboardBuilder()
    b.button(text="🗑 Ha, o'chirilsin", callback_data=f"vdelok:{vid}")
    b.button(text="⬅️ Bekor qilish", callback_data=f"vman:{vid}")
    b.adjust(1)
    return b.as_markup()


def vacancy_edit_fields_kb(vid):
    fields = [
        ("Lavozim nomi", "title"),
        ("Ish turi", "job_type"),
        ("Smena", "shift"),
        ("Oylik", "salary"),
        ("Ish vaqti", "work_time"),
        ("Talablar", "requirements"),
        ("Mas'uliyatlar", "responsibilities"),
        ("Ish sharoiti", "conditions"),
    ]
    b = InlineKeyboardBuilder()
    for label, f in fields:
        b.button(text=f"✏️ {label}", callback_data=f"vef:{vid}:{f}")
    b.button(text="⬅️ Orqaga", callback_data=f"vman:{vid}")
    b.adjust(2)
    return b.as_markup()


def trust_ack_kb(notice_id):
    """«Ishonch xabari» ostidagi «Ko'rib chiqdim» tugmasi (qabul qiluvchi bosadi)."""
    b = InlineKeyboardBuilder()
    b.button(text="✅ Ko'rib chiqdim", callback_data=f"trustack:{notice_id}")
    return b.as_markup()


def trust_ack_done_kb():
    """Tugma bosilgach ko'rsatiladigan tasdiq (qayta bosib bo'lmaydi)."""
    b = InlineKeyboardBuilder()
    b.button(text="✅ Ko'rib chiqildi", callback_data="trustnoop")
    return b.as_markup()


def trust_notices_list_kb(notices):
    """Bildirishnoma statistikasi — ishonch xabarlari ro'yxati (inline)."""
    b = InlineKeyboardBuilder()
    for n in notices:
        title = (n.get("title") or "Xabar").strip()
        if len(title) > 30:
            title = title[:30] + "…"
        seen = n.get("seen_count", 0)
        total = n.get("delivered", 0)
        b.button(
            text=f"📨 {title} · {seen}/{total} ✅",
            callback_data=f"trustst:{n['id']}",
        )
    b.adjust(1)
    return b.as_markup()


def broadcast_target_kb():
    b = InlineKeyboardBuilder()
    b.button(text="👥 Barchaga", callback_data="bc:all")
    b.button(text="👷 Barcha xodimlarga", callback_data="bc:staff")
    b.button(text="🧑‍💼 Nomzodlarga", callback_data="bc:candidate")
    b.button(text="🏢 Filial rahbarlariga", callback_data="bc:manager")
    b.button(text="🏬 Filial xodimlariga", callback_data="bc:branch")
    b.button(text="👤 Bitta xodimga", callback_data="bc:one")
    b.adjust(2, 2, 2)
    return b.as_markup()


def broadcast_branch_kb(branches, prefix="bcbr"):
    """Xabarnoma uchun filial tanlash (filialsiz varianti yo'q)."""
    b = InlineKeyboardBuilder()
    for br in branches:
        b.button(text=f"🏢 {br['name']}", callback_data=f"{prefix}:{br['id']}")
    b.button(text="⬅️ Orqaga", callback_data="bc:back")
    b.adjust(1)
    return b.as_markup()


def broadcast_employee_kb(profiles, branch_id):
    """Tanlangan filial xodimlari — bittasiga xabar yuborish uchun."""
    b = InlineKeyboardBuilder()
    for p in profiles:
        name = p.get("full_name") or str(p.get("tg_id"))
        pos = p.get("position") or p.get("role") or "-"
        b.button(text=f"👤 {name} · {pos}", callback_data=f"bcemp:{p['user_id']}")
    b.button(text="⬅️ Filialni qayta tanlash", callback_data="bc:one")
    b.adjust(1)
    return b.as_markup()


def search_field_kb():
    b = InlineKeyboardBuilder()
    b.button(text="👤 Ism", callback_data="srch:full_name")
    b.button(text="📞 Telefon", callback_data="srch:phone")
    b.button(text="🏢 Filial", callback_data="srch:branch")
    b.button(text="💼 Lavozim", callback_data="srch:vacancy")
    b.adjust(2, 2)
    return b.as_markup()


def yes_no_active_kb():
    b = InlineKeyboardBuilder()
    b.button(text="✅ Faol", callback_data="vac_active:1")
    b.button(text="⛔ Nofaol", callback_data="vac_active:0")
    b.adjust(2)
    return b.as_markup()


def branch_pick_kb(branches, prefix="pickbr"):
    b = InlineKeyboardBuilder()
    for br in branches:
        b.button(text=f"🏢 {br['name']}", callback_data=f"{prefix}:{br['id']}")
    b.button(text="➖ Filialsiz", callback_data=f"{prefix}:0")
    b.adjust(2)
    return b.as_markup()


def vacancies_manage_list_kb(vacancies, prefix="vman"):
    b = InlineKeyboardBuilder()
    for v in vacancies:
        status = "🟢" if v.get("is_active") else "🔴"
        branch = f" · {v['branch_name']}" if v.get("branch_name") else ""
        b.button(
            text=f"{status} #{v['id']} · {v['title']}{branch}",
            callback_data=f"{prefix}:{v['id']}",
        )
    b.adjust(1)
    return b.as_markup()


def employee_profiles_list_kb(profiles, prefix="empview", with_search=True,
                              search_cb=None):
    """Xodimlar ro'yxati. `with_search` — tepasida «🔍 Xodim qidirish» tugmasi.

    `search_cb` — qidiruv tugmasining callback'i. Berilmasa, panelga mos
    umumiy qidiruv (`empfind:<prefix>`) ishlatiladi — natija tugmalari shu
    panelning (prefix) kartochkasini ochadi."""
    b = InlineKeyboardBuilder()
    if with_search:
        b.button(
            text="🔍 Xodim qidirish (ism/username/ID)",
            callback_data=search_cb or f"empfind:{prefix}",
        )
    for p in profiles:
        role = p.get("role") or "xodim"
        branch = f" · {p['branch_name']}" if p.get("branch_name") else ""
        b.button(
            text=f"{p.get('full_name') or p.get('tg_id')} · {role}{branch}",
            callback_data=f"{prefix}:{p['user_id']}",
        )
    b.adjust(1)
    return b.as_markup()


# ---------------- XODIM QIDIRUVI ----------------
EMP_SEARCH_ROLES = [
    (ROLE_PHARMACIST, "💊 Farmatsevt"),
    (ROLE_MANAGER, "👨‍💼 Filial rahbari"),
    (ROLE_DIRECTOR, "👔 Direktor"),
    (ROLE_ACCOUNTANT, "🧮 Moliya bo'limi"),
    (ROLE_EMPLOYEE, "👷 Oddiy xodim"),
    (ROLE_HR, "🧑‍💼 HR"),
]


def employee_search_kb():
    """Xodim qidirish usullari."""
    b = InlineKeyboardBuilder()
    b.button(text="🔤 Ism / username / telefon", callback_data="empsrch:text")
    b.button(text="🏢 Filial bo'yicha", callback_data="empsrch:branch")
    b.button(text="💼 Lavozim bo'yicha", callback_data="empsrch:role")
    b.button(text="👥 Barcha xodimlar", callback_data="empsrch:all")
    b.adjust(1)
    return b.as_markup()


def employee_search_branch_kb(branches):
    b = InlineKeyboardBuilder()
    for br in branches:
        b.button(text=f"🏢 {br['name']}", callback_data=f"empsrchb:{br['id']}")
    b.button(text="⬅️ Orqaga", callback_data="empsrch")
    b.adjust(1)
    return b.as_markup()


def employee_search_role_kb():
    b = InlineKeyboardBuilder()
    for role, label in EMP_SEARCH_ROLES:
        b.button(text=label, callback_data=f"empsrchr:{role}")
    b.button(text="⬅️ Orqaga", callback_data="empsrch")
    b.adjust(1)
    return b.as_markup()


# ---------------- DIREKTOR «👥 FILIAL XODIMLARI» QIDIRUVI ----------------
def director_search_kb(show_branch=True):
    """Direktor xodimlarni qidirish usullari.
    `show_branch` — direktor bitta filialga biriktirilgan bo'lsa, filial
    tanlash ma'nosiz, shu sababli tugma ko'rsatilmaydi."""
    b = InlineKeyboardBuilder()
    b.button(text="🔤 Ism / username / telefon", callback_data="dirsrch:text")
    if show_branch:
        b.button(text="🏢 Filial bo'yicha", callback_data="dirsrch:branch")
    b.button(text="💼 Lavozim bo'yicha", callback_data="dirsrch:role")
    b.button(text="👥 Barcha xodimlar", callback_data="dirsrch:all")
    b.adjust(1)
    return b.as_markup()


def director_search_branch_kb(branches):
    b = InlineKeyboardBuilder()
    for br in branches:
        b.button(text=f"🏢 {br['name']}", callback_data=f"dirsrchb:{br['id']}")
    b.button(text="⬅️ Orqaga", callback_data="dirsrch:home")
    b.adjust(1)
    return b.as_markup()


def director_search_role_kb():
    b = InlineKeyboardBuilder()
    for role, label in EMP_SEARCH_ROLES:
        b.button(text=label, callback_data=f"dirsrchr:{role}")
    b.button(text="⬅️ Orqaga", callback_data="dirsrch:home")
    b.adjust(1)
    return b.as_markup()


def manager_requests_list_kb(requests, prefix="mrview"):
    b = InlineKeyboardBuilder()
    for r in requests:
        kind = "Xodim" if r.get("kind") == "vacancy" else "Texnik"
        title = r.get("title") or "So'rov"
        b.button(
            text=f"#{r['id']} · {kind} · {title} · {r.get('status') or '-'}",
            callback_data=f"{prefix}:{r['id']}",
        )
    b.adjust(1)
    return b.as_markup()


def fines_list_kb(fines, prefix="fineview"):
    b = InlineKeyboardBuilder()
    for fine in fines:
        b.button(
            text=f"#{fine['id']} · {fine['amount']} · {fine.get('created_at') or ''}",
            callback_data=f"{prefix}:{fine['id']}",
        )
    b.adjust(1)
    return b.as_markup()


def uniform_employee_kb(user_id, current_status=None):
    b = InlineKeyboardBuilder()
    if current_status != "yes":
        b.button(text="✅ Forma bor", callback_data=f"ufset:{user_id}:yes")
    if current_status != "no":
        b.button(text="❌ Forma yo'q", callback_data=f"ufset:{user_id}:no")
    b.adjust(2)
    return b.as_markup()


def pharmacist_manage_kb(user_id, uniform_status=None):
    b = InlineKeyboardBuilder()
    b.button(text="💰 Oylik belgilash", callback_data=f"phsal:{user_id}")
    b.button(text="💸 Jarima yozish", callback_data=f"phfine:{user_id}")
    b.button(text="📋 Jarimalar", callback_data=f"phfines:{user_id}")
    if uniform_status != "yes":
        b.button(text="👕 Forma berildi", callback_data=f"ufset:{user_id}:yes")
    else:
        b.button(text="👕 Forma yo'q deb belgilash", callback_data=f"ufset:{user_id}:no")
    b.adjust(1, 2, 1)
    return b.as_markup()


def staff_fire_kb(user_id):
    """Xodim profili tagida «Ishdan bo'shatish» tugmasi (rahbar/direktor)."""
    b = InlineKeyboardBuilder()
    b.button(text="🚫 Ishdan bo'shatish", callback_data=f"fire:{user_id}")
    b.adjust(1)
    return b.as_markup()


def termination_actions_kb(rid):
    """HR uchun: ishdan bo'shatish so'rovini tasdiqlash / rad etish."""
    b = InlineKeyboardBuilder()
    b.button(text="✅ Tasdiqlash", callback_data=f"tacc:{rid}")
    b.button(text="❌ Rad etish", callback_data=f"trej:{rid}")
    b.adjust(2)
    return b.as_markup()


# ---- HR tashabbusli ishdan bo'shatish (filial -> xodim -> tasdiq) ----
def hr_fire_branch_kb(branches):
    """HR «Ishdan bo'shatish» — filiallar ro'yxati."""
    b = InlineKeyboardBuilder()
    for br in branches:
        b.button(text=f"🏢 {br['name']}", callback_data=f"hrfbr:{br['id']}")
    b.adjust(2)
    return b.as_markup()


def hr_fire_employees_kb(profiles):
    """Tanlangan filial xodimlari — bittasini bosib ishdan bo'shatish."""
    b = InlineKeyboardBuilder()
    for p in profiles:
        role = p.get("role") or "xodim"
        b.button(
            text=f"👤 {p.get('full_name') or p.get('tg_id')} · {role}",
            callback_data=f"hrfemp:{p['user_id']}",
        )
    b.adjust(1)
    return b.as_markup()


def hr_fire_start_kb(user_id):
    """Xodim profili tagida «Ishdan bo'shatish» tugmasi (HR)."""
    b = InlineKeyboardBuilder()
    b.button(text="🚫 Ishdan bo'shatish", callback_data=f"hrfask:{user_id}")
    b.adjust(1)
    return b.as_markup()


def hr_fire_confirm_kb(user_id):
    """«Ishdan bo'shatmoqchimisiz?» — tasdiqlash / rad etish."""
    b = InlineKeyboardBuilder()
    b.button(text="✅ Ha, ishdan bo'shatish", callback_data=f"hrfyes:{user_id}")
    b.button(text="❌ Yo'q, bekor qilish", callback_data=f"hrfno:{user_id}")
    b.adjust(1)
    return b.as_markup()


def manager_request_actions_kb(request_id, kind):
    b = InlineKeyboardBuilder()
    if kind == "vacancy":
        b.button(text="✅ Vakansiya ochish", callback_data=f"mracc:{request_id}")
    else:
        b.button(text="✅ Qabul qilindi", callback_data=f"mracc:{request_id}")
    b.button(text="❌ Yopish", callback_data=f"mrclose:{request_id}")
    b.adjust(1)
    return b.as_markup()


# ---- Filial rahbari vakansiya (xodim kerak) so'rovi ----
MGR_SHIFT_MORNING = "☀️ Ertalabki smena (08:00 - 17:00)"
MGR_SHIFT_EVENING = "🌙 Kechki smena (14:00 - 00:00)"
MGR_VAC_SKIP = "⏭️ O'tkazib yuborish"


def manager_vacancy_position_kb(positions=None):
    b = ReplyKeyboardBuilder()
    for label, _role, _pos in staff_role_options(positions):
        b.button(text=label)
    b.button(text=CANCEL_BTN)
    b.adjust(2)
    return b.as_markup(resize_keyboard=True, one_time_keyboard=True)


def manager_vacancy_shift_kb():
    return _choices([MGR_SHIFT_MORNING, MGR_SHIFT_EVENING], row=1)


# Vakansiyaga qanday xodim kerak: erkak / ayol / ikkalasi ham
MGR_GENDER_MALE = "👨 Erkak"
MGR_GENDER_FEMALE = "👩 Ayol"
MGR_GENDER_ANY = "👥 Ikkalasi ham"

MGR_GENDER_VALUES = {
    MGR_GENDER_MALE: "male",
    MGR_GENDER_FEMALE: "female",
    MGR_GENDER_ANY: "any",
}


def manager_vacancy_gender_kb():
    return _choices(
        [MGR_GENDER_MALE, MGR_GENDER_FEMALE, MGR_GENDER_ANY], row=2
    )


def manager_vacancy_skip_kb():
    b = ReplyKeyboardBuilder()
    b.button(text=MGR_VAC_SKIP)
    b.button(text=CANCEL_BTN)
    b.adjust(1)
    return b.as_markup(resize_keyboard=True, one_time_keyboard=True)


def manager_vacancy_confirm_kb():
    b = InlineKeyboardBuilder()
    b.button(text="✅ Tasdiqlab HR ga yuborish", callback_data="mgrvac_confirm")
    b.button(text="❌ Bekor qilish", callback_data="mgrvac_cancel")
    b.adjust(1)
    return b.as_markup()


def manager_my_vacancies_kb(vacancies, prefix="mymgrvac"):
    b = InlineKeyboardBuilder()
    for v in vacancies:
        if v.get("filled"):
            mark = "✅ to'ldi"
        elif v.get("is_active"):
            mark = "🟢 faol"
        else:
            mark = "🔴 yopiq"
        b.button(
            text=f"{mark} · {v.get('title') or '-'} ({v.get('staff_count') or '-'})",
            callback_data=f"{prefix}:{v['id']}",
        )
    b.adjust(1)
    return b.as_markup()


def manager_vacancy_finish_kb(vid):
    b = InlineKeyboardBuilder()
    b.button(text="✅ Yakunlash (hodimlar soni to'ldi)", callback_data=f"mgrvacfin:{vid}")
    b.adjust(1)
    return b.as_markup()


def manager_menu():
    b = ReplyKeyboardBuilder()
    b.button(text="➕ Xodim kerak")
    b.button(text="📢 Mening vakansiyalarim")
    b.button(text="🔧 Texnik nosozlik")
    b.button(text="👥 Filial xodimlari")
    b.button(text="📊 Bugungi davomat")
    b.button(text="📊 Filial statistikasi")
    b.button(text="📍 Davomat")
    b.button(text="⏰ Kech/erta hisobot")
    b.button(text="⏸ Tanaffus hisoboti")
    b.button(text="👕 Formasi yo'q xodimlar")
    b.button(text="📋 Filial arizalari")
    b.button(text="🛌 Dam olish so'rovlari")
    b.button(text="📋 Mening so'rovlarim")
    b.button(text="💬 HR ga xabar")
    b.button(text="🏠 Asosiy menyu")
    b.adjust(2, 2, 2, 2, 2, 2, 2, 1)
    return b.as_markup(resize_keyboard=True)


def pharmacist_menu():
    b = ReplyKeyboardBuilder()
    b.button(text="📊 Mening profilim")
    b.button(text="💸 Jarimalarim")
    b.button(text="🏠 Asosiy menyu")
    b.adjust(1)
    return b.as_markup(resize_keyboard=True)


def director_menu():
    b = ReplyKeyboardBuilder()
    b.button(text="📊 Direktor statistikasi")
    b.button(text="👥 Xodimlar statistikasi")
    b.button(text="🎓 Diplom statistikasi")
    b.button(text="👥 Filial xodimlari")
    b.button(text="🏢 Filiallar kesimi")
    b.button(text="📥 Arizalar kesimi")
    b.button(text="📍 Davomat")
    b.button(text="⏰ Kech/erta hisobot")
    b.button(text="⏸ Tanaffus hisoboti")
    b.button(text="🏆 Filiallar reytingi")
    b.button(text="📈 Taqqoslash")
    b.button(text="📑 Hisobot (Excel)")
    b.button(text="🏠 Asosiy menyu")
    b.adjust(2, 2, 2, 2, 2, 2, 1)
    return b.as_markup(resize_keyboard=True)


def director_application_status_kb():
    b = InlineKeyboardBuilder()
    b.button(text="🆕 Yangi", callback_data="dirapps:new")
    b.button(text="📅 Suhbat", callback_data="dirapps:interview")
    b.button(text="✅ Qabul", callback_data="dirapps:accepted")
    b.button(text="❌ Rad", callback_data="dirapps:rejected")
    b.button(text="📋 Barchasi", callback_data="dirapps:all")
    b.adjust(2, 2, 1)
    return b.as_markup()


# ---------------- ADMIN PANEL ----------------
def admin_menu():
    b = ReplyKeyboardBuilder()
    b.button(text="📊 Statistika")
    b.button(text="🏢 Filiallar")
    b.button(text="📢 Kanallar")
    b.button(text="👥 Adminlar")
    b.button(text="🧑‍💼 HR xodimlari")
    b.button(text="🎭 Rollar")
    b.button(text="👤 Foydalanuvchilar")
    b.button(text="💼 Vakansiyalar (Admin)")
    b.button(text="🏷 Lavozimlar")
    b.button(text="📢 Xabarnoma")
    b.button(text="📤 Eksport")
    b.button(text="⚙️ Sozlamalar")
    b.button(text="💵 Avans sozlamalari")
    b.button(text="🧾 Audit log")
    b.button(text=PROFILE_UPDATE_BTN)
    b.button(text=EMP_MANAGE_BTN)
    b.button(text="🔀 Filial almashtirish")
    b.button(text="🏠 Asosiy menyu")
    b.adjust(2, 2, 2, 2, 2, 2, 2, 2, 2)
    return b.as_markup(resize_keyboard=True)


def export_kb(scope="admin"):
    b = InlineKeyboardBuilder()
    b.button(text="📄 Arizalar (Excel)", callback_data="exp:apps")
    if scope == "admin":
        b.button(text="👥 Foydalanuvchilar (Excel)", callback_data="exp:users")
    b.button(text="📊 Umumiy hisobot (Excel)", callback_data="exp:report")
    b.adjust(1)
    return b.as_markup()


def users_list_kb(users, prefix="usrview"):
    b = InlineKeyboardBuilder()
    for u in users:
        mark = "🚫 " if u.get("blocked") else ""
        name = u.get("full_name") or u.get("username") or u.get("tg_id")
        b.button(text=f"{mark}{name} · {u.get('role') or '-'}", callback_data=f"{prefix}:{u['tg_id']}")
    b.adjust(1)
    return b.as_markup()


def user_manage_kb(tg_id, blocked=False):
    b = InlineKeyboardBuilder()
    if blocked:
        b.button(text="✅ Blokdan chiqarish", callback_data=f"usrunblock:{tg_id}")
    else:
        b.button(text="🚫 Bloklash", callback_data=f"usrblock:{tg_id}")
    b.button(text="🎭 Rol berish", callback_data=f"usrrole:{tg_id}")
    b.adjust(1)
    return b.as_markup()


def admin_settings_kb(require_sub=True, secret_channel=None, match_threshold=60,
                      vacancy_channel=None, candidate_channel=None,
                      interview_channel=None):
    b = InlineKeyboardBuilder()
    if require_sub:
        b.button(text="📢 Majburiy obuna: 🟢 YOQILGAN", callback_data="setsub:off")
    else:
        b.button(text="📢 Majburiy obuna: 🔴 O'CHIQ", callback_data="setsub:on")
    b.button(text="✍️ Xush kelibsiz matnini o'zgartirish", callback_data="setwelcome")
    b.button(text="♻️ Xush kelibsiz matnini tiklash", callback_data="setwelcome_reset")
    if secret_channel:
        b.button(text="🔒 Maxfiy kanal: 🟢 ULANGAN (o'zgartirish)", callback_data="setsecret")
        b.button(text="🗑 Maxfiy kanalni uzish", callback_data="setsecret_clear")
    else:
        b.button(text="🔒 Maxfiy kanal: 🔴 ULANMAGAN (ulash)", callback_data="setsecret")
    if vacancy_channel:
        b.button(text="📣 Vakansiya kanali: 🟢 ULANGAN (o'zgartirish)", callback_data="setvac")
        b.button(text="🗑 Vakansiya kanalini uzish", callback_data="setvac_clear")
    else:
        b.button(text="📣 Vakansiya kanali: 🔴 ULANMAGAN (ulash)", callback_data="setvac")
    if candidate_channel:
        b.button(text="📇 Nomzodlar kanali: 🟢 ULANGAN (o'zgartirish)", callback_data="setcand")
        b.button(text="🗑 Nomzodlar kanalini uzish", callback_data="setcand_clear")
    else:
        b.button(text="📇 Nomzodlar kanali: 🔴 ULANMAGAN (ulash)", callback_data="setcand")
    if interview_channel:
        b.button(text="🗣 Suhbat kanali: 🟢 ULANGAN (o'zgartirish)", callback_data="setint")
        b.button(text="🗑 Suhbat kanalini uzish", callback_data="setint_clear")
    else:
        b.button(text="🗣 Suhbat kanali: 🔴 ULANMAGAN (ulash)", callback_data="setint")
    b.button(text=f"🎯 Moslik chegarasi: {match_threshold}%", callback_data="setmatch")
    b.adjust(1)
    return b.as_markup()


def interviews_list_kb(interviews, prefix="intview"):
    b = InlineKeyboardBuilder()
    att_marks = {"came": "✅", "absent": "❌"}
    conf_marks = {"pending": "🟡", "confirmed": "☑️", "reschedule": "🔄"}
    for i in interviews:
        # Kelish belgilangan bo'lsa uni, aks holda nomzod javobini ko'rsatamiz
        mark = att_marks.get(i.get("attendance")) or conf_marks.get(i.get("status"), "📅")
        when = f"{i.get('date') or '-'} {i.get('time') or ''}".strip()
        b.button(
            text=f"{mark} {i.get('full_name') or '-'} · {when}",
            callback_data=f"{prefix}:{i['id']}",
        )
    b.adjust(1)
    return b.as_markup()


def interview_attendance_kb(iid, aid, attendance=None):
    """Suhbat kartochkasi ostidagi tugmalar.

    Kelish belgilanmagan bo'lsa: «✅ Keldi» / «❌ Kelmadi».
    «Keldi» belgilangach — keyingi bosqich: «✅ Ishga qabul» / «❌ Rad etish»."""
    b = InlineKeyboardBuilder()
    if attendance == "came":
        b.button(text="✅ Keldi ✓", callback_data=f"intcame:{iid}")
        b.button(text="↩️ Kelmadi deb o'zgartirish", callback_data=f"intabsent:{iid}")
        b.button(text="✅ Ishga qabul", callback_data=f"apphire:{aid}")
        b.button(text="🧪 Sinovga qabul", callback_data=f"apptrial:{aid}")
        b.button(text="❌ Rad etish", callback_data=f"apprej:{aid}")
        b.button(text="👁 Batafsil ariza", callback_data=f"appview:{aid}")
        b.adjust(2, 2, 1, 1)
    elif attendance == "absent":
        b.button(text="❌ Kelmadi ✓", callback_data=f"intabsent:{iid}")
        b.button(text="↩️ Keldi deb o'zgartirish", callback_data=f"intcame:{iid}")
        b.button(text="👁 Batafsil ariza", callback_data=f"appview:{aid}")
        b.adjust(2, 1)
    else:
        b.button(text="✅ Keldi", callback_data=f"intcame:{iid}")
        b.button(text="❌ Kelmadi", callback_data=f"intabsent:{iid}")
        b.button(text="👁 Batafsil ariza", callback_data=f"appview:{aid}")
        b.adjust(2, 1)
    return b.as_markup()


def director_app_actions_kb(aid):
    b = InlineKeyboardBuilder()
    b.button(text="💬 Izoh qoldirish", callback_data=f"dircom:{aid}")
    b.adjust(1)
    return b.as_markup()


def channels_manage_kb(channels):
    b = InlineKeyboardBuilder()
    b.button(text="➕ Kanal qo'shish", callback_data="ch_add")
    for ch in channels:
        status = "🟢" if ch["active"] else "🔴"
        b.button(
            text=f"{status} {ch['title'] or ch['chat_id']} | almashtirish",
            callback_data=f"ch_tog:{ch['id']}",
        )
        b.button(text="🗑", callback_data=f"ch_del:{ch['id']}")
    b.adjust(1)
    return b.as_markup()


def branches_root_kb():
    """Admin «🏢 Filiallar» — ikki yo'nalish: tahrirlash / xodimlar kesimi."""
    b = InlineKeyboardBuilder()
    b.button(text="✏️ Filial tahrirlash", callback_data="brroot:edit")
    b.button(text="👥 Filial xodimlari bo'yicha ko'rish", callback_data="brroot:staff")
    b.adjust(1)
    return b.as_markup()


# ================= XODIM MA'LUMOTLARINI O'ZGARTIRISH (admin/HR) =================
# Oqim: qidiruv usuli -> filial/ism -> xodim -> profil -> rol/filial/maqom o'zgartirish
def emp_manage_entry_kb():
    """«🛠 Ma'lumotlarni o'zgartirish» — qidiruv usuli."""
    b = InlineKeyboardBuilder()
    b.button(text="🏢 Filial bo'yicha", callback_data="emm:branch")
    b.button(text="🔤 Ism / username / telefon", callback_data="emm:text")
    b.button(text="👥 Barcha xodimlar", callback_data="emm:all")
    b.adjust(1)
    return b.as_markup()


def emp_manage_branch_kb(branches):
    """Filial tanlash (xodim tahrirlash oqimi uchun)."""
    b = InlineKeyboardBuilder()
    for br in branches:
        b.button(text=f"🏢 {br['name']}", callback_data=f"emmbr:{br['id']}")
    b.button(text="⬅️ Orqaga", callback_data="emm:home")
    b.adjust(1)
    return b.as_markup()


def emp_manage_list_kb(profiles, prefix="emmemp"):
    """Xodimlar ro'yxati — filial rahbari (👑) ro'yxat boshida ajratiladi."""
    b = InlineKeyboardBuilder()
    for p in profiles:
        role = p.get("role")
        if role == ROLE_MANAGER:
            mark = "👑"
        elif role == ROLE_DIRECTOR:
            mark = "👔"
        else:
            mark = "👤"
        name = p.get("full_name") or p.get("tg_id")
        b.button(text=f"{mark} {name}", callback_data=f"{prefix}:{p['user_id']}")
    b.button(text="⬅️ Orqaga", callback_data="emm:home")
    b.adjust(1)
    return b.as_markup()


def emp_manage_edit_kb(uid):
    """Bitta xodim kartochkasi ostidagi tahrirlash tugmalari."""
    b = InlineKeyboardBuilder()
    b.button(text="✏️ Ma'lumotni tahrirlash", callback_data=f"emmedit:{uid}")
    b.button(text="🎭 Rolni almashtirish", callback_data=f"emmrole:{uid}")
    b.button(text="🏢 Filialni almashtirish", callback_data=f"emmbranch:{uid}")
    b.button(text="🏷 Maqomni belgilash", callback_data=f"emmstatus:{uid}")
    b.button(text="🔄 Yangilashni so'rash (xodim o'zi)", callback_data=f"emmreqfresh:{uid}")
    b.adjust(1)
    return b.as_markup()


# Tahrirlanadigan maydonlar: (kalit, tugma matni, so'rov matni)
# kalit «name» / «phone» — users jadvali; «photo» — rasm; qolganlari employee_profiles.
EMP_EDIT_FIELDS = [
    ("photo", "🖼 Rasm", "🖼 Xodimning yangi rasmini yuboring:"),
    ("name", "👤 Ism familiya", "👤 Yangi ism familiyani yozing:"),
    ("phone", "📱 Telefon", "📱 Yangi telefon raqamni yozing (masalan +998901234567):"),
    ("position", "💼 Lavozim", "💼 Yangi lavozimni yozing:"),
    ("birth_date", "📅 Tug'ilgan sana", "📅 Tug'ilgan sanani yozing (kun.oy.yil):"),
    ("address", "📍 Manzil", "📍 Yangi manzilni yozing:"),
    ("work_hours", "🕒 Ish vaqti", "🕒 Ish vaqtini yozing (masalan 08:00 - 17:00):"),
    ("rest_day", "🛌 Dam olish kuni", "🛌 Dam olish kunini yozing (masalan Yakshanba):"),
    ("monthly_salary", "💰 Oylik", "💰 Oylik miqdorini yozing:"),
    ("education", "🎓 Ma'lumoti", "🎓 Ma'lumoti / diplomini yozing:"),
    ("since", "⏳ Gulnora Farmda", "⏳ Necha yildan beri ishlashini yozing:"),
    ("extra_info", "🧩 Qo'shimcha", "🧩 Qo'shimcha ma'lumotni yozing:"),
]

EMP_EDIT_PROMPTS = {k: prompt for k, _label, prompt in EMP_EDIT_FIELDS}


def emp_manage_field_kb(uid):
    """«✏️ Tahrirlash» — har bir maydon uchun alohida tugma."""
    b = InlineKeyboardBuilder()
    for key, label, _prompt in EMP_EDIT_FIELDS:
        b.button(text=label, callback_data=f"emmf:{uid}:{key}")
    b.button(text="⬅️ Orqaga", callback_data=f"emmemp:{uid}")
    b.adjust(2)
    return b.as_markup()


# Ma'lumot (education) tanlash tugmalari — qo'lda yozish o'rniga
EDUCATION_OPTIONS = [
    "🎓 Oliy farmatsevt",
    "🕗 Tugallanmagan oliy farmatsevt",
    "📘 O'rta maxsus farmatsevt",
    "🕓 Tugallanmagan o'rta maxsus",
    "🎓 Oliy — boshqa soha",
    "🕗 Tugallanmagan oliy — boshqa soha",
    "📗 Umumiy o'rta ta'lim",
    "❌ Diplom yo'q",
]


def emp_manage_education_kb(uid):
    """Xodim ma'lumotini (oliy/o'rta/farmatsevt...) tugma orqali tanlash."""
    b = InlineKeyboardBuilder()
    for i, opt in enumerate(EDUCATION_OPTIONS):
        b.button(text=opt, callback_data=f"emmedu:{uid}:{i}")
    b.button(text="⬅️ Orqaga", callback_data=f"emmedit:{uid}")
    b.adjust(1)
    return b.as_markup()


# Rol tanlash — o'rganuvchi/sinov maqom sifatida (rolni o'zgartirmaydi)
EMP_MANAGE_ROLES = [
    (ROLE_PHARMACIST, "💊 Farmatsevt"),
    (ROLE_MANAGER, "🏢 Filial rahbari"),
    (ROLE_DIRECTOR, "👔 Direktor"),
    (ROLE_ACCOUNTANT, "🧮 Moliya bo'limi"),
    (ROLE_IT, "🖥 IT xodim"),
    (ROLE_HR, "🧑‍💼 HR"),
    (ROLE_EMPLOYEE, "👷 Oddiy xodim"),
]


def emp_manage_role_kb(uid):
    b = InlineKeyboardBuilder()
    for role, label in EMP_MANAGE_ROLES:
        b.button(text=label, callback_data=f"emmsetrole:{uid}:{role}")
    b.button(text="⬅️ Orqaga", callback_data=f"emmemp:{uid}")
    b.adjust(1)
    return b.as_markup()


def emp_manage_status_kb(uid):
    """Xodim maqomi: doimiy / sinovda / o'rganuvchi."""
    b = InlineKeyboardBuilder()
    b.button(text="🟢 Doimiy xodim", callback_data=f"emmsetstatus:{uid}:regular")
    b.button(text="🧪 Sinovda", callback_data=f"emmsetstatus:{uid}:trial")
    b.button(text="🎓 O'rganuvchi", callback_data=f"emmsetstatus:{uid}:learner")
    b.button(text="⬅️ Orqaga", callback_data=f"emmemp:{uid}")
    b.adjust(1)
    return b.as_markup()


def emp_manage_branch_pick_kb(uid, branches):
    b = InlineKeyboardBuilder()
    for br in branches:
        b.button(text=f"🏢 {br['name']}", callback_data=f"emmsetbr:{uid}:{br['id']}")
    b.button(text="⬅️ Orqaga", callback_data=f"emmemp:{uid}")
    b.adjust(1)
    return b.as_markup()


def branches_manage_kb(branches):
    b = InlineKeyboardBuilder()
    b.button(text="➕ Filial qo'shish", callback_data="br_add")
    b.button(text="📍 Koordinatalarni sozlash", callback_data="br_locmenu")
    for br in branches:
        geo = "📍" if br.get("latitude") is not None else "❌"
        b.button(text=f"✏️ {geo} {br['name']}", callback_data=f"br_edit:{br['id']}")
        b.button(text="🗑", callback_data=f"br_del:{br['id']}")
    b.adjust(2)
    return b.as_markup()


def admins_manage_kb(admins):
    b = InlineKeyboardBuilder()
    b.button(text="➕ Admin qo'shish", callback_data="adm_add")
    for a in admins:
        b.button(
            text=f"🗑 {a['full_name'] or a['tg_id']}",
            callback_data=f"adm_del:{a['tg_id']}",
        )
    b.adjust(1)
    return b.as_markup()


def hrs_manage_kb(hrs):
    b = InlineKeyboardBuilder()
    b.button(text="➕ HR qo'shish", callback_data="hr_add")
    for h in hrs:
        b.button(
            text=f"🗑 {h['full_name'] or h['tg_id']}",
            callback_data=f"hr_del:{h['tg_id']}",
        )
    b.adjust(1)
    return b.as_markup()


def roles_pick_kb():
    b = InlineKeyboardBuilder()
    b.button(text="👑 Administrator", callback_data="setrole:admin")
    b.button(text="🧑‍💼 HR", callback_data="setrole:hr")
    b.button(text="👔 Direktor", callback_data="setrole:director")
    b.button(text="🧮 Moliya bo'limi", callback_data="setrole:accountant")
    b.button(text="🖥 IT xodim", callback_data="setrole:it")
    b.button(text="🏢 Filial rahbari", callback_data="setrole:manager")
    b.button(text="💊 Farmatsevt", callback_data="setrole:pharmacist")
    b.button(text="👷 Oddiy xodim", callback_data="setrole:employee")
    b.button(text="🧑 Nomzod (default)", callback_data="setrole:candidate")
    b.adjust(1)
    return b.as_markup()


def role_branch_pick_kb(role, branches):
    """Xodim-tipidagi rol (rahbar/farmatsevt/xodim...) berilganda filial tanlash."""
    b = InlineKeyboardBuilder()
    for br in branches:
        b.button(text=f"🏢 {br['name']}", callback_data=f"rolebr:{role}:{br['id']}")
    b.button(text="➖ Filialsiz (o'zgarmasin)", callback_data=f"rolebr:{role}:0")
    b.adjust(1)
    return b.as_markup()


# ================= GULNORA FARM HODIMI (SELF-REGISTRATSIYA) =================
# Yo'nalish (rol) tugmalari — matn -> (role, position)
STAFF_ROLES = [
    ("💊 Farmatsevt", ROLE_PHARMACIST, "Farmatsevt"),
    ("👨‍💼 Filial rahbari", ROLE_MANAGER, "Filial rahbari"),
    ("👔 Direktor", ROLE_DIRECTOR, "Direktor"),
    ("🧮 Moliya bo'limi", ROLE_ACCOUNTANT, "Moliya bo'limi"),
    ("📦 Omborchi", ROLE_EMPLOYEE, "Omborchi"),
    ("🚚 Haydovchi", ROLE_EMPLOYEE, "Haydovchi"),
]


def staff_role_options(positions=None):
    """Standart STAFF_ROLES + admin «🏷 Lavozimlar»da qo'shgan lavozimlar.
    Har bir element — (label, role, position). Admin qo'shgan yangi yo'nalishlar
    oddiy xodim (ROLE_EMPLOYEE) sifatida maplanadi va davomat panelini oladi.
    Dublikat label (standart ro'yxatda bor bo'lsa) qayta qo'shilmaydi."""
    opts = list(STAFF_ROLES)
    seen = {label for label, _r, _p in opts}
    for name in (positions or []):
        if name in seen:
            continue
        seen.add(name)
        opts.append((name, ROLE_EMPLOYEE, name))
    return opts


def staff_role_kb(positions=None):
    b = ReplyKeyboardBuilder()
    for label, _role, _pos in staff_role_options(positions):
        b.button(text=label)
    b.button(text=CANCEL_BTN)
    b.adjust(2)
    return b.as_markup(resize_keyboard=True, one_time_keyboard=True)


# Smena tugmalari va ularga mos standart ish vaqti
STAFF_SHIFT_DAY = "☀️ Kunduzgi smena"
STAFF_SHIFT_NIGHT = "🌙 Kechki smena"
STAFF_SHIFT_DOUBLE = "🔄 Qo'sh smenali"
STAFF_HOURS_CUSTOM = "✏️ Boshqa vaqt (custom)"

# Smena -> (standart ish vaqti tugmasi matni, toza vaqt)
SHIFT_PRESETS = {
    STAFF_SHIFT_DAY: ("🕗 08:00 - 17:00", "08:00 - 17:00"),
    STAFF_SHIFT_NIGHT: ("🕑 14:00 - 00:00", "14:00 - 00:00"),
}


def staff_shift_kb():
    return _choices(
        [STAFF_SHIFT_DAY, STAFF_SHIFT_NIGHT, STAFF_SHIFT_DOUBLE], row=2
    )


def staff_work_hours_kb(shift=None):
    """Tanlangan smenaga qarab standart vaqt + custom tugmasi."""
    if shift == STAFF_SHIFT_DAY:
        options = [SHIFT_PRESETS[STAFF_SHIFT_DAY][0], STAFF_HOURS_CUSTOM]
    elif shift == STAFF_SHIFT_NIGHT:
        options = [SHIFT_PRESETS[STAFF_SHIFT_NIGHT][0], STAFF_HOURS_CUSTOM]
    elif shift == STAFF_SHIFT_DOUBLE:
        options = [
            SHIFT_PRESETS[STAFF_SHIFT_DAY][0],
            SHIFT_PRESETS[STAFF_SHIFT_NIGHT][0],
            STAFF_HOURS_CUSTOM,
        ]
    else:
        options = [
            SHIFT_PRESETS[STAFF_SHIFT_DAY][0],
            SHIFT_PRESETS[STAFF_SHIFT_NIGHT][0],
            STAFF_HOURS_CUSTOM,
        ]
    return _choices(options, row=2)


def staff_rest_day_kb(lang=None):
    return _group_kb("rest_day", row=2, lang=lang)


# ---------------- MA'LUMOT (DIPLOM) TURLARI ----------------
# Bitta ro'yxat — nomzod anketasi, xodim self-registratsiyasi va farmatsevt
# savolida bir xil variantlar chiqsin (avval har joyda boshqacha edi).
STAFF_NO_DIPLOMA = "❌ Diplom yo'q"
EDUCATION_OPTIONS = [
    "🎓 Oliy farmatsevt",
    "🕗 Tugallanmagan oliy farmatsevt",
    "📘 O'rta maxsus farmatsevt",
    "🕓 Tugallanmagan o'rta maxsus",
    "🎓 Oliy — boshqa soha",
    "🕗 Tugallanmagan oliy — boshqa soha",
    "📗 Umumiy o'rta ta'lim",
    STAFF_NO_DIPLOMA,
]
STAFF_EDUCATION = EDUCATION_OPTIONS  # eski nom — mos kelishi uchun qoldirilgan

# Diplomsiz hisoblanadigan javoblar statistika uchun `queries.NO_DIPLOMA_VALUES`
# da turadi — bu ro'yxatni o'zgartirsangiz, o'shanisini ham yangilang.


def staff_education_kb(lang=None):
    return _group_kb("education", row=1, lang=lang)


def apply_education_kb(lang=None):
    return _group_kb("education", row=1, lang=lang)


def staff_since_kb(lang=None):
    return _group_kb("since", row=2, lang=lang)


def staff_photo_kb(lang=None):
    b = ReplyKeyboardBuilder()
    b.button(text=cancel_text(lang))
    return b.as_markup(resize_keyboard=True, one_time_keyboard=True)


def staff_confirm_kb(update_mode=False):
    b = InlineKeyboardBuilder()
    b.button(
        text="✅ Ha, ma'lumotlarim yangilansin" if update_mode
        else "✅ Ha, HR panelga yuborilsin",
        callback_data="sreg_confirm",
    )
    b.button(text="❌ Bekor qilish", callback_data="sreg_cancel")
    b.adjust(1)
    return b.as_markup()


def staff_reg_actions_kb(rid):
    b = InlineKeyboardBuilder()
    b.button(text="✅ Tasdiqlash", callback_data=f"sracc:{rid}")
    b.button(text="❌ Rad etish", callback_data=f"srrej:{rid}")
    b.adjust(2)
    return b.as_markup()


def staff_regs_list_kb(regs, prefix="srview"):
    b = InlineKeyboardBuilder()
    for r in regs:
        b.button(
            text=f"#{r['id']} · {r.get('full_name') or '-'} · {r.get('position') or '-'} · {r.get('status') or '-'}",
            callback_data=f"{prefix}:{r['id']}",
        )
    b.adjust(1)
    return b.as_markup()


# ================= DAVOMAT (ATTENDANCE) =================
def break_stats_kb(scope="mgr"):
    """Tanaffus/joylashuv statistikasi uchun davr tanlash."""
    b = InlineKeyboardBuilder()
    b.button(text="📅 Bugun", callback_data=f"brk:{scope}:day")
    b.button(text="🗓 Hafta", callback_data=f"brk:{scope}:week")
    b.button(text="📆 Oy", callback_data=f"brk:{scope}:month")
    b.adjust(3)
    return b.as_markup()


def attendance_settings_kb(enabled, interval_hours):
    """HR: periodik joylashuv tekshiruvi sozlamalari."""
    b = InlineKeyboardBuilder()
    if enabled:
        b.button(text="🟢 Tekshiruv YOQILGAN (bosib o'chirish)", callback_data="attset:toggle")
    else:
        b.button(text="🔴 Tekshiruv O'CHIRILGAN (bosib yoqish)", callback_data="attset:toggle")
    for h in (1, 2, 3):
        mark = "✅ " if str(interval_hours) == str(h) else ""
        b.button(text=f"{mark}{h} soatda", callback_data=f"attset:int:{h}")
    b.adjust(1, 3)
    return b.as_markup()


def attendance_location_kb():
    b = ReplyKeyboardBuilder()
    b.button(text="📍 Joylashuvni yuborish", request_location=True)
    b.button(text=CANCEL_BTN)
    b.adjust(1)
    return b.as_markup(resize_keyboard=True, one_time_keyboard=True)


def attendance_reminder_kb(kind, lang=None):
    """Ish vaqti eslatmasi ostidagi tugma: «📍 Ishga keldim» (kind='in') yoki
    «🏁 Ishdan ketdim» (kind='out'). Tugma bosilsa — odatdagi davomat oqimi
    ishga tushadi. «🏠 Asosiy menyu» esa to'liq menyuni tiklaydi."""
    b = ReplyKeyboardBuilder()
    b.button(text=t("btn.checkin", lang) if kind == "in" else t("btn.checkout", lang))
    b.button(text=t("btn.main_menu", lang))
    b.adjust(1)
    return b.as_markup(resize_keyboard=True)


def attendance_report_kb(scope="hr"):
    """scope: hr | dir | mgr — davr tanlash."""
    b = InlineKeyboardBuilder()
    b.button(text="📅 Bugun", callback_data=f"att:{scope}:day")
    b.button(text="🗓 Hafta", callback_data=f"att:{scope}:week")
    b.button(text="📆 Oy", callback_data=f"att:{scope}:month")
    if scope != "mgr":
        b.button(text="🏢 Filiallar kesimi", callback_data=f"attbr:{scope}:day")
    b.adjust(3, 1)
    return b.as_markup()


def attendance_branch_period_kb(scope="hr"):
    b = InlineKeyboardBuilder()
    b.button(text="📅 Bugun", callback_data=f"attbr:{scope}:day")
    b.button(text="🗓 Hafta", callback_data=f"attbr:{scope}:week")
    b.button(text="📆 Oy", callback_data=f"attbr:{scope}:month")
    b.button(text="⬅️ Orqaga", callback_data=f"att:{scope}:day")
    b.adjust(3, 1)
    return b.as_markup()


def late_early_kb():
    b = InlineKeyboardBuilder()
    b.button(text="📅 Bugun", callback_data="le:day")
    b.button(text="🗓 Hafta", callback_data="le:week")
    b.button(text="📆 Oy", callback_data="le:month")
    b.adjust(3)
    return b.as_markup()


# ---- Admin: filialga koordinata biriktirish ----
def branch_location_request_kb():
    b = ReplyKeyboardBuilder()
    b.button(text="📍 Filial joylashuvini yuborish", request_location=True)
    b.button(text="⏭️ O'tkazib yuborish")
    b.adjust(1)
    return b.as_markup(resize_keyboard=True, one_time_keyboard=True)


def branch_setloc_kb(branches):
    b = InlineKeyboardBuilder()
    for br in branches:
        mark = "✅" if br.get("latitude") is not None else "➖"
        b.button(text=f"{mark} {br['name']}", callback_data=f"br_loc:{br['id']}")
    b.adjust(1)
    return b.as_markup()


# ================= BUXGALTER PANELI =================
def accountant_menu():
    b = ReplyKeyboardBuilder()
    b.button(text="📍 Davomat")
    b.button(text="⏰ Kech/erta hisobot")
    b.button(text="🏢 Filial tanlab ko'rish")
    b.button(text="👥 Xodimlar (oylik/jarima)")
    b.button(text="✂️ Oylik kesish")
    b.button(text="🚫 Jarimani bekor qilish")
    b.button(text="🛌 Dam olish so'rovlari")
    b.button(text="💵 Avans oluvchilar")
    b.button(text="🏠 Asosiy menyu")
    b.adjust(2, 2, 1, 1, 1, 1)
    return b.as_markup(resize_keyboard=True)


# ---------------- OYLIKDAN FOIZ KESISH ----------------
# Kimdan qancha foiz kesiladi
DEDUCTION_PERCENT = {"manager": 10, "employee": 5}
DEDUCTION_LABELS = {
    "manager": "👨‍💼 Filial rahbaridan",
    "employee": "👷 Xodimdan",
}


def deduction_target_kb():
    """Oylik kesish — kimdan kesiladi?"""
    b = InlineKeyboardBuilder()
    for kind, label in DEDUCTION_LABELS.items():
        pct = DEDUCTION_PERCENT[kind]
        b.button(text=f"{label} ({pct}%)", callback_data=f"ded:{kind}")
    b.adjust(1)
    return b.as_markup()


def deduction_branch_kb(branches, kind):
    """Filial tanlash (kesish oqimi uchun)."""
    b = InlineKeyboardBuilder()
    for br in branches:
        b.button(text=f"🏢 {br['name']}", callback_data=f"dedbr:{kind}:{br['id']}")
    b.button(text="⬅️ Orqaga", callback_data="ded:back")
    b.adjust(1)
    return b.as_markup()


def deduction_people_kb(profiles, kind):
    """Filialdagi odamlar ro'yxati (rahbar yoki xodim)."""
    b = InlineKeyboardBuilder()
    for p in profiles:
        name = p.get("full_name") or str(p.get("tg_id"))
        pos = p.get("position") or p.get("role") or "-"
        b.button(text=f"👤 {name} · {pos}", callback_data=f"dedemp:{kind}:{p['user_id']}")
    b.button(text="⬅️ Orqaga", callback_data=f"ded:{kind}")
    b.adjust(1)
    return b.as_markup()


def deduction_confirm_kb(user_id, kind):
    """Profil kartochkasi tagidagi «N% kesish» tugmasi."""
    pct = DEDUCTION_PERCENT.get(kind, 5)
    b = InlineKeyboardBuilder()
    b.button(text=f"✂️ Oylikdan {pct}% kesish", callback_data=f"dedgo:{kind}:{user_id}")
    b.button(text="❌ Bekor qilish", callback_data="ded:back")
    b.adjust(1)
    return b.as_markup()


def accountant_branch_kb(branches, prefix="accbr"):
    b = InlineKeyboardBuilder()
    for br in branches:
        b.button(text=f"🏢 {br['name']}", callback_data=f"{prefix}:{br['id']}")
    b.adjust(2)
    return b.as_markup()


def accountant_employee_kb(user_id):
    b = InlineKeyboardBuilder()
    b.button(text="💰 Oylik belgilash", callback_data=f"accsal:{user_id}")
    b.button(text="⬆️ Oylik oshirish", callback_data=f"accraise:{user_id}")
    b.button(text="✅ Oylik berildi", callback_data=f"accpaid:{user_id}:paid")
    b.button(text="❌ Oylik berilmadi", callback_data=f"accpaid:{user_id}:unpaid")
    b.button(text="💸 Jarima yozish", callback_data=f"accfine:{user_id}")
    b.button(text="📋 Jarimalar", callback_data=f"accfines:{user_id}")
    b.button(text="💊 Dori yozish", callback_data=f"accmed:{user_id}")
    b.button(text="📋 Dorilar", callback_data=f"accmeds:{user_id}")
    b.button(text="🧮 Yakuniy oylik", callback_data=f"accfinal:{user_id}")
    b.button(text="📨 Hisobotni yuborish", callback_data=f"accsendreport:{user_id}")
    b.button(text="🧾 To'lovlar tarixi", callback_data=f"accpayhist:{user_id}")
    b.adjust(2, 2, 2, 2, 2, 1)
    return b.as_markup()


# ================= FILIAL ALMASHTIRISH (admin/HR) =================
def branch_change_entry_kb():
    """«🔀 Filial almashtirish» — xodimni qanday topamiz?"""
    b = InlineKeyboardBuilder()
    b.button(text="🔍 Qidirish", callback_data="bch:find")
    b.button(text="🏢 Filial bo'yicha", callback_data="bch:branch")
    b.adjust(1)
    return b.as_markup()


def branch_change_branches_kb(branches, prefix="bchbr"):
    """Filiallar ro'yxati (xodim tanlash uchun)."""
    b = InlineKeyboardBuilder()
    for br in branches:
        b.button(text=f"🏢 {br['name']}", callback_data=f"{prefix}:{br['id']}")
    b.button(text="⬅️ Orqaga", callback_data="bch:home")
    b.adjust(2)
    return b.as_markup()


def branch_change_people_kb(profiles, prefix="bchemp"):
    """Filial/qidiruv natijasidagi xodimlar — tanlab kartochkasi ochiladi."""
    b = InlineKeyboardBuilder()
    for p in profiles:
        name = p.get("full_name") or str(p.get("tg_id"))
        br = f" · 🏢 {p['branch_name']}" if p.get("branch_name") else ""
        b.button(text=f"👤 {name}{br}", callback_data=f"{prefix}:{p['user_id']}")
    b.adjust(1)
    return b.as_markup()


def branch_change_card_kb(user_id):
    """Xodim kartochkasi tagidagi «Filialni almashtirish» tugmasi."""
    b = InlineKeyboardBuilder()
    b.button(text="🔀 Filialni almashtirish", callback_data=f"bchmove:{user_id}")
    b.adjust(1)
    return b.as_markup()


def branch_change_target_kb(user_id, branches, current_branch_id=None):
    """Yangi filialni tanlash (joriy filial ro'yxatda ko'rsatilmaydi)."""
    b = InlineKeyboardBuilder()
    for br in branches:
        if current_branch_id and br["id"] == current_branch_id:
            continue
        b.button(text=f"🏢 {br['name']}", callback_data=f"bchto:{user_id}:{br['id']}")
    b.button(text="⬅️ Orqaga", callback_data=f"bchemp:{user_id}")
    b.adjust(2)
    return b.as_markup()


def branch_change_confirm_kb(user_id, branch_id):
    """«Shu hodimni shu filialga o'tkazmoqchimisiz?» — Ha / Yo'q."""
    b = InlineKeyboardBuilder()
    b.button(text="✅ Ha, o'tkazilsin", callback_data=f"bchgo:{user_id}:{branch_id}")
    b.button(text="❌ Yo'q", callback_data=f"bchemp:{user_id}")
    b.adjust(1)
    return b.as_markup()


def hr_employee_kb(user_id, profile=None):
    """HR panelidagi xodim kartochkasi tugmalari — jarima (moliyaga boradi)
    va (farmatsevt bo'lsa) forma holati."""
    b = InlineKeyboardBuilder()
    b.button(text="💸 Jarima yozish", callback_data=f"phfine:{user_id}")
    b.button(text="📋 Jarimalar", callback_data=f"phfines:{user_id}")
    sizes = [2]
    from utils import is_pharmacist_like
    if profile and is_pharmacist_like(profile):
        status = profile.get("uniform_status")
        if status != "yes":
            b.button(text="✅ Forma bor", callback_data=f"ufset:{user_id}:yes")
        if status != "no":
            b.button(text="❌ Forma yo'q", callback_data=f"ufset:{user_id}:no")
        sizes.append(2)
    b.adjust(*sizes)
    return b.as_markup()


def fine_cancel_people_kb(rows, prefix="fcperson"):
    """Jarimasi bor xodimlar ro'yxati (bekor qilish uchun) + qidiruv tugmasi."""
    b = InlineKeyboardBuilder()
    b.button(text="🔍 Qidirish (filial/ism/username/ID)", callback_data="fcfind")
    for p in rows:
        name = p.get("full_name") or str(p.get("tg_id"))
        br = p.get("branch_name") or "-"
        cnt = p.get("fine_cnt") or 0
        b.button(
            text=f"👤 {name} · 🏢 {br} · 💸 {cnt} ta",
            callback_data=f"{prefix}:{p['user_id']}",
        )
    b.adjust(1)
    return b.as_markup()


def fine_cancel_list_kb(fines, user_id):
    """Bitta xodimning jarimalari — har biri yonida «bekor qilish» tugmasi."""
    b = InlineKeyboardBuilder()
    for f in fines:
        amt = f.get("amount") or "-"
        d = (f.get("created_at") or "")[:10]
        b.button(
            text=f"🚫 {amt} · {d} — bekor qilish",
            callback_data=f"fcancel:{f['id']}",
        )
    b.adjust(1)
    return b.as_markup()


# ================= IT XODIM PANELI =================
def it_menu():
    b = ReplyKeyboardBuilder()
    b.button(text="📊 Oylik hisobot (14-sana)")
    b.button(text="👥 Xodimlar")
    b.button(text="✏️ Ism o'zgartirishlar")
    b.button(text="🏠 Asosiy menyu")
    b.adjust(1, 2, 1)
    return b.as_markup(resize_keyboard=True)


def it_employee_branch_kb(branches):
    """IT panel — «Xodimlar» bosilganda filiallar ro'yxati."""
    b = InlineKeyboardBuilder()
    for br in branches:
        b.button(text=f"🏢 {br['name']}", callback_data=f"itempbr:{br['id']}")
    b.button(text="➖ Filialsiz xodimlar", callback_data="itempbr:0")
    b.adjust(2)
    return b.as_markup()


def it_employee_kb(user_id):
    b = InlineKeyboardBuilder()
    b.button(text="✏️ Ismini o'zgartirish", callback_data=f"itren:{user_id}")
    b.button(text="🔄 Filialga ko'chirish", callback_data=f"itmove:{user_id}")
    b.adjust(1)
    return b.as_markup()


def it_branch_pick_kb(branches, user_id):
    b = InlineKeyboardBuilder()
    for br in branches:
        b.button(text=f"🏢 {br['name']}", callback_data=f"itmovebr:{user_id}:{br['id']}")
    b.adjust(2)
    return b.as_markup()


# ================= AVANS (oldindan to'lov) =================
def advance_yes_no_kb(period):
    b = InlineKeyboardBuilder()
    b.button(text="✅ Ha", callback_data=f"avns_yes:{period}")
    b.button(text="❌ Yo'q", callback_data=f"avns_no:{period}")
    b.adjust(2)
    return b.as_markup()


def _fmt_amount(value):
    """123456 -> '123 456' (minglar probel bilan)."""
    return f"{int(value):,}".replace(",", " ")


def advance_amount_kb(options):
    """Avans miqdori tugmalari — oylikning ulushiga qarab (oshmaydigan qiymatlar).

    options — [(amount, percent), ...] ko'rinishida.
    """
    b = InlineKeyboardBuilder()
    for amount, pct in options:
        b.button(
            text=f"💵 {_fmt_amount(amount)} so'm  ({pct}%)",
            callback_data=f"avns_amt:{int(amount)}",
        )
    b.adjust(1)
    return b.as_markup()


def advance_confirm_kb():
    b = InlineKeyboardBuilder()
    b.button(text="✅ Tasdiqlash", callback_data="avns_confirm")
    b.button(text="✏️ Tahrirlash", callback_data="avns_edit")
    b.adjust(2)
    return b.as_markup()


def advance_send_acc_kb(period):
    b = InlineKeyboardBuilder()
    b.button(text="📤 Moliya bo'limiga yuborish", callback_data=f"avns_send:{period}")
    return b.as_markup()


def advance_settings_kb(prompt_day, pay_day, enabled=True):
    b = InlineKeyboardBuilder()
    if enabled:
        b.button(text="💵 Avans so'rovi: 🟢 YOQILGAN", callback_data="avset:toggle")
    else:
        b.button(text="💵 Avans so'rovi: 🔴 O'CHIQ", callback_data="avset:toggle")
    b.button(
        text=f"📨 So'rov yuboriladigan kun: {prompt_day}-sana",
        callback_data="avset:promptday",
    )
    b.button(
        text=f"💳 To'lov sanasi: {pay_day}-sana",
        callback_data="avset:payday",
    )
    b.adjust(1)
    return b.as_markup()


# ================= DAM OLISH KUNINI ALMASHTIRISH =================
WEEK_DAYS = [
    "Dushanba", "Seshanba", "Chorshanba", "Payshanba",
    "Juma", "Shanba", "Yakshanba",
]


def dayoff_day_kb():
    b = ReplyKeyboardBuilder()
    for day in WEEK_DAYS:
        b.button(text=day)
    b.button(text=CANCEL_BTN)
    b.adjust(2)
    return b.as_markup(resize_keyboard=True, one_time_keyboard=True)


def dayoff_actions_kb(rid):
    b = InlineKeyboardBuilder()
    b.button(text="✅ Tasdiqlash", callback_data=f"doacc:{rid}")
    b.button(text="❌ Rad etish", callback_data=f"dorej:{rid}")
    b.adjust(2)
    return b.as_markup()


def dayoff_list_kb(reqs, prefix="doview"):
    b = InlineKeyboardBuilder()
    for r in reqs:
        b.button(
            text=f"#{r['id']} · {r.get('full_name') or '-'} · {r.get('from_day')}→{r.get('to_day')} · {r.get('status')}",
            callback_data=f"{prefix}:{r['id']}",
        )
    b.adjust(1)
    return b.as_markup()


# ---------------- KUNLIK DAM OLISH REJASI (17:00 tasdiq) ----------------
def dayoff_plan_confirm_kb(plan_id):
    b = InlineKeyboardBuilder()
    b.button(text="✅ Tasdiqlash", callback_data=f"dopl_ok:{plan_id}")
    b.button(text="✏️ Tahrirlash", callback_data=f"dopl_edit:{plan_id}")
    b.adjust(2)
    return b.as_markup()


def dayoff_plan_edit_kb(plan_id, items):
    """Har bir xodim uchun holat tugmasi: 🛌 dam oladi <-> ✅ keladi."""
    b = InlineKeyboardBuilder()
    for it in items:
        if it.get("day_status") == "off":
            label = f"🛌 {it.get('full_name') or '-'} — dam oladi"
        else:
            label = f"✅ {it.get('full_name') or '-'} — keladi"
        b.button(text=label, callback_data=f"dopl_tog:{it['id']}")
    b.button(text="✅ Tasdiqlash", callback_data=f"dopl_ok:{plan_id}")
    b.adjust(1)
    return b.as_markup()
