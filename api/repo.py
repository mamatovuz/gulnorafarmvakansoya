"""Ma'lumotlarni o'qish va API formatiga keltirish (serializerlar).

Barcha resurslar botning haqiqiy jadvallaridan o'qiladi:
  employee   = users + employee_profiles (+ api_employee_meta)
  branch     = branches (+ api_branch_meta)
  position   = positions (+ api_position_meta)
  department = api_departments
  attendance = attendance
  leave      = dayoff_requests
"""
import json

from database.db import EMP_STATUS_LABELS, request_status_label

from api.core import fetch_all, fetch_one, iso

ROLE_LABELS = {
    "admin": "Administrator", "hr": "HR", "manager": "Filial rahbari",
    "employee": "Xodim", "pharmacist": "Farmatsevt", "director": "Direktor",
    "accountant": "Moliya bo'limi", "it": "IT", "tech": "Texnik xodim",
    "candidate": "Nomzod",
}
# API orqali beriladigan rollar ("admin" faqat .env SUPER_ADMINS orqali)
ASSIGNABLE_ROLES = ["employee", "pharmacist", "manager", "hr", "director",
                    "accountant", "it", "tech"]
EMP_STATUSES = ["regular", "trial", "learner"]
UNIFORM_STATUSES = ["yes", "no", "unknown"]

ENTITY_TYPES = ["employee", "branch", "department", "position", "attendance", "leave"]


# ---------------- TASHQI ID ----------------
async def external_ids_map(entity_type, ids):
    """{entity_id: {source: external_id}}"""
    ids = [int(i) for i in ids if i is not None]
    if not ids:
        return {}
    marks = ",".join("?" * len(ids))
    rows = await fetch_all(
        f"SELECT entity_id, source, external_id FROM api_external_ids "
        f"WHERE entity_type=? AND entity_id IN ({marks})",
        (entity_type, *ids),
    )
    out = {}
    for r in rows:
        out.setdefault(r["entity_id"], {})[r["source"]] = r["external_id"]
    return out


async def find_by_external(entity_type, source, external_id):
    row = await fetch_one(
        "SELECT entity_id FROM api_external_ids WHERE entity_type=? AND source=? AND external_id=?",
        (entity_type, source, str(external_id)),
    )
    return row["entity_id"] if row else None


async def set_external_id(db, entity_type, entity_id, source, external_id):
    """Ochiq `db` ulanishida (tranzaksiya ichida) bog'lash. Ziddiyat bo'lsa ApiError."""
    from api.core import ApiError
    cur = await db.execute(
        "SELECT entity_id FROM api_external_ids WHERE entity_type=? AND source=? AND external_id=?",
        (entity_type, source, str(external_id)),
    )
    row = await cur.fetchone()
    if row and int(row[0]) != int(entity_id):
        raise ApiError(409, "external_id_conflict",
                       "Bu external_id boshqa yozuvga bog'langan.",
                       {"entity_type": entity_type, "source": source,
                        "external_id": external_id, "entity_id": row[0]})
    await db.execute(
        """INSERT INTO api_external_ids (entity_type, entity_id, source, external_id)
           VALUES (?,?,?,?)
           ON CONFLICT(entity_type, entity_id, source) DO UPDATE SET
               external_id=excluded.external_id,
               updated_at=datetime('now','+5 hours')""",
        (entity_type, entity_id, source, str(external_id)),
    )


# ---------------- EMPLOYEE ----------------
EMPLOYEE_SELECT = """
SELECT ep.*, u.tg_id, u.full_name, u.username, u.phone, u.lang,
       COALESCE(u.blocked, 0) AS blocked, u.role AS user_role,
       b.name AS branch_name,
       m.department_id, d.name AS department_name,
       COALESCE(m.manager_user_id, (
           SELECT u2.id FROM users u2
            LEFT JOIN employee_profiles ep2 ON ep2.user_id=u2.id
            WHERE u2.role='manager' AND u2.id != ep.user_id
              AND (u2.branch_id=ep.branch_id OR ep2.branch_id=ep.branch_id)
            ORDER BY u2.id LIMIT 1)) AS manager_id,
       (SELECT MIN(p.id) FROM positions p WHERE p.name=ep.position) AS position_id
  FROM employee_profiles ep
  JOIN users u ON u.id=ep.user_id
  LEFT JOIN branches b ON b.id=ep.branch_id
  LEFT JOIN api_employee_meta m ON m.user_id=ep.user_id
  LEFT JOIN api_departments d ON d.id=m.department_id
"""


async def get_employee_row(user_id):
    return await fetch_one(EMPLOYEE_SELECT + " WHERE ep.user_id=?", (user_id,))


async def _names(ids):
    ids = [i for i in set(ids) if i]
    if not ids:
        return {}
    marks = ",".join("?" * len(ids))
    rows = await fetch_all(
        f"SELECT id, full_name, tg_id FROM users WHERE id IN ({marks})", tuple(ids))
    return {r["id"]: r for r in rows}


async def serialize_employees(rows, include_salary=False, include_sensitive=False):
    ext = await external_ids_map("employee", [r["user_id"] for r in rows])
    managers = await _names([r.get("manager_id") for r in rows])
    out = []
    for r in rows:
        uid = r["user_id"]
        mgr = managers.get(r.get("manager_id"))
        item = {
            "id": uid,
            "telegram_id": r.get("tg_id"),
            "telegram_username": r.get("username"),
            "external_ids": ext.get(uid, {}),
            "full_name": r.get("full_name"),
            "phone": r.get("phone"),
            "birth_date": r.get("birth_date"),
            "address": r.get("address"),
            "parent_phone": r.get("parent_phone"),
            "role": r.get("role") or r.get("user_role"),
            "role_label": ROLE_LABELS.get(r.get("role") or r.get("user_role")),
            "position": r.get("position"),
            "position_id": r.get("position_id"),
            "branch": ({"id": r["branch_id"], "name": r.get("branch_name")}
                       if r.get("branch_id") else None),
            "department": ({"id": r["department_id"], "name": r.get("department_name")}
                           if r.get("department_id") else None),
            "manager": ({"id": mgr["id"], "full_name": mgr["full_name"]} if mgr else None),
            "status": "blocked" if r.get("blocked") else "active",
            "employment_status": r.get("emp_status") or "regular",
            "employment_status_label": EMP_STATUS_LABELS.get(r.get("emp_status") or "regular"),
            "hired_at": iso(r.get("created_at")),
            "experience": r.get("since"),
            "education": r.get("education"),
            "uniform_status": r.get("uniform_status"),
            "schedule": {
                "work_hours": r.get("work_hours"),
                "rest_day": r.get("rest_day"),
                "shift": r.get("shift"),
            },
            "extra_info": r.get("extra_info"),
            "language": r.get("lang"),
            "photo": {
                "has_photo": bool(r.get("photo_file_id")),
                "url": f"/api/v1/employees/{uid}/photo" if r.get("photo_file_id") else None,
            },
            "documents": {
                "passport_front": bool(r.get("passport_front")),
                "passport_back": bool(r.get("passport_back")),
                "diploma": bool(r.get("diploma_file")),
            },
            "profile_update_required": bool(r.get("update_required")),
            "created_at": iso(r.get("created_at")),
            "updated_at": iso(r.get("updated_at")),
        }
        if include_salary:
            item["salary"] = {"monthly_salary": r.get("monthly_salary"), "currency": "UZS"}
        if include_sensitive:
            item["documents"]["telegram_file_ids"] = {
                "photo": r.get("photo_file_id"),
                "passport_front": r.get("passport_front"),
                "passport_back": r.get("passport_back"),
                "diploma": r.get("diploma_file"),
            }
        out.append(item)
    return out


async def load_employee(user_id, include_salary=False, include_sensitive=False):
    row = await get_employee_row(user_id)
    if not row:
        return None
    return (await serialize_employees([row], include_salary, include_sensitive))[0]


# ---------------- BRANCH ----------------
BRANCH_SELECT = """
SELECT b.*, bm.code, COALESCE(bm.status, 'active') AS status, bm.updated_at,
       (SELECT COUNT(*) FROM employee_profiles ep WHERE ep.branch_id=b.id) AS employee_count
  FROM branches b
  LEFT JOIN api_branch_meta bm ON bm.branch_id=b.id
"""


async def serialize_branches(rows):
    ids = [r["id"] for r in rows]
    ext = await external_ids_map("branch", ids)
    managers = {}
    if ids:
        marks = ",".join("?" * len(ids))
        mrows = await fetch_all(
            f"""SELECT DISTINCT COALESCE(ep.branch_id, u.branch_id) AS bid,
                       u.id, u.full_name, u.tg_id, u.phone
                  FROM users u LEFT JOIN employee_profiles ep ON ep.user_id=u.id
                 WHERE u.role='manager' AND COALESCE(ep.branch_id, u.branch_id) IN ({marks})
                 ORDER BY u.full_name""",
            tuple(ids),
        )
        for m in mrows:
            managers.setdefault(m["bid"], []).append(
                {"id": m["id"], "full_name": m["full_name"],
                 "telegram_id": m["tg_id"], "phone": m["phone"]})
    return [{
        "id": r["id"],
        "name": r["name"],
        "code": r.get("code"),
        "address": r.get("address"),
        "phone": r.get("phone"),
        "latitude": r.get("latitude"),
        "longitude": r.get("longitude"),
        "radius": r.get("radius"),
        "working_hours": r.get("work_hours"),
        "status": r.get("status") or "active",
        "managers": managers.get(r["id"], []),
        "employee_count": r.get("employee_count") or 0,
        "external_ids": ext.get(r["id"], {}),
        "created_at": iso(r.get("created_at")),
        "updated_at": iso(r.get("updated_at") or r.get("created_at")),
    } for r in rows]


async def load_branch(bid):
    row = await fetch_one(BRANCH_SELECT + " WHERE b.id=?", (bid,))
    return (await serialize_branches([row]))[0] if row else None


# ---------------- POSITION ----------------
POSITION_SELECT = """
SELECT p.*, pm.code, pm.description, pm.department_id, COALESCE(pm.status,'active') AS status,
       pm.updated_at,
       (SELECT COUNT(*) FROM employee_profiles ep WHERE ep.position=p.name) AS employee_count
  FROM positions p
  LEFT JOIN api_position_meta pm ON pm.position_id=p.id
"""


async def serialize_positions(rows):
    ext = await external_ids_map("position", [r["id"] for r in rows])
    return [{
        "id": r["id"],
        "name": r["name"],
        "code": r.get("code"),
        "description": r.get("description"),
        "department_id": r.get("department_id"),
        "status": r.get("status") or "active",
        "employee_count": r.get("employee_count") or 0,
        "external_ids": ext.get(r["id"], {}),
        "created_at": iso(r.get("created_at")),
        "updated_at": iso(r.get("updated_at") or r.get("created_at")),
    } for r in rows]


async def load_position(pid):
    row = await fetch_one(POSITION_SELECT + " WHERE p.id=?", (pid,))
    return (await serialize_positions([row]))[0] if row else None


# ---------------- DEPARTMENT ----------------
DEPARTMENT_SELECT = """
SELECT d.*, u.full_name AS head_name,
       (SELECT COUNT(*) FROM api_employee_meta m JOIN employee_profiles ep
          ON ep.user_id=m.user_id WHERE m.department_id=d.id) AS employee_count
  FROM api_departments d
  LEFT JOIN users u ON u.id=d.head_user_id
"""


async def serialize_departments(rows):
    ext = await external_ids_map("department", [r["id"] for r in rows])
    return [{
        "id": r["id"],
        "name": r["name"],
        "code": r.get("code"),
        "description": r.get("description"),
        "parent_id": r.get("parent_id"),
        "head": ({"id": r["head_user_id"], "full_name": r.get("head_name")}
                 if r.get("head_user_id") else None),
        "status": r.get("status") or "active",
        "employee_count": r.get("employee_count") or 0,
        "external_ids": ext.get(r["id"], {}),
        "created_at": iso(r.get("created_at")),
        "updated_at": iso(r.get("updated_at")),
    } for r in rows]


async def load_department(did):
    row = await fetch_one(DEPARTMENT_SELECT + " WHERE d.id=?", (did,))
    return (await serialize_departments([row]))[0] if row else None


# ---------------- ATTENDANCE ----------------
ATTENDANCE_SELECT = """
SELECT a.*, u.full_name, u.tg_id, b.name AS branch_name
  FROM attendance a
  LEFT JOIN users u ON u.id=a.user_id
  LEFT JOIN branches b ON b.id=a.branch_id
"""


def _dt(date, time):
    if not date or not time:
        return None
    return iso(f"{date} {str(time)[:8]}")


def _seconds_between(date, t1, t2):
    from datetime import datetime
    try:
        a = datetime.strptime(f"{date} {str(t1)[:8]}", "%Y-%m-%d %H:%M:%S")
        b = datetime.strptime(f"{date} {str(t2)[:8]}", "%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        return None
    diff = int((b - a).total_seconds())
    if diff < 0:  # tungi smena — ertasi kuni ketgan
        diff += 86400
    return diff


async def serialize_attendance(rows):
    ext = await external_ids_map("attendance", [r["id"] for r in rows])
    out = []
    for r in rows:
        worked = None
        if r.get("time") and r.get("out_time"):
            worked = _seconds_between(r["date"], r["time"], r["out_time"])
            if worked is not None:
                worked = max(0, worked - int(r.get("break_seconds") or 0))
        if r.get("out_time"):
            state = "checked_out"
        elif r.get("time"):
            state = "checked_in"
        else:
            state = r.get("status") or "absent"
        out.append({
            "id": r["id"],
            "employee": {"id": r["user_id"], "full_name": r.get("full_name"),
                         "telegram_id": r.get("tg_id")},
            "branch": ({"id": r["branch_id"], "name": r.get("branch_name")}
                       if r.get("branch_id") else None),
            "date": r.get("date"),
            "check_in": _dt(r.get("date"), r.get("time")),
            "check_out": _dt(r.get("date"), r.get("out_time")),
            "worked_seconds": worked,
            "worked_minutes": worked // 60 if worked is not None else None,
            "break_seconds": int(r.get("break_seconds") or 0),
            "late": bool(r.get("late")),
            "late_seconds": int(r.get("late_seconds") or 0),
            "early_leave": bool(r.get("early")),
            "early_leave_seconds": int(r.get("early_seconds") or 0),
            "status": r.get("status") or "present",
            "state": state,
            "verification_method": r.get("verification_method"),
            "check_out_verification_method": r.get("out_verification_method"),
            "device": r.get("device"),
            "check_out_device": r.get("out_device"),
            "location": {
                "check_in": {"latitude": r.get("latitude"), "longitude": r.get("longitude"),
                             "distance_m": r.get("distance")},
                "check_out": {"latitude": r.get("out_latitude"),
                              "longitude": r.get("out_longitude"),
                              "distance_m": r.get("out_distance")},
            },
            "source": r.get("source") or "bot",
            "note": r.get("note"),
            "external_ids": ext.get(r["id"], {}),
            "created_at": iso(r.get("created_at")),
            "updated_at": iso(r.get("updated_at") or r.get("created_at")),
        })
    return out


async def load_attendance(aid):
    row = await fetch_one(ATTENDANCE_SELECT + " WHERE a.id=?", (aid,))
    return (await serialize_attendance([row]))[0] if row else None


# ---------------- LEAVE (dayoff_requests) ----------------
LEAVE_SELECT = """
SELECT dr.*, u.full_name, u.tg_id, b.name AS branch_name, h.full_name AS handler_name
  FROM dayoff_requests dr
  LEFT JOIN users u ON u.id=dr.user_id
  LEFT JOIN branches b ON b.id=dr.branch_id
  LEFT JOIN users h ON h.id=dr.handled_by
"""

LEAVE_STATUS_MAP = {"new": "pending", "approved": "approved", "rejected": "rejected"}


async def serialize_leaves(rows):
    ext = await external_ids_map("leave", [r["id"] for r in rows])
    return [{
        "id": r["id"],
        "type": "rest_day_change",
        "employee": {"id": r["user_id"], "full_name": r.get("full_name"),
                     "telegram_id": r.get("tg_id")},
        "branch": ({"id": r["branch_id"], "name": r.get("branch_name")}
                   if r.get("branch_id") else None),
        "from_day": r.get("from_day"),
        "to_day": r.get("to_day"),
        "reason": r.get("reason"),
        "status": LEAVE_STATUS_MAP.get(r.get("status"), r.get("status")),
        "status_label": request_status_label(r.get("status")),
        "handled_by": ({"id": r["handled_by"], "full_name": r.get("handler_name")}
                       if r.get("handled_by") else None),
        "external_ids": ext.get(r["id"], {}),
        "created_at": iso(r.get("created_at")),
    } for r in rows]


async def load_leave(lid):
    row = await fetch_one(LEAVE_SELECT + " WHERE dr.id=?", (lid,))
    return (await serialize_leaves([row]))[0] if row else None


# ---------------- ANNOUNCEMENT ----------------
async def load_announcement(aid):
    r = await fetch_one("SELECT * FROM api_announcements WHERE id=?", (aid,))
    if not r:
        return None
    seen = 0
    if r.get("trust_notice_id"):
        seen = (await fetch_one(
            "SELECT COUNT(*) c FROM trust_notice_reads WHERE notice_id=? AND seen=1",
            (r["trust_notice_id"],)))["c"]
    return {
        "id": r["id"],
        "title": r.get("title"),
        "message": r.get("message"),
        "target": json.loads(r.get("target") or "{}"),
        "target_label": r.get("target_label"),
        "require_ack": bool(r.get("require_ack")),
        "source": r.get("source"),
        "status": r.get("status"),
        "scheduled_at": iso(r.get("scheduled_at")),
        "stats": {"recipients": r.get("total") or 0, "sent": r.get("sent") or 0,
                  "failed": r.get("failed") or 0, "acknowledged": seen},
        "created_at": iso(r.get("created_at")),
        "sent_at": iso(r.get("sent_at")),
    }


LOADERS = {
    "employee": load_employee,
    "branch": load_branch,
    "position": load_position,
    "department": load_department,
    "attendance": load_attendance,
    "leave": load_leave,
    "announcement": load_announcement,
}
