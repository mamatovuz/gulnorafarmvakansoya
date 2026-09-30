"""FastAPI ilovasi: /api/v1 + Swagger (/api/docs)."""
import asyncio
import hashlib
import json
import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response

from api import API_VERSION, settings
from api.core import ApiError, connect, error_response, ok, write_lock
from api.routers import comms, employees, integration, org, workforce

logger = logging.getLogger("hrbot.api")

DESCRIPTION = """
**Gulnora Farm HR Telegram bot** uchun integratsiya API (Staffora SaaS va boshqa tizimlar).

### Autentifikatsiya
`Authorization: Bearer gfk_xxxxxxxx_...` (yoki `X-API-Key`). Kalitlar `python -m api.manage create-key`
yoki `POST /api/v1/api-keys` (admin) orqali yaratiladi. Har kalitda **scopes** (ruxsatlar),
muddat (`expires_at`), bekor qilish (`revoke`) va qayta yaratish (`rotate`) bor.

### Javob formati
```json
{"success": true, "data": {...}, "meta": {"page": 1, "limit": 50, "total": 120, "pages": 3}}
{"success": false, "error": {"code": "not_found", "message": "...", "details": {}}}
```

### Idempotency
Yozish so'rovlarida `Idempotency-Key: <uuid>` yuboring — tarmoq xatosida qayta yuborilsa,
yozuv ikki marta yaratilmaydi, oldingi javob qaytadi (`Idempotent-Replayed: true`).

### Webhooklar
`POST /api/v1/webhooks` — imzo: `X-Webhook-Signature: t=<unix>,v1=hex(HMAC_SHA256(secret, "<t>.<body>"))`.
Xato bo'lsa eksponensial retry; jurnal: `GET /api/v1/webhooks/{id}/deliveries`.

### Vaqt
Barcha vaqtlar ISO 8601, `Asia/Tashkent` (+05:00).
"""

TAGS = [
    {"name": "Employees", "description": "Xodimlar (users + employee_profiles)"},
    {"name": "Branches", "description": "Filiallar"},
    {"name": "Departments", "description": "Bo'limlar (API orqali qo'shilgan tuzilma)"},
    {"name": "Positions", "description": "Lavozimlar (botdagi yo'nalishlar)"},
    {"name": "Schedules", "description": "Ish vaqti, dam olish kuni, smena"},
    {"name": "Attendance", "description": "Check-in / check-out (tashqi qurilma, Staffora)"},
    {"name": "Leaves", "description": "Dam olish kunini almashtirish so'rovlari"},
    {"name": "Announcements", "description": "Bot orqali e'lon (Ishonch xabari)"},
    {"name": "Notifications", "description": "Bitta xodimga bot xabari"},
    {"name": "Users", "description": "Bot foydalanuvchilari (Telegram)"},
    {"name": "Company", "description": "Kompaniya"},
    {"name": "Integration", "description": "Staffora integratsiyasi: info, health, sync, changes, webhook"},
    {"name": "Webhooks", "description": "Chiquvchi webhook obunalari"},
    {"name": "API keys", "description": "Kalitlarni boshqarish (admin)"},
]

_stop = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _stop
    from api.migrations import run_migrations
    from config import DB_PATH
    await run_migrations(DB_PATH)
    task = None
    if settings.API_WORKERS_ENABLED:
        from api.workers import worker_loop
        _stop = asyncio.Event()
        task = asyncio.create_task(worker_loop(_stop))
    logger.info("API tayyor: http://%s:%s/api/docs", settings.API_HOST, settings.API_PORT)
    try:
        yield
    finally:
        if task:
            _stop.set()
            await task
        from api import telegram
        await telegram.close()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Gulnora Farm HR Bot API",
        version=API_VERSION,
        description=DESCRIPTION,
        openapi_tags=TAGS,
        lifespan=lifespan,
        docs_url="/api/docs" if settings.API_DOCS_ENABLED else None,
        redoc_url="/api/redoc" if settings.API_DOCS_ENABLED else None,
        openapi_url="/api/openapi.json" if settings.API_DOCS_ENABLED else None,
    )

    # ---------------- XATOLAR (yagona format) ----------------
    @app.exception_handler(ApiError)
    async def _api_error(request, exc: ApiError):
        return error_response(exc.status, exc.code, exc.message, exc.details, exc.headers)

    @app.exception_handler(RequestValidationError)
    async def _validation(request, exc: RequestValidationError):
        errors = [{"field": ".".join(str(x) for x in e.get("loc", []) if x != "body"),
                   "message": e.get("msg"), "type": e.get("type")} for e in exc.errors()]
        return error_response(422, "validation_error", "So'rov ma'lumotlari noto'g'ri.",
                              {"errors": errors})

    @app.exception_handler(StarletteHTTPException)
    async def _http(request, exc: StarletteHTTPException):
        code = {404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "http_error")
        return error_response(exc.status_code, code, str(exc.detail))

    @app.exception_handler(Exception)
    async def _unhandled(request, exc: Exception):
        logger.exception("Kutilmagan xato: %s %s", request.method, request.url.path)
        return error_response(500, "internal_error", "Ichki server xatosi.",
                              {"request_id": getattr(request.state, "request_id", None)})

    # ---------------- MIDDLEWARE ----------------
    @app.middleware("http")
    async def idempotency(request: Request, call_next):
        key = request.headers.get("idempotency-key")
        if (not key or request.method not in ("POST", "PUT", "PATCH", "DELETE")
                or not request.url.path.startswith("/api/v1/")):
            return await call_next(request)
        if len(key) > 200:
            return error_response(400, "invalid_idempotency_key", "Idempotency-Key juda uzun.")
        from api.security import KEY_PREFIX, _extract_token, hash_key
        token = _extract_token(request)
        parts = token.split("_", 2)
        if len(parts) != 3 or parts[0] != KEY_PREFIX:
            return await call_next(request)  # autentifikatsiya routerda rad etiladi
        async with connect() as db:
            cur = await db.execute("SELECT id, key_hash FROM api_keys WHERE key_prefix=?",
                                   (parts[1],))
            row = await cur.fetchone()
        if not row or row[1] != hash_key(token):
            return await call_next(request)
        key_id = row[0]
        body = await request.body()
        req_hash = hashlib.sha256(
            b"|".join([request.method.encode(), request.url.path.encode(),
                       str(request.url.query).encode(), body])).hexdigest()
        async with connect() as db:
            cur = await db.execute(
                "INSERT OR IGNORE INTO api_idempotency (api_key_id, idem_key, method, path, "
                "request_hash) VALUES (?,?,?,?,?)",
                (key_id, key, request.method, request.url.path, req_hash))
            await db.commit()
            inserted = cur.rowcount > 0
            if not inserted:
                prev = await (await db.execute(
                    "SELECT request_hash, state, status_code, response_body FROM api_idempotency "
                    "WHERE api_key_id=? AND idem_key=?", (key_id, key))).fetchone()
        if not inserted:
            if prev[0] != req_hash:
                return error_response(422, "idempotency_key_reused",
                                      "Bu Idempotency-Key boshqa so'rov uchun ishlatilgan.")
            if prev[1] != "done":
                return error_response(409, "request_in_progress",
                                      "Shu Idempotency-Key bilan so'rov bajarilmoqda.")
            return Response(content=prev[3], status_code=prev[2], media_type="application/json",
                            headers={"Idempotent-Replayed": "true"})
        try:
            response = await call_next(request)
        except Exception:
            async with connect() as db:  # qayta urinish mumkin bo'lsin
                await db.execute("DELETE FROM api_idempotency WHERE api_key_id=? AND idem_key=?",
                                 (key_id, key))
                await db.commit()
            raise
        chunks = [c async for c in response.body_iterator]
        content = b"".join(chunks)
        async with connect() as db:
            if response.status_code >= 500:
                await db.execute("DELETE FROM api_idempotency WHERE api_key_id=? AND idem_key=?",
                                 (key_id, key))
            else:
                await db.execute(
                    "UPDATE api_idempotency SET state='done', status_code=?, response_body=? "
                    "WHERE api_key_id=? AND idem_key=?",
                    (response.status_code, content.decode("utf-8", "replace"), key_id, key))
            await db.commit()
        headers = {k: v for k, v in response.headers.items() if k.lower() != "content-length"}
        return Response(content=content, status_code=response.status_code, headers=headers,
                        media_type=response.media_type)

    @app.middleware("http")
    async def serialize_writes(request: Request, call_next):
        """Yozuvchi so'rovlar API jarayoni ichida ketma-ket (SQLite yagona writer)."""
        if request.method in ("POST", "PUT", "PATCH", "DELETE") and                 request.url.path.startswith("/api/v1/"):
            async with write_lock():
                return await call_next(request)
        return await call_next(request)

    @app.middleware("http")
    async def common_headers(request: Request, call_next):
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex
        request.state.request_id = rid[:64]
        is_https = request.url.scheme == "https"
        if (settings.API_REQUIRE_HTTPS and not is_https
                and request.url.path.startswith("/api/")
                and request.url.path != "/api/v1/health"):
            response = error_response(403, "https_required", "Faqat HTTPS orqali ruxsat etiladi.")
            response.headers["X-Request-Id"] = request.state.request_id
            return response
        response = await call_next(request)
        if is_https:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["X-Request-Id"] = request.state.request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        if request.url.path.startswith("/api/v1/"):
            response.headers["Cache-Control"] = response.headers.get("Cache-Control", "no-store")
        for k, v in (getattr(request.state, "rate_headers", None) or {}).items():
            response.headers[k] = v
        return response

    if settings.API_CORS_ORIGINS:
        app.add_middleware(
            CORSMiddleware, allow_origins=settings.API_CORS_ORIGINS, allow_credentials=False,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
            allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-API-Key",
                           "X-Request-Id"],
            expose_headers=["X-Request-Id", "X-RateLimit-Limit", "X-RateLimit-Remaining",
                            "Idempotent-Replayed"],
        )

    # ---------------- ROUTERLAR ----------------
    prefix = "/api/v1"

    @app.get(prefix + "/health", tags=["Integration"], summary="Ochiq holat tekshiruvi (auth talab qilinmaydi)")
    async def public_health():
        data = await integration._health(False)
        return ok(data, status=200 if data["status"] == "ok" else 503)

    for r in (employees.router, workforce.attendance, org.branches, org.departments,
              org.positions, workforce.schedules, workforce.leaves, comms.announcements,
              comms.notifications, comms.users, comms.company, integration.integration,
              integration.hooks, integration.keys):
        app.include_router(r, prefix=prefix)

    def custom_openapi():
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(title=app.title, version=app.version, description=app.description,
                             routes=app.routes, tags=TAGS)
        schema.setdefault("components", {})["securitySchemes"] = {
            "BearerAuth": {"type": "http", "scheme": "bearer", "bearerFormat": "gfk_<prefix>_<secret>"}}
        public = {prefix + "/health", prefix + "/integration/webhook"}
        for path, ops in schema.get("paths", {}).items():
            for op in ops.values():
                if path not in public:
                    op["security"] = [{"BearerAuth": []}]
                op.setdefault("responses", {}).update({
                    "401": {"description": "API kalit yo'q / noto'g'ri / bekor qilingan / muddati o'tgan"},
                    "403": {"description": "Ruxsat (scope) yetarli emas"},
                    "429": {"description": "Rate limit"},
                } if path not in public else {})
        app.openapi_schema = schema
        return schema

    app.openapi = custom_openapi
    return app


app = create_app()
