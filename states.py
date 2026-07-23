"""FSM holatlari (Finite State Machine)."""
from aiogram.fsm.state import State, StatesGroup


class Reg(StatesGroup):
    """Nomzod ro'yxatdan o'tishi."""
    phone = State()


class Apply(StatesGroup):
    """Ishga ariza topshirish."""
    full_name = State()        # 1
    birth_date = State()       # 2 (kun.oy.yil)
    city = State()             # 3
    district = State()         # 4
    address = State()          # 5
    branch = State()           # 6
    position = State()         # 7
    position_extra = State()   # 7b
    uniform = State()          # farmatsevtlar uchun
    shift = State()            # 8
    education = State()        # 9
    exp_years = State()        # 10
    prev_years = State()       # 11
    criminal = State()         # 12
    marital = State()          # 13
    children = State()         # 13b
    prev_salary = State()      # 14
    expected_salary = State()  # 15
    computer_level = State()   # 16 kompyuter savodxonligi (Word/Excel o'rniga)
    languages = State()        # 18
    work_intent = State()      # 19
    reason = State()           # 20
    phone = State()            # 21
    photo = State()            # 21b oxirgi 10 kunda tushgan rasm (majburiy)
    resume = State()           # 22
    confirm = State()          # yakuniy tasdiqlash
    edit_field = State()       # bitta maydonni tahrirlash


class VacancyForm(StatesGroup):
    """HR vakansiya yaratish/tahrirlash."""
    title = State()
    branch = State()
    job_type = State()
    shift = State()
    salary = State()
    work_time = State()
    requirements = State()
    responsibilities = State()
    conditions = State()
    edit_value = State()


class InterviewForm(StatesGroup):
    """Suhbatga chaqirish."""
    date = State()
    time = State()
    location = State()
    comment = State()


class CommentForm(StatesGroup):
    text = State()


class RejectForm(StatesGroup):
    reason = State()


class RescheduleForm(StatesGroup):
    text = State()


class Broadcast(StatesGroup):
    """Xabarnoma yuborish."""
    target = State()
    content = State()


class SearchForm(StatesGroup):
    query = State()


class ApplicationFilterForm(StatesGroup):
    """HR arizalarni kengaytirilgan filter bilan izlaydi."""
    query = State()


class BranchForm(StatesGroup):
    name = State()
    address = State()
    location = State()      # filial GPS koordinatasi (qo'shishda)
    radius = State()        # ruxsat etilgan masofa (metr)
    edit_name = State()
    edit_address = State()
    set_location = State()  # mavjud filialga koordinata biriktirish


class StaffReg(StatesGroup):
    """Gulnora Farm mavjud xodimi o'zini ro'yxatdan o'tkazadi."""
    full_name = State()      # 1  Ism familiya
    birth_date = State()     # 2  Tug'ilgan sana kun.oy.yil
    phone = State()          # 3  Telefon raqam (qo'lda yoziladi)
    role = State()           # 4  Yo'nalish (rol)
    address = State()        # 4  Manzil
    branch = State()         # 5  Filial (admin ro'yxatidan)
    shift = State()          # 6  Smena (kunduzgi/kechki/qo'sh)
    work_hours = State()     # 7  Ish vaqti (dan-gacha)
    salary = State()         # 7  Oylik
    rest_day = State()       # 8  Dam olish kuni
    uniform = State()        # 9  Forma bormi
    education = State()      # 9b Ma'lumoti / diplomi
    since = State()          # 10 Necha yildan beri Gulnora Farmda ishlaydi
    extra = State()          # 10b rolga oid qo'shimcha savol
    photo = State()          # 11 oxirgi 10 kundagi rasm
    confirm = State()        # yakuniy tasdiqlash


class AttendanceForm(StatesGroup):
    """Ishga kelish/ketish — GPS lokatsiya kutilmoqda."""
    location = State()      # Ishga keldim
    checkout = State()      # Ishdan ketdim


class DayoffForm(StatesGroup):
    """Dam olish kunini almashtirish so'rovi."""
    from_day = State()
    to_day = State()
    reason = State()


class AccForm(StatesGroup):
    """Buxgalter: oylik/jarima kiritish."""
    salary = State()
    raise_amount = State()
    fine_amount = State()
    fine_reason = State()


class ChannelForm(StatesGroup):
    chat_id = State()
    title = State()
    url = State()


class PositionForm(StatesGroup):
    """Ishga arizadagi yo'nalishlarni boshqarish (admin/HR)."""
    name = State()


class RoleForm(StatesGroup):
    """Rol berish (admin/hr/manager/employee)."""
    tg_id = State()
    branch = State()


class ManagerVacancyForm(StatesGroup):
    """Filial rahbari HR ga xodim kerakligi haqida so'rov yuboradi."""
    position = State()      # yo'nalish (lavozim)
    staff_count = State()   # nechta xodim kerak
    gender = State()        # kimlar kerak: erkak / ayol / ikkalasi ham
    shift = State()         # smena (ertalabki/kechki)
    experience = State()    # talab qilinadigan tajriba
    details = State()       # qo'shimcha izoh (ixtiyoriy)
    confirm = State()       # yakuniy tasdiqlash


class TechIssueForm(StatesGroup):
    """Filial rahbari texnik nosozlik yuboradi."""
    title = State()
    details = State()


class SalaryForm(StatesGroup):
    """HR farmatsevt oyligini belgilaydi."""
    value = State()


class FineForm(StatesGroup):
    """HR farmatsevtga jarima yozadi."""
    amount = State()
    reason = State()


class UserManageForm(StatesGroup):
    """Admin foydalanuvchilarni qidiradi."""
    search = State()


class SettingsForm(StatesGroup):
    """Admin bot sozlamalarini o'zgartiradi."""
    welcome = State()
    secret_channel = State()   # maxfiy kanal chat_id
    vacancy_channel = State()  # vakansiyalar joylanadigan kanal chat_id
    candidate_channel = State()  # kutuvchi nomzodlar joylanadigan maxfiy kanal chat_id
    interview_channel = State()  # suhbatga chaqirilganlar joylanadigan kanal chat_id
    match_threshold = State()  # moslik (tavsiya) foizi
    avans_prompt_day = State()  # avans so'rovi yuboriladigan kun
    avans_pay_day = State()     # avans to'lov sanasi


class ProbationForm(StatesGroup):
    """HR ariza qabul qilganda sinov/o'rganuvchi muddatini belgilaydi."""
    branch = State()       # qaysi filialga chiqadi
    start_date = State()   # muddat qaysi kundan boshlanadi
    days = State()         # o'rganuvchi uchun — necha kun


class SalaryNegoForm(StatesGroup):
    """Oylik kelishuvi: HR taklif beradi, nomzod boshqa summa taklif qiladi."""
    hr_amount = State()         # HR taklif/qarshi taklif summasini yozadi
    candidate_amount = State()  # nomzod boshqa summa yozadi


class CandidateMessageForm(StatesGroup):
    """HR nomzodga to'g'ridan-to'g'ri xabar yozadi."""
    text = State()


class ManagerMessageForm(StatesGroup):
    """Filial rahbari HR ga xabar yozadi."""
    text = State()


class AdvanceForm(StatesGroup):
    """Xodim avans (oldindan to'lov) so'raydi — karta raqami kutilmoqda."""
    card = State()         # karta raqamini kiritish / tahrirlash


class TerminationForm(StatesGroup):
    """Filial rahbari/direktor xodimni ishdan bo'shatish sababini yozadi."""
    reason = State()


class ITForm(StatesGroup):
    """IT xodim: xodim ism-familiyasini o'zgartiradi."""
    rename = State()


class TerminationRejectForm(StatesGroup):
    """HR ishdan bo'shatish so'rovini rad etadi — sababini yozadi."""
    reason = State()


class SalaryRaiseForm(StatesGroup):
    """Xodim maosh oshirishni so'raydi; HR ⇄ xodim kelishuvi."""
    amount = State()         # xodim so'ramoqchi bo'lgan summani kiritadi/tahrirlaydi
    hr_amount = State()      # HR qarshi taklif summasini kiritadi/tahrirlaydi
    reject_reason = State()  # HR rad etish sababini yozadi


class StaffRegRejectForm(StatesGroup):
    """HR «Gulnora Farm hodimi» so'rovini rad etadi — sababini yozadi."""
    reason = State()


class WorkHoursForm(StatesGroup):
    """Xodim ish vaqtini o'zgartirishni so'raydi; HR tasdiqlaydi/rad etadi."""
    hours = State()          # xodim yangi ish vaqtini yozadi (dan-gacha)
    reject_reason = State()  # HR rad etish sababini yozadi


class HRMessageForm(StatesGroup):
    """Xodim «boshqa masalada» HR ga murojaat yozadi."""
    text = State()
