"""REST API testlari: auth, CRUD, davomat, e'lon, webhook, idempotency, sync ..."""
import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import httpx
import pytest

from conftest import make_key, run, sql

V1 = "/api/v1"


def H(raw):
    return {"Authorization": f"Bearer {raw}"}


def new_employee(client, headers, tg=700001, **extra):
    body = {"telegram_id": tg, "full_name": "Valiyev Ali", "phone": "+998901234567",
            "role": "pharmacist", "branch_id": 1, "position": "💊 Farmatsevt",
            "work_hours": "08:00 - 17:00", "rest_day": "Yakshanba", **extra}
    r = client.post(f"{V1}/employees", json=body, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["data"]


# ======================= AUTH =======================
def test_health_is_public(env):
    r = env.get(f"{V1}/health")
    assert r.status_code == 200
    assert r.json()["success"] is True and r.json()["data"]["database"] == "ok"
    assert "X-Request-Id" in r.headers


def test_missing_and_invalid_token(env):
    r = env.get(f"{V1}/employees")
    assert r.status_code == 401
    body = r.json()
    assert body == {"success": False, "error": {"code": "unauthorized", "message": body["error"]["message"],
                                                "details": {}}}
    assert env.get(f"{V1}/employees", headers=H("gfk_bad_token")).status_code == 401
    assert env.get(f"{V1}/employees", headers=H("random")).json()["error"]["code"] == "invalid_token"


def test_revoked_expired_and_scope(env):
    raw, row = make_key(env, ["branches:read"])
    assert env.get(f"{V1}/branches", headers=H(raw)).status_code == 200
    # scope yo'q
    r = env.get(f"{V1}/employees", headers=H(raw))
    assert r.status_code == 403 and r.json()["error"]["code"] == "insufficient_scope"
    # write => read emas, lekin read => write emas
    assert env.post(f"{V1}/branches", json={"name": "X filial"}, headers=H(raw)).status_code == 403
    # bekor qilingan
    from api.security import revoke_api_key
    run(env, revoke_api_key, row["id"])
    assert env.get(f"{V1}/branches", headers=H(raw)).json()["error"]["code"] == "token_revoked"
    # muddati o'tgan
    raw2, _ = make_key(env, ["branches:read"], expires_at="2020-01-01 00:00:00")
    assert env.get(f"{V1}/branches", headers=H(raw2)).json()["error"]["code"] == "token_expired"
    # X-API-Key header ham ishlaydi
    raw3, _ = make_key(env, ["branches:read"])
    assert env.get(f"{V1}/branches", headers={"X-API-Key": raw3}).status_code == 200


def test_key_hash_only_stored_and_rotate(env, admin_headers):
    r = env.post(f"{V1}/api-keys", json={"name": "staffora", "scopes": ["employees:read"]},
                 headers=admin_headers)
    assert r.status_code == 201
    raw = r.json()["data"]["api_key"]
    kid = r.json()["data"]["id"]
    rows = sql(env, "SELECT * FROM api_keys WHERE id=?", (kid,))
    assert raw not in json.dumps(rows)  # kalitning o'zi bazada yo'q
    listed = env.get(f"{V1}/api-keys", headers=admin_headers).json()["data"]
    assert all("api_key" not in k and "key_hash" not in k for k in listed)
    r = env.post(f"{V1}/api-keys/{kid}/rotate", headers=admin_headers)
    new_raw = r.json()["data"]["api_key"]
    assert env.get(f"{V1}/employees", headers=H(raw)).status_code == 401
    assert env.get(f"{V1}/employees", headers=H(new_raw)).status_code == 200
    bad = env.post(f"{V1}/api-keys", json={"name": "xx", "scopes": ["root"]}, headers=admin_headers)
    assert bad.status_code == 400 and bad.json()["error"]["code"] == "invalid_scope"


def test_rate_limit(env):
    raw, _ = make_key(env, ["branches:read"], rate_limit_per_minute=3)
    codes = [env.get(f"{V1}/branches", headers=H(raw)).status_code for _ in range(4)]
    assert codes == [200, 200, 200, 429]
    r = env.get(f"{V1}/branches", headers=H(raw))
    assert r.json()["error"]["code"] == "rate_limited" and "Retry-After" in r.headers


# ======================= EMPLOYEES =======================
def test_employee_crud_flow(env, admin_headers):
    emp = new_employee(env, admin_headers, external_ids={"staffora": "ST-000123"})
    uid = emp["id"]
    assert emp["telegram_id"] == 700001
    assert emp["branch"]["id"] == 1 and emp["role"] == "pharmacist"
    assert emp["external_ids"] == {"staffora": "ST-000123"}
    assert emp["schedule"]["work_hours"] == "08:00 - 17:00"
    # bot jadvallarida botdagi kabi yozildi
    u = sql(env, "SELECT role, branch_id, name_locked FROM users WHERE id=?", (uid,))[0]
    assert u == {"role": "pharmacist", "branch_id": 1, "name_locked": 1}
    assert sql(env, "SELECT event_type FROM hr_events WHERE user_id=?", (uid,))[0]["event_type"] == "hired"
    assert sql(env, "SELECT type FROM api_notifications WHERE user_id=?", (uid,))[0]["type"] == "employee_hired"

    # GET / by-telegram / by-external
    assert env.get(f"{V1}/employees/{uid}", headers=admin_headers).json()["data"]["full_name"] == "Valiyev Ali"
    assert env.get(f"{V1}/employees/by-telegram/700001", headers=admin_headers).json()["data"]["id"] == uid
    assert env.get(f"{V1}/employees/by-external/staffora/ST-000123", headers=admin_headers).json()["data"]["id"] == uid
    assert env.get(f"{V1}/employees/99999", headers=admin_headers).status_code == 404

    # PATCH: ism + filial -> hr_events (IT paneli hisoboti bilan mos)
    r = env.patch(f"{V1}/employees/{uid}", json={"full_name": "Valiyev Alisher", "branch_id": 2,
                                                   "employment_status": "trial"}, headers=admin_headers)
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["full_name"] == "Valiyev Alisher" and d["branch"]["id"] == 2
    assert d["employment_status"] == "trial"
    events = [e["event_type"] for e in sql(env, "SELECT event_type FROM hr_events WHERE user_id=? ORDER BY id", (uid,))]
    assert events == ["hired", "name_changed", "transferred"]

    # PUT: yuborilmagan maydonlar tozalanadi
    r = env.put(f"{V1}/employees/{uid}", json={"full_name": "Valiyev Alisher", "role": "employee",
                                                "branch_id": 2}, headers=admin_headers)
    d = r.json()["data"]
    assert d["role"] == "employee" and d["schedule"]["work_hours"] is None and d["phone"] is None
    assert d["employment_status"] == "regular"

    # DELETE -> botdagi ishdan bo'shatish
    r = env.delete(f"{V1}/employees/{uid}?reason=Test", headers=admin_headers)
    assert r.status_code == 200
    assert sql(env, "SELECT role, branch_id FROM users WHERE id=?", (uid,))[0] == {"role": "candidate", "branch_id": None}
    assert sql(env, "SELECT reason FROM dismissed_employees WHERE user_id=?", (uid,))[0]["reason"] == "Test"
    assert env.get(f"{V1}/employees/{uid}", headers=admin_headers).status_code == 404
    dismissed = env.get(f"{V1}/employees/dismissed", headers=admin_headers).json()
    assert dismissed["data"][0]["employee_id"] == uid


def test_employee_validation_and_duplicates(env, admin_headers):
    new_employee(env, admin_headers, external_ids={"staffora": "ST-1"})
    # bir xil telegram_id
    r = env.post(f"{V1}/employees", json={"telegram_id": 700001, "full_name": "Boshqa Odam"},
                 headers=admin_headers)
    assert r.status_code == 409 and r.json()["error"]["code"] == "duplicate"
    # bir xil external_id
    r = env.post(f"{V1}/employees", json={"telegram_id": 700002, "full_name": "Boshqa Odam",
                                           "external_ids": {"staffora": "ST-1"}}, headers=admin_headers)
    assert r.status_code == 409
    # noto'g'ri telefon / rol / filial / noma'lum maydon
    for bad in ({"phone": "12345"}, {"role": "admin"}, {"branch_id": 9999}, {"hacker": 1}):
        r = env.post(f"{V1}/employees", json={"telegram_id": 700003, "full_name": "Test Test", **bad},
                     headers=admin_headers)
        assert r.status_code == 422, (bad, r.text)
        assert r.json()["success"] is False
    # super admin himoyalangan
    r = env.post(f"{V1}/employees", json={"telegram_id": 999000111, "full_name": "Admin"},
                 headers=admin_headers)
    assert r.status_code == 409 and r.json()["error"]["code"] == "protected_account"
    # telefon normalizatsiyasi (bot qoidasi +998XXXXXXXXX)
    r = env.post(f"{V1}/employees", json={"telegram_id": 700004, "full_name": "Test Test",
                                           "phone": "998 90 123-45-67"}, headers=admin_headers)
    assert r.json()["data"]["phone"] == "+998901234567"


def test_salary_scope(env, admin_headers):
    new_employee(env, admin_headers, monthly_salary="5000000")
    raw, _ = make_key(env, ["employees:read", "employees:write"])
    d = env.get(f"{V1}/employees/by-telegram/700001", headers=H(raw)).json()["data"]
    assert "salary" not in d and "telegram_file_ids" not in d["documents"]
    r = env.patch(f"{V1}/employees/{d['id']}", json={"monthly_salary": "1"}, headers=H(raw))
    assert r.status_code == 403
    d = env.get(f"{V1}/employees/by-telegram/700001", headers=admin_headers).json()["data"]
    assert d["salary"]["monthly_salary"] == "5000000"


def test_employee_list_pagination_search_filter(env, admin_headers):
    for i in range(7):
        new_employee(env, admin_headers, tg=800000 + i, full_name=f"Xodim {i:02d}",
                     branch_id=1 if i < 4 else 2, notify=False)
    r = env.get(f"{V1}/employees?page=2&limit=3&sort=full_name", headers=admin_headers).json()
    assert r["meta"] == {"page": 2, "limit": 3, "total": 7, "pages": 3}
    assert [e["full_name"] for e in r["data"]] == ["Xodim 03", "Xodim 04", "Xodim 05"]
    r = env.get(f"{V1}/employees?branch_id=2", headers=admin_headers).json()
    assert r["meta"]["total"] == 3
    r = env.get(f"{V1}/employees?search=xodim 06", headers=admin_headers).json()
    assert [e["full_name"] for e in r["data"]] == ["Xodim 06"]
    r = env.get(f"{V1}/employees?sort=-hacked", headers=admin_headers)
    assert r.status_code == 400 and r.json()["error"]["code"] == "invalid_sort"
    assert env.get(f"{V1}/employees?limit=1000", headers=admin_headers).status_code == 422
    # SQL injection urinishi — oddiy matn sifatida
    r = env.get(f"{V1}/employees", params={"search": "x' OR 1=1 --"}, headers=admin_headers).json()
    assert r["meta"]["total"] == 0


# ======================= BRANCH / DEPARTMENT / POSITION =======================
def test_branch_crud(env, admin_headers):
    r = env.post(f"{V1}/branches", json={"name": "Test filiali", "code": "TST", "latitude": 40.7,
                                          "longitude": 72.3, "radius": 200, "working_hours": "08:00 - 22:00",
                                          "external_ids": {"staffora": "BR-9"}}, headers=admin_headers)
    assert r.status_code == 201, r.text
    b = r.json()["data"]
    assert b["code"] == "TST" and b["radius"] == 200 and b["status"] == "active"
    bid = b["id"]
    r = env.patch(f"{V1}/branches/{bid}", json={"status": "inactive", "phone": "+998900000000"},
                  headers=admin_headers)
    assert r.json()["data"]["status"] == "inactive" and r.json()["data"]["phone"] == "+998900000000"
    assert env.post(f"{V1}/branches", json={"name": "Dublikat", "code": "TST"},
                    headers=admin_headers).status_code == 409
    lst = env.get(f"{V1}/branches?limit=100", headers=admin_headers).json()
    assert lst["meta"]["total"] == 17  # 16 standart + 1
    # xodimi bor filial o'chmaydi
    new_employee(env, admin_headers, branch_id=bid)
    r = env.delete(f"{V1}/branches/{bid}", headers=admin_headers)
    assert r.status_code == 409 and r.json()["error"]["code"] == "branch_not_empty"
    b2 = env.post(f"{V1}/branches", json={"name": "Bo'sh filial"}, headers=admin_headers).json()["data"]
    assert env.delete(f"{V1}/branches/{b2['id']}", headers=admin_headers).status_code == 200
    assert env.get(f"{V1}/branches/{b2['id']}", headers=admin_headers).status_code == 404
    # manager filialga bog'lanadi
    new_employee(env, admin_headers, tg=700050, role="manager", branch_id=bid, full_name="Rahbar Bir")
    b = env.get(f"{V1}/branches/{bid}", headers=admin_headers).json()["data"]
    assert [m["full_name"] for m in b["managers"]] == ["Rahbar Bir"]


def test_department_and_position_crud(env, admin_headers):
    d = env.post(f"{V1}/departments", json={"name": "Savdo", "code": "SALES"}, headers=admin_headers)
    assert d.status_code == 201
    did = d.json()["data"]["id"]
    child = env.post(f"{V1}/departments", json={"name": "Chakana", "parent_id": did},
                     headers=admin_headers).json()["data"]
    assert child["parent_id"] == did
    assert env.patch(f"{V1}/departments/{did}", json={"parent_id": did},
                     headers=admin_headers).status_code == 422
    p = env.post(f"{V1}/positions", json={"name": "Kassir", "code": "CASH", "department_id": did},
                 headers=admin_headers)
    assert p.status_code == 201
    pid = p.json()["data"]["id"]
    emp = new_employee(env, admin_headers, position_id=pid, department_id=did)
    assert emp["position"] == "Kassir" and emp["department"]["id"] == did
    # lavozim nomi o'zgarsa — xodimlardagi matn ham
    env.patch(f"{V1}/positions/{pid}", json={"name": "Katta kassir"}, headers=admin_headers)
    assert env.get(f"{V1}/employees/{emp['id']}", headers=admin_headers).json()["data"]["position"] == "Katta kassir"
    assert env.delete(f"{V1}/positions/{pid}", headers=admin_headers).status_code == 409
    assert env.delete(f"{V1}/departments/{did}", headers=admin_headers).status_code == 409
    assert env.delete(f"{V1}/departments/{child['id']}", headers=admin_headers).status_code == 200
    assert env.get(f"{V1}/departments", headers=admin_headers).json()["meta"]["total"] == 1
    assert env.get(f"{V1}/positions?search=kassir", headers=admin_headers).json()["meta"]["total"] == 1


# ======================= ATTENDANCE =======================
def test_attendance_check_in_out(env, admin_headers):
    emp = new_employee(env, admin_headers)
    body = {"employee_id": emp["id"], "timestamp": "2026-09-15T08:15:30+05:00",
            "verification_method": "face", "device": "Terminal-1",
            "location": {"latitude": 40.747291, "longitude": 72.36142}, "external_id": "ATT-1"}
    r = env.post(f"{V1}/attendance/check-in", json=body, headers=admin_headers)
    assert r.status_code == 201, r.text
    a = r.json()["data"]
    assert a["late"] is True and a["late_seconds"] == 15 * 60 + 30
    assert a["check_in"] == "2026-09-15T08:15:30+05:00" and a["location"]["check_in"]["distance_m"] == 0
    assert a["verification_method"] == "face" and a["state"] == "checked_in"
    # takroriy check-in — yangi yozuv yaratilmaydi
    r = env.post(f"{V1}/attendance/check-in", json=body, headers=admin_headers)
    assert r.status_code == 200 and r.json()["meta"]["duplicate"] is True
    r = env.post(f"{V1}/attendance/check-out", json={"telegram_id": 700001,
                                                      "timestamp": "2026-09-15T16:30:00+05:00"},
                 headers=admin_headers)
    a = r.json()["data"]
    assert a["early_leave"] is True and a["early_leave_seconds"] == 30 * 60
    assert a["worked_minutes"] == (16 * 60 + 30) - (8 * 60 + 15) - 1
    lst = env.get(f"{V1}/attendance?date_from=2026-09-01&date_to=2026-09-30&late=true",
                  headers=admin_headers).json()
    assert lst["meta"]["total"] == 1
    assert env.get(f"{V1}/employees/{emp['id']}/attendance", headers=admin_headers).json()["meta"]["total"] == 1
    assert env.get(f"{V1}/attendance/{a['id']}", headers=admin_headers).json()["data"]["external_ids"]


def test_attendance_geofence_and_errors(env, admin_headers):
    emp = new_employee(env, admin_headers)
    far = {"employee_id": emp["id"], "location": {"latitude": 41.3, "longitude": 69.2},
           "enforce_geofence": True}
    r = env.post(f"{V1}/attendance/check-in", json=far, headers=admin_headers)
    assert r.status_code == 422 and r.json()["error"]["code"] == "outside_geofence"
    r = env.post(f"{V1}/attendance/check-out", json={"employee_id": emp["id"]}, headers=admin_headers)
    assert r.status_code == 409 and r.json()["error"]["code"] == "not_checked_in"
    r = env.post(f"{V1}/attendance/check-in", json={"employee_id": 424242}, headers=admin_headers)
    assert r.status_code == 404
    r = env.post(f"{V1}/attendance/check-in", json={}, headers=admin_headers)
    assert r.status_code == 422
    r = env.post(f"{V1}/attendance/check-in",
                 json={"employee_id": emp["id"], "timestamp": "2099-01-01T08:00:00+05:00"},
                 headers=admin_headers)
    assert r.status_code == 422


# ======================= SCHEDULES / LEAVES =======================
def test_schedule_and_leave_flow(env, admin_headers):
    emp = new_employee(env, admin_headers)
    mgr = new_employee(env, admin_headers, tg=700010, role="manager", full_name="Rahbar Filial")
    r = env.patch(f"{V1}/schedules/{emp['id']}", json={"work_hours": "09:00 - 18:00"}, headers=admin_headers)
    assert r.json()["data"]["start_time"] == "09:00"
    env.sent.messages.clear()
    r = env.post(f"{V1}/leaves", json={"employee_id": emp["id"], "from_day": "Yakshanba",
                                        "to_day": "Shanba", "reason": "Oilaviy"}, headers=admin_headers)
    assert r.status_code == 201
    lv = r.json()["data"]
    assert lv["status"] == "pending"
    # botdagidek filial rahbariga tasdiqlash tugmalari bilan bordi
    to_mgr = [m for m in env.sent.messages if m["chat_id"] == mgr["telegram_id"]]
    assert to_mgr and "doacc:" in json.dumps(to_mgr[0]["markup"].model_dump())
    assert sql(env, "SELECT COUNT(*) c FROM request_notices WHERE kind='dayoff'")[0]["c"] >= 1
    r = env.patch(f"{V1}/leaves/{lv['id']}", json={"status": "approved"}, headers=admin_headers)
    assert r.json()["data"]["status"] == "approved"
    assert env.get(f"{V1}/schedules/{emp['id']}", headers=admin_headers).json()["data"]["rest_day"] == "Shanba"
    r = env.patch(f"{V1}/leaves/{lv['id']}", json={"status": "rejected"}, headers=admin_headers)
    assert r.status_code == 409 and r.json()["error"]["code"] == "already_processed"
    assert env.get(f"{V1}/leaves?status=approved", headers=admin_headers).json()["meta"]["total"] == 1


# ======================= ANNOUNCEMENTS / NOTIFICATIONS =======================
def test_announcement_sent_via_bot_with_ack(env, admin_headers):
    from api.workers import run_once
    e1 = new_employee(env, admin_headers, tg=700001, branch_id=1, notify=False)
    new_employee(env, admin_headers, tg=700002, branch_id=2, notify=False)
    e3 = new_employee(env, admin_headers, tg=700003, branch_id=1, notify=False)
    env.sent.fail_ids.add(700003)
    r = env.post(f"{V1}/announcements", json={"title": "Yig'ilish", "message": "Ertaga <9:00>",
                                               "branch_id": 1, "source": "staffora"},
                 headers=admin_headers)
    assert r.status_code == 201, r.text
    aid = r.json()["data"]["id"]
    assert r.json()["data"]["stats"]["recipients"] == 2
    run(env, run_once)
    msgs = [m for m in env.sent.messages if m["chat_id"] == 700001]
    assert msgs and "&lt;9:00&gt;" in msgs[0]["text"]  # HTML escape
    assert "trustack:" in json.dumps(msgs[0]["markup"].model_dump())
    d = env.get(f"{V1}/announcements/{aid}?include_recipients=true", headers=admin_headers).json()["data"]
    assert d["status"] == "sent" and d["stats"]["sent"] == 1 and d["stats"]["failed"] == 1
    # bot «Ko'rib chiqdim» handleri ishlatadigan jadval
    notice = sql(env, "SELECT * FROM trust_notices")[0]
    sql(env, "UPDATE trust_notice_reads SET seen=1 WHERE notice_id=? AND chat_id=?", (notice["id"], 700001))
    d = env.get(f"{V1}/announcements/{aid}?include_recipients=true", headers=admin_headers).json()["data"]
    assert d["stats"]["acknowledged"] == 1
    assert {x["employee_id"]: x["delivery_status"] for x in d["recipients"]} == {e1["id"]: "sent", e3["id"]: "failed"}
    r = env.post(f"{V1}/announcements", json={"message": "x"}, headers=admin_headers)
    assert r.status_code == 422


def test_scheduled_announcement_and_cancel(env, admin_headers):
    new_employee(env, admin_headers, notify=False)
    r = env.post(f"{V1}/announcements", json={"message": "Kelajakda", "send_to_all": True,
                                               "scheduled_at": "2099-01-01T09:00:00+05:00"},
                 headers=admin_headers)
    aid = r.json()["data"]["id"]
    from api.workers import run_once
    run(env, run_once)
    assert env.get(f"{V1}/announcements/{aid}", headers=admin_headers).json()["data"]["status"] == "scheduled"
    assert env.post(f"{V1}/announcements/{aid}/cancel", headers=admin_headers).json()["data"]["status"] == "cancelled"
    assert env.post(f"{V1}/announcements/{aid}/cancel", headers=admin_headers).status_code == 409


def test_notifications(env, admin_headers):
    from api.workers import run_once
    emp = new_employee(env, admin_headers, notify=False)
    r = env.post(f"{V1}/notifications", json={"employee_id": emp["id"], "title": "Eslatma",
                                               "message": "Hujjat olib keling"}, headers=admin_headers)
    assert r.status_code == 202 and r.json()["data"]["status"] == "queued"
    run(env, run_once)
    lst = env.get(f"{V1}/notifications?employee_id={emp['id']}", headers=admin_headers).json()
    assert lst["data"][0]["status"] == "sent"
    assert env.sent.messages[-1]["text"].startswith("<b>Eslatma</b>")
    assert env.post(f"{V1}/notifications", json={"employee_id": 99999, "message": "x"},
                    headers=admin_headers).status_code == 422


# ======================= WEBHOOKS =======================
class Receiver:
    def __init__(self, fail_times=0):
        self.calls = []
        self.fail_times = fail_times

    def handler(self, request: httpx.Request):
        self.calls.append(request)
        if len(self.calls) <= self.fail_times:
            return httpx.Response(503, text="down")
        return httpx.Response(200, json={"ok": True})


def test_webhook_delivery_signature_and_bot_side_events(env, admin_headers):
    from api import webhooks
    from api.workers import run_once
    from database import queries as q
    rec = Receiver()
    webhooks.set_http_client(httpx.AsyncClient(transport=httpx.MockTransport(rec.handler)))
    r = env.post(f"{V1}/webhooks", json={"url": "https://staffora.example/hooks",
                                          "events": ["employee.*", "branch.created"]}, headers=admin_headers)
    assert r.status_code == 201
    secret = r.json()["data"]["secret"]
    assert "secret" not in env.get(f"{V1}/webhooks", headers=admin_headers).json()["data"][0]
    run(env, run_once)  # oldingi (seed) hodisalarni tozalash
    rec.calls.clear()

    emp = new_employee(env, admin_headers)
    # BOT tomonidagi o'zgarish (API emas) ham webhook beradi — trigger orqali
    run(env, q.update_rest_day, emp["id"], "Juma")
    run(env, run_once)
    bodies = [json.loads(c.content) for c in rec.calls]
    events = [b["event"] for b in bodies]
    assert events == ["employee.created"] or events == ["employee.created", "employee.updated"]
    run(env, q.update_rest_day, emp["id"], "Shanba")
    run(env, run_once)
    bodies = [json.loads(c.content) for c in rec.calls]
    last = bodies[-1]
    assert last["event"] == "employee.updated" and last["source"] == "employee_bot"
    assert last["data"]["schedule"]["rest_day"] == "Shanba"
    assert "salary" not in last["data"]
    # imzo
    req = rec.calls[-1]
    sig = dict(p.split("=", 1) for p in req.headers["X-Webhook-Signature"].split(","))
    expected = hmac.new(secret.encode(), f"{sig['t']}.{req.content.decode()}".encode(),
                        hashlib.sha256).hexdigest()
    assert hmac.compare_digest(expected, sig["v1"])
    assert webhooks.verify_signature(secret, req.headers["X-Webhook-Signature"], req.content.decode())
    # o'chirish hodisasi
    env.delete(f"{V1}/employees/{emp['id']}", headers=admin_headers)
    run(env, run_once)
    deleted = json.loads(rec.calls[-1].content)
    assert deleted["event"] == "employee.deleted" and deleted["data"]["telegram_id"] == 700001
    # obunaga kirmagan hodisa yuborilmaydi
    n = len(rec.calls)
    env.post(f"{V1}/departments", json={"name": "Yangi"}, headers=admin_headers)
    run(env, run_once)
    assert len(rec.calls) == n


def test_webhook_retry_backoff_and_dead(env, admin_headers):
    from api import webhooks
    from api.workers import run_once
    rec = Receiver(fail_times=100)
    webhooks.set_http_client(httpx.AsyncClient(transport=httpx.MockTransport(rec.handler)))
    hid = env.post(f"{V1}/webhooks", json={"url": "https://x.example/h", "events": ["branch.created"]},
                   headers=admin_headers).json()["data"]["id"]
    run(env, run_once)
    env.post(f"{V1}/branches", json={"name": "Retry filial"}, headers=admin_headers)
    run(env, run_once)
    d = env.get(f"{V1}/webhooks/{hid}/deliveries", headers=admin_headers).json()["data"][0]
    assert d["status"] == "failed" and d["attempts"] == 1 and d["last_status_code"] == 503
    assert d["next_attempt_at"] is not None
    run(env, run_once)  # vaqti kelmagan — qayta urinilmaydi
    assert env.get(f"{V1}/webhooks/{hid}/deliveries", headers=admin_headers).json()["data"][0]["attempts"] == 1
    for _ in range(2):
        env.post(f"{V1}/webhooks/deliveries/{d['id']}/retry", headers=admin_headers)
    d = env.get(f"{V1}/webhooks/{hid}/deliveries", headers=admin_headers).json()["data"][0]
    assert d["status"] == "dead" and d["attempts"] == 3
    rec.fail_times = 0
    r = env.post(f"{V1}/webhooks/deliveries/{d['id']}/retry", headers=admin_headers)
    assert r.json()["data"]["status"] == "success"
    ping = env.post(f"{V1}/webhooks/{hid}/test", headers=admin_headers).json()["data"]
    assert ping["status"] == "success" and ping["event"] == "ping"
    assert env.post(f"{V1}/webhooks", json={"url": "ftp://x", "events": ["*"]},
                    headers=admin_headers).status_code == 422
    assert env.post(f"{V1}/webhooks", json={"url": "https://x", "events": ["nope"]},
                    headers=admin_headers).status_code == 422


# ======================= IDEMPOTENCY =======================
def test_idempotency_key(env, admin_headers):
    h = {**admin_headers, "Idempotency-Key": "abc-123"}
    body = {"name": "Idem filial"}
    r1 = env.post(f"{V1}/branches", json=body, headers=h)
    r2 = env.post(f"{V1}/branches", json=body, headers=h)
    assert r1.status_code == r2.status_code == 201
    assert r1.json()["data"]["id"] == r2.json()["data"]["id"]
    assert r2.headers.get("Idempotent-Replayed") == "true"
    assert sql(env, "SELECT COUNT(*) c FROM branches WHERE name='Idem filial'")[0]["c"] == 1
    r3 = env.post(f"{V1}/branches", json={"name": "Boshqa"}, headers=h)
    assert r3.status_code == 422 and r3.json()["error"]["code"] == "idempotency_key_reused"
    # boshqa kalit bilan bir xil Idempotency-Key — mustaqil
    raw, _ = make_key(env, ["branches:write"])
    r4 = env.post(f"{V1}/branches", json=body, headers={**H(raw), "Idempotency-Key": "abc-123"})
    assert r4.status_code == 201 and r4.json()["data"]["id"] != r1.json()["data"]["id"]


# ======================= SYNC / INBOUND / CHANGES =======================
def test_sync_upsert_is_idempotent(env, admin_headers):
    payload = {
        "source": "staffora",
        "departments": [{"external_id": "D-1", "name": "Farmatsiya", "code": "PHARM"}],
        "branches": [{"external_id": "B-1", "name": "Staffora filiali", "code": "SB1"}],
        "positions": [{"external_id": "P-1", "name": "Provizor", "department_external_id": "D-1"}],
        "employees": [
            {"external_id": "E-1", "telegram_id": 710001, "full_name": "Sync Bir",
             "branch_external_id": "B-1", "position_external_id": "P-1", "department_external_id": "D-1"},
            {"external_id": "E-2", "full_name": "Telegramsiz"},
        ],
    }
    r = env.post(f"{V1}/integration/sync", json=payload, headers=admin_headers)
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["data"]["employees"][0]["action"] == "created"
    assert res["data"]["employees"][1]["action"] == "error"
    emp = env.get(f"{V1}/employees/by-external/staffora/E-1", headers=admin_headers).json()["data"]
    assert emp["position"] == "Provizor" and emp["branch"]["name"] == "Staffora filiali"
    assert emp["department"]["name"] == "Farmatsiya"
    # qayta yuborilsa — dublikat yaratilmaydi, updated bo'ladi
    payload["employees"][0]["full_name"] = "Sync Birinchi"
    r = env.post(f"{V1}/integration/sync", json=payload, headers=admin_headers).json()
    assert r["meta"]["summary"]["employees"]["updated"] == 1
    assert r["meta"]["summary"]["branches"] == {"updated": 1}
    assert sql(env, "SELECT COUNT(*) c FROM users WHERE tg_id=710001")[0]["c"] == 1
    # dry run
    dry = env.post(f"{V1}/integration/sync", json={"branches": [{"external_id": "B-9", "name": "Dry"}],
                                                    "dry_run": True}, headers=admin_headers).json()
    assert dry["data"]["branches"][0]["action"] == "created"
    assert sql(env, "SELECT COUNT(*) c FROM branches WHERE name='Dry'")[0]["c"] == 0
    # changes feed
    ch = env.get(f"{V1}/integration/changes?since_id=0&limit=500", headers=admin_headers).json()
    assert any(i["event"] == "employee.created" for i in ch["data"])
    assert ch["meta"]["next_cursor"] > 0


def _signed(secret, body):
    ts = int(time.time())
    raw = json.dumps(body)
    sig = hmac.new(secret.encode(), f"{ts}.{raw}".encode(), hashlib.sha256).hexdigest()
    return raw, {"X-Webhook-Signature": f"t={ts},v1={sig}", "Content-Type": "application/json"}


def test_inbound_webhook(env, admin_headers):
    body = {"id": "st_evt_1", "event": "branch.created",
            "data": {"external_id": "SB-77", "name": "Inbound filial"}}
    raw, headers = _signed("inbound-test-secret", body)
    r = env.post(f"{V1}/integration/webhook", content=raw, headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["result"]["action"] == "created"
    r = env.post(f"{V1}/integration/webhook", content=raw, headers=headers)
    assert r.json()["data"]["duplicate"] is True
    assert sql(env, "SELECT COUNT(*) c FROM branches WHERE name='Inbound filial'")[0]["c"] == 1
    bad = {**headers, "X-Webhook-Signature": "t=1,v1=00"}
    assert env.post(f"{V1}/integration/webhook", content=raw, headers=bad).status_code == 401


# ======================= TELEGRAM IDENTITY =======================
def _init_data(user, token="123456:TEST-TOKEN", auth_date=None):
    fields = {"auth_date": str(auth_date or int(time.time())), "query_id": "AAA",
              "user": json.dumps(user, separators=(",", ":"))}
    check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


def test_telegram_init_data_verification(env, admin_headers):
    emp = new_employee(env, admin_headers)
    ok_data = _init_data({"id": 700001, "first_name": "Ali"})
    r = env.post(f"{V1}/integration/telegram/verify", json={"init_data": ok_data}, headers=admin_headers)
    assert r.status_code == 200 and r.json()["data"]["employee"]["id"] == emp["id"]
    # soxta: boshqa token bilan imzolangan / telegram_id almashtirilgan
    forged = _init_data({"id": 700001}, token="999:OTHER")
    assert env.post(f"{V1}/integration/telegram/verify", json={"init_data": forged},
                    headers=admin_headers).status_code == 401
    tampered = ok_data.replace("700001", "700002")
    assert env.post(f"{V1}/integration/telegram/verify", json={"init_data": tampered},
                    headers=admin_headers).status_code == 401
    old = _init_data({"id": 700001}, auth_date=int(time.time()) - 10 * 86400)
    assert env.post(f"{V1}/integration/telegram/verify", json={"init_data": old},
                    headers=admin_headers).status_code == 401


# ======================= MISC =======================
def test_company_users_info_and_docs(env, admin_headers):
    r = env.patch(f"{V1}/company", json={"legal_name": "Gulnora Farm MChJ"}, headers=admin_headers)
    assert r.json()["data"]["legal_name"] == "Gulnora Farm MChJ"
    assert r.json()["data"]["stats"]["branches"] == 16
    new_employee(env, admin_headers)
    u = env.get(f"{V1}/users/by-telegram/700001", headers=admin_headers).json()["data"]
    assert u["is_employee"] is True
    r = env.patch(f"{V1}/users/{u['id']}", json={"blocked": True}, headers=admin_headers)
    assert r.json()["data"]["blocked"] is True
    admin_user = env.get(f"{V1}/users/by-telegram/999000111", headers=admin_headers).json()["data"]
    assert env.patch(f"{V1}/users/{admin_user['id']}", json={"blocked": True},
                     headers=admin_headers).status_code == 409
    info = env.get(f"{V1}/integration/info", headers=admin_headers).json()["data"]
    assert "employee.created" in info["webhook_events"]
    assert env.get("/api/openapi.json").status_code == 200
    assert env.get("/api/docs").status_code == 200
    assert env.get(f"{V1}/nope", headers=admin_headers).json()["error"]["code"] == "not_found"


def test_existing_bot_database_migrates(tmp_path, monkeypatch):
    """Haqiqiy bot bazasining NUSXASIDA migratsiya xatosiz ishlashi (asl faylga tegilmaydi)."""
    import shutil
    import sqlite3
    from pathlib import Path
    src = Path(__file__).resolve().parent.parent / "hrbot.db"
    if not src.exists():
        pytest.skip("hrbot.db yo'q")
    dst = tmp_path / "copy.db"
    con = sqlite3.connect(str(src))
    bk = sqlite3.connect(str(dst))
    con.backup(bk)
    con.close()
    bk.close()
    import config
    from database import db as botdb
    from database import queries as q
    for mod in (config, botdb, q):
        monkeypatch.setattr(mod, "DB_PATH", str(dst))
    import asyncio
    from api.migrations import run_migrations
    asyncio.run(run_migrations(str(dst)))
    asyncio.run(run_migrations(str(dst)))  # ikkinchi marta ham (idempotent)
    c = sqlite3.connect(str(dst))
    cols = {r[1] for r in c.execute("PRAGMA table_info(attendance)")}
    assert {"source", "device", "verification_method"} <= cols
    trig = c.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='trigger' AND name LIKE 'trg_api_%'").fetchone()[0]
    assert trig >= 20
    c.close()
    del shutil


# ======================= PRODUCTION (Railway) =======================
def test_production_https_and_ssrf(env, admin_headers, monkeypatch):
    from api import settings
    monkeypatch.setattr(settings, "API_REQUIRE_HTTPS", True)
    monkeypatch.setattr(settings, "WEBHOOK_REQUIRE_HTTPS", True)
    # health — ochiq (Railway/monitoring uchun), qolgani faqat HTTPS
    assert env.get(f"{V1}/health").status_code == 200
    r = env.get(f"{V1}/company", headers=admin_headers)
    assert r.status_code == 403 and r.json()["error"]["code"] == "https_required"
    # TLS Railway edge'da tugaydi; https so'rov o'tadi va HSTS qo'yiladi
    r = env.get(f"https://testserver{V1}/company", headers=admin_headers)
    assert r.status_code == 200 and "Strict-Transport-Security" in r.headers
    # webhook: http va ichki manzillar rad etiladi
    for url in ("http://staffora.uz/h", "https://localhost/h", "https://127.0.0.1/h",
                "https://10.0.0.5/h", "https://192.168.1.2/h"):
        r = env.post(f"https://testserver{V1}/webhooks", json={"url": url, "events": ["*"]},
                     headers=admin_headers)
        assert r.status_code == 422, url
    r = env.post(f"https://testserver{V1}/webhooks",
                 json={"url": "https://api.staffora.uz/h", "events": ["*"]}, headers=admin_headers)
    assert r.status_code == 201


def test_port_from_railway_env(monkeypatch):
    import importlib
    from api import settings
    monkeypatch.setenv("PORT", "4321")
    monkeypatch.delenv("API_PORT", raising=False)
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    monkeypatch.delenv("API_HOST", raising=False)
    monkeypatch.delenv("API_DOCS_ENABLED", raising=False)
    s = importlib.reload(settings)
    try:
        assert s.API_PORT == 4321 and s.API_HOST == "0.0.0.0"
        assert s.API_DOCS_ENABLED is False and s.API_REQUIRE_HTTPS is True
        assert s.WEBHOOK_REQUIRE_HTTPS is True
    finally:
        monkeypatch.undo()
        importlib.reload(settings)
