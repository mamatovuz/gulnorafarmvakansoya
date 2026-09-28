"""Gulnora Farm HR web app.

This app runs next to the Telegram bot and uses the same SQLite database.
It intentionally depends only on the Python standard library so it can start
without installing another framework.
"""
from __future__ import annotations

import base64
import csv
import hashlib
import hmac
import json
import math
import mimetypes
import os
import re
import secrets
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parent
WEB_ROOT = ROOT / "web"
DB_PATH = Path(os.getenv("DB_PATH", ROOT / "hrbot.db")).resolve()
APP_HOST = os.getenv("APP_HOST", "127.0.0.1")
APP_PORT = int(os.getenv("APP_PORT", "8088"))
TZ = timezone(timedelta(hours=5))
TOKEN_TTL_SECONDS = 60 * 60 * 24 * 14
APP_SECRET = (
    os.getenv("APP_SECRET")
    or os.getenv("BOT_TOKEN")
    or hashlib.sha256(str(DB_PATH).encode("utf-8")).hexdigest()
)

ROLE_ADMIN = "admin"
ROLE_HR = "hr"
ROLE_MANAGER = "manager"
ROLE_EMPLOYEE = "employee"
ROLE_PHARMACIST = "pharmacist"
ROLE_DIRECTOR = "director"
ROLE_ACCOUNTANT = "accountant"
ROLE_IT = "it"
ROLE_TECH = "tech"
ROLE_CANDIDATE = "candidate"

STAFF_ROLES = {
    ROLE_ADMIN,
    ROLE_HR,
    ROLE_MANAGER,
    ROLE_EMPLOYEE,
    ROLE_PHARMACIST,
    ROLE_DIRECTOR,
    ROLE_ACCOUNTANT,
    ROLE_IT,
    ROLE_TECH,
}
PEOPLE_ROLES = {ROLE_ADMIN, ROLE_HR, ROLE_MANAGER, ROLE_DIRECTOR, ROLE_ACCOUNTANT, ROLE_IT}
HR_ROLES = {ROLE_ADMIN, ROLE_HR}
LEAD_ROLES = {ROLE_ADMIN, ROLE_HR, ROLE_MANAGER, ROLE_DIRECTOR}
FINANCE_ROLES = {ROLE_ADMIN, ROLE_HR, ROLE_ACCOUNTANT, ROLE_DIRECTOR}

STATUS_LABELS = {
    "new": "Yangi",
    "pending": "Kutilmoqda",
    "approved": "Tasdiqlangan",
    "accepted": "Qabul qilingan",
    "rejected": "Rad etilgan",
    "interview": "Suhbat",
    "waiting": "Kutuvda",
    "confirmed": "Tasdiqlangan",
    "declined": "Rad etilgan",
    "closed": "Yopilgan",
    "done": "Bajarilgan",
}

ROLE_LABELS = {
    ROLE_ADMIN: "Administrator",
    ROLE_HR: "HR",
    ROLE_MANAGER: "Filial rahbari",
    ROLE_EMPLOYEE: "Xodim",
    ROLE_PHARMACIST: "Farmatsevt",
    ROLE_DIRECTOR: "Direktor",
    ROLE_ACCOUNTANT: "Moliya",
    ROLE_IT: "IT",
    ROLE_TECH: "Texnik",
    ROLE_CANDIDATE: "Nomzod",
}

ALLOWED_PROFILE_FIELDS = {
    "phone": ("users", "phone"),
    "address": ("employee_profiles", "address"),
    "parent_phone": ("employee_profiles", "parent_phone"),
    "work_hours": ("employee_profiles", "work_hours"),
    "rest_day": ("employee_profiles", "rest_day"),
    "education": ("employee_profiles", "education"),
    "uniform_status": ("employee_profiles", "uniform_status"),
}


class AppError(Exception):
    def __init__(self, status: int, message: str, details: Any | None = None):
        super().__init__(message)
        self.status = status
        self.message = message
        self.details = details


def now() -> datetime:
    return datetime.now(TZ)


def now_sql() -> str:
    return now().strftime("%Y-%m-%d %H:%M:%S")


def today_sql() -> str:
    return now().strftime("%Y-%m-%d")


def month_sql() -> str:
    return now().strftime("%Y-%m")


def db() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH, timeout=8, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA busy_timeout=8000")
    return con


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row else None


def rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def table_exists(con: sqlite3.Connection, name: str) -> bool:
    row = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return bool(row)


def has_column(con: sqlite3.Connection, table: str, column: str) -> bool:
    try:
        rows = con.execute(f"PRAGMA table_info({table})").fetchall()
    except sqlite3.Error:
        return False
    return any(row["name"] == column for row in rows)


def init_app_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with db() as con:
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS app_attendance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                branch_id INTEGER,
                work_date TEXT NOT NULL,
                check_in_at TEXT,
                check_out_at TEXT,
                break_started_at TEXT,
                break_total_minutes INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'open',
                check_in_lat REAL,
                check_in_lon REAL,
                check_out_lat REAL,
                check_out_lon REAL,
                distance_m INTEGER,
                checkout_distance_m INTEGER,
                note TEXT,
                created_at TEXT DEFAULT (datetime('now','+5 hours')),
                updated_at TEXT DEFAULT (datetime('now','+5 hours')),
                UNIQUE(user_id, work_date)
            );
            CREATE INDEX IF NOT EXISTS idx_app_attendance_user_date
                ON app_attendance(user_id, work_date);

            CREATE TABLE IF NOT EXISTS app_notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                body TEXT,
                target_type TEXT NOT NULL DEFAULT 'all',
                target_value TEXT,
                sender_id INTEGER,
                sender_name TEXT,
                created_at TEXT DEFAULT (datetime('now','+5 hours'))
            );
            CREATE TABLE IF NOT EXISTS app_notification_reads (
                notification_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                read_at TEXT DEFAULT (datetime('now','+5 hours')),
                PRIMARY KEY(notification_id, user_id)
            );

            CREATE TABLE IF NOT EXISTS app_hr_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                branch_id INTEGER,
                subject TEXT,
                message TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'new',
                handled_by INTEGER,
                response TEXT,
                created_at TEXT DEFAULT (datetime('now','+5 hours')),
                updated_at TEXT DEFAULT (datetime('now','+5 hours'))
            );
            """
        )
        ensure_app_schema(con)
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_app_notifications_target "
            "ON app_notifications(target_type, target_value)"
        )
        con.commit()


def ensure_app_schema(con: sqlite3.Connection) -> None:
    """Bring earlier app-only tables up to the current shape."""
    migrations = {
        "app_attendance": {
            "branch_id": "INTEGER",
            "work_date": "TEXT",
            "check_in_at": "TEXT",
            "check_out_at": "TEXT",
            "break_started_at": "TEXT",
            "break_total_minutes": "INTEGER NOT NULL DEFAULT 0",
            "status": "TEXT NOT NULL DEFAULT 'open'",
            "check_in_lat": "REAL",
            "check_in_lon": "REAL",
            "check_out_lat": "REAL",
            "check_out_lon": "REAL",
            "distance_m": "INTEGER",
            "checkout_distance_m": "INTEGER",
            "note": "TEXT",
            "created_at": "TEXT",
            "updated_at": "TEXT",
        },
        "app_notifications": {
            "title": "TEXT",
            "body": "TEXT",
            "target_type": "TEXT NOT NULL DEFAULT 'all'",
            "target_value": "TEXT",
            "sender_id": "INTEGER",
            "sender_name": "TEXT",
            "created_at": "TEXT",
        },
        "app_notification_reads": {
            "notification_id": "INTEGER",
            "user_id": "INTEGER",
            "read_at": "TEXT",
        },
        "app_hr_messages": {
            "user_id": "INTEGER",
            "branch_id": "INTEGER",
            "subject": "TEXT",
            "message": "TEXT",
            "status": "TEXT NOT NULL DEFAULT 'new'",
            "handled_by": "INTEGER",
            "response": "TEXT",
            "created_at": "TEXT",
            "updated_at": "TEXT",
        },
    }
    for table, columns in migrations.items():
        if not table_exists(con, table):
            continue
        for column, definition in columns.items():
            if not has_column(con, table, column):
                con.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
    con.execute("UPDATE app_notifications SET target_type='all' WHERE target_type IS NULL OR target_type=''")
    con.execute("UPDATE app_attendance SET status='open' WHERE status IS NULL OR status=''")


def safe_int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def clean_text(value: Any, max_len: int = 800) -> str:
    text = "" if value is None else str(value)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_len]


def sql_count(con: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> int:
    try:
        row = con.execute(sql, params).fetchone()
        return int(row[0]) if row else 0
    except sqlite3.Error:
        return 0


def status_label(value: Any) -> str:
    return STATUS_LABELS.get(str(value or "").lower(), str(value or "-"))


def role_label(value: Any) -> str:
    return ROLE_LABELS.get(str(value or ""), str(value or "Nomzod"))


def b64_json(data: dict[str, Any]) -> str:
    raw = json.dumps(data, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def unb64_json(data: str) -> dict[str, Any]:
    padded = data + "=" * (-len(data) % 4)
    raw = base64.urlsafe_b64decode(padded.encode("ascii"))
    return json.loads(raw.decode("utf-8"))


def sign(payload: str) -> str:
    mac = hmac.new(APP_SECRET.encode("utf-8"), payload.encode("ascii"), hashlib.sha256)
    return base64.urlsafe_b64encode(mac.digest()).decode("ascii").rstrip("=")


def make_token(user: dict[str, Any]) -> str:
    payload = b64_json(
        {
            "uid": user["id"],
            "tg_id": user.get("tg_id"),
            "role": user.get("role"),
            "exp": int(time.time()) + TOKEN_TTL_SECONDS,
            "nonce": secrets.token_hex(8),
        }
    )
    return f"{payload}.{sign(payload)}"


def verify_token(token: str) -> dict[str, Any]:
    if not token or "." not in token:
        raise AppError(HTTPStatus.UNAUTHORIZED, "Kirish talab qilinadi.")
    payload, signature = token.split(".", 1)
    if not hmac.compare_digest(signature, sign(payload)):
        raise AppError(HTTPStatus.UNAUTHORIZED, "Sessiya noto'g'ri.")
    data = unb64_json(payload)
    if int(data.get("exp", 0)) < int(time.time()):
        raise AppError(HTTPStatus.UNAUTHORIZED, "Sessiya muddati tugagan.")
    return data


def get_auth_user(headers: dict[str, str]) -> dict[str, Any]:
    auth = headers.get("authorization", "")
    token = auth[7:] if auth.lower().startswith("bearer ") else ""
    data = verify_token(token)
    with db() as con:
        user = row_to_dict(con.execute("SELECT * FROM users WHERE id=?", (data["uid"],)).fetchone())
    if not user:
        raise AppError(HTTPStatus.UNAUTHORIZED, "Foydalanuvchi topilmadi.")
    if user.get("blocked"):
        raise AppError(HTTPStatus.FORBIDDEN, "Foydalanuvchi bloklangan.")
    return user


def require_role(user: dict[str, Any], roles: set[str]) -> None:
    if user.get("role") not in roles:
        raise AppError(HTTPStatus.FORBIDDEN, "Bu amal uchun ruxsat yo'q.")


def can_view_branch(user: dict[str, Any], branch_id: Any) -> bool:
    if user.get("role") in {ROLE_ADMIN, ROLE_HR, ROLE_DIRECTOR, ROLE_ACCOUNTANT, ROLE_IT}:
        return True
    if user.get("role") == ROLE_MANAGER:
        return safe_int(branch_id) == safe_int(user.get("branch_id"))
    return False


def get_profile(con: sqlite3.Connection, user_id: int) -> dict[str, Any] | None:
    row = con.execute(
        """
        SELECT ep.*, u.tg_id, u.full_name, u.username, u.phone, u.role AS user_role,
               u.branch_id AS user_branch_id, b.name AS branch_name, b.address AS branch_address,
               b.latitude, b.longitude, b.radius, b.work_hours AS branch_work_hours
          FROM employee_profiles ep
          JOIN users u ON u.id=ep.user_id
          LEFT JOIN branches b ON b.id=ep.branch_id
         WHERE ep.user_id=?
        """,
        (user_id,),
    ).fetchone()
    return row_to_dict(row)


def public_user(user: dict[str, Any], profile: dict[str, Any] | None = None) -> dict[str, Any]:
    branch_id = user.get("branch_id") or (profile or {}).get("branch_id")
    return {
        "id": user.get("id"),
        "tg_id": user.get("tg_id"),
        "full_name": user.get("full_name") or "Foydalanuvchi",
        "username": user.get("username"),
        "phone": user.get("phone"),
        "role": user.get("role"),
        "role_label": role_label(user.get("role")),
        "branch_id": branch_id,
        "branch_name": (profile or {}).get("branch_name"),
        "is_staff": user.get("role") in STAFF_ROLES,
        "permissions": {
            "hr": user.get("role") in HR_ROLES,
            "people": user.get("role") in PEOPLE_ROLES,
            "lead": user.get("role") in LEAD_ROLES,
            "finance": user.get("role") in FINANCE_ROLES,
            "manager": user.get("role") == ROLE_MANAGER,
            "admin": user.get("role") == ROLE_ADMIN,
        },
    }


def parse_phone_or_tg(identifier: str) -> tuple[str, str]:
    text = clean_text(identifier, 80)
    if not text:
        raise AppError(HTTPStatus.BAD_REQUEST, "Telegram ID yoki telefon kiriting.")
    digits = "".join(ch for ch in text if ch.isdigit())
    if len(digits) >= 7 and not text.startswith("@"):
        return "phone", digits
    return "tg_id", text.lstrip("@")


def normalize_phone_for_sql(column: str) -> str:
    expr = column
    for char in ["+", " ", "-", "(", ")"]:
        expr = f"replace({expr},'{char}','')"
    return expr


def api_login(data: dict[str, Any]) -> dict[str, Any]:
    text = clean_text(data.get("identifier"), 80)
    if not text:
        raise AppError(HTTPStatus.BAD_REQUEST, "Telegram ID yoki telefon kiriting.")
    digits = "".join(ch for ch in text if ch.isdigit())
    username = text.lstrip("@")
    user = None
    with db() as con:
        if re.fullmatch(r"-?\d+", text):
            user = row_to_dict(con.execute("SELECT * FROM users WHERE tg_id=?", (int(text),)).fetchone())
        if not user and digits and text.startswith("+"):
            expr = normalize_phone_for_sql("phone")
            user = row_to_dict(
                con.execute(f"SELECT * FROM users WHERE {expr} LIKE ? ORDER BY id DESC LIMIT 1", (f"%{digits[-9:]}",)).fetchone()
            )
        if not user and digits and len(digits) >= 9:
            expr = normalize_phone_for_sql("phone")
            user = row_to_dict(
                con.execute(f"SELECT * FROM users WHERE {expr} LIKE ? ORDER BY id DESC LIMIT 1", (f"%{digits[-9:]}",)).fetchone()
            )
        if not user and username:
            user = row_to_dict(
                con.execute(
                    "SELECT * FROM users WHERE lower(username)=lower(?) ORDER BY id DESC LIMIT 1",
                    (username,),
                ).fetchone()
            )
        if not user:
            raise AppError(HTTPStatus.NOT_FOUND, "Bazada bunday foydalanuvchi topilmadi.")
        profile = get_profile(con, user["id"])
    return {"token": make_token(user), "user": public_user(user, profile)}


def today_attendance(con: sqlite3.Connection, user_id: int) -> dict[str, Any] | None:
    row = con.execute(
        "SELECT * FROM app_attendance WHERE user_id=? AND work_date=?",
        (user_id, today_sql()),
    ).fetchone()
    return row_to_dict(row)


def parse_work_hours(text: str | None) -> tuple[str, str] | None:
    if not text:
        return None
    match = re.search(r"(\d{1,2})(?::(\d{2}))?\s*[-–—]\s*(\d{1,2})(?::(\d{2}))?", text)
    if not match:
        return None
    h1, m1, h2, m2 = match.group(1), match.group(2) or "00", match.group(3), match.group(4) or "00"
    try:
        start = f"{int(h1):02d}:{int(m1):02d}"
        end = f"{int(h2):02d}:{int(m2):02d}"
    except ValueError:
        return None
    return start, end


def minutes_since_midnight(value: str) -> int:
    hh, mm = value.split(":")
    return int(hh) * 60 + int(mm)


def work_flags(profile: dict[str, Any] | None, check_type: str) -> str:
    hours = parse_work_hours((profile or {}).get("work_hours") or (profile or {}).get("branch_work_hours"))
    if not hours:
        return ""
    start, end = hours
    current = now().hour * 60 + now().minute
    if check_type == "in" and current > minutes_since_midnight(start) + 5:
        return "late"
    if check_type == "out" and current < minutes_since_midnight(end) - 5:
        return "early"
    return ""


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> int:
    radius = 6371000
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return int(radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))


def location_result(profile: dict[str, Any] | None, lat: Any, lon: Any) -> dict[str, Any]:
    if lat is None or lon is None:
        raise AppError(HTTPStatus.BAD_REQUEST, "GPS joylashuv kerak.")
    try:
        user_lat = float(lat)
        user_lon = float(lon)
    except (TypeError, ValueError):
        raise AppError(HTTPStatus.BAD_REQUEST, "GPS koordinata noto'g'ri.")
    branch_lat = (profile or {}).get("latitude")
    branch_lon = (profile or {}).get("longitude")
    radius = safe_int((profile or {}).get("radius")) or 150
    if branch_lat is None or branch_lon is None:
        return {
            "ok": True,
            "lat": user_lat,
            "lon": user_lon,
            "distance_m": None,
            "radius": radius,
            "message": "Filial GPS koordinatasi kiritilmagan.",
        }
    distance = haversine_m(user_lat, user_lon, float(branch_lat), float(branch_lon))
    return {
        "ok": distance <= radius,
        "lat": user_lat,
        "lon": user_lon,
        "distance_m": distance,
        "radius": radius,
        "message": f"Masofa {distance} m, ruxsat {radius} m.",
    }


def api_me(user: dict[str, Any]) -> dict[str, Any]:
    with db() as con:
        profile = get_profile(con, user["id"])
        attendance = today_attendance(con, user["id"])
        counts = dashboard_counts(con, user, profile)
    return {
        "user": public_user(user, profile),
        "profile": profile,
        "attendance": attendance,
        "counts": counts,
        "server_time": now_sql(),
    }


def dashboard_counts(con: sqlite3.Connection, user: dict[str, Any], profile: dict[str, Any] | None) -> dict[str, int]:
    role = user.get("role")
    branch_id = user.get("branch_id") or (profile or {}).get("branch_id")
    counts = {
        "vacancies": sql_count(con, "SELECT COUNT(*) FROM vacancies WHERE is_active=1 AND COALESCE(filled,0)=0"),
        "my_applications": sql_count(con, "SELECT COUNT(*) FROM applications WHERE user_id=?", (user["id"],)),
        "notifications": count_notifications(con, user, unread_only=True),
        "attendance_month": sql_count(
            con,
            "SELECT COUNT(*) FROM app_attendance WHERE user_id=? AND substr(work_date,1,7)=?",
            (user["id"], month_sql()),
        ),
    }
    if role in HR_ROLES | {ROLE_DIRECTOR, ROLE_ACCOUNTANT, ROLE_IT}:
        counts.update(
            {
                "employees": sql_count(con, "SELECT COUNT(*) FROM employee_profiles"),
                "new_apps": sql_count(con, "SELECT COUNT(*) FROM applications WHERE status='new'"),
                "dayoff_new": sql_count(con, "SELECT COUNT(*) FROM dayoff_requests WHERE status='new'"),
                "staff_regs": sql_count(con, "SELECT COUNT(*) FROM staff_regs WHERE status='new'"),
                "attendance_today": sql_count(
                    con, "SELECT COUNT(*) FROM app_attendance WHERE work_date=?", (today_sql(),)
                ),
            }
        )
    elif role == ROLE_MANAGER and branch_id:
        counts.update(
            {
                "employees": sql_count(con, "SELECT COUNT(*) FROM employee_profiles WHERE branch_id=?", (branch_id,)),
                "new_apps": sql_count(con, "SELECT COUNT(*) FROM applications WHERE status='new' AND branch_id=?", (branch_id,)),
                "dayoff_new": sql_count(
                    con, "SELECT COUNT(*) FROM dayoff_requests WHERE status='new' AND branch_id=?", (branch_id,)
                ),
                "attendance_today": sql_count(
                    con,
                    "SELECT COUNT(*) FROM app_attendance WHERE work_date=? AND branch_id=?",
                    (today_sql(), branch_id),
                ),
            }
        )
    return counts


def api_home(user: dict[str, Any]) -> dict[str, Any]:
    with db() as con:
        profile = get_profile(con, user["id"])
        counts = dashboard_counts(con, user, profile)
        latest_apps = list_applications(con, user, {"limit": "5"})
        latest_reqs = list_requests(con, user, {"limit": "6"})
        notices = list_notifications(con, user, limit=5)
    return {
        "counts": counts,
        "applications": latest_apps,
        "requests": latest_reqs,
        "notifications": notices,
    }


def api_attendance_today(user: dict[str, Any]) -> dict[str, Any]:
    with db() as con:
        profile = get_profile(con, user["id"])
        row = today_attendance(con, user["id"])
        history = rows_to_dicts(
            con.execute(
                """
                SELECT * FROM app_attendance
                 WHERE user_id=?
                 ORDER BY work_date DESC
                 LIMIT 14
                """,
                (user["id"],),
            ).fetchall()
        )
    return {"today": row, "history": history, "profile": profile}


def api_attendance_action(user: dict[str, Any], action: str, data: dict[str, Any]) -> dict[str, Any]:
    if user.get("role") not in STAFF_ROLES:
        raise AppError(HTTPStatus.FORBIDDEN, "Davomat faqat xodimlar uchun.")
    with db() as con:
        profile = get_profile(con, user["id"])
        branch_id = user.get("branch_id") or (profile or {}).get("branch_id")
        existing = today_attendance(con, user["id"])
        if action in {"checkin", "checkout"}:
            loc = location_result(profile, data.get("lat"), data.get("lon"))
            if not loc["ok"]:
                raise AppError(HTTPStatus.BAD_REQUEST, "Siz filial hududida emassiz.", loc)
        else:
            loc = {"lat": None, "lon": None, "distance_m": None, "message": ""}

        if action == "checkin":
            if existing and existing.get("check_in_at"):
                return {"attendance": existing, "message": "Bugun kelish qayd qilingan."}
            flag = work_flags(profile, "in")
            note = "Kechikdi" if flag == "late" else "Vaqtida"
            con.execute(
                """
                INSERT INTO app_attendance
                    (user_id, branch_id, work_date, check_in_at, status,
                     check_in_lat, check_in_lon, distance_m, note, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(user_id, work_date) DO UPDATE SET
                    check_in_at=excluded.check_in_at,
                    status='open',
                    check_in_lat=excluded.check_in_lat,
                    check_in_lon=excluded.check_in_lon,
                    distance_m=excluded.distance_m,
                    note=excluded.note,
                    updated_at=excluded.updated_at
                """,
                (
                    user["id"],
                    branch_id,
                    today_sql(),
                    now_sql(),
                    "open",
                    loc["lat"],
                    loc["lon"],
                    loc["distance_m"],
                    note,
                    now_sql(),
                ),
            )
            con.execute(
                "INSERT INTO audit_logs (tg_id, actor_name, action, details) VALUES (?,?,?,?)",
                (user.get("tg_id"), user.get("full_name"), "app_checkin", loc["message"]),
            )
        elif action == "checkout":
            if not existing or not existing.get("check_in_at"):
                raise AppError(HTTPStatus.BAD_REQUEST, "Avval ishga kelishni qayd qiling.")
            if existing.get("check_out_at"):
                return {"attendance": existing, "message": "Bugun ketish qayd qilingan."}
            flag = work_flags(profile, "out")
            note = clean_text(" / ".join(x for x in [existing.get("note"), "Erta ketdi" if flag == "early" else "Ketish"] if x), 200)
            break_minutes = safe_int(existing.get("break_total_minutes")) or 0
            if existing.get("break_started_at"):
                started = datetime.strptime(existing["break_started_at"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=TZ)
                break_minutes += max(0, int((now() - started).total_seconds() // 60))
            con.execute(
                """
                UPDATE app_attendance
                   SET check_out_at=?, status='closed', check_out_lat=?, check_out_lon=?,
                       checkout_distance_m=?, break_started_at=NULL,
                       break_total_minutes=?, note=?, updated_at=?
                 WHERE id=?
                """,
                (
                    now_sql(),
                    loc["lat"],
                    loc["lon"],
                    loc["distance_m"],
                    break_minutes,
                    note,
                    now_sql(),
                    existing["id"],
                ),
            )
            con.execute(
                "INSERT INTO audit_logs (tg_id, actor_name, action, details) VALUES (?,?,?,?)",
                (user.get("tg_id"), user.get("full_name"), "app_checkout", loc["message"]),
            )
        elif action == "break_start":
            if not existing or not existing.get("check_in_at") or existing.get("check_out_at"):
                raise AppError(HTTPStatus.BAD_REQUEST, "Tanaffus uchun ochiq ish kuni kerak.")
            if existing.get("break_started_at"):
                return {"attendance": existing, "message": "Tanaffus allaqachon boshlangan."}
            con.execute(
                "UPDATE app_attendance SET break_started_at=?, updated_at=? WHERE id=?",
                (now_sql(), now_sql(), existing["id"]),
            )
        elif action == "break_end":
            if not existing or not existing.get("break_started_at"):
                raise AppError(HTTPStatus.BAD_REQUEST, "Boshlangan tanaffus topilmadi.")
            started = datetime.strptime(existing["break_started_at"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=TZ)
            minutes = max(0, int((now() - started).total_seconds() // 60))
            total = (safe_int(existing.get("break_total_minutes")) or 0) + minutes
            con.execute(
                """
                UPDATE app_attendance
                   SET break_started_at=NULL, break_total_minutes=?, updated_at=?
                 WHERE id=?
                """,
                (total, now_sql(), existing["id"]),
            )
        else:
            raise AppError(HTTPStatus.NOT_FOUND, "Noma'lum davomat amali.")
        con.commit()
        row = today_attendance(con, user["id"])
    return {"attendance": row, "message": "Qayd qilindi."}


def api_attendance_report(user: dict[str, Any], params: dict[str, str]) -> dict[str, Any]:
    require_role(user, LEAD_ROLES | {ROLE_ACCOUNTANT, ROLE_IT})
    branch_id = safe_int(params.get("branch_id"))
    date = params.get("date") or today_sql()
    with db() as con:
        base = """
            SELECT aa.*, u.full_name, u.phone, ep.position, b.name AS branch_name
              FROM app_attendance aa
              JOIN users u ON u.id=aa.user_id
              LEFT JOIN employee_profiles ep ON ep.user_id=aa.user_id
              LEFT JOIN branches b ON b.id=aa.branch_id
             WHERE aa.work_date=?
        """
        sql = base
        args: list[Any] = [date]
        if user.get("role") == ROLE_MANAGER:
            branch_id = safe_int(user.get("branch_id"))
        if branch_id:
            sql += " AND aa.branch_id=?"
            args.append(branch_id)
        sql += " ORDER BY aa.check_in_at DESC"
        rows = rows_to_dicts(con.execute(sql, args).fetchall())
        branch_arg = branch_id
        total_staff = (
            sql_count(con, "SELECT COUNT(*) FROM employee_profiles WHERE branch_id=?", (branch_arg,))
            if branch_arg
            else sql_count(con, "SELECT COUNT(*) FROM employee_profiles")
        )
    return {
        "date": date,
        "items": rows,
        "summary": {
            "came": len(rows),
            "closed": len([r for r in rows if r.get("check_out_at")]),
            "open": len([r for r in rows if r.get("check_in_at") and not r.get("check_out_at")]),
            "staff": total_staff,
            "absent": max(total_staff - len({r["user_id"] for r in rows}), 0),
        },
    }


def list_vacancies(con: sqlite3.Connection, params: dict[str, str] | None = None) -> list[dict[str, Any]]:
    params = params or {}
    show_all = params.get("all") == "1"
    limit = min(safe_int(params.get("limit")) or 50, 200)
    sql = """
        SELECT v.*, b.name AS branch_name
          FROM vacancies v
          LEFT JOIN branches b ON b.id=v.branch_id
         WHERE 1=1
    """
    args: list[Any] = []
    if not show_all:
        sql += " AND v.is_active=1 AND COALESCE(v.filled,0)=0"
    if params.get("q"):
        sql += " AND (lower(v.title) LIKE lower(?) OR lower(b.name) LIKE lower(?))"
        like = f"%{params['q']}%"
        args.extend([like, like])
    sql += " ORDER BY v.id DESC LIMIT ?"
    args.append(limit)
    return rows_to_dicts(con.execute(sql, args).fetchall())


def api_vacancies(user: dict[str, Any], params: dict[str, str]) -> dict[str, Any]:
    with db() as con:
        rows = list_vacancies(con, params)
    return {"items": rows}


def api_create_vacancy(user: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    require_role(user, HR_ROLES | {ROLE_MANAGER})
    title = clean_text(data.get("title"), 160)
    if len(title) < 2:
        raise AppError(HTTPStatus.BAD_REQUEST, "Vakansiya nomini kiriting.")
    branch_id = safe_int(data.get("branch_id")) or safe_int(user.get("branch_id"))
    if user.get("role") == ROLE_MANAGER:
        branch_id = safe_int(user.get("branch_id"))
    with db() as con:
        cur = con.execute(
            """
            INSERT INTO vacancies
                (title, branch_id, job_type, shift, salary, work_time, requirements,
                 responsibilities, conditions, staff_count, experience, gender,
                 is_active, created_by)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,1,?)
            """,
            (
                title,
                branch_id,
                clean_text(data.get("job_type"), 80),
                clean_text(data.get("shift"), 80),
                clean_text(data.get("salary"), 80),
                clean_text(data.get("work_time"), 80),
                clean_text(data.get("requirements"), 1200),
                clean_text(data.get("responsibilities"), 1200),
                clean_text(data.get("conditions"), 1200),
                clean_text(data.get("staff_count"), 40),
                clean_text(data.get("experience"), 160),
                clean_text(data.get("gender"), 30) or "any",
                user["id"],
            ),
        )
        con.execute(
            "INSERT INTO audit_logs (tg_id, actor_name, action, details) VALUES (?,?,?,?)",
            (user.get("tg_id"), user.get("full_name"), "app_vacancy_create", f"#{cur.lastrowid}: {title}"),
        )
        con.commit()
        item = row_to_dict(
            con.execute(
                "SELECT v.*, b.name AS branch_name FROM vacancies v LEFT JOIN branches b ON b.id=v.branch_id WHERE v.id=?",
                (cur.lastrowid,),
            ).fetchone()
        )
    return {"item": item}


def api_update_vacancy(user: dict[str, Any], vid: int, data: dict[str, Any]) -> dict[str, Any]:
    require_role(user, HR_ROLES | {ROLE_MANAGER})
    allowed = {
        "title",
        "branch_id",
        "job_type",
        "shift",
        "salary",
        "work_time",
        "requirements",
        "responsibilities",
        "conditions",
        "staff_count",
        "experience",
        "gender",
        "is_active",
        "filled",
    }
    fields = [key for key in data if key in allowed]
    if not fields:
        raise AppError(HTTPStatus.BAD_REQUEST, "Yangilash uchun maydon yo'q.")
    with db() as con:
        old = row_to_dict(con.execute("SELECT * FROM vacancies WHERE id=?", (vid,)).fetchone())
        if not old:
            raise AppError(HTTPStatus.NOT_FOUND, "Vakansiya topilmadi.")
        if user.get("role") == ROLE_MANAGER and safe_int(old.get("branch_id")) != safe_int(user.get("branch_id")):
            raise AppError(HTTPStatus.FORBIDDEN, "Bu filial vakansiyasi emas.")
        set_sql = ", ".join(f"{field}=?" for field in fields)
        values = [data[field] for field in fields]
        values.append(vid)
        con.execute(f"UPDATE vacancies SET {set_sql} WHERE id=?", values)
        con.commit()
        item = row_to_dict(
            con.execute(
                "SELECT v.*, b.name AS branch_name FROM vacancies v LEFT JOIN branches b ON b.id=v.branch_id WHERE v.id=?",
                (vid,),
            ).fetchone()
        )
    return {"item": item}


def application_scope_sql(user: dict[str, Any]) -> tuple[str, list[Any]]:
    role = user.get("role")
    if role in HR_ROLES | {ROLE_DIRECTOR, ROLE_IT}:
        return "1=1", []
    if role == ROLE_MANAGER:
        return "a.branch_id=?", [user.get("branch_id")]
    return "a.user_id=?", [user["id"]]


def list_applications(con: sqlite3.Connection, user: dict[str, Any], params: dict[str, str] | None = None) -> list[dict[str, Any]]:
    params = params or {}
    limit = min(safe_int(params.get("limit")) or 50, 200)
    scope_sql, args = application_scope_sql(user)
    sql = f"""
        SELECT a.*, b.name AS branch_name, v.title AS vacancy_title, u.tg_id, u.username
          FROM applications a
          LEFT JOIN branches b ON b.id=a.branch_id
          LEFT JOIN vacancies v ON v.id=a.vacancy_id
          LEFT JOIN users u ON u.id=a.user_id
         WHERE {scope_sql}
    """
    if params.get("status"):
        sql += " AND a.status=?"
        args.append(params["status"])
    if params.get("q"):
        like = f"%{params['q']}%"
        sql += " AND (lower(a.full_name) LIKE lower(?) OR lower(a.phone) LIKE lower(?) OR lower(a.position) LIKE lower(?))"
        args.extend([like, like, like])
    sql += " ORDER BY a.id DESC LIMIT ?"
    args.append(limit)
    return rows_to_dicts(con.execute(sql, args).fetchall())


def api_applications(user: dict[str, Any], params: dict[str, str]) -> dict[str, Any]:
    with db() as con:
        rows = list_applications(con, user, params)
    return {"items": rows}


def api_create_application(user: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    full_name = clean_text(data.get("full_name") or user.get("full_name"), 160)
    phone = clean_text(data.get("phone") or user.get("phone"), 60)
    if len(full_name) < 3:
        raise AppError(HTTPStatus.BAD_REQUEST, "Ism-familiya kiriting.")
    if len("".join(ch for ch in phone if ch.isdigit())) < 7:
        raise AppError(HTTPStatus.BAD_REQUEST, "Telefon raqam kiriting.")
    vacancy_id = safe_int(data.get("vacancy_id"))
    branch_id = safe_int(data.get("branch_id"))
    with db() as con:
        if vacancy_id and not branch_id:
            vac = con.execute("SELECT branch_id, title FROM vacancies WHERE id=?", (vacancy_id,)).fetchone()
            if vac:
                branch_id = vac["branch_id"]
                data.setdefault("position", vac["title"])
        cur = con.execute(
            """
            INSERT INTO applications
                (user_id, vacancy_id, branch_id, full_name, birth_date, gender, city,
                 district, address, position, position_extra, shift, education,
                 exp_years, prev_years, criminal, marital, children, prev_salary,
                 expected_salary, computer_level, languages, work_intent, reason,
                 phone, status)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'new')
            """,
            (
                user["id"],
                vacancy_id,
                branch_id,
                full_name,
                clean_text(data.get("birth_date"), 40),
                clean_text(data.get("gender"), 20),
                clean_text(data.get("city"), 100),
                clean_text(data.get("district"), 100),
                clean_text(data.get("address"), 240),
                clean_text(data.get("position"), 140),
                clean_text(data.get("position_extra"), 400),
                clean_text(data.get("shift"), 80),
                clean_text(data.get("education"), 180),
                clean_text(data.get("exp_years"), 80),
                clean_text(data.get("prev_years"), 80),
                clean_text(data.get("criminal"), 80),
                clean_text(data.get("marital"), 80),
                clean_text(data.get("children"), 80),
                clean_text(data.get("prev_salary"), 80),
                clean_text(data.get("expected_salary"), 80),
                clean_text(data.get("computer_level"), 80),
                clean_text(data.get("languages"), 240),
                clean_text(data.get("work_intent"), 200),
                clean_text(data.get("reason"), 600),
                phone,
            ),
        )
        con.execute("UPDATE users SET full_name=?, phone=?, name_locked=1 WHERE id=?", (full_name, phone, user["id"]))
        con.execute(
            "INSERT INTO audit_logs (tg_id, actor_name, action, details) VALUES (?,?,?,?)",
            (user.get("tg_id"), full_name, "app_application_create", f"#{cur.lastrowid}"),
        )
        con.commit()
        item = row_to_dict(con.execute("SELECT * FROM applications WHERE id=?", (cur.lastrowid,)).fetchone())
    return {"item": item}


def api_application_action(user: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    require_role(user, HR_ROLES | {ROLE_DIRECTOR})
    aid = safe_int(data.get("id"))
    action = clean_text(data.get("action"), 40)
    if not aid:
        raise AppError(HTTPStatus.BAD_REQUEST, "Ariza ID kerak.")
    status_map = {
        "accept": "accepted",
        "reject": "rejected",
        "waiting": "waiting",
        "interview": "interview",
        "new": "new",
    }
    with db() as con:
        item = row_to_dict(con.execute("SELECT * FROM applications WHERE id=?", (aid,)).fetchone())
        if not item:
            raise AppError(HTTPStatus.NOT_FOUND, "Ariza topilmadi.")
        if action in status_map:
            con.execute(
                "UPDATE applications SET status=?, handled_by=?, hr_comment=COALESCE(?, hr_comment) WHERE id=?",
                (status_map[action], user["id"], clean_text(data.get("comment"), 1000) or None, aid),
            )
            if action == "interview":
                con.execute(
                    """
                    INSERT INTO interviews
                        (application_id, date, time, location, comment, created_by)
                    VALUES (?,?,?,?,?,?)
                    """,
                    (
                        aid,
                        clean_text(data.get("date"), 30),
                        clean_text(data.get("time"), 30),
                        clean_text(data.get("location"), 200),
                        clean_text(data.get("comment"), 500),
                        user["id"],
                    ),
                )
        elif action == "comment":
            con.execute(
                "UPDATE applications SET hr_comment=?, handled_by=? WHERE id=?",
                (clean_text(data.get("comment"), 1000), user["id"], aid),
            )
        else:
            raise AppError(HTTPStatus.BAD_REQUEST, "Noma'lum amal.")
        con.execute(
            "INSERT INTO audit_logs (tg_id, actor_name, action, details) VALUES (?,?,?,?)",
            (user.get("tg_id"), user.get("full_name"), f"app_application_{action}", f"#{aid}"),
        )
        con.commit()
        updated = row_to_dict(con.execute("SELECT * FROM applications WHERE id=?", (aid,)).fetchone())
    return {"item": updated}


def list_employees(con: sqlite3.Connection, user: dict[str, Any], params: dict[str, str] | None = None) -> list[dict[str, Any]]:
    params = params or {}
    if user.get("role") not in PEOPLE_ROLES:
        return []
    limit = min(safe_int(params.get("limit")) or 80, 300)
    sql = """
        SELECT ep.*, u.tg_id, u.full_name, u.username, u.phone, u.role AS user_role,
               b.name AS branch_name
          FROM employee_profiles ep
          JOIN users u ON u.id=ep.user_id
          LEFT JOIN branches b ON b.id=ep.branch_id
         WHERE 1=1
    """
    args: list[Any] = []
    if user.get("role") == ROLE_MANAGER:
        sql += " AND ep.branch_id=?"
        args.append(user.get("branch_id"))
    if params.get("branch_id"):
        sql += " AND ep.branch_id=?"
        args.append(safe_int(params.get("branch_id")))
    if params.get("role"):
        sql += " AND ep.role=?"
        args.append(params["role"])
    if params.get("q"):
        like = f"%{params['q']}%"
        sql += """
            AND (lower(u.full_name) LIKE lower(?)
              OR lower(COALESCE(u.phone,'')) LIKE lower(?)
              OR lower(COALESCE(ep.position,'')) LIKE lower(?)
              OR lower(COALESCE(u.username,'')) LIKE lower(?))
        """
        args.extend([like, like, like, like])
    sql += " ORDER BY u.full_name LIMIT ?"
    args.append(limit)
    return rows_to_dicts(con.execute(sql, args).fetchall())


def api_employees(user: dict[str, Any], params: dict[str, str]) -> dict[str, Any]:
    require_role(user, PEOPLE_ROLES)
    with db() as con:
        rows = list_employees(con, user, params)
    return {"items": rows}


def api_update_employee(user: dict[str, Any], uid: int, data: dict[str, Any]) -> dict[str, Any]:
    require_role(user, HR_ROLES | {ROLE_IT, ROLE_DIRECTOR})
    with db() as con:
        profile = get_profile(con, uid)
        if not profile:
            raise AppError(HTTPStatus.NOT_FOUND, "Xodim topilmadi.")
        allowed_ep = {
            "position",
            "branch_id",
            "uniform_status",
            "monthly_salary",
            "work_hours",
            "rest_day",
            "education",
            "emp_status",
        }
        ep_fields = [key for key in data if key in allowed_ep]
        if ep_fields:
            values = [data[key] for key in ep_fields]
            values.append(now_sql())
            values.append(uid)
            con.execute(
                f"UPDATE employee_profiles SET {', '.join(f'{key}=?' for key in ep_fields)}, updated_at=? WHERE user_id=?",
                values,
            )
        if "full_name" in data or "phone" in data or "role" in data or "branch_id" in data:
            parts = []
            values = []
            for field in ["full_name", "phone", "role", "branch_id"]:
                if field in data:
                    parts.append(f"{field}=?")
                    values.append(data[field])
            values.append(uid)
            con.execute(f"UPDATE users SET {', '.join(parts)} WHERE id=?", values)
        con.execute(
            "INSERT INTO audit_logs (tg_id, actor_name, action, details) VALUES (?,?,?,?)",
            (user.get("tg_id"), user.get("full_name"), "app_employee_update", f"#{uid}"),
        )
        con.commit()
        item = get_profile(con, uid)
    return {"item": item}


def create_dayoff(user: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    with db() as con:
        profile = get_profile(con, user["id"])
        if not profile:
            raise AppError(HTTPStatus.FORBIDDEN, "Xodim profili topilmadi.")
        cur = con.execute(
            """
            INSERT INTO dayoff_requests (user_id, branch_id, from_day, to_day, reason, status)
            VALUES (?,?,?,?,?,'new')
            """,
            (
                user["id"],
                profile.get("branch_id") or user.get("branch_id"),
                clean_text(data.get("from_day"), 40) or profile.get("rest_day"),
                clean_text(data.get("to_day"), 40),
                clean_text(data.get("reason"), 500),
            ),
        )
        con.commit()
        return {"item": row_to_dict(con.execute("SELECT * FROM dayoff_requests WHERE id=?", (cur.lastrowid,)).fetchone())}


def create_work_hour(user: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    requested = clean_text(data.get("requested_hours"), 80)
    if not parse_work_hours(requested):
        raise AppError(HTTPStatus.BAD_REQUEST, "Ish vaqti formati: 09:00 - 18:00")
    with db() as con:
        profile = get_profile(con, user["id"])
        if not profile:
            raise AppError(HTTPStatus.FORBIDDEN, "Xodim profili topilmadi.")
        cur = con.execute(
            """
            INSERT INTO work_hour_requests
                (user_id, branch_id, position, current_hours, requested_hours, status)
            VALUES (?,?,?,?,?,'pending')
            """,
            (
                user["id"],
                profile.get("branch_id"),
                profile.get("position"),
                profile.get("work_hours"),
                requested,
            ),
        )
        con.commit()
        return {"item": row_to_dict(con.execute("SELECT * FROM work_hour_requests WHERE id=?", (cur.lastrowid,)).fetchone())}


def create_salary_raise(user: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    amount = clean_text(data.get("requested_amount"), 80)
    if not amount:
        raise AppError(HTTPStatus.BAD_REQUEST, "So'ralgan maoshni kiriting.")
    with db() as con:
        profile = get_profile(con, user["id"])
        if not profile:
            raise AppError(HTTPStatus.FORBIDDEN, "Xodim profili topilmadi.")
        cur = con.execute(
            """
            INSERT INTO salary_raise_requests
                (user_id, branch_id, position, current_salary, requested_amount,
                 last_offer_by, status)
            VALUES (?,?,?,?,?,'employee','pending')
            """,
            (
                user["id"],
                profile.get("branch_id"),
                profile.get("position"),
                profile.get("monthly_salary"),
                amount,
            ),
        )
        con.commit()
        return {"item": row_to_dict(con.execute("SELECT * FROM salary_raise_requests WHERE id=?", (cur.lastrowid,)).fetchone())}


def create_branch_transfer(user: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    to_branch = safe_int(data.get("to_branch_id"))
    if not to_branch:
        raise AppError(HTTPStatus.BAD_REQUEST, "Yangi filialni tanlang.")
    with db() as con:
        profile = get_profile(con, user["id"])
        if not profile:
            raise AppError(HTTPStatus.FORBIDDEN, "Xodim profili topilmadi.")
        cur = con.execute(
            """
            INSERT INTO branch_transfer_requests
                (user_id, from_branch_id, to_branch_id, position, status)
            VALUES (?,?,?,?, 'pending')
            """,
            (user["id"], profile.get("branch_id"), to_branch, profile.get("position")),
        )
        con.commit()
        return {"item": row_to_dict(con.execute("SELECT * FROM branch_transfer_requests WHERE id=?", (cur.lastrowid,)).fetchone())}


def create_hr_message(user: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    message = clean_text(data.get("message"), 1200)
    if len(message) < 2:
        raise AppError(HTTPStatus.BAD_REQUEST, "Murojaat matnini yozing.")
    with db() as con:
        profile = get_profile(con, user["id"])
        cur = con.execute(
            """
            INSERT INTO app_hr_messages (user_id, branch_id, subject, message)
            VALUES (?,?,?,?)
            """,
            (
                user["id"],
                (profile or {}).get("branch_id") or user.get("branch_id"),
                clean_text(data.get("subject"), 120) or "HR ga murojaat",
                message,
            ),
        )
        con.commit()
        return {"item": row_to_dict(con.execute("SELECT * FROM app_hr_messages WHERE id=?", (cur.lastrowid,)).fetchone())}


def create_manager_request(user: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    require_role(user, {ROLE_MANAGER, ROLE_DIRECTOR, ROLE_ADMIN, ROLE_HR})
    kind = clean_text(data.get("kind"), 40) or "vacancy"
    title = clean_text(data.get("title"), 180)
    if not title:
        raise AppError(HTTPStatus.BAD_REQUEST, "So'rov mavzusini kiriting.")
    branch_id = safe_int(data.get("branch_id")) or safe_int(user.get("branch_id"))
    if user.get("role") == ROLE_MANAGER:
        branch_id = safe_int(user.get("branch_id"))
    with db() as con:
        cur = con.execute(
            """
            INSERT INTO manager_requests
                (manager_user_id, branch_id, kind, title, staff_count, shift,
                 experience, gender, details, status)
            VALUES (?,?,?,?,?,?,?,?,?,'new')
            """,
            (
                user["id"],
                branch_id,
                kind,
                title,
                clean_text(data.get("staff_count"), 40),
                clean_text(data.get("shift"), 80),
                clean_text(data.get("experience"), 180),
                clean_text(data.get("gender"), 40) or "any",
                clean_text(data.get("details"), 1000),
            ),
        )
        con.commit()
        return {"item": row_to_dict(con.execute("SELECT * FROM manager_requests WHERE id=?", (cur.lastrowid,)).fetchone())}


def list_requests(con: sqlite3.Connection, user: dict[str, Any], params: dict[str, str] | None = None) -> list[dict[str, Any]]:
    params = params or {}
    limit = min(safe_int(params.get("limit")) or 60, 200)
    items: list[dict[str, Any]] = []
    role = user.get("role")
    branch_id = user.get("branch_id")

    def add_rows(kind: str, sql: str, args: tuple[Any, ...] = ()) -> None:
        for row in con.execute(sql, args).fetchall():
            item = dict(row)
            item["kind"] = kind
            item["status_label"] = status_label(item.get("status"))
            items.append(item)

    if role in HR_ROLES | {ROLE_DIRECTOR, ROLE_ACCOUNTANT}:
        add_rows(
            "dayoff",
            """
            SELECT dr.id, dr.status, dr.created_at, dr.from_day, dr.to_day, dr.reason,
                   u.full_name, b.name AS branch_name
              FROM dayoff_requests dr
              JOIN users u ON u.id=dr.user_id
              LEFT JOIN branches b ON b.id=dr.branch_id
             ORDER BY dr.id DESC LIMIT ?
            """,
            (limit,),
        )
        add_rows(
            "work_hours",
            """
            SELECT wh.id, wh.status, wh.created_at, wh.current_hours, wh.requested_hours,
                   u.full_name, b.name AS branch_name
              FROM work_hour_requests wh
              JOIN users u ON u.id=wh.user_id
              LEFT JOIN branches b ON b.id=wh.branch_id
             ORDER BY wh.id DESC LIMIT ?
            """,
            (limit,),
        )
        add_rows(
            "salary",
            """
            SELECT sr.id, sr.status, sr.created_at, sr.current_salary, sr.requested_amount,
                   sr.offered_amount, u.full_name, b.name AS branch_name
              FROM salary_raise_requests sr
              JOIN users u ON u.id=sr.user_id
              LEFT JOIN branches b ON b.id=sr.branch_id
             ORDER BY sr.id DESC LIMIT ?
            """,
            (limit,),
        )
        add_rows(
            "branch_transfer",
            """
            SELECT bt.id, bt.status, bt.created_at, u.full_name,
                   bf.name AS from_branch_name, tb.name AS to_branch_name
              FROM branch_transfer_requests bt
              JOIN users u ON u.id=bt.user_id
              LEFT JOIN branches bf ON bf.id=bt.from_branch_id
              LEFT JOIN branches tb ON tb.id=bt.to_branch_id
             ORDER BY bt.id DESC LIMIT ?
            """,
            (limit,),
        )
        add_rows(
            "manager_request",
            """
            SELECT mr.id, mr.status, mr.created_at, mr.kind AS request_kind, mr.title,
                   mr.details, u.full_name, b.name AS branch_name
              FROM manager_requests mr
              JOIN users u ON u.id=mr.manager_user_id
              LEFT JOIN branches b ON b.id=mr.branch_id
             ORDER BY mr.id DESC LIMIT ?
            """,
            (limit,),
        )
        add_rows(
            "hr_message",
            """
            SELECT hm.id, hm.status, hm.created_at, hm.subject, hm.message,
                   u.full_name, b.name AS branch_name
              FROM app_hr_messages hm
              JOIN users u ON u.id=hm.user_id
              LEFT JOIN branches b ON b.id=hm.branch_id
             ORDER BY hm.id DESC LIMIT ?
            """,
            (limit,),
        )
    elif role == ROLE_MANAGER:
        add_rows(
            "dayoff",
            """
            SELECT dr.id, dr.status, dr.created_at, dr.from_day, dr.to_day, dr.reason,
                   u.full_name, b.name AS branch_name
              FROM dayoff_requests dr
              JOIN users u ON u.id=dr.user_id
              LEFT JOIN branches b ON b.id=dr.branch_id
             WHERE dr.branch_id=?
             ORDER BY dr.id DESC LIMIT ?
            """,
            (branch_id, limit),
        )
        add_rows(
            "manager_request",
            """
            SELECT mr.id, mr.status, mr.created_at, mr.kind AS request_kind, mr.title,
                   mr.details, u.full_name, b.name AS branch_name
              FROM manager_requests mr
              JOIN users u ON u.id=mr.manager_user_id
              LEFT JOIN branches b ON b.id=mr.branch_id
             WHERE mr.manager_user_id=? OR mr.branch_id=?
             ORDER BY mr.id DESC LIMIT ?
            """,
            (user["id"], branch_id, limit),
        )
    else:
        add_rows(
            "dayoff",
            """
            SELECT dr.id, dr.status, dr.created_at, dr.from_day, dr.to_day, dr.reason,
                   u.full_name, b.name AS branch_name
              FROM dayoff_requests dr
              JOIN users u ON u.id=dr.user_id
              LEFT JOIN branches b ON b.id=dr.branch_id
             WHERE dr.user_id=?
             ORDER BY dr.id DESC LIMIT ?
            """,
            (user["id"], limit),
        )
        add_rows(
            "work_hours",
            """
            SELECT wh.id, wh.status, wh.created_at, wh.current_hours, wh.requested_hours,
                   u.full_name, b.name AS branch_name
              FROM work_hour_requests wh
              JOIN users u ON u.id=wh.user_id
              LEFT JOIN branches b ON b.id=wh.branch_id
             WHERE wh.user_id=?
             ORDER BY wh.id DESC LIMIT ?
            """,
            (user["id"], limit),
        )
        add_rows(
            "salary",
            """
            SELECT sr.id, sr.status, sr.created_at, sr.current_salary, sr.requested_amount,
                   sr.offered_amount, u.full_name, b.name AS branch_name
              FROM salary_raise_requests sr
              JOIN users u ON u.id=sr.user_id
              LEFT JOIN branches b ON b.id=sr.branch_id
             WHERE sr.user_id=?
             ORDER BY sr.id DESC LIMIT ?
            """,
            (user["id"], limit),
        )
        add_rows(
            "branch_transfer",
            """
            SELECT bt.id, bt.status, bt.created_at, u.full_name,
                   bf.name AS from_branch_name, tb.name AS to_branch_name
              FROM branch_transfer_requests bt
              JOIN users u ON u.id=bt.user_id
              LEFT JOIN branches bf ON bf.id=bt.from_branch_id
              LEFT JOIN branches tb ON tb.id=bt.to_branch_id
             WHERE bt.user_id=?
             ORDER BY bt.id DESC LIMIT ?
            """,
            (user["id"], limit),
        )
        add_rows(
            "hr_message",
            """
            SELECT hm.id, hm.status, hm.created_at, hm.subject, hm.message,
                   u.full_name, b.name AS branch_name
              FROM app_hr_messages hm
              JOIN users u ON u.id=hm.user_id
              LEFT JOIN branches b ON b.id=hm.branch_id
             WHERE hm.user_id=?
             ORDER BY hm.id DESC LIMIT ?
            """,
            (user["id"], limit),
        )
    items.sort(key=lambda item: item.get("created_at") or "", reverse=True)
    return items[:limit]


def api_requests(user: dict[str, Any], params: dict[str, str]) -> dict[str, Any]:
    with db() as con:
        items = list_requests(con, user, params)
    return {"items": items}


def api_create_request(user: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    kind = clean_text(data.get("kind"), 60)
    if kind == "dayoff":
        return create_dayoff(user, data)
    if kind == "work_hours":
        return create_work_hour(user, data)
    if kind == "salary":
        return create_salary_raise(user, data)
    if kind == "branch_transfer":
        return create_branch_transfer(user, data)
    if kind == "hr_message":
        return create_hr_message(user, data)
    if kind == "manager_request":
        return create_manager_request(user, data)
    raise AppError(HTTPStatus.BAD_REQUEST, "Noma'lum so'rov turi.")


def api_request_action(user: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    kind = clean_text(data.get("kind"), 60)
    rid = safe_int(data.get("id"))
    action = clean_text(data.get("action"), 60)
    if not rid:
        raise AppError(HTTPStatus.BAD_REQUEST, "So'rov ID kerak.")
    require_role(user, LEAD_ROLES | {ROLE_ACCOUNTANT})
    with db() as con:
        if kind == "dayoff":
            req = row_to_dict(con.execute("SELECT * FROM dayoff_requests WHERE id=?", (rid,)).fetchone())
            if not req:
                raise AppError(HTTPStatus.NOT_FOUND, "So'rov topilmadi.")
            if not can_view_branch(user, req.get("branch_id")):
                raise AppError(HTTPStatus.FORBIDDEN, "Bu filial so'rovi emas.")
            status = "approved" if action == "approve" else "rejected"
            con.execute("UPDATE dayoff_requests SET status=?, handled_by=? WHERE id=?", (status, user["id"], rid))
            if status == "approved" and req.get("to_day"):
                con.execute(
                    "UPDATE employee_profiles SET rest_day=?, updated_at=? WHERE user_id=?",
                    (req["to_day"], now_sql(), req["user_id"]),
                )
        elif kind == "work_hours":
            req = row_to_dict(con.execute("SELECT * FROM work_hour_requests WHERE id=?", (rid,)).fetchone())
            if not req:
                raise AppError(HTTPStatus.NOT_FOUND, "So'rov topilmadi.")
            status = "approved" if action == "approve" else "rejected"
            con.execute(
                "UPDATE work_hour_requests SET status=?, reject_reason=COALESCE(?, reject_reason), handled_by=?, updated_at=? WHERE id=?",
                (status, clean_text(data.get("reason"), 300) or None, user["id"], now_sql(), rid),
            )
            if status == "approved":
                con.execute(
                    "UPDATE employee_profiles SET work_hours=?, updated_at=? WHERE user_id=?",
                    (req["requested_hours"], now_sql(), req["user_id"]),
                )
        elif kind == "salary":
            req = row_to_dict(con.execute("SELECT * FROM salary_raise_requests WHERE id=?", (rid,)).fetchone())
            if not req:
                raise AppError(HTTPStatus.NOT_FOUND, "So'rov topilmadi.")
            if action == "offer":
                con.execute(
                    "UPDATE salary_raise_requests SET offered_amount=?, last_offer_by='hr', status='pending', handled_by=?, updated_at=? WHERE id=?",
                    (clean_text(data.get("amount"), 80), user["id"], now_sql(), rid),
                )
            else:
                status = "agreed" if action == "approve" else "rejected"
                final_amount = clean_text(data.get("amount"), 80) or req.get("requested_amount") or req.get("offered_amount")
                con.execute(
                    "UPDATE salary_raise_requests SET status=?, final_amount=?, reject_reason=COALESCE(?, reject_reason), handled_by=?, updated_at=? WHERE id=?",
                    (status, final_amount if status == "agreed" else None, clean_text(data.get("reason"), 300) or None, user["id"], now_sql(), rid),
                )
                if status == "agreed" and final_amount:
                    con.execute(
                        "UPDATE employee_profiles SET monthly_salary=?, updated_at=? WHERE user_id=?",
                        (final_amount, now_sql(), req["user_id"]),
                    )
        elif kind == "branch_transfer":
            req = row_to_dict(con.execute("SELECT * FROM branch_transfer_requests WHERE id=?", (rid,)).fetchone())
            if not req:
                raise AppError(HTTPStatus.NOT_FOUND, "So'rov topilmadi.")
            status = "approved" if action == "approve" else "rejected"
            con.execute(
                "UPDATE branch_transfer_requests SET status=?, handled_by=?, updated_at=? WHERE id=?",
                (status, user["id"], now_sql(), rid),
            )
            if status == "approved":
                con.execute("UPDATE users SET branch_id=? WHERE id=?", (req["to_branch_id"], req["user_id"]))
                con.execute(
                    "UPDATE employee_profiles SET branch_id=?, updated_at=? WHERE user_id=?",
                    (req["to_branch_id"], now_sql(), req["user_id"]),
                )
        elif kind == "manager_request":
            req = row_to_dict(con.execute("SELECT * FROM manager_requests WHERE id=?", (rid,)).fetchone())
            if not req:
                raise AppError(HTTPStatus.NOT_FOUND, "So'rov topilmadi.")
            status = "accepted" if action in {"approve", "accept"} else "closed"
            con.execute(
                "UPDATE manager_requests SET status=?, hr_comment=COALESCE(?, hr_comment), handled_by=? WHERE id=?",
                (status, clean_text(data.get("comment"), 500) or None, user["id"], rid),
            )
            if status == "accepted" and req.get("kind") == "vacancy":
                con.execute(
                    """
                    INSERT INTO vacancies
                        (title, branch_id, shift, staff_count, experience, gender,
                         manager_request_id, is_active, created_by)
                    VALUES (?,?,?,?,?,?,?,1,?)
                    """,
                    (
                        req.get("title"),
                        req.get("branch_id"),
                        req.get("shift"),
                        req.get("staff_count"),
                        req.get("experience"),
                        req.get("gender"),
                        rid,
                        user["id"],
                    ),
                )
        elif kind == "hr_message":
            status = "closed" if action in {"close", "approve"} else "new"
            con.execute(
                "UPDATE app_hr_messages SET status=?, handled_by=?, response=?, updated_at=? WHERE id=?",
                (status, user["id"], clean_text(data.get("response"), 800), now_sql(), rid),
            )
        else:
            raise AppError(HTTPStatus.BAD_REQUEST, "Noma'lum so'rov turi.")
        con.execute(
            "INSERT INTO audit_logs (tg_id, actor_name, action, details) VALUES (?,?,?,?)",
            (user.get("tg_id"), user.get("full_name"), f"app_request_{action}", f"{kind} #{rid}"),
        )
        con.commit()
    return {"ok": True}


def normalize_role(role_value: Any, position: Any = "") -> str:
    text = f"{role_value or ''} {position or ''}".lower()
    direct = {
        ROLE_ADMIN,
        ROLE_HR,
        ROLE_MANAGER,
        ROLE_EMPLOYEE,
        ROLE_PHARMACIST,
        ROLE_DIRECTOR,
        ROLE_ACCOUNTANT,
        ROLE_IT,
        ROLE_TECH,
        ROLE_CANDIDATE,
    }
    if str(role_value) in direct:
        return str(role_value)
    rules = [
        (("farm", "apteka", "dorishunos", "pharm"), ROLE_PHARMACIST),
        (("rahbar", "manager", "boshliq"), ROLE_MANAGER),
        (("direktor", "director"), ROLE_DIRECTOR),
        (("moliya", "bux", "hisob"), ROLE_ACCOUNTANT),
        (("texnik", "usta", "ta'mir"), ROLE_TECH),
        (("it", "dastur", "kompyuter"), ROLE_IT),
        (("hr", "kadr"), ROLE_HR),
    ]
    for keys, role in rules:
        if any(key in text for key in keys):
            return role
    return ROLE_EMPLOYEE


def parse_money(value: Any) -> int:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    return int(digits or "0")


def api_stats(user: dict[str, Any]) -> dict[str, Any]:
    with db() as con:
        role_rows = rows_to_dicts(
            con.execute("SELECT role, COUNT(*) AS count FROM users GROUP BY role ORDER BY count DESC").fetchall()
        )
        branch_rows = rows_to_dicts(
            con.execute(
                """
                SELECT b.id, b.name, COUNT(ep.id) AS employees,
                       SUM(CASE WHEN ep.uniform_status='no' OR ep.uniform_status='unknown' THEN 1 ELSE 0 END) AS uniform_issues
                  FROM branches b
                  LEFT JOIN employee_profiles ep ON ep.branch_id=b.id
                 GROUP BY b.id, b.name
                 ORDER BY employees DESC, b.name
                """
            ).fetchall()
        )
        app_rows = rows_to_dicts(
            con.execute("SELECT status, COUNT(*) AS count FROM applications GROUP BY status").fetchall()
        )
        tech_rows = rows_to_dicts(
            con.execute("SELECT status, COUNT(*) AS count FROM tech_tasks GROUP BY status").fetchall()
        )
        finance = {
            "fines_month": sql_count(con, "SELECT COUNT(*) FROM fines WHERE substr(created_at,1,7)=?", (month_sql(),)),
            "advance_pending": sql_count(con, "SELECT COUNT(*) FROM advance_requests WHERE status='confirmed'"),
            "paid_month": sql_count(con, "SELECT COUNT(*) FROM salary_payments WHERE period=?", (month_sql(),)),
        }
        totals = {
            "users": sql_count(con, "SELECT COUNT(*) FROM users"),
            "employees": sql_count(con, "SELECT COUNT(*) FROM employee_profiles"),
            "applications": sql_count(con, "SELECT COUNT(*) FROM applications"),
            "vacancies": sql_count(con, "SELECT COUNT(*) FROM vacancies WHERE is_active=1 AND COALESCE(filled,0)=0"),
            "staff_regs": sql_count(con, "SELECT COUNT(*) FROM staff_regs WHERE status='new'"),
            "tech_open": sql_count(con, "SELECT COUNT(*) FROM tech_tasks WHERE status NOT IN ('done','rated','closed')"),
        }
    return {
        "totals": totals,
        "roles": role_rows,
        "branches": branch_rows,
        "applications": app_rows,
        "tech": tech_rows,
        "finance": finance,
    }


def list_staff_regs(con: sqlite3.Connection, user: dict[str, Any], params: dict[str, str]) -> list[dict[str, Any]]:
    limit = min(safe_int(params.get("limit")) or 80, 300)
    sql = """
        SELECT sr.*, u.tg_id, u.username, b.name AS branch_actual_name
          FROM staff_regs sr
          JOIN users u ON u.id=sr.user_id
          LEFT JOIN branches b ON b.id=sr.branch_id
         WHERE 1=1
    """
    args: list[Any] = []
    if user.get("role") in HR_ROLES | {ROLE_DIRECTOR, ROLE_IT}:
        pass
    elif user.get("role") == ROLE_MANAGER:
        sql += " AND sr.branch_id=?"
        args.append(user.get("branch_id"))
    else:
        sql += " AND sr.user_id=?"
        args.append(user["id"])
    if params.get("status"):
        sql += " AND sr.status=?"
        args.append(params["status"])
    sql += " ORDER BY sr.id DESC LIMIT ?"
    args.append(limit)
    return rows_to_dicts(con.execute(sql, args).fetchall())


def api_staff_regs(user: dict[str, Any], params: dict[str, str]) -> dict[str, Any]:
    with db() as con:
        return {"items": list_staff_regs(con, user, params)}


def api_create_staff_reg(user: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    full_name = clean_text(data.get("full_name") or user.get("full_name"), 160)
    phone = clean_text(data.get("phone") or user.get("phone"), 80)
    if len(full_name) < 3:
        raise AppError(HTTPStatus.BAD_REQUEST, "Ism-familiya kiriting.")
    branch_id = safe_int(data.get("branch_id")) or safe_int(user.get("branch_id"))
    with db() as con:
        cur = con.execute(
            """
            INSERT INTO staff_regs
                (user_id, full_name, birth_date, phone, role, position, address,
                 branch_id, branch_name, work_hours, salary, rest_day,
                 uniform_status, since, extra_info, education, parent_phone, status)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'new')
            """,
            (
                user["id"],
                full_name,
                clean_text(data.get("birth_date"), 40),
                phone,
                clean_text(data.get("role"), 80),
                clean_text(data.get("position"), 140),
                clean_text(data.get("address"), 240),
                branch_id,
                clean_text(data.get("branch_name"), 160),
                clean_text(data.get("work_hours"), 80),
                clean_text(data.get("salary"), 80),
                clean_text(data.get("rest_day"), 80),
                clean_text(data.get("uniform_status"), 40) or "unknown",
                clean_text(data.get("since"), 80),
                clean_text(data.get("extra_info"), 800),
                clean_text(data.get("education"), 200),
                clean_text(data.get("parent_phone"), 80),
            ),
        )
        con.execute(
            "UPDATE users SET full_name=?, phone=COALESCE(?, phone), name_locked=1 WHERE id=?",
            (full_name, phone or None, user["id"]),
        )
        con.commit()
        item = row_to_dict(con.execute("SELECT * FROM staff_regs WHERE id=?", (cur.lastrowid,)).fetchone())
    return {"item": item}


def api_staff_reg_action(user: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    require_role(user, HR_ROLES | {ROLE_DIRECTOR})
    rid = safe_int(data.get("id"))
    action = clean_text(data.get("action"), 40)
    if not rid:
        raise AppError(HTTPStatus.BAD_REQUEST, "So'rov ID kerak.")
    with db() as con:
        reg = row_to_dict(con.execute("SELECT * FROM staff_regs WHERE id=?", (rid,)).fetchone())
        if not reg:
            raise AppError(HTTPStatus.NOT_FOUND, "Xodim so'rovi topilmadi.")
        if action == "approve":
            role = normalize_role(reg.get("role"), reg.get("position"))
            existing = con.execute("SELECT id FROM employee_profiles WHERE user_id=?", (reg["user_id"],)).fetchone()
            values = (
                reg["user_id"],
                role,
                reg.get("position") or role_label(role),
                reg.get("branch_id"),
                reg.get("uniform_status") or "unknown",
                reg.get("salary"),
                reg.get("birth_date"),
                reg.get("address"),
                reg.get("work_hours"),
                reg.get("rest_day"),
                reg.get("photo_file_id"),
                reg.get("extra_info"),
                reg.get("since"),
                reg.get("education"),
                reg.get("parent_phone"),
                now_sql(),
            )
            if existing:
                con.execute(
                    """
                    UPDATE employee_profiles
                       SET role=?, position=?, branch_id=?, uniform_status=?,
                           monthly_salary=?, birth_date=?, address=?, work_hours=?,
                           rest_day=?, photo_file_id=COALESCE(?, photo_file_id),
                           extra_info=?, since=?, education=?, parent_phone=?,
                           updated_at=?
                     WHERE user_id=?
                    """,
                    values[1:] + (reg["user_id"],),
                )
            else:
                con.execute(
                    """
                    INSERT INTO employee_profiles
                        (user_id, role, position, branch_id, uniform_status,
                         monthly_salary, birth_date, address, work_hours, rest_day,
                         photo_file_id, extra_info, since, education, parent_phone,
                         updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    values,
                )
            con.execute(
                "UPDATE users SET role=?, branch_id=?, full_name=?, phone=COALESCE(?, phone), name_locked=1 WHERE id=?",
                (role, reg.get("branch_id"), reg.get("full_name"), reg.get("phone"), reg["user_id"]),
            )
            con.execute("UPDATE staff_regs SET status='approved', handled_by=? WHERE id=?", (user["id"], rid))
        elif action == "reject":
            con.execute(
                "UPDATE staff_regs SET status='rejected', reject_reason=?, handled_by=? WHERE id=?",
                (clean_text(data.get("reason"), 500), user["id"], rid),
            )
        else:
            raise AppError(HTTPStatus.BAD_REQUEST, "Noma'lum amal.")
        con.execute(
            "INSERT INTO audit_logs (tg_id, actor_name, action, details) VALUES (?,?,?,?)",
            (user.get("tg_id"), user.get("full_name"), f"app_staff_reg_{action}", f"#{rid}"),
        )
        con.commit()
    return {"ok": True}


def api_interviews(user: dict[str, Any], params: dict[str, str]) -> dict[str, Any]:
    limit = min(safe_int(params.get("limit")) or 80, 200)
    with db() as con:
        sql = """
            SELECT i.*, a.full_name, a.phone, a.position, b.name AS branch_name
              FROM interviews i
              JOIN applications a ON a.id=i.application_id
              LEFT JOIN branches b ON b.id=a.branch_id
             WHERE 1=1
        """
        args: list[Any] = []
        if user.get("role") in HR_ROLES | {ROLE_DIRECTOR}:
            pass
        else:
            sql += " AND a.user_id=?"
            args.append(user["id"])
        sql += " ORDER BY i.id DESC LIMIT ?"
        args.append(limit)
        rows = rows_to_dicts(con.execute(sql, args).fetchall())
    return {"items": rows}


def api_interview_action(user: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    iid = safe_int(data.get("id"))
    action = clean_text(data.get("action"), 40)
    if not iid:
        raise AppError(HTTPStatus.BAD_REQUEST, "Suhbat ID kerak.")
    with db() as con:
        item = row_to_dict(
            con.execute(
                """
                SELECT i.*, a.user_id AS app_user_id
                  FROM interviews i JOIN applications a ON a.id=i.application_id
                 WHERE i.id=?
                """,
                (iid,),
            ).fetchone()
        )
        if not item:
            raise AppError(HTTPStatus.NOT_FOUND, "Suhbat topilmadi.")
        if action in {"came", "absent"}:
            require_role(user, HR_ROLES | {ROLE_DIRECTOR})
            con.execute("UPDATE interviews SET attendance=? WHERE id=?", (action, iid))
        elif action in {"confirm", "reschedule"}:
            if user["id"] != item.get("app_user_id") and user.get("role") not in HR_ROLES:
                raise AppError(HTTPStatus.FORBIDDEN, "Bu suhbat sizga tegishli emas.")
            con.execute(
                "UPDATE interviews SET status=?, comment=COALESCE(?, comment) WHERE id=?",
                ("confirmed" if action == "confirm" else "reschedule", clean_text(data.get("comment"), 500) or None, iid),
            )
        else:
            raise AppError(HTTPStatus.BAD_REQUEST, "Noma'lum amal.")
        con.commit()
    return {"ok": True}


def api_finance(user: dict[str, Any], params: dict[str, str]) -> dict[str, Any]:
    require_role(user, FINANCE_ROLES)
    period = params.get("period") or month_sql()
    with db() as con:
        rows = rows_to_dicts(
            con.execute(
                """
                SELECT ep.user_id, u.full_name, u.phone, ep.position, ep.monthly_salary,
                       b.name AS branch_name,
                       COALESCE((SELECT SUM(CAST(amount AS INTEGER)) FROM fines f
                                  WHERE f.employee_user_id=ep.user_id AND COALESCE(f.cancelled,0)=0
                                    AND COALESCE(f.period, substr(f.created_at,1,7))=?),0) AS fines_total,
                       COALESCE((SELECT SUM(amount) FROM staff_medicines sm
                                  WHERE sm.employee_user_id=ep.user_id AND sm.period=?),0) AS medicines_total,
                       COALESCE((SELECT SUM(amount) FROM salary_deductions sd
                                  WHERE sd.employee_user_id=ep.user_id AND sd.period=?),0) AS deductions_total,
                       (SELECT status FROM salary_payments sp
                         WHERE sp.employee_user_id=ep.user_id AND sp.period=?
                         ORDER BY sp.id DESC LIMIT 1) AS payment_status
                  FROM employee_profiles ep
                  JOIN users u ON u.id=ep.user_id
                  LEFT JOIN branches b ON b.id=ep.branch_id
                 ORDER BY b.name, u.full_name
                """,
                (period, period, period, period),
            ).fetchall()
        )
    return {"period": period, "items": rows}


def api_finance_action(user: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    require_role(user, FINANCE_ROLES)
    uid = safe_int(data.get("user_id"))
    action = clean_text(data.get("action"), 40)
    period = clean_text(data.get("period"), 20) or month_sql()
    if not uid:
        raise AppError(HTTPStatus.BAD_REQUEST, "Xodim ID kerak.")
    with db() as con:
        profile = get_profile(con, uid)
        if not profile:
            raise AppError(HTTPStatus.NOT_FOUND, "Xodim topilmadi.")
        if action == "set_salary":
            amount = clean_text(data.get("amount"), 80)
            con.execute("UPDATE employee_profiles SET monthly_salary=?, updated_at=? WHERE user_id=?", (amount, now_sql(), uid))
        elif action == "fine":
            amount = clean_text(data.get("amount"), 80)
            con.execute(
                "INSERT INTO fines (employee_user_id, branch_id, period, amount, reason, source, created_by) VALUES (?,?,?,?,?,'app',?)",
                (uid, profile.get("branch_id"), period, amount, clean_text(data.get("reason"), 500), user["id"]),
            )
        elif action == "medicine":
            con.execute(
                "INSERT INTO staff_medicines (employee_user_id, branch_id, period, amount, reason, created_by) VALUES (?,?,?,?,?,?)",
                (uid, profile.get("branch_id"), period, parse_money(data.get("amount")), clean_text(data.get("reason"), 500), user["id"]),
            )
        elif action == "deduction":
            base = parse_money(profile.get("monthly_salary"))
            percent = safe_int(data.get("percent")) or 5
            amount = int(base * percent / 100) if base else parse_money(data.get("amount"))
            con.execute(
                """
                INSERT INTO salary_deductions
                    (employee_user_id, branch_id, period, kind, percent, base_salary,
                     base_amount, amount, remaining, created_by)
                VALUES (?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    uid,
                    profile.get("branch_id"),
                    period,
                    clean_text(data.get("kind"), 40) or "employee",
                    percent,
                    profile.get("monthly_salary"),
                    base,
                    amount,
                    max(base - amount, 0) if base else None,
                    user["id"],
                ),
            )
        elif action == "paid":
            amount = clean_text(data.get("amount"), 80) or profile.get("monthly_salary")
            con.execute(
                "INSERT INTO salary_payments (employee_user_id, period, amount, status, note, created_by) VALUES (?,?,?,?,?,?)",
                (uid, period, amount, "paid", clean_text(data.get("note"), 300), user["id"]),
            )
        else:
            raise AppError(HTTPStatus.BAD_REQUEST, "Noma'lum moliya amali.")
        con.execute(
            "INSERT INTO audit_logs (tg_id, actor_name, action, details) VALUES (?,?,?,?)",
            (user.get("tg_id"), user.get("full_name"), f"app_finance_{action}", f"#{uid}"),
        )
        con.commit()
    return {"ok": True}


def api_advance(user: dict[str, Any], params: dict[str, str]) -> dict[str, Any]:
    period = params.get("period") or month_sql()
    with db() as con:
        sql = """
            SELECT ar.*, u.full_name, ep.monthly_salary, b.name AS branch_name
              FROM advance_requests ar
              JOIN users u ON u.id=ar.user_id
              LEFT JOIN employee_profiles ep ON ep.user_id=ar.user_id
              LEFT JOIN branches b ON b.id=ep.branch_id
             WHERE ar.period=?
        """
        args: list[Any] = [period]
        if user.get("role") not in HR_ROLES | {ROLE_ACCOUNTANT, ROLE_DIRECTOR}:
            sql += " AND ar.user_id=?"
            args.append(user["id"])
        sql += " ORDER BY ar.id DESC"
        rows = rows_to_dicts(con.execute(sql, args).fetchall())
    return {"period": period, "items": rows}


def api_create_advance(user: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    period = clean_text(data.get("period"), 20) or month_sql()
    with db() as con:
        con.execute(
            """
            INSERT INTO advance_requests (user_id, period, full_name, card_number, amount, status)
            VALUES (?,?,?,?,?,'confirmed')
            ON CONFLICT(user_id, period) DO UPDATE SET
                card_number=excluded.card_number,
                amount=excluded.amount,
                status='confirmed',
                updated_at=datetime('now','+5 hours')
            """,
            (
                user["id"],
                period,
                user.get("full_name"),
                clean_text(data.get("card_number"), 40),
                parse_money(data.get("amount")),
            ),
        )
        con.commit()
    return {"ok": True}


def api_advance_action(user: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    require_role(user, HR_ROLES | {ROLE_ACCOUNTANT, ROLE_DIRECTOR})
    rid = safe_int(data.get("id"))
    status = clean_text(data.get("status"), 30)
    if status not in {"confirmed", "declined", "pending"}:
        raise AppError(HTTPStatus.BAD_REQUEST, "Avans statusi noto'g'ri.")
    with db() as con:
        con.execute("UPDATE advance_requests SET status=?, updated_at=? WHERE id=?", (status, now_sql(), rid))
        con.commit()
    return {"ok": True}


def api_tech(user: dict[str, Any], params: dict[str, str]) -> dict[str, Any]:
    limit = min(safe_int(params.get("limit")) or 100, 250)
    with db() as con:
        sql = """
            SELECT tt.*, b.name AS branch_name, mu.full_name AS manager_name,
                   tu.full_name AS tech_name
              FROM tech_tasks tt
              LEFT JOIN branches b ON b.id=tt.branch_id
              LEFT JOIN users mu ON mu.id=tt.manager_user_id
              LEFT JOIN users tu ON tu.id=tt.tech_user_id
             WHERE 1=1
        """
        args: list[Any] = []
        if user.get("role") == ROLE_MANAGER:
            sql += " AND tt.branch_id=?"
            args.append(user.get("branch_id"))
        elif user.get("role") == ROLE_TECH:
            sql += " AND (tt.tech_user_id=? OR tt.tech_user_id IS NULL OR tt.status='assigned')"
            args.append(user["id"])
        elif user.get("role") not in HR_ROLES | {ROLE_DIRECTOR, ROLE_ADMIN}:
            raise AppError(HTTPStatus.FORBIDDEN, "Texnik panel uchun ruxsat yo'q.")
        sql += " ORDER BY CASE WHEN tt.priority='urgent' THEN 0 ELSE 1 END, tt.id DESC LIMIT ?"
        args.append(limit)
        rows = rows_to_dicts(con.execute(sql, args).fetchall())
    return {"items": rows}


def api_create_tech(user: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    require_role(user, LEAD_ROLES | {ROLE_TECH})
    branch_id = safe_int(data.get("branch_id")) or safe_int(user.get("branch_id"))
    status = "assigned" if user.get("role") in HR_ROLES | {ROLE_DIRECTOR, ROLE_ADMIN} else "pending_hr"
    with db() as con:
        cur = con.execute(
            """
            INSERT INTO tech_tasks
                (branch_id, manager_user_id, assigned_by, title, details, kind,
                 deadline, status, priority, category, deadline_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                branch_id,
                user["id"],
                user["id"] if status == "assigned" else None,
                clean_text(data.get("title"), 180),
                clean_text(data.get("details"), 1000),
                clean_text(data.get("kind"), 80) or "Matn",
                clean_text(data.get("deadline"), 120),
                status,
                clean_text(data.get("priority"), 40) or "normal",
                clean_text(data.get("category"), 120),
                clean_text(data.get("deadline_at"), 40),
            ),
        )
        con.commit()
        item = row_to_dict(con.execute("SELECT * FROM tech_tasks WHERE id=?", (cur.lastrowid,)).fetchone())
    return {"item": item}


def api_tech_action(user: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    tid = safe_int(data.get("id"))
    action = clean_text(data.get("action"), 40)
    if not tid:
        raise AppError(HTTPStatus.BAD_REQUEST, "Topshiriq ID kerak.")
    with db() as con:
        task = row_to_dict(con.execute("SELECT * FROM tech_tasks WHERE id=?", (tid,)).fetchone())
        if not task:
            raise AppError(HTTPStatus.NOT_FOUND, "Topshiriq topilmadi.")
        if action == "accept":
            require_role(user, {ROLE_TECH, ROLE_ADMIN, ROLE_HR})
            con.execute("UPDATE tech_tasks SET tech_user_id=?, status='in_progress', started_at=COALESCE(started_at, ?) WHERE id=?", (user["id"], now_sql(), tid))
        elif action == "start":
            require_role(user, {ROLE_TECH, ROLE_ADMIN, ROLE_HR})
            con.execute("UPDATE tech_tasks SET status='in_progress', started_at=COALESCE(started_at, ?) WHERE id=?", (now_sql(), tid))
        elif action == "done":
            require_role(user, {ROLE_TECH, ROLE_ADMIN, ROLE_HR})
            con.execute("UPDATE tech_tasks SET status='done', done_at=?, cost=COALESCE(?, cost) WHERE id=?", (now_sql(), safe_int(data.get("cost")), tid))
        elif action == "close":
            require_role(user, HR_ROLES | {ROLE_DIRECTOR, ROLE_ADMIN})
            con.execute("UPDATE tech_tasks SET status='closed' WHERE id=?", (tid,))
        elif action == "assign":
            require_role(user, HR_ROLES | {ROLE_DIRECTOR, ROLE_ADMIN})
            con.execute("UPDATE tech_tasks SET status='assigned', assigned_by=? WHERE id=?", (user["id"], tid))
        else:
            raise AppError(HTTPStatus.BAD_REQUEST, "Noma'lum texnik amal.")
        con.commit()
    return {"ok": True}


def api_positions_action(user: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    require_role(user, HR_ROLES | {ROLE_ADMIN})
    action = clean_text(data.get("action"), 30)
    with db() as con:
        if action == "add":
            name = clean_text(data.get("name"), 160)
            if not name:
                raise AppError(HTTPStatus.BAD_REQUEST, "Lavozim nomini kiriting.")
            con.execute("INSERT INTO positions (name) VALUES (?)", (name,))
        elif action == "delete":
            pid = safe_int(data.get("id"))
            con.execute("DELETE FROM positions WHERE id=?", (pid,))
        else:
            raise AppError(HTTPStatus.BAD_REQUEST, "Noma'lum lavozim amali.")
        con.commit()
    return {"ok": True}


def api_user_update(user: dict[str, Any], uid: int, data: dict[str, Any]) -> dict[str, Any]:
    require_role(user, {ROLE_ADMIN})
    allowed = {"role", "branch_id", "blocked", "full_name", "phone"}
    fields = [field for field in data if field in allowed]
    if not fields:
        raise AppError(HTTPStatus.BAD_REQUEST, "Yangilash uchun maydon yo'q.")
    with db() as con:
        values = [data[field] for field in fields]
        values.append(uid)
        con.execute(f"UPDATE users SET {', '.join(f'{field}=?' for field in fields)} WHERE id=?", values)
        con.commit()
        item = row_to_dict(con.execute("SELECT id,tg_id,full_name,username,phone,role,branch_id,blocked FROM users WHERE id=?", (uid,)).fetchone())
    return {"item": item}


def api_settings(user: dict[str, Any], data: dict[str, Any] | None = None) -> dict[str, Any]:
    require_role(user, {ROLE_ADMIN})
    with db() as con:
        if data is not None:
            for key, value in data.items():
                key = clean_text(key, 80)
                if not key:
                    continue
                con.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)", (key, str(value)))
            con.commit()
        rows = rows_to_dicts(con.execute("SELECT key, value FROM settings ORDER BY key").fetchall())
    return {"items": rows}


def notification_visible_sql(user: dict[str, Any]) -> tuple[str, list[Any]]:
    clauses = ["n.target_type='all'"]
    args: list[Any] = []
    if user.get("role"):
        clauses.append("(n.target_type='role' AND n.target_value=?)")
        args.append(user["role"])
    if user.get("branch_id"):
        clauses.append("(n.target_type='branch' AND n.target_value=?)")
        args.append(str(user["branch_id"]))
    clauses.append("(n.target_type='user' AND n.target_value=?)")
    args.append(str(user["id"]))
    return " OR ".join(clauses), args


def count_notifications(con: sqlite3.Connection, user: dict[str, Any], unread_only: bool = False) -> int:
    visible, args = notification_visible_sql(user)
    sql = f"""
        SELECT COUNT(*)
          FROM app_notifications n
          LEFT JOIN app_notification_reads r
            ON r.notification_id=n.id AND r.user_id=?
         WHERE ({visible})
    """
    final_args = [user["id"]] + args
    if unread_only:
        sql += " AND r.notification_id IS NULL"
    app_count = sql_count(con, sql, tuple(final_args))
    trust_count = sql_count(
        con,
        "SELECT COUNT(*) FROM trust_notice_reads WHERE chat_id=? AND seen=0",
        (user.get("tg_id"),),
    )
    return app_count + trust_count


def list_notifications(con: sqlite3.Connection, user: dict[str, Any], limit: int = 50) -> list[dict[str, Any]]:
    visible, args = notification_visible_sql(user)
    rows = rows_to_dicts(
        con.execute(
            f"""
            SELECT n.*, CASE WHEN r.notification_id IS NULL THEN 0 ELSE 1 END AS read
              FROM app_notifications n
              LEFT JOIN app_notification_reads r
                ON r.notification_id=n.id AND r.user_id=?
             WHERE ({visible})
             ORDER BY n.id DESC
             LIMIT ?
            """,
            tuple([user["id"]] + args + [limit]),
        ).fetchall()
    )
    for item in rows:
        item["kind"] = "app"
    trust_rows = rows_to_dicts(
        con.execute(
            """
            SELECT tn.id, tn.title, tn.target_label, tn.sender_name, tn.created_at,
                   tr.seen AS read, tr.seen_at
              FROM trust_notice_reads tr
              JOIN trust_notices tn ON tn.id=tr.notice_id
             WHERE tr.chat_id=?
             ORDER BY tn.id DESC
             LIMIT ?
            """,
            (user.get("tg_id"), limit),
        ).fetchall()
    )
    for item in trust_rows:
        item["kind"] = "trust"
        item["body"] = item.get("target_label")
    all_rows = rows + trust_rows
    all_rows.sort(key=lambda item: item.get("created_at") or "", reverse=True)
    return all_rows[:limit]


def api_notifications(user: dict[str, Any], params: dict[str, str]) -> dict[str, Any]:
    with db() as con:
        items = list_notifications(con, user, min(safe_int(params.get("limit")) or 60, 120))
    return {"items": items}


def api_create_notification(user: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    require_role(user, HR_ROLES | {ROLE_DIRECTOR, ROLE_MANAGER})
    title = clean_text(data.get("title"), 160)
    body = clean_text(data.get("body"), 2000)
    if not title and body:
        title = body[:80]
    if not title:
        raise AppError(HTTPStatus.BAD_REQUEST, "Xabar sarlavhasini kiriting.")
    target_type = clean_text(data.get("target_type"), 20) or "all"
    target_value = clean_text(data.get("target_value"), 80) or None
    if user.get("role") == ROLE_MANAGER:
        target_type = "branch"
        target_value = str(user.get("branch_id"))
    with db() as con:
        cur = con.execute(
            """
            INSERT INTO app_notifications
                (title, body, target_type, target_value, sender_id, sender_name)
            VALUES (?,?,?,?,?,?)
            """,
            (title, body, target_type, target_value, user["id"], user.get("full_name")),
        )
        con.commit()
        item = row_to_dict(con.execute("SELECT * FROM app_notifications WHERE id=?", (cur.lastrowid,)).fetchone())
    return {"item": item}


def api_mark_notification(user: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    kind = clean_text(data.get("kind"), 20) or "app"
    nid = safe_int(data.get("id"))
    if not nid:
        raise AppError(HTTPStatus.BAD_REQUEST, "Xabar ID kerak.")
    with db() as con:
        if kind == "trust":
            con.execute(
                "UPDATE trust_notice_reads SET seen=1, seen_at=? WHERE notice_id=? AND chat_id=?",
                (now_sql(), nid, user.get("tg_id")),
            )
        else:
            con.execute(
                "INSERT OR IGNORE INTO app_notification_reads (notification_id, user_id) VALUES (?,?)",
                (nid, user["id"]),
            )
        con.commit()
    return {"ok": True}


def api_profile_update(user: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    with db() as con:
        profile = get_profile(con, user["id"])
        if not profile and user.get("role") != ROLE_CANDIDATE:
            raise AppError(HTTPStatus.NOT_FOUND, "Profil topilmadi.")
        for field, (table, column) in ALLOWED_PROFILE_FIELDS.items():
            if field not in data:
                continue
            value = clean_text(data.get(field), 500)
            if table == "users":
                con.execute(f"UPDATE users SET {column}=? WHERE id=?", (value, user["id"]))
            elif profile:
                con.execute(
                    f"UPDATE employee_profiles SET {column}=?, updated_at=? WHERE user_id=?",
                    (value, now_sql(), user["id"]),
                )
        if "full_name" in data:
            con.execute(
                "UPDATE users SET full_name=?, name_locked=1 WHERE id=?",
                (clean_text(data.get("full_name"), 160), user["id"]),
            )
        con.commit()
        fresh_user = row_to_dict(con.execute("SELECT * FROM users WHERE id=?", (user["id"],)).fetchone())
        fresh_profile = get_profile(con, user["id"])
    return {"user": public_user(fresh_user, fresh_profile), "profile": fresh_profile}


def api_reference(user: dict[str, Any]) -> dict[str, Any]:
    with db() as con:
        branches = rows_to_dicts(con.execute("SELECT * FROM branches ORDER BY name").fetchall())
        positions = rows_to_dicts(con.execute("SELECT * FROM positions ORDER BY id").fetchall())
        users = []
        if user.get("role") == ROLE_ADMIN:
            users = rows_to_dicts(
                con.execute(
                    "SELECT id, tg_id, full_name, username, phone, role, branch_id, created_at FROM users ORDER BY id DESC LIMIT 300"
                ).fetchall()
            )
    return {
        "branches": branches,
        "positions": positions,
        "roles": [{"value": key, "label": value} for key, value in ROLE_LABELS.items()],
        "users": users,
    }


def api_create_branch(user: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    require_role(user, {ROLE_ADMIN})
    name = clean_text(data.get("name"), 160)
    if not name:
        raise AppError(HTTPStatus.BAD_REQUEST, "Filial nomini kiriting.")
    with db() as con:
        cur = con.execute(
            """
            INSERT INTO branches (name, address, latitude, longitude, radius, phone, work_hours)
            VALUES (?,?,?,?,?,?,?)
            """,
            (
                name,
                clean_text(data.get("address"), 240),
                data.get("latitude"),
                data.get("longitude"),
                safe_int(data.get("radius")) or 150,
                clean_text(data.get("phone"), 80),
                clean_text(data.get("work_hours"), 80),
            ),
        )
        con.commit()
        item = row_to_dict(con.execute("SELECT * FROM branches WHERE id=?", (cur.lastrowid,)).fetchone())
    return {"item": item}


def api_export(user: dict[str, Any], kind: str, params: dict[str, str]) -> tuple[str, bytes, str]:
    require_role(user, HR_ROLES | {ROLE_DIRECTOR, ROLE_ACCOUNTANT, ROLE_IT})
    with db() as con:
        if kind == "attendance":
            data = api_attendance_report(user, params)["items"]
            headers = ["id", "work_date", "full_name", "branch_name", "position", "check_in_at", "check_out_at", "note"]
        elif kind == "applications":
            data = list_applications(con, user, {"limit": "1000", **params})
            headers = ["id", "created_at", "full_name", "phone", "branch_name", "position", "status", "hr_comment"]
        elif kind == "employees":
            data = list_employees(con, user, {"limit": "1000", **params})
            headers = ["user_id", "full_name", "phone", "branch_name", "position", "role", "monthly_salary", "work_hours", "rest_day"]
        else:
            raise AppError(HTTPStatus.NOT_FOUND, "Eksport turi topilmadi.")
    lines: list[list[Any]] = [headers]
    for row in data:
        lines.append([row.get(col, "") for col in headers])
    out = []
    for line in lines:
        rendered = []
        for value in line:
            text = "" if value is None else str(value)
            if any(ch in text for ch in [",", '"', "\n"]):
                text = '"' + text.replace('"', '""') + '"'
            rendered.append(text)
        out.append(",".join(rendered))
    body = "\ufeff" + "\n".join(out)
    filename = f"{kind}-{today_sql()}.csv"
    return filename, body.encode("utf-8"), "text/csv; charset=utf-8"


class Handler(SimpleHTTPRequestHandler):
    server_version = "GulnoraFarmApp/1.0"

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("%s | %s\n" % (now_sql(), fmt % args))

    def end_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        super().end_headers()

    def do_GET(self) -> None:
        try:
            parsed = urlparse(self.path)
            if parsed.path.startswith("/api/"):
                self.route_api("GET", parsed.path, parse_qs(parsed.query))
            else:
                self.serve_static(parsed.path)
        except AppError as exc:
            self.send_json({"error": exc.message, "details": exc.details}, exc.status)
        except Exception as exc:  # pragma: no cover - safety net for local app
            self.send_json({"error": "Server xatosi", "details": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_POST(self) -> None:
        self.handle_write("POST")

    def do_PATCH(self) -> None:
        self.handle_write("PATCH")

    def handle_write(self, method: str) -> None:
        try:
            parsed = urlparse(self.path)
            if not parsed.path.startswith("/api/"):
                raise AppError(HTTPStatus.NOT_FOUND, "Sahifa topilmadi.")
            self.route_api(method, parsed.path, parse_qs(parsed.query))
        except AppError as exc:
            self.send_json({"error": exc.message, "details": exc.details}, exc.status)
        except Exception as exc:
            self.send_json({"error": "Server xatosi", "details": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("content-length") or "0")
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            raise AppError(HTTPStatus.BAD_REQUEST, "JSON noto'g'ri.")

    def auth_user(self) -> dict[str, Any]:
        return get_auth_user({key.lower(): value for key, value in self.headers.items()})

    def route_api(self, method: str, path: str, query_raw: dict[str, list[str]]) -> None:
        params = {key: values[-1] for key, values in query_raw.items()}
        if method == "GET" and path == "/api/health":
            with db() as con:
                data = {
                    "ok": True,
                    "db": str(DB_PATH),
                    "users": sql_count(con, "SELECT COUNT(*) FROM users"),
                    "employees": sql_count(con, "SELECT COUNT(*) FROM employee_profiles"),
                    "time": now_sql(),
                }
            self.send_json(data)
            return
        if method == "POST" and path == "/api/auth/login":
            self.send_json(api_login(self.read_json()))
            return

        user = self.auth_user()
        if method == "GET" and path == "/api/me":
            self.send_json(api_me(user))
        elif method == "GET" and path == "/api/home":
            self.send_json(api_home(user))
        elif method == "GET" and path == "/api/reference":
            self.send_json(api_reference(user))
        elif method == "GET" and path == "/api/stats":
            self.send_json(api_stats(user))
        elif method == "GET" and path == "/api/attendance/today":
            self.send_json(api_attendance_today(user))
        elif method == "GET" and path == "/api/attendance/report":
            self.send_json(api_attendance_report(user, params))
        elif method == "POST" and path.startswith("/api/attendance/"):
            self.send_json(api_attendance_action(user, path.rsplit("/", 1)[-1], self.read_json()))
        elif method == "GET" and path == "/api/vacancies":
            self.send_json(api_vacancies(user, params))
        elif method == "POST" and path == "/api/vacancies":
            self.send_json(api_create_vacancy(user, self.read_json()))
        elif method == "PATCH" and path.startswith("/api/vacancies/"):
            self.send_json(api_update_vacancy(user, int(path.rsplit("/", 1)[-1]), self.read_json()))
        elif method == "GET" and path == "/api/applications":
            self.send_json(api_applications(user, params))
        elif method == "POST" and path == "/api/applications":
            self.send_json(api_create_application(user, self.read_json()))
        elif method == "POST" and path == "/api/applications/action":
            self.send_json(api_application_action(user, self.read_json()))
        elif method == "GET" and path == "/api/employees":
            self.send_json(api_employees(user, params))
        elif method == "PATCH" and path.startswith("/api/employees/"):
            self.send_json(api_update_employee(user, int(path.rsplit("/", 1)[-1]), self.read_json()))
        elif method == "GET" and path == "/api/requests":
            self.send_json(api_requests(user, params))
        elif method == "POST" and path == "/api/requests":
            self.send_json(api_create_request(user, self.read_json()))
        elif method == "POST" and path == "/api/requests/action":
            self.send_json(api_request_action(user, self.read_json()))
        elif method == "GET" and path == "/api/staff-registrations":
            self.send_json(api_staff_regs(user, params))
        elif method == "POST" and path == "/api/staff-registrations":
            self.send_json(api_create_staff_reg(user, self.read_json()))
        elif method == "POST" and path == "/api/staff-registrations/action":
            self.send_json(api_staff_reg_action(user, self.read_json()))
        elif method == "GET" and path == "/api/interviews":
            self.send_json(api_interviews(user, params))
        elif method == "POST" and path == "/api/interviews/action":
            self.send_json(api_interview_action(user, self.read_json()))
        elif method == "GET" and path == "/api/finance":
            self.send_json(api_finance(user, params))
        elif method == "POST" and path == "/api/finance/action":
            self.send_json(api_finance_action(user, self.read_json()))
        elif method == "GET" and path == "/api/advance":
            self.send_json(api_advance(user, params))
        elif method == "POST" and path == "/api/advance":
            self.send_json(api_create_advance(user, self.read_json()))
        elif method == "POST" and path == "/api/advance/action":
            self.send_json(api_advance_action(user, self.read_json()))
        elif method == "GET" and path == "/api/tech":
            self.send_json(api_tech(user, params))
        elif method == "POST" and path == "/api/tech":
            self.send_json(api_create_tech(user, self.read_json()))
        elif method == "POST" and path == "/api/tech/action":
            self.send_json(api_tech_action(user, self.read_json()))
        elif method == "POST" and path == "/api/positions/action":
            self.send_json(api_positions_action(user, self.read_json()))
        elif method == "PATCH" and path.startswith("/api/users/"):
            self.send_json(api_user_update(user, int(path.rsplit("/", 1)[-1]), self.read_json()))
        elif method == "GET" and path == "/api/settings":
            self.send_json(api_settings(user))
        elif method == "PATCH" and path == "/api/settings":
            self.send_json(api_settings(user, self.read_json()))
        elif method == "GET" and path == "/api/notifications":
            self.send_json(api_notifications(user, params))
        elif method == "POST" and path == "/api/notifications":
            self.send_json(api_create_notification(user, self.read_json()))
        elif method == "POST" and path == "/api/notifications/read":
            self.send_json(api_mark_notification(user, self.read_json()))
        elif method == "PATCH" and path == "/api/profile":
            self.send_json(api_profile_update(user, self.read_json()))
        elif method == "POST" and path == "/api/admin/branches":
            self.send_json(api_create_branch(user, self.read_json()))
        elif method == "GET" and path.startswith("/api/export/"):
            filename, body, content_type = api_export(user, path.rsplit("/", 1)[-1], params)
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            raise AppError(HTTPStatus.NOT_FOUND, "API topilmadi.")

    def serve_static(self, path: str) -> None:
        if path in {"", "/"}:
            path = "/index.html"
        target = (WEB_ROOT / path.lstrip("/")).resolve()
        if not str(target).startswith(str(WEB_ROOT.resolve())):
            raise AppError(HTTPStatus.FORBIDDEN, "Ruxsat yo'q.")
        if not target.exists() or target.is_dir():
            target = WEB_ROOT / "index.html"
        body = target.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", mimetypes.guess_type(str(target))[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, data: dict[str, Any], status: int = HTTPStatus.OK) -> None:
        body = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    init_app_db()
    WEB_ROOT.mkdir(exist_ok=True)
    httpd = ThreadingHTTPServer((APP_HOST, APP_PORT), Handler)
    print(f"Gulnora Farm ilova: http://{APP_HOST}:{APP_PORT}")
    print(f"SQLite baza: {DB_PATH}")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
