"""API kalitlari (Bearer token), ruxsatlar (scopes) va rate limit.

Kalit formati:  gfk_<prefix>_<secret>
  * Bazada faqat `prefix` va sha256(kalit) saqlanadi — kalitning o'zi hech qachon
    saqlanmaydi, loglarga va javoblarga chiqmaydi (faqat yaratilganda BIR MARTA).
  * Header:  Authorization: Bearer gfk_...   (yoki  X-API-Key: gfk_...)
"""
import hashlib
import hmac
import secrets
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field

from fastapi import Request

from api import settings
from api.core import ApiError, execute, fetch_all, fetch_one, now_sql, now_tk, parse_dt

KEY_PREFIX = "gfk"

SCOPES = {
    "employees:read": "Xodimlarni o'qish",
    "employees:write": "Xodim yaratish / o'zgartirish / ishdan bo'shatish",
    "employees:salary": "Maosh (monthly_salary) maydonini o'qish va yozish",
    "employees:sensitive": "Maxfiy hujjatlar (pasport/diplom file_id) va rasm",
    "branches:read": "Filiallarni o'qish",
    "branches:write": "Filiallarni boshqarish",
    "departments:read": "Bo'limlarni o'qish",
    "departments:write": "Bo'limlarni boshqarish",
    "positions:read": "Lavozimlarni o'qish",
    "positions:write": "Lavozimlarni boshqarish",
    "schedules:read": "Ish jadvalini o'qish",
    "schedules:write": "Ish jadvalini o'zgartirish",
    "attendance:read": "Davomatni o'qish",
    "attendance:write": "Check-in / check-out yozish",
    "leaves:read": "Dam olish so'rovlarini o'qish",
    "leaves:write": "Dam olish so'rovlarini yaratish / tasdiqlash",
    "announcements:read": "E'lonlarni o'qish",
    "announcements:write": "E'lon yuborish (bot orqali)",
    "notifications:read": "Bildirishnomalarni o'qish",
    "notifications:write": "Bildirishnoma yuborish (bot orqali)",
    "users:read": "Telegram foydalanuvchilarini o'qish",
    "users:write": "Foydalanuvchini bloklash / blokdan chiqarish",
    "company:read": "Kompaniya ma'lumotlari",
    "company:write": "Kompaniya ma'lumotlarini o'zgartirish",
    "integration:read": "Integratsiya holati, o'zgarishlar lentasi",
    "integration:write": "Sync (ommaviy upsert), tashqi ID xaritasi",
    "webhooks:read": "Webhook obunalari va yetkazish jurnalini o'qish",
    "webhooks:write": "Webhook obunalarini boshqarish",
    "admin": "Barcha ruxsatlar + API kalitlarini boshqarish",
}

# Staffora uchun tavsiya etilgan to'plam (salary/sensitive/admin yo'q)
STAFFORA_DEFAULT_SCOPES = [
    "employees:read", "employees:write", "branches:read", "branches:write",
    "departments:read", "departments:write", "positions:read", "positions:write",
    "schedules:read", "schedules:write", "attendance:read", "attendance:write",
    "leaves:read", "leaves:write", "announcements:read", "announcements:write",
    "notifications:read", "notifications:write", "company:read",
    "integration:read", "integration:write", "webhooks:read", "webhooks:write",
]


def hash_key(raw):
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def validate_scopes(scopes):
    bad = [s for s in scopes if s not in SCOPES]
    if bad:
        raise ApiError(400, "invalid_scope", "Noma'lum ruxsat(lar).",
                       {"invalid": bad, "allowed": sorted(SCOPES)})
    return sorted(set(scopes))


async def create_api_key(name, scopes, expires_at=None, description=None,
                         created_by=None, rate_limit_per_minute=None):
    """Yangi kalit yaratadi. (row, raw_key) qaytaradi — raw_key faqat shu yerda."""
    scopes = validate_scopes(scopes)
    prefix = secrets.token_hex(4)
    raw = f"{KEY_PREFIX}_{prefix}_{secrets.token_urlsafe(32)}"
    kid, _ = await execute(
        "INSERT INTO api_keys (name, description, key_prefix, key_hash, scopes, "
        "rate_limit_per_minute, expires_at, created_by) VALUES (?,?,?,?,?,?,?,?)",
        (name, description, prefix, hash_key(raw), " ".join(scopes),
         rate_limit_per_minute, expires_at, created_by),
    )
    return await get_api_key(kid), raw


async def get_api_key(kid):
    return await fetch_one("SELECT * FROM api_keys WHERE id=?", (kid,))


async def list_api_keys():
    return await fetch_all("SELECT * FROM api_keys ORDER BY id DESC")


async def revoke_api_key(kid):
    _, n = await execute(
        "UPDATE api_keys SET revoked_at=? WHERE id=? AND revoked_at IS NULL",
        (now_sql(), kid),
    )
    return n > 0


async def rotate_api_key(kid):
    """Kalitni qayta yaratadi (eski kalit darhol ishlamay qoladi, ruxsatlar saqlanadi)."""
    row = await get_api_key(kid)
    if not row:
        return None, None
    prefix = secrets.token_hex(4)
    raw = f"{KEY_PREFIX}_{prefix}_{secrets.token_urlsafe(32)}"
    await execute(
        "UPDATE api_keys SET key_prefix=?, key_hash=?, revoked_at=NULL WHERE id=?",
        (prefix, hash_key(raw), kid),
    )
    return await get_api_key(kid), raw


def public_key(row):
    """Kalit ma'lumoti — hash va kalitning o'zisiz."""
    from api.core import iso
    expires = row.get("expires_at")
    return {
        "id": row["id"],
        "name": row["name"],
        "description": row.get("description"),
        "key_prefix": f"{KEY_PREFIX}_{row['key_prefix']}_…",
        "scopes": [s for s in (row.get("scopes") or "").split() if s],
        "rate_limit_per_minute": row.get("rate_limit_per_minute"),
        "expires_at": iso(expires),
        "revoked": bool(row.get("revoked_at")),
        "revoked_at": iso(row.get("revoked_at")),
        "last_used_at": iso(row.get("last_used_at")),
        "created_by": row.get("created_by"),
        "created_at": iso(row.get("created_at")),
    }


# ---------------- AUTENTIFIKATSIYA ----------------
@dataclass
class Principal:
    key_id: int
    name: str
    scopes: set = field(default_factory=set)
    rate_limit: int = 0

    def has(self, scope):
        if "admin" in self.scopes or scope in self.scopes:
            return True
        # write => read
        if scope.endswith(":read"):
            return scope.replace(":read", ":write") in self.scopes
        return False

    @property
    def actor(self):
        return f"API:{self.name}"


class _RateLimiter:
    """Oddiy sliding-window limiter (jarayon ichida, bitta API instansiya uchun)."""

    def __init__(self):
        self.hits = defaultdict(deque)

    def check(self, bucket, limit, window=60.0):
        now = time.monotonic()
        dq = self.hits[bucket]
        while dq and now - dq[0] >= window:
            dq.popleft()
        if len(dq) >= limit:
            retry = max(1, int(window - (now - dq[0])) + 1)
            return False, 0, retry
        dq.append(now)
        return True, limit - len(dq), 0

    def reset(self):
        self.hits.clear()


rate_limiter = _RateLimiter()
_last_used_cache = {}
FAILED_AUTH_PER_MINUTE = 30


def _extract_token(request: Request):
    auth = request.headers.get("authorization") or ""
    if auth[:7].lower() == "bearer ":
        return auth[7:].strip()
    return (request.headers.get("x-api-key") or "").strip()


def _client_ip(request: Request):
    return request.client.host if request.client else "unknown"


async def authenticate(request: Request) -> Principal:
    ip = _client_ip(request)
    token = _extract_token(request)

    def fail(code, message):
        allowed, _, retry = rate_limiter.check(f"authfail:{ip}", FAILED_AUTH_PER_MINUTE)
        if not allowed:
            raise ApiError(429, "rate_limited", "Juda ko'p muvaffaqiyatsiz urinish.",
                           headers={"Retry-After": str(retry)})
        raise ApiError(401, code, message, headers={"WWW-Authenticate": "Bearer"})

    if not token:
        fail("unauthorized", "API kalit talab qilinadi (Authorization: Bearer <key>).")
    parts = token.split("_", 2)
    if len(parts) != 3 or parts[0] != KEY_PREFIX:
        fail("invalid_token", "API kalit noto'g'ri.")
    row = await fetch_one("SELECT * FROM api_keys WHERE key_prefix=?", (parts[1],))
    if not row or not hmac.compare_digest(row["key_hash"], hash_key(token)):
        fail("invalid_token", "API kalit noto'g'ri.")
    if row.get("revoked_at"):
        fail("token_revoked", "API kalit bekor qilingan.")
    if row.get("expires_at"):
        try:
            expired = parse_dt(row["expires_at"]) <= now_tk()
        except ValueError:
            expired = True
        if expired:
            fail("token_expired", "API kalit muddati tugagan.")

    principal = Principal(
        key_id=row["id"], name=row["name"],
        scopes=set((row.get("scopes") or "").split()),
        rate_limit=row.get("rate_limit_per_minute") or settings.API_RATE_LIMIT_PER_MINUTE,
    )
    allowed, remaining, retry = rate_limiter.check(f"key:{row['id']}", principal.rate_limit)
    request.state.rate_headers = {
        "X-RateLimit-Limit": str(principal.rate_limit),
        "X-RateLimit-Remaining": str(remaining),
    }
    if not allowed:
        raise ApiError(429, "rate_limited", "So'rovlar limiti oshib ketdi.",
                       {"limit_per_minute": principal.rate_limit},
                       headers={"Retry-After": str(retry)})

    # last_used ni har so'rovda emas, daqiqada bir marta yozamiz
    mono = time.monotonic()
    if mono - _last_used_cache.get(row["id"], -1e9) > 60:
        _last_used_cache[row["id"]] = mono
        await execute("UPDATE api_keys SET last_used_at=?, last_used_ip=? WHERE id=?",
                      (now_sql(), ip, row["id"]))
    request.state.principal = principal
    return principal


def require(*scopes):
    """Endpoint uchun dependency: kalit + kerakli ruxsatlar."""

    async def dependency(request: Request) -> Principal:
        principal = await authenticate(request)
        missing = [s for s in scopes if not principal.has(s)]
        if missing:
            raise ApiError(403, "insufficient_scope", "Bu amal uchun ruxsat yo'q.",
                           {"required": list(scopes), "missing": missing})
        return principal

    dependency.__name__ = "require_" + "_".join(s.replace(":", "_") for s in scopes)
    return dependency
