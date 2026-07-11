"""Ma'lumotlar bazasi ulanishi va jadvallarni yaratish."""
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
ROLE_CANDIDATE = "candidate"  # Nomzod (default)

# Ariza holatlari
ST_NEW = "new"
ST_INTERVIEW = "interview"
ST_ACCEPTED = "accepted"
ST_REJECTED = "rejected"

STATUS_LABELS = {
    ST_NEW: "🆕 Yangi",
    ST_INTERVIEW: "📅 Suhbatga chaqirilgan",
    ST_ACCEPTED: "✅ Ishga qabul qilingan",
    ST_REJECTED: "❌ Rad etilgan",
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tg_id INTEGER UNIQUE NOT NULL,
    full_name TEXT,
    username TEXT,
    phone TEXT,
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
);

CREATE TABLE IF NOT EXISTS interviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    application_id INTEGER NOT NULL,
    date TEXT,
    time TEXT,
    location TEXT,
    comment TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
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
    status TEXT NOT NULL DEFAULT 'new',
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

CREATE TABLE IF NOT EXISTS fines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_user_id INTEGER NOT NULL,
    amount TEXT NOT NULL,
    reason TEXT,
    created_by INTEGER,
    created_at TEXT DEFAULT (datetime('now','+5 hours'))
);

CREATE TABLE IF NOT EXISTS manager_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    manager_user_id INTEGER NOT NULL,
    branch_id INTEGER,
    kind TEXT NOT NULL,
    title TEXT,
    staff_count TEXT,
    details TEXT,
    status TEXT NOT NULL DEFAULT 'new',
    hr_comment TEXT,
    handled_by INTEGER,
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

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
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
    status TEXT NOT NULL DEFAULT 'active',   -- active / finished
    manager_notified INTEGER NOT NULL DEFAULT 0,
    hr_3day_sent INTEGER NOT NULL DEFAULT 0,
    hr_end_sent INTEGER NOT NULL DEFAULT 0,
    created_by INTEGER,
    created_at TEXT DEFAULT (datetime('now','+5 hours'))
);
"""

# Ishga arizadagi standart yo'nalishlar (positions jadvali bo'sh bo'lsa seed qilinadi)
DEFAULT_POSITIONS = [
    "💊 Farmatsevt", "👨‍💼 Filial rahbari", "👔 Direktor", "🧮 Buxgalter",
    "🧹 Tozalik xodimi", "📦 Omborchi", "🚚 Haydovchi",
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
APP_COLUMNS = {
    "branch_id": "INTEGER", "birth_date": "TEXT", "city": "TEXT",
    "district": "TEXT", "address": "TEXT", "position": "TEXT",
    "position_extra": "TEXT", "uniform_status": "TEXT",
    "shift": "TEXT", "education": "TEXT",
    "exp_years": "TEXT", "prev_years": "TEXT", "criminal": "TEXT",
    "marital": "TEXT", "children": "TEXT", "prev_salary": "TEXT",
    "expected_salary": "TEXT", "word_level": "TEXT", "excel_level": "TEXT",
    "languages": "TEXT", "work_intent": "TEXT", "reason": "TEXT",
    "resume_file_id": "TEXT", "resume_type": "TEXT",
    "favorite": "INTEGER NOT NULL DEFAULT 0",
}

INTERVIEW_COLUMNS = {
    "reminder_day_sent": "INTEGER NOT NULL DEFAULT 0",
    "reminder_2h_sent": "INTEGER NOT NULL DEFAULT 0",
}

USER_COLUMNS = {
    "blocked": "INTEGER NOT NULL DEFAULT 0",
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
}

ATTENDANCE_COLUMNS = {
    "out_time": "TEXT",
    "out_latitude": "REAL",
    "out_longitude": "REAL",
    "out_distance": "INTEGER",
    "late": "INTEGER NOT NULL DEFAULT 0",
    "early": "INTEGER NOT NULL DEFAULT 0",
    "on_break": "INTEGER NOT NULL DEFAULT 0",
    "break_seconds": "INTEGER NOT NULL DEFAULT 0",
    "break_started_at": "TEXT",
    "last_prompt_at": "TEXT",
}

STAFF_REG_COLUMNS = {
    "phone": "TEXT",
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


async def _migrate(db):
    cur = await db.execute("PRAGMA table_info(applications)")
    columns = await cur.fetchall()
    await _rebuild_applications_if_needed(db, columns)

    cur = await db.execute("PRAGMA table_info(applications)")
    existing = {row[1] for row in await cur.fetchall()}
    for col, coltype in APP_COLUMNS.items():
        if col not in existing:
            await db.execute(f"ALTER TABLE applications ADD COLUMN {col} {coltype}")

    cur = await db.execute("PRAGMA table_info(interviews)")
    existing = {row[1] for row in await cur.fetchall()}
    for col, coltype in INTERVIEW_COLUMNS.items():
        if col not in existing:
            await db.execute(f"ALTER TABLE interviews ADD COLUMN {col} {coltype}")

    cur = await db.execute("PRAGMA table_info(users)")
    existing = {row[1] for row in await cur.fetchall()}
    for col, coltype in USER_COLUMNS.items():
        if col not in existing:
            await db.execute(f"ALTER TABLE users ADD COLUMN {col} {coltype}")

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
