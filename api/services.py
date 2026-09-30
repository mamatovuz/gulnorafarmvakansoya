"""Yozish amallari — botdagi biznes qoidalari bilan bir xil.

Xodim:
  * yaratish  = botdagi «xodim so'rovini tasdiqlash» (staffreg.py): users.role/branch,
                haqiqiy ism (name_locked=1), employee_profiles, hr_events('hired'), audit_logs
  * filial    = set_employee_branch + hr_events('transferred', eski -> yangi filial)
  * ism       = rename + name_locked + hr_events('name_changed') (IT paneli hisoboti)
  * o'chirish = botdagi «🚫 Ishdan bo'shatish»: hr_events('left'), dismissed_employees
                arxivi, ochiq sinovlar bekor, profil o'chadi, rol -> candidate
Har bir amal bitta tranzaksiyada bajariladi.
"""
from config import SUPER_ADMINS
from database import queries as q

from api.core import ApiError, connect, fetch_one, now_sql, not_found
from api.repo import ASSIGNABLE_ROLES, set_external_id

PROFILE_FIELDS = {
    # API nomi -> employee_profiles ustuni
    "position": "position",
    "birth_date": "birth_date",
    "address": "address",
    "parent_phone": "parent_phone",
    "work_hours": "work_hours",
    "rest_day": "rest_day",
    "shift": "shift",
    "education": "education",
    "experience": "since",
    "extra_info": "extra_info",
    "uniform_status": "uniform_status",
    "employment_status": "emp_status",
    "monthly_salary": "monthly_salary",
}
PROFILE_DEFAULTS = {"uniform_status": "unknown", "emp_status": "regular"}


def normalize_phone(value):
    """Bot qoidasi: +998XXXXXXXXX. 998.. / 9 xonali raqam ham qabul qilinadi."""
    from utils import normalize_phone as strict, phone_from_contact
    if value in (None, ""):
        return None
    text = str(value).strip()
    fixed = strict(text) or phone_from_contact(text.replace(" ", "").replace("-", ""))
    if not fixed:
        raise ApiError(422, "validation_error", "Telefon formati noto'g'ri (+998XXXXXXXXX).",
                       {"field": "phone", "value": text})
    return fixed


async def _exists(db, sql, params):
    cur = await db.execute(sql, params)
    return await cur.fetchone()


async def _check_refs(db, data):
    if data.get("branch_id") is not None and not await _exists(
            db, "SELECT 1 FROM branches WHERE id=?", (data["branch_id"],)):
        raise ApiError(422, "invalid_reference", "Filial topilmadi.",
                       {"field": "branch_id", "value": data["branch_id"]})
    if data.get("department_id") is not None and not await _exists(
            db, "SELECT 1 FROM api_departments WHERE id=?", (data["department_id"],)):
        raise ApiError(422, "invalid_reference", "Bo'lim topilmadi.",
                       {"field": "department_id", "value": data["department_id"]})
    if data.get("manager_id") is not None and not await _exists(
            db, "SELECT 1 FROM employee_profiles WHERE user_id=?", (data["manager_id"],)):
        raise ApiError(422, "invalid_reference", "Rahbar (xodim) topilmadi.",
                       {"field": "manager_id", "value": data["manager_id"]})
    if data.get("position_id") is not None:
        row = await _exists(db, "SELECT name FROM positions WHERE id=?", (data["position_id"],))
        if not row:
            raise ApiError(422, "invalid_reference", "Lavozim topilmadi.",
                           {"field": "position_id", "value": data["position_id"]})
        data["position"] = row[0]
    if data.get("role") is not None and data["role"] not in ASSIGNABLE_ROLES:
        raise ApiError(422, "validation_error", "Rol noto'g'ri.",
                       {"field": "role", "allowed": ASSIGNABLE_ROLES})


async def _log(db, actor, action, details):
    await db.execute(
        "INSERT INTO audit_logs (tg_id, actor_name, action, details) VALUES (?,?,?,?)",
        (None, actor, action, details))


async def _hr_event(db, event_type, user_id, full_name, branch_id=None,
                    old_value=None, new_value=None, details=None):
    await db.execute(
        """INSERT INTO hr_events (event_type, user_id, full_name, old_value, new_value,
               branch_id, details, created_by) VALUES (?,?,?,?,?,?,?,NULL)""",
        (event_type, user_id, full_name, old_value, new_value, branch_id, details))


async def _branch_name(db, bid):
    if not bid:
        return None
    row = await _exists(db, "SELECT name FROM branches WHERE id=?", (bid,))
    return row[0] if row else None


async def _upsert_meta(db, user_id, data, replace=False):
    keys = [k for k in ("department_id", "manager_id") if k in data or replace]
    if not keys:
        return
    await db.execute("INSERT OR IGNORE INTO api_employee_meta (user_id) VALUES (?)", (user_id,))
    sets = ", ".join(
        f"{'manager_user_id' if k == 'manager_id' else k}=?" for k in keys)
    await db.execute(
        f"UPDATE api_employee_meta SET {sets}, updated_at=? WHERE user_id=?",
        (*[data.get(k) for k in keys], now_sql(), user_id))


async def _set_external_ids(db, entity, entity_id, external_ids):
    for source, ext in (external_ids or {}).items():
        if source and ext not in (None, ""):
            await set_external_id(db, entity, entity_id, source, ext)


# ---------------- EMPLOYEE ----------------
async def create_employee(data, principal):
    tg_id = int(data["telegram_id"])
    if tg_id in SUPER_ADMINS:
        raise ApiError(409, "protected_account",
                       "Bosh administrator hisobini API orqali xodimga aylantirib bo'lmaydi.")
    data["phone"] = normalize_phone(data.get("phone"))
    role = data.get("role") or "employee"
    data["role"] = role
    full_name = data["full_name"].strip()

    async with connect() as db:
        await _check_refs(db, data)
        for source, ext in (data.get("external_ids") or {}).items():
            row = await _exists(
                db, "SELECT entity_id FROM api_external_ids WHERE entity_type='employee' "
                    "AND source=? AND external_id=?", (source, str(ext)))
            if row:
                raise ApiError(409, "duplicate", "Bu external_id bilan xodim allaqachon mavjud.",
                               {"existing_id": row[0], "source": source, "external_id": ext})
        user = await _exists(db, "SELECT id, role FROM users WHERE tg_id=?", (tg_id,))
        if user:
            uid = user[0]
            if user[1] == "admin":
                raise ApiError(409, "protected_account",
                               "Administrator hisobini API orqali o'zgartirib bo'lmaydi.")
            if await _exists(db, "SELECT 1 FROM employee_profiles WHERE user_id=?", (uid,)):
                raise ApiError(409, "duplicate",
                               "Bu Telegram ID bilan xodim allaqachon mavjud.",
                               {"existing_id": uid, "telegram_id": tg_id})
            await db.execute(
                "UPDATE users SET role=?, branch_id=?, full_name=?, name_locked=1, "
                "phone=COALESCE(?, phone) WHERE id=?",
                (role, data.get("branch_id"), full_name, data["phone"], uid))
        else:
            cur = await db.execute(
                "INSERT INTO users (tg_id, full_name, role, branch_id, phone, name_locked) "
                "VALUES (?,?,?,?,?,1)",
                (tg_id, full_name, role, data.get("branch_id"), data["phone"]))
            uid = cur.lastrowid

        cols = {"user_id": uid, "role": role, "branch_id": data.get("branch_id")}
        for api_name, col in PROFILE_FIELDS.items():
            if data.get(api_name) is not None:
                cols[col] = data[api_name]
        for col, default in PROFILE_DEFAULTS.items():
            cols.setdefault(col, default)
        names = ", ".join(cols)
        await db.execute(
            f"INSERT INTO employee_profiles ({names}) VALUES ({','.join('?' * len(cols))})",
            tuple(cols.values()))
        await _upsert_meta(db, uid, {k: data[k] for k in ("department_id", "manager_id")
                                     if data.get(k) is not None})
        await _set_external_ids(db, "employee", uid, data.get("external_ids"))
        await _hr_event(db, "hired", uid, full_name, data.get("branch_id"),
                        details=f"{principal.actor}")
        await _log(db, principal.actor, "api_hodim_qoshildi", f"user#{uid}: {full_name}")
        if data.get("notify", True):
            await db.execute(
                "INSERT INTO api_notifications (user_id, tg_id, title, message, type, source, api_key_id) "
                "VALUES (?,?,?,?,?,?,?)",
                (uid, tg_id, "🎉 Tabriklaymiz!",
                 "Siz Gulnora Farm hodimi sifatida tasdiqlandingiz.\n"
                 "Yangilangan menyuni ko'rish uchun /start bosing.",
                 "employee_hired", "system", principal.key_id))
        await db.commit()
    return uid


async def update_employee(uid, data, principal, replace=False):
    """PATCH (replace=False) — faqat yuborilgan maydonlar; PUT (replace=True) —
    yuborilmagan tahrirlanadigan maydonlar tozalanadi (NULL / standart qiymat)."""
    if "phone" in data:
        data["phone"] = normalize_phone(data.get("phone"))
    async with connect() as db:
        cur = await db.execute(
            """SELECT ep.*, u.full_name, u.phone AS u_phone, u.role AS user_role, u.tg_id
                 FROM employee_profiles ep JOIN users u ON u.id=ep.user_id
                WHERE ep.user_id=?""", (uid,))
        row = await cur.fetchone()
        if not row:
            raise not_found("Xodim", uid)
        cur_ = dict(row)
        if cur_["user_role"] == "admin" or cur_["tg_id"] in SUPER_ADMINS:
            if data.get("role") not in (None, "admin") or "status" in data:
                raise ApiError(409, "protected_account",
                               "Administrator rolini/holatini API orqali o'zgartirib bo'lmaydi.")
            data.pop("role", None)
        await _check_refs(db, data)
        changes = []

        # --- ism ---
        new_name = (data.get("full_name") or "").strip()
        if new_name and new_name != cur_["full_name"]:
            await db.execute("UPDATE users SET full_name=?, name_locked=1 WHERE id=?",
                             (new_name, uid))
            await db.execute(
                "UPDATE probations SET full_name=? WHERE user_id=? AND status='active'",
                (new_name, uid))
            await _hr_event(db, "name_changed", uid, new_name, cur_["branch_id"],
                            cur_["full_name"], new_name, principal.actor)
            changes.append("full_name")
        name_now = new_name or cur_["full_name"]

        # --- telefon ---
        if "phone" in data or replace:
            await db.execute("UPDATE users SET phone=? WHERE id=?", (data.get("phone"), uid))
            changes.append("phone")

        # --- rol ---
        if data.get("role") and data["role"] != cur_["role"]:
            await db.execute("UPDATE users SET role=? WHERE id=?", (data["role"], uid))
            await db.execute("UPDATE employee_profiles SET role=? WHERE user_id=?",
                             (data["role"], uid))
            changes.append("role")

        # --- filial ---
        if "branch_id" in data and data["branch_id"] != cur_["branch_id"]:
            old_b = await _branch_name(db, cur_["branch_id"])
            new_b = await _branch_name(db, data["branch_id"])
            await db.execute("UPDATE users SET branch_id=? WHERE id=?", (data["branch_id"], uid))
            await db.execute("UPDATE employee_profiles SET branch_id=? WHERE user_id=?",
                             (data["branch_id"], uid))
            await _hr_event(db, "transferred", uid, name_now, data["branch_id"],
                            old_b, new_b, principal.actor)
            changes.append("branch_id")

        # --- holat (active / blocked) ---
        if "status" in data and data["status"]:
            await db.execute("UPDATE users SET blocked=? WHERE id=?",
                             (1 if data["status"] == "blocked" else 0, uid))
            changes.append("status")

        # --- profil maydonlari ---
        sets, params = [], []
        for api_name, col in PROFILE_FIELDS.items():
            if api_name == "monthly_salary" and not principal.has("employees:salary"):
                continue
            if api_name in data:
                value = data[api_name]
            elif replace:
                value = None
            else:
                continue
            if value is None and col in PROFILE_DEFAULTS:
                value = PROFILE_DEFAULTS[col]
            sets.append(f"{col}=?")
            params.append(value)
            changes.append(api_name)
        if sets:
            await db.execute(
                f"UPDATE employee_profiles SET {', '.join(sets)}, updated_at=? WHERE user_id=?",
                (*params, now_sql(), uid))
        else:
            await db.execute("UPDATE employee_profiles SET updated_at=? WHERE user_id=?",
                             (now_sql(), uid))

        await _upsert_meta(db, uid, data, replace=replace)
        await _set_external_ids(db, "employee", uid, data.get("external_ids"))
        if changes:
            await _log(db, principal.actor, "api_hodim_ozgartirildi",
                       f"user#{uid}: {', '.join(sorted(set(changes)))}")
        await db.commit()


async def dismiss_employee(uid, reason, principal, notify=False):
    reason = reason or f"{principal.actor} orqali ishdan bo'shatildi"
    async with connect() as db:
        cur = await db.execute(
            """SELECT ep.branch_id, u.full_name, u.tg_id, u.role FROM employee_profiles ep
                 JOIN users u ON u.id=ep.user_id WHERE ep.user_id=?""", (uid,))
        row = await cur.fetchone()
        if not row:
            raise not_found("Xodim", uid)
        branch_id, name, tg_id, role = row
        if role == "admin" or tg_id in SUPER_ADMINS:
            raise ApiError(409, "protected_account",
                           "Administratorni API orqali ishdan bo'shatib bo'lmaydi.")
        await _hr_event(db, "left", uid, name, branch_id, details=reason)
        # Botning o'z yordamchilari (shu tranzaksiyada)
        await q._archive_dismissed(db, uid, reason, None)
        await q._cancel_user_probations(db, uid)
        await db.execute("DELETE FROM employee_profiles WHERE user_id=?", (uid,))
        await db.execute("UPDATE users SET role='candidate', branch_id=NULL WHERE id=?", (uid,))
        await db.execute("DELETE FROM api_employee_meta WHERE user_id=?", (uid,))
        await _log(db, principal.actor, "api_ishdan_boshatdi", f"user#{uid}: {name}")
        if notify and tg_id:
            await db.execute(
                "INSERT INTO api_notifications (user_id, tg_id, title, message, type, source, api_key_id) "
                "VALUES (?,?,?,?,?,?,?)",
                (uid, tg_id, "Ma'lumot", "Siz Gulnora Farm xodimlari ro'yxatidan chiqarildingiz.",
                 "employee_dismissed", "system", principal.key_id))
        await db.commit()


# ---------------- BRANCH ----------------
BRANCH_COLS = {"name": "name", "address": "address", "phone": "phone",
               "latitude": "latitude", "longitude": "longitude", "radius": "radius",
               "working_hours": "work_hours"}


async def save_branch(data, principal, bid=None, replace=False):
    async with connect() as db:
        if data.get("code"):
            row = await _exists(db, "SELECT branch_id FROM api_branch_meta WHERE code=?",
                                (data["code"],))
            if row and row[0] != bid:
                raise ApiError(409, "duplicate", "Bu kod bilan filial mavjud.",
                               {"existing_id": row[0], "code": data["code"]})
        if bid is None:
            cols = {c: data.get(k) for k, c in BRANCH_COLS.items() if data.get(k) is not None}
            cols.setdefault("radius", 150)
            cur = await db.execute(
                f"INSERT INTO branches ({', '.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                tuple(cols.values()))
            bid = cur.lastrowid
            await _log(db, principal.actor, "api_filial_qoshildi", f"#{bid}: {data.get('name')}")
        else:
            if not await _exists(db, "SELECT 1 FROM branches WHERE id=?", (bid,)):
                raise not_found("Filial", bid)
            sets, params = [], []
            for k, c in BRANCH_COLS.items():
                if k in data or (replace and k != "name"):
                    v = data.get(k)
                    if c == "radius" and v is None:
                        v = 150
                    sets.append(f"{c}=?")
                    params.append(v)
            if sets:
                await db.execute(f"UPDATE branches SET {', '.join(sets)} WHERE id=?",
                                 (*params, bid))
            await _log(db, principal.actor, "api_filial_ozgartirildi", f"#{bid}")
        if "code" in data or "status" in data or replace:
            await db.execute("INSERT OR IGNORE INTO api_branch_meta (branch_id) VALUES (?)", (bid,))
            sets, params = [], []
            if "code" in data or replace:
                sets.append("code=?")
                params.append(data.get("code"))
            if "status" in data or replace:
                sets.append("status=?")
                params.append(data.get("status") or "active")
            await db.execute(
                f"UPDATE api_branch_meta SET {', '.join(sets)}, updated_at=? WHERE branch_id=?",
                (*params, now_sql(), bid))
        await _set_external_ids(db, "branch", bid, data.get("external_ids"))
        await db.commit()
    return bid


async def delete_branch(bid, principal):
    async with connect() as db:
        if not await _exists(db, "SELECT 1 FROM branches WHERE id=?", (bid,)):
            raise not_found("Filial", bid)
        cur = await db.execute("SELECT COUNT(*) FROM employee_profiles WHERE branch_id=?", (bid,))
        n = (await cur.fetchone())[0]
        if n:
            raise ApiError(409, "branch_not_empty",
                           "Filialda xodimlar bor. Avval ularni boshqa filialga o'tkazing "
                           "yoki filialni status=inactive qiling.", {"employee_count": n})
        await db.execute("DELETE FROM branches WHERE id=?", (bid,))
        await db.execute("DELETE FROM api_branch_meta WHERE branch_id=?", (bid,))
        await _log(db, principal.actor, "api_filial_ochirildi", f"#{bid}")
        await db.commit()


# ---------------- POSITION ----------------
async def save_position(data, principal, pid=None, replace=False):
    async with connect() as db:
        if data.get("code"):
            row = await _exists(db, "SELECT position_id FROM api_position_meta WHERE code=?",
                                (data["code"],))
            if row and row[0] != pid:
                raise ApiError(409, "duplicate", "Bu kod bilan lavozim mavjud.",
                               {"existing_id": row[0]})
        if data.get("department_id") is not None and not await _exists(
                db, "SELECT 1 FROM api_departments WHERE id=?", (data["department_id"],)):
            raise ApiError(422, "invalid_reference", "Bo'lim topilmadi.",
                           {"field": "department_id"})
        name = (data.get("name") or "").strip() or None
        if name:
            row = await _exists(db, "SELECT id FROM positions WHERE name=?", (name,))
            if row and row[0] != pid:
                raise ApiError(409, "duplicate", "Bu nomli lavozim mavjud.",
                               {"existing_id": row[0], "name": name})
        if pid is None:
            cur = await db.execute("INSERT INTO positions (name) VALUES (?)", (name,))
            pid = cur.lastrowid
        else:
            cur = await db.execute("SELECT name FROM positions WHERE id=?", (pid,))
            row = await cur.fetchone()
            if not row:
                raise not_found("Lavozim", pid)
            if name and name != row[0]:
                await db.execute("UPDATE positions SET name=? WHERE id=?", (name, pid))
                # Xodimlarda lavozim matn sifatida saqlanadi — ular ham yangilanadi
                await db.execute(
                    "UPDATE employee_profiles SET position=?, updated_at=? WHERE position=?",
                    (name, now_sql(), row[0]))
        meta_keys = [k for k in ("code", "description", "department_id", "status")
                     if k in data or replace]
        if meta_keys:
            await db.execute("INSERT OR IGNORE INTO api_position_meta (position_id) VALUES (?)",
                             (pid,))
            vals = [data.get(k) if k != "status" else (data.get(k) or "active") for k in meta_keys]
            await db.execute(
                f"UPDATE api_position_meta SET {', '.join(k + '=?' for k in meta_keys)}, "
                f"updated_at=? WHERE position_id=?", (*vals, now_sql(), pid))
        await _set_external_ids(db, "position", pid, data.get("external_ids"))
        await _log(db, principal.actor, "api_lavozim_saqlandi", f"#{pid}: {name or ''}")
        await db.commit()
    return pid


async def delete_position(pid, principal):
    async with connect() as db:
        cur = await db.execute("SELECT name FROM positions WHERE id=?", (pid,))
        row = await cur.fetchone()
        if not row:
            raise not_found("Lavozim", pid)
        cur = await db.execute("SELECT COUNT(*) FROM employee_profiles WHERE position=?", (row[0],))
        n = (await cur.fetchone())[0]
        if n:
            raise ApiError(409, "position_in_use", "Bu lavozimda xodimlar bor.",
                           {"employee_count": n})
        await db.execute("DELETE FROM positions WHERE id=?", (pid,))
        await db.execute("DELETE FROM api_position_meta WHERE position_id=?", (pid,))
        await _log(db, principal.actor, "api_lavozim_ochirildi", f"#{pid}: {row[0]}")
        await db.commit()


# ---------------- DEPARTMENT ----------------
DEPT_COLS = ["name", "code", "description", "parent_id", "head_user_id", "status"]


async def save_department(data, principal, did=None, replace=False):
    if "head_id" in data:
        data["head_user_id"] = data.pop("head_id")
    async with connect() as db:
        if data.get("code"):
            row = await _exists(db, "SELECT id FROM api_departments WHERE code=?", (data["code"],))
            if row and row[0] != did:
                raise ApiError(409, "duplicate", "Bu kod bilan bo'lim mavjud.",
                               {"existing_id": row[0]})
        if data.get("parent_id") is not None:
            if did is not None and data["parent_id"] == did:
                raise ApiError(422, "validation_error", "Bo'lim o'ziga ota bo'la olmaydi.")
            if not await _exists(db, "SELECT 1 FROM api_departments WHERE id=?",
                                 (data["parent_id"],)):
                raise ApiError(422, "invalid_reference", "Ota bo'lim topilmadi.",
                               {"field": "parent_id"})
        if data.get("head_user_id") is not None and not await _exists(
                db, "SELECT 1 FROM employee_profiles WHERE user_id=?", (data["head_user_id"],)):
            raise ApiError(422, "invalid_reference", "Bo'lim rahbari (xodim) topilmadi.",
                           {"field": "head_id"})
        if did is None:
            cols = {c: data.get(c) for c in DEPT_COLS if data.get(c) is not None}
            cols.setdefault("status", "active")
            cur = await db.execute(
                f"INSERT INTO api_departments ({', '.join(cols)}) "
                f"VALUES ({','.join('?' * len(cols))})", tuple(cols.values()))
            did = cur.lastrowid
        else:
            if not await _exists(db, "SELECT 1 FROM api_departments WHERE id=?", (did,)):
                raise not_found("Bo'lim", did)
            keys = [c for c in DEPT_COLS if c in data or (replace and c != "name")]
            if keys:
                vals = [data.get(k) if k != "status" else (data.get(k) or "active") for k in keys]
                await db.execute(
                    f"UPDATE api_departments SET {', '.join(k + '=?' for k in keys)}, "
                    f"updated_at=? WHERE id=?", (*vals, now_sql(), did))
        await _set_external_ids(db, "department", did, data.get("external_ids"))
        await _log(db, principal.actor, "api_bolim_saqlandi", f"#{did}")
        await db.commit()
    return did


async def delete_department(did, principal):
    async with connect() as db:
        if not await _exists(db, "SELECT 1 FROM api_departments WHERE id=?", (did,)):
            raise not_found("Bo'lim", did)
        cur = await db.execute(
            "SELECT COUNT(*) FROM api_employee_meta WHERE department_id=?", (did,))
        n = (await cur.fetchone())[0]
        cur = await db.execute("SELECT COUNT(*) FROM api_departments WHERE parent_id=?", (did,))
        children = (await cur.fetchone())[0]
        if n or children:
            raise ApiError(409, "department_in_use", "Bo'limda xodimlar yoki ichki bo'limlar bor.",
                           {"employee_count": n, "child_departments": children})
        await db.execute("DELETE FROM api_departments WHERE id=?", (did,))
        await db.execute("UPDATE api_position_meta SET department_id=NULL WHERE department_id=?",
                         (did,))
        await _log(db, principal.actor, "api_bolim_ochirildi", f"#{did}")
        await db.commit()


async def employee_exists(uid):
    return await fetch_one("SELECT user_id FROM employee_profiles WHERE user_id=?", (uid,))
