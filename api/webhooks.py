"""Chiquvchi webhook tizimi: hodisalar -> obunalar -> imzolangan yetkazish + retry.

Oqim:
  1. TRIGGER lar `api_events` ga hodisa yozadi (bot yoki API o'zgarishi).
  2. `fanout_events()` hodisa uchun yakuniy payload ni quradi va har bir mos
     faol obuna uchun `api_webhook_deliveries` yozuvini yaratadi.
  3. `deliver_due()` vaqti kelgan yetkazishlarni POST qiladi. Xato bo'lsa —
     eksponensial kechikish (base * 2^n, max 6 soat) bilan qayta urinadi;
     WEBHOOK_MAX_ATTEMPTS dan keyin `dead` holatiga o'tadi (qo'lda retry mumkin).

Imzo:  X-Webhook-Signature: t=<unix>,v1=<hex(HMAC_SHA256(secret, f"{t}.{body}"))>
"""
import hashlib
import hmac
import json
import logging
import time
from datetime import timedelta

import httpx

from api import settings
from api.core import connect, fetch_all, iso, now_sql, now_tk
from api.repo import LOADERS

logger = logging.getLogger("hrbot.api.webhooks")

EVENT_TYPES = [
    "employee.created", "employee.updated", "employee.deleted",
    "branch.created", "branch.updated", "branch.deleted",
    "department.created", "department.updated", "department.deleted",
    "position.created", "position.updated", "position.deleted",
    "attendance.created", "attendance.updated",
    "leave.created", "leave.updated",
    "announcement.created",
]

_http_client = None


def set_http_client(client):
    """Testlar uchun (httpx.AsyncClient yoki MockTransport)."""
    global _http_client
    _http_client = client


def sign(secret, timestamp, body):
    mac = hmac.new(secret.encode(), f"{timestamp}.{body}".encode(), hashlib.sha256)
    return mac.hexdigest()


def verify_signature(secret, header, body, tolerance=300):
    """Kiruvchi / chiquvchi imzoni tekshirish (Staffora ham shu funksiya mantiqini ishlatadi)."""
    try:
        parts = dict(p.split("=", 1) for p in (header or "").split(","))
        ts = int(parts["t"])
        sig = parts["v1"]
    except (KeyError, ValueError):
        return False
    if abs(time.time() - ts) > tolerance:
        return False
    return hmac.compare_digest(sign(secret, ts, body), sig)


def _matches(webhook_events, event_type):
    if webhook_events in (None, "", "*"):
        return True
    try:
        lst = json.loads(webhook_events)
    except ValueError:
        return False
    return "*" in lst or event_type in lst or f"{event_type.split('.')[0]}.*" in lst


async def build_data(event, include_salary=False):
    if event["event_type"].endswith(".deleted"):
        data = json.loads(event.get("snapshot") or "{}") or {"id": event["entity_id"]}
        from api.repo import external_ids_map
        ext = await external_ids_map(event["entity_type"], [event["entity_id"]])
        data["external_ids"] = ext.get(event["entity_id"], {})
        return data
    loader = LOADERS.get(event["entity_type"])
    if not loader:
        return {"id": event["entity_id"]}
    if event["entity_type"] == "employee":
        data = await loader(event["entity_id"], include_salary=include_salary)
    else:
        data = await loader(event["entity_id"])
    return data or {"id": event["entity_id"], "deleted": True}


def envelope(event, data):
    return {
        "id": f"evt_{event['id']}",
        "event": event["event_type"],
        "timestamp": iso(event.get("created_at")) or iso(now_sql()),
        "source": settings.EVENT_SOURCE,
        "api_version": "v1",
        "data": data,
    }


async def fanout_events(limit=200):
    """Ishlov berilmagan hodisalarni obunalarga tarqatadi. Qayta ishlangan son."""
    events = await fetch_all(
        "SELECT * FROM api_events WHERE processed=0 ORDER BY id LIMIT ?", (limit,))
    if not events:
        return 0
    hooks = await fetch_all("SELECT * FROM api_webhooks WHERE active=1")
    for ev in events:
        base = await build_data(ev, include_salary=False)
        payload_plain = json.dumps(envelope(ev, base), ensure_ascii=False, default=str)
        rich = None
        async with connect() as db:
            for h in hooks:
                if not _matches(h.get("events"), ev["event_type"]):
                    continue
                body = payload_plain
                if h.get("include_salary") and ev["entity_type"] == "employee" \
                        and not ev["event_type"].endswith(".deleted"):
                    if rich is None:
                        rich = json.dumps(envelope(ev, await build_data(ev, True)),
                                          ensure_ascii=False, default=str)
                    body = rich
                await db.execute(
                    "INSERT INTO api_webhook_deliveries (webhook_id, event_id, event_type, payload) "
                    "VALUES (?,?,?,?)",
                    (h["id"], ev["id"], ev["event_type"], body),
                )
            await db.execute(
                "UPDATE api_events SET processed=1, processed_at=?, payload=? WHERE id=?",
                (now_sql(), json.dumps(base, ensure_ascii=False, default=str), ev["id"]),
            )
            await db.commit()
    return len(events)


def _backoff(attempts):
    seconds = settings.WEBHOOK_BACKOFF_BASE_SECONDS * (2 ** max(0, attempts - 1))
    return min(seconds, 6 * 3600)


async def deliver_one(delivery, hook):
    ts = int(time.time())
    body = delivery["payload"]
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "GulnoraFarm-HRBot-Webhooks/1.0",
        "X-Webhook-Id": f"dlv_{delivery['id']}",
        "X-Webhook-Event": delivery["event_type"],
        "X-Webhook-Timestamp": str(ts),
        "X-Webhook-Signature": f"t={ts},v1={sign(hook['secret'], ts, body)}",
    }
    attempts = int(delivery["attempts"] or 0) + 1
    status_code, error = None, None
    try:
        client = _http_client or httpx.AsyncClient(timeout=settings.WEBHOOK_TIMEOUT_SECONDS)
        try:
            resp = await client.post(hook["url"], content=body.encode("utf-8"), headers=headers)
        finally:
            if _http_client is None:
                await client.aclose()
        status_code = resp.status_code
        success = 200 <= resp.status_code < 300
        if not success:
            error = f"HTTP {resp.status_code}: {resp.text[:300]}"
    except Exception as e:
        success = False
        error = f"{type(e).__name__}: {str(e)[:300]}"

    async with connect() as db:
        if success:
            await db.execute(
                "UPDATE api_webhook_deliveries SET status='success', attempts=?, "
                "last_status_code=?, last_error=NULL, delivered_at=? WHERE id=?",
                (attempts, status_code, now_sql(), delivery["id"]),
            )
        else:
            dead = attempts >= settings.WEBHOOK_MAX_ATTEMPTS
            nxt = (now_tk() + timedelta(seconds=_backoff(attempts))).strftime("%Y-%m-%d %H:%M:%S")
            await db.execute(
                "UPDATE api_webhook_deliveries SET status=?, attempts=?, last_status_code=?, "
                "last_error=?, next_attempt_at=? WHERE id=?",
                ("dead" if dead else "failed", attempts, status_code, error,
                 None if dead else nxt, delivery["id"]),
            )
        await db.commit()
    return success


async def deliver_due(limit=50):
    rows = await fetch_all(
        """SELECT d.*, w.url, w.secret, w.active FROM api_webhook_deliveries d
             JOIN api_webhooks w ON w.id=d.webhook_id
            WHERE d.status IN ('pending','failed') AND w.active=1
              AND (d.next_attempt_at IS NULL OR d.next_attempt_at<=?)
            ORDER BY d.id LIMIT ?""",
        (now_sql(), limit),
    )
    ok = 0
    for d in rows:
        if await deliver_one(d, d):
            ok += 1
    return ok


def public_delivery(d):
    return {
        "id": d["id"],
        "webhook_id": d["webhook_id"],
        "event_id": f"evt_{d['event_id']}" if d.get("event_id") else None,
        "event": d["event_type"],
        "status": d["status"],
        "attempts": d["attempts"],
        "next_attempt_at": iso(d.get("next_attempt_at")) if d["status"] in ("pending", "failed") else None,
        "last_status_code": d.get("last_status_code"),
        "last_error": d.get("last_error"),
        "created_at": iso(d.get("created_at")),
        "delivered_at": iso(d.get("delivered_at")),
    }


def public_webhook(h, reveal_secret=False):
    events = h.get("events") or "*"
    try:
        events = json.loads(events) if events != "*" else ["*"]
    except ValueError:
        events = ["*"]
    out = {
        "id": h["id"],
        "url": h["url"],
        "description": h.get("description"),
        "events": events,
        "include_salary": bool(h.get("include_salary")),
        "active": bool(h.get("active")),
        "created_at": iso(h.get("created_at")),
        "updated_at": iso(h.get("updated_at")),
    }
    if reveal_secret:
        out["secret"] = h["secret"]
    return out
