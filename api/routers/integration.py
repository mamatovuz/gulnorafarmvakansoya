"""/api/v1/integration/*, /webhooks, /api-keys — tashqi tizim (Staffora) integratsiyasi."""
import hashlib
import hmac
import json
import secrets
import time
from typing import Optional
from urllib.parse import parse_qsl, urlparse

from fastapi import APIRouter, Depends, Path, Query, Request
from pydantic import ValidationError

from api import API_VERSION, repo, services, settings, webhooks
from api.core import (ApiError, Page, connect, execute, fetch_all, fetch_one, fetch_val, iso,
                      not_found, now_sql, ok)
from api.schemas import (ApiKeyCreate, BranchCreate, BranchFields, DepartmentCreate,
                         DepartmentFields, EmployeeCreate, EmployeePatch, ExternalIdLink,
                         PositionCreate, PositionFields, SyncRequest, TelegramVerify,
                         WebhookCreate, WebhookPatch)
from api.security import (SCOPES, STAFFORA_DEFAULT_SCOPES, Principal, create_api_key,
                          get_api_key, list_api_keys, public_key, require, revoke_api_key,
                          rotate_api_key)

integration = APIRouter(prefix="/integration", tags=["Integration"])
hooks = APIRouter(prefix="/webhooks", tags=["Webhooks"])
keys = APIRouter(prefix="/api-keys", tags=["API keys"])

_STARTED = time.time()


# ================= INFO / HEALTH =================
@integration.get("/info", summary="Integratsiya imkoniyatlari (ruxsatlar, hodisalar, resurslar)")
async def info(p: Principal = Depends(require("integration:read"))):
    return ok({
        "name": "Gulnora Farm HR Bot API",
        "source": settings.EVENT_SOURCE,
        "api_version": "v1",
        "build": API_VERSION,
        "timezone": settings.TIMEZONE,
        "auth": {"type": "bearer", "header": "Authorization: Bearer <api_key>",
                 "key_prefix": "gfk_"},
        "your_key": {"name": p.name, "scopes": sorted(p.scopes)},
        "scopes": SCOPES,
        "recommended_scopes": {"staffora": STAFFORA_DEFAULT_SCOPES},
        "resources": ["employees", "branches", "departments", "positions", "schedules",
                      "attendance", "leaves", "announcements", "notifications", "users",
                      "company"],
        "webhook_events": webhooks.EVENT_TYPES,
        "webhook_signature": "X-Webhook-Signature: t=<unix>,v1=hex(HMAC_SHA256(secret, '<t>.<body>'))",
        "idempotency": "Idempotency-Key header (POST/PUT/PATCH/DELETE), 24 soat",
        "external_id_entities": repo.ENTITY_TYPES,
        "pagination": {"params": ["page", "limit"], "max_limit": 200},
    })


@integration.get("/health", summary="Holat tekshiruvi (autentifikatsiyasiz: /api/v1/health)")
async def health_detailed(p: Principal = Depends(require("integration:read"))):
    return ok(await _health(True))


async def _health(detailed=False):
    t0 = time.perf_counter()
    try:
        await fetch_val("SELECT 1")
        db_ok = True
    except Exception:
        db_ok = False
    data = {"status": "ok" if db_ok else "degraded", "database": "ok" if db_ok else "error",
            "db_latency_ms": round((time.perf_counter() - t0) * 1000, 2),
            "uptime_seconds": int(time.time() - _STARTED), "version": API_VERSION}
    if detailed and db_ok:
        data["queues"] = await fetch_one(
            """SELECT (SELECT COUNT(*) FROM api_events WHERE processed=0) AS pending_events,
                      (SELECT COUNT(*) FROM api_webhook_deliveries WHERE status IN ('pending','failed')) AS pending_deliveries,
                      (SELECT COUNT(*) FROM api_webhook_deliveries WHERE status='dead') AS dead_deliveries,
                      (SELECT COUNT(*) FROM api_notifications WHERE status='queued') AS queued_notifications,
                      (SELECT COUNT(*) FROM api_announcements WHERE status='scheduled') AS scheduled_announcements""")
        data["workers_enabled"] = settings.API_WORKERS_ENABLED
        data["telegram_send_enabled"] = settings.API_TELEGRAM_SEND_ENABLED
    return data


# ================= CHANGES FEED (pull) =================
@integration.get("/changes", summary="O'zgarishlar lentasi (kursor bilan; webhook'ga zaxira)")
async def changes(since_id: int = Query(0, ge=0, description="Oldingi javobdagi next_cursor"),
                  limit: int = Query(100, ge=1, le=500),
                  entity_type: Optional[str] = Query(None, max_length=20),
                  p: Principal = Depends(require("integration:read"))):
    sql = "SELECT * FROM api_events WHERE id>?"
    params = [since_id]
    if entity_type:
        sql += " AND entity_type=?"
        params.append(entity_type)
    rows = await fetch_all(sql + " ORDER BY id LIMIT ?", (*params, limit))
    items = []
    for ev in rows:
        data = json.loads(ev["payload"]) if ev.get("payload") else await webhooks.build_data(ev)
        if ev["entity_type"] == "employee" and isinstance(data, dict) and "salary" in data \
                and not p.has("employees:salary"):
            data.pop("salary", None)
        items.append(webhooks.envelope(ev, data))
    nxt = rows[-1]["id"] if rows else since_id
    return ok(items, {"next_cursor": nxt, "has_more": len(rows) == limit})


# ================= EXTERNAL IDS =================
@integration.get("/external-ids", summary="Tashqi ID xaritasi")
async def list_external(page: Page = Depends(),
                        entity_type: Optional[str] = Query(None, max_length=20),
                        source: Optional[str] = Query(None, max_length=40),
                        p: Principal = Depends(require("integration:read"))):
    where, params = ["1=1"], []
    for col, val in (("entity_type", entity_type), ("source", source)):
        if val:
            where.append(f"{col}=?")
            params.append(val)
    w = " WHERE " + " AND ".join(where)
    total = await fetch_val("SELECT COUNT(*) FROM api_external_ids" + w, tuple(params))
    rows = await fetch_all("SELECT * FROM api_external_ids" + w + " ORDER BY id LIMIT ? OFFSET ?",
                           (*params, page.limit, page.offset))
    return ok([{"entity_type": r["entity_type"], "entity_id": r["entity_id"],
                "source": r["source"], "external_id": r["external_id"],
                "updated_at": iso(r["updated_at"])} for r in rows], page.meta(total))


_ENTITY_TABLE = {"employee": ("employee_profiles", "user_id"), "branch": ("branches", "id"),
                 "department": ("api_departments", "id"), "position": ("positions", "id"),
                 "attendance": ("attendance", "id"), "leave": ("dayoff_requests", "id")}


@integration.put("/external-ids", summary="Tashqi ID ni bog'lash (upsert)")
async def link_external(body: ExternalIdLink, p: Principal = Depends(require("integration:write"))):
    table, col = _ENTITY_TABLE[body.entity_type]
    if not await fetch_val(f"SELECT {col} FROM {table} WHERE {col}=?", (body.entity_id,)):
        raise not_found(body.entity_type, body.entity_id)
    async with connect() as db:
        await repo.set_external_id(db, body.entity_type, body.entity_id, body.source,
                                   body.external_id)
        await db.commit()
    return ok(body.model_dump())


@integration.delete("/external-ids/{entity_type}/{source}/{external_id}",
                    summary="Tashqi ID bog'lanishini o'chirish")
async def unlink_external(entity_type: str = Path(..., max_length=20),
                          source: str = Path(..., max_length=40),
                          external_id: str = Path(..., max_length=120),
                          p: Principal = Depends(require("integration:write"))):
    _, n = await execute("DELETE FROM api_external_ids WHERE entity_type=? AND source=? "
                         "AND external_id=?", (entity_type, source, external_id))
    if not n:
        raise not_found("Bog'lanish", external_id)
    return ok({"deleted": True})


# ================= SYNC (ommaviy upsert) =================
_SYNC = {
    # entity: (create model, patch model, natural key finder, save fn, delete fn)
    "department": (DepartmentCreate, DepartmentFields),
    "branch": (BranchCreate, BranchFields),
    "position": (PositionCreate, PositionFields),
    "employee": (EmployeeCreate, EmployeePatch),
}
_REF_FIELDS = {"branch_external_id": ("branch", "branch_id"),
               "department_external_id": ("department", "department_id"),
               "position_external_id": ("position", "position_id"),
               "manager_external_id": ("employee", "manager_id"),
               "parent_external_id": ("department", "parent_id"),
               "head_external_id": ("employee", "head_id")}


async def _natural_match(entity, item):
    if entity == "employee" and item.get("telegram_id"):
        return await fetch_val(
            "SELECT ep.user_id FROM employee_profiles ep JOIN users u ON u.id=ep.user_id "
            "WHERE u.tg_id=?", (item["telegram_id"],))
    if entity == "branch":
        if item.get("code"):
            bid = await fetch_val("SELECT branch_id FROM api_branch_meta WHERE code=?", (item["code"],))
            if bid:
                return bid
        if item.get("name"):
            return await fetch_val("SELECT id FROM branches WHERE name=?", (item["name"],))
    if entity == "position" and item.get("name"):
        return await fetch_val("SELECT id FROM positions WHERE name=?", (item["name"],))
    if entity == "department":
        if item.get("code"):
            return await fetch_val("SELECT id FROM api_departments WHERE code=?", (item["code"],))
        if item.get("name"):
            return await fetch_val("SELECT id FROM api_departments WHERE name=?", (item["name"],))
    return None


async def _save(entity, data, p, eid=None):
    if entity == "employee":
        if eid is None:
            return await services.create_employee(data, p)
        await services.update_employee(eid, data, p)
        return eid
    fn = {"branch": services.save_branch, "position": services.save_position,
          "department": services.save_department}[entity]
    if entity == "branch":
        return await fn(data, p, bid=eid)
    if entity == "position":
        return await fn(data, p, pid=eid)
    return await fn(data, p, did=eid)


async def _delete(entity, eid, p):
    if entity == "employee":
        await services.dismiss_employee(eid, None, p)
    elif entity == "branch":
        await services.delete_branch(eid, p)
    elif entity == "position":
        await services.delete_position(eid, p)
    else:
        await services.delete_department(eid, p)


async def sync_item(entity, raw, source, p, dry_run=False):
    item = dict(raw)
    ext = item.pop("external_id", None)
    deleted = bool(item.pop("deleted", False))
    result = {"entity": entity, "external_id": ext}
    try:
        for ref, (ref_entity, field) in _REF_FIELDS.items():
            if ref in item:
                ref_val = item.pop(ref)
                if ref_val is None:
                    item[field] = None
                    continue
                rid = await repo.find_by_external(ref_entity, source, ref_val)
                if not rid:
                    raise ApiError(422, "invalid_reference",
                                   f"{ref_entity} topilmadi (external_id={ref_val}).",
                                   {"field": ref})
                item[field] = rid
        eid = await repo.find_by_external(entity, source, ext) if ext else None
        matched_by = "external_id" if eid else None
        if not eid:
            eid = await _natural_match(entity, item)
            matched_by = "natural_key" if eid else None
        if ext:
            item["external_ids"] = {**(item.get("external_ids") or {}), source: ext}
        if deleted:
            if not eid:
                return {**result, "action": "skipped", "reason": "not_found"}
            if not dry_run:
                await _delete(entity, eid, p)
            return {**result, "id": eid, "action": "deleted"}
        create_model, patch_model = _SYNC[entity]
        if eid:
            item.pop("telegram_id", None)
            item.pop("notify", None)
            model = patch_model(**item)
            action = "updated"
        else:
            if entity == "employee":
                item.setdefault("notify", False)
            model = create_model(**item)
            action = "created"
        data = model.model_dump(exclude_unset=True, exclude={"first_name", "last_name"})
        if getattr(model, "full_name", None):
            data["full_name"] = model.full_name
        if entity == "employee" and "notify" in item:
            data["notify"] = item["notify"]
        if "monthly_salary" in data and not p.has("employees:salary"):
            data.pop("monthly_salary")
        if dry_run:
            return {**result, "id": eid, "action": action, "matched_by": matched_by,
                    "dry_run": True}
        new_id = await _save(entity, data, p, eid)
        return {**result, "id": new_id, "action": action, "matched_by": matched_by}
    except ValidationError as e:
        return {**result, "action": "error",
                "error": {"code": "validation_error", "message": "Ma'lumot noto'g'ri.",
                          "details": json.loads(e.json(include_url=False, include_input=False))}}
    except ApiError as e:
        return {**result, "action": "error",
                "error": {"code": e.code, "message": e.message, "details": e.details}}


@integration.post("/sync", summary="Ommaviy upsert: departments → branches → positions → employees")
async def sync(body: SyncRequest, p: Principal = Depends(require("integration:write"))):
    need = {"branches": "branches:write", "departments": "departments:write",
            "positions": "positions:write", "employees": "employees:write"}
    missing = [s for k, s in need.items() if getattr(body, k) and not p.has(s)]
    if missing:
        raise ApiError(403, "insufficient_scope", "Sync uchun ruxsat yetarli emas.",
                       {"missing": missing})
    results = {}
    for key, entity in (("departments", "department"), ("branches", "branch"),
                        ("positions", "position"), ("employees", "employee")):
        items = getattr(body, key)
        results[key] = [await sync_item(entity, it, body.source, p, body.dry_run) for it in items]
    summary = {}
    for key, rows in results.items():
        for r in rows:
            summary.setdefault(key, {}).setdefault(r["action"], 0)
            summary[key][r["action"]] += 1
    return ok(results, {"summary": summary, "source": body.source, "dry_run": body.dry_run})


# ================= KIRUVCHI WEBHOOK (Staffora -> bot) =================
_INBOUND_MAP = {"employee": "employee", "branch": "branch", "department": "department",
                "position": "position"}


@integration.post("/webhook", summary="Staffora dan kiruvchi webhook (HMAC imzo bilan)",
                  description="Header: `X-Webhook-Signature: t=<unix>,v1=<hex>` "
                              "(secret = INTEGRATION_INBOUND_SECRET). Body: "
                              "`{id, event, data}`. Event: `<entity>.created|updated|deleted`. "
                              "`data.external_id` majburiy. Bir xil `id` qayta kelsa — takrorlanmaydi.")
async def inbound_webhook(request: Request):
    secret = settings.INTEGRATION_INBOUND_SECRET
    if not secret:
        raise ApiError(503, "not_configured", "INTEGRATION_INBOUND_SECRET sozlanmagan.")
    raw = (await request.body()).decode("utf-8", "replace")
    if not webhooks.verify_signature(secret, request.headers.get("x-webhook-signature"), raw):
        raise ApiError(401, "invalid_signature", "Webhook imzosi noto'g'ri yoki eskirgan.")
    try:
        body = json.loads(raw)
        event_id = str(body["id"])[:120]
        event = str(body["event"])
        data = dict(body.get("data") or {})
    except (ValueError, KeyError, TypeError):
        raise ApiError(400, "invalid_payload", "Body: {id, event, data} bo'lishi kerak.")
    source = str(body.get("source") or "staffora").lower()[:40]
    async with connect() as db:
        cur = await db.execute(
            "INSERT OR IGNORE INTO api_inbound_events (source, event_id, event_type, payload) "
            "VALUES (?,?,?,?)", (source, event_id, event, raw[:100000]))
        await db.commit()
        if cur.rowcount == 0:
            prev = await (await db.execute(
                "SELECT status, result FROM api_inbound_events WHERE source=? AND event_id=?",
                (source, event_id))).fetchone()
            return ok({"duplicate": True, "status": prev[0],
                       "result": json.loads(prev[1]) if prev[1] else None})
    entity, _, action = event.partition(".")
    principal = Principal(key_id=0, name=f"{source}-webhook", scopes=set(STAFFORA_DEFAULT_SCOPES))
    if entity not in _INBOUND_MAP or action not in ("created", "updated", "deleted"):
        status, result = "ignored", {"reason": "unsupported_event"}
    else:
        if action == "deleted":
            data["deleted"] = True
        result = await sync_item(_INBOUND_MAP[entity], data, source, principal)
        status = "failed" if result.get("action") == "error" else "processed"
    await execute("UPDATE api_inbound_events SET status=?, result=?, processed_at=? "
                  "WHERE source=? AND event_id=?",
                  (status, json.dumps(result, ensure_ascii=False, default=str), now_sql(),
                   source, event_id))
    if status == "failed":
        raise ApiError(422, "processing_failed", "Hodisani qayta ishlab bo'lmadi.", result)
    return ok({"status": status, "result": result})


# ================= TELEGRAM MINI APP IDENTITY =================
def verify_init_data(init_data, bot_token, max_age):
    """Telegram WebApp initData ni server tomonda tekshiradi (rasmiy algoritm)."""
    pairs = dict(parse_qsl(init_data, keep_blank_values=True, strict_parsing=False))
    received = pairs.pop("hash", None)
    if not received:
        return None
    check = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    calc = hmac.new(secret_key, check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calc, received):
        return None
    try:
        auth_date = int(pairs.get("auth_date", "0"))
    except ValueError:
        return None
    if max_age and time.time() - auth_date > max_age:
        return None
    try:
        user = json.loads(pairs.get("user") or "{}")
    except ValueError:
        return None
    return {"user": user, "auth_date": auth_date}


@integration.post("/telegram/verify",
                  summary="Telegram Mini App initData ni tekshirib, xodimni aniqlash",
                  description="Frontend yuborgan telegram_id ga ishonilmaydi — faqat bot token bilan "
                              "imzolangan initData tekshiriladi.")
async def telegram_verify(body: TelegramVerify, p: Principal = Depends(require("employees:read"))):
    from config import BOT_TOKEN
    res = verify_init_data(body.init_data, BOT_TOKEN, settings.TELEGRAM_INIT_DATA_MAX_AGE)
    if not res or not res["user"].get("id"):
        raise ApiError(401, "invalid_init_data", "Telegram initData noto'g'ri yoki eskirgan.")
    tg_id = int(res["user"]["id"])
    uid = await fetch_val("SELECT ep.user_id FROM employee_profiles ep JOIN users u "
                          "ON u.id=ep.user_id WHERE u.tg_id=?", (tg_id,))
    emp = await repo.load_employee(uid, include_salary=p.has("employees:salary")) if uid else None
    return ok({"verified": True, "telegram_user": {
        "id": tg_id, "first_name": res["user"].get("first_name"),
        "last_name": res["user"].get("last_name"), "username": res["user"].get("username"),
        "language_code": res["user"].get("language_code")},
        "auth_date": res["auth_date"], "is_employee": bool(emp), "employee": emp})


# ================= WEBHOOK OBUNALARI =================
def _is_internal_host(host):
    import ipaddress
    host = (host or "").strip("[]").lower()
    if host in ("localhost",) or host.endswith((".localhost", ".internal", ".local")):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved         or ip.is_multicast or ip.is_unspecified


def _check_url(url):
    u = urlparse(url)
    allowed = ("https",) if settings.WEBHOOK_REQUIRE_HTTPS else ("http", "https")
    if u.scheme not in allowed or not u.hostname:
        raise ApiError(422, "validation_error", "Webhook URL noto'g'ri.",
                       {"field": "url", "allowed_schemes": list(allowed)})
    # Productionda ichki tarmoqqa (SSRF) webhook yuborishga yo'l qo'yilmaydi
    if settings.WEBHOOK_REQUIRE_HTTPS and _is_internal_host(u.hostname):
        raise ApiError(422, "validation_error", "Ichki/localhost manzilga webhook ruxsat etilmaydi.",
                       {"field": "url"})


def _check_events(events):
    valid = set(webhooks.EVENT_TYPES) | {"*"} | {e.split(".")[0] + ".*" for e in webhooks.EVENT_TYPES}
    bad = [e for e in events if e not in valid]
    if bad or not events:
        raise ApiError(422, "validation_error", "Noma'lum hodisa turi.",
                       {"invalid": bad, "allowed": webhooks.EVENT_TYPES})


@hooks.get("", summary="Webhook obunalari")
async def list_hooks(p: Principal = Depends(require("webhooks:read"))):
    return ok([webhooks.public_webhook(h) for h in
               await fetch_all("SELECT * FROM api_webhooks ORDER BY id")])


@hooks.post("", status_code=201, summary="Webhook obunasi yaratish (secret FAQAT bir marta qaytadi)")
async def create_hook(body: WebhookCreate, p: Principal = Depends(require("webhooks:write"))):
    _check_url(body.url)
    _check_events(body.events)
    if body.include_salary and not p.has("employees:salary"):
        raise ApiError(403, "insufficient_scope", "include_salary uchun employees:salary kerak.")
    secret = "whsec_" + secrets.token_urlsafe(32)
    hid, _ = await execute(
        "INSERT INTO api_webhooks (url, description, events, secret, include_salary, active, "
        "api_key_id) VALUES (?,?,?,?,?,?,?)",
        (body.url, body.description, json.dumps(body.events), secret,
         1 if body.include_salary else 0, 1 if body.active else 0, p.key_id))
    h = await fetch_one("SELECT * FROM api_webhooks WHERE id=?", (hid,))
    return ok(webhooks.public_webhook(h, reveal_secret=True), status=201)


async def _hook(hid):
    h = await fetch_one("SELECT * FROM api_webhooks WHERE id=?", (hid,))
    if not h:
        raise not_found("Webhook", hid)
    return h


@hooks.get("/{webhook_id}", summary="Bitta obuna")
async def get_hook(webhook_id: int = Path(..., gt=0), p: Principal = Depends(require("webhooks:read"))):
    return ok(webhooks.public_webhook(await _hook(webhook_id)))


@hooks.patch("/{webhook_id}", summary="Obunani yangilash")
async def patch_hook(body: WebhookPatch, webhook_id: int = Path(..., gt=0),
                     p: Principal = Depends(require("webhooks:write"))):
    await _hook(webhook_id)
    data = body.model_dump(exclude_unset=True)
    if "url" in data:
        _check_url(data["url"])
    if "events" in data:
        _check_events(data["events"])
        data["events"] = json.dumps(data["events"])
    if data.get("include_salary") and not p.has("employees:salary"):
        raise ApiError(403, "insufficient_scope", "include_salary uchun employees:salary kerak.")
    for k in ("include_salary", "active"):
        if k in data:
            data[k] = 1 if data[k] else 0
    if data:
        await execute(f"UPDATE api_webhooks SET {', '.join(k + '=?' for k in data)}, updated_at=? "
                      "WHERE id=?", (*data.values(), now_sql(), webhook_id))
    return ok(webhooks.public_webhook(await _hook(webhook_id)))


@hooks.delete("/{webhook_id}", summary="Obunani o'chirish")
async def delete_hook(webhook_id: int = Path(..., gt=0),
                      p: Principal = Depends(require("webhooks:write"))):
    await _hook(webhook_id)
    await execute("DELETE FROM api_webhooks WHERE id=?", (webhook_id,))
    await execute("DELETE FROM api_webhook_deliveries WHERE webhook_id=? AND status IN "
                  "('pending','failed')", (webhook_id,))
    return ok({"id": webhook_id, "deleted": True})


@hooks.post("/{webhook_id}/rotate-secret", summary="Imzo kalitini yangilash")
async def rotate_hook_secret(webhook_id: int = Path(..., gt=0),
                             p: Principal = Depends(require("webhooks:write"))):
    await _hook(webhook_id)
    secret = "whsec_" + secrets.token_urlsafe(32)
    await execute("UPDATE api_webhooks SET secret=?, updated_at=? WHERE id=?",
                  (secret, now_sql(), webhook_id))
    return ok(webhooks.public_webhook(await _hook(webhook_id), reveal_secret=True))


@hooks.post("/{webhook_id}/test", summary="Test (ping) hodisasini darhol yuborish")
async def test_hook(webhook_id: int = Path(..., gt=0),
                    p: Principal = Depends(require("webhooks:write"))):
    h = await _hook(webhook_id)
    payload = json.dumps({"id": f"evt_ping_{secrets.token_hex(6)}", "event": "ping",
                          "timestamp": iso(now_sql()), "source": settings.EVENT_SOURCE,
                          "api_version": "v1", "data": {"webhook_id": webhook_id}})
    did, _ = await execute(
        "INSERT INTO api_webhook_deliveries (webhook_id, event_type, payload) VALUES (?,?,?)",
        (webhook_id, "ping", payload))
    d = await fetch_one("SELECT * FROM api_webhook_deliveries WHERE id=?", (did,))
    await webhooks.deliver_one(d, h)
    return ok(webhooks.public_delivery(
        await fetch_one("SELECT * FROM api_webhook_deliveries WHERE id=?", (did,))))


@hooks.get("/{webhook_id}/deliveries", summary="Yetkazish jurnali (status, urinishlar, xato)")
async def list_deliveries(webhook_id: int = Path(..., gt=0), page: Page = Depends(),
                          status: Optional[str] = Query(None, pattern="^(pending|success|failed|dead)$"),
                          p: Principal = Depends(require("webhooks:read"))):
    await _hook(webhook_id)
    where, params = "WHERE webhook_id=?", [webhook_id]
    if status:
        where += " AND status=?"
        params.append(status)
    total = await fetch_val(f"SELECT COUNT(*) FROM api_webhook_deliveries {where}", tuple(params))
    rows = await fetch_all(f"SELECT * FROM api_webhook_deliveries {where} ORDER BY id DESC "
                           "LIMIT ? OFFSET ?", (*params, page.limit, page.offset))
    return ok([webhooks.public_delivery(r) for r in rows], page.meta(total))


@hooks.post("/deliveries/{delivery_id}/retry", summary="Muvaffaqiyatsiz yetkazishni qayta yuborish")
async def retry_delivery(delivery_id: int = Path(..., gt=0),
                         p: Principal = Depends(require("webhooks:write"))):
    d = await fetch_one("SELECT * FROM api_webhook_deliveries WHERE id=?", (delivery_id,))
    if not d:
        raise not_found("Yetkazish", delivery_id)
    if d["status"] == "success":
        raise ApiError(409, "already_delivered", "Allaqachon yetkazilgan.")
    h = await _hook(d["webhook_id"])
    await webhooks.deliver_one(d, h)
    return ok(webhooks.public_delivery(
        await fetch_one("SELECT * FROM api_webhook_deliveries WHERE id=?", (delivery_id,))))


# ================= API KALITLARI (admin) =================
@keys.get("", summary="API kalitlari (kalitning o'zi qaytmaydi)")
async def list_keys(p: Principal = Depends(require("admin"))):
    return ok([public_key(k) for k in await list_api_keys()])


@keys.post("", status_code=201, summary="Yangi kalit (to'liq kalit FAQAT shu javobda)")
async def create_key(body: ApiKeyCreate, p: Principal = Depends(require("admin"))):
    expires = None
    if body.expires_at:
        from api.core import parse_dt
        expires = parse_dt(body.expires_at).strftime("%Y-%m-%d %H:%M:%S")
    row, raw = await create_api_key(body.name, body.scopes, expires, body.description,
                                    p.actor, body.rate_limit_per_minute)
    return ok({**public_key(row), "api_key": raw}, status=201)


@keys.get("/{key_id}", summary="Kalit ma'lumoti")
async def get_key(key_id: int = Path(..., gt=0), p: Principal = Depends(require("admin"))):
    row = await get_api_key(key_id)
    if not row:
        raise not_found("API kalit", key_id)
    return ok(public_key(row))


@keys.post("/{key_id}/revoke", summary="Kalitni bekor qilish")
async def revoke_key(key_id: int = Path(..., gt=0), p: Principal = Depends(require("admin"))):
    if not await get_api_key(key_id):
        raise not_found("API kalit", key_id)
    await revoke_api_key(key_id)
    return ok(public_key(await get_api_key(key_id)))


@keys.post("/{key_id}/rotate", summary="Kalitni qayta yaratish (eski kalit darhol ishlamaydi)")
async def rotate_key(key_id: int = Path(..., gt=0), p: Principal = Depends(require("admin"))):
    row, raw = await rotate_api_key(key_id)
    if not row:
        raise not_found("API kalit", key_id)
    return ok({**public_key(row), "api_key": raw})
