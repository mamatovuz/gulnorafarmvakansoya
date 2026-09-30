"""/api/v1/branches, /departments, /positions — tashkiliy tuzilma."""
from typing import Optional

from fastapi import APIRouter, Depends, Path, Query

from api import repo, services
from api.core import Page, fetch_all, fetch_val, like, not_found, ok, order_by
from api.schemas import (BranchCreate, BranchFields, BranchReplace, DepartmentCreate,
                         DepartmentFields, PositionCreate, PositionFields)
from api.security import Principal, require

branches = APIRouter(prefix="/branches", tags=["Branches"])
departments = APIRouter(prefix="/departments", tags=["Departments"])
positions = APIRouter(prefix="/positions", tags=["Positions"])


def _dump(body):
    return body.model_dump(exclude_unset=True)


# ================= BRANCHES =================
@branches.get("", summary="Filiallar ro'yxati")
async def list_branches(page: Page = Depends(),
                        search: Optional[str] = Query(None, max_length=100),
                        status: Optional[str] = Query(None, pattern="^(active|inactive)$"),
                        code: Optional[str] = Query(None, max_length=40),
                        sort: Optional[str] = None,
                        p: Principal = Depends(require("branches:read"))):
    where, params = ["1=1"], []
    if search:
        where.append("(pylower(b.name) LIKE ? OR pylower(COALESCE(b.address,'')) LIKE ?)")
        params += [like(search)] * 2
    if status:
        where.append("COALESCE(bm.status,'active')=?")
        params.append(status)
    if code:
        where.append("bm.code=?")
        params.append(code)
    w = " WHERE " + " AND ".join(where)
    total = await fetch_val(
        "SELECT COUNT(*) FROM branches b LEFT JOIN api_branch_meta bm ON bm.branch_id=b.id" + w,
        tuple(params))
    rows = await fetch_all(
        repo.BRANCH_SELECT + w + " ORDER BY " +
        order_by(sort, {"id": "b.id", "name": "b.name", "created_at": "b.created_at"}, "b.name")
        + " LIMIT ? OFFSET ?", (*params, page.limit, page.offset))
    return ok(await repo.serialize_branches(rows), page.meta(total))


@branches.get("/{branch_id}", summary="Bitta filial")
async def get_branch(branch_id: int = Path(..., gt=0),
                     p: Principal = Depends(require("branches:read"))):
    data = await repo.load_branch(branch_id)
    if not data:
        raise not_found("Filial", branch_id)
    return ok(data)


@branches.post("", status_code=201, summary="Filial yaratish")
async def create_branch(body: BranchCreate, p: Principal = Depends(require("branches:write"))):
    bid = await services.save_branch(_dump(body), p)
    return ok(await repo.load_branch(bid), status=201)


@branches.put("/{branch_id}", summary="Filialni to'liq almashtirish")
async def replace_branch(body: BranchReplace, branch_id: int = Path(..., gt=0),
                         p: Principal = Depends(require("branches:write"))):
    await services.save_branch(_dump(body), p, bid=branch_id, replace=True)
    return ok(await repo.load_branch(branch_id))


@branches.patch("/{branch_id}", summary="Filialni qisman yangilash")
async def patch_branch(body: BranchFields, branch_id: int = Path(..., gt=0),
                       p: Principal = Depends(require("branches:write"))):
    await services.save_branch(_dump(body), p, bid=branch_id)
    return ok(await repo.load_branch(branch_id))


@branches.delete("/{branch_id}", summary="Filialni o'chirish (xodimsiz bo'lsa)")
async def delete_branch(branch_id: int = Path(..., gt=0),
                        p: Principal = Depends(require("branches:write"))):
    await services.delete_branch(branch_id, p)
    return ok({"id": branch_id, "deleted": True})


# ================= DEPARTMENTS =================
@departments.get("", summary="Bo'limlar ro'yxati")
async def list_departments(page: Page = Depends(),
                           search: Optional[str] = Query(None, max_length=100),
                           parent_id: Optional[int] = None,
                           status: Optional[str] = Query(None, pattern="^(active|inactive)$"),
                           sort: Optional[str] = None,
                           p: Principal = Depends(require("departments:read"))):
    where, params = ["1=1"], []
    if search:
        where.append("(pylower(d.name) LIKE ? OR pylower(COALESCE(d.code,'')) LIKE ?)")
        params += [like(search)] * 2
    if parent_id is not None:
        where.append("d.parent_id=?")
        params.append(parent_id)
    if status:
        where.append("d.status=?")
        params.append(status)
    w = " WHERE " + " AND ".join(where)
    total = await fetch_val("SELECT COUNT(*) FROM api_departments d" + w, tuple(params))
    rows = await fetch_all(
        repo.DEPARTMENT_SELECT + w + " ORDER BY " +
        order_by(sort, {"id": "d.id", "name": "d.name", "created_at": "d.created_at"}, "d.name")
        + " LIMIT ? OFFSET ?", (*params, page.limit, page.offset))
    return ok(await repo.serialize_departments(rows), page.meta(total))


@departments.get("/{department_id}", summary="Bitta bo'lim")
async def get_department(department_id: int = Path(..., gt=0),
                         p: Principal = Depends(require("departments:read"))):
    data = await repo.load_department(department_id)
    if not data:
        raise not_found("Bo'lim", department_id)
    return ok(data)


@departments.post("", status_code=201, summary="Bo'lim yaratish")
async def create_department(body: DepartmentCreate,
                            p: Principal = Depends(require("departments:write"))):
    did = await services.save_department(_dump(body), p)
    return ok(await repo.load_department(did), status=201)


@departments.put("/{department_id}", summary="Bo'limni to'liq almashtirish")
async def replace_department(body: DepartmentCreate, department_id: int = Path(..., gt=0),
                             p: Principal = Depends(require("departments:write"))):
    await services.save_department(_dump(body), p, did=department_id, replace=True)
    return ok(await repo.load_department(department_id))


@departments.patch("/{department_id}", summary="Bo'limni qisman yangilash")
async def patch_department(body: DepartmentFields, department_id: int = Path(..., gt=0),
                           p: Principal = Depends(require("departments:write"))):
    await services.save_department(_dump(body), p, did=department_id)
    return ok(await repo.load_department(department_id))


@departments.delete("/{department_id}", summary="Bo'limni o'chirish (bo'sh bo'lsa)")
async def delete_department(department_id: int = Path(..., gt=0),
                            p: Principal = Depends(require("departments:write"))):
    await services.delete_department(department_id, p)
    return ok({"id": department_id, "deleted": True})


# ================= POSITIONS =================
@positions.get("", summary="Lavozimlar (botdagi «yo'nalishlar») ro'yxati")
async def list_positions(page: Page = Depends(),
                         search: Optional[str] = Query(None, max_length=100),
                         department_id: Optional[int] = None,
                         status: Optional[str] = Query(None, pattern="^(active|inactive)$"),
                         sort: Optional[str] = None,
                         p: Principal = Depends(require("positions:read"))):
    where, params = ["1=1"], []
    if search:
        where.append("pylower(p.name) LIKE ?")
        params.append(like(search))
    if department_id is not None:
        where.append("pm.department_id=?")
        params.append(department_id)
    if status:
        where.append("COALESCE(pm.status,'active')=?")
        params.append(status)
    w = " WHERE " + " AND ".join(where)
    total = await fetch_val(
        "SELECT COUNT(*) FROM positions p LEFT JOIN api_position_meta pm ON pm.position_id=p.id" + w,
        tuple(params))
    rows = await fetch_all(
        repo.POSITION_SELECT + w + " ORDER BY " +
        order_by(sort, {"id": "p.id", "name": "p.name", "created_at": "p.created_at"}, "p.id")
        + " LIMIT ? OFFSET ?", (*params, page.limit, page.offset))
    return ok(await repo.serialize_positions(rows), page.meta(total))


@positions.get("/{position_id}", summary="Bitta lavozim")
async def get_position(position_id: int = Path(..., gt=0),
                       p: Principal = Depends(require("positions:read"))):
    data = await repo.load_position(position_id)
    if not data:
        raise not_found("Lavozim", position_id)
    return ok(data)


@positions.post("", status_code=201, summary="Lavozim yaratish (bot ariza/anketasida ham ko'rinadi)")
async def create_position(body: PositionCreate, p: Principal = Depends(require("positions:write"))):
    pid = await services.save_position(_dump(body), p)
    return ok(await repo.load_position(pid), status=201)


@positions.put("/{position_id}", summary="Lavozimni to'liq almashtirish")
async def replace_position(body: PositionCreate, position_id: int = Path(..., gt=0),
                           p: Principal = Depends(require("positions:write"))):
    await services.save_position(_dump(body), p, pid=position_id, replace=True)
    return ok(await repo.load_position(position_id))


@positions.patch("/{position_id}",
                 summary="Lavozimni qisman yangilash (nom o'zgarsa xodimlardagi lavozim ham yangilanadi)")
async def patch_position(body: PositionFields, position_id: int = Path(..., gt=0),
                         p: Principal = Depends(require("positions:write"))):
    await services.save_position(_dump(body), p, pid=position_id)
    return ok(await repo.load_position(position_id))


@positions.delete("/{position_id}", summary="Lavozimni o'chirish (xodimsiz bo'lsa)")
async def delete_position(position_id: int = Path(..., gt=0),
                          p: Principal = Depends(require("positions:write"))):
    await services.delete_position(position_id, p)
    return ok({"id": position_id, "deleted": True})
