# Gulnora Farm HR ilova

Bu web/PWA ilova Telegram bot bilan bir xil `hrbot.db` bazasida ishlaydi.
Botni buzmaydi: bot alohida, ilova alohida ishga tushadi.

## Ishga tushirish

```powershell
cd C:\Users\i7\OneDrive\Desktop\gulnorafarm
python app.py
```

Bu kompyuterda `python` buyrug'i Windows Store stub bo'lib qolsa, to'liq Python
interpreter bilan ishga tushiring:

```powershell
& "C:\Program Files\PostgreSQL\18\pgAdmin 4\python\python.exe" app.py
```

Brauzerda ochish:

```text
http://127.0.0.1:8088
```

Agar boshqa port kerak bo'lsa:

```powershell
$env:APP_PORT="8090"
python app.py
```

## Kirish

Bot bazasida bor foydalanuvchi Telegram ID, username yoki telefon raqam bilan
kiradi. Masalan: `123456789`, `username`, yoki `+998901234567`.

## Qo'shilgan imkoniyatlar

- Mobilga mos pastki navigatsiya: Bosh sahifa, Davomat, Profil, Bildirishnoma.
- GPS davomat: ishga kelish, ketish, tanaffus, filial radiusi bo'yicha tekshiruv.
- Profilni ko'rish va asosiy ma'lumotlarni yangilash.
- Vakansiya, ariza, xodim, so'rov va davomat hisobotlari.
- HR/Admin/Rahbar uchun so'rovlarni tasdiqlash/rad etish..
- Ilova ichki bildirishnomalari va CSV eksport.
- PWA manifest va service worker: telefon ekraniga o'rnatib ishlatish mumkin.
