"""/api/v1/announcements, /notifications, /users, /company."""
import json
from typing import Optional

from fastapi import APIRouter, Depends, Path, Query

from database import queries as q

from api import messaging, repo, settings
from api.core import (ApiError, Page, execute, fetch_all, fetch_one, fetch_val, iso, like,
                      not_found, now_tk, ok, parse_dt)
from api.schemas import AnnouncementCreate, CompanyPatch, NotificationCreate, UserPatch
from api.security import Principal, require

announcements = APIRouter(prefix="/announcements", tags=["Announcements"])
notifications = APIRouter(prefix="/notifications", tags=["Notifications"])
users = APIRouter(prefix="/users", tags=["Users"])
company = APIRouter(prefix="/company", tags=["Company"])


# ================= ANNOUNCEMENTS =================
@announcements.post("", status_code=201,
                    summary="E'lon yuborish (bot orqali, «Ko'rib chiqdim» statistikasi bilan)")
async def create_announcement(body: AnnouncementCreate,
                              p: Principal = Depends(require("announcements:write"))):
    target = body.target()
    if not any(target.get(k) for k in ("send_to_all", "branch_ids", "department_ids",
                                         "position_ids", "roles", "employee_ids")):
        raise ApiError(422, "validation_error",
                       "Qabul qiluvchilar ko'rsatilmagan (send_to_all yoki filtrlar).")
    scheduled = None
    if body.scheduled_at:
        dt = parse_dt(body.scheduled_at)
        if dt > now_tk():
            scheduled = dt.strftime("%Y-%m-%d %H:%M:%S")
    aid = await messaging.create_announcement(
        body.title, body.message, target, body.require_ack, scheduled,
        body.source or "api", p.key_id)
    return ok(await repo.load_announcement(aid), status=201)


@announcements.get("", summary="E'lonlar ro'yxati")
async def list_announcements(page: Page = Depends(),
                             status: Optional[str] = Query(None, pattern="^(scheduled|sending|sent|cancelled|failed)$"),
                             p: Principal = Depends(require("announcements:read"))):
    where, params = "WHERE 1=1", []
    if status:
        where += " AND status=?"
        params.append(status)
    total = await fetch_val(f"SELECT COUNT(*) FROM api_announcements {where}", tuple(params))
    ids = await fetch_all(f"SELECT id FROM api_announcements {where} ORDER BY id DESC "
                          "LIMIT ? OFFSET ?", (*params, page.limit, page.offset))
    return ok([await repo.load_announcement(r["id"]) for r in ids], page.meta(total))


@announcements.get("/{announcement_id}", summary="E'lon + yetkazish statistikasi")
async def get_announcement(announcement_id: int = Path(..., gt=0),
                           include_recipients: bool = False,
                           p: Principal = Depends(require("announcements:read"))):
    data = await repo.load_announcement(announcement_id)
    if not data:
        raise not_found("E'lon", announcement_id)
    if include_recipients:
        ann = await fetch_one("SELECT trust_notice_id FROM api_announcements WHERE id=?",
                              (announcement_id,))
        rows = await fetch_all(
            """SELECT r.user_id, r.status, r.error, r.sent_at, u.full_name,
                      tr.seen, tr.seen_at
                 FROM api_announcement_recipients r
                 LEFT JOIN users u ON u.id=r.user_id
                 LEFT JOIN trust_notice_reads tr ON tr.notice_id=? AND tr.chat_id=r.tg_id
                WHERE r.announcement_id=? ORDER BY u.full_name""",
            (ann["trust_notice_id"] or 0, announcement_id))
        data["recipients"] = [{
            "employee_id": r["user_id"], "full_name": r["full_name"],
            "delivery_status": r["status"], "error": r["error"], "sent_at": iso(r["sent_at"]),
            "acknowledged": bool(r["seen"]), "acknowledged_at": iso(r["seen_at"]),
        } for r in rows]
    return ok(data)


@announcements.post("/{announcement_id}/cancel", summary="Rejalashtirilgan e'lonni bekor qilish")
async def cancel_announcement(announcement_id: int = Path(..., gt=0),
                              p: Principal = Depends(require("announcements:write"))):
    _, n = await execute("UPDATE api_announcements SET status='cancelled' "
                         "WHERE id=? AND status='scheduled'", (announcement_id,))
    if not n:
        if not await fetch_val("SELECT id FROM api_announcements WHERE id=?", (announcement_id,)):
            raise not_found("E'lon", announcement_id)
        raise ApiError(409, "not_cancellable", "E'lon allaqachon yuborilgan yoki bekor qilingan.")
    return ok(await repo.load_announcement(announcement_id))


# ================= NOTIFICATIONS =================
def _notif(r):
    return {
        "id": r["id"], "employee_id": r["user_id"], "title": r.get("title"),
        "message": r["message"], "type": r["type"], "source": r.get("source"),
        "channel": "telegram", "status": r["status"], "attempts": r["attempts"],
        "error": r.get("error"), "created_at": iso(r["created_at"]), "sent_at": iso(r.get("sent_at")),
    }


@notifications.get("", summary="Bildirishnomalar (xodim bo'yicha filtr)")
async def list_notifications(page: Page = Depends(), employee_id: Optional[int] = None,
                             status: Optional[str] = Query(None, pattern="^(queued|sent|failed)$"),
                             type: Optional[str] = Query(None, max_length=40),
                             p: Principal = Depends(require("notifications:read"))):
    where, params = ["1=1"], []
    for col, val in (("user_id", employee_id), ("status", status), ("type", type)):
        if val is not None:
            where.append(f"{col}=?")
            params.append(val)
    w = " WHERE " + " AND ".join(where)
    total = await fetch_val("SELECT COUNT(*) FROM api_notifications" + w, tuple(params))
    rows = await fetch_all("SELECT * FROM api_notifications" + w +
                           " ORDER BY id DESC LIMIT ? OFFSET ?", (*params, page.limit, page.offset))
    return ok([_notif(r) for r in rows], page.meta(total))


@notifications.get("/{notification_id}", summary="Bitta bildirishnoma")
async def get_notification(notification_id: int = Path(..., gt=0),
                           p: Principal = Depends(require("notifications:read"))):
    r = await fetch_one("SELECT * FROM api_notifications WHERE id=?", (notification_id,))
    if not r:
        raise not_found("Bildirishnoma", notification_id)
    return ok(_notif(r))


@notifications.post("", status_code=202,
                    summary="Xodimga bot orqali bildirishnoma (navbatga qo'yiladi, retry bilan)")
async def create_notification(body: NotificationCreate,
                              p: Principal = Depends(require("notifications:write"))):
    if body.employee_id:
        row = await fetch_one(
            "SELECT u.id, u.tg_id FROM employee_profiles ep JOIN users u ON u.id=ep.user_id "
            "WHERE ep.user_id=?", (body.employee_id,))
    else:
        row = await fetch_one(
            "SELECT u.id, u.tg_id FROM employee_profiles ep JOIN users u ON u.id=ep.user_id "
            "WHERE u.tg_id=?", (body.telegram_id,))
    if not row:
        raise ApiError(422, "invalid_reference", "Xodim topilmadi.")
    nid, _ = await execute(
        "INSERT INTO api_notifications (user_id, tg_id, title, message, type, source, api_key_id) "
        "VALUES (?,?,?,?,?,?,?)",
        (row["id"], row["tg_id"], body.title, body.message, body.type, body.source or "api",
         p.key_id))
    return ok(_notif(await fetch_one("SELECT * FROM api_notifications WHERE id=?", (nid,))),
              status=202)


# ================= USERS (Telegram foydalanuvchilari) =================
def _user(r):
    return {
        "id": r["id"], "telegram_id": r["tg_id"], "full_name": r.get("full_name"),
        "telegram_name": r.get("tg_name"), "username": r.get("username"),
        "phone": r.get("phone"), "role": r.get("role"),
        "role_label": repo.ROLE_LABELS.get(r.get("role")),
        "is_employee": bool(r.get("is_employee")),
        "branch_id": r.get("branch_id"), "language": r.get("lang"),
        "blocked": bool(r.get("blocked")), "created_at": iso(r.get("created_at")),
    }


USER_SELECT = ("SELECT u.*, EXISTS(SELECT 1 FROM employee_profiles ep WHERE ep.user_id=u.id) "
               "AS is_employee FROM users u")


@users.get("", summary="Bot foydalanuvchilari (nomzodlar ham)")
async def list_users(page: Page = Depends(), search: Optional[str] = Query(None, max_length=100),
                     role: Optional[str] = Query(None, max_length=20),
                     blocked: Optional[bool] = None,
                     p: Principal = Depends(require("users:read"))):
    where, params = ["1=1"], []
    if search:
        where.append("(pylower(COALESCE(u.full_name,'')) LIKE ? OR pylower(COALESCE(u.username,'')) "
                     "LIKE ? OR COALESCE(u.phone,'') LIKE ? OR CAST(u.tg_id AS TEXT) LIKE ?)")
        params += [like(search.lstrip("@"))] * 4
    if role:
        where.append("u.role=?")
        params.append(role)
    if blocked is not None:
        where.append("COALESCE(u.blocked,0)=?")
        params.append(1 if blocked else 0)
    w = " WHERE " + " AND ".join(where)
    total = await fetch_val("SELECT COUNT(*) FROM users u" + w, tuple(params))
    rows = await fetch_all(USER_SELECT + w + " ORDER BY u.id DESC LIMIT ? OFFSET ?",
                           (*params, page.limit, page.offset))
    return ok([_user(r) for r in rows], page.meta(total))


@users.get("/by-telegram/{telegram_id}", summary="Telegram ID bo'yicha foydalanuvchi")
async def user_by_tg(telegram_id: int = Path(..., gt=0), p: Principal = Depends(require("users:read"))):
    r = await fetch_one(USER_SELECT + " WHERE u.tg_id=?", (telegram_id,))
    if not r:
        raise not_found("Foydalanuvchi", telegram_id)
    return ok(_user(r))


@users.get("/{user_id}", summary="Bitta foydalanuvchi")
async def get_user(user_id: int = Path(..., gt=0), p: Principal = Depends(require("users:read"))):
    r = await fetch_one(USER_SELECT + " WHERE u.id=?", (user_id,))
    if not r:
        raise not_found("Foydalanuvchi", user_id)
    return ok(_user(r))


@users.patch("/{user_id}", summary="Bloklash / blokdan chiqarish (botdagi admin amali)")
async def patch_user(body: UserPatch, user_id: int = Path(..., gt=0),
                     p: Principal = Depends(require("users:write"))):
    from config import SUPER_ADMINS
    r = await fetch_one("SELECT * FROM users WHERE id=?", (user_id,))
    if not r:
        raise not_found("Foydalanuvchi", user_id)
    if r["tg_id"] in SUPER_ADMINS or r["role"] == "admin":
        raise ApiError(409, "protected_account", "Administratorni bloklab bo'lmaydi.")
    await q.set_user_blocked(r["tg_id"], body.blocked)
    await q.add_log(None, p.actor, "api_blok" if body.blocked else "api_blokdan_chiqarish",
                    f"user#{user_id}")
    return ok(_user(await fetch_one(USER_SELECT + " WHERE u.id=?", (user_id,))))


# ================= COMPANY =================
async def _company():
    raw = await q.get_setting("api_company")
    info = json.loads(raw) if raw else {}
    counts = await fetch_one(
        """SELECT (SELECT COUNT(*) FROM employee_profiles) AS employees,
                  (SELECT COUNT(*) FROM branches) AS branches,
                  (SELECT COUNT(*) FROM positions) AS positions,
                  (SELECT COUNT(*) FROM api_departments) AS departments""")
    return {
        "name": info.get("name") or settings.COMPANY_NAME,
        "legal_name": info.get("legal_name"),
        "phone": info.get("phone"), "email": info.get("email"),
        "website": info.get("website"), "address": info.get("address"),
        "tax_id": info.get("tax_id"),
        "timezone": settings.TIMEZONE, "utc_offset": "+05:00", "currency": "UZS",
        "languages": ["uz", "ru"],
        "stats": counts,
    }


@company.get("", summary="Kompaniya ma'lumotlari")
async def get_company(p: Principal = Depends(require("company:read"))):
    return ok(await _company())


@company.patch("", summary="Kompaniya ma'lumotlarini yangilash")
async def patch_company(body: CompanyPatch, p: Principal = Depends(require("company:write"))):
    raw = await q.get_setting("api_company")
    info = json.loads(raw) if raw else {}
    info.update(body.model_dump(exclude_unset=True))
    await q.set_setting("api_company", json.dumps(info, ensure_ascii=False))
    return ok(await _company())
