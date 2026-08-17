"""Ko'p tillilik (i18n) — o'zbekcha va ruscha.

Foydalanish:
    from i18n import t, tf, choices, canon

    t("start.welcome", lang)              # matn
    tf("btn.apply")                       # aiogram filtri (har ikki tilni tutadi)
    choices("education", lang)            # tugma variantlari
    canon("education", message.text)      # javobni kanonik (uz) ko'rinishga qaytarish

MUHIM: foydalanuvchi tanlagan javoblar bazaga HAR DOIM o'zbekcha (kanonik)
ko'rinishda yoziladi — HR paneli, hisobotlar va statistika bir xil qiymatlar
bilan ishlashi uchun. Foydalanuvchi esa o'z tilida ko'radi.
"""
from aiogram import F

LANGS = ("uz", "ru")
DEFAULT_LANG = "uz"

LANG_NAMES = {"uz": "🇺🇿 O'zbekcha", "ru": "🇷🇺 Русский"}


# ==================== MATNLAR ====================
TEXTS = {
    # ---------- Til ----------
    "lang.ask": {
        "uz": "🌐 <b>Tilni tanlang</b>\n\nBotdan qaysi tilda foydalanmoqchisiz?",
        "ru": "🌐 <b>Выберите язык</b>\n\nНа каком языке вы хотите пользоваться ботом?",
    },
    "lang.changed": {
        "uz": "✅ Til o'zbekchaga o'zgartirildi.",
        "ru": "✅ Язык изменён на русский.",
    },
    "btn.lang": {"uz": "🌐 Til", "ru": "🌐 Язык"},

    # ---------- /start ----------
    "start.welcome": {
        "uz": (
            "🌿 <b>Assalomu alaykum!</b>\n\n"
            "Bu — Gulnora Farm botiga xush kelibsiz.\n"
            "Bu yerda siz bo'sh ish o'rniga ariza topshirishingiz yoki "
            "Gulnora Farm hodimi sifatida ro'yxatdan o'tishingiz mumkin.\n\n"
            "Quyidagi tugmalardan birini tanlang 👇"
        ),
        "ru": (
            "🌿 <b>Здравствуйте!</b>\n\n"
            "Добро пожаловать в бот Gulnora Farm.\n"
            "Здесь вы можете подать заявку на вакансию или "
            "зарегистрироваться как сотрудник Gulnora Farm.\n\n"
            "Выберите одну из кнопок ниже 👇"
        ),
    },
    "start.pending": {
        "uz": (
            "⏳ <b>Arizangiz tekshirilmoqda</b>\n\n"
            "HR jamoamiz arizangizni ko'rib chiqmoqda va tez orada siz bilan "
            "bog'lanadi.\nSabrli bo'ling! 😊"
        ),
        "ru": (
            "⏳ <b>Ваша заявка на рассмотрении</b>\n\n"
            "Наша HR-команда рассматривает вашу заявку и скоро свяжется с вами.\n"
            "Пожалуйста, подождите! 😊"
        ),
    },
    "start.blocked": {
        "uz": "⛔ Kechirasiz, siz botdan foydalana olmaysiz.",
        "ru": "⛔ Извините, вы не можете пользоваться ботом.",
    },
    "menu.main": {"uz": "🏠 Asosiy menyu", "ru": "🏠 Главное меню"},

    # ---------- Asosiy menyu tugmalari ----------
    "btn.apply": {
        "uz": "📝 Ishga ariza topshirish",
        "ru": "📝 Подать заявку на работу",
    },
    "btn.staffreg": {
        "uz": "🏢 Gulnora Farm hodimi",
        "ru": "🏢 Сотрудник Gulnora Farm",
    },
    "btn.vacancies": {"uz": "💼 Vakansiyalar", "ru": "💼 Вакансии"},
    "btn.my_apps": {"uz": "📄 Mening arizalarim", "ru": "📄 Мои заявки"},
    "btn.checkin": {"uz": "📍 Ishga keldim", "ru": "📍 Пришёл на работу"},
    "btn.checkout": {"uz": "🏁 Ishdan ketdim", "ru": "🏁 Ушёл с работы"},
    "btn.break": {"uz": "⏸ Tanaffus", "ru": "⏸ Перерыв"},
    "btn.resume": {"uz": "▶️ Ishni davom ettirish", "ru": "▶️ Продолжить работу"},
    "btn.profile": {"uz": "👤 Mening profilim", "ru": "👤 Мой профиль"},
    "btn.dayoff": {
        "uz": "🔄 Dam olish kunini almashtirish",
        "ru": "🔄 Поменять выходной день",
    },
    "btn.hr_request": {"uz": "📩 HR ga murojaat", "ru": "📩 Обращение в HR"},
    "btn.main_menu": {"uz": "🏠 Asosiy menyu", "ru": "🏠 Главное меню"},
    "btn.help": {"uz": "ℹ️ Yordam", "ru": "ℹ️ Помощь"},
    "btn.cancel": {"uz": "❌ Bekor qilish", "ru": "❌ Отмена"},
    "btn.skip": {"uz": "⏭️ O'tkazib yuborish", "ru": "⏭️ Пропустить"},

    # ---------- Umumiy ----------
    "common.cancelled": {"uz": "❌ Bekor qilindi.", "ru": "❌ Отменено."},
    "common.no_profile": {
        "uz": "Profil topilmadi. HR bilan bog'laning.",
        "ru": "Профиль не найден. Свяжитесь с HR.",
    },
    "common.pick_buttons": {
        "uz": "❗️ Iltimos, quyidagi tugmalardan birini tanlang:",
        "ru": "❗️ Пожалуйста, выберите одну из кнопок ниже:",
    },

    # ---------- ARIZA ANKETASI ----------
    "apply.intro": {
        "uz": (
            "📝 <b>Ishga ariza topshirish</b>\n\n"
            "Assalomu alaykum! Ishga ariza topshirish uchun quyidagi savollarga "
            "ketma-ket javob bering.\n"
            "Istalgan payt «❌ Bekor qilish» tugmasi bilan to'xtatishingiz mumkin.\n\n"
            "<b>1-savol</b>\n👤 Ism-sharifingizni kiriting.\n"
            "Misol: <i>Ravshanova Robiya</i>"
        ),
        "ru": (
            "📝 <b>Подача заявки на работу</b>\n\n"
            "Здравствуйте! Чтобы подать заявку, ответьте по порядку на следующие "
            "вопросы.\n"
            "В любой момент можно остановиться кнопкой «❌ Отмена».\n\n"
            "<b>Вопрос 1</b>\n👤 Введите ваши фамилию и имя.\n"
            "Пример: <i>Равшанова Робия</i>"
        ),
    },
    "apply.q_num": {"uz": "<b>{n}-savol</b>", "ru": "<b>Вопрос {n}</b>"},
    "apply.birth": {
        "uz": "📅 Tug'ilgan sanangizni kiriting.\nFormat: <b>kun.oy.yil</b>\n"
              "Misol: <i>29.08.2009</i>",
        "ru": "📅 Введите дату рождения.\nФормат: <b>день.месяц.год</b>\n"
              "Пример: <i>29.08.2009</i>",
    },
    "apply.birth_bad": {
        "uz": "❗️ Sana noto'g'ri. Iltimos <b>kun.oy.yil</b> ko'rinishida kiriting.\n"
              "Misol: <i>29.08.2009</i>",
        "ru": "❗️ Неверная дата. Введите в формате <b>день.месяц.год</b>.\n"
              "Пример: <i>29.08.2009</i>",
    },
    "apply.gender": {"uz": "🚻 Jinsingizni tanlang.", "ru": "🚻 Выберите ваш пол."},
    "apply.gender_bad": {
        "uz": "❗️ Jinsni <b>tugmalardan</b> tanlang — bu savol majburiy.",
        "ru": "❗️ Выберите пол <b>кнопками</b> — этот вопрос обязателен.",
    },
    "apply.city": {
        "uz": "🌆 Qaysi shahar/viloyatda yashaysiz?",
        "ru": "🌆 В каком городе/области вы живёте?",
    },
    "apply.city_bad": {
        "uz": "❗️ Shahar/viloyatni <b>ro'yxatdan tanlang</b> — bu savol majburiy.",
        "ru": "❗️ Выберите город/область <b>из списка</b> — вопрос обязателен.",
    },
    "apply.district": {"uz": "📍 Tumaningizni tanlang.", "ru": "📍 Выберите ваш район."},
    "apply.district_bad": {
        "uz": "❗️ Tumanni <b>ro'yxatdan tanlang</b> yoki to'liq yozing — "
              "bu savol majburiy.",
        "ru": "❗️ Выберите район <b>из списка</b> или напишите полностью — "
              "вопрос обязателен.",
    },
    "apply.address": {
        "uz": "🏠 Aniq manzilingizni yuboring.\nMisol: <i>Xursandlik MFY, 37-uy</i>",
        "ru": "🏠 Укажите точный адрес.\nПример: <i>махалля Хурсандлик, дом 37</i>",
    },
    "apply.address_bad": {
        "uz": "❗️ Manzilni <b>to'liqroq</b> yozing (kamida 5 ta belgi) — "
              "bu savol majburiy.",
        "ru": "❗️ Напишите адрес <b>подробнее</b> (минимум 5 символов) — "
              "вопрос обязателен.",
    },
    "apply.branch": {
        "uz": "🏢 Ishlamoqchi bo'lgan filialni tanlang.",
        "ru": "🏢 Выберите филиал, в котором хотите работать.",
    },
    "apply.branch_write": {
        "uz": "🏢 Ishlamoqchi bo'lgan filial nomini yozing:",
        "ru": "🏢 Напишите название филиала, в котором хотите работать:",
    },
    "apply.branch_bad": {
        "uz": "❗️ Bunday filial topilmadi. Iltimos, <b>quyidagi tugmalardan</b> "
              "birini tanlang — filial majburiy.",
        "ru": "❗️ Такой филиал не найден. Выберите <b>одну из кнопок ниже</b> — "
              "филиал обязателен.",
    },
    "apply.position": {
        "uz": "💼 Qaysi lavozim bo'yicha ishga kirmoqchisiz?",
        "ru": "💼 На какую должность вы хотите устроиться?",
    },
    "apply.shift": {
        "uz": "🕒 Qaysi smenada ishlay olasiz?",
        "ru": "🕒 В какую смену вы можете работать?",
    },
    "apply.education": {
        "uz": "🎓 Ma'lumot darajangizni tanlang.",
        "ru": "🎓 Выберите ваш уровень образования.",
    },
    "apply.exp": {
        "uz": "💼 Umumiy ish tajribangiz qancha?",
        "ru": "💼 Каков ваш общий опыт работы?",
    },
    "apply.prev_years": {
        "uz": "🏢 Oldingi ish joyingizda qancha ishlagansiz?",
        "ru": "🏢 Сколько вы проработали на прошлом месте работы?",
    },
    "apply.criminal": {"uz": "⚖️ Sudlanganmisiz?", "ru": "⚖️ Есть ли судимость?"},
    "apply.marital": {
        "uz": "👨‍👩‍👧 Oilaviy holatingizni tanlang.",
        "ru": "👨‍👩‍👧 Выберите ваше семейное положение.",
    },
    "apply.children": {"uz": "👶 Farzandingiz bormi?", "ru": "👶 Есть ли у вас дети?"},
    "apply.prev_salary": {
        "uz": "💰 Oxirgi ish joyingizdagi maoshingiz qancha edi?",
        "ru": "💰 Какая была зарплата на последнем месте работы?",
    },
    "apply.expected_salary": {
        "uz": "💵 Qancha maoshga ishlashni xohlaysiz?",
        "ru": "💵 На какую зарплату вы рассчитываете?",
    },
    "apply.computer": {
        "uz": "💻 Kompyuter savodxonligingiz bormi?",
        "ru": "💻 Владеете ли вы компьютером?",
    },
    "apply.languages": {
        "uz": "🌍 Qaysi tillarni bilasiz?\nMisol: <i>O'zbek — a'lo, rus — o'rtacha</i>",
        "ru": "🌍 Какими языками владеете?\nПример: <i>Узбекский — отлично, "
              "русский — средне</i>",
    },
    "apply.work_intent": {
        "uz": "📅 «Gulnora Farm»da qancha muddat ishlash niyatingiz bor?",
        "ru": "📅 Как долго вы планируете работать в «Gulnora Farm»?",
    },
    "apply.reason": {
        "uz": "✍️ Nima uchun aynan Gulnora Farmda ishlashni xohlaysiz?",
        "ru": "✍️ Почему вы хотите работать именно в Gulnora Farm?",
    },
    "apply.phone": {
        "uz": "📱 Telefon raqamingizni yozing.\n"
              "Faqat <b>bitta</b> raqam, <b>+998</b> bilan va orada bo'sh joysiz.\n"
              "Misol: <code>+998932303410</code>",
        "ru": "📱 Напишите ваш номер телефона.\n"
              "Только <b>один</b> номер, с <b>+998</b> и без пробелов.\n"
              "Пример: <code>+998932303410</code>",
    },
    "apply.phone_bad": {
        "uz": "❗️ Telefon raqam noto'g'ri. Faqat bitta raqam, +998 bilan, "
              "bo'sh joysiz.\nMisol: <code>+998932303410</code>",
        "ru": "❗️ Неверный номер. Только один номер, с +998, без пробелов.\n"
              "Пример: <code>+998932303410</code>",
    },
    "apply.photo": {
        "uz": "📸 Iltimos, <b>oxirgi 10 kun ichida tushgan</b> shaxsiy rasmingizni "
              "yuboring.\n\n<i>Rasm aniq va yaqinda olingan bo'lishi shart. "
              "Bu majburiy bosqich.</i>",
        "ru": "📸 Пришлите ваше личное фото, <b>сделанное за последние 10 дней</b>.\n\n"
              "<i>Фото должно быть чётким и свежим. Это обязательный шаг.</i>",
    },
    "apply.photo_bad": {
        "uz": "❗️ Iltimos, <b>rasm (foto)</b> yuboring — oxirgi 10 kun ichida "
              "tushgan shaxsiy rasmingiz. Faqat rasm qabul qilinadi.",
        "ru": "❗️ Пришлите именно <b>фото</b> — ваш личный снимок за последние "
              "10 дней. Принимается только фото.",
    },
    "apply.resume": {
        "uz": "📄 Rezyume (CV) yoki diplom rasmini yubormoqchimisiz?\n"
              "Faylni yuboring yoki «⏭️ O'tkazib yuborish» tugmasini bosing.",
        "ru": "📄 Хотите отправить резюме (CV) или фото диплома?\n"
              "Отправьте файл или нажмите «⏭️ Пропустить».",
    },
    "apply.collected": {
        "uz": "✅ Ma'lumotlar to'plandi.",
        "ru": "✅ Данные собраны.",
    },
    "apply.cancelled": {
        "uz": "❌ Ariza bekor qilindi.",
        "ru": "❌ Заявка отменена.",
    },
    "apply.sent": {
        "uz": "✅ <b>Arizangiz muvaffaqiyatli qabul qilindi!</b>",
        "ru": "✅ <b>Ваша заявка успешно принята!</b>",
    },
    "apply.missing": {
        "uz": "⚠️ <b>Ariza yuborilmadi</b>\n\nQuyidagi savollarga javob berilmagan:",
        "ru": "⚠️ <b>Заявка не отправлена</b>\n\nНе отвечено на следующие вопросы:",
    },
    "apply.missing_hint": {
        "uz": "\n\nUlarni to'ldirish uchun tugmani bosing 👇",
        "ru": "\n\nНажмите кнопку, чтобы заполнить 👇",
    },
    "apply.expired": {
        "uz": "⏳ Sessiya tugagan. Iltimos, «📝 Ishga ariza topshirish» orqali "
              "qaytadan boshlang.",
        "ru": "⏳ Сессия истекла. Начните заново через «📝 Подать заявку на работу».",
    },

    # ---------- XODIM RO'YXATI ----------
    "sreg.intro": {
        "uz": "🏢 <b>Gulnora Farm hodimi ro'yxati</b>\n\n"
              "Quyidagi savollarga javob bering — so'rovingiz HR bo'limiga boradi.\n\n"
              "<b>1-savol</b>\n👤 Ism-familiyangizni yozing.",
        "ru": "🏢 <b>Регистрация сотрудника Gulnora Farm</b>\n\n"
              "Ответьте на вопросы — ваш запрос будет отправлен в отдел HR.\n\n"
              "<b>Вопрос 1</b>\n👤 Напишите вашу фамилию и имя.",
    },
    "sreg.birth": {
        "uz": "📅 Tug'ilgan sanangizni kiriting.\nFormat: <b>kun.oy.yil</b>\n"
              "Misol: <i>29.08.1995</i>",
        "ru": "📅 Введите дату рождения.\nФормат: <b>день.месяц.год</b>\n"
              "Пример: <i>29.08.1995</i>",
    },
    "sreg.phone": {
        "uz": "📱 Telefon raqamingizni <b>qo'lda yozing</b>.\n"
              "Faqat <b>bitta</b> raqam, <b>+998</b> bilan va orada bo'sh joysiz.\n"
              "Misol: <code>+998932303410</code>",
        "ru": "📱 <b>Напишите вручную</b> ваш номер телефона.\n"
              "Только <b>один</b> номер, с <b>+998</b> и без пробелов.\n"
              "Пример: <code>+998932303410</code>",
    },
    "sreg.role": {
        "uz": "💼 Qaysi lavozimda ishlaysiz? Tanlang:",
        "ru": "💼 В каком направлении вы работаете? Выберите:",
    },
    "sreg.address": {
        "uz": "🏠 Yashash manzilingizni yozing.\n"
              "Misol: <i>Chilonzor tumani, 12-kvartal</i>",
        "ru": "🏠 Напишите ваш адрес проживания.\n"
              "Пример: <i>Чиланзарский район, 12-квартал</i>",
    },
    "sreg.branch": {
        "uz": "🏢 Qaysi filialda ishlaysiz? Tanlang:",
        "ru": "🏢 В каком филиале вы работаете? Выберите:",
    },
    "sreg.branch_write": {
        "uz": "🏢 Qaysi filialda ishlaysiz? Filial nomini yozing:",
        "ru": "🏢 В каком филиале вы работаете? Напишите название филиала:",
    },
    "sreg.shift": {
        "uz": "🔀 Qaysi smenada ishlaysiz? Tanlang:",
        "ru": "🔀 В какую смену вы работаете? Выберите:",
    },
    "sreg.work_hours": {
        "uz": "🕒 Ish vaqtingiz nechidan nechigacha? Tayyor variantni tanlang "
              "yoki o'zingiz yozing (masalan <i>09:00 - 18:00</i>):",
        "ru": "🕒 Ваш рабочий график? Выберите готовый вариант или напишите сами "
              "(например <i>09:00 - 18:00</i>):",
    },
    "sreg.salary": {
        "uz": "💰 Oyligingiz qancha?\nMisol: <i>4 000 000 so'm</i>",
        "ru": "💰 Какая у вас зарплата?\nПример: <i>4 000 000 сум</i>",
    },
    "sreg.rest_day": {
        "uz": "🛌 Haftaning qaysi kuni dam olasiz? Tanlang:",
        "ru": "🛌 В какой день недели у вас выходной? Выберите:",
    },
    "sreg.uniform": {
        "uz": "👕 Ish formangiz bormi?",
        "ru": "👕 Есть ли у вас рабочая форма?",
    },
    "sreg.education": {
        "uz": "🎓 Ma'lumotingiz qanday? Tanlang:",
        "ru": "🎓 Какое у вас образование? Выберите:",
    },
    "sreg.since": {
        "uz": "⏳ Necha yildan beri Gulnora Farmda ishlaysiz?",
        "ru": "⏳ Сколько лет вы работаете в Gulnora Farm?",
    },
    "sreg.photo": {
        "uz": "📸 <b>Oxirgi savol</b>\nOxirgi 10 kun ichida olingan rasmingizni "
              "yuboring (shaxsingiz aniq ko'rinadigan surat).",
        "ru": "📸 <b>Последний вопрос</b>\nПришлите ваше фото за последние 10 дней "
              "(чтобы лицо было хорошо видно).",
    },
    "sreg.cancelled": {
        "uz": "❌ Ro'yxatdan o'tish bekor qilindi.",
        "ru": "❌ Регистрация отменена.",
    },
    "sreg.sent": {
        "uz": "📤 So'rovingiz HR bo'limiga yuborildi. Javobni kuting.",
        "ru": "📤 Ваш запрос отправлен в отдел HR. Ожидайте ответа.",
    },
}


# ==================== TUGMA VARIANTLARI ====================
# Har bir variant: kanonik (uz) qiymat + ruscha ko'rinishi.
# Bazaga HAR DOIM "uz" yoziladi (`canon()` orqali).
CHOICES = {
    "gender": [
        {"uz": "👨 Erkak", "ru": "👨 Мужчина"},
        {"uz": "👩 Ayol", "ru": "👩 Женщина"},
    ],
    "shift": [
        {"uz": "🌞 Ertalabgi smena", "ru": "🌞 Утренняя смена"},
        {"uz": "🌙 Kechki smena", "ru": "🌙 Вечерняя смена"},
        {"uz": "🔄 Farqi yo'q", "ru": "🔄 Без разницы"},
    ],
    "education": [
        # — O'rta maxsus ta'lim —
        {"uz": "📘 O'rta maxsus farmatsevt",
         "ru": "📘 Среднее специальное фармацевтическое"},
        {"uz": "🕓 Tugallanmagan o'rta maxsus farmatsevt",
         "ru": "🕓 Неоконченное среднее специальное фармацевтическое"},
        {"uz": "📘 O'rta maxsus — boshqa soha",
         "ru": "📘 Среднее специальное — другая сфера"},
        {"uz": "🕓 Tugallanmagan o'rta maxsus — boshqa soha",
         "ru": "🕓 Неоконченное среднее специальное — другая сфера"},
        # — Oliy ta'lim —
        {"uz": "🎓 Oliy ma'lumotli farmatsevt",
         "ru": "🎓 Высшее фармацевтическое"},
        {"uz": "🕗 Tugallanmagan oliy ma'lumotli farmatsevt",
         "ru": "🕗 Неоконченное высшее фармацевтическое"},
        {"uz": "🎓 Oliy ma'lumotli — boshqa soha",
         "ru": "🎓 Высшее — другая сфера"},
        {"uz": "🕗 Tugallanmagan oliy ma'lumotli — boshqa soha",
         "ru": "🕗 Неоконченное высшее — другая сфера"},
        # — Umumiy —
        {"uz": "📗 Umumiy o'rta ta'lim", "ru": "📗 Общее среднее образование"},
        {"uz": "❌ Diplom yo'q", "ru": "❌ Нет диплома"},
    ],
    "criminal": [
        {"uz": "✅ Yo'q", "ru": "✅ Нет"},
        {"uz": "❌ Ha", "ru": "❌ Да"},
    ],
    "marital": [
        {"uz": "💍 Turmush qurganman", "ru": "💍 Женат / замужем"},
        {"uz": "🙋 Turmush qurmaganman", "ru": "🙋 Не женат / не замужем"},
        {"uz": "💔 Ajrashganman", "ru": "💔 В разводе"},
    ],
    "children": [
        {"uz": "👶 Ha", "ru": "👶 Да"},
        {"uz": "🚫 Yo'q", "ru": "🚫 Нет"},
    ],
    "computer": [
        {"uz": "✅ Ha", "ru": "✅ Да"},
        {"uz": "🟠 O'rtacha", "ru": "🟠 Средне"},
        {"uz": "❌ Yo'q", "ru": "❌ Нет"},
    ],
    "experience": [
        {"uz": "🚫 Tajribam yo'q", "ru": "🚫 Нет опыта"},
        {"uz": "🟡 1 yilgacha", "ru": "🟡 До 1 года"},
        {"uz": "🟠 1-3 yil", "ru": "🟠 1-3 года"},
        {"uz": "🟢 3+ yil", "ru": "🟢 3+ лет"},
    ],
    "prev_years": [
        {"uz": "🚫 Ishlamaganman", "ru": "🚫 Не работал(а)"},
        {"uz": "🟡 1 yilgacha", "ru": "🟡 До 1 года"},
        {"uz": "🟠 1-3 yil", "ru": "🟠 1-3 года"},
        {"uz": "🟢 3+ yil", "ru": "🟢 3+ лет"},
    ],
    "work_intent": [
        {"uz": "🟡 1 yilgacha", "ru": "🟡 До 1 года"},
        {"uz": "🟠 1-3 yil", "ru": "🟠 1-3 года"},
        {"uz": "🟢 3+ yil", "ru": "🟢 3+ лет"},
        {"uz": "🔒 Uzoq muddat", "ru": "🔒 Долгосрочно"},
    ],
    "uniform": [
        {"uz": "✅ Ha, bor", "ru": "✅ Да, есть"},
        {"uz": "❌ Yo'q, kerak", "ru": "❌ Нет, нужна"},
    ],
    "since": [
        {"uz": "🟡 1 yildan kam", "ru": "🟡 Меньше 1 года"},
        {"uz": "🟠 1-3 yil", "ru": "🟠 1-3 года"},
        {"uz": "🟢 3-5 yil", "ru": "🟢 3-5 лет"},
        {"uz": "🔵 5+ yil", "ru": "🔵 5+ лет"},
    ],
    "rest_day": [
        {"uz": "Dushanba", "ru": "Понедельник"},
        {"uz": "Seshanba", "ru": "Вторник"},
        {"uz": "Chorshanba", "ru": "Среда"},
        {"uz": "Payshanba", "ru": "Четверг"},
        {"uz": "Juma", "ru": "Пятница"},
        {"uz": "Shanba", "ru": "Суббота"},
        {"uz": "Yakshanba", "ru": "Воскресенье"},
        {"uz": "🚫 Dam olish kunim yo'q", "ru": "🚫 Нет выходного дня"},
    ],
}


# ==================== YORDAMCHI FUNKSIYALAR ====================
def norm_lang(lang):
    """Noma'lum til kelsa — standart tilga qaytaradi."""
    lang = (lang or "").strip().lower()
    return lang if lang in LANGS else DEFAULT_LANG


def t(key, lang=None, **kwargs):
    """Kalit bo'yicha matn. Kalit topilmasa kalitning o'zi qaytadi."""
    entry = TEXTS.get(key)
    if not entry:
        return key
    text = entry.get(norm_lang(lang)) or entry.get(DEFAULT_LANG) or key
    return text.format(**kwargs) if kwargs else text


def variants(*keys):
    """Kalitlarning barcha tildagi variantlari — filtr uchun to'plam."""
    out = set()
    for key in keys:
        out |= {v for v in TEXTS.get(key, {}).values() if v}
    return out


def tf(*keys):
    """aiogram filtri: matn shu kalitlarning istalgan tildagi variantiga teng.

    Masalan: @router.message(tf("btn.apply"))"""
    return F.text.in_(variants(*keys))


def choices(key, lang=None):
    """Tanlov guruhining berilgan tildagi variantlari (tugmalar uchun)."""
    lang = norm_lang(lang)
    return [c.get(lang) or c["uz"] for c in CHOICES.get(key, [])]


def canon(key, text):
    """Har qanday tildagi javobni kanonik (o'zbekcha) ko'rinishga qaytaradi.

    Bazaga shu qiymat yoziladi — statistika va hisobotlar bir xil qiymat
    bilan ishlashi uchun. Ro'yxatda topilmasa matn o'zgarishsiz qaytadi."""
    value = (text or "").strip()
    for c in CHOICES.get(key, []):
        if value in (c.get("uz"), c.get("ru")):
            return c["uz"]
    return value


def all_choice_values(key):
    """Guruhning barcha tildagi qiymatlari — javobni tekshirish uchun."""
    out = set()
    for c in CHOICES.get(key, []):
        out |= {v for v in c.values() if v}
    return out
