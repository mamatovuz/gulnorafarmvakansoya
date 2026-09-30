"""/api/v1/attendance, /schedules, /leaves."""
import re
from datetime import datetime, timedelta
from math import asin, cos, radians, sin, sqrt
from typing import Optional

from fastapi import APIRouter, Depends, Path, Query

from database import queries as q

from api import repo, telegram
from api.core import (ApiError, Page, connect, execute, fetch_all, fetch_one, fetch_val, iso,
                      like, not_found, now_sql, now_tk, ok, order_by, parse_dt)
from api.schemas import AttendanceCheck, LeaveCreate, LeaveDecision, ScheduleUpdate
from api.security import Principal, require

attendance = APIRouter(tags=["Attendance"])
schedules = APIRouter(prefix="/schedules", tags=["Schedules"])
leaves = APIRouter(prefix="/leaves", tags=["Leaves"])


# ================= ATTENDANCE =================
def _haversine(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(radians, (lat1, lon1, lat2, lon2))
    a = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2
    return int(2 * 6371000 * asin(sqrt(a)))


def parse_hours(text):
    """«08:00 - 17:00» -> (08:00, 17:00) daqiqalarda; topilmasa None."""
    m = re.search(r"(\d{1,2})[:.](\d{2})\s*[-–—]\s*(\d{1,2})[:.](\d{2})", text or "")
    if not m:
        return None
    h1, m1, h2, m2 = map(int, m.groups())
    if h1 > 24 or h2 > 24 or m1 > 59 or m2 > 59:
        return None
    return h1 * 60 + m1, (h2 % 24) * 60 + m2


async def _resolve_employee(body: AttendanceCheck):
    if body.employee_id:
        uid = body.employee_id
    elif body.telegram_id:
        uid = await fetch_val("SELECT id FROM users WHERE tg_id=?", (body.telegram_id,))
    else:
        uid = await repo.find_by_external("employee", body.external_source,
                                          body.external_employee_id)
    row = await fetch_one(
        """SELECT ep.user_id, ep.branch_id, ep.work_hours, b.work_hours AS branch_hours,
                  b.latitude, b.longitude, b.radius, COALESCE(u.blocked,0) AS blocked
             FROM employee_profiles ep JOIN users u ON u.id=ep.user_id
             LEFT JOIN branches b ON b.id=ep.branch_id
            WHERE ep.user_id=?""", (uid or 0,))
    if not row:
        raise ApiError(404, "not_found", "Xodim topilmadi.")
    if row["blocked"]:
        raise ApiError(409, "employee_blocked", "Xodim bloklangan.")
    return row


async def _geo(body: AttendanceCheck, emp, branch_id):
    if not body.location:
        return None, None, None
    br = emp
    if branch_id and branch_id != emp["branch_id"]:
        br = await fetch_one("SELECT latitude, longitude, radius FROM branches WHERE id=?",
                             (branch_id,))
        if not br:
            raise ApiError(422, "invalid_reference", "Filial topilmadi.", {"field": "branch_id"})
    lat, lon = body.location.latitude, body.location.longitude
    dist = None
    if br and br.get("latitude") is not None and br.get("longitude") is not None:
        dist = _haversine(lat, lon, br["latitude"], br["longitude"])
        radius = br.get("radius") or 150
        if body.enforce_geofence and dist > radius:
            raise ApiError(422, "outside_geofence", "Xodim filial hududidan tashqarida.",
                           {"distance_m": dist, "radius_m": radius})
    return lat, lon, dist


def _event_time(body):
    ts = parse_dt(body.timestamp) if body.timestamp else now_tk()
    if ts > now_tk() + timedelta(minutes=5):
        raise ApiError(422, "validation_error", "timestamp kelajakda bo'lishi mumkin emas.")
    return ts


@attendance.post("/attendance/check-in", status_code=201, summary="Ishga kelish (check-in)")
async def check_in(body: AttendanceCheck, p: Principal = Depends(require("attendance:write"))):
    emp = await _resolve_employee(body)
    ts = _event_time(body)
    branch_id = body.branch_id or emp["branch_id"]
    work_date = ts.strftime("%Y-%m-%d")
    existing = await fetch_one(
        "SELECT id FROM attendance WHERE user_id=? AND date=? AND time IS NOT NULL "
        "ORDER BY id DESC LIMIT 1", (emp["user_id"], work_date))
    if existing:
        return ok(await repo.load_attendance(existing["id"]),
                  meta={"duplicate": True, "message": "Bugun kelish allaqachon qayd etilgan."})
    lat, lon, dist = await _geo(body, emp, branch_id)
    late_seconds = 0
    hours = parse_hours(emp.get("work_hours") or emp.get("branch_hours"))
    if hours:
        now_sec = ts.hour * 3600 + ts.minute * 60 + ts.second
        late_seconds = max(0, now_sec - hours[0] * 60)
        if late_seconds > 12 * 3600:  # tungi smena / noto'g'ri solishtirish
            late_seconds = 0
    source = body.source or p.name.lower().replace(" ", "_")[:40]
    async with connect() as db:
        cur = await db.execute(
            """INSERT INTO attendance (user_id, branch_id, date, time, latitude, longitude,
                   distance, status, late, late_seconds, source, device, verification_method,
                   note, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?, 'present', ?,?,?,?,?,?,?,?)""",
            (emp["user_id"], branch_id, work_date, ts.strftime("%H:%M:%S"), lat, lon, dist,
             1 if late_seconds > 0 else 0, late_seconds, source, body.device,
             body.verification_method, body.note, now_sql(), now_sql()))
        aid = cur.lastrowid
        if body.external_id:
            await repo.set_external_id(db, "attendance", aid, source, body.external_id)
        await db.commit()
    return ok(await repo.load_attendance(aid), status=201)


@attendance.post("/attendance/check-out", summary="Ishdan ketish (check-out)")
async def check_out(body: AttendanceCheck, p: Principal = Depends(require("attendance:write"))):
    emp = await _resolve_employee(body)
    ts = _event_time(body)
    today = ts.strftime("%Y-%m-%d")
    yesterday = (ts - timedelta(days=1)).strftime("%Y-%m-%d")
    row = await fetch_one(
        "SELECT * FROM attendance WHERE user_id=? AND date IN (?,?) AND time IS NOT NULL "
        "ORDER BY date DESC, id DESC LIMIT 1", (emp["user_id"], today, yesterday))
    if not row or (row["date"] == yesterday and row.get("out_time")):
        raise ApiError(409, "not_checked_in", "Ochiq check-in topilmadi.")
    if row.get("out_time"):
        return ok(await repo.load_attendance(row["id"]),
                  meta={"duplicate": True, "message": "Ketish allaqachon qayd etilgan."})
    lat, lon, dist = await _geo(body, emp, row.get("branch_id") or emp["branch_id"])
    early_seconds = 0
    hours = parse_hours(emp.get("work_hours") or emp.get("branch_hours"))
    if hours and row["date"] == today:
        end = hours[1] if hours[1] > hours[0] else None  # tungi smenada hisoblanmaydi
        now_sec = ts.hour * 3600 + ts.minute * 60 + ts.second
        if end is not None:
            early_seconds = max(0, end * 60 - now_sec)
    await execute(
        """UPDATE attendance SET out_time=?, out_latitude=?, out_longitude=?, out_distance=?,
               early=?, early_seconds=?, out_device=?, out_verification_method=?,
               note=COALESCE(?, note), updated_at=? WHERE id=?""",
        (ts.strftime("%H:%M:%S"), lat, lon, dist, 1 if early_seconds > 0 else 0,
         early_seconds, body.device, body.verification_method, body.note, now_sql(), row["id"]))
    return ok(await repo.load_attendance(row["id"]))


async def _list_attendance(page, sort, where, params):
    w = " WHERE " + " AND ".join(where)
    total = await fetch_val("SELECT COUNT(*) FROM attendance a" + w, tuple(params))
    rows = await fetch_all(
        repo.ATTENDANCE_SELECT + w + " ORDER BY " +
        order_by(sort, {"id": "a.id", "date": "a.date", "check_in": "a.date, a.time",
                        "created_at": "a.created_at"}, "a.date DESC, a.time DESC")
        + " LIMIT ? OFFSET ?", (*params, page.limit, page.offset))
    return ok(await repo.serialize_attendance(rows), page.meta(total))


def _att_filters(employee_id, branch_id, date, date_from, date_to, late, early_leave, source,
                 open_only):
    where, params = ["1=1"], []
    for col, val in (("a.user_id", employee_id), ("a.branch_id", branch_id), ("a.date", date)):
        if val is not None:
            where.append(f"{col}=?")
            params.append(val)
    if date_from:
        where.append("a.date>=?")
        params.append(date_from)
    if date_to:
        where.append("a.date<=?")
        params.append(date_to)
    if late is not None:
        where.append("COALESCE(a.late,0)=?")
        params.append(1 if late else 0)
    if early_leave is not None:
        where.append("COALESCE(a.early,0)=?")
        params.append(1 if early_leave else 0)
    if source:
        where.append("COALESCE(a.source,'bot')=?")
        params.append(source)
    if open_only:
        where.append("a.out_time IS NULL")
    return where, params


DATE_RE = r"^\d{4}-\d{2}-\d{2}$"


@attendance.get("/attendance", summary="Davomat yozuvlari (filtr + sana oralig'i)")
async def list_attendance(page: Page = Depends(),
                          employee_id: Optional[int] = None,
                          branch_id: Optional[int] = None,
                          date: Optional[str] = Query(None, pattern=DATE_RE),
                          date_from: Optional[str] = Query(None, pattern=DATE_RE),
                          date_to: Optional[str] = Query(None, pattern=DATE_RE),
                          late: Optional[bool] = None,
                          early_leave: Optional[bool] = None,
                          source: Optional[str] = Query(None, max_length=40),
                          open_only: bool = Query(False, description="Faqat check-out qilinmaganlar"),
                          sort: Optional[str] = None,
                          p: Principal = Depends(require("attendance:read"))):
    where, params = _att_filters(employee_id, branch_id, date, date_from, date_to, late,
                                 early_leave, source, open_only)
    return await _list_attendance(page, sort, where, params)


@attendance.get("/attendance/{attendance_id}", summary="Bitta davomat yozuvi")
async def get_attendance(attendance_id: int = Path(..., gt=0),
                         p: Principal = Depends(require("attendance:read"))):
    data = await repo.load_attendance(attendance_id)
    if not data:
        raise not_found("Davomat", attendance_id)
    return ok(data)


@attendance.get("/employees/{employee_id}/attendance", tags=["Employees"],
                summary="Xodimning davomati")
async def employee_attendance(employee_id: int = Path(..., gt=0), page: Page = Depends(),
                              date_from: Optional[str] = Query(None, pattern=DATE_RE),
                              date_to: Optional[str] = Query(None, pattern=DATE_RE),
                              sort: Optional[str] = None,
                              p: Principal = Depends(require("attendance:read"))):
    if not await fetch_val("SELECT id FROM users WHERE id=?", (employee_id,)):
        raise not_found("Xodim", employee_id)
    where, params = _att_filters(employee_id, None, None, date_from, date_to, None, None,
                                 None, False)
    return await _list_attendance(page, sort, where, params)


# ================= SCHEDULES =================
def _schedule(r):
    hours = parse_hours(r.get("work_hours") or r.get("branch_hours"))
    return {
        "employee": {"id": r["user_id"], "full_name": r.get("full_name")},
        "branch": ({"id": r["branch_id"], "name": r.get("branch_name")}
                   if r.get("branch_id") else None),
        "work_hours": r.get("work_hours"),
        "effective_work_hours": r.get("work_hours") or r.get("branch_hours"),
        "start_time": f"{hours[0] // 60:02d}:{hours[0] % 60:02d}" if hours else None,
        "end_time": f"{hours[1] // 60:02d}:{hours[1] % 60:02d}" if hours else None,
        "rest_day": r.get("rest_day"),
        "shift": r.get("shift"),
        "updated_at": iso(r.get("updated_at")),
    }


SCHED_SELECT = """SELECT ep.user_id, ep.branch_id, ep.work_hours, ep.rest_day, ep.shift,
                         ep.updated_at, u.full_name, b.name AS branch_name,
                         b.work_hours AS branch_hours
                    FROM employee_profiles ep JOIN users u ON u.id=ep.user_id
                    LEFT JOIN branches b ON b.id=ep.branch_id"""


@schedules.get("", summary="Xodimlar ish jadvali (ish vaqti, dam olish kuni, smena)")
async def list_schedules(page: Page = Depends(), branch_id: Optional[int] = None,
                         rest_day: Optional[str] = Query(None, max_length=30),
                         search: Optional[str] = Query(None, max_length=100),
                         p: Principal = Depends(require("schedules:read"))):
    where, params = ["1=1"], []
    if branch_id:
        where.append("ep.branch_id=?")
        params.append(branch_id)
    if rest_day:
        where.append("ep.rest_day=?")
        params.append(rest_day)
    if search:
        where.append("pylower(COALESCE(u.full_name,'')) LIKE ?")
        params.append(like(search))
    w = " WHERE " + " AND ".join(where)
    total = await fetch_val(
        "SELECT COUNT(*) FROM employee_profiles ep JOIN users u ON u.id=ep.user_id" + w,
        tuple(params))
    rows = await fetch_all(SCHED_SELECT + w + " ORDER BY u.full_name LIMIT ? OFFSET ?",
                           (*params, page.limit, page.offset))
    return ok([_schedule(r) for r in rows], page.meta(total))


@schedules.get("/dayoff-plans", summary="Kunlik dam olish rejalari (filial rahbari tasdig'i)")
async def dayoff_plans(date: str = Query(..., pattern=DATE_RE), branch_id: Optional[int] = None,
                       p: Principal = Depends(require("schedules:read"))):
    sql = """SELECT dp.*, b.name AS branch_name FROM dayoff_plans dp
               LEFT JOIN branches b ON b.id=dp.branch_id WHERE dp.plan_date=?"""
    params = [date]
    if branch_id:
        sql += " AND dp.branch_id=?"
        params.append(branch_id)
    plans = await fetch_all(sql + " ORDER BY b.name", tuple(params))
    out = []
    for pl in plans:
        items = await fetch_all(
            "SELECT user_id, full_name, position, day_status FROM dayoff_plan_items "
            "WHERE plan_id=? ORDER BY full_name", (pl["id"],))
        out.append({
            "id": pl["id"], "date": pl["plan_date"], "weekday": pl["weekday"],
            "branch": {"id": pl["branch_id"], "name": pl["branch_name"]},
            "status": pl["status"], "confirmed_at": iso(pl["confirmed_at"]),
            "items": [{"employee_id": i["user_id"], "full_name": i["full_name"],
                       "position": i["position"], "day_status": i["day_status"]} for i in items],
        })
    return ok(out)


@schedules.get("/{employee_id}", summary="Bitta xodimning ish jadvali")
async def get_schedule(employee_id: int = Path(..., gt=0),
                       p: Principal = Depends(require("schedules:read"))):
    r = await fetch_one(SCHED_SELECT + " WHERE ep.user_id=?", (employee_id,))
    if not r:
        raise not_found("Xodim", employee_id)
    return ok(_schedule(r))


@schedules.patch("/{employee_id}", summary="Ish jadvalini yangilash")
@schedules.put("/{employee_id}", summary="Ish jadvalini almashtirish", include_in_schema=True)
async def update_schedule(body: ScheduleUpdate, employee_id: int = Path(..., gt=0),
                          p: Principal = Depends(require("schedules:write"))):
    data = body.model_dump(exclude_unset=True)
    if not await fetch_val("SELECT user_id FROM employee_profiles WHERE user_id=?", (employee_id,)):
        raise not_found("Xodim", employee_id)
    if data:
        sets = ", ".join(f"{k}=?" for k in data)
        await execute(f"UPDATE employee_profiles SET {sets}, updated_at=? WHERE user_id=?",
                      (*data.values(), now_sql(), employee_id))
        await q.add_log(None, p.actor, "api_ish_jadvali", f"user#{employee_id}: {', '.join(data)}")
    r = await fetch_one(SCHED_SELECT + " WHERE ep.user_id=?", (employee_id,))
    return ok(_schedule(r))


# ================= LEAVES (dam olish kunini almashtirish) =================
@leaves.get("", summary="Dam olish so'rovlari")
async def list_leaves(page: Page = Depends(), employee_id: Optional[int] = None,
                      branch_id: Optional[int] = None,
                      status: Optional[str] = Query(None, pattern="^(pending|approved|rejected)$"),
                      date_from: Optional[str] = Query(None, pattern=DATE_RE),
                      date_to: Optional[str] = Query(None, pattern=DATE_RE),
                      sort: Optional[str] = None,
                      p: Principal = Depends(require("leaves:read"))):
    where, params = ["1=1"], []
    for col, val in (("dr.user_id", employee_id), ("dr.branch_id", branch_id)):
        if val is not None:
            where.append(f"{col}=?")
            params.append(val)
    if status:
        where.append("dr.status=?")
        params.append({"pending": "new"}.get(status, status))
    if date_from:
        where.append("date(dr.created_at)>=?")
        params.append(date_from)
    if date_to:
        where.append("date(dr.created_at)<=?")
        params.append(date_to)
    w = " WHERE " + " AND ".join(where)
    total = await fetch_val("SELECT COUNT(*) FROM dayoff_requests dr" + w, tuple(params))
    rows = await fetch_all(
        repo.LEAVE_SELECT + w + " ORDER BY " +
        order_by(sort, {"id": "dr.id", "created_at": "dr.created_at"}, "dr.id DESC")
        + " LIMIT ? OFFSET ?", (*params, page.limit, page.offset))
    return ok(await repo.serialize_leaves(rows), page.meta(total))


@leaves.get("/{leave_id}", summary="Bitta so'rov")
async def get_leave(leave_id: int = Path(..., gt=0), p: Principal = Depends(require("leaves:read"))):
    data = await repo.load_leave(leave_id)
    if not data:
        raise not_found("So'rov", leave_id)
    return ok(data)


@leaves.post("", status_code=201,
             summary="So'rov yaratish — botdagidek filial rahbari/HR/adminga tasdiqlash tugmalari bilan boradi")
async def create_leave(body: LeaveCreate,
                       notify_approvers: bool = Query(True),
                       p: Principal = Depends(require("leaves:write"))):
    emp = await fetch_one(
        "SELECT ep.user_id, COALESCE(u.branch_id, ep.branch_id) AS branch_id, u.tg_id "
        "FROM employee_profiles ep JOIN users u ON u.id=ep.user_id WHERE ep.user_id=?",
        (body.employee_id,))
    if not emp:
        raise ApiError(422, "invalid_reference", "Xodim topilmadi.", {"field": "employee_id"})
    rid = await q.add_dayoff_request(emp["user_id"], emp["branch_id"], body.from_day,
                                     body.to_day, body.reason or "")
    if body.external_ids:
        async with connect() as db:
            for src, ext in body.external_ids.items():
                await repo.set_external_id(db, "leave", rid, src, ext)
            await db.commit()
    await q.add_log(None, p.actor, "dam_olish_sorov", f"#{rid} (API)")
    if notify_approvers:
        await _notify_approvers(rid, emp)
    return ok(await repo.load_leave(rid), status=201)


async def _notify_approvers(rid, emp):
    """Botdagi `dayoff_start` bilan bir xil: filial rahbari + HR + admin, tasdiqlash tugmalari."""
    import keyboards as kb
    from handlers.dayoff import _req_text
    req = await q.get_dayoff_request(rid)
    targets = set()
    if emp["branch_id"]:
        targets.update(await q.all_user_tg_ids(role="manager", branch_id=emp["branch_id"]))
    targets.update(await q.all_user_tg_ids(role="hr"))
    targets.update(await q.all_user_tg_ids(role="admin"))
    targets.discard(emp["tg_id"])
    text = "🔔 <b>Yangi dam olish so'rovi!</b>\n\n" + _req_text(req)
    for tid in targets:
        sent, mid, _ = await telegram.send_text(tid, text, reply_markup=kb.dayoff_actions_kb(rid))
        if sent and mid:
            await q.add_request_notice("dayoff", rid, tid, mid)


@leaves.patch("/{leave_id}", summary="So'rovni tasdiqlash / rad etish (atomik, bir martalik)")
async def decide_leave(body: LeaveDecision, leave_id: int = Path(..., gt=0),
                       p: Principal = Depends(require("leaves:write"))):
    req = await q.get_dayoff_request(leave_id)
    if not req:
        raise not_found("So'rov", leave_id)
    if not await q.claim_request("dayoff_requests", leave_id, body.status, None, "new"):
        raise ApiError(409, "already_processed", "So'rov allaqachon ko'rib chiqilgan.",
                       {"status": repo.LEAVE_STATUS_MAP.get(req["status"], req["status"])})
    if body.status == "approved" and req.get("to_day"):
        await q.update_rest_day(req["user_id"], req["to_day"])
    action = "dam_olish_tasdiq" if body.status == "approved" else "dam_olish_rad"
    await q.add_log(None, p.actor, action, f"#{leave_id}" + (f": {body.comment}" if body.comment else ""))
    # Botdagi HR/rahbarlardagi so'rov kartochkalarini yopamiz
    try:
        from utils import close_request_notices
        if telegram._custom_sender is None:
            await close_request_notices(telegram._get_bot(), "dayoff", leave_id)
        else:
            await q.pop_request_notices("dayoff", leave_id)
    except Exception:
        pass
    if body.notify and req.get("user_tg"):
        msg = (f"✅ Dam olish kunini almashtirish so'rovingiz tasdiqlandi.\n"
               f"Yangi dam olish kuningiz: <b>{req.get('to_day')}</b>"
               if body.status == "approved"
               else "😔 Dam olish kunini almashtirish so'rovingiz rad etildi.")
        await execute(
            "INSERT INTO api_notifications (user_id, tg_id, message, type, source, is_html, "
            "api_key_id) VALUES (?,?,?,?,?,1,?)",
            (req["user_id"], req["user_tg"], msg, "leave_decision", "system", p.key_id))
    return ok(await repo.load_leave(leave_id))
