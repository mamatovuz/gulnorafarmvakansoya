"""Ma'lumotlar bazasi bilan ishlash uchun yordamchi funksiyalar."""
import aiosqlite
from config import DB_PATH, SUPER_ADMINS
from database.db import ROLE_CANDIDATE, ROLE_ADMIN, ROLE_MANAGER


async def _conn():
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    return db


# ---------------- FOYDALANUVCHILAR ----------------
async def get_or_create_user(tg_id, full_name=None, username=None):
    db = await _conn()
    try:
        cur = await db.execute("SELECT * FROM users WHERE tg_id=?", (tg_id,))
        row = await cur.fetchone()
        if row:
            # ma'lumotlarni yangilab qo'yamiz
            await db.execute(
                "UPDATE users SET full_name=COALESCE(?, full_name), username=? WHERE tg_id=?",
                (full_name, username, tg_id),
            )
            await db.commit()
            cur = await db.execute("SELECT * FROM users WHERE tg_id=?", (tg_id,))
            return dict(await cur.fetchone())
        role = ROLE_ADMIN if tg_id in SUPER_ADMINS else ROLE_CANDIDATE
        await db.execute(
            "INSERT INTO users (tg_id, full_name, username, role) VALUES (?,?,?,?)",
            (tg_id, full_name, username, role),
        )
        await db.commit()
        cur = await db.execute("SELECT * FROM users WHERE tg_id=?", (tg_id,))
        return dict(await cur.fetchone())
    finally:
        await db.close()


async def get_user(tg_id):
    db = await _conn()
    try:
        cur = await db.execute("SELECT * FROM users WHERE tg_id=?", (tg_id,))
        row = await cur.fetchone()
        return dict(row) if row else None
    finally:
        await db.close()


async def get_user_by_id(uid):
    db = await _conn()
    try:
        cur = await db.execute("SELECT * FROM users WHERE id=?", (uid,))
        row = await cur.fetchone()
        return dict(row) if row else None
    finally:
        await db.close()


async def set_role(tg_id, role, branch_id=None):
    db = await _conn()
    try:
        await db.execute(
            "UPDATE users SET role=?, branch_id=? WHERE tg_id=?",
            (role, branch_id, tg_id),
        )
        await db.commit()
    finally:
        await db.close()


async def update_phone(tg_id, phone):
    db = await _conn()
    try:
        await db.execute("UPDATE users SET phone=? WHERE tg_id=?", (phone, tg_id))
        await db.commit()
    finally:
        await db.close()


async def list_users_by_role(role):
    db = await _conn()
    try:
        cur = await db.execute(
            "SELECT * FROM users WHERE role=? ORDER BY id DESC", (role,)
        )
        return [dict(r) for r in await cur.fetchall()]
    finally:
        await db.close()


async def find_user_by_tg(tg_id):
    return await get_user(tg_id)


async def all_user_tg_ids(role=None, branch_id=None):
    db = await _conn()
    try:
        q = "SELECT tg_id FROM users WHERE 1=1"
        params = []
        if role:
            q += " AND role=?"
            params.append(role)
        if branch_id:
            q += " AND branch_id=?"
            params.append(branch_id)
        cur = await db.execute(q, params)
        return [r["tg_id"] for r in await cur.fetchall()]
    finally:
        await db.close()


async def count_users(role=None):
    db = await _conn()
    try:
        if role:
            cur = await db.execute("SELECT COUNT(*) c FROM users WHERE role=?", (role,))
        else:
            cur = await db.execute("SELECT COUNT(*) c FROM users")
        return (await cur.fetchone())["c"]
    finally:
        await db.close()


# ---------------- KANALLAR (majburiy obuna) ----------------
async def add_channel(chat_id, title, url):
    db = await _conn()
    try:
        await db.execute(
            "INSERT INTO channels (chat_id, title, url) VALUES (?,?,?)",
            (chat_id, title, url),
        )
        await db.commit()
    finally:
        await db.close()


async def list_channels(active_only=False):
    db = await _conn()
    try:
        q = "SELECT * FROM channels"
        if active_only:
            q += " WHERE active=1"
        q += " ORDER BY id"
        cur = await db.execute(q)
        return [dict(r) for r in await cur.fetchall()]
    finally:
        await db.close()


async def delete_channel(cid):
    db = await _conn()
    try:
        await db.execute("DELETE FROM channels WHERE id=?", (cid,))
        await db.commit()
    finally:
        await db.close()


async def toggle_channel(cid):
    db = await _conn()
    try:
        await db.execute("UPDATE channels SET active = 1 - active WHERE id=?", (cid,))
        await db.commit()
    finally:
        await db.close()


# ---------------- FILIALLAR ----------------
async def add_branch(name, address, latitude=None, longitude=None, radius=150,
                     phone=None, work_hours=None):
    db = await _conn()
    try:
        cur = await db.execute(
            "INSERT INTO branches (name, address, latitude, longitude, radius, phone, work_hours) "
            "VALUES (?,?,?,?,?,?,?)",
            (name, address, latitude, longitude, radius, phone, work_hours),
        )
        await db.commit()
        return cur.lastrowid
    finally:
        await db.close()


async def list_branches():
    db = await _conn()
    try:
        cur = await db.execute("SELECT * FROM branches ORDER BY name")
        return [dict(r) for r in await cur.fetchall()]
    finally:
        await db.close()


async def get_branch(bid):
    db = await _conn()
    try:
        cur = await db.execute("SELECT * FROM branches WHERE id=?", (bid,))
        row = await cur.fetchone()
        return dict(row) if row else None
    finally:
        await db.close()


async def update_branch(bid, name, address):
    db = await _conn()
    try:
        await db.execute(
            "UPDATE branches SET name=?, address=? WHERE id=?", (name, address, bid)
        )
        await db.commit()
    finally:
        await db.close()


async def set_branch_location(bid, latitude, longitude, radius=None):
    db = await _conn()
    try:
        if radius is None:
            await db.execute(
                "UPDATE branches SET latitude=?, longitude=? WHERE id=?",
                (latitude, longitude, bid),
            )
        else:
            await db.execute(
                "UPDATE branches SET latitude=?, longitude=?, radius=? WHERE id=?",
                (latitude, longitude, radius, bid),
            )
        await db.commit()
    finally:
        await db.close()


async def delete_branch(bid):
    db = await _conn()
    try:
        await db.execute("DELETE FROM branches WHERE id=?", (bid,))
        await db.commit()
    finally:
        await db.close()


# ---------------- YO'NALISHLAR (POSITIONS) ----------------
async def list_positions():
    db = await _conn()
    try:
        cur = await db.execute("SELECT * FROM positions ORDER BY id")
        return [dict(r) for r in await cur.fetchall()]
    finally:
        await db.close()


async def list_position_names():
    rows = await list_positions()
    return [r["name"] for r in rows]


async def add_position(name):
    db = await _conn()
    try:
        cur = await db.execute("INSERT INTO positions (name) VALUES (?)", (name,))
        await db.commit()
        return cur.lastrowid
    finally:
        await db.close()


async def delete_position(pid):
    db = await _conn()
    try:
        await db.execute("DELETE FROM positions WHERE id=?", (pid,))
        await db.commit()
    finally:
        await db.close()


# ---------------- VAKANSIYALAR ----------------
async def add_vacancy(data, created_by):
    db = await _conn()
    try:
        cur = await db.execute(
            """INSERT INTO vacancies
            (title, branch_id, job_type, shift, salary, work_time,
             requirements, responsibilities, conditions, is_active, created_by)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                data.get("title"),
                data.get("branch_id"),
                data.get("job_type"),
                data.get("shift"),
                data.get("salary"),
                data.get("work_time"),
                data.get("requirements"),
                data.get("responsibilities"),
                data.get("conditions"),
                1 if data.get("is_active", True) else 0,
                created_by,
            ),
        )
        await db.commit()
        return cur.lastrowid
    finally:
        await db.close()


async def get_vacancy(vid):
    db = await _conn()
    try:
        cur = await db.execute(
            """SELECT v.*, b.name AS branch_name
               FROM vacancies v LEFT JOIN branches b ON b.id=v.branch_id
               WHERE v.id=?""",
            (vid,),
        )
        row = await cur.fetchone()
        return dict(row) if row else None
    finally:
        await db.close()


async def list_vacancies(active_only=False):
    db = await _conn()
    try:
        q = """SELECT v.*, b.name AS branch_name
               FROM vacancies v LEFT JOIN branches b ON b.id=v.branch_id"""
        if active_only:
            q += " WHERE v.is_active=1"
        q += " ORDER BY v.id DESC"
        cur = await db.execute(q)
        return [dict(r) for r in await cur.fetchall()]
    finally:
        await db.close()


async def update_vacancy_field(vid, field, value):
    allowed = {
        "title", "branch_id", "job_type", "shift", "salary", "work_time",
        "requirements", "responsibilities", "conditions", "is_active",
    }
    if field not in allowed:
        raise ValueError("Ruxsat etilmagan maydon")
    db = await _conn()
    try:
        await db.execute(f"UPDATE vacancies SET {field}=? WHERE id=?", (value, vid))
        await db.commit()
    finally:
        await db.close()


async def delete_vacancy(vid):
    db = await _conn()
    try:
        await db.execute("DELETE FROM vacancies WHERE id=?", (vid,))
        await db.commit()
    finally:
        await db.close()


# ---------------- ARIZALAR ----------------
APP_FIELDS = [
    "user_id", "vacancy_id", "branch_id", "full_name", "birth_date", "city",
    "district", "address", "position", "position_extra", "uniform_status",
    "shift", "education", "exp_years", "prev_years", "criminal", "marital",
    "children", "prev_salary", "expected_salary", "word_level", "excel_level",
    "languages", "work_intent", "reason", "phone", "resume_file_id",
    "resume_type",
]


async def add_application(data):
    db = await _conn()
    try:
        cols = ", ".join(APP_FIELDS)
        placeholders = ", ".join("?" for _ in APP_FIELDS)
        values = [data.get(f) for f in APP_FIELDS]
        cur = await db.execute(
            f"INSERT INTO applications ({cols}) VALUES ({placeholders})", values
        )
        await db.commit()
        return cur.lastrowid
    finally:
        await db.close()


async def get_application(aid):
    db = await _conn()
    try:
        cur = await db.execute(
            """SELECT a.*, COALESCE(v.title, a.position) AS vacancy_title,
                      b.name AS branch_name, u.tg_id AS applicant_tg
               FROM applications a
               LEFT JOIN vacancies v ON v.id=a.vacancy_id
               LEFT JOIN branches b ON b.id=COALESCE(a.branch_id, v.branch_id)
               LEFT JOIN users u ON u.id=a.user_id
               WHERE a.id=?""",
            (aid,),
        )
        row = await cur.fetchone()
        return dict(row) if row else None
    finally:
        await db.close()


async def list_applications(status=None, limit=None):
    db = await _conn()
    try:
        q = """SELECT a.*, COALESCE(v.title, a.position) AS vacancy_title,
                      b.name AS branch_name
               FROM applications a
               LEFT JOIN vacancies v ON v.id=a.vacancy_id
               LEFT JOIN branches b ON b.id=COALESCE(a.branch_id, v.branch_id)"""
        params = []
        if status:
            q += " WHERE a.status=?"
            params.append(status)
        q += " ORDER BY a.id DESC"
        if limit:
            q += f" LIMIT {int(limit)}"
        cur = await db.execute(q, params)
        return [dict(r) for r in await cur.fetchall()]
    finally:
        await db.close()


async def filter_applications(filters=None, limit=30):
    filters = filters or {}
    db = await _conn()
    try:
        q = """SELECT a.*, COALESCE(v.title, a.position) AS vacancy_title,
                      b.name AS branch_name
               FROM applications a
               LEFT JOIN vacancies v ON v.id=a.vacancy_id
               LEFT JOIN branches b ON b.id=COALESCE(a.branch_id, v.branch_id)
               WHERE 1=1"""
        params = []
        if filters.get("status"):
            q += " AND a.status=?"
            params.append(filters["status"])
        if filters.get("branch_id"):
            q += " AND COALESCE(a.branch_id, v.branch_id)=?"
            params.append(filters["branch_id"])
        if filters.get("uniform_status"):
            q += " AND a.uniform_status=?"
            params.append(filters["uniform_status"])
        if filters.get("city"):
            q += " AND a.city LIKE ?"
            params.append(f"%{filters['city']}%")
        if filters.get("district"):
            q += " AND a.district LIKE ?"
            params.append(f"%{filters['district']}%")
        if filters.get("position"):
            q += " AND COALESCE(v.title, a.position) LIKE ?"
            params.append(f"%{filters['position']}%")
        q += " ORDER BY a.id DESC"
        if limit:
            q += f" LIMIT {int(limit)}"
        cur = await db.execute(q, params)
        return [dict(r) for r in await cur.fetchall()]
    finally:
        await db.close()


async def application_status_counts():
    db = await _conn()
    try:
        cur = await db.execute(
            """SELECT status, COUNT(*) AS cnt
               FROM applications
               GROUP BY status"""
        )
        return {r["status"]: r["cnt"] for r in await cur.fetchall()}
    finally:
        await db.close()


async def user_applications(user_id):
    db = await _conn()
    try:
        cur = await db.execute(
            """SELECT a.*, COALESCE(v.title, a.position) AS vacancy_title
               FROM applications a
               LEFT JOIN vacancies v ON v.id=a.vacancy_id
               WHERE a.user_id=? ORDER BY a.id DESC""",
            (user_id,),
        )
        return [dict(r) for r in await cur.fetchall()]
    finally:
        await db.close()


async def count_applications(user_id):
    db = await _conn()
    try:
        cur = await db.execute(
            "SELECT COUNT(*) c FROM applications WHERE user_id=?", (user_id,)
        )
        return (await cur.fetchone())["c"]
    finally:
        await db.close()


async def set_application_status(aid, status, handled_by=None):
    db = await _conn()
    try:
        await db.execute(
            "UPDATE applications SET status=?, handled_by=? WHERE id=?",
            (status, handled_by, aid),
        )
        await db.commit()
    finally:
        await db.close()


async def set_application_comment(aid, comment):
    db = await _conn()
    try:
        await db.execute(
            "UPDATE applications SET hr_comment=? WHERE id=?", (comment, aid)
        )
        await db.commit()
    finally:
        await db.close()


# ---------------- XODIM PROFILLARI / FORMA / JARIMALAR ----------------
async def upsert_employee_profile(
    user_id, application_id, role, position, branch_id=None, uniform_status=None,
    monthly_salary=None, birth_date=None, address=None, work_hours=None,
    rest_day=None, photo_file_id=None, extra_info=None, since=None,
):
    """Xodim profilini yaratadi yoki yangilaydi.
    None berilgan qo'shimcha maydonlar mavjud qiymatni o'zgartirmaydi (COALESCE)."""
    db = await _conn()
    try:
        cur = await db.execute(
            "SELECT id, uniform_status FROM employee_profiles WHERE user_id=?",
            (user_id,),
        )
        row = await cur.fetchone()
        status = uniform_status or (row["uniform_status"] if row else "unknown")
        if row:
            await db.execute(
                """UPDATE employee_profiles
                   SET application_id=?, role=?, position=?, branch_id=?,
                       uniform_status=?,
                       monthly_salary=COALESCE(?, monthly_salary),
                       birth_date=COALESCE(?, birth_date),
                       address=COALESCE(?, address),
                       work_hours=COALESCE(?, work_hours),
                       rest_day=COALESCE(?, rest_day),
                       photo_file_id=COALESCE(?, photo_file_id),
                       extra_info=COALESCE(?, extra_info),
                       since=COALESCE(?, since),
                       updated_at=datetime('now','+5 hours')
                   WHERE user_id=?""",
                (application_id, role, position, branch_id, status,
                 monthly_salary, birth_date, address, work_hours, rest_day,
                 photo_file_id, extra_info, since, user_id),
            )
        else:
            await db.execute(
                """INSERT INTO employee_profiles
                   (user_id, application_id, role, position, branch_id, uniform_status,
                    monthly_salary, birth_date, address, work_hours, rest_day,
                    photo_file_id, extra_info, since)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (user_id, application_id, role, position, branch_id, status,
                 monthly_salary, birth_date, address, work_hours, rest_day,
                 photo_file_id, extra_info, since),
            )
        await db.commit()
    finally:
        await db.close()


async def get_employee_profile(user_id):
    db = await _conn()
    try:
        cur = await db.execute(
            """SELECT ep.*, u.tg_id, u.full_name, u.phone, b.name AS branch_name
               FROM employee_profiles ep
               JOIN users u ON u.id=ep.user_id
               LEFT JOIN branches b ON b.id=ep.branch_id
               WHERE ep.user_id=?""",
            (user_id,),
        )
        row = await cur.fetchone()
        return dict(row) if row else None
    finally:
        await db.close()


async def get_employee_profile_by_tg(tg_id):
    db = await _conn()
    try:
        cur = await db.execute(
            """SELECT ep.*, u.tg_id, u.full_name, u.phone, b.name AS branch_name
               FROM employee_profiles ep
               JOIN users u ON u.id=ep.user_id
               LEFT JOIN branches b ON b.id=ep.branch_id
               WHERE u.tg_id=?""",
            (tg_id,),
        )
        row = await cur.fetchone()
        return dict(row) if row else None
    finally:
        await db.close()


async def list_employee_profiles(role=None, uniform_status=None, branch_id=None):
    db = await _conn()
    try:
        q = """SELECT ep.*, u.tg_id, u.full_name, u.phone, b.name AS branch_name
               FROM employee_profiles ep
               JOIN users u ON u.id=ep.user_id
               LEFT JOIN branches b ON b.id=ep.branch_id
               WHERE 1=1"""
        params = []
        if role:
            q += " AND ep.role=?"
            params.append(role)
        if uniform_status:
            q += " AND ep.uniform_status=?"
            params.append(uniform_status)
        if branch_id:
            q += " AND ep.branch_id=?"
            params.append(branch_id)
        q += " ORDER BY ep.id DESC"
        cur = await db.execute(q, params)
        return [dict(r) for r in await cur.fetchall()]
    finally:
        await db.close()


async def uniform_stats(role=None):
    db = await _conn()
    try:
        sql = """SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN uniform_status='yes' THEN 1 ELSE 0 END) AS has_uniform,
                    SUM(CASE WHEN uniform_status='no' THEN 1 ELSE 0 END) AS no_uniform,
                    SUM(CASE WHEN uniform_status NOT IN ('yes','no') OR uniform_status IS NULL THEN 1 ELSE 0 END) AS unknown
                 FROM employee_profiles"""
        params = []
        if role:
            sql += " WHERE role=?"
            params.append(role)
        cur = await db.execute(sql, params)
        row = await cur.fetchone()
        return dict(row)
    finally:
        await db.close()


async def update_uniform_status(user_id, status):
    db = await _conn()
    try:
        await db.execute(
            """UPDATE employee_profiles
               SET uniform_status=?, updated_at=datetime('now','+5 hours')
               WHERE user_id=?""",
            (status, user_id),
        )
        await db.commit()
    finally:
        await db.close()


async def update_rest_day(user_id, rest_day):
    db = await _conn()
    try:
        await db.execute(
            """UPDATE employee_profiles
               SET rest_day=?, updated_at=datetime('now','+5 hours')
               WHERE user_id=?""",
            (rest_day, user_id),
        )
        await db.commit()
    finally:
        await db.close()


async def update_monthly_salary(user_id, salary):
    db = await _conn()
    try:
        await db.execute(
            """UPDATE employee_profiles
               SET monthly_salary=?, updated_at=datetime('now','+5 hours')
               WHERE user_id=?""",
            (salary, user_id),
        )
        await db.commit()
    finally:
        await db.close()


async def add_fine(employee_user_id, amount, reason, created_by):
    db = await _conn()
    try:
        cur = await db.execute(
            """INSERT INTO fines (employee_user_id, amount, reason, created_by)
               VALUES (?,?,?,?)""",
            (employee_user_id, amount, reason, created_by),
        )
        await db.commit()
        return cur.lastrowid
    finally:
        await db.close()


async def list_fines(employee_user_id, limit=30):
    db = await _conn()
    try:
        cur = await db.execute(
            """SELECT f.*, u.full_name AS created_by_name
               FROM fines f
               LEFT JOIN users u ON u.id=f.created_by
               WHERE f.employee_user_id=?
               ORDER BY f.id DESC LIMIT ?""",
            (employee_user_id, limit),
        )
        return [dict(r) for r in await cur.fetchall()]
    finally:
        await db.close()


async def get_fine(fid):
    db = await _conn()
    try:
        cur = await db.execute(
            """SELECT f.*, u.full_name AS created_by_name,
                      ep.user_id AS profile_user_id, owner.tg_id AS employee_tg,
                      owner.full_name AS employee_name
               FROM fines f
               LEFT JOIN users u ON u.id=f.created_by
               LEFT JOIN employee_profiles ep ON ep.user_id=f.employee_user_id
               LEFT JOIN users owner ON owner.id=f.employee_user_id
               WHERE f.id=?""",
            (fid,),
        )
        row = await cur.fetchone()
        return dict(row) if row else None
    finally:
        await db.close()


# ---------------- FILIAL RAHBARI SO'ROVLARI ----------------
async def add_manager_request(data):
    db = await _conn()
    try:
        cur = await db.execute(
            """INSERT INTO manager_requests
               (manager_user_id, branch_id, kind, title, staff_count, details)
               VALUES (?,?,?,?,?,?)""",
            (
                data.get("manager_user_id"),
                data.get("branch_id"),
                data.get("kind"),
                data.get("title"),
                data.get("staff_count"),
                data.get("details"),
            ),
        )
        await db.commit()
        return cur.lastrowid
    finally:
        await db.close()


async def get_manager_request(rid):
    db = await _conn()
    try:
        cur = await db.execute(
            """SELECT mr.*, u.tg_id AS manager_tg, u.full_name AS manager_name,
                      b.name AS branch_name
               FROM manager_requests mr
               JOIN users u ON u.id=mr.manager_user_id
               LEFT JOIN branches b ON b.id=mr.branch_id
               WHERE mr.id=?""",
            (rid,),
        )
        row = await cur.fetchone()
        return dict(row) if row else None
    finally:
        await db.close()


async def list_manager_requests(status=None, manager_user_id=None, limit=30):
    db = await _conn()
    try:
        sql = """SELECT mr.*, u.tg_id AS manager_tg, u.full_name AS manager_name,
                        b.name AS branch_name
                 FROM manager_requests mr
                 JOIN users u ON u.id=mr.manager_user_id
                 LEFT JOIN branches b ON b.id=mr.branch_id
                 WHERE 1=1"""
        params = []
        if status:
            sql += " AND mr.status=?"
            params.append(status)
        if manager_user_id:
            sql += " AND mr.manager_user_id=?"
            params.append(manager_user_id)
        sql += " ORDER BY mr.id DESC"
        if limit:
            sql += f" LIMIT {int(limit)}"
        cur = await db.execute(sql, params)
        return [dict(r) for r in await cur.fetchall()]
    finally:
        await db.close()


async def set_manager_request_status(rid, status, handled_by=None, comment=None):
    db = await _conn()
    try:
        await db.execute(
            """UPDATE manager_requests
               SET status=?, handled_by=?, hr_comment=COALESCE(?, hr_comment)
               WHERE id=?""",
            (status, handled_by, comment, rid),
        )
        await db.commit()
    finally:
        await db.close()


# ---------------- ISHDAN BO'SHATISH SO'ROVLARI ----------------
async def add_termination_request(data):
    db = await _conn()
    try:
        cur = await db.execute(
            """INSERT INTO termination_requests
               (employee_user_id, requested_by, branch_id, reason)
               VALUES (?,?,?,?)""",
            (
                data.get("employee_user_id"),
                data.get("requested_by"),
                data.get("branch_id"),
                data.get("reason"),
            ),
        )
        await db.commit()
        return cur.lastrowid
    finally:
        await db.close()


async def get_termination_request(rid):
    db = await _conn()
    try:
        cur = await db.execute(
            """SELECT tr.*,
                      emp.tg_id AS employee_tg, emp.full_name AS employee_name,
                      req.tg_id AS requester_tg, req.full_name AS requester_name,
                      req.role AS requester_role,
                      b.name AS branch_name,
                      ep.since AS employee_since, ep.position AS employee_position
               FROM termination_requests tr
               JOIN users emp ON emp.id = tr.employee_user_id
               JOIN users req ON req.id = tr.requested_by
               LEFT JOIN branches b ON b.id = tr.branch_id
               LEFT JOIN employee_profiles ep ON ep.user_id = tr.employee_user_id
               WHERE tr.id=?""",
            (rid,),
        )
        row = await cur.fetchone()
        return dict(row) if row else None
    finally:
        await db.close()


async def set_termination_request_status(rid, status, handled_by=None, comment=None):
    db = await _conn()
    try:
        await db.execute(
            """UPDATE termination_requests
               SET status=?, handled_by=?, hr_comment=COALESCE(?, hr_comment)
               WHERE id=?""",
            (status, handled_by, comment, rid),
        )
        await db.commit()
    finally:
        await db.close()


async def fire_employee(user_id):
    """Xodimni ishdan bo'shatadi: profilini o'chiradi va rolini nomzodga qaytaradi
    (shu bilan xodim paneli va «Ishga keldim» tugmalari yo'qoladi)."""
    db = await _conn()
    try:
        await db.execute("DELETE FROM employee_profiles WHERE user_id=?", (user_id,))
        await db.execute(
            "UPDATE users SET role='candidate', branch_id=NULL WHERE id=?",
            (user_id,),
        )
        await db.commit()
    finally:
        await db.close()


async def search_applications(field, value):
    """field: full_name | phone | branch | vacancy"""
    db = await _conn()
    try:
        base = """SELECT a.*, COALESCE(v.title, a.position) AS vacancy_title,
                         b.name AS branch_name
                  FROM applications a
                  LEFT JOIN vacancies v ON v.id=a.vacancy_id
                  LEFT JOIN branches b ON b.id=COALESCE(a.branch_id, v.branch_id)
                  WHERE """
        like = f"%{value}%"
        if field == "full_name":
            q = base + "a.full_name LIKE ?"
        elif field == "phone":
            q = base + "a.phone LIKE ?"
        elif field == "branch":
            q = base + "b.name LIKE ?"
        elif field == "vacancy":
            q = base + "COALESCE(v.title, a.position) LIKE ?"
        else:
            return []
        q += " ORDER BY a.id DESC LIMIT 30"
        cur = await db.execute(q, (like,))
        return [dict(r) for r in await cur.fetchall()]
    finally:
        await db.close()


# ---------------- SUHBATLAR ----------------
async def add_interview(application_id, date, time, location, comment, created_by):
    db = await _conn()
    try:
        cur = await db.execute(
            """INSERT INTO interviews
               (application_id, date, time, location, comment, created_by)
               VALUES (?,?,?,?,?,?)""",
            (application_id, date, time, location, comment, created_by),
        )
        await db.commit()
        return cur.lastrowid
    finally:
        await db.close()


async def get_interview(iid):
    db = await _conn()
    try:
        cur = await db.execute("SELECT * FROM interviews WHERE id=?", (iid,))
        row = await cur.fetchone()
        return dict(row) if row else None
    finally:
        await db.close()


async def latest_interview_for_app(aid):
    db = await _conn()
    try:
        cur = await db.execute(
            "SELECT * FROM interviews WHERE application_id=? ORDER BY id DESC LIMIT 1",
            (aid,),
        )
        row = await cur.fetchone()
        return dict(row) if row else None
    finally:
        await db.close()


async def set_interview_status(iid, status):
    db = await _conn()
    try:
        await db.execute("UPDATE interviews SET status=? WHERE id=?", (status, iid))
        await db.commit()
    finally:
        await db.close()


async def interviews_for_reminders(limit=100):
    db = await _conn()
    try:
        cur = await db.execute(
            """SELECT i.*, a.full_name, COALESCE(v.title, a.position) AS vacancy_title,
                      u.tg_id AS applicant_tg
               FROM interviews i
               JOIN applications a ON a.id=i.application_id
               LEFT JOIN vacancies v ON v.id=a.vacancy_id
               LEFT JOIN users u ON u.id=a.user_id
               WHERE i.status IN ('pending','confirmed')
                 AND (i.reminder_day_sent=0 OR i.reminder_2h_sent=0)
               ORDER BY i.id DESC
               LIMIT ?""",
            (limit,),
        )
        return [dict(r) for r in await cur.fetchall()]
    finally:
        await db.close()


async def mark_interview_reminder_sent(iid, kind):
    if kind not in {"day", "2h"}:
        raise ValueError("Noto'g'ri reminder turi")
    field = "reminder_day_sent" if kind == "day" else "reminder_2h_sent"
    db = await _conn()
    try:
        await db.execute(f"UPDATE interviews SET {field}=1 WHERE id=?", (iid,))
        await db.commit()
    finally:
        await db.close()


# ---------------- AUDIT LOG ----------------
async def add_log(tg_id, actor_name, action, details=""):
    db = await _conn()
    try:
        await db.execute(
            "INSERT INTO audit_logs (tg_id, actor_name, action, details) VALUES (?,?,?,?)",
            (tg_id, actor_name, action, details),
        )
        await db.commit()
    finally:
        await db.close()


async def list_logs(limit=30):
    db = await _conn()
    try:
        cur = await db.execute(
            "SELECT * FROM audit_logs ORDER BY id DESC LIMIT ?", (limit,)
        )
        return [dict(r) for r in await cur.fetchall()]
    finally:
        await db.close()


# ---------------- STATISTIKA ----------------
async def stats_counts():
    db = await _conn()
    try:
        out = {}
        for key, sql in {
            "today": "SELECT COUNT(*) c FROM applications WHERE date(created_at)=date('now','+5 hours')",
            "week": "SELECT COUNT(*) c FROM applications WHERE date(created_at)>=date('now','+5 hours','-6 days')",
            "month": "SELECT COUNT(*) c FROM applications WHERE date(created_at)>=date('now','+5 hours','-29 days')",
            "accepted": "SELECT COUNT(*) c FROM applications WHERE status='accepted'",
            "rejected": "SELECT COUNT(*) c FROM applications WHERE status='rejected'",
            "interview": "SELECT COUNT(*) c FROM applications WHERE status='interview'",
            "new": "SELECT COUNT(*) c FROM applications WHERE status='new'",
            "total": "SELECT COUNT(*) c FROM applications",
        }.items():
            cur = await db.execute(sql)
            out[key] = (await cur.fetchone())["c"]
        return out
    finally:
        await db.close()


async def stats_by_branch():
    db = await _conn()
    try:
        cur = await db.execute(
            """SELECT b.name AS name, COUNT(a.id) AS cnt
               FROM applications a
               LEFT JOIN vacancies v ON v.id=a.vacancy_id
               LEFT JOIN branches b ON b.id=COALESCE(a.branch_id, v.branch_id)
               GROUP BY b.name ORDER BY cnt DESC"""
        )
        return [dict(r) for r in await cur.fetchall()]
    finally:
        await db.close()


async def stats_by_vacancy():
    db = await _conn()
    try:
        cur = await db.execute(
            """SELECT COALESCE(v.title, a.position) AS name, COUNT(a.id) AS cnt
               FROM applications a
               LEFT JOIN vacancies v ON v.id=a.vacancy_id
               GROUP BY COALESCE(v.title, a.position) ORDER BY cnt DESC"""
        )
        return [dict(r) for r in await cur.fetchall()]
    finally:
        await db.close()


async def employee_stats_by_branch():
    db = await _conn()
    try:
        cur = await db.execute(
            """SELECT COALESCE(b.name, 'Filialsiz') AS name,
                      COUNT(ep.id) AS total,
                      SUM(CASE WHEN ep.role='pharmacist' THEN 1 ELSE 0 END) AS pharmacists,
                      SUM(CASE WHEN ep.role='manager' THEN 1 ELSE 0 END) AS managers,
                      SUM(CASE WHEN ep.role='employee' THEN 1 ELSE 0 END) AS employees,
                      SUM(CASE WHEN ep.uniform_status='yes' THEN 1 ELSE 0 END) AS has_uniform,
                      SUM(CASE WHEN ep.uniform_status='no' THEN 1 ELSE 0 END) AS no_uniform
               FROM employee_profiles ep
               LEFT JOIN branches b ON b.id=ep.branch_id
               GROUP BY ep.branch_id
               ORDER BY total DESC"""
        )
        return [dict(r) for r in await cur.fetchall()]
    finally:
        await db.close()


async def employee_stats_by_role():
    db = await _conn()
    try:
        cur = await db.execute(
            """SELECT role, COUNT(*) AS cnt
               FROM employee_profiles
               GROUP BY role
               ORDER BY cnt DESC"""
        )
        return [dict(r) for r in await cur.fetchall()]
    finally:
        await db.close()


async def manager_request_counts():
    db = await _conn()
    try:
        cur = await db.execute(
            """SELECT status, COUNT(*) AS cnt
               FROM manager_requests
               GROUP BY status"""
        )
        return {r["status"]: r["cnt"] for r in await cur.fetchall()}
    finally:
        await db.close()


async def top_hr():
    db = await _conn()
    try:
        cur = await db.execute(
            """SELECT u.full_name AS name, COUNT(a.id) AS cnt
               FROM applications a
               JOIN users u ON u.id=a.handled_by
               GROUP BY u.id ORDER BY cnt DESC LIMIT 10"""
        )
        return [dict(r) for r in await cur.fetchall()]
    finally:
        await db.close()


# ---------------- SOZLAMALAR ----------------
async def get_setting(key, default=None):
    db = await _conn()
    try:
        cur = await db.execute("SELECT value FROM settings WHERE key=?", (key,))
        row = await cur.fetchone()
        return row["value"] if row else default
    finally:
        await db.close()


async def set_setting(key, value):
    db = await _conn()
    try:
        await db.execute(
            """INSERT INTO settings (key, value) VALUES (?,?)
               ON CONFLICT(key) DO UPDATE SET value=excluded.value""",
            (key, value),
        )
        await db.commit()
    finally:
        await db.close()


# ---------------- FOYDALANUVCHILAR BOSHQARUVI ----------------
async def list_users(search=None, blocked=None, limit=50):
    db = await _conn()
    try:
        sql = """SELECT u.*, b.name AS branch_name
                 FROM users u LEFT JOIN branches b ON b.id=u.branch_id
                 WHERE 1=1"""
        params = []
        if search:
            sql += " AND (u.full_name LIKE ? OR u.username LIKE ? OR CAST(u.tg_id AS TEXT) LIKE ? OR u.phone LIKE ?)"
            like = f"%{search}%"
            params += [like, like, like, like]
        if blocked is not None:
            sql += " AND COALESCE(u.blocked,0)=?"
            params.append(1 if blocked else 0)
        sql += " ORDER BY u.id DESC"
        if limit:
            sql += f" LIMIT {int(limit)}"
        cur = await db.execute(sql, params)
        return [dict(r) for r in await cur.fetchall()]
    finally:
        await db.close()


async def set_user_blocked(tg_id, blocked):
    db = await _conn()
    try:
        await db.execute(
            "UPDATE users SET blocked=? WHERE tg_id=?", (1 if blocked else 0, tg_id)
        )
        await db.commit()
    finally:
        await db.close()


async def is_user_blocked(tg_id):
    db = await _conn()
    try:
        cur = await db.execute("SELECT COALESCE(blocked,0) b FROM users WHERE tg_id=?", (tg_id,))
        row = await cur.fetchone()
        return bool(row and row["b"])
    finally:
        await db.close()


async def count_blocked():
    db = await _conn()
    try:
        cur = await db.execute("SELECT COUNT(*) c FROM users WHERE COALESCE(blocked,0)=1")
        return (await cur.fetchone())["c"]
    finally:
        await db.close()


# ---------------- SARALANGAN (SHORTLIST) ARIZALAR ----------------
async def toggle_favorite(aid):
    db = await _conn()
    try:
        await db.execute(
            "UPDATE applications SET favorite = 1 - COALESCE(favorite,0) WHERE id=?", (aid,)
        )
        await db.commit()
        cur = await db.execute("SELECT COALESCE(favorite,0) f FROM applications WHERE id=?", (aid,))
        row = await cur.fetchone()
        return bool(row and row["f"])
    finally:
        await db.close()


async def list_favorite_applications(limit=30):
    db = await _conn()
    try:
        cur = await db.execute(
            """SELECT a.*, COALESCE(v.title, a.position) AS vacancy_title,
                      b.name AS branch_name
               FROM applications a
               LEFT JOIN vacancies v ON v.id=a.vacancy_id
               LEFT JOIN branches b ON b.id=COALESCE(a.branch_id, v.branch_id)
               WHERE COALESCE(a.favorite,0)=1
               ORDER BY a.id DESC LIMIT ?""",
            (limit,),
        )
        return [dict(r) for r in await cur.fetchall()]
    finally:
        await db.close()


# ---------------- SUHBATLAR KALENDARI ----------------
async def list_upcoming_interviews(limit=30):
    db = await _conn()
    try:
        cur = await db.execute(
            """SELECT i.*, a.full_name, a.phone,
                      COALESCE(v.title, a.position) AS vacancy_title,
                      b.name AS branch_name
               FROM interviews i
               JOIN applications a ON a.id=i.application_id
               LEFT JOIN vacancies v ON v.id=a.vacancy_id
               LEFT JOIN branches b ON b.id=COALESCE(a.branch_id, v.branch_id)
               WHERE i.status IN ('pending','confirmed','reschedule')
               ORDER BY i.id DESC LIMIT ?""",
            (limit,),
        )
        return [dict(r) for r in await cur.fetchall()]
    finally:
        await db.close()


# ---------------- DAVRIY TAQQOSLASH / REYTING ----------------
async def stats_periods():
    """Bu hafta/o'tgan hafta, bu oy/o'tgan oy ariza va qabul sonlari."""
    db = await _conn()
    try:
        out = {}
        queries = {
            "week_now": "date(created_at) >= date('now','+5 hours','-6 days')",
            "week_prev": "date(created_at) >= date('now','+5 hours','-13 days') AND date(created_at) < date('now','+5 hours','-6 days')",
            "month_now": "date(created_at) >= date('now','+5 hours','-29 days')",
            "month_prev": "date(created_at) >= date('now','+5 hours','-59 days') AND date(created_at) < date('now','+5 hours','-29 days')",
        }
        for key, cond in queries.items():
            cur = await db.execute(f"SELECT COUNT(*) c FROM applications WHERE {cond}")
            out[key] = (await cur.fetchone())["c"]
            cur = await db.execute(
                f"SELECT COUNT(*) c FROM applications WHERE status='accepted' AND {cond}"
            )
            out[key + "_acc"] = (await cur.fetchone())["c"]
        return out
    finally:
        await db.close()


async def branch_ranking():
    """Filiallar bo'yicha ariza, qabul va xodim soni reytingi."""
    db = await _conn()
    try:
        cur = await db.execute(
            """SELECT COALESCE(b.name,'Filialsiz') AS name,
                      COUNT(a.id) AS total,
                      SUM(CASE WHEN a.status='accepted' THEN 1 ELSE 0 END) AS accepted,
                      SUM(CASE WHEN a.status='new' THEN 1 ELSE 0 END) AS new_cnt
               FROM applications a
               LEFT JOIN vacancies v ON v.id=a.vacancy_id
               LEFT JOIN branches b ON b.id=COALESCE(a.branch_id, v.branch_id)
               GROUP BY COALESCE(b.name,'Filialsiz')
               ORDER BY total DESC"""
        )
        return [dict(r) for r in await cur.fetchall()]
    finally:
        await db.close()


# ---------------- GULNORA FARM HODIMI (SELF-REGISTRATSIYA) ----------------
STAFF_REG_FIELDS = [
    "user_id", "full_name", "birth_date", "phone", "role", "position", "address",
    "branch_id", "branch_name", "work_hours", "salary", "rest_day",
    "uniform_status", "photo_file_id", "since", "extra_info",
]


async def add_staff_reg(data):
    db = await _conn()
    try:
        cols = ", ".join(STAFF_REG_FIELDS)
        placeholders = ", ".join("?" for _ in STAFF_REG_FIELDS)
        values = [data.get(f) for f in STAFF_REG_FIELDS]
        cur = await db.execute(
            f"INSERT INTO staff_regs ({cols}) VALUES ({placeholders})", values
        )
        await db.commit()
        return cur.lastrowid
    finally:
        await db.close()


async def get_staff_reg(rid):
    db = await _conn()
    try:
        cur = await db.execute(
            """SELECT sr.*, u.tg_id AS user_tg, b.name AS branch_db_name
               FROM staff_regs sr
               JOIN users u ON u.id=sr.user_id
               LEFT JOIN branches b ON b.id=sr.branch_id
               WHERE sr.id=?""",
            (rid,),
        )
        row = await cur.fetchone()
        return dict(row) if row else None
    finally:
        await db.close()


async def list_staff_regs(status=None, limit=30):
    db = await _conn()
    try:
        sql = """SELECT sr.*, u.tg_id AS user_tg, b.name AS branch_db_name
                 FROM staff_regs sr
                 JOIN users u ON u.id=sr.user_id
                 LEFT JOIN branches b ON b.id=sr.branch_id
                 WHERE 1=1"""
        params = []
        if status:
            sql += " AND sr.status=?"
            params.append(status)
        sql += " ORDER BY sr.id DESC"
        if limit:
            sql += f" LIMIT {int(limit)}"
        cur = await db.execute(sql, params)
        return [dict(r) for r in await cur.fetchall()]
    finally:
        await db.close()


async def set_staff_reg_status(rid, status, handled_by=None):
    db = await _conn()
    try:
        await db.execute(
            "UPDATE staff_regs SET status=?, handled_by=? WHERE id=?",
            (status, handled_by, rid),
        )
        await db.commit()
    finally:
        await db.close()


async def count_staff_regs(status=None):
    db = await _conn()
    try:
        if status:
            cur = await db.execute(
                "SELECT COUNT(*) c FROM staff_regs WHERE status=?", (status,)
            )
        else:
            cur = await db.execute("SELECT COUNT(*) c FROM staff_regs")
        return (await cur.fetchone())["c"]
    finally:
        await db.close()


# ---------------- DAVOMAT (ATTENDANCE) ----------------
async def get_attendance_today(tg_id):
    """Bugungi oxirgi davomat yozuvi. tg_id (Telegram id) qabul qiladi va
    ichki users.id ga bog'lab qidiradi (attendance.user_id = users.id)."""
    db = await _conn()
    try:
        cur = await db.execute(
            """SELECT a.* FROM attendance a
               JOIN users u ON u.id = a.user_id
               WHERE u.tg_id=? AND a.date=date('now','+5 hours')
               ORDER BY a.id DESC LIMIT 1""",
            (tg_id,),
        )
        row = await cur.fetchone()
        return dict(row) if row else None
    finally:
        await db.close()


async def add_attendance(user_id, branch_id, latitude, longitude, distance,
                         status="present", late=0):
    db = await _conn()
    try:
        cur = await db.execute(
            """INSERT INTO attendance
               (user_id, branch_id, date, time, latitude, longitude, distance, status,
                late, last_prompt_at)
               VALUES (?,?,date('now','+5 hours'),time('now','+5 hours'),?,?,?,?,?,
                       datetime('now','+5 hours'))""",
            (user_id, branch_id, latitude, longitude, distance, status, 1 if late else 0),
        )
        await db.commit()
        return cur.lastrowid
    finally:
        await db.close()


async def set_attendance_checkout(att_id, latitude, longitude, distance, early=0):
    db = await _conn()
    try:
        await db.execute(
            """UPDATE attendance
               SET out_time=time('now','+5 hours'), out_latitude=?, out_longitude=?,
                   out_distance=?, early=?
               WHERE id=?""",
            (latitude, longitude, distance, 1 if early else 0, att_id),
        )
        await db.commit()
    finally:
        await db.close()


# ---------------- TANAFFUS (break) ----------------
async def start_break(att_id):
    """Tanaffusni boshlaydi (break_started_at = hozir, on_break=1)."""
    db = await _conn()
    try:
        await db.execute(
            """UPDATE attendance
               SET on_break=1, break_started_at=datetime('now','+5 hours')
               WHERE id=?""",
            (att_id,),
        )
        await db.commit()
    finally:
        await db.close()


async def end_break(att_id):
    """Tanaffusni tugatadi: o'tgan vaqtni break_seconds ga qo'shadi."""
    db = await _conn()
    try:
        await db.execute(
            """UPDATE attendance
               SET break_seconds = break_seconds + CAST(
                     (julianday(datetime('now','+5 hours')) - julianday(break_started_at))
                     * 86400 AS INTEGER),
                   on_break=0, break_started_at=NULL, last_prompt_at=datetime('now','+5 hours')
               WHERE id=? AND on_break=1 AND break_started_at IS NOT NULL""",
            (att_id,),
        )
        await db.commit()
    finally:
        await db.close()


async def break_total_today(tg_id):
    """Bugungi jami tanaffus (sekund). Agar hozir tanaffusda bo'lsa — davomini ham qo'shadi."""
    row = await get_attendance_today(tg_id)
    if not row:
        return 0
    total = row.get("break_seconds") or 0
    return total


# ---------------- JOYLASHUV TEKSHIRUVLARI (periodik) ----------------
async def add_location_check(attendance_id, user_id, branch_id, kind="auto"):
    db = await _conn()
    try:
        cur = await db.execute(
            """INSERT INTO location_checks
               (attendance_id, user_id, branch_id, date, requested_at, status, kind)
               VALUES (?,?,?,date('now','+5 hours'),datetime('now','+5 hours'),'pending',?)""",
            (attendance_id, user_id, branch_id, kind),
        )
        await db.commit()
        return cur.lastrowid
    finally:
        await db.close()


async def latest_pending_location_check(tg_id):
    """Foydalanuvchining bugungi javob kutayotgan (pending) oxirgi tekshiruvi."""
    db = await _conn()
    try:
        cur = await db.execute(
            """SELECT lc.* FROM location_checks lc
               JOIN users u ON u.id = lc.user_id
               WHERE u.tg_id=? AND lc.date=date('now','+5 hours') AND lc.status='pending'
               ORDER BY lc.id DESC LIMIT 1""",
            (tg_id,),
        )
        row = await cur.fetchone()
        return dict(row) if row else None
    finally:
        await db.close()


async def resolve_location_check(check_id, status, distance=None):
    db = await _conn()
    try:
        await db.execute(
            """UPDATE location_checks
               SET status=?, distance=?, responded_at=datetime('now','+5 hours')
               WHERE id=?""",
            (status, distance, check_id),
        )
        await db.commit()
    finally:
        await db.close()


async def mark_stale_location_checks(minutes=30):
    """Belgilangan vaqtdan oshgan javobsiz tekshiruvlarni 'missed' qiladi."""
    db = await _conn()
    try:
        await db.execute(
            f"""UPDATE location_checks
                SET status='missed'
                WHERE status='pending'
                  AND (julianday(datetime('now','+5 hours')) - julianday(requested_at))
                      * 1440 > {int(minutes)}""",
        )
        await db.commit()
    finally:
        await db.close()


async def attendance_due_for_check(interval_hours):
    """Periodik joylashuv so'rovi kerak bo'lgan bugungi davomat yozuvlari.
    Ishda (present), ketmagan, tanaffusda emas va oxirgi so'rovdan interval o'tgan."""
    db = await _conn()
    try:
        cur = await db.execute(
            """SELECT a.*, u.tg_id, u.full_name
               FROM attendance a
               JOIN users u ON u.id=a.user_id
               WHERE a.date=date('now','+5 hours')
                 AND a.status='present' AND a.out_time IS NULL
                 AND COALESCE(a.on_break,0)=0
                 AND (a.last_prompt_at IS NULL OR
                      (julianday(datetime('now','+5 hours')) - julianday(a.last_prompt_at))
                      * 24 >= ?)""",
            (float(interval_hours),),
        )
        return [dict(r) for r in await cur.fetchall()]
    finally:
        await db.close()


async def touch_attendance_prompt(att_id):
    db = await _conn()
    try:
        await db.execute(
            "UPDATE attendance SET last_prompt_at=datetime('now','+5 hours') WHERE id=?",
            (att_id,),
        )
        await db.commit()
    finally:
        await db.close()


async def break_and_check_stats(period="month", branch_id=None):
    """Xodimlar kesimida tanaffus va joylashuv tekshiruvi statistikasi (filial rahbari uchun)."""
    db = await _conn()
    try:
        cond = _period_cond(period)
        sql = f"""SELECT u.id AS user_id, u.tg_id, u.full_name,
                         b.name AS branch_name,
                         SUM(COALESCE(a.break_seconds,0)) AS break_seconds,
                         COUNT(DISTINCT a.date) AS days
                  FROM attendance a
                  JOIN users u ON u.id=a.user_id
                  LEFT JOIN branches b ON b.id=a.branch_id
                  WHERE a.status='present' AND {cond}"""
        params = []
        if branch_id:
            sql += " AND a.branch_id=?"
            params.append(branch_id)
        sql += " GROUP BY u.id ORDER BY break_seconds DESC, u.full_name"
        cur = await db.execute(sql, params)
        rows = [dict(r) for r in await cur.fetchall()]

        # Joylashuv tekshiruvlari kesimi
        chk_sql = f"""SELECT lc.user_id,
                             SUM(CASE WHEN lc.status='present' THEN 1 ELSE 0 END) AS ok_cnt,
                             SUM(CASE WHEN lc.status='away' THEN 1 ELSE 0 END) AS away_cnt,
                             SUM(CASE WHEN lc.status='missed' THEN 1 ELSE 0 END) AS missed_cnt
                      FROM location_checks lc
                      JOIN attendance a ON a.id=lc.attendance_id
                      WHERE {cond}"""
        cparams = []
        if branch_id:
            chk_sql += " AND lc.branch_id=?"
            cparams.append(branch_id)
        chk_sql += " GROUP BY lc.user_id"
        cur = await db.execute(chk_sql, cparams)
        checks = {r["user_id"]: dict(r) for r in await cur.fetchall()}
        for r in rows:
            c = checks.get(r["user_id"], {})
            r["ok_cnt"] = c.get("ok_cnt") or 0
            r["away_cnt"] = c.get("away_cnt") or 0
            r["missed_cnt"] = c.get("missed_cnt") or 0
        return rows
    finally:
        await db.close()


# Davr shartlari (SQLite sana)
_PERIOD_COND = {
    "day": "a.date = date('now','+5 hours')",
    "week": "a.date >= date('now','+5 hours','-6 days')",
    "month": "a.date >= date('now','+5 hours','-29 days')",
}


def _period_cond(period):
    return _PERIOD_COND.get(period, _PERIOD_COND["day"])


async def attendance_present_by_employee(period="day", branch_id=None):
    """Davr ichida kelgan xodimlar va ularning kelgan kunlari soni."""
    db = await _conn()
    try:
        cond = _period_cond(period)
        sql = f"""SELECT u.id AS user_id, u.tg_id, u.full_name,
                         b.name AS branch_name,
                         COUNT(DISTINCT a.date) AS days,
                         SUM(a.late) AS lates,
                         SUM(a.early) AS earlies,
                         MAX(a.date || ' ' || COALESCE(a.time,'')) AS last_seen
                  FROM attendance a
                  JOIN users u ON u.id=a.user_id
                  LEFT JOIN branches b ON b.id=a.branch_id
                  WHERE a.status='present' AND {cond}"""
        params = []
        if branch_id:
            sql += " AND a.branch_id=?"
            params.append(branch_id)
        sql += " GROUP BY u.id ORDER BY days DESC, u.full_name"
        cur = await db.execute(sql, params)
        return [dict(r) for r in await cur.fetchall()]
    finally:
        await db.close()


async def attendance_detail(period="day", branch_id=None, limit=60):
    """Davr ichidagi har bir kelish yozuvi: kelgan/ketgan vaqt, kech/erta."""
    db = await _conn()
    try:
        cond = _period_cond(period)
        sql = f"""SELECT a.*, u.full_name, b.name AS branch_name
                  FROM attendance a
                  JOIN users u ON u.id=a.user_id
                  LEFT JOIN branches b ON b.id=a.branch_id
                  WHERE a.status='present' AND {cond}"""
        params = []
        if branch_id:
            sql += " AND a.branch_id=?"
            params.append(branch_id)
        sql += " ORDER BY a.date DESC, a.time DESC"
        if limit:
            sql += f" LIMIT {int(limit)}"
        cur = await db.execute(sql, params)
        return [dict(r) for r in await cur.fetchall()]
    finally:
        await db.close()


async def attendance_late_early(period="day", branch_id=None):
    """Davr ichida kech kelgan va erta ketgan yozuvlar."""
    db = await _conn()
    try:
        cond = _period_cond(period)
        sql = f"""SELECT a.date, a.time, a.out_time, a.late, a.early,
                         u.full_name, b.name AS branch_name
                  FROM attendance a
                  JOIN users u ON u.id=a.user_id
                  LEFT JOIN branches b ON b.id=a.branch_id
                  WHERE a.status='present' AND (a.late=1 OR a.early=1) AND {cond}"""
        params = []
        if branch_id:
            sql += " AND a.branch_id=?"
            params.append(branch_id)
        sql += " ORDER BY a.date DESC, a.time DESC"
        cur = await db.execute(sql, params)
        return [dict(r) for r in await cur.fetchall()]
    finally:
        await db.close()


async def attendance_absent_today(branch_id=None):
    """Bugun hali kelmagan (yoki 'far' bo'lgan) faol xodimlar ro'yxati."""
    db = await _conn()
    try:
        sql = """SELECT ep.user_id, u.tg_id, u.full_name, ep.position,
                        b.name AS branch_name
                 FROM employee_profiles ep
                 JOIN users u ON u.id=ep.user_id
                 LEFT JOIN branches b ON b.id=ep.branch_id
                 WHERE u.id NOT IN (
                     SELECT user_id FROM attendance
                     WHERE date=date('now','+5 hours') AND status='present'
                 )"""
        params = []
        if branch_id:
            sql += " AND ep.branch_id=?"
            params.append(branch_id)
        sql += " ORDER BY u.full_name"
        cur = await db.execute(sql, params)
        return [dict(r) for r in await cur.fetchall()]
    finally:
        await db.close()


async def attendance_branch_summary(period="day"):
    """Filiallar kesimida davr ichidagi kelishlar soni."""
    db = await _conn()
    try:
        cond = _period_cond(period)
        cur = await db.execute(
            f"""SELECT COALESCE(b.name,'Filialsiz') AS name,
                       COUNT(DISTINCT a.user_id || '_' || a.date) AS check_ins,
                       COUNT(DISTINCT a.user_id) AS employees
                FROM attendance a
                LEFT JOIN branches b ON b.id=a.branch_id
                WHERE a.status='present' AND {cond}
                GROUP BY a.branch_id
                ORDER BY check_ins DESC"""
        )
        return [dict(r) for r in await cur.fetchall()]
    finally:
        await db.close()


async def attendance_history(user_id, limit=30):
    db = await _conn()
    try:
        cur = await db.execute(
            """SELECT a.*, b.name AS branch_name
               FROM attendance a
               LEFT JOIN branches b ON b.id=a.branch_id
               WHERE a.user_id=?
               ORDER BY a.id DESC LIMIT ?""",
            (user_id, limit),
        )
        return [dict(r) for r in await cur.fetchall()]
    finally:
        await db.close()


async def count_active_employees(branch_id=None):
    db = await _conn()
    try:
        if branch_id:
            cur = await db.execute(
                "SELECT COUNT(*) c FROM employee_profiles WHERE branch_id=?", (branch_id,)
            )
        else:
            cur = await db.execute("SELECT COUNT(*) c FROM employee_profiles")
        return (await cur.fetchone())["c"]
    finally:
        await db.close()


# ---------------- OYLIK TO'LOVLARI (BUXGALTER) ----------------
async def add_salary_payment(employee_user_id, period, amount, status, note, created_by):
    db = await _conn()
    try:
        cur = await db.execute(
            """INSERT INTO salary_payments
               (employee_user_id, period, amount, status, note, created_by)
               VALUES (?,?,?,?,?,?)""",
            (employee_user_id, period, amount, status, note, created_by),
        )
        await db.commit()
        return cur.lastrowid
    finally:
        await db.close()


async def list_salary_payments(employee_user_id, limit=12):
    db = await _conn()
    try:
        cur = await db.execute(
            """SELECT sp.*, u.full_name AS created_by_name
               FROM salary_payments sp
               LEFT JOIN users u ON u.id=sp.created_by
               WHERE sp.employee_user_id=?
               ORDER BY sp.id DESC LIMIT ?""",
            (employee_user_id, limit),
        )
        return [dict(r) for r in await cur.fetchall()]
    finally:
        await db.close()


async def latest_salary_payment(employee_user_id, period):
    db = await _conn()
    try:
        cur = await db.execute(
            """SELECT * FROM salary_payments
               WHERE employee_user_id=? AND period=?
               ORDER BY id DESC LIMIT 1""",
            (employee_user_id, period),
        )
        row = await cur.fetchone()
        return dict(row) if row else None
    finally:
        await db.close()


# ---------------- AVANS (oldindan to'lov) ----------------
async def advance_employee_tg_ids():
    """Avans so'rovi yuboriladigan xodimlar (employee_profiles bor va bloklanmagan)."""
    db = await _conn()
    try:
        cur = await db.execute(
            """SELECT DISTINCT u.tg_id
               FROM employee_profiles ep
               JOIN users u ON u.id=ep.user_id
               WHERE u.tg_id IS NOT NULL
                 AND COALESCE(u.blocked, 0) = 0"""
        )
        return [r["tg_id"] for r in await cur.fetchall()]
    finally:
        await db.close()


async def upsert_advance_request(user_id, period, full_name, card_number, status):
    """Xodimning shu oydagi avans so'rovini yaratadi yoki yangilaydi."""
    db = await _conn()
    try:
        await db.execute(
            """INSERT INTO advance_requests
                   (user_id, period, full_name, card_number, status)
               VALUES (?,?,?,?,?)
               ON CONFLICT(user_id, period) DO UPDATE SET
                   full_name=excluded.full_name,
                   card_number=excluded.card_number,
                   status=excluded.status,
                   updated_at=datetime('now','+5 hours')""",
            (user_id, period, full_name, card_number, status),
        )
        await db.commit()
    finally:
        await db.close()


async def get_advance_request(user_id, period):
    db = await _conn()
    try:
        cur = await db.execute(
            "SELECT * FROM advance_requests WHERE user_id=? AND period=?",
            (user_id, period),
        )
        row = await cur.fetchone()
        return dict(row) if row else None
    finally:
        await db.close()


async def set_advance_status(user_id, period, status):
    db = await _conn()
    try:
        await db.execute(
            """UPDATE advance_requests
               SET status=?, updated_at=datetime('now','+5 hours')
               WHERE user_id=? AND period=?""",
            (status, user_id, period),
        )
        await db.commit()
    finally:
        await db.close()


async def list_advances(period, status="confirmed"):
    """Avans oluvchilar ro'yxati (Excel uchun): ism, karta, filial, lavozim, telefon."""
    db = await _conn()
    try:
        cur = await db.execute(
            """SELECT ar.*, u.tg_id, u.phone,
                      ep.position, ep.role AS emp_role,
                      b.name AS branch_name
               FROM advance_requests ar
               JOIN users u ON u.id=ar.user_id
               LEFT JOIN employee_profiles ep ON ep.user_id=ar.user_id
               LEFT JOIN branches b ON b.id=ep.branch_id
               WHERE ar.period=? AND ar.status=?
               ORDER BY b.name, ar.full_name""",
            (period, status),
        )
        return [dict(r) for r in await cur.fetchall()]
    finally:
        await db.close()


async def count_advances(period, status="confirmed"):
    db = await _conn()
    try:
        cur = await db.execute(
            "SELECT COUNT(*) c FROM advance_requests WHERE period=? AND status=?",
            (period, status),
        )
        return (await cur.fetchone())["c"]
    finally:
        await db.close()


# ---------------- DAM OLISH KUNINI ALMASHTIRISH ----------------
async def add_dayoff_request(user_id, branch_id, from_day, to_day, reason):
    db = await _conn()
    try:
        cur = await db.execute(
            """INSERT INTO dayoff_requests
               (user_id, branch_id, from_day, to_day, reason)
               VALUES (?,?,?,?,?)""",
            (user_id, branch_id, from_day, to_day, reason),
        )
        await db.commit()
        return cur.lastrowid
    finally:
        await db.close()


async def get_dayoff_request(rid):
    db = await _conn()
    try:
        cur = await db.execute(
            """SELECT dr.*, u.tg_id AS user_tg, u.full_name, b.name AS branch_name
               FROM dayoff_requests dr
               JOIN users u ON u.id=dr.user_id
               LEFT JOIN branches b ON b.id=dr.branch_id
               WHERE dr.id=?""",
            (rid,),
        )
        row = await cur.fetchone()
        return dict(row) if row else None
    finally:
        await db.close()


async def list_dayoff_requests(status=None, branch_id=None, limit=30):
    db = await _conn()
    try:
        sql = """SELECT dr.*, u.tg_id AS user_tg, u.full_name, b.name AS branch_name
                 FROM dayoff_requests dr
                 JOIN users u ON u.id=dr.user_id
                 LEFT JOIN branches b ON b.id=dr.branch_id
                 WHERE 1=1"""
        params = []
        if status:
            sql += " AND dr.status=?"
            params.append(status)
        if branch_id:
            sql += " AND dr.branch_id=?"
            params.append(branch_id)
        sql += " ORDER BY dr.id DESC"
        if limit:
            sql += f" LIMIT {int(limit)}"
        cur = await db.execute(sql, params)
        return [dict(r) for r in await cur.fetchall()]
    finally:
        await db.close()


async def set_dayoff_status(rid, status, handled_by=None):
    db = await _conn()
    try:
        await db.execute(
            "UPDATE dayoff_requests SET status=?, handled_by=? WHERE id=?",
            (status, handled_by, rid),
        )
        await db.commit()
    finally:
        await db.close()


# ---------------- SINOV MUDDATI (PROBATION) ----------------
async def add_probation(data):
    db = await _conn()
    try:
        cur = await db.execute(
            """INSERT INTO probations
               (application_id, user_id, branch_id, full_name, position,
                start_date, end_date, days, kind, created_by)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                data.get("application_id"),
                data.get("user_id"),
                data.get("branch_id"),
                data.get("full_name"),
                data.get("position"),
                data.get("start_date"),
                data.get("end_date"),
                data.get("days", 15),
                data.get("kind", "trial"),
                data.get("created_by"),
            ),
        )
        await db.commit()
        return cur.lastrowid
    finally:
        await db.close()


async def get_probation(pid):
    db = await _conn()
    try:
        cur = await db.execute(
            """SELECT p.*, b.name AS branch_name, u.tg_id AS employee_tg
               FROM probations p
               LEFT JOIN branches b ON b.id=p.branch_id
               LEFT JOIN users u ON u.id=p.user_id
               WHERE p.id=?""",
            (pid,),
        )
        row = await cur.fetchone()
        return dict(row) if row else None
    finally:
        await db.close()


async def list_probations(status=None, limit=30, kind=None):
    db = await _conn()
    try:
        sql = """SELECT p.*, b.name AS branch_name, u.tg_id AS employee_tg
                 FROM probations p
                 LEFT JOIN branches b ON b.id=p.branch_id
                 LEFT JOIN users u ON u.id=p.user_id
                 WHERE 1=1"""
        params = []
        if status:
            sql += " AND p.status=?"
            params.append(status)
        if kind:
            sql += " AND p.kind=?"
            params.append(kind)
        sql += " ORDER BY p.end_date ASC, p.id DESC"
        if limit:
            sql += f" LIMIT {int(limit)}"
        cur = await db.execute(sql, params)
        return [dict(r) for r in await cur.fetchall()]
    finally:
        await db.close()


async def list_active_probations(kind=None):
    return await list_probations(status="active", limit=200, kind=kind)


async def mark_probation_flag(pid, flag):
    allowed = {"manager_notified", "hr_3day_sent", "hr_end_sent"}
    if flag not in allowed:
        raise ValueError("Ruxsat etilmagan bayroq")
    db = await _conn()
    try:
        await db.execute(f"UPDATE probations SET {flag}=1 WHERE id=?", (pid,))
        await db.commit()
    finally:
        await db.close()


async def set_probation_status(pid, status):
    db = await _conn()
    try:
        await db.execute("UPDATE probations SET status=? WHERE id=?", (status, pid))
        await db.commit()
    finally:
        await db.close()


async def branch_manager_tg_ids(branch_id):
    """Filial rahbarlarining tg_id lari (users.branch_id yoki profil bo'yicha)."""
    if not branch_id:
        return []
    db = await _conn()
    try:
        cur = await db.execute(
            """SELECT DISTINCT u.tg_id
               FROM users u
               LEFT JOIN employee_profiles ep ON ep.user_id=u.id
               WHERE u.role=? AND (u.branch_id=? OR ep.branch_id=?)""",
            (ROLE_MANAGER, branch_id, branch_id),
        )
        return [r["tg_id"] for r in await cur.fetchall()]
    finally:
        await db.close()


# ---------------- KADRLAR HARAKATI (IT paneli hisoboti) ----------------
async def add_hr_event(event_type, user_id=None, full_name=None, old_value=None,
                       new_value=None, branch_id=None, details=None, created_by=None):
    """Kadrlar harakati voqeasini yozadi (hired / left / transferred / name_changed)."""
    db = await _conn()
    try:
        await db.execute(
            """INSERT INTO hr_events
               (event_type, user_id, full_name, old_value, new_value,
                branch_id, details, created_by)
               VALUES (?,?,?,?,?,?,?,?)""",
            (event_type, user_id, full_name, old_value, new_value,
             branch_id, details, created_by),
        )
        await db.commit()
    finally:
        await db.close()


async def hr_event_counts(start_iso, end_iso=None):
    """Berilgan davr ichida har bir voqea turi sonini qaytaradi.
    start_iso <= created_at < end_iso (end_iso berilmasa — hozirgacha)."""
    db = await _conn()
    try:
        sql = ("SELECT event_type, COUNT(*) c FROM hr_events "
               "WHERE created_at >= ?")
        params = [start_iso]
        if end_iso:
            sql += " AND created_at < ?"
            params.append(end_iso)
        sql += " GROUP BY event_type"
        cur = await db.execute(sql, params)
        rows = await cur.fetchall()
        result = {"hired": 0, "left": 0, "transferred": 0, "name_changed": 0}
        for r in rows:
            result[r["event_type"]] = r["c"]
        return result
    finally:
        await db.close()


async def list_hr_events(event_type, start_iso, end_iso=None, limit=50):
    """Davr ichidagi ma'lum turdagi voqealar ro'yxati (yangidan eskiga)."""
    db = await _conn()
    try:
        sql = ("SELECT * FROM hr_events WHERE event_type=? AND created_at >= ?")
        params = [event_type, start_iso]
        if end_iso:
            sql += " AND created_at < ?"
            params.append(end_iso)
        sql += f" ORDER BY id DESC LIMIT {int(limit)}"
        cur = await db.execute(sql, params)
        return [dict(r) for r in await cur.fetchall()]
    finally:
        await db.close()


async def count_active_probations(kind=None):
    db = await _conn()
    try:
        sql = "SELECT COUNT(*) c FROM probations WHERE status='active'"
        params = []
        if kind:
            sql += " AND kind=?"
            params.append(kind)
        cur = await db.execute(sql, params)
        return (await cur.fetchone())["c"]
    finally:
        await db.close()


# ---------------- OYLIK KELISHUVI (nomzod ⇄ HR) ----------------
async def set_salary_offer(aid, amount, offer_by):
    """Arizaga oylik taklifini yozadi (pending). offer_by: 'hr' yoki 'candidate'."""
    db = await _conn()
    try:
        await db.execute(
            "UPDATE applications SET offered_salary=?, salary_offer_by=?, "
            "salary_status='pending' WHERE id=?",
            (amount, offer_by, aid),
        )
        await db.commit()
    finally:
        await db.close()


async def agree_salary(aid):
    """Joriy taklifni kelishilgan deb belgilaydi va kelishilgan summani qaytaradi."""
    db = await _conn()
    try:
        cur = await db.execute(
            "SELECT offered_salary FROM applications WHERE id=?", (aid,)
        )
        row = await cur.fetchone()
        amount = row["offered_salary"] if row else None
        await db.execute(
            "UPDATE applications SET salary_status='agreed' WHERE id=?", (aid,)
        )
        await db.commit()
        return amount
    finally:
        await db.close()


# ---------------- MAOSH OSHIRISH SO'ROVI (xodim ⇄ HR) ----------------
async def get_pending_raise_for_user(user_id):
    """Xodimning hali yopilmagan (pending) maosh so'rovini qaytaradi (bo'lmasa None)."""
    db = await _conn()
    try:
        cur = await db.execute(
            "SELECT * FROM salary_raise_requests "
            "WHERE user_id=? AND status='pending' ORDER BY id DESC LIMIT 1",
            (user_id,),
        )
        row = await cur.fetchone()
        return dict(row) if row else None
    finally:
        await db.close()


async def add_raise_request(user_id, branch_id, position, current_salary, requested_amount):
    """Yangi maosh oshirish so'rovini yaratadi (xodim taklifi). id qaytaradi."""
    db = await _conn()
    try:
        cur = await db.execute(
            "INSERT INTO salary_raise_requests "
            "(user_id, branch_id, position, current_salary, requested_amount, "
            " last_offer_by, status) VALUES (?,?,?,?,?, 'employee', 'pending')",
            (user_id, branch_id, position, current_salary, requested_amount),
        )
        await db.commit()
        return cur.lastrowid
    finally:
        await db.close()


async def get_raise_request(rid):
    """So'rovni xodim tg_id, ism va filial nomi bilan birga qaytaradi."""
    db = await _conn()
    try:
        cur = await db.execute(
            """SELECT r.*, u.tg_id AS user_tg, u.full_name, b.name AS branch_name
               FROM salary_raise_requests r
               JOIN users u ON u.id=r.user_id
               LEFT JOIN branches b ON b.id=r.branch_id
               WHERE r.id=?""",
            (rid,),
        )
        row = await cur.fetchone()
        return dict(row) if row else None
    finally:
        await db.close()


async def set_raise_offer(rid, amount, offer_by):
    """So'rovga yangi taklif yozadi. offer_by: 'employee' yoki 'hr'."""
    db = await _conn()
    try:
        if offer_by == "hr":
            await db.execute(
                "UPDATE salary_raise_requests SET offered_amount=?, last_offer_by='hr', "
                "status='pending', updated_at=datetime('now','+5 hours') WHERE id=?",
                (amount, rid),
            )
        else:
            await db.execute(
                "UPDATE salary_raise_requests SET requested_amount=?, "
                "last_offer_by='employee', status='pending', "
                "updated_at=datetime('now','+5 hours') WHERE id=?",
                (amount, rid),
            )
        await db.commit()
    finally:
        await db.close()


async def agree_raise(rid, final_amount, handled_by=None):
    """So'rovni kelishilgan deb belgilaydi va yakuniy summani yozadi."""
    db = await _conn()
    try:
        await db.execute(
            "UPDATE salary_raise_requests SET status='agreed', final_amount=?, "
            "handled_by=COALESCE(?, handled_by), updated_at=datetime('now','+5 hours') "
            "WHERE id=?",
            (final_amount, handled_by, rid),
        )
        await db.commit()
    finally:
        await db.close()


async def reject_raise(rid, reason, handled_by=None):
    """So'rovni rad etadi va sababini yozadi."""
    db = await _conn()
    try:
        await db.execute(
            "UPDATE salary_raise_requests SET status='rejected', reject_reason=?, "
            "handled_by=COALESCE(?, handled_by), updated_at=datetime('now','+5 hours') "
            "WHERE id=?",
            (reason, handled_by, rid),
        )
        await db.commit()
    finally:
        await db.close()


async def list_pending_raise_requests(limit=30):
    """HR paneli uchun ochiq (pending) maosh so'rovlari ro'yxati."""
    db = await _conn()
    try:
        cur = await db.execute(
            """SELECT r.*, u.full_name, b.name AS branch_name
               FROM salary_raise_requests r
               JOIN users u ON u.id=r.user_id
               LEFT JOIN branches b ON b.id=r.branch_id
               WHERE r.status='pending'
               ORDER BY r.id DESC LIMIT ?""",
            (limit,),
        )
        return [dict(r) for r in await cur.fetchall()]
    finally:
        await db.close()


async def rename_user(user_id, new_name):
    """Xodim ism-familiyasini o'zgartiradi. Eski ismni qaytaradi.
    users.full_name asosiy manba; aktiv sinov yozuvidagi nusxa ham yangilanadi."""
    db = await _conn()
    try:
        cur = await db.execute("SELECT full_name FROM users WHERE id=?", (user_id,))
        row = await cur.fetchone()
        old_name = row["full_name"] if row else None
        await db.execute(
            "UPDATE users SET full_name=? WHERE id=?", (new_name, user_id)
        )
        await db.execute(
            "UPDATE probations SET full_name=? WHERE user_id=? AND status='active'",
            (new_name, user_id),
        )
        await db.commit()
        return old_name
    finally:
        await db.close()


async def set_employee_branch(user_id, branch_id):
    """Xodimni boshqa filialga ko'chiradi (users va profil). Eski filialni qaytaradi."""
    db = await _conn()
    try:
        cur = await db.execute(
            "SELECT branch_id FROM employee_profiles WHERE user_id=?", (user_id,)
        )
        row = await cur.fetchone()
        old_branch = row["branch_id"] if row else None
        await db.execute(
            "UPDATE users SET branch_id=? WHERE id=?", (branch_id, user_id)
        )
        await db.execute(
            "UPDATE employee_profiles SET branch_id=?, updated_at=datetime('now','+5 hours') "
            "WHERE user_id=?",
            (branch_id, user_id),
        )
        await db.commit()
        return old_branch
    finally:
        await db.close()


async def probation_attendance_stats(user_id, start_iso, end_iso):
    """Sinov davri ichida kelgan kunlar, kechikish/erta ketishlar soni."""
    db = await _conn()
    try:
        cur = await db.execute(
            """SELECT COUNT(DISTINCT a.date) AS present_days,
                      COALESCE(SUM(a.late),0)  AS lates,
                      COALESCE(SUM(a.early),0) AS earlies
               FROM attendance a
               WHERE a.user_id=? AND a.status='present'
                 AND a.date BETWEEN ? AND ?""",
            (user_id, start_iso, end_iso),
        )
        row = await cur.fetchone()
        return dict(row) if row else {"present_days": 0, "lates": 0, "earlies": 0}
    finally:
        await db.close()
