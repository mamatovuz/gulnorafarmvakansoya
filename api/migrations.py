"""API qatlami uchun DB migratsiyalari (idempotent).

Qoidalar:
  * Botning mavjud jadvallari O'ZGARTIRILMAYDI (ustun qo'shilmaydi, o'chirilmaydi).
    Yagona istisno — bot 2026-09 da ishlatishni to'xtatgan eski `attendance`
    jadvali: API davomat manbasi sifatida uni qayta ishlatadi va unga
    `source/device/verification_method/...` ustunlarini qo'shadi.
  * API ga tegishli barcha yangi jadvallar `api_` prefiksi bilan.
  * Webhook hodisalari SQLite TRIGGER lari orqali yoziladi — shuning uchun
    bot orqali qilingan o'zgarishlar (masalan HR botda xodimni tasdiqlasa) ham
    API orqali qilinganlari kabi Staffora ga yetkaziladi, botning kodiga
    tegmasdan.
"""
import aiosqlite

API_SCHEMA = """
CREATE TABLE IF NOT EXISTS api_keys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT,
    key_prefix TEXT NOT NULL UNIQUE,      -- ochiq qism (kalitni aniqlash uchun)
    key_hash TEXT NOT NULL,               -- sha256(to'liq kalit); kalitning o'zi saqlanmaydi
    scopes TEXT NOT NULL DEFAULT '',      -- bo'sh joy bilan ajratilgan ruxsatlar
    rate_limit_per_minute INTEGER,        -- NULL => umumiy sozlama
    expires_at TEXT,                      -- NULL => muddatsiz
    revoked_at TEXT,
    last_used_at TEXT,
    last_used_ip TEXT,
    created_by TEXT,
    created_at TEXT DEFAULT (datetime('now','+5 hours'))
);

CREATE TABLE IF NOT EXISTS api_idempotency (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    api_key_id INTEGER NOT NULL,
    idem_key TEXT NOT NULL,
    method TEXT NOT NULL,
    path TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'processing',  -- processing / done
    status_code INTEGER,
    response_body TEXT,
    created_at TEXT DEFAULT (datetime('now','+5 hours')),
    UNIQUE(api_key_id, idem_key)
);

-- Tashqi tizim identifikatorlari (masalan source='staffora', external_id='ST-000123')
CREATE TABLE IF NOT EXISTS api_external_ids (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL,     -- employee / branch / department / position / attendance / leave
    entity_id INTEGER NOT NULL,
    source TEXT NOT NULL,
    external_id TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now','+5 hours')),
    updated_at TEXT DEFAULT (datetime('now','+5 hours')),
    UNIQUE(entity_type, source, external_id),
    UNIQUE(entity_type, entity_id, source)
);

-- Bo'limlar (botda bo'lim tushunchasi yo'q — API orqali yangi qo'shiladi)
CREATE TABLE IF NOT EXISTS api_departments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    code TEXT UNIQUE,
    description TEXT,
    parent_id INTEGER,
    head_user_id INTEGER,              -- bo'lim rahbari (users.id)
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT DEFAULT (datetime('now','+5 hours')),
    updated_at TEXT DEFAULT (datetime('now','+5 hours'))
);

-- Xodimga oid, botda yo'q qo'shimcha maydonlar (bot jadvaliga tegmaslik uchun alohida)
CREATE TABLE IF NOT EXISTS api_employee_meta (
    user_id INTEGER PRIMARY KEY,
    department_id INTEGER,
    manager_user_id INTEGER,           -- bevosita rahbar (bo'lmasa filial rahbari olinadi)
    updated_at TEXT DEFAULT (datetime('now','+5 hours'))
);

CREATE TABLE IF NOT EXISTS api_branch_meta (
    branch_id INTEGER PRIMARY KEY,
    code TEXT UNIQUE,
    status TEXT NOT NULL DEFAULT 'active',
    updated_at TEXT DEFAULT (datetime('now','+5 hours'))
);

CREATE TABLE IF NOT EXISTS api_position_meta (
    position_id INTEGER PRIMARY KEY,
    code TEXT UNIQUE,
    description TEXT,
    department_id INTEGER,
    status TEXT NOT NULL DEFAULT 'active',
    updated_at TEXT DEFAULT (datetime('now','+5 hours'))
);

-- Hodisalar jurnali (webhook + /integration/changes uchun). TRIGGER lar yozadi.
CREATE TABLE IF NOT EXISTS api_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id INTEGER NOT NULL,
    snapshot TEXT,                     -- o'chirilgan yozuv nusxasi (JSON)
    payload TEXT,                      -- yuborilgan yakuniy "data" (JSON)
    processed INTEGER NOT NULL DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now','+5 hours')),
    processed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_api_events_pending ON api_events(processed, id);
CREATE INDEX IF NOT EXISTS idx_api_events_entity ON api_events(entity_type, entity_id, processed);

CREATE TABLE IF NOT EXISTS api_webhooks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL,
    description TEXT,
    events TEXT NOT NULL DEFAULT '*',  -- JSON ro'yxat yoki '*'
    secret TEXT NOT NULL,              -- HMAC imzo kaliti
    include_salary INTEGER NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 1,
    api_key_id INTEGER,
    created_at TEXT DEFAULT (datetime('now','+5 hours')),
    updated_at TEXT DEFAULT (datetime('now','+5 hours'))
);

CREATE TABLE IF NOT EXISTS api_webhook_deliveries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    webhook_id INTEGER NOT NULL,
    event_id INTEGER,
    event_type TEXT NOT NULL,
    payload TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',   -- pending / success / failed (qayta urinadi) / dead
    attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TEXT DEFAULT (datetime('now','+5 hours')),
    last_status_code INTEGER,
    last_error TEXT,
    created_at TEXT DEFAULT (datetime('now','+5 hours')),
    delivered_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_api_deliveries_due
    ON api_webhook_deliveries(status, next_attempt_at);

-- API orqali yaratilgan e'lonlar (bot orqali «Ishonch xabari» sifatida yuboriladi)
CREATE TABLE IF NOT EXISTS api_announcements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT,
    message TEXT NOT NULL,
    target TEXT NOT NULL,              -- JSON: {send_to_all, branch_ids, department_ids, ...}
    target_label TEXT,
    require_ack INTEGER NOT NULL DEFAULT 1,
    source TEXT,
    status TEXT NOT NULL DEFAULT 'scheduled',  -- scheduled / sending / sent / cancelled / failed
    scheduled_at TEXT,                 -- NULL => darhol
    trust_notice_id INTEGER,           -- botdagi trust_notices.id («Ko'rib chiqdim» statistikasi)
    total INTEGER NOT NULL DEFAULT 0,
    sent INTEGER NOT NULL DEFAULT 0,
    failed INTEGER NOT NULL DEFAULT 0,
    api_key_id INTEGER,
    created_at TEXT DEFAULT (datetime('now','+5 hours')),
    updated_at TEXT DEFAULT (datetime('now','+5 hours')),
    sent_at TEXT
);

CREATE TABLE IF NOT EXISTS api_announcement_recipients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    announcement_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    tg_id INTEGER,
    status TEXT NOT NULL DEFAULT 'pending',   -- pending / sent / failed
    message_id INTEGER,
    error TEXT,
    sent_at TEXT,
    UNIQUE(announcement_id, user_id)
);

-- Bitta xodimga yuboriladigan bildirishnomalar (bot orqali)
CREATE TABLE IF NOT EXISTS api_notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    tg_id INTEGER,
    title TEXT,
    message TEXT NOT NULL,
    type TEXT NOT NULL DEFAULT 'info',
    source TEXT,
    is_html INTEGER NOT NULL DEFAULT 0,        -- 1 => tizim matni (tayyor HTML); aks holda escape
    status TEXT NOT NULL DEFAULT 'queued',    -- queued / sent / failed
    attempts INTEGER NOT NULL DEFAULT 0,
    tg_message_id INTEGER,
    error TEXT,
    api_key_id INTEGER,
    created_at TEXT DEFAULT (datetime('now','+5 hours')),
    sent_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_api_notifications_user ON api_notifications(user_id);

-- Staffora dan kelgan webhooklar (event_id bo'yicha takrorlanmaslik)
CREATE TABLE IF NOT EXISTS api_inbound_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    event_id TEXT NOT NULL,
    event_type TEXT,
    payload TEXT,
    status TEXT NOT NULL DEFAULT 'received',  -- received / processed / ignored / failed
    result TEXT,
    received_at TEXT DEFAULT (datetime('now','+5 hours')),
    processed_at TEXT,
    UNIQUE(source, event_id)
);

-- Eski bot davomat jadvali (yangi bazada bot uni endi yaratmaydi). Asl sxema.
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
    created_at TEXT DEFAULT (datetime('now','+5 hours'))
);
CREATE INDEX IF NOT EXISTS idx_attendance_user_date ON attendance(user_id, date);
"""

# Eski attendance jadvaliga qo'shiladigan ustunlar
ATTENDANCE_COLUMNS = {
    "on_break": "INTEGER NOT NULL DEFAULT 0",
    "break_seconds": "INTEGER NOT NULL DEFAULT 0",
    "break_started_at": "TEXT",
    "last_prompt_at": "TEXT",
    "late_seconds": "INTEGER NOT NULL DEFAULT 0",
    "early_seconds": "INTEGER NOT NULL DEFAULT 0",
    "source": "TEXT",                  # NULL => eski bot yozuvi; api / staffora / ...
    "device": "TEXT",                  # check-in qurilmasi
    "out_device": "TEXT",
    "verification_method": "TEXT",     # gps / face / fingerprint / card / manual / qr
    "out_verification_method": "TEXT",
    "note": "TEXT",
    "updated_at": "TEXT",
}


def _coalesce(entity, types):
    """Ishlov berilmagan bir xil hodisa bo'lsa, yangisini yozmaydi (bitta PATCH
    bir nechta jadvalni o'zgartirsa ham bitta `*.updated` webhook ketadi)."""
    in_list = ",".join(f"'{t}'" for t in types)
    return (
        f"NOT EXISTS (SELECT 1 FROM api_events e WHERE e.processed=0 "
        f"AND e.entity_type='{entity}' AND e.entity_id={{eid}} "
        f"AND e.event_type IN ({in_list}))"
    )


def _ins(event, entity, eid, snapshot="NULL", guard=None):
    where = f" WHERE {guard.format(eid=eid)}" if guard else ""
    return (
        "INSERT INTO api_events (event_type, entity_type, entity_id, snapshot) "
        f"SELECT '{event}', '{entity}', {eid}, {snapshot}{where};"
    )


def _changed(cols):
    return " OR ".join(f"OLD.{c} IS NOT NEW.{c}" for c in cols)


_EMP_PROFILE_COLS = [
    "role", "position", "branch_id", "uniform_status", "monthly_salary",
    "birth_date", "address", "work_hours", "rest_day", "photo_file_id",
    "extra_info", "since", "emp_status", "education", "shift", "parent_phone",
]
_USER_COLS = ["full_name", "phone", "role", "branch_id", "username", "blocked"]

_EMP_UPD_GUARD = _coalesce("employee", ["employee.created", "employee.updated"])
_BRANCH_UPD_GUARD = _coalesce("branch", ["branch.created", "branch.updated"])
_POS_UPD_GUARD = _coalesce("position", ["position.created", "position.updated"])
_DEP_UPD_GUARD = _coalesce("department", ["department.created", "department.updated"])
_ATT_UPD_GUARD = _coalesce("attendance", ["attendance.created", "attendance.updated"])
_LEAVE_UPD_GUARD = _coalesce("leave", ["leave.created", "leave.updated"])

TRIGGERS = {
    # ---- employee ----
    "trg_api_emp_insert": f"""
        CREATE TRIGGER trg_api_emp_insert AFTER INSERT ON employee_profiles
        BEGIN {_ins('employee.created', 'employee', 'NEW.user_id')} END""",
    "trg_api_emp_update": f"""
        CREATE TRIGGER trg_api_emp_update AFTER UPDATE ON employee_profiles
        WHEN {_changed(_EMP_PROFILE_COLS)}
        BEGIN {_ins('employee.updated', 'employee', 'NEW.user_id', guard=_EMP_UPD_GUARD)} END""",
    "trg_api_emp_user_update": f"""
        CREATE TRIGGER trg_api_emp_user_update AFTER UPDATE ON users
        WHEN ({_changed(_USER_COLS)})
         AND EXISTS (SELECT 1 FROM employee_profiles WHERE user_id=NEW.id)
        BEGIN {_ins('employee.updated', 'employee', 'NEW.id', guard=_EMP_UPD_GUARD)} END""",
    "trg_api_emp_meta_insert": f"""
        CREATE TRIGGER trg_api_emp_meta_insert AFTER INSERT ON api_employee_meta
        WHEN EXISTS (SELECT 1 FROM employee_profiles WHERE user_id=NEW.user_id)
        BEGIN {_ins('employee.updated', 'employee', 'NEW.user_id', guard=_EMP_UPD_GUARD)} END""",
    "trg_api_emp_meta_update": f"""
        CREATE TRIGGER trg_api_emp_meta_update AFTER UPDATE ON api_employee_meta
        WHEN {_changed(['department_id', 'manager_user_id'])}
        BEGIN {_ins('employee.updated', 'employee', 'NEW.user_id', guard=_EMP_UPD_GUARD)} END""",
    "trg_api_emp_delete": f"""
        CREATE TRIGGER trg_api_emp_delete AFTER DELETE ON employee_profiles
        BEGIN {_ins('employee.deleted', 'employee', 'OLD.user_id', snapshot='''json_object(
            'id', OLD.user_id,
            'telegram_id', (SELECT tg_id FROM users WHERE id=OLD.user_id),
            'full_name', (SELECT full_name FROM users WHERE id=OLD.user_id),
            'phone', (SELECT phone FROM users WHERE id=OLD.user_id),
            'role', OLD.role, 'position', OLD.position, 'branch_id', OLD.branch_id,
            'hired_at', OLD.created_at)''')} END""",
    # ---- branch ----
    "trg_api_branch_insert": f"""
        CREATE TRIGGER trg_api_branch_insert AFTER INSERT ON branches
        BEGIN {_ins('branch.created', 'branch', 'NEW.id')} END""",
    "trg_api_branch_update": f"""
        CREATE TRIGGER trg_api_branch_update AFTER UPDATE ON branches
        BEGIN {_ins('branch.updated', 'branch', 'NEW.id', guard=_BRANCH_UPD_GUARD)} END""",
    "trg_api_branch_meta_insert": f"""
        CREATE TRIGGER trg_api_branch_meta_insert AFTER INSERT ON api_branch_meta
        BEGIN {_ins('branch.updated', 'branch', 'NEW.branch_id', guard=_BRANCH_UPD_GUARD)} END""",
    "trg_api_branch_meta_update": f"""
        CREATE TRIGGER trg_api_branch_meta_update AFTER UPDATE ON api_branch_meta
        BEGIN {_ins('branch.updated', 'branch', 'NEW.branch_id', guard=_BRANCH_UPD_GUARD)} END""",
    "trg_api_branch_delete": f"""
        CREATE TRIGGER trg_api_branch_delete AFTER DELETE ON branches
        BEGIN {_ins('branch.deleted', 'branch', 'OLD.id', snapshot='''json_object(
            'id', OLD.id, 'name', OLD.name, 'address', OLD.address)''')} END""",
    # ---- position ----
    "trg_api_pos_insert": f"""
        CREATE TRIGGER trg_api_pos_insert AFTER INSERT ON positions
        BEGIN {_ins('position.created', 'position', 'NEW.id')} END""",
    "trg_api_pos_update": f"""
        CREATE TRIGGER trg_api_pos_update AFTER UPDATE ON positions
        BEGIN {_ins('position.updated', 'position', 'NEW.id', guard=_POS_UPD_GUARD)} END""",
    "trg_api_pos_meta_insert": f"""
        CREATE TRIGGER trg_api_pos_meta_insert AFTER INSERT ON api_position_meta
        BEGIN {_ins('position.updated', 'position', 'NEW.position_id', guard=_POS_UPD_GUARD)} END""",
    "trg_api_pos_meta_update": f"""
        CREATE TRIGGER trg_api_pos_meta_update AFTER UPDATE ON api_position_meta
        BEGIN {_ins('position.updated', 'position', 'NEW.position_id', guard=_POS_UPD_GUARD)} END""",
    "trg_api_pos_delete": f"""
        CREATE TRIGGER trg_api_pos_delete AFTER DELETE ON positions
        BEGIN {_ins('position.deleted', 'position', 'OLD.id', snapshot='''json_object(
            'id', OLD.id, 'name', OLD.name)''')} END""",
    # ---- department ----
    "trg_api_dep_insert": f"""
        CREATE TRIGGER trg_api_dep_insert AFTER INSERT ON api_departments
        BEGIN {_ins('department.created', 'department', 'NEW.id')} END""",
    "trg_api_dep_update": f"""
        CREATE TRIGGER trg_api_dep_update AFTER UPDATE ON api_departments
        BEGIN {_ins('department.updated', 'department', 'NEW.id', guard=_DEP_UPD_GUARD)} END""",
    "trg_api_dep_delete": f"""
        CREATE TRIGGER trg_api_dep_delete AFTER DELETE ON api_departments
        BEGIN {_ins('department.deleted', 'department', 'OLD.id', snapshot='''json_object(
            'id', OLD.id, 'name', OLD.name, 'code', OLD.code)''')} END""",
    # ---- attendance ----
    "trg_api_att_insert": f"""
        CREATE TRIGGER trg_api_att_insert AFTER INSERT ON attendance
        BEGIN {_ins('attendance.created', 'attendance', 'NEW.id')} END""",
    "trg_api_att_update": f"""
        CREATE TRIGGER trg_api_att_update AFTER UPDATE ON attendance
        BEGIN {_ins('attendance.updated', 'attendance', 'NEW.id', guard=_ATT_UPD_GUARD)} END""",
    # ---- leave (dam olish kunini almashtirish so'rovlari) ----
    "trg_api_leave_insert": f"""
        CREATE TRIGGER trg_api_leave_insert AFTER INSERT ON dayoff_requests
        BEGIN {_ins('leave.created', 'leave', 'NEW.id')} END""",
    "trg_api_leave_update": f"""
        CREATE TRIGGER trg_api_leave_update AFTER UPDATE ON dayoff_requests
        BEGIN {_ins('leave.updated', 'leave', 'NEW.id', guard=_LEAVE_UPD_GUARD)} END""",
    # ---- announcement ----
    "trg_api_ann_insert": f"""
        CREATE TRIGGER trg_api_ann_insert AFTER INSERT ON api_announcements
        BEGIN {_ins('announcement.created', 'announcement', 'NEW.id')} END""",
}

# Trigger sxemasi o'zgarsa versiya oshiriladi — eski triggerlar qayta yaratiladi.
TRIGGER_VERSION = "1"


async def run_migrations(db_path):
    """Bot sxemasi mavjudligiga ishonch hosil qiladi va API jadvallarini yaratadi."""
    # Avval botning o'z sxemasi/migratsiyasi (idempotent) — yangi bazada ham ishlasin
    from database.db import init_db
    await init_db()

    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.executescript(API_SCHEMA)
        cur = await db.execute("PRAGMA table_info(attendance)")
        existing = {row[1] for row in await cur.fetchall()}
        for col, coltype in ATTENDANCE_COLUMNS.items():
            if col not in existing:
                await db.execute(f"ALTER TABLE attendance ADD COLUMN {col} {coltype}")

        cur = await db.execute("SELECT value FROM settings WHERE key='api_trigger_version'")
        row = await cur.fetchone()
        rebuild = not row or row[0] != TRIGGER_VERSION
        for name, sql in TRIGGERS.items():
            if rebuild:
                await db.execute(f"DROP TRIGGER IF EXISTS {name}")
            cur = await db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='trigger' AND name=?", (name,)
            )
            if not await cur.fetchone():
                await db.execute(sql)
        await db.execute(
            "INSERT INTO settings (key, value) VALUES ('api_trigger_version', ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (TRIGGER_VERSION,),
        )
        await db.commit()
