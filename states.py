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
    word_level = State()       # 16
    excel_level = State()      # 17
    languages = State()        # 18
    work_intent = State()      # 19
    reason = State()           # 20
    phone = State()            # 21
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
    since = State()          # 10 (rahbar/direktor) qachondan beri
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
    title = State()
    staff_count = State()
    details = State()


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
    match_threshold = State()  # moslik (tavsiya) foizi


class ProbationForm(StatesGroup):
    """HR ariza qabul qilganda sinov muddatini belgilaydi."""
    branch = State()       # qaysi filialga chiqadi
    start_date = State()   # sinov qaysi kundan boshlanadi


class CandidateMessageForm(StatesGroup):
    """HR nomzodga to'g'ridan-to'g'ri xabar yozadi."""
    text = State()


class ManagerMessageForm(StatesGroup):
    """Filial rahbari HR ga xabar yozadi."""
    text = State()


class TerminationForm(StatesGroup):
    """Filial rahbari/direktor xodimni ishdan bo'shatish sababini yozadi."""
    reason = State()


class TerminationRejectForm(StatesGroup):
    """HR ishdan bo'shatish so'rovini rad etadi — sababini yozadi."""
    reason = State()
