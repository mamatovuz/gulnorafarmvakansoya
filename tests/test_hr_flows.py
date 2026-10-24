"""HR oqimlari: xodim so'rovi / ariza tasdig'i (atomik), «🔄 Boshidan tasdiqlash»,
sinov muddati paneli toifalari va qarorlari."""
from datetime import timedelta

import pytest

from conftest import run, sql


# ---------------- soxta Telegram obyektlari ----------------
class FakeBot:
    def __init__(self):
        self.sent = []
        self._mid = 5000

    def _next(self):
        self._mid += 1
        return type("Msg", (), {"message_id": self._mid})()

    async def send_message(self, chat_id, text, reply_markup=None, **kw):
        self.sent.append({"chat_id": chat_id, "text": text, "markup": reply_markup})
        return self._next()

    async def send_photo(self, chat_id, photo, caption=None, reply_markup=None, **kw):
        self.sent.append({"chat_id": chat_id, "text": caption, "markup": reply_markup})
        return self._next()

    async def delete_message(self, *a, **kw):
        return True

    async def edit_message_reply_markup(self, *a, **kw):
        return True

    async def edit_message_text(self, *a, **kw):
        return True

    async def edit_message_caption(self, *a, **kw):
        return True


class FakeChat:
    def __init__(self, cid):
        self.id = cid


class FakeUser:
    def __init__(self, uid):
        self.id = uid
        self.full_name = "Test"


class FakeMessage:
    def __init__(self, tg_id, text=None):
        self.from_user = FakeUser(tg_id)
        self.chat = FakeChat(tg_id)
        self.text = text
        self.answers = []
        self._mid = 9000

    async def answer(self, text, reply_markup=None, **kw):
        self.answers.append({"text": text, "markup": reply_markup})
        self._mid += 1
        return type("Msg", (), {"message_id": self._mid})()

    async def answer_photo(self, photo, caption=None, reply_markup=None, **kw):
        return await self.answer(caption or "", reply_markup=reply_markup)

    async def edit_reply_markup(self, reply_markup=None):
        return True


class FakeCall:
    def __init__(self, tg_id, data):
        self.from_user = FakeUser(tg_id)
        self.data = data
        self.message = FakeMessage(tg_id)
        self.alerts = []

    async def answer(self, text=None, show_alert=False, **kw):
        self.alerts.append(text)


def buttons(markup):
    if not markup:
        return []
    return [btn.callback_data for row in markup.inline_keyboard for btn in row]


HR_TG = 810001
MGR_TG = 810002
EMP_TG = 810003


def _seed(env):
    sql(env, "INSERT INTO branches (id,name) VALUES (?,?)", (71, "Sinov filiali"))
    sql(env, "INSERT INTO users (id,tg_id,full_name,role) VALUES (?,?,?,?)",
        (7001, HR_TG, "HR Xodimi", "hr"))
    sql(env, "INSERT INTO users (id,tg_id,full_name,role,branch_id) VALUES (?,?,?,?,?)",
        (7002, MGR_TG, "Filial Rahbari", "manager", 71))
    sql(env, "INSERT INTO users (id,tg_id,full_name,role) VALUES (?,?,?,?)",
        (7003, EMP_TG, "Nomzod Ali", "candidate"))


def _staff_reg(env, status="new"):
    sql(env, "INSERT INTO staff_regs (id,user_id,full_name,role,position,branch_id,"
             "branch_name,salary,status) VALUES (?,?,?,?,?,?,?,?,?)",
        (301, 7003, "Valiyev Ali", "pharmacist", "💊 Farmatsevt", 71, "Sinov filiali",
         "4 000 000", status))


# ======================= XODIM SO'ROVI =======================
def test_staff_reg_approve_is_atomic_and_reapprove_restores(env):
    from database import queries as q
    _seed(env)
    _staff_reg(env)
    res = run(env, q.approve_staff_reg, 301, 7001)
    assert res and res["created"] is True
    prof = sql(env, "SELECT * FROM employee_profiles WHERE user_id=7003")
    assert prof and prof[0]["branch_id"] == 71
    assert sql(env, "SELECT role FROM users WHERE id=7003")[0]["role"] == "pharmacist"
    reg = sql(env, "SELECT status, handled_by, handled_at FROM staff_regs WHERE id=301")[0]
    assert reg["status"] == "approved" and reg["handled_by"] == 7001 and reg["handled_at"]
    # Ikkinchi marta oddiy tasdiq — yo'q (atomik)
    assert run(env, q.approve_staff_reg, 301, 7001) is None
    assert len(sql(env, "SELECT * FROM hr_events WHERE user_id=7003")) == 1

    # Xato holat: tasdiqlangan, lekin profil yo'q (eski bug) — ro'yxatda chiqadi
    sql(env, "DELETE FROM employee_profiles WHERE user_id=7003")
    missing = run(env, q.list_staff_regs_missing_profile)
    assert [r["id"] for r in missing] == [301]
    res = env.portal.call(lambda: q.approve_staff_reg(301, 7001,
                                                      allowed=("approved", "rejected")))
    assert res["created"] is True and res["prev_status"] == "approved"
    assert sql(env, "SELECT 1 FROM employee_profiles WHERE user_id=7003")
    assert run(env, q.list_staff_regs_missing_profile) == []


def test_staff_reg_approve_rolls_back_on_error(env, monkeypatch):
    from database import queries as q
    _seed(env)
    _staff_reg(env)

    async def boom(*a, **kw):
        raise RuntimeError("database is locked")

    monkeypatch.setattr(q, "_upsert_profile_tx", boom)
    with pytest.raises(RuntimeError):
        run(env, q.approve_staff_reg, 301, 7001)
    # Hech narsa yozilmadi — so'rov «yangi» bo'lib qoldi, qayta tasdiqlash mumkin
    assert sql(env, "SELECT status FROM staff_regs WHERE id=301")[0]["status"] == "new"
    assert sql(env, "SELECT role FROM users WHERE id=7003")[0]["role"] == "candidate"


def test_dismissed_employee_reapproved_is_rehired(env):
    from database import queries as q
    _seed(env)
    _staff_reg(env)
    run(env, q.approve_staff_reg, 301, 7001)
    env.portal.call(lambda: q.fire_employee(7003, reason="test", dismissed_by=7001))
    assert run(env, q.list_staff_regs_missing_profile) == []   # bo'shatilgan — xato emas
    pres = run(env, q.employee_presence, 7003)
    from utils import employee_state
    assert employee_state(pres)[0] == "dismissed"
    res = env.portal.call(lambda: q.approve_staff_reg(301, 7001,
                                                      allowed=("approved", "rejected")))
    assert res["created"] is True
    assert sql(env, "SELECT rehired FROM dismissed_employees WHERE user_id=7003")[0]["rehired"] == 1


def test_handled_staff_reg_card_shows_who_and_reapprove_button(env):
    from handlers import staffreg
    _seed(env)
    _staff_reg(env)
    bot = FakeBot()
    call = FakeCall(HR_TG, "sracc:301")
    env.portal.call(lambda: staffreg.sr_approve(call, bot))
    # Boshqa HR eski xabardagi «✅ Tasdiqlash» ni bosdi
    call2 = FakeCall(HR_TG, "sracc:301")
    env.portal.call(lambda: staffreg.sr_approve(call2, bot))
    assert "HR Xodimi" in call2.alerts[0]
    card = call2.message.answers[-1]
    assert "Tasdiqladi" in card["text"] and "HR Xodimi" in card["text"]
    assert "sragain:301" in buttons(card["markup"])
    # Boshidan tasdiqlash: so'rov → tasdiq
    ask = FakeCall(HR_TG, "sragain:301")
    env.portal.call(lambda: staffreg.sr_reapprove_ask(ask))
    assert "sragok:301" in buttons(ask.message.answers[-1]["markup"])
    ok = FakeCall(HR_TG, "sragok:301")
    env.portal.call(lambda: staffreg.sr_reapprove_do(ok, bot))
    assert any("Boshidan tasdiqlandi" in a["text"] for a in ok.message.answers)


# ======================= ARIZA → SINOV =======================
def _application(env, aid=401, status="interview"):
    sql(env, "INSERT INTO applications (id,user_id,full_name,position,branch_id,status,phone)"
             " VALUES (?,?,?,?,?,?,?)",
        (aid, 7003, "Valiyev Ali", "Farmatsevt", 71, status, "+998901112233"))


def test_trial_accept_waits_for_arrival_then_adds_employee(env):
    from database import queries as q
    _seed(env)
    _application(env)
    res = env.portal.call(lambda: q.accept_application_tx(
        401, 7001, "trial", "pharmacist", 71, start_iso="2026-10-20",
        end_iso="2026-11-03", days=15, want_defer=True))
    assert res["defer"] is True and res["created"] is False
    assert not sql(env, "SELECT 1 FROM employee_profiles WHERE user_id=7003")
    assert sql(env, "SELECT status FROM probations WHERE id=?", (res["pid"],))[0]["status"] == "awaiting"
    # Ikkinchi qabul — yo'q
    assert env.portal.call(lambda: q.accept_application_tx(
        401, 7001, "trial", "pharmacist", 71, want_defer=True)) is None
    arr = run(env, q.confirm_probation_arrival, res["pid"], 7002, "pharmacist")
    assert arr["created"] is True
    prof = sql(env, "SELECT emp_status FROM employee_profiles WHERE user_id=7003")[0]
    assert prof["emp_status"] == "trial"
    assert run(env, q.confirm_probation_arrival, res["pid"], 7002, "pharmacist") is None
    p = run(env, q.get_probation, res["pid"])
    assert p["arrived_by_name"] == "Filial Rahbari" and p["created_by_name"] == "HR Xodimi"


def test_reaccept_replaces_open_probation(env):
    from database import queries as q
    _seed(env)
    _application(env)
    first = env.portal.call(lambda: q.accept_application_tx(
        401, 7001, "trial", "pharmacist", 71, start_iso="2026-10-20",
        end_iso="2026-11-03", days=15, want_defer=True))
    again = env.portal.call(lambda: q.accept_application_tx(
        401, 7001, "hire", "pharmacist", 71, start_iso="2026-10-22", reaccept=True))
    assert again["old_pids"] == [first["pid"]] and again["created"] is True
    assert sql(env, "SELECT status FROM probations WHERE id=?", (first["pid"],))[0]["status"] == "replaced"
    assert sql(env, "SELECT emp_status FROM employee_profiles WHERE user_id=7003")[0]["emp_status"] == "regular"
    assert sql(env, "SELECT accept_kind FROM applications WHERE id=401")[0]["accept_kind"] == "hire"


def test_old_accept_button_on_accepted_app_shows_status_not_flow(env):
    from handlers import hr
    _seed(env)
    _application(env, status="accepted")
    sql(env, "UPDATE applications SET handled_by=7001, accept_kind='trial' WHERE id=401")

    class FakeState:
        def __init__(self):
            self.data, self.st = {}, None

        async def set_state(self, s):
            self.st = s

        async def update_data(self, **kw):
            self.data.update(kw)

    st = FakeState()
    call = FakeCall(HR_TG, "apptrial:401")
    env.portal.call(lambda: hr.app_accept_trial(call, st))
    assert st.st is None                       # qabul oqimi BOSHLANMADI
    assert "HR Xodimi" in call.alerts[0]
    block = call.message.answers[-1]
    assert "YO'Q" in block["text"]             # qabul qilingan, ro'yxatda yo'q
    assert "appagain:401" in buttons(block["markup"])


def test_finalize_accept_falls_back_to_hr_when_manager_unreachable(env):
    from handlers import hr
    _seed(env)
    _application(env)
    bot = FakeBot()

    async def no_manager_delivery(*a, **kw):
        return 0

    import handlers.hr as hrmod
    orig = hrmod.broadcast_request
    hrmod.broadcast_request = no_manager_delivery
    try:
        msg = FakeMessage(HR_TG)
        me = {"id": 7001, "full_name": "HR Xodimi"}
        env.portal.call(lambda: hr._finalize_accept(
            bot, msg, me, 401, 71, "2026-10-20", "trial", shift="🌞 Ertalabgi smena"))
    finally:
        hrmod.broadcast_request = orig
    fallback = [a for a in msg.answers if "yetib bormadi" in a["text"]]
    assert fallback, [a["text"] for a in msg.answers]
    assert any(b.startswith("probarr:ok:") for b in buttons(fallback[0]["markup"]))


# ======================= SINOV MUDDATI PANELI =======================
def test_probation_panel_buckets_and_newest_finished_first(env):
    from database import queries as q
    from handlers import hr
    from utils import today_tk
    _seed(env)
    today = today_tk()

    def iso(d):
        return (today + timedelta(days=d)).isoformat()

    users = []
    for i in range(14):
        uid = 7100 + i
        users.append(uid)
        sql(env, "INSERT INTO users (id,tg_id,full_name,role) VALUES (?,?,?,?)",
            (uid, 820000 + i, f"Xodim {i:02d}", "pharmacist"))
        sql(env, "INSERT INTO employee_profiles (user_id,role,position,branch_id) "
                 "VALUES (?,?,?,?)", (uid, "pharmacist", "Farmatsevt", 71))
    # 12 ta eski tugagan (finished), eng yangisi — kecha
    for i in range(12):
        sql(env, "INSERT INTO probations (user_id,branch_id,full_name,start_date,end_date,"
                 "status) VALUES (?,?,?,?,?,?)",
            (users[i], 71, f"Xodim {i:02d}", iso(-60), iso(-40 + i * 3), "finished"))
    sql(env, "UPDATE probations SET end_date=? WHERE full_name='Xodim 11'", (iso(-1),))
    sql(env, "INSERT INTO probations (user_id,branch_id,full_name,start_date,end_date,status)"
             " VALUES (?,?,?,?,?,?)", (users[12], 71, "Yaqin", iso(-12), iso(2), "active"))
    sql(env, "INSERT INTO probations (user_id,branch_id,full_name,start_date,end_date,status)"
             " VALUES (?,?,?,?,?,?)", (users[13], 71, "Uzoq", iso(-2), iso(12), "active"))
    # Profilsiz faol yozuv (bo'shatilgan) — panelda chiqmasligi kerak
    sql(env, "INSERT INTO probations (user_id,branch_id,full_name,start_date,end_date,status)"
             " VALUES (?,?,?,?,?,?)", (7003, 71, "Eski", iso(-5), iso(9), "active"))

    buckets = env.portal.call(hr._probation_buckets)
    assert [p["full_name"] for p in buckets["soon"]] == ["Yaqin"]
    assert [p["full_name"] for p in buckets["active"]] == ["Uzoq"]
    assert len(buckets["ended"]) == 12
    assert buckets["ended"][0]["full_name"] == "Xodim 11"   # eng oxirgi tugagan tepada

    pid = buckets["soon"][0]["id"]
    assert run(env, q.probation_make_permanent, pid, 7001) is True
    assert run(env, q.get_probation, pid)["status"] == "passed"
    ended_pid = buckets["ended"][0]["id"]
    assert run(env, q.probation_extend, ended_pid, iso(7), 70, 7001) is True
    p = run(env, q.get_probation, ended_pid)
    assert p["status"] == "active" and p["hr_end_sent"] == 0


def test_reminder_loop_retires_stale_and_finishes_with_actions(env):
    from services import reminders
    from utils import today_tk
    _seed(env)
    sql(env, "INSERT INTO employee_profiles (user_id,role,position,branch_id) VALUES (?,?,?,?)",
        (7003, "pharmacist", "Farmatsevt", 71))
    sql(env, "INSERT INTO users (id,tg_id,full_name,role) VALUES (?,?,?,?)",
        (7004, 810004, "Ketgan", "candidate"))
    y = (today_tk() - timedelta(days=1)).isoformat()
    sql(env, "INSERT INTO probations (id,user_id,branch_id,full_name,start_date,end_date,status)"
             " VALUES (?,?,?,?,?,?,?)", (901, 7003, 71, "Valiyev Ali", "2026-01-01", y, "active"))
    sql(env, "INSERT INTO probations (id,user_id,branch_id,full_name,start_date,end_date,status)"
             " VALUES (?,?,?,?,?,?,?)", (902, 7004, 71, "Ketgan", "2026-01-01", y, "active"))
    bot = FakeBot()
    env.portal.call(lambda: reminders._check_probations(bot))
    rows = {r["id"]: r for r in sql(env, "SELECT id,status,hr_end_sent FROM probations")}
    assert rows[901]["status"] == "finished" and rows[901]["hr_end_sent"] == 1
    assert rows[902]["status"] == "dismissed"
    ended = [m for m in bot.sent if "tugadi" in (m["text"] or "")]
    assert ended and "probpass:901" in buttons(ended[0]["markup"])
    assert not any("Ketgan" in (m["text"] or "") for m in bot.sent)
