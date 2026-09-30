"""API sozlamalari (.env / muhit o'zgaruvchilaridan)."""
import os

from dotenv import load_dotenv

load_dotenv()


def _bool(name, default=False):
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int(name, default):
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


# Railway (yoki boshqa PaaS) muhitini aniqlash — production uchun xavfsiz standartlar
IS_PRODUCTION = bool(
    os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("RAILWAY_PROJECT_ID")
    or os.getenv("API_ENV", "").strip().lower() == "production"
)

# Railway portni $PORT orqali beradi va tashqi so'rovlarni shu portga yo'naltiradi.
# Ustuvorlik: API_PORT > PORT > 8090
API_PORT = int(os.getenv("API_PORT") or os.getenv("PORT") or 8090)
# Railway konteyneri tashqaridan kirishi uchun 0.0.0.0 da tinglash kerak
API_HOST = os.getenv("API_HOST", "0.0.0.0" if IS_PRODUCTION else "127.0.0.1").strip()

# TLS Railway edge'da tugaydi; ilova X-Forwarded-Proto orqali tekshiradi.
# true => http orqali kelgan /api/v1 so'rovlari rad etiladi (health bundan mustasno).
API_REQUIRE_HTTPS = _bool("API_REQUIRE_HTTPS", IS_PRODUCTION)

# Vergul bilan ajratilgan ruxsat etilgan originlar. Bo'sh => CORS o'chiq
# (server-server integratsiyasi uchun CORS kerak emas).
API_CORS_ORIGINS = [
    o.strip() for o in os.getenv("API_CORS_ORIGINS", "").split(",") if o.strip()
]

# Har bir API kalit uchun daqiqasiga so'rovlar limiti
API_RATE_LIMIT_PER_MINUTE = _int("API_RATE_LIMIT_PER_MINUTE", 120)

# Swagger / OpenAPI (/api/docs, /api/openapi.json). Productionda standart — o'chiq.
API_DOCS_ENABLED = _bool("API_DOCS_ENABLED", not IS_PRODUCTION)

# Fon ishchilari (webhook yetkazish, Telegram outbox). Testlarda o'chiriladi.
API_WORKERS_ENABLED = _bool("API_WORKERS_ENABLED", True)
API_WORKER_INTERVAL_SECONDS = _int("API_WORKER_INTERVAL_SECONDS", 5)

# Telegram orqali xabar yuborish (e'lon / bildirishnoma). O'chirilsa — navbatda qoladi.
API_TELEGRAM_SEND_ENABLED = _bool("API_TELEGRAM_SEND_ENABLED", True)

# Webhook yetkazish sozlamalari
WEBHOOK_MAX_ATTEMPTS = _int("WEBHOOK_MAX_ATTEMPTS", 8)
WEBHOOK_TIMEOUT_SECONDS = _int("WEBHOOK_TIMEOUT_SECONDS", 10)
WEBHOOK_BACKOFF_BASE_SECONDS = _int("WEBHOOK_BACKOFF_BASE_SECONDS", 30)
# true => faqat https:// webhook manzillari, localhost/ichki IP lar taqiqlanadi (SSRF)
WEBHOOK_REQUIRE_HTTPS = _bool("WEBHOOK_REQUIRE_HTTPS", IS_PRODUCTION)

# Staffora -> bot kiruvchi webhook imzosi uchun umumiy maxfiy kalit
INTEGRATION_INBOUND_SECRET = os.getenv("INTEGRATION_INBOUND_SECRET", "").strip()

# Telegram Mini App initData amal qilish muddati (soniya)
TELEGRAM_INIT_DATA_MAX_AGE = _int("TELEGRAM_INIT_DATA_MAX_AGE", 86400)

EVENT_SOURCE = os.getenv("API_EVENT_SOURCE", "employee_bot").strip() or "employee_bot"
COMPANY_NAME = os.getenv("COMPANY_NAME", "Gulnora Farm").strip()
TIMEZONE = "Asia/Tashkent"
