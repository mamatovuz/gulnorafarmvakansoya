# Gulnora Farm HR Bot — REST API (v1)

Staffora SaaS va boshqa tashqi tizimlar uchun API. Telegram bot bilan **bir xil `hrbot.db`**
bazasida ishlaydi va botning `database/queries.py` funksiyalari hamda biznes qoidalarini
qayta ishlatadi. Bot kodi o'zgartirilmagan.

## Ishga tushirish

```powershell
pip install -r requirements.txt
python -m api.manage create-key --name staffora --preset staffora   # kalit BIR MARTA ko'rsatiladi
python bot.py        # bot (avvalgidek)
python -m api        # API — alohida jarayon, standart port 8090
```

- Swagger: `http://127.0.0.1:8090/api/docs` · ReDoc: `/api/redoc` · OpenAPI: `/api/openapi.json`
- Testlar: `pip install -r requirements-dev.txt` → `python -m pytest`

API birinchi ishga tushganda migratsiya avtomatik bajariladi (qo'shimcha; bor ma'lumotlar o'chirilmaydi).

## Arxitektura

| API resursi | Bot jadvali | Izoh |
|---|---|---|
| employees | `users` + `employee_profiles` (+ `api_employee_meta`) | `id` = ichki `users.id` |
| branches | `branches` (+ `api_branch_meta`: code, status) | |
| positions | `positions` (+ `api_position_meta`) | Xodimda lavozim **matn** sifatida saqlanadi |
| departments | `api_departments` | Botda bo'lim tushunchasi yo'q edi — yangi |
| schedules | `employee_profiles.work_hours/rest_day/shift` | |
| attendance | `attendance` (eski bot jadvali) | Bot davomatni 2026-09 da o'chirgan; endi tashqi qurilma/Staffora yozadi |
| leaves | `dayoff_requests` | Dam olish kunini almashtirish so'rovi |
| announcements | `api_announcements` → `trust_notices` | Botdagi «Ishonch xabari» + «✅ Ko'rib chiqdim» |
| notifications | `api_notifications` | Bitta xodimga bot xabari |
| users | `users` | Nomzodlar ham |

Botdagi qoidalar API da ham saqlanadi:
- **Xodim yaratish** = HR xodim so'rovini tasdiqlashi: rol + filial, haqiqiy ism qulflanadi (`name_locked`), `hr_events('hired')`, `audit_logs`, xodimga bot orqali tabrik.
- **Filial o'zgarishi** → `hr_events('transferred')`. **Ism o'zgarishi** → `hr_events('name_changed')` (IT paneli hisobotiga tushadi).
- **DELETE** = botdagi «🚫 Ishdan bo'shatish»: `dismissed_employees` arxivi, sinov yozuvlari bekor, rol → `candidate`.
- **Dam olish tasdig'i** atomik (`claim_request`) — botda ham, API da ham faqat bir marta tasdiqlanadi; tasdiqlansa `rest_day` yangilanadi.
- API orqali yaratilgan dam olish so'rovi filial rahbari/HR/adminga botdagi kabi ✅/❌ tugmalari bilan boradi.
- Administrator (SUPER_ADMINS) hisobini API orqali o'zgartirib, bloklab yoki bo'shatib bo'lmaydi; `admin` rolini API orqali berib bo'lmaydi.

## Autentifikatsiya

`Authorization: Bearer gfk_<prefix>_<secret>` (yoki `X-API-Key`).
Bazada faqat sha256 hash saqlanadi. Kalitda: **scopes**, `expires_at`, **revoke**, **rotate**, alohida rate limit.

| Scope | |
|---|---|
| `employees:read/write` | Xodimlar |
| `employees:salary` | `monthly_salary` (bo'lmasa javobda maosh chiqmaydi) |
| `employees:sensitive` | Pasport/diplom/rasm `file_id` lari |
| `branches`, `departments`, `positions`, `schedules`, `attendance`, `leaves`, `announcements`, `notifications`, `users`, `company`, `integration`, `webhooks` `:read/write` | |
| `admin` | Hammasi + `/api-keys` |

`*:write` avtomatik `*:read` ni ham beradi. Staffora uchun tavsiya: `--preset staffora` (maosh/maxfiy/admin yo'q).

## Javob formati

```json
{"success": true, "data": {}, "meta": {"page": 1, "limit": 50, "total": 120, "pages": 3}}
{"success": false, "error": {"code": "duplicate", "message": "...", "details": {"existing_id": 42}}}
```
Kodlar: 400, 401 (`unauthorized/invalid_token/token_revoked/token_expired`), 403 (`insufficient_scope`),
404, 409 (`duplicate/already_processed/branch_not_empty/protected_account`), 422 (`validation_error`),
429 (`rate_limited` + `Retry-After`), 500. Vaqtlar ISO 8601 `+05:00`.

Ro'yxatlarda: `page`, `limit` (≤200), `search`, filtrlar, `sort=full_name,-hired_at`, sana oralig'i (`date_from/date_to`, `hired_from/hired_to`, `updated_since`).

## Endpointlar (`/api/v1`)

```
GET    /health                                  (ochiq)
GET|POST            /employees
GET|PUT|PATCH|DELETE /employees/{id}
GET    /employees/by-telegram/{telegram_id}
GET    /employees/by-external/{source}/{external_id}
GET    /employees/dismissed
GET    /employees/{id}/photo | /employees/{id}/attendance
GET|POST /branches          GET|PUT|PATCH|DELETE /branches/{id}
GET|POST /departments       GET|PUT|PATCH|DELETE /departments/{id}
GET|POST /positions         GET|PUT|PATCH|DELETE /positions/{id}
GET    /schedules   GET|PUT|PATCH /schedules/{employee_id}   GET /schedules/dayoff-plans?date=
GET    /attendance  GET /attendance/{id}  POST /attendance/check-in  POST /attendance/check-out
GET|POST /leaves    GET|PATCH /leaves/{id}
GET|POST /announcements  GET /announcements/{id}  POST /announcements/{id}/cancel
GET|POST /notifications  GET /notifications/{id}
GET    /users  /users/{id}  /users/by-telegram/{tg}   PATCH /users/{id} (blocked)
GET|PATCH /company
GET    /integration/info | /integration/health | /integration/changes?since_id=
POST   /integration/sync               — ommaviy upsert (dry_run bor)
POST   /integration/webhook            — Staffora → bot (HMAC imzo)
GET|PUT /integration/external-ids      DELETE /integration/external-ids/{type}/{source}/{id}
POST   /integration/telegram/verify    — Mini App initData tekshiruvi
GET|POST /webhooks  GET|PATCH|DELETE /webhooks/{id}  POST /webhooks/{id}/rotate-secret|test
GET    /webhooks/{id}/deliveries        POST /webhooks/deliveries/{id}/retry
GET|POST /api-keys  GET /api-keys/{id}  POST /api-keys/{id}/revoke|rotate   (admin)
```

### Misollar

```bash
curl -X POST http://127.0.0.1:8090/api/v1/employees \
  -H "Authorization: Bearer $KEY" -H "Idempotency-Key: 5b8c..." -H "Content-Type: application/json" \
  -d '{"telegram_id":123456789,"full_name":"Valiyev Ali","phone":"+998901234567",
       "role":"pharmacist","branch_id":3,"position":"💊 Farmatsevt",
       "work_hours":"08:00 - 17:00","rest_day":"Yakshanba",
       "external_ids":{"staffora":"ST-000123"}}'

curl -X POST .../api/v1/attendance/check-in -H "Authorization: Bearer $KEY" \
  -d '{"external_source":"staffora","external_employee_id":"ST-000123",
       "timestamp":"2026-10-01T08:04:00+05:00","verification_method":"face",
       "device":"Terminal-7","location":{"latitude":40.7473,"longitude":72.3614}}'

curl -X POST .../api/v1/announcements -H "Authorization: Bearer $KEY" \
  -d '{"title":"Yig'"'"'ilish","message":"Ertaga 9:00","branch_id":3,"require_ack":true}'
```

## Idempotency va dublikatlar

- `Idempotency-Key` header (POST/PUT/PATCH/DELETE): 24 soat ichida qayta yuborilsa, oldingi javob qaytadi (`Idempotent-Replayed: true`); boshqa body bilan → 422.
- Tabiiy kalitlar: xodim — `telegram_id` va `external_ids`; filial — `code`; lavozim — `name`; bo'lim — `code`. Takrorlansa 409 `duplicate` + `existing_id`.
- Check-in bir kunda bir marta (takror → 200, `meta.duplicate=true`).

## External ID

`api_external_ids(entity_type, entity_id, source, external_id)` — bitta yozuv bir nechta tizimga bog'lanishi mumkin.
Yaratish/yangilashda `"external_ids": {"staffora": "ST-000123"}`; sync'da `external_id` + `branch_external_id` va h.k.

## Webhooklar (bot → Staffora)

Hodisalar: `employee.created|updated|deleted`, `branch.*`, `department.*`, `position.*`,
`attendance.created|updated`, `leave.created|updated`, `announcement.created`.

Hodisalar **SQLite triggerlari** orqali yoziladi — botda qilingan o'zgarishlar (HR botda xodimni tasdiqlashi, dam olish tasdig'i va h.k.) ham yuboriladi.
Bir necha tez o'zgarish bitta hodisaga birlashtiriladi (payload doimo oxirgi holatni beradi).

```json
{"id":"evt_42","event":"employee.created","timestamp":"2026-10-01T08:00:00+05:00",
 "source":"employee_bot","api_version":"v1","data":{ ...xodim... }}
```
Headerlar: `X-Webhook-Id`, `X-Webhook-Event`, `X-Webhook-Timestamp`,
`X-Webhook-Signature: t=<unix>,v1=hex(HMAC_SHA256(secret, "<t>.<raw body>"))` — 5 daqiqadan eski imzoni rad eting.
Retry: 2xx bo'lmasa `30s·2^(n-1)` (max 6 soat), `WEBHOOK_MAX_ATTEMPTS` dan keyin `dead`; jurnal va qo'lda retry bor.
Webhook'ga zaxira: `GET /integration/changes?since_id=<cursor>`.

## Staffora → bot

`POST /api/v1/integration/webhook`, body `{"id":"...","event":"employee.updated","data":{"external_id":"ST-1",...}}`,
xuddi shu imzo formati, secret = `INTEGRATION_INBOUND_SECRET`. Bir xil `id` ikkinchi marta qayta ishlanmaydi.

## Xavfsizlik

- Telegram ID frontenddan ishonchli identity sifatida qabul qilinmaydi: Mini App uchun `/integration/telegram/verify` initData ni bot token bilan HMAC orqali tekshiradi va `auth_date` muddatini ham ko'radi.
- SQL: barcha qiymatlar parametrlangan; `sort` faqat oq ro'yxatdagi maydonlar bo'yicha ishlaydi; noma'lum JSON maydonlar rad etiladi.
- Maxfiy ma'lumotlar: kalit/secret/token javob va loglarga chiqmaydi (secret faqat yaratilganda bir marta ko'rsatiladi); maosh va hujjatlar alohida scope bilan beriladi; rasm bot token ko'rinmasligi uchun proksi orqali uzatiladi.
- Rate limit har kalitga alohida (standart 120/daqiqa), muvaffaqiyatsiz auth urinishlari IP bo'yicha cheklanadi. CORS standart holatda o'chiq.
- Production uchun API ni HTTPS reverse-proxy (nginx/caddy) ortida ishga tushiring va `WEBHOOK_REQUIRE_HTTPS=true` qiling.
