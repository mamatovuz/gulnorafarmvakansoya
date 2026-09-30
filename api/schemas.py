"""So'rov (input) modellari — pydantic v2. Noma'lum maydonlar rad etiladi."""
import re
from datetime import date, datetime
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Role = Literal["employee", "pharmacist", "manager", "hr", "director", "accountant", "it", "tech"]
EmpStatus = Literal["regular", "trial", "learner"]
Uniform = Literal["yes", "no", "unknown"]
ActiveStatus = Literal["active", "inactive"]
Verification = Literal["gps", "face", "fingerprint", "card", "qr", "pin", "manual", "telegram", "other"]

Str120 = Field(None, max_length=120)
ExternalIds = Dict[str, str]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def _norm_birth(v):
    """Bot formati: DD.MM.YYYY. ISO (YYYY-MM-DD) ham qabul qilinadi."""
    if v in (None, ""):
        return None
    text = str(v).strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        d = date.fromisoformat(text)
        return d.strftime("%d.%m.%Y")
    if re.fullmatch(r"\d{2}\.\d{2}\.\d{4}", text):
        datetime.strptime(text, "%d.%m.%Y")
        return text
    raise ValueError("birth_date formati: YYYY-MM-DD yoki DD.MM.YYYY")


def _check_ext(v):
    if v is None:
        return v
    for k, val in v.items():
        if not re.fullmatch(r"[a-z0-9_\-]{1,40}", k or ""):
            raise ValueError("external_ids kaliti (source): kichik lotin harf/raqam, 1-40 belgi")
        if not val or len(str(val)) > 120:
            raise ValueError("external_id bo'sh bo'lmasligi va 120 belgidan oshmasligi kerak")
    return v


# ---------------- EMPLOYEE ----------------
class EmployeeFields(Strict):
    full_name: Optional[str] = Field(None, min_length=2, max_length=120)
    first_name: Optional[str] = Field(None, max_length=60, description="full_name o'rniga (familiya bilan)")
    last_name: Optional[str] = Field(None, max_length=60)
    phone: Optional[str] = Field(None, max_length=20, examples=["+998901234567"])
    birth_date: Optional[str] = Field(None, examples=["1995-04-30"])
    address: Optional[str] = Field(None, max_length=300)
    parent_phone: Optional[str] = Field(None, max_length=40)
    role: Optional[Role] = None
    position: Optional[str] = Field(None, max_length=120)
    position_id: Optional[int] = Field(None, gt=0)
    branch_id: Optional[int] = Field(None, gt=0)
    department_id: Optional[int] = Field(None, gt=0)
    manager_id: Optional[int] = Field(None, gt=0, description="Bevosita rahbar (xodim id)")
    work_hours: Optional[str] = Field(None, max_length=60, examples=["08:00 - 17:00"])
    rest_day: Optional[str] = Field(None, max_length=60, examples=["Yakshanba"])
    shift: Optional[str] = Field(None, max_length=60)
    education: Optional[str] = Field(None, max_length=120)
    experience: Optional[str] = Field(None, max_length=60)
    extra_info: Optional[str] = Field(None, max_length=1000)
    uniform_status: Optional[Uniform] = None
    employment_status: Optional[EmpStatus] = None
    monthly_salary: Optional[str] = Field(None, max_length=40,
                                          description="`employees:salary` ruxsati kerak")
    external_ids: Optional[ExternalIds] = Field(None, examples=[{"staffora": "ST-000123"}])

    @field_validator("birth_date")
    @classmethod
    def v_birth(cls, v):
        return _norm_birth(v)

    @field_validator("external_ids")
    @classmethod
    def v_ext(cls, v):
        return _check_ext(v)

    @field_validator("monthly_salary", mode="before")
    @classmethod
    def v_salary_str(cls, v):
        return None if v is None else str(v)

    @model_validator(mode="after")
    def v_compose_name(self):
        if not self.full_name and (self.first_name or self.last_name):
            # Botdagi tartib: «Familiya Ism»
            self.full_name = " ".join(x for x in (self.last_name, self.first_name) if x)
        return self


class EmployeeCreate(EmployeeFields):
    telegram_id: int = Field(..., gt=0, description="Xodimning Telegram user ID si (majburiy)")
    notify: bool = Field(True, description="Xodimga bot orqali tabrik xabari yuborilsinmi")

    @model_validator(mode="after")
    def v_need_name(self):
        if not self.full_name:
            raise ValueError("full_name (yoki first_name/last_name) majburiy")
        return self


class EmployeeReplace(EmployeeFields):
    status: Optional[Literal["active", "blocked"]] = None

    @model_validator(mode="after")
    def v_need(self):
        if not self.full_name or not self.role:
            raise ValueError("PUT uchun full_name va role majburiy")
        return self


class EmployeePatch(EmployeeFields):
    status: Optional[Literal["active", "blocked"]] = None


# ---------------- BRANCH ----------------
class BranchFields(Strict):
    name: Optional[str] = Field(None, min_length=2, max_length=120)
    code: Optional[str] = Field(None, max_length=40, pattern=r"^[A-Za-z0-9_\-]+$")
    address: Optional[str] = Field(None, max_length=300)
    phone: Optional[str] = Field(None, max_length=40)
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    radius: Optional[int] = Field(None, ge=10, le=100000, description="Geofence radiusi (metr)")
    working_hours: Optional[str] = Field(None, max_length=60, examples=["08:00 – 24:00"])
    status: Optional[ActiveStatus] = None
    external_ids: Optional[ExternalIds] = None

    @field_validator("external_ids")
    @classmethod
    def v_ext(cls, v):
        return _check_ext(v)


class BranchCreate(BranchFields):
    name: str = Field(..., min_length=2, max_length=120)


class BranchReplace(BranchCreate):
    pass


# ---------------- POSITION ----------------
class PositionFields(Strict):
    name: Optional[str] = Field(None, min_length=2, max_length=120)
    code: Optional[str] = Field(None, max_length=40, pattern=r"^[A-Za-z0-9_\-]+$")
    description: Optional[str] = Field(None, max_length=500)
    department_id: Optional[int] = Field(None, gt=0)
    status: Optional[ActiveStatus] = None
    external_ids: Optional[ExternalIds] = None

    @field_validator("external_ids")
    @classmethod
    def v_ext(cls, v):
        return _check_ext(v)


class PositionCreate(PositionFields):
    name: str = Field(..., min_length=2, max_length=120)


# ---------------- DEPARTMENT ----------------
class DepartmentFields(Strict):
    name: Optional[str] = Field(None, min_length=2, max_length=120)
    code: Optional[str] = Field(None, max_length=40, pattern=r"^[A-Za-z0-9_\-]+$")
    description: Optional[str] = Field(None, max_length=500)
    parent_id: Optional[int] = Field(None, gt=0)
    head_id: Optional[int] = Field(None, gt=0, description="Bo'lim rahbari (xodim id)")
    status: Optional[ActiveStatus] = None
    external_ids: Optional[ExternalIds] = None

    @field_validator("external_ids")
    @classmethod
    def v_ext(cls, v):
        return _check_ext(v)


class DepartmentCreate(DepartmentFields):
    name: str = Field(..., min_length=2, max_length=120)


# ---------------- SCHEDULE ----------------
class ScheduleUpdate(Strict):
    work_hours: Optional[str] = Field(None, max_length=60, examples=["08:00 - 17:00"])
    rest_day: Optional[str] = Field(None, max_length=60, examples=["Yakshanba"])
    shift: Optional[str] = Field(None, max_length=60)


# ---------------- ATTENDANCE ----------------
class Location(Strict):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)


class AttendanceCheck(Strict):
    employee_id: Optional[int] = Field(None, gt=0)
    telegram_id: Optional[int] = Field(None, gt=0)
    external_employee_id: Optional[str] = Field(None, max_length=120)
    external_source: Optional[str] = Field(None, max_length=40)
    timestamp: Optional[datetime] = Field(
        None, description="Hodisa vaqti (ISO 8601). Bo'lmasa — server vaqti.")
    branch_id: Optional[int] = Field(None, gt=0, description="Bo'lmasa — xodim filiali")
    location: Optional[Location] = None
    verification_method: Optional[Verification] = None
    device: Optional[str] = Field(None, max_length=120)
    source: Optional[str] = Field(None, max_length=40, pattern=r"^[a-z0-9_\-]+$")
    note: Optional[str] = Field(None, max_length=500)
    enforce_geofence: bool = Field(False, description="true => filial radiusidan tashqarida rad etiladi")
    external_id: Optional[str] = Field(None, max_length=120, description="Tashqi davomat yozuvi ID si")

    @model_validator(mode="after")
    def v_who(self):
        if not (self.employee_id or self.telegram_id or self.external_employee_id):
            raise ValueError("employee_id, telegram_id yoki external_employee_id kerak")
        if self.external_employee_id and not self.external_source:
            raise ValueError("external_employee_id bilan external_source ham kerak")
        return self


# ---------------- LEAVE ----------------
class LeaveCreate(Strict):
    employee_id: int = Field(..., gt=0)
    from_day: str = Field(..., max_length=30, description="Hozirgi dam olish kuni (hafta kuni)")
    to_day: str = Field(..., max_length=30, description="So'ralayotgan dam olish kuni")
    reason: Optional[str] = Field(None, max_length=1000)
    external_ids: Optional[ExternalIds] = None

    @field_validator("external_ids")
    @classmethod
    def v_ext(cls, v):
        return _check_ext(v)


class LeaveDecision(Strict):
    status: Literal["approved", "rejected"]
    comment: Optional[str] = Field(None, max_length=500)
    notify: bool = True


# ---------------- ANNOUNCEMENT / NOTIFICATION ----------------
class Recipients(Strict):
    send_to_all: bool = False
    branch_ids: Optional[List[int]] = None
    department_ids: Optional[List[int]] = None
    position_ids: Optional[List[int]] = None
    roles: Optional[List[Role]] = None
    employee_ids: Optional[List[int]] = Field(None, max_length=5000)


class AnnouncementCreate(Strict):
    title: Optional[str] = Field(None, max_length=200)
    message: str = Field(..., min_length=1, max_length=3500)
    recipients: Optional[Recipients] = None
    # Qisqa yo'l (spetsifikatsiyadagi yassi maydonlar) — recipients bilan birlashtiriladi
    send_to_all: Optional[bool] = None
    branch_id: Optional[int] = Field(None, gt=0)
    department_id: Optional[int] = Field(None, gt=0)
    position_id: Optional[int] = Field(None, gt=0)
    employee_ids: Optional[List[int]] = None
    require_ack: bool = Field(True, description="«✅ Ko'rib chiqdim» tugmasi (botdagi Ishonch xabari)")
    scheduled_at: Optional[datetime] = None
    source: Optional[str] = Field(None, max_length=40, pattern=r"^[a-z0-9_\-]+$")

    def target(self):
        r = (self.recipients or Recipients()).model_dump(exclude_none=True)
        if self.send_to_all:
            r["send_to_all"] = True
        for flat, key in (("branch_id", "branch_ids"), ("department_id", "department_ids"),
                          ("position_id", "position_ids")):
            v = getattr(self, flat)
            if v:
                r[key] = sorted(set((r.get(key) or []) + [v]))
        if self.employee_ids:
            r["employee_ids"] = sorted(set((r.get("employee_ids") or []) + self.employee_ids))
        if not r.get("send_to_all"):
            r.pop("send_to_all", None)
        return r


class NotificationCreate(Strict):
    employee_id: Optional[int] = Field(None, gt=0)
    telegram_id: Optional[int] = Field(None, gt=0)
    title: Optional[str] = Field(None, max_length=200)
    message: str = Field(..., min_length=1, max_length=3500)
    type: str = Field("info", max_length=40, pattern=r"^[a-z0-9_\-.]+$")
    source: Optional[str] = Field(None, max_length=40, pattern=r"^[a-z0-9_\-]+$")

    @model_validator(mode="after")
    def v_who(self):
        if not (self.employee_id or self.telegram_id):
            raise ValueError("employee_id yoki telegram_id kerak")
        return self


# ---------------- USERS / COMPANY ----------------
class UserPatch(Strict):
    blocked: bool


class CompanyPatch(Strict):
    name: Optional[str] = Field(None, max_length=120)
    legal_name: Optional[str] = Field(None, max_length=200)
    phone: Optional[str] = Field(None, max_length=40)
    email: Optional[str] = Field(None, max_length=120)
    website: Optional[str] = Field(None, max_length=200)
    address: Optional[str] = Field(None, max_length=300)
    tax_id: Optional[str] = Field(None, max_length=40)


# ---------------- WEBHOOKS / KEYS ----------------
class WebhookCreate(Strict):
    url: str = Field(..., max_length=500)
    events: List[str] = Field(default_factory=lambda: ["*"])
    description: Optional[str] = Field(None, max_length=200)
    include_salary: bool = False
    active: bool = True


class WebhookPatch(Strict):
    url: Optional[str] = Field(None, max_length=500)
    events: Optional[List[str]] = None
    description: Optional[str] = Field(None, max_length=200)
    include_salary: Optional[bool] = None
    active: Optional[bool] = None


class ApiKeyCreate(Strict):
    name: str = Field(..., min_length=2, max_length=60)
    scopes: List[str]
    description: Optional[str] = Field(None, max_length=200)
    expires_at: Optional[datetime] = None
    rate_limit_per_minute: Optional[int] = Field(None, ge=1, le=10000)


class ExternalIdLink(Strict):
    entity_type: Literal["employee", "branch", "department", "position", "attendance", "leave"]
    entity_id: int = Field(..., gt=0)
    source: str = Field(..., pattern=r"^[a-z0-9_\-]{1,40}$")
    external_id: str = Field(..., min_length=1, max_length=120)


class TelegramVerify(Strict):
    init_data: str = Field(..., max_length=4096, description="Telegram.WebApp.initData (xom satr)")


class SyncRequest(Strict):
    source: str = Field("staffora", pattern=r"^[a-z0-9_\-]{1,40}$")
    branches: List[dict] = Field(default_factory=list, max_length=1000)
    departments: List[dict] = Field(default_factory=list, max_length=1000)
    positions: List[dict] = Field(default_factory=list, max_length=1000)
    employees: List[dict] = Field(default_factory=list, max_length=5000)
    dry_run: bool = False
