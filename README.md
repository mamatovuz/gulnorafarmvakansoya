# 🌿 Gulnora Farm — HR / Ishga qabul boti

To'liq ishlaydigan **Telegram bot** — ishga qabul qilish jarayonini boshqarish uchun.
Nomzod, HR va Administrator uchun alohida panellar bilan.

## ⚙️ Imkoniyatlar

### 🧑 Nomzod
- Majburiy obuna tekshiruvi (bir nechta kanal)
- Vakansiyalarni ko'rish
- **📝 Ishga ariza topshirish** — 20 savoldan iborat to'liq anketa:
  ism, tug'ilgan sana (`kun.oy.yil` — majburiy tekshiriladi), manzil, filial, lavozim,
  smena, ma'lumot, ish tajribasi, sudlanganlik, oilaviy holat, farzandlar,
  oldingi/kutilayotgan maosh, **kompyuter savodxonligi** (Ha / O'rtacha / Yo'q),
  tillar, ishlash niyati, sabab,
  **telefon** (faqat `+998XXXXXXXXX` — bo'sh joysiz, bitta raqam),
  rezyume/diplom (fayl yoki o'tkazib yuborish)
- Yakuniy tasdiqlash: **✅ Tasdiqlash · ✏️ Tahrirlash · ❌ Bekor qilish**
- Tasdiqlangach ariza avtomatik HR va Adminlarga yuboriladi
- Suhbat taklifini tasdiqlash yoki boshqa vaqt taklif qilish
- «Mening arizalarim» — holatni kuzatish

### 👨‍💼 HR panel
- **Dashboard** — bugungi / haftalik / oylik arizalar, holatlar, filial va vakansiya statistikasi
- **Arizalar** — holat bo'yicha filtrlash (yangi / suhbat / qabul / rad)
  - 👁 Batafsil ko'rish · 📅 Suhbatga chaqirish · ✅ Ishga qabul · ❌ Rad etish · 📝 Izoh
- **Vakansiyalar** — yaratish / tahrirlash / yopish / qayta ochish / o'chirish
- **Xabarnoma** — barchaga / xodimlarga / nomzodlarga / filial bo'yicha (rasm, video, fayl)
- **Qidiruv** — ism / telefon / filial / lavozim bo'yicha

### 🏢 Gulnora Farm hodimi (self-registratsiya)
- `/start` → **🏢 Gulnora Farm hodimi** tugmasi orqali mavjud xodim o'zini ro'yxatdan o'tkazadi
- Savollar: ism-familiya, tug'ilgan sana, **telefon** (`+998XXXXXXXXX`), **yo'nalish (rol)**,
  manzil, **filial** (admin ro'yxatidan), ish vaqti (dan-gacha), oylik, dam olish kuni,
  forma bor/yo'q, **ma'lumoti** (o'rta maxsus / oliy farmatsevt / boshqa yo'nalish / diplom yo'q),
  **necha yildan beri Gulnora Farmda ishlaydi**, **oxirgi 10 kundagi rasm**
- Rolga qarab qo'shimcha savol: filial rahbari/direktor uchun boshqaruv hajmi
- Yakunda: **HR panelga yuborilsinmi?** → tasdiqlansa xodimga rol va davomat paneli ochiladi
- HR **rad etsa sababini yozadi** — sabab ariza raqami bilan xodimga yuboriladi, panel ochilmaydi
- Tasdiqlangach xodim ma'lumotlari **maxfiy kanalga** avtomatik joylanadi (kanal ulangan bo'lsa)
- **🎓 Diplom statistikasi** (HR va Direktor panelida) — nechta xodimda diplom bor / yo'q,
  ma'lumot turlari va filiallar kesimida + diplomi yo'q xodimlar ro'yxati
- Yo'nalishlar: 💊 Farmatsevt · 👨‍💼 Filial rahbari · 👔 Direktor · 🧮 Buxgalter · 🧹 Tozalik rahbari · 📦 Omborchi · 🚚 Haydovchi

### 📍 Davomat (GPS)
- **📍 Ishga keldim** — bot GPS joylashuvni so'raydi; filial koordinatasidan **belgilangan radius** (default 150 m)
  ichida bo'lsa ✅ kelgan vaqt yoziladi, uzoqda bo'lsa ❌ «Siz ofisda emassiz»
- **🏁 Ishdan ketdim** — ketish vaqti ham GPS bilan yoziladi (kelgan/ketgan vaqt hisobotda ko'rinadi)
- **Kech qolgan / erta ketgan** — ish vaqti (`09:00 - 18:00`) asosida avtomatik belgilanadi
- **⏸ Tanaffus / ▶️ Ishni davom ettirish** — ochiq ish kuni yozuvi bo'yicha ishlaydi
  (tungi smenada yarim tundan o'tsa ham topiladi)
- **🔄 Dam olish kunini almashtirish** — so'rov filial rahbari + HR ga boradi, tasdiqlansa dam kuni yangilanadi
- **📩 HR ga murojaat** — 3 yo'nalish: 🕒 ish soatini o'zgartirish · 💸 maoshni oshirish ·
  ✉️ boshqa masala. Ish soati so'rovi HR tasdiqlagach profilga yoziladi va davomat
  aynan yangi vaqtdan hisoblanadi; rad etilsa HR sababi xodimga yuboriladi
- Hisobotlar: **kunlik / haftalik / oylik**, **filial kesimida**, kim necha kun keldi / kim kelmadi —
  HR, Direktor, Filial rahbari va Buxgalter panellarida

### 🧮 Buxgalter paneli
- **📍 Davomat** va **⏰ Kech/erta hisobot** (barcha filiallar bo'yicha)
- **🏢 Filial tanlab ko'rish** — tanlangan filial xodimlari va bugungi keldi/ketti
- **👥 Xodimlar** — oylik belgilash / oshirish, **oylik berildi/berilmadi**, jarima yozish, to'lovlar tarixi
- **🛌 Dam olish so'rovlari**

### 👑 Administrator paneli
- **Statistika** — foydalanuvchilar, xodimlar, arizalar, eng faol HR, eng ko'p ariza lavozimlar
- **Filiallar** — qo'shish / tahrirlash / o'chirish + **📍 GPS koordinatasi** (davomat uchun)
- **Kanallar** (majburiy obuna) — qo'shish / o'chirish / faollashtirish
- **Adminlar** va **HR xodimlari** — qo'shish / o'chirish
- **Rollar** — Administrator / HR / Direktor / Buxgalter / Filial rahbari / Farmatsevt / Oddiy xodim / Nomzod
- **Audit log** — barcha harakatlar sana-vaqti bilan

## 🚀 Ishga tushirish

```bash
# 1. Virtual muhit
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Linux/Mac

# 2. Kutubxonalar
pip install -r requirements.txt

# 3. Sozlamalar
copy .env.example .env       # Windows  (Linux: cp .env.example .env)
# .env faylni oching va to'ldiring:
#   BOT_TOKEN      — @BotFather dan olingan token
#   SUPER_ADMINS   — sizning Telegram ID (bir nechta bo'lsa vergul bilan)

# 4. Ishga tushirish
python bot.py
```

## 📌 Muhim eslatmalar

- **Bosh admin**: `.env` dagi `SUPER_ADMINS` ID lari avtomatik administrator bo'ladi.
- **Majburiy obuna**: bot tekshirishi uchun **kanalда administrator** qilib qo'yilishi shart.
  Aks holda obunani aniqlay olmaydi (va foydalanuvchi bloklanmasligi uchun o'sha kanal o'tkazib yuboriladi).
- Yopiq kanal ID si `-100...` ko'rinishida, ochiq kanal `@username` ko'rinishida kiritiladi.
- Yangi HR/admin qo'shishdan oldin, o'sha odam **botga `/start`** bosgan bo'lishi kerak (ID bazaga tushishi uchun).

## 📂 Loyiha tuzilishi

```
gulnorafarm/
├── bot.py                 # Ishga tushirish nuqtasi
├── config.py              # .env dan sozlamalar
├── states.py              # FSM holatlari
├── keyboards.py           # Barcha tugmalar
├── utils.py               # Obuna tekshirish, matn formatlash, broadcast
├── database/
│   ├── db.py              # Jadvallar (schema) va init
│   └── queries.py         # Barcha SQL so'rovlar
└── handlers/
    ├── common.py          # /start, obuna, yordam
    ├── candidate.py       # Nomzod: vakansiya, ariza, suhbat
    ├── hr.py              # HR panel
    ├── admin.py           # Administrator paneli (+ filial GPS koordinatasi)
    ├── staff.py           # Filial rahbari / Farmatsevt / Direktor panellari
    ├── staffreg.py        # 🏢 Gulnora Farm hodimi self-registratsiya + HR tasdiqlash
    ├── attendance.py      # 📍 Ishga keldim/🏁 Ishdan ketdim (GPS) + davomat hisobotlari
    ├── accountant.py      # 🧮 Buxgalter paneli (oylik/jarima/davomat)
    └── dayoff.py          # 🔄 Dam olish kunini almashtirish so'rovlari
```

## 🛠 Texnologiyalar
- Python 3.10+
- [aiogram 3.x](https://docs.aiogram.dev/) — Telegram Bot API
- SQLite (aiosqlite) — ma'lumotlar bazasi
