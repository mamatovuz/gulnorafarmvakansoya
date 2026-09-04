"""Ma'lumotlar bazasi ulanishi va jadvallarni yaratish."""
import re
import aiosqlite
from config import DB_PATH, SUPER_ADMINS

# Rollar
ROLE_ADMIN = "admin"
ROLE_HR = "hr"
ROLE_MANAGER = "manager"      # Filial rahbari
ROLE_EMPLOYEE = "employee"    # Oddiy xodim
ROLE_PHARMACIST = "pharmacist"  # Farmatsevt
ROLE_DIRECTOR = "director"    # Direktor
ROLE_ACCOUNTANT = "accountant"  # Buxgalter
ROLE_IT = "it"                # IT xodim (kadrlar harakati hisoboti)
ROLE_TECH = "tech"            # Texnik xodim (filial texnik nosozliklarini bartaraf etadi)
ROLE_CANDIDATE = "candidate"  # Nomzod (default)

# Ariza holatlari
ST_NEW = "new"
ST_INTERVIEW = "interview"
ST_ACCEPTED = "accepted"
ST_REJECTED = "rejected"
ST_WAITING = "waiting"        # Kutuvda — nomzodlar bazasiga qo'shilgan

STATUS_LABELS = {
    ST_NEW: "🆕 Yangi",
    ST_INTERVIEW: "📅 Suhbatga chaqirilgan",
    ST_ACCEPTED: "✅ Ishga qabul qilingan",
    ST_REJECTED: "❌ Rad etilgan",
    ST_WAITING: "⏳ Kutuvda",
}

# Qabul turlari (applications.accept_kind) — HR arizani qaysi maqomda qabul qilgani
AK_HIRE = "hire"          # to'g'ridan-to'g'ri ishga
AK_TRIAL = "trial"        # sinov muddati
AK_LEARNER = "learner"    # o'rganuvchi

ACCEPT_KIND_LABELS = {
    AK_HIRE: "✅ Ishga qabul qilingan",
    AK_TRIAL: "🧪 Sinov muddatida",
    AK_LEARNER: "🎓 O'rganuvchi",
}

# Xodimning bandlik maqomi (employee_profiles.emp_status) — rol o'zgartirmasdan
# xodimni «sinovda» yoki «o'rganuvchi» deb belgilash uchun.
ES_REGULAR = "regular"    # doimiy xodim (default)
ES_TRIAL = "trial"        # sinov muddatida
ES_LEARNER = "learner"    # o'rganuvchi

EMP_STATUS_LABELS = {
    ES_REGULAR: "🟢 Doimiy xodim",
    ES_TRIAL: "🧪 Sinovda",
    ES_LEARNER: "🎓 O'rganuvchi",
}


def application_status_label(a):
    """Ariza statusi yorlig'i.

    Qabul qilingan ariza uchun umumiy «Ishga qabul qilingan» emas, balki
    aniq maqom ko'rsatiladi: sinov muddatida / o'rganuvchi / ishga qabul."""
    status = a.get("status")
    if status == ST_ACCEPTED:
        label = ACCEPT_KIND_LABELS.get(a.get("accept_kind"))
        if label:
            return label
    return STATUS_LABELS.get(status, status or "-")


# Yo'nalish / lavozim nomidan icon aniqlash (kalit so'z bo'yicha).
# Ro'yxatga faqat ICON chiqadi — nomi emas (kompakt bo'lsin).
def application_role_icon(a):
    text = (a.get("vacancy_title") or a.get("position") or "").lower()
    rules = [
        (("farmatsevt", "farmasev", "аптек"), "💊"),
        (("rahbar", "boshliq", "manager"), "👨‍💼"),
        (("direktor", "director"), "👔"),
        (("moliya", "buxgalter", "accountant", "hisobchi"), "🧮"),
        (("ombor", "склад"), "📦"),
        (("haydov", "logist", "kur'er", "kuryer", "driver", "достав", "курьер"), "🚚"),
        (("texnik", "tech", "montaj", "usta"), "🔧"),
        (("hr", "kadr", "inspektor"), "🧑‍💼"),
        (("it ", "dasturchi", "programmer", "sysadmin"), "💻"),
    ]
    for keys, icon in rules:
        if any(k in text for k in keys):
            return icon
    return "💼"  # umumiy


# Ariza holati uchun faqat ICON (matnsiz).
def application_status_icon(a):
    status = a.get("status")
    if status == ST_ACCEPTED:
        kind = a.get("accept_kind")
        if kind == AK_TRIAL:
            return "🕒"   # sinov muddati (soat)
        if kind == AK_LEARNER:
            return "🎓"   # o'rganuvchi
        return "✅"       # ishga qabul (galichka)
    return {
        ST_NEW: "🆕",
        ST_INTERVIEW: "📅",
        ST_REJECTED: "❌",
        ST_WAITING: "⏳",
    }.get(status, "•")


def branch_short(name):
    """Filial nomidan «filiali» (yoki «filial») so'zini olib tashlaydi.

    Ariza ko'rinishlarida filial nomi qisqa chiqishi uchun:
    «Asaka filiali» → «Asaka», «Yangi bozor filiali №2» → «Yangi bozor №2»."""
    if not name:
        return name
    short = re.sub(r"\s*\bfiliali?\b\s*", " ", name, flags=re.IGNORECASE)
    short = re.sub(r"\s{2,}", " ", short).strip(" ·-")
    return short or name


def application_list_label(a):
    """Ariza ro'yxati tugmasi uchun qisqa, ICONLI yorliq.

    Format: «#ID · <yo'nalish iconi> · Ism Familiya · 🏢 Filial · <status iconi>».
    Masalan: «#12 · 💊 · Ali Valiyev · 🏢 Asaka · 🆕».
    HR panel va boshqa barcha ariza ro'yxatlarida bir xil ko'rinishi uchun
    shu yagona funksiya ishlatiladi."""
    name = a.get("full_name") or "-"
    branch = branch_short(a.get("branch_name"))
    parts = [f"#{a['id']}", application_role_icon(a), name]
    if branch:
        parts.append(f"🏢 {branch}")
    parts.append(application_status_icon(a))
    return " · ".join(parts)

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tg_id INTEGER UNIQUE NOT NULL,
    full_name TEXT,               -- ko'rsatiladigan ism (ro'yxatdan o'tgan bo'lsa — o'shanisi)
    tg_name TEXT,                 -- Telegram profilidagi nom (ma'lumot uchun)
    name_locked INTEGER NOT NULL DEFAULT 0,  -- 1 => full_name haqiqiy ism, ustiga yozilmaydi
    username TEXT,
    phone TEXT,
    lang TEXT,                    -- interfeys tili: uz / ru (NULL => tanlanmagan)
    role TEXT NOT NULL DEFAULT 'candidate',
    branch_id INTEGER,
    created_at TEXT DEFAULT (datetime('now','+5 hours'))
);

CREATE TABLE IF NOT EXISTS channels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id TEXT NOT NULL,
    title TEXT,
    url TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now','+5 hours'))
);

CREATE TABLE IF NOT EXISTS branches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    address TEXT,
    latitude REAL,
    longitude REAL,
    radius INTEGER NOT NULL DEFAULT 150,
    phone TEXT,
    work_hours TEXT,
    created_at TEXT DEFAULT (datetime('now','+5 hours'))
);

CREATE TABLE IF NOT EXISTS vacancies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    branch_id INTEGER,
    job_type TEXT,
    shift TEXT,
    salary TEXT,
    work_time TEXT,
    requirements TEXT,
    responsibilities TEXT,
    conditions TEXT,
    staff_count TEXT,                 -- nechta xodim kerak (rahbar so'rovi)
    experience TEXT,                  -- talab qilinadigan tajriba
    gender TEXT,                      -- kerakli xodim jinsi: male / female / any
    manager_request_id INTEGER,       -- qaysi rahbar so'rovidan ochilgan
    channel_chat_id TEXT,             -- kanalga joylangan bo'lsa — chat id
    channel_message_id INTEGER,       -- kanaldagi post message id
    filled INTEGER NOT NULL DEFAULT 0,-- 1 => hodimlar soni to'ldi (yakunlandi)
    is_active INTEGER NOT NULL DEFAULT 1,
    created_by INTEGER,
    created_at TEXT DEFAULT (datetime('now','+5 hours'))
);

CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    vacancy_id INTEGER,
    branch_id INTEGER,
    full_name TEXT,
    birth_date TEXT,
    gender TEXT,                  -- male / female (vakansiyaga moslik uchun)
    city TEXT,
    district TEXT,
    address TEXT,
    position TEXT,
    position_extra TEXT,
    uniform_status TEXT,
    shift TEXT,
    education TEXT,
    exp_years TEXT,
    prev_years TEXT,
    criminal TEXT,
    marital TEXT,
    children TEXT,
    prev_salary TEXT,
    expected_salary TEXT,
    word_level TEXT,              -- eski bazalar uchun qoldirilgan
    excel_level TEXT,             -- eski bazalar uchun qoldirilgan
    computer_level TEXT,          -- kompyuter savodxonligi (Word/Excel o'rniga)
    languages TEXT,
    work_intent TEXT,
    reason TEXT,
    phone TEXT,
    resume_file_id TEXT,
    resume_type TEXT,
    photo_file_id TEXT,           -- oxirgi 10 kunda tushgan rasm (majburiy)
    channel_chat_id TEXT,         -- kandidatlar kanaliga joylangan bo'lsa — chat id
    channel_message_id INTEGER,   -- kanaldagi post message id (status yangilash uchun)
    offered_salary TEXT,          -- kelishuvdagi joriy oylik summasi
    salary_offer_by TEXT,         -- oxirgi taklifni kim berdi: hr / candidate
    salary_status TEXT,           -- NULL / pending / agreed
    status TEXT NOT NULL DEFAULT 'new',
    accept_kind TEXT,             -- hire / trial / learner — qaysi maqomda qabul qilindi
    hr_comment TEXT,
    handled_by INTEGER,
    created_at TEXT DEFAULT (datetime('now','+5 hours'))
);

CREATE TABLE IF NOT EXISTS interviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    application_id INTEGER NOT NULL,
    date TEXT,
    time TEXT,
    location TEXT,
    comment TEXT,
    status TEXT NOT NULL DEFAULT 'pending',       -- nomzod javobi: pending/confirmed/reschedule
    attendance TEXT,                              -- kelish holati: NULL / came / absent
    channel_chat_id TEXT,                         -- suhbat kanaliga joylangan bo'lsa
    channel_message_id INTEGER,                   -- kanaldagi post id (yangilash uchun)
    reminder_day_sent INTEGER NOT NULL DEFAULT 0,
    reminder_2h_sent INTEGER NOT NULL DEFAULT 0,
    created_by INTEGER,
    created_at TEXT DEFAULT (datetime('now','+5 hours'))
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tg_id INTEGER,
    actor_name TEXT,
    action TEXT,
    details TEXT,
    created_at TEXT DEFAULT (datetime('now','+5 hours'))
);

CREATE TABLE IF NOT EXISTS employee_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER UNIQUE NOT NULL,
    application_id INTEGER,
    role TEXT,
    position TEXT,
    branch_id INTEGER,
    uniform_status TEXT NOT NULL DEFAULT 'unknown',
    monthly_salary TEXT,
    birth_date TEXT,
    address TEXT,
    work_hours TEXT,
    rest_day TEXT,
    photo_file_id TEXT,
    extra_info TEXT,
    since TEXT,
    emp_status TEXT NOT NULL DEFAULT 'regular',  -- regular / trial / learner
    education TEXT,               -- ma'lumoti / diplomi (staff_regs dan ko'chiriladi)
    shift TEXT,                   -- smena: kunduzgi / tungi (qabulda belgilanadi)
    parent_phone TEXT,            -- ota yoki ona telefon raqami
    passport_front TEXT,          -- pasport / ID karta OLDI rasmi (file_id) — maxfiy, kanalga chiqmaydi
    passport_back TEXT,           -- pasport / ID karta ORQA rasmi (file_id) — maxfiy
    diploma_file TEXT,            -- diplom rasmi / hujjati (file_id) — maxfiy
    update_required INTEGER NOT NULL DEFAULT 0,  -- admin «ma'lumotlarni yangilash» so'ragan
    update_requested_at TEXT,
    updated_by_self_at TEXT,      -- xodim oxirgi marta o'zi yangilagan vaqt
    created_at TEXT DEFAULT (datetime('now','+5 hours')),
    updated_at TEXT DEFAULT (datetime('now','+5 hours'))
);

CREATE TABLE IF NOT EXISTS staff_regs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    full_name TEXT,
    birth_date TEXT,
    phone TEXT,
    role TEXT,
    position TEXT,
    address TEXT,
    branch_id INTEGER,
    branch_name TEXT,
    work_hours TEXT,
    salary TEXT,
    rest_day TEXT,
    uniform_status TEXT NOT NULL DEFAULT 'unknown',
    photo_file_id TEXT,
    since TEXT,
    extra_info TEXT,
    education TEXT,               -- ma'lumoti: o'rta maxsus / oliy farmatsevt / boshqa / diplom yo'q
    parent_phone TEXT,            -- ota yoki ona telefon raqami
    passport_front TEXT,          -- pasport / ID karta OLDI rasmi (file_id) — maxfiy
    passport_back TEXT,           -- pasport / ID karta ORQA rasmi (file_id) — maxfiy
    diploma_file TEXT,            -- diplom rasmi / hujjati (file_id) — maxfiy
    status TEXT NOT NULL DEFAULT 'new',
    reject_reason TEXT,           -- HR rad etganda yozgan sabab
    handled_by INTEGER,
    created_at TEXT DEFAULT (datetime('now','+5 hours'))
);

CREATE TABLE IF NOT EXISTS attendance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    branch_id INTEGER,
    date TEXT NOT NULL,
    time TEXT,
    latitude REAL,
    longitude REAL,
    distance INTEGER,
    status TEXT NOT NULL DEFAULT 'present',
    out_time TEXT,
    out_latitude REAL,
    out_longitude REAL,
    out_distance INTEGER,
    late INTEGER NOT NULL DEFAULT 0,
    early INTEGER NOT NULL DEFAULT 0,
    late_seconds INTEGER NOT NULL DEFAULT 0,
    early_seconds INTEGER NOT NULL DEFAULT 0,
    on_break INTEGER NOT NULL DEFAULT 0,
    break_seconds INTEGER NOT NULL DEFAULT 0,
    break_started_at TEXT,
    last_prompt_at TEXT,
    created_at TEXT DEFAULT (datetime('now','+5 hours'))
);

CREATE TABLE IF NOT EXISTS location_checks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    attendance_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    branch_id INTEGER,
    date TEXT,
    requested_at TEXT,
    responded_at TEXT,
    status TEXT NOT NULL DEFAULT 'pending',   -- pending / present / away / missed
    distance INTEGER,
    kind TEXT NOT NULL DEFAULT 'auto',        -- auto / resume
    created_at TEXT DEFAULT (datetime('now','+5 hours'))
);

CREATE TABLE IF NOT EXISTS salary_payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_user_id INTEGER NOT NULL,
    period TEXT NOT NULL,
    amount TEXT,
    status TEXT NOT NULL DEFAULT 'paid',
    note TEXT,
    created_by INTEGER,
    created_at TEXT DEFAULT (datetime('now','+5 hours'))
);

CREATE TABLE IF NOT EXISTS dayoff_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    branch_id INTEGER,
    from_day TEXT,
    to_day TEXT,
    reason TEXT,
    status TEXT NOT NULL DEFAULT 'new',
    handled_by INTEGER,
    created_at TEXT DEFAULT (datetime('now','+5 hours'))
);

-- Oylikdan foiz kesish (moliya bo'limi).
-- Har bir yozuv AYNAN BITTA OYGA tegishli (period = YYYY-MM).
CREATE TABLE IF NOT EXISTS salary_deductions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_user_id INTEGER NOT NULL,   -- kimdan kesildi (users.id)
    branch_id INTEGER,
    period TEXT NOT NULL,                -- qaysi oy: YYYY-MM
    kind TEXT NOT NULL,                  -- manager (filial rahbari) / employee (xodim)
    percent INTEGER NOT NULL,            -- kesilgan foiz: 10 / 5
    base_salary TEXT,                    -- kesish paytidagi oylik (matn, snapshot)
    base_amount INTEGER,                 -- o'sha oylikning raqamli qiymati
    amount INTEGER,                      -- kesilgan summa (so'm)
    remaining INTEGER,                   -- shu oydagi barcha kesimlardan keyin qolgani
    created_by INTEGER,                  -- kim kesdi (users.id)
    created_at TEXT DEFAULT (datetime('now','+5 hours'))
);

CREATE INDEX IF NOT EXISTS idx_salary_deductions_period
    ON salary_deductions(employee_user_id, period);

CREATE TABLE IF NOT EXISTS fines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_user_id INTEGER NOT NULL,
    branch_id INTEGER,
    period TEXT,                          -- qaysi oy: YYYY-MM (created_at asosida)
    amount TEXT NOT NULL,
    reason TEXT,
    source TEXT NOT NULL DEFAULT 'finance', -- finance (moliya) / hr (kadrlar)
    cancelled INTEGER NOT NULL DEFAULT 0,   -- 1 => bekor qilingan (oylikdan qaytariladi)
    cancelled_by INTEGER,
    cancelled_at TEXT,
    created_by INTEGER,
    created_at TEXT DEFAULT (datetime('now','+5 hours'))
);

-- Dorixonadan olingan dorilar (yakuniy oylikdan ayiriladi)
CREATE TABLE IF NOT EXISTS staff_medicines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_user_id INTEGER NOT NULL,   -- kimdan (users.id)
    branch_id INTEGER,
    period TEXT NOT NULL,                -- qaysi oy: YYYY-MM
    amount INTEGER NOT NULL,             -- dori qiymati (so'm)
    reason TEXT,                         -- izoh (qanday dori)
    created_by INTEGER,                  -- kim yozdi (users.id)
    created_at TEXT DEFAULT (datetime('now','+5 hours'))
);

CREATE INDEX IF NOT EXISTS idx_staff_medicines_period
    ON staff_medicines(employee_user_id, period);

-- Xodim maosh oshirish so'rovi (xodim ⇄ HR kelishuvi)
CREATE TABLE IF NOT EXISTS salary_raise_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,          -- users.id (ichki)
    branch_id INTEGER,
    position TEXT,
    current_salary TEXT,               -- so'rov paytidagi joriy oylik (snapshot)
    requested_amount TEXT,             -- xodim so'ragan oxirgi summa
    offered_amount TEXT,               -- HR taklif qilgan oxirgi summa
    last_offer_by TEXT,                -- 'employee' / 'hr'
    status TEXT NOT NULL DEFAULT 'pending',  -- pending / agreed / rejected
    final_amount TEXT,                 -- kelishilgan yakuniy summa
    reject_reason TEXT,
    handled_by INTEGER,
    created_at TEXT DEFAULT (datetime('now','+5 hours')),
    updated_at TEXT DEFAULT (datetime('now','+5 hours'))
);

CREATE TABLE IF NOT EXISTS work_hour_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,          -- users.id (ichki)
    branch_id INTEGER,
    position TEXT,
    current_hours TEXT,                -- so'rov paytidagi ish vaqti (snapshot)
    requested_hours TEXT,              -- xodim so'ragan yangi ish vaqti «08:00 - 17:00»
    status TEXT NOT NULL DEFAULT 'pending',  -- pending / approved / rejected
    reject_reason TEXT,
    handled_by INTEGER,
    created_at TEXT DEFAULT (datetime('now','+5 hours')),
    updated_at TEXT DEFAULT (datetime('now','+5 hours'))
);

-- Xodim boshqa filialga o'tish so'rovi (xodim ⇄ HR yozishmasi bilan)
CREATE TABLE IF NOT EXISTS branch_transfer_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,          -- users.id (ichki)
    from_branch_id INTEGER,            -- hozirgi filial
    to_branch_id INTEGER,              -- o'tmoqchi bo'lgan filial
    position TEXT,                     -- so'rov paytidagi lavozim (snapshot)
    status TEXT NOT NULL DEFAULT 'pending',  -- pending / approved / rejected
    handled_by INTEGER,                -- so'rov bilan ishlayotgan HR (users.id)
    created_at TEXT DEFAULT (datetime('now','+5 hours')),
    updated_at TEXT DEFAULT (datetime('now','+5 hours'))
);

CREATE TABLE IF NOT EXISTS manager_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    manager_user_id INTEGER NOT NULL,
    branch_id INTEGER,
    kind TEXT NOT NULL,
    title TEXT,
    staff_count TEXT,
    shift TEXT,                       -- smena (ertalabki/kechki)
    experience TEXT,                  -- talab qilinadigan tajriba
    gender TEXT,                      -- kerakli xodim jinsi: male / female / any
    details TEXT,
    status TEXT NOT NULL DEFAULT 'new',
    hr_comment TEXT,
    handled_by INTEGER,
    created_at TEXT DEFAULT (datetime('now','+5 hours'))
);

-- Kunlik dam olish rejasi: har filial, har kun uchun bitta reja.
-- Filial rahbari 17:00 da tasdiqlaydi/tahrirlaydi; 08:30 da HR ga to'planadi.
CREATE TABLE IF NOT EXISTS dayoff_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    branch_id INTEGER,
    plan_date TEXT NOT NULL,          -- reja qaysi kunga (ertangi kun) ISO YYYY-MM-DD
    weekday TEXT,                     -- hafta kuni nomi (Dushanba...)
    status TEXT NOT NULL DEFAULT 'pending',  -- pending / confirmed
    confirmed_by INTEGER,
    confirmed_at TEXT,
    created_at TEXT DEFAULT (datetime('now','+5 hours')),
    UNIQUE(branch_id, plan_date)
);

CREATE TABLE IF NOT EXISTS dayoff_plan_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    full_name TEXT,
    position TEXT,
    -- 'off' => ertaga dam oladi (kelmaydi); 'work' => keladi (rahbar o'zgartirgan)
    day_status TEXT NOT NULL DEFAULT 'off',
    created_at TEXT DEFAULT (datetime('now','+5 hours'))
);

CREATE TABLE IF NOT EXISTS termination_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_user_id INTEGER NOT NULL,   -- ishdan bo'shatilayotgan xodim (users.id)
    requested_by INTEGER NOT NULL,       -- so'rovni yuborgan rahbar/direktor (users.id)
    branch_id INTEGER,
    reason TEXT,                         -- rahbar yozgan sabab
    status TEXT NOT NULL DEFAULT 'new',  -- new / approved / rejected
    hr_comment TEXT,                     -- HR rad etganda yozgan sabab
    handled_by INTEGER,
    created_at TEXT DEFAULT (datetime('now','+5 hours'))
);

CREATE TABLE IF NOT EXISTS dismissed_employees (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,                     -- ishdan bo'shatilgan xodim (users.id)
    tg_id INTEGER,
    full_name TEXT,
    phone TEXT,
    branch_id INTEGER,                   -- oldingi ishlagan filiali
    branch_name TEXT,
    position TEXT,
    monthly_salary TEXT,                 -- oldingi maoshi
    role TEXT,                           -- oldingi roli (pharmacist/employee...)
    profile_json TEXT,                   -- profil ma'lumotlarining to'liq nusxasi (JSON)
    reason TEXT,                         -- bo'shatish sababi (bo'lsa)
    dismissed_by INTEGER,                -- kim bo'shatgani (users.id)
    dismissed_at TEXT DEFAULT (datetime('now','+5 hours')),
    rehired INTEGER NOT NULL DEFAULT 0,  -- ishga qayta olingan bo'lsa 1
    rehired_at TEXT
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now','+5 hours'))
);

CREATE TABLE IF NOT EXISTS advance_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,        -- ichki users.id
    period TEXT NOT NULL,            -- qaysi oy avansi: YYYY-MM
    full_name TEXT,
    card_number TEXT,
    amount INTEGER,                 -- xodim tanlagan avans miqdori (so'm)
    status TEXT NOT NULL DEFAULT 'pending',   -- pending / confirmed / declined
    created_at TEXT DEFAULT (datetime('now','+5 hours')),
    updated_at TEXT DEFAULT (datetime('now','+5 hours')),
    UNIQUE(user_id, period)
);

CREATE TABLE IF NOT EXISTS hr_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,     -- hired / left / transferred / name_changed
    user_id INTEGER,              -- ta'sirlangan xodim (users.id)
    full_name TEXT,               -- voqea paytidagi (yangi) ism
    old_value TEXT,               -- eski qiymat (eski ism / eski filial)
    new_value TEXT,               -- yangi qiymat (yangi ism / yangi filial)
    branch_id INTEGER,
    details TEXT,
    created_by INTEGER,           -- amalni bajargan (users.id)
    created_at TEXT DEFAULT (datetime('now','+5 hours'))
);

CREATE TABLE IF NOT EXISTS probations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    application_id INTEGER,
    user_id INTEGER NOT NULL,
    branch_id INTEGER,
    full_name TEXT,
    position TEXT,
    start_date TEXT,      -- ISO: YYYY-MM-DD
    end_date TEXT,        -- ISO: YYYY-MM-DD (start + 14 kun)
    days INTEGER NOT NULL DEFAULT 15,
    kind TEXT NOT NULL DEFAULT 'trial',      -- trial (sinov) / learner (o'rganuvchi)
    status TEXT NOT NULL DEFAULT 'active',   -- active / finished
    manager_notified INTEGER NOT NULL DEFAULT 0,
    hr_3day_sent INTEGER NOT NULL DEFAULT 0,
    hr_end_sent INTEGER NOT NULL DEFAULT 0,
    created_by INTEGER,
    created_at TEXT DEFAULT (datetime('now','+5 hours'))
);

-- Bir so'rov bir nechta HR/adminga yuboriladi. Kimdir tasdiqlagach qolganlaridagi
-- xabar o'chirilishi uchun yuborilgan xabarlarning (chat_id, message_id) lari
-- shu yerda saqlanadi.
CREATE TABLE IF NOT EXISTS request_notices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,               -- staff_reg / manager_request / dayoff / ...
    ref_id INTEGER NOT NULL,          -- so'rov id si
    chat_id INTEGER NOT NULL,         -- kimga yuborilgan (tg_id)
    message_id INTEGER NOT NULL,
    created_at TEXT DEFAULT (datetime('now','+5 hours'))
);

CREATE INDEX IF NOT EXISTS idx_request_notices_ref
    ON request_notices(kind, ref_id);

-- «Ishonch xabari» — HR yuborgan, «✅ Ko'rib chiqdim» tugmasi bilan
-- kuzatiladigan xabarnoma. Har bir yuborilgan xabar `trust_notice_reads`
-- da qayd etiladi; qabul qiluvchi tugmani bosgach «seen» belgilanadi.
CREATE TABLE IF NOT EXISTS trust_notices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT,                 -- xabar matnining boshlanishi (ro'yxatda ko'rsatish uchun)
    target_label TEXT,          -- kimga yuborilgani (matnli tavsif)
    sender_id INTEGER,          -- yuborgan HR (users.id)
    sender_name TEXT,
    total INTEGER NOT NULL DEFAULT 0,   -- muvaffaqiyatli yuborilgan (yetkazilgan) soni
    created_at TEXT DEFAULT (datetime('now','+5 hours'))
);

CREATE TABLE IF NOT EXISTS trust_notice_reads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    notice_id INTEGER NOT NULL,
    chat_id INTEGER NOT NULL,   -- qabul qiluvchi tg_id
    message_id INTEGER,         -- yuborilgan xabar id si (tugmani yangilash uchun)
    full_name TEXT,             -- qabul qiluvchi ismi (statistikada ko'rsatish uchun)
    seen INTEGER NOT NULL DEFAULT 0,   -- «Ko'rib chiqdim» bosilganmi
    seen_at TEXT,
    UNIQUE(notice_id, chat_id)
);

CREATE INDEX IF NOT EXISTS idx_trust_reads_notice
    ON trust_notice_reads(notice_id);

-- Texnik topshiriqlar: filial rahbari -> HR tasdiqi -> texnik xodim.
-- Rahbar texnik nosozlik + muddat yuboradi; HR tasdiqlaydi va topshiriq
-- barcha texnik xodimlarga tushadi. Texnik xodim «boshladim / tugatdim»
-- tugmalari bilan holatni yangilaydi; tugagach rahbar 1..5 yulduz bilan baholaydi.
CREATE TABLE IF NOT EXISTS tech_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    manager_request_id INTEGER,       -- bog'liq manager_requests (kind=technical)
    branch_id INTEGER,
    manager_user_id INTEGER,          -- so'rovni yuborgan rahbar (users.id)
    tech_user_id INTEGER,             -- topshiriqni bajarayotgan texnik xodim (users.id)
    assigned_by INTEGER,              -- HR/admin — tasdiqlab yuborgan (users.id)
    title TEXT,                       -- qisqa mavzu
    details TEXT,                     -- rahbar izohi (caption/matn)
    kind TEXT,                        -- 🖼 Rasm / 🎬 Video / 📝 Matn ...
    deadline TEXT,                    -- rahbar kiritgan muddat (matn)
    src_chat_id INTEGER,              -- media manbai (copy_message uchun)
    src_message_id INTEGER,
    -- pending_hr (HR tasdig'ini kutmoqda) / assigned (texniklarga yuborildi) /
    -- tomorrow (ertaga boshlanadi) / in_progress (boshlandi) / done (tugatildi) /
    -- rated (rahbar baholadi) / closed (HR yopdi)
    status TEXT NOT NULL DEFAULT 'pending_hr',
    rating INTEGER,                   -- rahbar bahosi (1..5 yulduz)
    started_at TEXT,
    done_at TEXT,
    rated_at TEXT,
    channel_chat_id INTEGER,          -- texnik ishlar kanalidagi ochiq kartochka
    channel_message_id INTEGER,       -- (kim olgani text-edit bilan yangilanadi)
    pending_transfer_to INTEGER,      -- boshqa texnikka o'tkazish taklifi (users.id)
    prev_tech_name TEXT,              -- o'tkazishdan oldingi ega ismi (kartochkada)
    created_at TEXT DEFAULT (datetime('now','+5 hours'))
);

CREATE INDEX IF NOT EXISTS idx_tech_tasks_status ON tech_tasks(status);
CREATE INDEX IF NOT EXISTS idx_tech_tasks_tech ON tech_tasks(tech_user_id);
CREATE INDEX IF NOT EXISTS idx_tech_tasks_request ON tech_tasks(manager_request_id);

-- Texnik topshiriq bo'yicha yozishmalar (texnik xodim «💬 Javob berish» qilsa —
-- filial rahbariga boradi; rahbar javobi ham shu yerda saqlanadi).
CREATE TABLE IF NOT EXISTS tech_task_replies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL,
    from_role TEXT,                   -- tech / manager
    from_user_id INTEGER,            -- users.id
    from_name TEXT,
    text TEXT,
    created_at TEXT DEFAULT (datetime('now','+5 hours'))
);
CREATE INDEX IF NOT EXISTS idx_tech_replies_task ON tech_task_replies(task_id);
"""

# Ishga arizadagi standart yo'nalishlar (positions jadvali bo'sh bo'lsa seed qilinadi)
DEFAULT_POSITIONS = [
    "💊 Farmatsevt", "👨‍💼 Filial rahbari", "👔 Direktor", "🧮 Moliya bo'limi",
    "🧹 Tozalik xodimi", "📦 Omborchi", "🚚 Haydovchi", "🔧 Texnik xodim",
]

# Standart filiallar — nomi bo'yicha mavjud bo'lmasa qo'shiladi (koordinatasi bilan).
# Admin panelda tahrirlash / o'chirish / koordinatani to'g'rilash mumkin.
# (nom, manzil, kenglik, uzunlik, telefon, ish_vaqti)
_WH = "08:00 – 24:00"
DEFAULT_BRANCHES = [
    ("Gorgaz filiali", "Andijon shahar, gorgaz krugavoy", 40.747291, 72.36142, "+998972663100", _WH),
    ("Eski shahar №1 filiali", "Andijon shahar, Fitrat ko'chasi", 40.784818, 72.346347, "+998914760028", _WH),
    ("Soy filiali", "Andijon shahar, krugavoyda (3-Poliklinika qatorida)", 40.7979344, 72.3459594, "+998972721555", _WH),
    ("Yangi bozor filiali", "Andijon shahar, Boburshoh ko'chasi 37-B", 40.7594818, 72.3532151, "+998959171746", _WH),
    ("Jalabek filiali", "A. Yo'ldashev ko'chasi 7-uy", 40.759345, 72.334462, "+998934760028", _WH),
    ("Soy №2 filiali", "Cholpon Shoh ko'chasi 46-uy", 40.796833, 72.346242, "+998884750028", _WH),
    ("Sanchas filiali", "Klinika Med Sanchas", 40.810534, 72.326574, "+998872951100", _WH),
    ("Yangi bozor filiali №2", "Andijon shahar, Boburshoh ko'chasi 37-B (Akmal farm yonida)", 40.7594818, 72.3532151, "+998914750028", _WH),
    ("Paytug' filiali", "Shifokorlar ko'chasi 1-uy", 40.895216, 72.256457, "+998951115044", _WH),
    ("Semashka filiali", "Mirpo'stun ko'chasi", 40.754213, 72.375309, "+998887818883", _WH),
    ("Boston filiali", "Gulbadanbegim ko'chasi 6a-uy", 40.773943, 72.384646, "+998905440028", _WH),
    ("Kanechka filiali", "Andijon shahar, Furqat ko'chasi", 40.743662, 72.336832, "+998902033903", _WH),
    ("Old Sitiy filiali", "Andijon sh., Abdurauf Fitrat 251-b", 40.785320, 72.347544, "+998944860028", _WH),
    ("Asaka filiali", "Asaka shahar, Umid ko'chasi", 40.646383, 72.24248, "+998887791001", _WH),
    ("Qo'rg'ontepa filiali", "Andijon viloyati, Qo'rg'ontepa tumani", 40.730607, 72.759374, "+998914880121", _WH),
    ("Xo'jaobod filiali", "Andijon viloyati, Xo'jaobod tumani", 40.669493, 72.558542, "+998902030028", _WH),
]


# Eski bazalar uchun migratsiya: yangi ustunlar
TECH_TASK_COLUMNS = {
    "accepted_at": "TEXT",       # texnik xodim topshiriqni qabul qilgan vaqt
    "cancel_reason": "TEXT",     # bekor qilish sababi (texnik xodimdan)
    "cancelled_at": "TEXT",
    "cancelled_by": "INTEGER",   # bekor qilgan (users.id)
    "manager_review": "TEXT",    # filial rahbari otzivi (baho bilan birga)
    "channel_chat_id": "INTEGER",     # texnik ishlar kanalidagi ochiq kartochka
    "channel_message_id": "INTEGER",  # (kim olgani text-edit bilan yangilanadi)
    "pending_transfer_to": "INTEGER", # boshqa texnikka o'tkazish taklifi (users.id)
    "prev_tech_name": "TEXT",         # o'tkazishdan oldingi ega ismi
}

APP_COLUMNS = {
    "branch_id": "INTEGER", "birth_date": "TEXT", "city": "TEXT",
    "district": "TEXT", "address": "TEXT", "position": "TEXT",
    "position_extra": "TEXT", "uniform_status": "TEXT",
    "shift": "TEXT", "education": "TEXT",
    "exp_years": "TEXT", "prev_years": "TEXT", "criminal": "TEXT",
    "marital": "TEXT", "children": "TEXT", "prev_salary": "TEXT",
    "expected_salary": "TEXT", "word_level": "TEXT", "excel_level": "TEXT",
    "computer_level": "TEXT",
    "languages": "TEXT", "work_intent": "TEXT", "reason": "TEXT",
    "resume_file_id": "TEXT", "resume_type": "TEXT",
    "favorite": "INTEGER NOT NULL DEFAULT 0",
    "offered_salary": "TEXT", "salary_offer_by": "TEXT", "salary_status": "TEXT",
    "photo_file_id": "TEXT",
    "channel_chat_id": "TEXT", "channel_message_id": "INTEGER",
    "accept_kind": "TEXT",
    "gender": "TEXT",                 # male / female — vakansiyaga moslik uchun
}

VACANCY_COLUMNS = {
    "staff_count": "TEXT",
    "experience": "TEXT",
    "manager_request_id": "INTEGER",
    "channel_chat_id": "TEXT",
    "channel_message_id": "INTEGER",
    "filled": "INTEGER NOT NULL DEFAULT 0",
    "gender": "TEXT",                 # male / female / any — kerakli xodim jinsi
}

MANAGER_REQUEST_COLUMNS = {
    "shift": "TEXT",
    "experience": "TEXT",
    "gender": "TEXT",                 # male / female / any — kerakli xodim jinsi
}

PROBATION_COLUMNS = {
    "kind": "TEXT NOT NULL DEFAULT 'trial'",
}

INTERVIEW_COLUMNS = {
    "reminder_day_sent": "INTEGER NOT NULL DEFAULT 0",
    "reminder_2h_sent": "INTEGER NOT NULL DEFAULT 0",
    "attendance": "TEXT",
    "channel_chat_id": "TEXT",
    "channel_message_id": "INTEGER",
}

USER_COLUMNS = {
    "blocked": "INTEGER NOT NULL DEFAULT 0",
    # Telegram profilidagi nom (faqat ma'lumot uchun saqlanadi)
    "tg_name": "TEXT",
    # 1 => full_name ro'yxatdan o'tishda kiritilgan haqiqiy ism.
    # Bunday holatda /start bosilganda Telegram nomi uni almashtirmaydi.
    "name_locked": "INTEGER NOT NULL DEFAULT 0",
    # Interfeys tili: uz / ru. NULL => hali tanlanmagan (/start da so'raladi).
    "lang": "TEXT",
}

BRANCH_COLUMNS = {
    "latitude": "REAL",
    "longitude": "REAL",
    "radius": "INTEGER NOT NULL DEFAULT 150",
    "phone": "TEXT",
    "work_hours": "TEXT",
}

EMPLOYEE_PROFILE_COLUMNS = {
    "birth_date": "TEXT",
    "address": "TEXT",
    "work_hours": "TEXT",
    "rest_day": "TEXT",
    "photo_file_id": "TEXT",
    "extra_info": "TEXT",
    "since": "TEXT",
    "emp_status": "TEXT NOT NULL DEFAULT 'regular'",
    "education": "TEXT",
    "shift": "TEXT",                       # smena: kunduzgi / tungi / ... (qabulda belgilanadi)
    "parent_phone": "TEXT",                # ota/ona telefoni
    "passport_front": "TEXT",              # pasport/ID oldi rasmi (maxfiy)
    "passport_back": "TEXT",               # pasport/ID orqa rasmi (maxfiy)
    "diploma_file": "TEXT",                # diplom rasmi/hujjati (maxfiy)
    "update_required": "INTEGER NOT NULL DEFAULT 0",
    "update_requested_at": "TEXT",
    "updated_by_self_at": "TEXT",
}

ATTENDANCE_COLUMNS = {
    "out_time": "TEXT",
    "out_latitude": "REAL",
    "out_longitude": "REAL",
    "out_distance": "INTEGER",
    "late": "INTEGER NOT NULL DEFAULT 0",
    "early": "INTEGER NOT NULL DEFAULT 0",
    "late_seconds": "INTEGER NOT NULL DEFAULT 0",   # kechikkan vaqt (sekund)
    "early_seconds": "INTEGER NOT NULL DEFAULT 0",  # erta ketgan vaqt (sekund)
    "on_break": "INTEGER NOT NULL DEFAULT 0",
    "break_seconds": "INTEGER NOT NULL DEFAULT 0",
    "break_started_at": "TEXT",
    "last_prompt_at": "TEXT",
}

FINES_COLUMNS = {
    "branch_id": "INTEGER",
    "period": "TEXT",
    "source": "TEXT NOT NULL DEFAULT 'finance'",
    "cancelled": "INTEGER NOT NULL DEFAULT 0",
    "cancelled_by": "INTEGER",
    "cancelled_at": "TEXT",
}

STAFF_REG_COLUMNS = {
    "phone": "TEXT",
    "reject_reason": "TEXT",
    "education": "TEXT",
    "parent_phone": "TEXT",
    "passport_front": "TEXT",
    "passport_back": "TEXT",
    "diploma_file": "TEXT",
}


async def _rebuild_applications_if_needed(db, columns):
    """Eski bazalarda vacancy_id NOT NULL bo'lib qolgan bo'lsa, jadvalni qayta yaratadi."""
    meta = {row[1]: row for row in columns}
    vacancy = meta.get("vacancy_id")
    if not vacancy or not vacancy[3]:
        return

    await db.execute("ALTER TABLE applications RENAME TO applications_old")
    await db.execute(
        """
        CREATE TABLE applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            vacancy_id INTEGER,
            branch_id INTEGER,
            full_name TEXT,
            birth_date TEXT,
            city TEXT,
            district TEXT,
            address TEXT,
            position TEXT,
            position_extra TEXT,
            uniform_status TEXT,
            shift TEXT,
            education TEXT,
            exp_years TEXT,
            prev_years TEXT,
            criminal TEXT,
            marital TEXT,
            children TEXT,
            prev_salary TEXT,
            expected_salary TEXT,
            word_level TEXT,
            excel_level TEXT,
            languages TEXT,
            work_intent TEXT,
            reason TEXT,
            phone TEXT,
            resume_file_id TEXT,
            resume_type TEXT,
            status TEXT NOT NULL DEFAULT 'new',
            hr_comment TEXT,
            handled_by INTEGER,
            created_at TEXT DEFAULT (datetime('now','+5 hours'))
        )
        """
    )

    target_cols = [
        "id", "user_id", "vacancy_id", "branch_id", "full_name", "birth_date",
        "city", "district", "address", "position", "position_extra",
        "uniform_status", "shift", "education", "exp_years", "prev_years",
        "criminal", "marital", "children", "prev_salary", "expected_salary",
        "word_level", "excel_level", "languages", "work_intent", "reason",
        "phone", "resume_file_id", "resume_type", "status", "hr_comment",
        "handled_by", "created_at",
    ]
    old_cols = set(meta)
    copy_cols = [col for col in target_cols if col in old_cols]
    cols_sql = ", ".join(copy_cols)
    await db.execute(
        f"INSERT INTO applications ({cols_sql}) SELECT {cols_sql} FROM applications_old"
    )
    await db.execute("DROP TABLE applications_old")


async def _backfill_accept_kind(db):
    """Eski arizalarda accept_kind bo'sh — uni sinov/o'rganuvchi yozuvidan tiklaymiz.

    Sinov muddati yoki o'rganuvchi yozuvi bo'lgan arizalar shu maqomni oladi,
    qolgan qabul qilinganlari esa oddiy «ishga qabul» hisoblanadi."""
    try:
        await db.execute(
            """UPDATE applications SET accept_kind = (
                   SELECT p.kind FROM probations p
                   WHERE p.application_id = applications.id
                   ORDER BY p.id DESC LIMIT 1
               )
               WHERE accept_kind IS NULL AND status='accepted'
                 AND EXISTS (SELECT 1 FROM probations p
                             WHERE p.application_id = applications.id)"""
        )
        await db.execute(
            "UPDATE applications SET accept_kind='hire' "
            "WHERE accept_kind IS NULL AND status='accepted'"
        )
    except Exception:
        pass  # probations jadvali hali yo'q bo'lsa — keyingi ishga tushishda bajariladi


async def _backfill_real_names(db):
    """Eski bazalarda users.full_name da Telegram nomi turgan bo'lishi mumkin.

    Ro'yxatdan o'tgan ismni (xodim so'rovi yoki arizadan) topib, uni asosiy
    ism qilib yozamiz va qulflaymiz — panellarda haqiqiy ism ko'rinsin.
    Xodim so'rovi arizadan ustun turadi (u yangiroq va aniqroq)."""
    try:
        # 1) Tasdiqlangan xodim so'rovidagi ism
        await db.execute(
            """UPDATE users SET full_name = (
                   SELECT sr.full_name FROM staff_regs sr
                   WHERE sr.user_id = users.id
                     AND sr.full_name IS NOT NULL AND sr.full_name != ''
                   ORDER BY sr.id DESC LIMIT 1
               ), name_locked = 1
               WHERE name_locked = 0
                 AND EXISTS (SELECT 1 FROM staff_regs sr
                             WHERE sr.user_id = users.id
                               AND sr.full_name IS NOT NULL AND sr.full_name != '')"""
        )
        # 2) Qolganlari uchun — arizadagi ism
        await db.execute(
            """UPDATE users SET full_name = (
                   SELECT a.full_name FROM applications a
                   WHERE a.user_id = users.id
                     AND a.full_name IS NOT NULL AND a.full_name != ''
                   ORDER BY a.id DESC LIMIT 1
               ), name_locked = 1
               WHERE name_locked = 0
                 AND EXISTS (SELECT 1 FROM applications a
                             WHERE a.user_id = users.id
                               AND a.full_name IS NOT NULL AND a.full_name != '')"""
        )
    except Exception:
        pass  # jadvallar hali yo'q bo'lsa — keyingi ishga tushishda bajariladi


async def _migrate(db):
    cur = await db.execute("PRAGMA table_info(applications)")
    columns = await cur.fetchall()
    await _rebuild_applications_if_needed(db, columns)

    cur = await db.execute("PRAGMA table_info(applications)")
    existing = {row[1] for row in await cur.fetchall()}
    for col, coltype in APP_COLUMNS.items():
        if col not in existing:
            await db.execute(f"ALTER TABLE applications ADD COLUMN {col} {coltype}")

    await _backfill_accept_kind(db)

    cur = await db.execute("PRAGMA table_info(interviews)")
    existing = {row[1] for row in await cur.fetchall()}
    for col, coltype in INTERVIEW_COLUMNS.items():
        if col not in existing:
            await db.execute(f"ALTER TABLE interviews ADD COLUMN {col} {coltype}")

    cur = await db.execute("PRAGMA table_info(users)")
    existing = {row[1] for row in await cur.fetchall()}
    added_name_cols = False
    for col, coltype in USER_COLUMNS.items():
        if col not in existing:
            await db.execute(f"ALTER TABLE users ADD COLUMN {col} {coltype}")
            if col == "name_locked":
                added_name_cols = True
    if added_name_cols:
        # Ustun endi qo'shildi — mavjud foydalanuvchilarning haqiqiy ismini tiklaymiz
        await _backfill_real_names(db)

    cur = await db.execute("PRAGMA table_info(branches)")
    existing = {row[1] for row in await cur.fetchall()}
    for col, coltype in BRANCH_COLUMNS.items():
        if col not in existing:
            await db.execute(f"ALTER TABLE branches ADD COLUMN {col} {coltype}")

    cur = await db.execute("PRAGMA table_info(employee_profiles)")
    existing = {row[1] for row in await cur.fetchall()}
    for col, coltype in EMPLOYEE_PROFILE_COLUMNS.items():
        if col not in existing:
            await db.execute(f"ALTER TABLE employee_profiles ADD COLUMN {col} {coltype}")

    cur = await db.execute("PRAGMA table_info(attendance)")
    existing = {row[1] for row in await cur.fetchall()}
    if existing:  # jadval mavjud bo'lsa
        for col, coltype in ATTENDANCE_COLUMNS.items():
            if col not in existing:
                await db.execute(f"ALTER TABLE attendance ADD COLUMN {col} {coltype}")

    cur = await db.execute("PRAGMA table_info(staff_regs)")
    existing = {row[1] for row in await cur.fetchall()}
    if existing:
        for col, coltype in STAFF_REG_COLUMNS.items():
            if col not in existing:
                await db.execute(f"ALTER TABLE staff_regs ADD COLUMN {col} {coltype}")

    cur = await db.execute("PRAGMA table_info(probations)")
    existing = {row[1] for row in await cur.fetchall()}
    if existing:
        for col, coltype in PROBATION_COLUMNS.items():
            if col not in existing:
                await db.execute(f"ALTER TABLE probations ADD COLUMN {col} {coltype}")

    cur = await db.execute("PRAGMA table_info(vacancies)")
    existing = {row[1] for row in await cur.fetchall()}
    if existing:
        for col, coltype in VACANCY_COLUMNS.items():
            if col not in existing:
                await db.execute(f"ALTER TABLE vacancies ADD COLUMN {col} {coltype}")

    cur = await db.execute("PRAGMA table_info(manager_requests)")
    existing = {row[1] for row in await cur.fetchall()}
    if existing:
        for col, coltype in MANAGER_REQUEST_COLUMNS.items():
            if col not in existing:
                await db.execute(f"ALTER TABLE manager_requests ADD COLUMN {col} {coltype}")

    cur = await db.execute("PRAGMA table_info(advance_requests)")
    existing = {row[1] for row in await cur.fetchall()}
    if existing and "amount" not in existing:
        await db.execute("ALTER TABLE advance_requests ADD COLUMN amount INTEGER")

    cur = await db.execute("PRAGMA table_info(tech_tasks)")
    existing = {row[1] for row in await cur.fetchall()}
    if existing:
        for col, coltype in TECH_TASK_COLUMNS.items():
            if col not in existing:
                await db.execute(f"ALTER TABLE tech_tasks ADD COLUMN {col} {coltype}")

    cur = await db.execute("PRAGMA table_info(fines)")
    existing = {row[1] for row in await cur.fetchall()}
    if existing:
        for col, coltype in FINES_COLUMNS.items():
            if col not in existing:
                await db.execute(f"ALTER TABLE fines ADD COLUMN {col} {coltype}")
        # Eski jarimalarga period ni created_at dan to'ldiramiz
        await db.execute(
            "UPDATE fines SET period=substr(created_at,1,7) "
            "WHERE period IS NULL OR period=''"
        )
    await db.commit()


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(SCHEMA)
        await db.commit()
        await _migrate(db)
        # Bosh adminlarni ro'yxatga olish / rolini yangilash
        for admin_id in SUPER_ADMINS:
            cur = await db.execute("SELECT id FROM users WHERE tg_id=?", (admin_id,))
            row = await cur.fetchone()
            if row:
                await db.execute(
                    "UPDATE users SET role=? WHERE tg_id=?", (ROLE_ADMIN, admin_id)
                )
            else:
                await db.execute(
                    "INSERT INTO users (tg_id, full_name, role) VALUES (?,?,?)",
                    (admin_id, "Bosh administrator", ROLE_ADMIN),
                )
        # Yo'nalishlar bo'sh bo'lsa standart ro'yxatni yozamiz
        cur = await db.execute("SELECT COUNT(*) FROM positions")
        if (await cur.fetchone())[0] == 0:
            for name in DEFAULT_POSITIONS:
                await db.execute("INSERT INTO positions (name) VALUES (?)", (name,))
        # Eski bazalarda "Buxgalter" yo'nalishini "Moliya bo'limi" ga o'zgartiramiz
        await db.execute(
            "UPDATE positions SET name=? WHERE name=?",
            ("🧮 Moliya bo'limi", "🧮 Buxgalter"),
        )
        # Standart filiallar — nomi bo'yicha mavjud bo'lmasa qo'shamiz (idempotent).
        # Agar avval koordinatasiz qo'shilgan bo'lsa, standart koordinata bilan to'ldiramiz
        # (admin qo'lda kiritgan koordinatalarni buzmaymiz).
        for name, address, lat, lon, phone, wh in DEFAULT_BRANCHES:
            cur = await db.execute(
                "SELECT id, latitude FROM branches WHERE name=?", (name,)
            )
            row = await cur.fetchone()
            if not row:
                await db.execute(
                    "INSERT INTO branches (name, address, latitude, longitude, phone, work_hours) "
                    "VALUES (?,?,?,?,?,?)",
                    (name, address, lat, lon, phone, wh),
                )
            elif row[1] is None:
                await db.execute(
                    "UPDATE branches SET address=?, latitude=?, longitude=?, "
                    "phone=COALESCE(phone,?), work_hours=COALESCE(work_hours,?) WHERE id=?",
                    (address, lat, lon, phone, wh, row[0]),
                )
        await db.commit()


def get_connection():
    """Har bir so'rov uchun yangi ulanish (context manager sifatida ishlatiladi)."""
    return aiosqlite.connect(DB_PATH)
