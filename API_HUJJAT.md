# Gulnora Farm HR Bot — REST API (v1)

Staffora SaaS va boshqa tashqi tizimlar uchun API. Telegram bot bilan **bir xil `hrbot.db`**
bazasida ishlaydi va botning `database/queries.py` funksiyalari hamda biznes qoidalarini
qayta ishlatadi. Bot kodi o'zgartirilmagan.

## Ishga tushirish

```powershell
pip install -r requirements.txt
python -m api.manage create-key --name staffora --preset staffora   # kalit BIR MARTA ko'rsatiladi
python start.py      # bot + API birga (Railway Start Command)
# yoki alohida:
python bot.py        # faqat bot (avvalgidek)
python -m api        # faqat API — standart port 8090 ($PORT bo'lsa o'sha)
```

- Swagger: `http://127.0.0.1:8090/api/docs` · ReDoc: `/api/redoc` · OpenAPI: `/api/openapi.json`
- Testlar: `pip install -r requirements-dev.txt` → `python -m pytest`

API birinchi ishga tushganda migratsiya avtomatik bajariladi (qo'shimcha; bor ma'lumotlar o'chirilmaydi).

## Railway (production)

Bitta servis, bitta Start Command: **`python start.py`** (`railway.json` da ham yozilgan).
`start.py` ikkita alohida jarayonni boshqaradi:

| Jarayon | Buyruq | Yiqilsa |
|---|---|---|
| Bot | `python bot.py` (o'zgarishsiz) | butun servis chiqadi → Railway qayta ishga tushiradi (avvalgidek) |
| REST API | `python -m api` (`$PORT`, `0.0.0.0`) | faqat API qayta ishga tushadi (5s→300s backoff), bot ishlashda davom etadi |

- Migratsiya ikkala jarayondan OLDIN bir marta bajariladi (bir vaqtda ALTER TABLE to'qnashuvi bo'lmaydi). Xato bo'lsa — bot baribir ishga tushadi, API o'tkazib yuboriladi.
- `START_API=0` — API ni kod o'zgartirmasdan o'chirish (faqat bot, avvalgi holat).
- SQLite: bot va API bitta faylni ishlatadi (WAL). API yozuvlari jarayon ichida ketma-ket bajariladi, `busy_timeout=30s`, `synchronous=NORMAL`. Stress test (120 parallel API yozuvi + 200 bot yozuvi): 0 xato, integrity `ok`. **API ni bitta uvicorn worker bilan ishlating** (start.py shunday qiladi).
- Productionda (Railway o'zgaruvchilari aniqlanadi) standart: `API_DOCS_ENABLED=false`, `API_REQUIRE_HTTPS=true` (TLS Railway edge'da, `X-Forwarded-Proto` tekshiriladi, HSTS), `WEBHOOK_REQUIRE_HTTPS=true` (+ localhost/ichki IP taqiqlanadi), CORS o'chiq.
- Health check: `GET /api/v1/health` (ochiq, HTTP ham).

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

## 2026-10-13 yangilanish: maosh, to'liq xodim ma'lumoti, mustahkam xabar yuborish

**Maosh (salary)**
- `staffora` preset endi `employees:salary` ni ham beradi. Eski Staffora kaliti (employees:write + integration:write) **API ishga tushganda avtomatik** maosh ruxsatini oladi, uning webhooklarida `include_salary=1` yoqiladi (bir martalik migratsiya, `settings.api_salary_upgrade`).
- Xodim javobida: `salary = {monthly_salary (botdagi matn), amount (so'm, int), currency, is_set, source, current_month}` va qisqa `monthly_salary` (int). `amount` «4 mln», «800 ming», «3 000 000 so'm» ni to'g'ri o'qiydi.
- Profil oyligi bo'sh bo'lsa — kelishilgan oylik zaxira sifatida olinadi: sinov (`probation`) → ariza (`application`, agreed) → ro'yxatdan o'tish (`registration`). Hech biri bo'lmasa `is_set=false` — botda «💰 Oylik belgilash» orqali kiriting.
- `current_month` — botdagi «🧮 Yakuniy oylik» formulasi: `final_amount = amount - jarimalar - tasdiqlangan avans - dorilar - KPI`.
- `GET /employees/{id}/finance?period=YYYY-MM` — jarimalar, avanslar, dorilar, KPI kesimlar, to'lovlar, maosh oshirish so'rovlari (`employees:salary`).
- Yozish: `monthly_salary` raqam (`3000000`) yoki matn bo'lishi mumkin — botda «3 000 000 so'm» bo'lib saqlanadi.
- `/integration/changes` lentasi va webhooklar endi maoshni ham olib boradi (ruxsat bo'lmasa olib tashlanadi).

**To'liq xodim ma'lumoti**: `first_name / last_name / middle_name`, `telegram_name`, `gender`, `questionnaire` (shahar, tuman, oilaviy holat, farzandlar, tillar, kompyuter, tajriba, qabul turi; maosh ruxsati bilan — avvalgi/kutilgan/kelishilgan oylik), `probation` (sinov/o'rganuvchi muddati), `updated_by_self_at`. `employees:sensitive` bilan: `GET /employees/{id}/documents/{passport_front|passport_back|diploma|photo}`.

**Webhook hodisalari**: jarima, avans, dori, KPI, oylik to'lovi, maosh oshirish, sinov o'zgarsa va pasport/diplom yuklansa ham `employee.updated` ketadi (`TRIGGER_VERSION=2`).

**Takroriy yaratish (idempotent)**: `POST /departments|branches|positions|employees` da `external_ids` allaqachon bog'langan bo'lsa — `external_id_conflict` o'rniga mavjud yozuv yangilanadi va o'sha `id` qaytadi. Bir xil `code` li bo'lim/filial, bir xil nomli lavozim ham shunga bog'lanadi.

**Bildirishnomalar (`POST /notifications`)**
- Qabul qiluvchi: `employee_id` | `telegram_id` | `external_id` (+`external_source`, standart `staffora`). Ishdan bo'shagan, lekin botdagi foydalanuvchiga ham yuboriladi.
- `format: "html"` (Telegram HTML), `buttons: [{text, url}]` (inline URL tugma), `reference_id`, `message` 12000 belgigacha (4096 dan uzuni bo'linadi). `type` katta harf bo'lsa ham qabul qilinadi.
- Yuborish: Telegram flood (429) da `retry_after` kutiladi; HTML xatosida oddiy matnga o'tadi; bloklagan/chat topilmadi — doimiy xato (`permanent_failure=true`, qayta urinilmaydi); vaqtinchalik xatoda 1/5/15/60 daqiqa backoff, 5 urinish; atomik egallash — ikki marta ketmaydi.
- `POST /notifications/{id}/retry` — qo'lda qayta navbatga qo'yish. Javobda `next_attempt_at`, `telegram_message_id`.

**API kalit ruxsatini o'zgartirish**: `PATCH /api-keys/{id}` `{"add_scopes": ["employees:salary"]}` (admin).
