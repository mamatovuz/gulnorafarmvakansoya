"""Umumiy yordamchilar: DB ulanishi, xato turlari, javob formati, sahifalash."""
import asyncio
import json
import math
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from fastapi import Query
from fastapi.responses import JSONResponse

from database import queries as q

TZ = timezone(timedelta(hours=5))  # Asia/Tashkent (DST yo'q) — bot bilan bir xil


# ---------------- DB ----------------
# Bot (python bot.py) va API (python -m api) bitta SQLite faylga ALOHIDA jarayonlardan
# yozadi. SQLite bir vaqtda faqat bitta yozuvchiga ruxsat beradi, shuning uchun:
#   * API o'z yozuvlarini jarayon ichida ketma-ket bajaradi (write_lock) — bot bilan
#     faqat BITTA yozuvchi sifatida raqobatlashadi, botning 5 s busy_timeout i yetadi;
#   * API ulanishi lock bo'shashini 30 s kutadi (xato bermaydi);
#   * synchronous=NORMAL (WAL rejimida xavfsiz, buzilish bo'lmaydi) — commit tez,
#     lock qisqa ushlanadi.
API_BUSY_TIMEOUT_MS = 30000
_write_locks = {}


def write_lock():
    """Joriy event loop uchun yozish qulfi (testlarda loop har safar yangi)."""
    loop = asyncio.get_running_loop()
    lock = _write_locks.get(id(loop))
    if lock is None:
        _write_locks.clear()
        lock = _write_locks[id(loop)] = asyncio.Lock()
    return lock


@asynccontextmanager
async def connect():
    """Botning o'zi ishlatadigan ulanish (WAL + pylower) + API sozlamalari."""
    db = await q._conn()
    try:
        await db.execute(f"PRAGMA busy_timeout={API_BUSY_TIMEOUT_MS}")
        await db.execute("PRAGMA synchronous=NORMAL")
        yield db
    finally:
        await db.close()


async def fetch_one(sql, params=()):
    async with connect() as db:
        cur = await db.execute(sql, params)
        row = await cur.fetchone()
        return dict(row) if row else None


async def fetch_all(sql, params=()):
    async with connect() as db:
        cur = await db.execute(sql, params)
        return [dict(r) for r in await cur.fetchall()]


async def fetch_val(sql, params=()):
    async with connect() as db:
        cur = await db.execute(sql, params)
        row = await cur.fetchone()
        return row[0] if row else None


async def execute(sql, params=()):
    async with connect() as db:
        cur = await db.execute(sql, params)
        await db.commit()
        return cur.lastrowid, cur.rowcount


# ---------------- VAQT ----------------
def now_tk():
    return datetime.now(TZ).replace(tzinfo=None)


def now_sql():
    return now_tk().strftime("%Y-%m-%d %H:%M:%S")


def iso(value):
    """Bot saqlagan 'YYYY-MM-DD HH:MM:SS' (Toshkent vaqti) -> ISO 8601 +05:00."""
    if not value:
        return None
    text = str(value).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(text[:19], fmt).replace(tzinfo=TZ).isoformat()
        except ValueError:
            continue
    return text


def parse_dt(value):
    """ISO sana/vaqtni Toshkent vaqtidagi naive datetime ga aylantiradi."""
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
    if dt.tzinfo is not None:
        dt = dt.astimezone(TZ).replace(tzinfo=None)
    return dt


# ---------------- XATOLAR ----------------
class ApiError(Exception):
    def __init__(self, status, code, message, details=None, headers=None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = details or {}
        self.headers = headers


def not_found(entity, eid):
    return ApiError(404, "not_found", f"{entity} topilmadi.", {"id": eid})


def error_response(status, code, message, details=None, headers=None):
    return JSONResponse(
        status_code=status,
        content={"success": False,
                 "error": {"code": code, "message": message, "details": details or {}}},
        headers=headers,
    )


# ---------------- JAVOB ----------------
def ok(data=None, meta=None, status=200):
    body = {"success": True, "data": data}
    if meta is not None:
        body["meta"] = meta
    return JSONResponse(status_code=status, content=json.loads(json.dumps(body, default=str)))


class Page:
    """?page=1&limit=50 sahifalash parametrlari."""

    def __init__(
        self,
        page: int = Query(1, ge=1, description="Sahifa raqami (1 dan)"),
        limit: int = Query(50, ge=1, le=200, description="Sahifadagi yozuvlar (max 200)"),
    ):
        self.page = page
        self.limit = limit

    @property
    def offset(self):
        return (self.page - 1) * self.limit

    def meta(self, total):
        return {
            "page": self.page,
            "limit": self.limit,
            "total": total,
            "pages": math.ceil(total / self.limit) if total else 0,
        }


def order_by(sort, allowed, default):
    """?sort=-created_at,name -> xavfsiz ORDER BY (faqat oq ro'yxatdagi ustunlar)."""
    if not sort:
        return default
    parts = []
    for raw in sort.split(","):
        raw = raw.strip()
        if not raw:
            continue
        desc = raw.startswith("-")
        key = raw.lstrip("-+")
        if key not in allowed:
            raise ApiError(400, "invalid_sort", f"Saralash maydoni noto'g'ri: {key}",
                           {"allowed": sorted(allowed)})
        parts.append(f"{allowed[key]} {'DESC' if desc else 'ASC'}")
    return ", ".join(parts) if parts else default


def like(text):
    return f"%{(text or '').strip().lower()}%"


def clean(value, max_len=None):
    if value is None:
        return None
    text = str(value).strip()
    if max_len:
        text = text[:max_len]
    return text
