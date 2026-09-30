"""/api/v1/employees — xodimlar."""
from typing import Optional

from fastapi import APIRouter, Depends, Path, Query
from fastapi.responses import Response

from api import repo, services
from api.core import ApiError, Page, fetch_all, fetch_val, iso, like, not_found, ok, order_by
from api.schemas import EmployeeCreate, EmployeePatch, EmployeeReplace
from api.security import Principal, require

router = APIRouter(prefix="/employees", tags=["Employees"])

SORT = {"id": "ep.user_id", "full_name": "u.full_name", "created_at": "ep.created_at",
        "hired_at": "ep.created_at", "updated_at": "ep.updated_at", "branch_id": "ep.branch_id",
        "position": "ep.position", "role": "ep.role"}


async def _out(uid, p: Principal):
    data = await repo.load_employee(uid, include_salary=p.has("employees:salary"),
                                    include_sensitive=p.has("employees:sensitive"))
    if not data:
        raise not_found("Xodim", uid)
    return data


@router.get("", summary="Xodimlar ro'yxati (sahifalash, qidiruv, filtr, saralash)")
async def list_employees(
    page: Page = Depends(),
    search: Optional[str] = Query(None, max_length=100, description="Ism, telefon, username, lavozim, ID"),
    branch_id: Optional[int] = None,
    department_id: Optional[int] = None,
    position_id: Optional[int] = None,
    position: Optional[str] = Query(None, max_length=120),
    role: Optional[str] = Query(None, max_length=20),
    status: Optional[str] = Query(None, pattern="^(active|blocked)$"),
    employment_status: Optional[str] = Query(None, pattern="^(regular|trial|learner)$"),
    telegram_id: Optional[int] = None,
    external_source: Optional[str] = Query(None, max_length=40),
    external_id: Optional[str] = Query(None, max_length=120),
    hired_from: Optional[str] = Query(None, description="YYYY-MM-DD"),
    hired_to: Optional[str] = Query(None, description="YYYY-MM-DD"),
    updated_since: Optional[str] = Query(None, description="YYYY-MM-DD[ HH:MM:SS]"),
    sort: Optional[str] = Query(None, description="Masalan: full_name,-hired_at"),
    p: Principal = Depends(require("employees:read")),
):
    where, params = ["1=1"], []
    if search:
        s = search.strip().lstrip("@")
        cond = ("(pylower(COALESCE(u.full_name,'')) LIKE ? OR pylower(COALESCE(u.username,'')) LIKE ? "
                "OR COALESCE(u.phone,'') LIKE ? OR pylower(COALESCE(ep.position,'')) LIKE ?")
        params += [like(s)] * 4
        if s.isdigit():
            cond += " OR u.id=? OR u.tg_id=?"
            params += [int(s), int(s)]
        where.append(cond + ")")
    for col, val in (("ep.branch_id", branch_id), ("m.department_id", department_id),
                     ("ep.role", role), ("u.tg_id", telegram_id), ("ep.position", position)):
        if val is not None:
            where.append(f"{col}=?")
            params.append(val)
    if position_id is not None:
        where.append("ep.position=(SELECT name FROM positions WHERE id=?)")
        params.append(position_id)
    if status:
        where.append("COALESCE(u.blocked,0)=?")
        params.append(1 if status == "blocked" else 0)
    if employment_status:
        where.append("COALESCE(ep.emp_status,'regular')=?")
        params.append(employment_status)
    if external_id:
        if not external_source:
            raise ApiError(400, "invalid_filter", "external_id bilan external_source ham kerak.")
        where.append("ep.user_id IN (SELECT entity_id FROM api_external_ids WHERE "
                     "entity_type='employee' AND source=? AND external_id=?)")
        params += [external_source, external_id]
    if hired_from:
        where.append("date(ep.created_at)>=date(?)")
        params.append(hired_from)
    if hired_to:
        where.append("date(ep.created_at)<=date(?)")
        params.append(hired_to)
    if updated_since:
        where.append("COALESCE(ep.updated_at, ep.created_at)>=?")
        params.append(updated_since)
    w = " WHERE " + " AND ".join(where)
    base_from = repo.EMPLOYEE_SELECT.split("FROM employee_profiles", 1)[1]
    total = await fetch_val("SELECT COUNT(*) FROM employee_profiles" + base_from + w, tuple(params))
    rows = await fetch_all(
        repo.EMPLOYEE_SELECT + w + f" ORDER BY {order_by(sort, SORT, 'u.full_name ASC')}"
        " LIMIT ? OFFSET ?", (*params, page.limit, page.offset))
    data = await repo.serialize_employees(rows, p.has("employees:salary"),
                                          p.has("employees:sensitive"))
    return ok(data, page.meta(total))


@router.get("/dismissed", summary="Ishdan bo'shatilganlar arxivi (dismissed_employees)")
async def list_dismissed(page: Page = Depends(),
                         search: Optional[str] = Query(None, max_length=100),
                         branch_id: Optional[int] = None,
                         p: Principal = Depends(require("employees:read"))):
    where, params = ["1=1"], []
    if search:
        where.append("(pylower(COALESCE(full_name,'')) LIKE ? OR COALESCE(phone,'') LIKE ?)")
        params += [like(search)] * 2
    if branch_id:
        where.append("branch_id=?")
        params.append(branch_id)
    w = " WHERE " + " AND ".join(where)
    total = await fetch_val("SELECT COUNT(*) FROM dismissed_employees" + w, tuple(params))
    rows = await fetch_all(
        "SELECT * FROM dismissed_employees" + w + " ORDER BY id DESC LIMIT ? OFFSET ?",
        (*params, page.limit, page.offset))
    data = [{
        "id": r["id"], "employee_id": r["user_id"], "telegram_id": r["tg_id"],
        "full_name": r["full_name"], "phone": r["phone"],
        "branch": {"id": r["branch_id"], "name": r["branch_name"]} if r["branch_id"] else None,
        "position": r["position"], "role": r["role"], "reason": r["reason"],
        "monthly_salary": r["monthly_salary"] if p.has("employees:salary") else None,
        "dismissed_at": iso(r["dismissed_at"]), "rehired": bool(r["rehired"]),
        "rehired_at": iso(r["rehired_at"]),
    } for r in rows]
    return ok(data, page.meta(total))


@router.get("/by-telegram/{telegram_id}", summary="Telegram ID bo'yicha xodim")
async def by_telegram(telegram_id: int = Path(..., gt=0),
                      p: Principal = Depends(require("employees:read"))):
    uid = await fetch_val(
        "SELECT ep.user_id FROM employee_profiles ep JOIN users u ON u.id=ep.user_id "
        "WHERE u.tg_id=?", (telegram_id,))
    if not uid:
        raise not_found("Xodim", telegram_id)
    return ok(await _out(uid, p))


@router.get("/by-external/{source}/{external_id}", summary="Tashqi ID bo'yicha xodim")
async def by_external(source: str = Path(..., pattern=r"^[a-z0-9_\-]{1,40}$"),
                      external_id: str = Path(..., max_length=120),
                      p: Principal = Depends(require("employees:read"))):
    uid = await repo.find_by_external("employee", source, external_id)
    if not uid:
        raise not_found("Xodim", external_id)
    return ok(await _out(uid, p))


@router.get("/{employee_id}", summary="Bitta xodim")
async def get_employee(employee_id: int = Path(..., gt=0),
                       p: Principal = Depends(require("employees:read"))):
    return ok(await _out(employee_id, p))


@router.get("/{employee_id}/photo", summary="Xodim rasmi (Telegram fayl proksi)",
            responses={200: {"content": {"image/jpeg": {}}}})
async def employee_photo(employee_id: int = Path(..., gt=0),
                         p: Principal = Depends(require("employees:read"))):
    fid = await fetch_val("SELECT photo_file_id FROM employee_profiles WHERE user_id=?",
                          (employee_id,))
    if not fid:
        raise not_found("Rasm", employee_id)
    from api import telegram
    try:
        content, name = await telegram.download_file(fid)
    except Exception:
        raise ApiError(502, "telegram_unavailable", "Rasmni Telegram dan olib bo'lmadi.")
    media = "image/png" if name.lower().endswith(".png") else "image/jpeg"
    return Response(content=content, media_type=media,
                    headers={"Cache-Control": "private, max-age=3600"})


def _payload(body, p: Principal):
    data = body.model_dump(exclude_unset=True, exclude={"first_name", "last_name"})
    if body.full_name:
        data["full_name"] = body.full_name
    if "monthly_salary" in data and not p.has("employees:salary"):
        raise ApiError(403, "insufficient_scope", "monthly_salary uchun ruxsat yo'q.",
                       {"missing": ["employees:salary"]})
    return data


@router.post("", status_code=201, summary="Xodim yaratish (botdagi tasdiqlash oqimi bilan bir xil)")
async def create_employee(body: EmployeeCreate, p: Principal = Depends(require("employees:write"))):
    data = _payload(body, p)
    data["notify"] = body.notify
    uid = await services.create_employee(data, p)
    return ok(await _out(uid, p), status=201)


@router.put("/{employee_id}", summary="Xodimni to'liq almashtirish")
async def replace_employee(body: EmployeeReplace, employee_id: int = Path(..., gt=0),
                           p: Principal = Depends(require("employees:write"))):
    await services.update_employee(employee_id, _payload(body, p), p, replace=True)
    return ok(await _out(employee_id, p))


@router.patch("/{employee_id}", summary="Xodimni qisman yangilash")
async def patch_employee(body: EmployeePatch, employee_id: int = Path(..., gt=0),
                         p: Principal = Depends(require("employees:write"))):
    await services.update_employee(employee_id, _payload(body, p), p, replace=False)
    return ok(await _out(employee_id, p))


@router.delete("/{employee_id}", summary="Ishdan bo'shatish (arxivga ko'chiriladi)")
async def delete_employee(employee_id: int = Path(..., gt=0),
                          reason: Optional[str] = Query(None, max_length=500),
                          notify: bool = Query(False, description="Xodimga bot orqali xabar"),
                          p: Principal = Depends(require("employees:write"))):
    await services.dismiss_employee(employee_id, reason, p, notify=notify)
    return ok({"id": employee_id, "dismissed": True})
