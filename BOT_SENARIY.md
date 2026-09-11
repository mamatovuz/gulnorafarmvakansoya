# Gulnora Farm boti — TO'LIQ SENARIY (tugmama-tugma)

Bu hujjat botning **butun ish jarayonini** boshidan oxirigacha yozadi: `/start`
bosilganda nima bo'ladi, har bir panelda qanday tugmalar bor, har bir tugma
bosilganda bot **nima qiladi** va **qanday matn/tugma chiqaradi**. Umumiy tuzilma,
jadvallar va fon jarayonlari `BOT_HUJJAT.md` da; bu yerda esa aniq senariy.

> Belgilar: 🔘 = Reply (pastdagi) tugma · ⬜ = Inline (xabar ostidagi) tugma ·
> ➡️ = tugma bosilganda nima bo'ladi.

---

## 0. `/start` — kirish senariysi (`handlers/common.py`)

Foydalanuvchi `/start` bosganda ketma-ketlik:

1. **Foydalanuvchi bazaga yoziladi** (`get_or_create_user`) va audit logga
   «Botga kirdi» yoziladi.
2. **Bloklangan bo'lsa** → «⛔ Siz bloklangansiz» tipidagi matn chiqadi, to'xtaydi.
3. **Til tanlanmagan bo'lsa** (yangi odam) → «Tilni tanlang» + ikkita inline
   tugma: ⬜ **O'zbekcha** / ⬜ **Русский** (`setlang:uz` / `setlang:ru`).
   - Til tanlangach til saqlanadi, «✅ Til o'zgartirildi» chiqadi, keyin obuna
     tekshiriladi va asosiy menyu ochiladi.
4. **Majburiy obuna yoqilgan va obuna bo'lmagan bo'lsa** → «📢 Kanal(lar)ga obuna
   bo'ling» + har kanal uchun ⬜ havola tugmasi + ⬜ **✅ Tekshirish**
   (`check_sub`). Tekshirishda hali obuna bo'lmasa alert, bo'lsa menyu ochiladi.
5. **Deep-link `/start vac_<id>`** (kanaldagi vakansiya tugmasidan) → o'sha
   vakansiya bo'yicha ariza anketasi darhol boshlanadi (filial+lavozim to'ldirilgan).
6. **Roli bo'yicha menyu:**
   - **Nomzod, ariza yo'q** → «Xush kelibsiz» + nomzod menyusi (2–3 tugma).
   - **Nomzod, arizasi bor, oxirgisi qabul qilinmagan** → «⏳ Kutish» matni.
   - **Nomzod, arizasi qabul qilingan / boshqa rol** → to'liq (rolga mos) menyu.

**Telefon so'rash** (`Reg.phone`): ba'zi oqimlarda telefon so'raladi — 🔘 «📱
Telefon raqamni yuborish» (kontakt) yoki qo'lda raqam. Kamida 7 raqam bo'lishi
shart, aks holda qайta so'raydi.

Boshqa umumiy tugmalar:
- 🔘 **🌐 Til** — istalgan payt tilni almashtirish (inline uz/ru).
- 🔘 **🏠 Asosiy menyu** — FSM tozalanib, rolga mos menyu qaytadi.
- `/help` yoki 🔘 yordam — bot imkoniyatlari haqida matn.

---

## 1. NOMZOD menyusi

Yangi nomzod (ariza topshirmagan) 3 tugma ko'radi: 🔘 **📝 Ishga ariza
topshirish**, 🔘 **🏢 Gulnora Farm hodimi**, 🔘 **🌐 Til**. Ariza topshirgach
qo'shimcha: 🔘 **💼 Vakansiyalar**, 🔘 **📄 Mening arizalarim**.

### 1.1. 🔘 💼 Vakansiyalar
- Faol vakansiyalar bo'lmasa: «😔 Hozircha faol vakansiyalar yo'q».
- Bo'lsa: «💼 Bo'sh ish o'rinlari» + har biri uchun ⬜ tugma (`vac:<id>`).
  - ⬜ vakansiya tanlansa → to'liq tavsif (lavozim, filial, oylik, ish vaqti,
    talablar, mas'uliyat, sharoit) + ⬜ **📝 Ariza topshirish** (`apply:<id>`) va
    ⬜ **⬅️ Orqaga** (`vac_back`).
  - ⬜ Ariza topshirish → anketa o'sha vakansiya uchun boshlanadi (filial+lavozim
    oldindan to'ldirilgan).
- *(HR/Admin bu tugmani bossa — boshqarish ro'yxati ochiladi, 3-bo'limga qarang.)*

### 1.2. 🔘 📝 Ishga ariza topshirish — ANKETA (23 savol)
«📝 Ishga ariza topshirish» kirish matni chiqadi, so'ng savollar **ketma-ket**
beriladi. Har qadamda 🔘 **❌ Bekor qilish** bor. Har javob tekshiriladi
(noto'g'ri bo'lsa qайta so'raydi). Bosqichlar:

1. 👤 Ism-sharif (≥3 harf) 2. 📅 Tug'ilgan sana (kun.oy.yil, 1940..joriy yil)
3. 🚻 Jins (🔘 Erkak/Ayol) 4. 🌆 Shahar/viloyat (tugmalar) 5. 📍 Tuman (tugmalar)
6. 🏠 Aniq manzil 7. 🏢 Filial (tugmalar — ro'yxatdagi filialga mos kelishi shart)
8. 💼 Lavozim (tugmalar) 9. 🧩 Lavozimga oid savol (farmatsevtga — ma'lumot/
sertifikat; rahbarga — jamoa hajmi; direktorga — tajriba) 10. 🕒 Smena
11. 🎓 Ma'lumot 12. 💼 Umumiy tajriba 13. 🏢 Oldingi ish yili 14. ⚖️ Sudlanganlik
15. 👨‍👩‍👧 Oilaviy holat + 👶 Farzand 16. 💰 Oldingi maosh 17. 💻 Kompyuter
savodxonligi (✅ Ha / 🟠 O'rtacha / ❌ Yo'q) 18. 🌍 Tillar 19. 📅 Ishlash niyati
20. ✍️ Sabab 21. 📱 Telefon (faqat `+998XXXXXXXXX`, kontakt ham bo'ladi)
22. 📸 **Rasm — oxirgi 10 kunda tushgan (majburiy)** 23. 📎 Rezyume (🔘 O'tkazib
yuborish bilan ixtiyoriy).

**Yakun** — «Ma'lumotlar to'plandi» + to'liq xulosa (rasm bilan) va inline:
⬜ **✅ Tasdiqlash** (`app_confirm`) · ⬜ **✏️ Tahrirlash** (`app_edit`) ·
⬜ **❌ Bekor qilish** (`app_cancel`).
- ⬜ Tahrirlash → maydonlar ro'yxati (⬜ har biri `ef:<field>`, ⬜ 📸 Rasm, ⬜ ⬅️
  Orqaga). Maydon tanlab yangi qiymat kiritiladi, xulosaga qaytadi.
- ⬜ Tasdiqlash → **majburiy maydonlar tekshiriladi**; biror savol javobsiz bo'lsa
  ariza YUBORILMAYDI, «⚠️ Ariza yuborilmadi» + to'ldirilmagan maydonlar tugmalari.
  Hammasi to'liq bo'lsa: ariza saqlanadi, «✅ Arizangiz qabul qilindi! Ariza raqami
  #N» chiqadi, menyu yangilanadi.
  - Ariza **barcha HR va adminlarga** kartochka (rasm+ma'lumot+tugmalar) bo'lib
    boradi; forma yo'q bo'lsa sarlavhada «👕 Forma kerak!». Vakansiyasiz ariza
    ochiq vakansiyalarга moslik bo'yicha tekshirilib, HR ga **avtomatik tavsiya**
    yuboriladi. Nomzodlar kanali ulangan bo'lsa — o'sha kanalga ham joylanadi.

### 1.3. 🔘 📄 Mening arizalarim
- Arizalar ro'yxati (⬜ `myapp:<id>`). Tanlansa — ariza kartochkasi (rasm+
  ma'lumot) va rezyume ko'rsatiladi.

### 1.4. Suhbatga javob (nomzodga keladi)
HR suhbat belgilaganda nomzodga xabar + inline: ⬜ **✅ Tasdiqlash** (`iok:`) ·
⬜ **🔄 Boshqa vaqt taklif qilish** (`ire:`).
- ⬜ Tasdiqlash → «✅ Siz suhbatni tasdiqladingiz», suhbat kanali yangilanadi,
  suhbatni yaratgan HR ga xabar boradi.
- ⬜ Boshqa vaqt → nomzoddan qulay vaqt so'raladi, matni HR ga yetkaziladi.

### 1.5. Oylik kelishuvi (nomzodga keladi)
HR oylik taklif qilsa: xabar + ⬜ **✅ Tasdiqlash** (`candsal_ok:`) · ⬜ **✏️
Boshqa summa** (`candsal_other:`).
- Tasdiqlasa → oylik kelishildi, profil bo'lsa darhol yoziladi, HR ga xabar.
- Boshqa summa → nomzod o'z summasini yozadi, HR ga «💰 Nomzoddan taklif» +
  ⬜ **✅ Tasdiqlash** / ⬜ **✏️ Boshqa summa** boradi (aylanma savdo).

---

## 2. «🏢 Gulnora Farm hodimi» — o'zini ro'yxatga olish (`staffreg.py`)

Mavjud xodim o'zini ro'yxatga oladi. Kirish matni + savollar ketma-ket
(har qadamda 🔘 ❌ Bekor qilish):

1. 👤 Ism-familiya 2. 📅 Tug'ilgan sana 3. 📱 Telefon (`+998…`) 3b. 👪 Ota/ona
telefoni 4. 💼 Rol/yo'nalish (tugmalar) 5. 📍 Manzil 6. 🏢 Filial (tugmalar)
7. 🕒 Smena (🔘 Kunduzgi/Kechki/Qo'sh) 8. 🕘 Ish vaqti (smenaga mos tugmalar yoki
«Boshqa vaqt» → qo'lda) 9. 💰 Oylik 10. 🛌 Dam olish kuni 11. 👕 Forma bormi
12. 🎓 Ma'lumot/diplom 13. ⏳ Necha yildan beri (tugmalar) 14. 🧩 (rahbar/direktor
uchun) qo'shimcha savol 15. 📸 Rasm (oxirgi 10 kun) 16. 🪪 **Pasport/ID — oldi va
orqa** (rasm/fayl, ikkalasi yoki 🔘 ✅ Tayyor; **maxfiy — kanalga chiqmaydi**)
17. 🎓 Diplom (rasm/fayl yoki 🔘 ⏭ Diplomsiz davom etish; maxfiy).

**Yakun** — rasm + to'liq xulosa + ⬜ **✅ Tasdiqlash** (`sreg_confirm`) / ⬜ **❌
Bekor qilish** (`sreg_cancel`).
- Tasdiqlasa → so'rov saqlanadi, «✅ So'rovingiz HR bo'limiga yuborildi! #N»,
  barcha HR/adminlarga rasm bilan kartochka + ⬜ **✅ Tasdiqlash** / ⬜ **❌ Rad
  etish** boradi (birortasi ko'rib chiqsa qolganlarникi o'chadi).
- **Yangilash rejimida** (admin so'ragan) — HR tasdig'isiz darhol profilga yoziladi
  (rol o'zgarmaydi; lavozim o'zgarsa HR ga xabar).

**HR/Admin tomoni** (🔘 «🧾 Xodim so'rovlari» yoki kartochkadan):
- ⬜ **✅ Tasdiqlash** → xodimga rol beriladi, profil yaratiladi, «hired» hodisasi
  yoziladi, xodimga «🎉 Tabriklaymiz!» xabari, maxfiy kanalga joylanadi.
- ⬜ **❌ Rad etish** → HR sabab yozadi, so'rov rad etiladi, xodimga sabab bilan
  xabar boradi.

---

## 3. XODIM (umumiy) menyusi

Rol berilgan har bir xodimda: 🔘 **👤 Mening profilim**, 🔘 **🔄 Dam olish kunini
almashtirish**, 🔘 **📩 HR ga murojaat**, 🔘 **💼 Vakansiyalar**, 🔘 **🌐 Til**,
va roliga mos panel tugmasi.

### 3.1. 🔘 👤 Mening profilim (`attendance.py`)
Profil topilsa — rasm bilan to'liq profil matni (ism, lavozim, filial, oylik, ish
vaqti, dam kuni, forma, ma'lumot va h.k.). Yo'q bo'lsa: «Profil topilmadi, HR
bilan bog'laning».

### 3.2. 🔘 🔄 Dam olish kunini almashtirish (`dayoff.py`)
- «Hozirgi dam kuningiz: X» + 🔘 kun tugmalari.
- 1) qaysi kunni almashtirish → 2) yangi kun → 3) ✍️ sabab.
- So'rov filial rahbari + HR/adminga boradi (⬜ **✅ Tasdiqlash** / ⬜ **❌ Rad
  etish**). Tasdiqlansa xodim profilidagi dam kuni yangilanadi va xodimga xabar.

### 3.3. 🔘 📩 HR ga murojaat (`hrrequest.py`)
Inline menyu: ⬜ **🕒 Ish soatini o'zgartirish** · ⬜ **💸 Maoshni oshirishni
so'rash** · ⬜ **🏢 Boshqa filialga ko'chirish** · ⬜ **✉️ Boshqa masalada**.

**⬜ 🕒 Ish soatini o'zgartirish** — «09:00 - 18:00» ko'rinishida vaqt yoziladi →
⬜ **✅ Tasdiqlash** / ⬜ **✏️ Tahrirlash** / ⬜ **❌ Bekor qilish**. Tasdiqlansa
HR ga so'rov boradi (⬜ **✅ Tasdiqlash** / ⬜ **❌ Rad etish**). HR tasdiqlasa
profildagi `work_hours` yangilanadi va **Verifiks/ish vaqti eslatmalari shu yangi
vaqtga moslashadi**.

**⬜ 💸 Maoshni oshirish** (`salaryraise.py`) — «Hozirgi maoshingiz: X» + ⬜ Ha/
Yo'q → yangi summa → ⬜ Tasdiqlash/Tahrirlash/Bekor. HR ga boradi; HR ⬜ **✅
Tasdiqlash** / ⬜ **💬 Taklif berish** (qarshi taklif) / ⬜ **❌ Rad etish**.
Qarshi taklif xodimga qaytadi (⬜ Tasdiqlash / ⬜ Taklif berish) — aylanma.
Kelishilgan summa profilга yoziladi.

**⬜ 🏢 Boshqa filialga ko'chirish** (`branchtransfer.py`) — ⬜ Ha/Yo'q → filial
tugmalari (hozirgisidan boshqa) → ⬜ Ha/Tahrirlash. HR ga boradi: ⬜ **✅
Tasdiqlash** / ⬜ **❌ Bekor qilish** / ⬜ **✉️ Xodimga xabar yozish** (yozishma).
Tasdiqlansa filial o'zgaradi, eski/yangi filial rahbarlariga xabar.

**⬜ ✉️ Boshqa masalada** — erkin matn HR/adminlarga «✉️ Xodimdan murojaat» bo'lib
boradi.

### 3.4. 🔘 💊 Farmatsevt panel (faqat farmatsevt)
Panel: profil + 🔘 **📊 Mening profilim**, 🔘 **💸 Jarimalarim**, 🔘 **🏠 Asosiy
menyu**.
- 💸 Jarimalarim → jarimalar ro'yxati (⬜ `myfine:<id>`), tanlansa jarima matni.

---

## 4. FILIAL RAHBARI paneli (🔘 🏢 Filial rahbari panel — `staff.py`)

Panel sarlavhasi + profil, so'ng tugmalar:

- 🔘 **➕ Xodim kerak** — HR ga vakansiya so'rovi: lavozim (tugma) → soni → 🚻
  kimlar kerak → 🕒 smena → 📈 tajriba → 📝 izoh (⏭ o'tkazish) → xulosa +
  ⬜ **✅ Tasdiqlash**/⬜ **❌ Bekor**. Tasdiqlanса barcha HR/adminга so'rov +
  ⬜ **✅ Qabul** / ⬜ **❌ Yopish** boradi.
- 🔘 **📢 Mening vakansiyalarim** — HR tasdiqlagan o'z vakansiyalari (⬜
  `mymgrvac:`). Kartochkada holat + ⬜ **✅ Yakunlash** (xodim to'ldi). Yakunlansa
  kanaldagi e'lon yangilanadi, HR ga xabar.
- 🔘 **🔧 Texnik nosozlik** — matn/rasm/video/dumaloq video + ⏰ muddat (tugma yoki
  qo'lda) → xulosa + ⬜ **✅ Ha, HR ga yuborilsin** / ⬜ **❌ Bekor**. Yuborilsa
  HR ga sarlavha + asl media, ⬜ **✅ Qabul** / ⬜ **❌ Yopish** bilan boradi.
- 🔘 **👥 Filial xodimlari** — filial xodimlari ro'yxati (⬜ `mgremp:`); tanlansa
  profil + ⬜ **🚫 Ishdan bo'shatish** (`fire:`).
- 🔘 **📊 Filial statistikasi** — xodimlar/farmatsevt/formasi yo'q soni +
  arizalar статистikasi.
- 🔘 **👕 Formasi yo'q xodimlar** — forma yo'q/noma'lumlar ro'yxati.
- 🔘 **📋 Filial arizalari** — filialга kelgan arizalar (⬜ `mgrapp:`), tanlansa
  to'liq ariza + rasm + rezyume.
- 🔘 **🛌 Dam olish so'rovlari** — filial dam olish so'rovlarini tasdiqlash/rad
  etish; shuningdek kunlik dam olish rejasini tasdiqlash (5-bo'limga qarang).
- 🔘 **📋 Mening so'rovlarim** — o'z so'rovlari ro'yxati.
- 🔘 **💬 HR ga xabar** — erkin matn HR/adminга boradi.

**🚫 Ishdan bo'shatish** (rahbar/direktor tashabbusi): profil ostidagi ⬜
`fire:` → sabab yoziladi → HR ga so'rov (⬜ **✅ Tasdiqlash** (`tacc:`) / ⬜ **❌
Rad etish** (`trej:`)). HR tasdiqlasa xodim bo'shatiladi, xabarlar tarqatiladi.

---

## 5. KUNLIK DAM OLISH REJASI (`dayoff_plan.py`)

- **17:00 (fon)** — har filial rahbariga «🛌 Ertangi dam olishni tasdiqlang» +
  dam oluvchilar ro'yxati + ⬜ **✅ Tasdiqlash** / ⬜ **✏️ Tahrirlash**.
  - ⬜ Tahrirlash → har xodim tugmasi (🛌 dam oladi ⇄ ✅ keladi almashadi) +
    ⬜ **✅ Tasdiqlash**.
  - Tasdiqlansa — reja «confirmed», tahrirlash hisobotgacha ochiq qoladi.
- **08:30 (fon)** — HR/adminга kunlik dam olish **Excel** hisoboti (summary bilan).
- HR 🔘 **🛌 Kunlik dam olish** tugmasi bilan istalgan payt bugungi hisobotni oladi.

---

## 6. DIREKTOR paneli (🔘 📈 Direktor panel — `staff.py`)

- 🔘 **📊 Direktor statistikasi** — arizalar (bugun/hafta/qabul/jami), vakansiyalar,
  forma holati, rahbar so'rovlari.
- 🔘 **👥 Xodimlar statistikasi** — rollar bo'yicha sonlar.
- 🔘 **🎓 Diplom statistikasi** — diplomi bor/yo'q, ma'lumot darajasi, filial kesimi.
- 🔘 **👥 Filial xodimlari** — qidiruv menyusi (⬜ matn / ⬜ filial / ⬜ lavozim /
  ⬜ barchasi). Natijada ⬜ `diremp:` — profil + ⬜ **🚫 Ishdan bo'shatish**.
- 🔘 **🏢 Filiallar kesimi** — har filial bo'yicha xodim/forma soni.
- 🔘 **📥 Arizalar kesimi** — status/filial/lavozim bo'yicha + ⬜ status tugmalari
  (`dirapps:`) → ariza ro'yxati → ⬜ `dirapp:` (to'liq ariza + ⬜ 📝 Izoh).
- 🔘 **🏆 Filiallar reytingi** — arizalar bo'yicha 🥇🥈🥉.
- 🔘 **📈 Taqqoslash** — hafta/oy davriy trend (📈/📉).
- 🔘 **🔧 Texnik ishlar** — texnik ishlar paneli (9-bo'limga qarang).
- 🔘 **💸 Jarima qo'llash** — bo'lim tanlash (⬜ `dfine:cat:`) → xodim (⬜
  `dfine:pick:`) → summa → sabab. Jarima moliyaга boradi, xodimга va moliyaга
  xabar, yakuniy oylikdan ayiriladi.
- 🔘 **📑 Hisobot (Excel)** — ⬜ eksport turlari (arizalar/hisobot).

---

## 7. MOLIYA BO'LIMI paneli (🔘 🧮 Moliya bo'limi — `accountant.py`)

- 🔘 **🏢 Filial tanlab ko'rish** — filial (⬜ `accbr:`) → xodimlar ro'yxati (⬜
  `accemp:`).
- 🔘 **👥 Xodimlar (oylik/jarima)** — qidiruv menyusi (matn/filial/lavozim/
  barchasi). Xodim tanlansa (⬜ `accemp:`) — profil + shu oy oyligi holati +
  tugmalar:
  - ⬜ **💰 Oylik belgilash** (`accsal:`) → summa.
  - ⬜ **⬆️ Oylik oshirish** (`accraise:`) → yangi summa.
  - ⬜ **💸 Jarima** (`accfine:`) → summa → sabab (source=finance).
  - ⬜ **💊 Dori** (`accmed:`) → qiymat → izoh (`staff_medicines`).
  - ⬜ **✅ Oylik berildi / ❌ berilmadi** (`accpaid:`).
  - ⬜ **🧾 To'lovlar tarixi** (`accpayhist:`), ⬜ **💸 Jarimalar** (`accfines:`),
    ⬜ **💊 Dorilar** (`accmeds:`).
  - ⬜ **🧮 Yakuniy oylik** (`accfinal:`) — asosiy oylik − jarima − avans − dori −
    KPI kesim = qo'lga tegadigan oylik.
  - ⬜ **📨 Hisobotni yuborish** (`accsendreport:`) — xodimга o'z hisobotini yuboradi.
- 🔘 **✂️ Oylik kesish** — kim (⬜ rahbar 10% / xodim 5%) → filial (⬜ `dedbr:`) →
  xodim (⬜ `dedemp:`) → hisob kartochkasi + ⬜ **N% kesish** (`dedgo:`). Kesilsa
  moliyaга hisob, xodimга batafsil xabar.
- 🔘 **🚫 Jarimani bekor qilish** — faol jarimali xodimlar (⬜ `fcperson:`), 🔍
  qidiruv (⬜ `fcfind`). Xodim → jarimalar → ⬜ **bekor qilish** (`fcancel:`).
  Bekor qilinса oylikdan ayirilmaydi, xodimга xabar.
- 🔘 **🛌 Dam olish so'rovlari** · 🔘 **💵 Avans oluvchilar** (HR yuborgan Excel).

---

## 8. AVANS tizimi (`advance.py`)

- **Fon (har oy, standart 13-sana)** — barcha xodimga «💵 Avans so'rovi» + ⬜
  **Ha** (`avns_yes:`) / ⬜ **Yo'q** (`avns_no:`).
  - ⬜ Ha → miqdor tugmalari (sozlangan summalar + ⬜ **✏️ Boshqa** — o'zi
    yozadi, oylikdan oshmaydi) → karta raqami → xulosa + ⬜ **✅ Tasdiqlash**
    (`avns_confirm`) / ⬜ **✏️ Tahrirlash** (`avns_edit`).
- **HR**: 🔘 **💵 Avans** → confirmed ro'yxati **Excel** + ⬜ **Buxgalterга
  yuborish** (`avns_send:`). 🔘 **🔄 Avans so'rovini boshidan yuborish** — eski
  javoblarni o'chirib qайta yuboradi.
- **HR/Admin — 🔘 💵 Avans sozlamalari**: ⬜ yoqish/o'chirish (`avset:toggle`),
  ⬜ so'rov kuni (`avset:promptday`), ⬜ to'lov kuni (`avset:payday`), ⬜
  miqdorlar (`avset:amounts` → qo'shish/tahrir/o'chirish).
- **Moliya**: 🔘 **💵 Avans oluvchilar** — HR yuborgan davr Excel'i.

---

## 9. TEXNIK XODIM va TEXNIK TOPSHIRIQLAR (`tech.py`)

**Texnik xodim paneli** (🔘 🔧 Texnik xodim panel): sanoqlar + 🔘 **🆕 Yangi
topshiriqlar**, 🔘 **🔧 Jarayondagi ishlar**, 🔘 **✅ Bajarilgan ishlar**. Har
topshiriq ⬜ ochiladi (matn + asl media). Topshiriq tugmalari holatga qarab:
⬜ **✅ Qabul qilish** (`ttaccept:`) · ⬜ **🕗 Ertaga boshlayman** (`tttom:`) ·
⬜ **▶️ Ishni boshladim** (`ttstart:`) · ⬜ **✅ Tugatdim** (`ttdone:`) · ⬜ **💬
Javob berish** (`ttreply:`) · ⬜ **🚫 Bekor qilish** (`ttcancel:` — sabab) · ⬜
**🔁 Boshqaga o'tkazish** (`ttxfer:`) · ⬜ **🙅 Bandman** / ⬜ **🙈 E'tiborsiz**
(topshiriq shu xodimдан olib tashlanadi).

**Oqim:** rahbar nosozlik yuboradi → HR **✅ Qabul** qiladi → topshiriq **barcha
texnik xodimga** tarqaladi (kim birinchi olsa — u egallaydi, qolganlaridan
o'chadi) → texnik «boshladim/tugatdim» → **rahbarga 1..5 ⭐ baholash** so'rovi
(`ttrate:`) + ixtiyoriy otziv → HR/direktor/adminга xabar va texnik ishlar
kanaliga yakuniy kartochka. **Diqqat:** baho/otziv texnik xodimга ko'rsatilmaydi.

**HR/Direktor/Admin — 🔘 🔧 Texnik ishlar**: sanoqlar + ⬜ holatlar (🆕 yangi /
🔧 bajarilmoqda / ✅ tugatilgan / 🚫 bekor) (`techadm:`) → ro'yxat → ⬜
`techadmview:` (to'liq matn + yozishmalar + asl media).

---

## 10. IT XODIM paneli (🔘 🖥 IT xodim panel — `it.py`)

Panel: sinov/o'rganuvchi sanoqlari + tugmalar:
- 🔘 **📊 Oylik hisobot (14-sana)** — kadrlar harakati (ishga kirdi/ketdi/
  ko'chirildi/sinovda/o'rganuvchi/ism o'zgardi), davr 14→14.
- 🔘 **👥 Xodimlar** — filial (⬜ `itempbr:`) → xodimlar (⬜ `itemp:`) → ⬜ **✏️
  Ism o'zgartirish** (`itren:`) va ⬜ **🔄 Boshqa filialga ko'chirish**
  (`itmove:` → `itmovebr:`). Har amalда «name_changed»/«transferred» hodisasi va
  xodimга xabar.
- 🔘 **✏️ Ism o'zgartirishlar** — joriy davrdagi ism o'zgarishlar tarixi.

---

## 11. HR PANELI (🔘 👨‍💼 HR panel — `hr.py`)

HR panel bosh menyusi bo'limlarга (submenu) yig'ilgan. Har biri 🔘 tugma; ichida
🔘 **👨‍💼 HR panel** (orqaga).

### 11.1. 🔘 📊 Dashboard
Arizalar oqimi, status, forma, filial va vakansiya kesimlari — bitta hisobot matn.

### 11.2. 🔘 📋 Arizalar / nomzodlar (submenu)
- 🔘 **📥 Arizalar** → ⬜ **🧭 Kanban** · ⬜ **🔎 Keng filter** · ⬜ status tugmalari
  (🆕/📅/✅/❌/📋 barchasi).
  - Ariza ro'yxati (⬜ `appview:`) → **ariza kartochkasi** (rasm+ma'lumot) +
    inline amallar: ⬜ **👁 Batafsil** · ⬜ **📅 Suhbatga chaqirish** (`appint:`) ·
    ⬜ **✅ Ishga qabul** (`apphire:`) · ⬜ **🧪 Sinovga qabul** (`apptrial:`) ·
    ⬜ **🎓 O'rganuvchi** (`applearn:`) · ⬜ **💰 Oylik taklif** (`appsal:`) · ⬜
    **⏳ Kutish** (`appwait:`) · ⬜ **❌ Rad etish** (`apprej:`) · ⬜ **📝 Izoh**
    (`appcom:`) · ⬜ **💬 Nomzodga xabar** (`appmsg:`) · ⬜ **⭐ Saralash** (`appfav:`).
  - **Qabul (hire/trial/learner):** filial tanlash → ishga chiqish sanasi → smena
    (⬜ ertalab/kечки/farqi yo'q) → (o'rganuvchiga) necha kun. So'ng xodim roli+
    profili yaratiladi, sinov/o'rganuvchi muddati ochiladi, rahbar+nomzod+maxfiy
    kanal xabardor qilinadi.
  - **Suhbatga chaqirish:** sana → vaqt → manzil → izoh → nomzodга taklif (⬜
    Tasdiqlash/Boshqa vaqt) + suhbat kanaliga joylanadi.
  - **Rad etish:** ⬜ **📋 Tayyor javoblar** / ⬜ **🔤 Umumiy (lotincha)** / ⬜ **🔡
    Кириллча** / ⬜ **✍️ O'zim yozaman** / ⬜ **✏️ Umumiy javobni tahrirlash**.
    Nomzodга tanlangan matn boradi, kanal statusi «❌ Rad» ga o'zgaradi.
  - **Oylik taklif:** summa → nomzodга (⬜ Tasdiqlash/Boshqa summa). Aylanma; HR ga
    ⬜ **✅ Tasdiqlash** (`hrsal_ok:`) / ⬜ **✏️ Boshqa summa** (`hrsal_other:`).
- 🔘 **⏳ Kutuvchilar** — kutuv bazasi (paginatsiyali), ⬜ `appview:`.
- 🔘 **📅 Suhbatlar** — keldi/kelmadi/belgilanmagan sanoq + ro'yxat (⬜ `intview:`);
  kartochkada ⬜ **✅ Keldi** (`intcame:`) / ⬜ **❌ Kelmadi** (`intabsent:`).
- 🔘 **⭐ Saralanganlar** — shortlist ro'yxati.
- 🔘 **💊 Farmatsevtlar** — farmatsevtlar (⬜ `phview:`) → profil + ⬜ **💰 Oylik**
  (`phsal:`) / ⬜ **💸 Jarima** (`phfine:`) / ⬜ **💸 Jarimalar** / ⬜ forma
  bor/yo'q. Jarima moliyaга boradi + xodimga xabar.
- 🔘 **❌ Rad etilgan murojaatlar** — rad etilgan arizalar + xodim so'rovlari (⬜
  `appview:` / ⬜ `rejreg:` — sabab bilan).

### 11.3. 🔘 📨 So'rovlar (submenu)
- 🔘 **📨 Rahbar so'rovlari** — yangi/oxirgi so'rovlar (⬜ `mrview:`) → matn +
  ⬜ **✅ Qabul** (`mracc:`) / ⬜ **❌ Yopish** (`mrclose:`). Vakansiya so'rovi
  qabulда — vakansiya ochilib kanalga joylanadi; texnik so'rov — texnik xodimlarга
  tarqatiladi.
- 🔘 **🧾 Xodim so'rovlari** — «Gulnora Farm hodimi» so'rovlari (2-bo'lim).
- 🔘 **💸 Maosh so'rovlari** — ⬜ `raiseview:` → ⬜ Tasdiqlash/Taklif berish/Rad.
- 🔘 **🕒 Ish vaqti so'rovlari** — ⬜ `whview:` → ⬜ Tasdiqlash/Rad.
- 🔘 **🏢 Filial o'zgartirish so'rovlari** — ⬜ `btrview:` → ⬜ Tasdiqlash/Bekor/
  Xodimga xabar.

### 11.4. 🔘 🛌 Dam olish / sinov (submenu)
- 🔘 **🛌 Dam olish so'rovlari** — yangi + tasdiqlangan; tasdiqlangan so'rovni
  ⬜ **✏️ Tahrirlash** (dam kunini o'zgartirish).
- 🔘 **🛌 Kunlik dam olish** — bugungi Excel hisobot.
- 🔘 **🧪 Sinov muddati** — faol/tugagan sinov-o'rganuvchilar (⬜ `probview:` →
  statistika matn).

### 11.5. 🔘 💵 Avans / maosh (submenu)
- 🔘 **💵 Avans**, 🔘 **💵 Avans sozlamalari**, 🔘 **🔄 Avans so'rovini boshidan
  yuborish** (8-bo'lim).

### 11.6. 🔘 📢 Xabarnomalar (submenu)
- 🔘 **📢 Xabarnoma** — kimga (⬜ Barchaga/Xodimlarga/Nomzodlarga/Rahbarlarga/
  Filial/Bitta) → xabar (matn/media) → yuboriladi (yuborildi/yuborilmadi soni).
- 🔘 **🔐 Ishonch xabari** — xuddi xabarnoma, lekin har qabul qiluvchida ⬜ **✅
  Ko'rib chiqdim** (`trustack:`) tugmasi; kim ko'rgani qayd etiladi.
- 🔘 **📊 Bildirishnoma statistika** — ishonch xabarlari ro'yxati (⬜ `trustst:`)
  → yetkazildi/ko'rdi/ko'rmadi + ismlar.
- 🔘 **📊 Excel eksport** — ⬜ arizalar / hisobot.

### 11.7. 🔘 🛠 Xodimlarni boshqarish (submenu)
- 🔘 **👥 Xodimlar** — qidiruv (matn/filial/lavozim/barcha), ⬜ `empview:` → profil
  + ⬜ jarima/forma/… (HR employee kb).
- 🔘 **🛠 Ma'lumotlarni o'zgartirish** (`empmanage.py`) — xodimni topib
  kartochkasidan ⬜ **rol** (`emmrole:`→`emmsetrole:`), ⬜ **filial** (`emmbranch:`),
  ⬜ **maqom** (`emmstatus:` — doimiy/sinov/o'rganuvchi), maydonma-maydon tahrir
  (`emmedit:`→`emmf:`; ism/telefon/rasm/pasport/diplom/ma'lumot...), ⬜ **butun
  filialга maqom**, ⬜ **xodimdan o'zi yangilashni so'rash** (`emmreqfresh:`).
- 🔘 **🔀 Filial almashtirish** — xodimni (yoki butun filialni) boshqa filialга
  o'tkazish (⬜ tasdiq → ikkala rahbarга xabar).
- 🔘 **🚫 Ishdan bo'shatish** — ⬜ **Bitta xodim** / ⬜ **Butun filial** → filial →
  xodim(lar) → ⬜ tasdiq. Bo'shatilса profil arxivга, rol nomzodга, rahbar+IT
  xabardor.
- 🔘 **🧑‍💼 Ishdan bo'shaganlar** — arxiv: ⬜ barchasi/filial/qidiruv → kartochka →
  ⬜ **♻️ Ishga qayta olish** (`dis:rehire:`) → filial → yangi maosh → profil
  tiklanadi, xodimга «🎉 Xush kelibsiz» xabari.

### 11.8. Boshqa HR tugmalari
- 🔘 **💼 Vakansiyalar (HR)** — ⬜ **➕ Vakansiya yaratish** (10 bosqichli) / ⬜
  **📋 Ro'yxat / boshqarish** (⬜ `vman:` → ⬜ Tahrirlash/Yopish/Ochish/O'chirish).
- 🔘 **🏷 Lavozimlar** (`positions.py`) — ⬜ **➕ Lavozim qo'shish** / ⬜ **🗑
  o'chirish**. Bu ro'yxat arizadagi lavozim tanlovida ko'rinadi.
- 🔘 **👕 Forma nazorati** — forma statistikasi + muammoli xodimlar ro'yxati.
- 🔘 **🎓 Diplom statistikasi** — 6-bo'limdagi kabi.
- 🔘 **🔧 Texnik ishlar** — 9-bo'lim.
- 🔘 **🔍 Qidiruv** — ⬜ ism/telefon/filial/lavozim bo'yicha ariza qidirish.

---

## 12. ADMIN PANELI (🔘 👑 Admin panel — `admin.py`)

Admin barcha panellarга (HR/Direktor/Moliya/IT/Rahbar/Texnik) kira oladi. O'ziga
xos tugmalar:

- 🔘 **📊 Statistika** — foydalanuvchilar (rollar), vakansiyalar, arizalar, filial/
  lavozim kesimi, eng faol HR.
- 🔘 **🏢 Filiallar** — ⬜ **✏️ Filial tahrirlash** (qo'shish `br_add`, tahrir
  `br_edit:`, koordinata `br_loc:`, o'chirish `br_del:`) / ⬜ **👥 Filial
  xodimlari bo'yicha ko'rish**. Filial qo'shishda GPS (📍 tugma yoki `lat,lon`).
- 🔘 **📢 Kanallar** — majburiy obuna kanallari (⬜ qo'shish `ch_add`, holat
  `ch_tog:`, o'chirish `ch_del:`). Bot kanalda admin bo'lishi shart.
- 🔘 **👥 Adminlar** — ⬜ qo'shish (TG ID orqali) / ⬜ o'chirish (bosh admin
  himoyalangan).
- 🔘 **🧑‍💼 HR xodimlari** — ⬜ HR qo'shish/o'chirish (TG ID).
- 🔘 **🎭 Rollar** — TG ID → rol tanlash (⬜ `setrole:`); xodim-rolга filial ham
  so'raladi (⬜ `rolebr:`). Rol berilса xodimга xabar.
- 🔘 **👤 Foydalanuvchilar** — ro'yxat + ⬜ **🔎 qidirish**. ⬜ `usrview:` →
  ma'lumot + ⬜ **🚫 Bloklash**/**✅ Blokdan chiqarish** (`usrblock:`/`usrunblock:`),
  ⬜ **🎭 Rol** (`usrrole:`).
- 🔘 **💼 Vakansiyalar (Admin)** — barcha vakansiyalarni boshqarish.
- 🔘 **🏷 Lavozimlar** — 11.8 kabi.
- 🔘 **📢 Xabarnoma** — 11.6 kabi.
- 🔘 **📤 Eksport** — ⬜ arizalar / foydalanuvchilar / hisobot (Excel).
- 🔘 **⚙️ Sozlamalar** — ⬜ **Majburiy obuna** (on/off), ⬜ **Xush kelibsiz matni**
  (tahrir/tiklash), ⬜ **🔒 Maxfiy kanal**, ⬜ **📣 Vakansiya kanali**, ⬜ **📇
  Nomzodlar kanali**, ⬜ **🗣 Suhbat kanali**, ⬜ **🔧 Texnik ishlar kanali**, ⬜
  **🎯 Moslik chegarasi (%)** — har biri ID/username so'raydi yoki tozalaydi.
- 🔘 **💵 Avans sozlamalari** — 8-bo'lim.
- 🔘 **🧾 Audit log** — oxirgi 30 ta harakat (kim, nima, qachon).
- 🔘 **🔄 Ma'lumotlarni yangilash** — kimga (⬜ barcha/filial/bitta) → tasdiq →
  tanlangan xodim(lar)ga «yangilang» so'rovi (ular yangilamaguncha bot boshqa
  bo'limlarga kirmaydi — `ProfileUpdateMiddleware`).
- 🔘 **🛠 Ma'lumotlarni o'zgartirish** — 11.7 kabi.
- 🔘 **🔀 Filial almashtirish** — 11.7 kabi.
- 🔘 **🚫 Ishdan bo'shatish** — 11.7 kabi.
- 🔘 **♻️ Dublikatlar** — bir xil ismli takror yozuvlar (⬜ `dupgrp:` → ⬜
  `dupdel:` → ⬜ tasdiq `dupdelok:`); bittasi o'chiriladi, qolgani saqlanadi.

---

## 13. Avtomatik fon jarayonlari va Verifiks eslatmalari

To'liq ro'yxat va Verifiks eslatmalari (ish boshi/oxiri ±5 daqiqa, kirish/chiqish
qayd etish) — `BOT_HUJJAT.md` ning **6 va 7-bo'limlarida** batafsil yozilgan.
Qisqacha: suhbat eslatmalari, sinov muddati, avans so'rovi (13-sana), IT hisoboti
(14-sana), kunlik dam olish (17:00 / 08:30), oy oxiri oylik hisoboti, ish vaqti +
**Verifiks** eslatmalari (har xodimga kuniga 6 xabar).

---

## 14. Umumiy qoidalar (barcha oqimlarга tegishli)

- **Ruxsat tekshiruvi:** har panel/tugma boshida rol tekshiriladi; mos kelmasa
  «⛔ Ruxsat yo'q» yoki alert.
- **Atomik tasdiqlash:** bir so'rov bir necha HR ga borsa, kim birinchi tasdiqласа
  (`claim_request`) qolganlaridagi xabar/tugma o'chadi («allaqachon ko'rib
  chiqilgan»).
- **Menyu tugmasi bosilса** yarim qolgan anketa bekor bo'ladi (`MenuEscapeMiddleware`).
- **Ismlar:** anketa/so'rovda kiritilgan ism panellarда ko'rinadi (Telegram nomi
  emas), `name_locked` bilan himoyalangan.
- **Maxfiylik:** pasport/ID va diplom faqat HR/rahbar/direktor panelida «🪪
  Hujjatlar» orqali ko'rinadi, hech qaysi kanalга chiqmaydi.
- **Audit:** deyarli har amal `audit_logs` ga yoziladi (admin «🧾 Audit log» da
  ko'radi).
