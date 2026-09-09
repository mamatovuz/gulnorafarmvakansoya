# Gulnora Farm — HR / Ishga qabul Telegram boti (to'liq hujjat)

Bu hujjatda bot boshidan oxirigacha nima ish qilishi, qaysi rol nima qila olishi,
qanday jadvallar ishlatilishi va qaysi jarayonlar avtomatik ishlashi — hammasi
batafsil, nuqta-verguligacha yozilgan.

> **Muhim eslatma (oxirgi yangilik):** Endi bot xodimlarga ish vaqti atrofida
> **Verifiks** ilovasidan **kirish/chiqish** qayd etishni eslatadi. Bu haqda
> pastdagi **«Ish vaqti va Verifiks eslatmalari»** bo'limida to'liq yozilgan.

---

## 1. Umumiy tavsif

- **Nomi:** Gulnora Farm — dorixonalar tarmog'i uchun HR va ishga qabul boti.
- **Vazifasi:** ishga nomzod qabul qilish (ariza → suhbat → qabul), mavjud
  xodimlarni ro'yxatga olish va boshqarish, oylik/avans/jarima hisob-kitobi,
  dam olish rejalari, texnik nosozliklar, kadrlar harakati hisoboti va turli
  avtomatik eslatmalar.
- **Til:** interfeys ikki tilda — **o'zbekcha (uz)** va **ruscha (ru)**. Til
  `/start` da so'raladi, keyin «🌐 Til» tugmasidan o'zgartirish mumkin.
- **Vaqt mintaqasi:** Toshkent vaqti (UTC+5). Bazadagi barcha sanalar
  `datetime('now','+5 hours')` bilan yoziladi.

### Texnologiyalar
- **Python** + **aiogram** (Telegram bot freymvorki, `async`).
- **SQLite** (`aiosqlite`) — ma'lumotlar bazasi.
- **Fon jarayonlari:** `asyncio` tsikllari (eslatmalar, hisobotlar).

### Ishga tushirish
1. `python -m venv venv` va `venv\Scripts\activate` (Windows).
2. `pip install -r requirements.txt`.
3. `.env.example` dan `.env` yarating.
4. `python bot.py`.

### `.env` sozlamalari (`config.py`)
- **`BOT_TOKEN`** — Telegram bot tokeni (majburiy; bo'lmasa bot ishga tushmaydi).
- **`SUPER_ADMINS`** — bosh adminlar tg_id lari, vergul bilan (masalan `12345,67890`).
  Ular har ishga tushishda avtomatik `admin` roli bilan yoziladi.
- **`DB_PATH`** — baza fayli yo'li (standart `hrbot.db`).

### Telegram komandalar
- **`/start`** — botni ishga tushirish (yagona ochiq komanda). Menyu koddan
  o'rnatiladi, BotFather kerak emas.

---

## 2. Rollar

Bir foydalanuvchi bitta rolga ega. Rollar (`database/db.py`):

| Rol | Kod | Kim |
|-----|-----|-----|
| Nomzod | `candidate` | Standart. Endi kirgan har kim. Ariza topshiradi. |
| Oddiy xodim | `employee` | Umumiy xodim (tozalik, ombor va h.k.). |
| Farmatsevt | `pharmacist` | Dorixona farmatsevti. |
| Filial rahbari | `manager` | Bitta filialni boshqaradi. |
| Direktor | `director` | Umumiy statistika, jarima qo'llash. |
| Moliya bo'limi | `accountant` | Oylik, avans, jarima, dori hisobi. |
| HR | `hr` | Kadrlar bo'limi — arizalar, xodimlar, so'rovlar. |
| IT xodim | `it` | Kadrlar harakati hisoboti, ism o'zgartirish. |
| Texnik xodim | `tech` | Filial texnik nosozliklarini bartaraf etadi. |
| Admin | `admin` | Hamma panellarga kira oladi, tizimni sozlaydi. |

**Admin** barcha panellarni (HR, Direktor, Moliya, IT, Rahbar, Texnik) ochib
ko'ra oladi.

---

## 3. Ma'lumotlar bazasi jadvallari (qisqacha)

`database/db.py` — sxema va migratsiya. Asosiy jadvallar:

- **`users`** — foydalanuvchilar: `tg_id`, `full_name` (haqiqiy ism),
  `name_locked` (1 bo'lsa Telegram nomi ustiga yozmaydi), `phone`, `lang`,
  `role`, `branch_id`, `blocked`.
- **`branches`** — filiallar: nom, manzil, GPS (`latitude`/`longitude`),
  `radius` (metr), telefon, `work_hours` (ish vaqti). Standart 16 ta Andijon
  filiali koddan seed qilinadi.
- **`vacancies`** — vakansiyalar: lavozim, filial, smena, oylik, talablar,
  mas'uliyat, sharoit, kerakli xodim soni/jinsi, kanalga joylangan post id lari,
  `filled` (to'ldi), `is_active`.
- **`applications`** — ishga arizalar: to'liq anketa (ism, tug'ilgan sana, jins,
  shahar/tuman/manzil, filial, lavozim, ma'lumot, tajriba, sudlanganlik, oilaviy
  holat, farzand, oldingi/kutilgan maosh, kompyuter savodxonligi, tillar,
  telefon, rasm, rezyume), `status`, `accept_kind` (hire/trial/learner),
  kelishilgan oylik.
- **`interviews`** — suhbatlar: sana, vaqt, manzil, izoh, nomzod javobi
  (`pending`/`confirmed`/`reschedule`), kelish holati, eslatma flaglari.
- **`employee_profiles`** — xodim profili: rol, lavozim, filial, forma holati,
  oylik, tug'ilgan sana, manzil, `work_hours`, `rest_day` (dam olish kuni),
  rasm, smena, ota/ona telefoni, **maxfiy hujjatlar** (pasport oldi/orqa,
  diplom), `emp_status` (doimiy/sinov/o'rganuvchi), yangilash bayroqlari.
- **`staff_regs`** — «Gulnora Farm hodimi» o'zini ro'yxatga olish so'rovlari
  (HR tasdiqlaydi/rad etadi).
- **`salary_payments`** — oylik to'lovlari.
- **`salary_deductions`** — oylikdan foiz kesish (rahbar 10%, xodim 5%), har
  yozuv aniq bitta oyga (`period` = YYYY-MM).
- **`fines`** — jarimalar: summa, sabab, `source` (finance/hr), `cancelled`
  (bekor qilingan).
- **`staff_medicines`** — dorixonadan olingan dorilar (yakuniy oylikdan ayiriladi).
- **`advance_requests`** — avans so'rovlari: `period`, karta raqami, miqdor,
  `status` (pending/confirmed/declined), (user, period) yagona.
- **`salary_raise_requests`** — maosh oshirish so'rovi (xodim ⇄ HR kelishuvi).
- **`work_hour_requests`** — ish vaqtini o'zgartirish so'rovi.
- **`branch_transfer_requests`** — boshqa filialga o'tish so'rovi.
- **`manager_requests`** — filial rahbari so'rovlari (xodim kerak / texnik).
- **`dayoff_requests`** — dam olish kunini almashtirish so'rovlari.
- **`dayoff_plans` / `dayoff_plan_items`** — kunlik dam olish rejasi (har filial,
  har kun uchun bitta reja; rahbar tasdiqlaydi, HR ga to'planadi).
- **`termination_requests`** — ishdan bo'shatish so'rovlari (rahbar/direktor → HR).
- **`dismissed_employees`** — ishdan bo'shatilganlar arxivi (qayta olish uchun).
- **`probations`** — sinov/o'rganuvchi muddati (start + N kun), eslatma flaglari.
- **`hr_events`** — kadrlar harakati (ishga olindi / ketdi / ko'chirildi /
  ism o'zgardi) — IT hisoboti uchun.
- **`positions`** — ishga arizadagi yo'nalishlar ro'yxati.
- **`channels`** — obuna kanallari.
- **`trust_notices` / `trust_notice_reads`** — «Ishonch xabari» va uni kim
  ko'rgani.
- **`tech_tasks` / `tech_task_replies`** — texnik topshiriqlar va yozishmalar.
- **`request_notices`** — bir so'rov bir necha HR ga yuborilganda, kimdir
  tasdiqlagach qolganlarnikini yangilash/o'chirish uchun xabar id lari.
- **`audit_logs`** — muhim amallar jurnali.
- **`settings`** — kalit-qiymat sozlamalari (soatlar, kanallar, «yuborildi»
  bayroqlari va h.k.).

> Migratsiya avtomatik: eski bazalarga yangi ustunlar `ALTER TABLE` bilan
> qo'shiladi, ismlar tiklanadi, `accept_kind` orqaga to'ldiriladi.

---

## 4. Foydalanuvchi turlariga ko'ra funksiyalar

### 4.1. Nomzod (`candidate`)
Endi kirgan har kim — nomzod. `/start` da til so'raladi, telefon so'raladi.
Asosiy menyu (ariza topshirmagan bo'lsa faqat 2 tugma):
- **«📝 Ishga ariza topshirish»** — to'liq anketa (quyida).
- **«🧑‍💼 Gulnora Farm hodimi»** — mavjud xodim o'zini ro'yxatga oladi.
- **«💼 Vakansiyalar»** — ochiq vakansiyalar ro'yxati, batafsil ko'rib, ariza
  topshirish.
- **«📄 Mening arizalarim»** — o'z arizalari holati.
- **«🌐 Til»** — til almashtirish.

**Ishga ariza (anketa) bosqichlari** (`Apply` FSM, `handlers/candidate.py`):
ism-sharif → tug'ilgan sana → jins → shahar/viloyat → tuman → aniq manzil →
filial → lavozim → lavozimga oid qo'shimcha savol → (farmatsevtga) forma bormi →
smena → ma'lumot → umumiy tajriba → oldingi ish yili → sudlanganlik → oilaviy
holat → farzand → oldingi maosh → kompyuter savodxonligi → tillar → ishlash
niyati → sabab → telefon → **rasm (oxirgi 10 kunda tushgan, majburiy)** →
rezyume (ixtiyoriy) → yakuniy tasdiqlash. Tasdiqdan oldin tahrirlash mumkin.
To'ldirilmagan majburiy maydonlar alohida ko'rsatiladi. Ariza HR ga va (sozlansa)
nomzodlar kanaliga tushadi.

### 4.2. Umumiy xodim menyusi (barcha xodim rollari)
Rol berilgach asosiy menyuda:
- **«👤 Mening profilim»** — o'z ma'lumotlari, oylik, filial, dam olish kuni.
- **«🔄 Dam olish kunini almashtirish»** — `DayoffForm` orqali so'rov.
- **«📩 HR ga murojaat»** — 4 yo'nalishli inline menyu:
  - «🕒 Ish soatini o'zgartirish» (`work_hour_requests`),
  - «💸 Maoshni oshirishni so'rash» (`salary_raise_requests`, HR ⇄ xodim kelishuvi),
  - «🏢 Boshqa filialga ko'chirish» (`branch_transfer_requests`),
  - «✉️ Boshqa masalada» (erkin matn HR ga).
- **«💼 Vakansiyalar»**, **«🌐 Til»**.

### 4.3. Farmatsevt (`pharmacist`)
«💊 Farmatsevt panel»:
- **«📊 Mening profilim»** — profil.
- **«💸 Jarimalarim»** — o'ziga yozilgan jarimalar ro'yxati.

### 4.4. Filial rahbari (`manager`)
«🏢 Filial rahbari panel» (`manager_menu`):
- **«➕ Xodim kerak»** — HR ga xodim so'rovi (`ManagerVacancyForm`: lavozim,
  soni, jinsi, smena, tajriba, izoh → tasdiq). HR tasdiqlasa vakansiya ochiladi.
- **«📢 Mening vakansiyalarim»** — o'z so'rovlaridan ochilgan vakansiyalar.
- **«🔧 Texnik nosozlik»** — matn/rasm/video/dumaloq video + muddat → HR tasdig'i
  → texnik xodimlarga topshiriq (`TechIssueForm`, `tech_tasks`).
- **«👥 Filial xodimlari»**, **«📊 Filial statistikasi»**,
  **«👕 Formasi yo'q xodimlar»**, **«📋 Filial arizalari»**.
- **«🛌 Dam olish so'rovlari»** — filial xodimlarining dam olish so'rovlarini
  tasdiqlash; shuningdek 17:00 dagi ertangi kunlik dam olish rejasini tasdiqlash.
- **«📋 Mening so'rovlarim»**, **«💬 HR ga xabar»**.

### 4.5. HR (`hr`)
«👨‍💼 HR panel» — bo'limlarga (submenu) yig'ilgan:
- **«📊 Dashboard»** — umumiy ko'rsatkichlar.
- **«📋 Arizalar / nomzodlar»**: 📥 Arizalar (Kanban / keng filter / status),
  ⏳ Kutuvchilar, 📅 Suhbatlar, ⭐ Saralanganlar, 💊 Farmatsevtlar,
  ❌ Rad etilgan murojaatlar. Ariza kartochkasida: batafsil ko'rish, suhbatga
  chaqirish, ishga/sinovga/o'rganuvchi qabul, oylik taklif qilish, kutishga
  qo'shish, rad etish, izoh, nomzodga xabar, saralashga qo'shish.
- **«📨 So'rovlar»**: 📨 Rahbar so'rovlari, 🧾 Xodim so'rovlari, 💸 Maosh
  so'rovlari, 🕒 Ish vaqti so'rovlari, 🏢 Filial o'zgartirish so'rovlari.
- **«🛌 Dam olish / sinov»**: 🛌 Dam olish so'rovlari, 🛌 Kunlik dam olish,
  🧪 Sinov muddati.
- **«💵 Avans / maosh»**: 💵 Avans, 💵 Avans sozlamalari, 🔄 Avans so'rovini
  boshidan yuborish.
- **«📢 Xabarnomalar»**: 📢 Xabarnoma (turli guruhlarga), 🔐 Ishonch xabari
  («Ko'rib chiqdim» tugmasi bilan kuzatiladi), 📊 Bildirishnoma statistika,
  📊 Excel eksport.
- **«🛠 Xodimlarni boshqarish»**: 👥 Xodimlar, 🛠 Ma'lumotlarni o'zgartirish
  (rol/filial/maqom), 🔀 Filial almashtirish, 🚫 Ishdan bo'shatish,
  🧑‍💼 Ishdan bo'shaganlar (qidiruv + ishga qayta olish).
- **«💼 Vakansiyalar (HR)»**, **«🏷 Lavozimlar»**, **«👕 Forma nazorati»**,
  **«🎓 Diplom statistikasi»**, **«🔧 Texnik ishlar»**, **«🔍 Qidiruv»**.

### 4.6. Direktor (`director`)
«📈 Direktor panel»: 📊 Direktor statistikasi, 👥 Xodimlar statistikasi,
🎓 Diplom statistikasi, 👥 Filial xodimlari, 🏢 Filiallar kesimi, 📥 Arizalar
kesimi, 🏆 Filiallar reytingi, 📈 Taqqoslash, 🔧 Texnik ishlar,
💸 Jarima qo'llash (bo'lim/yo'nalish bo'yicha), 📑 Hisobot (Excel).

### 4.7. Moliya bo'limi (`accountant`)
«🧮 Moliya bo'limi»: 🏢 Filial tanlab ko'rish, 👥 Xodimlar (oylik/jarima),
✂️ Oylik kesish (rahbardan 10% / xodimdan 5%), 🚫 Jarimani bekor qilish,
🛌 Dam olish so'rovlari, 💵 Avans oluvchilar. Xodim kartochkasida oylik
belgilash, jarima yozish, dori (`staff_medicines`) yozish va **«🧮 Yakuniy
oylik»** hisoblash (kunlik = oylik ÷ ish kunlari; jarima/avans/dori/kesim
ayiriladi).

### 4.8. IT xodim (`it`)
«🖥 IT xodim panel»: 📊 Oylik hisobot (14-sana) — o'tgan 14 dan shu 14 gacha
kadrlar harakati, 👥 Xodimlar (filial bo'yicha), ✏️ Ism o'zgartirishlar
(`ITForm.rename`).

### 4.9. Texnik xodim (`tech`)
«🔧 Texnik xodim panel»: 🆕 Yangi topshiriqlar, 🔧 Jarayondagi ishlar,
✅ Bajarilgan ishlar. Topshiriqni «boshladim / tugatdim» bilan yangilaydi,
rahbarga «💬 Javob berish», kerak bo'lsa bekor qilish (sabab bilan) yoki
boshqa texnikka o'tkazish. Tugagach rahbar 1..5 ⭐ baho beradi.

### 4.10. Admin (`admin`)
«👑 Admin panel»: 📊 Statistika, 🏢 Filiallar (qo'shish/tahrir/koordinata),
📢 Kanallar, 👥 Adminlar, 🧑‍💼 HR xodimlari, 🎭 Rollar (rol berish, filial),
👤 Foydalanuvchilar (qidiruv/bloklash), 💼 Vakansiyalar (Admin), 🏷 Lavozimlar,
📢 Xabarnoma, 📤 Eksport, ⚙️ Sozlamalar (matnlar, maxfiy/vakansiya/nomzod/suhbat/
texnik kanallar, moslik foizi), 💵 Avans sozlamalari, 🧾 Audit log,
🔄 Ma'lumotlarni yangilash (kampaniya), 🛠 Ma'lumotlarni o'zgartirish,
🔀 Filial almashtirish, 🚫 Ishdan bo'shatish, ♻️ Dublikatlar (takror yozuvlarni
o'chirish). Admin barcha boshqa panellarni ham ko'ra oladi.

---

## 5. Asosiy oqimlar (jarayonlar)

1. **Ishga qabul:** ariza → HR ko'rib chiqadi → suhbatga chaqiradi (nomzod
   tasdiqlaydi/boshqa vaqt so'raydi, eslatmalar boradi) → oylik kelishuvi
   (HR ⇄ nomzod) → ishga / sinovga / o'rganuvchi qabul → xodim profili yaratiladi.
2. **«Gulnora Farm hodimi» ro'yxati:** xodim `StaffReg` anketasini to'ldiradi
   (ism, sana, telefon, ota/ona telefoni, rol, manzil, filial, smena, ish vaqti,
   oylik, dam olish kuni, forma, ma'lumot/diplom, necha yildan beri, rasm,
   **pasport oldi+orqa**, **diplom** — oxirgi ikkisi maxfiy) → HR tasdiqlaydi
   yoki rad etadi (tayyor rad-javob matni bor).
3. **Sinov / o'rganuvchi muddati:** qabulda belgilanadi; tugashiga 3 kun qolganda
   va tugaganda HR/adminlarga avtomatik xabar.
4. **Avans:** har oy belgilangan kunda (standart 13) xodimlarga so'rov ketadi;
   xodim miqdorni (oylikning 30/60/80/100% yoki «boshqa») va karta raqamini
   tanlaydi; moliya ko'radi.
5. **Maosh oshirish / ish vaqti / filial almashtirish:** xodim so'raydi,
   HR ⇄ xodim kelishuv/tasdiqlash orqali hal qiladi.
6. **Kunlik dam olish:** 17:00 da har filial rahbariga ertangi kun rejasi
   boradi (tasdiq/tahrir), 08:30 da HR ga Excel bo'lib to'planadi.
7. **Texnik topshiriq:** rahbar (muddat bilan) → HR tasdig'i → barcha texnik
   xodimlar → biri oladi/boshlaydi/tugatadi → rahbar baholaydi.
8. **Ishdan bo'shatish / qayta olish:** rahbar/direktor so'rov yuboradi → HR
   tasdiqlaydi/rad etadi → xodim `dismissed_employees` ga arxivlanadi; keyin
   «🧑‍💼 Ishdan bo'shaganlar» dan qidirib, yangi maosh bilan ishga qaytarish mumkin.
9. **Oy oxiri hisoboti:** oyning oxirgi kunida (standart 19:00) har bir xodimga
   o'z oylik hisoboti (nimaga qancha kesilgani) yuboriladi.

---

## 6. Avtomatik fon jarayonlari (`services/reminders.py`)

Bot ishga tushganda `bot.py` quyidagi doimiy tsikllarni ishga tushiradi:

| Tsikl | Davri | Vazifasi |
|-------|-------|----------|
| `interview_reminder_loop` | 60 s | Suhbatga 1 kun va 2 soat qolganda nomzodga eslatma. |
| `probation_reminder_loop` | 1 soat | Sinov/o'rganuvchi tugashiga 3 kun / tugaganda HR ga xabar. |
| `advance_prompt_loop` | 1 soat | Belgilangan kunda (standart 13) avans so'rovi. |
| `it_report_loop` | 1 soat | Har oy 14-sanada kadrlar harakati hisoboti IT+adminlarga. |
| `dayoff_prompt_loop` | 60 s | 17:00 da rahbarlarga ertangi kunlik dam olish rejasi. |
| `dayoff_report_loop` | 60 s | 08:30 da HR ga kunlik dam olish Excel hisoboti. |
| `salary_report_loop` | 30 min | Oy oxiri (standart 19:00) xodimlarga oylik hisoboti. |
| `attendance_reminder_loop` | 60 s | Ish boshi/oxiri xabari **va Verifiks eslatmalari** (quyida). |

Har bir eslatma bir marta yuboriladi — buning uchun `settings` jadvalida
«yuborildi» bayrog'i saqlanadi. Kunlik/oylik bayroqlar har kuni bir marta
avtomatik tozalanadi (`cleanup_old_flags`), shunda `settings` cheksiz
o'smaydi.

---

## 7. Ish vaqti va Verifiks eslatmalari (batafsil)

Bu qism `attendance_reminder_loop` (har 60 soniyada) ichida ishlaydi. Har bir
xodimning ish vaqti (`employee_profiles.work_hours`, bo'lmasa filialning
`branches.work_hours`) «`08:00 - 18:00`» ko'rinishidan **boshlanish** va
**tugash** vaqtiga ajratiladi. **Dam olish kunida** (xodimning `rest_day` i
bugungi kun bo'lsa) hech qanday eslatma yuborilmaydi.

Har bir xodimga kun davomida jami **6 ta** xabar boradi (agar sozlama yoqilgan
bo'lsa — `att_reminder_enabled = 1`):

**Ish boshlanishi atrofida:**
1. **Boshlanishiga 5 daqiqa qolganda** (masalan ish 08:00 bo'lsa — 07:55 da):
   > ⏰ **Ish vaqtingiz boshlanishiga 5 daqiqa qoldi!**
   > Iltimos, **Verifiks** ilovasini oching va **kirish** qayd etib qo'ying. ✅
   > Kirishni o'z vaqtida belgilashni unutmang.
2. **Boshlanganda** (08:00 da) — umumiy tabrik:
   > ⏰ **Ish vaqtingiz boshlandi!** Xayrli, barakali ish tilaymiz! 🌿
3. **Boshlanganidan 5 daqiqa keyin** (08:05 da) — eslatma-tekshiruv:
   > ❗️ **Diqqat!** Ish vaqtingiz boshlanganiga 5 daqiqa bo'ldi. **Verifiks**
   > ilovasidan **kirish** qilishni esingizdan chiqarmadingizmi? Agar hali
   > kirmagan bo'lsangiz, iltimos hoziroq **Verifiks** ilovasiga kirib qo'ying. ✅

**Ish tugashi atrofida:**
4. **Tugashiga 5 daqiqa qolganda** (ish 18:00 bo'lsa — 17:55 da):
   > 🌇 **Ish vaqtingiz tugashiga 5 daqiqa qoldi!** **Verifiks** ilovasidan
   > **chiqish** qayd etishni esdan chiqarmang. ✅
5. **Tugaganda** (18:00 da) — umumiy:
   > 🌇 **Ish vaqtingiz tugadi!** Mehnatingiz uchun rahmat. Xayrli dam oling! 🌙
6. **Tugaganidan 5 daqiqa keyin** (18:05 da) — tekshiruv:
   > ❓ **Ish vaqtingiz tugadi.** **Verifiks** ilovasidan **chiqish**
   > qildingizmi? Agar hali chiqmagan bo'lsangiz, iltimos **Verifiks** ilovasidan
   > chiqishni belgilab qo'ying. ✅

**Texnik tafsilotlar:**
- Har bir Verifiks eslatmasi o'z target vaqtiga (ish boshi/oxiridan ±5 daqiqa)
  yetganda ishga tushadi. Vaqt `_shift_hm()` bilan hisoblanadi.
- Aniq vaqtda ketishi uchun Verifiks eslatmalari kichik (**4 daqiqalik**) oyna
  ichida yuboriladi — bot qayta ishga tushsa ham noto'g'ri vaqtda ketmasligi
  uchun. Umumiy «boshlandi/tugadi» xabarlari esa kengroq (30 daqiqalik) oynada.
- Har biri kuniga bir marta: bayroqlar `vf_in_before:`, `vf_in_after:`,
  `vf_out_before:`, `vf_out_after:` (+sana+tg_id). Ular ham har kuni
  `cleanup_old_flags` da tozalanadi.
- Yarim tundan o'tib ketadigan hollarda (masalan ish 00:02 da boshlansa)
  o'sha «5 daqiqa oldin» eslatmasi yuborilmaydi (`_shift_hm` None qaytaradi).

---

## 8. Middleware (oraliq qatlamlar) — `bot.py`

- **`BlockMiddleware`** — bloklangan foydalanuvchilarning barcha so'rovlarini
  to'xtatadi (super adminlardan tashqari).
- **`LangMiddleware`** — har bir handlerga foydalanuvchi tilini (`lang`) uzatadi.
- **`ProfileUpdateMiddleware`** — admin «🔄 Ma'lumotlarni yangilash» kampaniyasini
  boshlagan bo'lsa, xodim ma'lumotlarini yangilamaguncha boshqa bo'limlarga
  kira olmaydi.
- **`MenuEscapeMiddleware`** — asosiy menyu tugmasi bosilganda yarim qolgan
  anketani (FSM) bekor qiladi (tugma matni savolga javob bo'lib qolmasligi uchun).

---

## 9. Qo'shimcha xususiyatlar

- **Til:** to'liq uz/ru (`i18n.py`).
- **Kanallar:** vakansiyalar, nomzodlar (maxfiy), suhbat, texnik ishlar
  kanallariga avtomatik post; obuna tekshiruvi.
- **Qidiruv:** Unicode-mos (lotin/kiril) ism qidiruvi, telefon `+998` qoidasi.
- **Maxfiylik:** pasport va diplom rasmlari maxfiy — hech qaysi kanalga
  chiqmaydi, faqat «🪪 Hujjatlar» orqali ko'riladi.
- **Audit:** muhim amallar `audit_logs` ga yoziladi.
- **Ishonch xabari:** HR yuborgan xabarni kim ko'rgani `trust_notice_reads` da
  kuzatiladi, statistikasi bor.

---

*Hujjat kodning hozirgi holatiga (Gulnora Farm boti) mos. Yangi Verifiks
eslatmalari `services/reminders.py` ga qo'shildi.*
