"""E'lon (announcement) va bildirishnoma (notification) yuborish — bot orqali.

E'lon `require_ack=true` bo'lsa botning mavjud «🔐 Ishonch xabari» mexanizmi
ishlatiladi: `trust_notices` yozuvi yaratiladi, har bir xabar «✅ Ko'rib chiqdim»
(`trustack:<id>`) tugmasi bilan boradi va botdagi mavjud handler bosilganini
qayd etadi — HR botdagi «📊 Bildirishnoma statistika» da ham ko'radi.
"""
import html
import json
import logging

from database import queries as q

from api import telegram
from api.core import ApiError, connect, execute, fetch_all, now_sql

logger = logging.getLogger("hrbot.api.messaging")


def render(title, message):
    body = html.escape(message or "")
    if title:
        return f"<b>{html.escape(title)}</b>\n\n{body}"
    return body


async def resolve_recipients(target):
    """Target -> [(user_id, tg_id, full_name)] (faqat faol xodimlar, bloklanmagan)."""
    base = """SELECT ep.user_id, u.tg_id, u.full_name FROM employee_profiles ep
                JOIN users u ON u.id=ep.user_id
                LEFT JOIN api_employee_meta m ON m.user_id=ep.user_id
               WHERE COALESCE(u.blocked,0)=0 AND u.tg_id IS NOT NULL"""
    rows = []
    if target.get("send_to_all"):
        rows = await fetch_all(base)
    else:
        conds, params = [], []

        def add_in(col, values):
            if values:
                conds.append(f"{col} IN ({','.join('?' * len(values))})")
                params.extend(values)

        add_in("ep.branch_id", target.get("branch_ids"))
        add_in("m.department_id", target.get("department_ids"))
        add_in("ep.role", target.get("roles"))
        if target.get("position_ids"):
            names = await fetch_all(
                f"SELECT name FROM positions WHERE id IN "
                f"({','.join('?' * len(target['position_ids']))})",
                tuple(target["position_ids"]))
            add_in("ep.position", [n["name"] for n in names] or ["\x00none"])
        if conds:
            rows += await fetch_all(base + " AND " + " AND ".join(conds), tuple(params))
        if target.get("employee_ids"):
            ids = target["employee_ids"]
            rows += await fetch_all(
                base + f" AND ep.user_id IN ({','.join('?' * len(ids))})", tuple(ids))
    seen, out = set(), []
    for r in rows:
        if r["user_id"] not in seen:
            seen.add(r["user_id"])
            out.append((r["user_id"], r["tg_id"], r["full_name"]))
    return out


def target_label(target):
    if target.get("send_to_all"):
        return "barcha xodimlar"
    parts = []
    for key, label in (("branch_ids", "filial"), ("department_ids", "bo'lim"),
                       ("position_ids", "lavozim"), ("roles", "rol"),
                       ("employee_ids", "xodim")):
        if target.get(key):
            parts.append(f"{label}: {','.join(map(str, target[key]))}")
    return "API · " + "; ".join(parts)


async def create_announcement(title, message, target, require_ack, scheduled_at,
                              source, api_key_id):
    recipients = await resolve_recipients(target)
    if not recipients:
        raise ApiError(422, "no_recipients", "Tanlangan mezonlar bo'yicha xodim topilmadi.")
    async with connect() as db:
        cur = await db.execute(
            """INSERT INTO api_announcements (title, message, target, target_label, require_ack,
                   source, scheduled_at, total, api_key_id)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (title, message, json.dumps(target, ensure_ascii=False), target_label(target),
             1 if require_ack else 0, source, scheduled_at, len(recipients), api_key_id),
        )
        aid = cur.lastrowid
        await db.executemany(
            "INSERT OR IGNORE INTO api_announcement_recipients (announcement_id, user_id, tg_id) "
            "VALUES (?,?,?)",
            [(aid, uid, tg) for uid, tg, _ in recipients],
        )
        await db.commit()
    return aid


async def send_announcement(aid):
    """Bitta e'lonni yuboradi (worker chaqiradi). Atomik egallash — ikki marta ketmaydi."""
    async with connect() as db:
        cur = await db.execute(
            "UPDATE api_announcements SET status='sending', updated_at=? "
            "WHERE id=? AND status='scheduled'", (now_sql(), aid))
        await db.commit()
        if cur.rowcount == 0:
            return False
        cur = await db.execute("SELECT * FROM api_announcements WHERE id=?", (aid,))
        ann = dict(await cur.fetchone())

    markup = None
    notice_id = ann.get("trust_notice_id")
    if ann.get("require_ack"):
        import keyboards as kb
        if not notice_id:
            title = (ann.get("title") or ann.get("message") or "").strip()
            notice_id = await q.create_trust_notice(
                title[:120], ann.get("target_label"), None, f"API · {ann.get('source') or 'api'}")
            await execute("UPDATE api_announcements SET trust_notice_id=? WHERE id=?",
                          (notice_id, aid))
        markup = kb.trust_ack_kb(notice_id)

    text = render(ann.get("title"), ann.get("message"))
    pending = await fetch_all(
        """SELECT r.*, u.full_name FROM api_announcement_recipients r
             LEFT JOIN users u ON u.id=r.user_id
            WHERE r.announcement_id=? AND r.status='pending'""", (aid,))
    for r in pending:
        ok, mid, err = await telegram.send_text(r["tg_id"], text, reply_markup=markup)
        await execute(
            "UPDATE api_announcement_recipients SET status=?, message_id=?, error=?, sent_at=? "
            "WHERE id=?",
            ("sent" if ok else "failed", mid, err, now_sql() if ok else None, r["id"]))
        if ok and notice_id:
            try:
                await q.add_trust_notice_read(notice_id, r["tg_id"], mid, r.get("full_name"))
            except Exception:
                logger.exception("trust_notice_read yozilmadi")

    async with connect() as db:
        cur = await db.execute(
            "SELECT SUM(status='sent'), SUM(status='failed') FROM api_announcement_recipients "
            "WHERE announcement_id=?", (aid,))
        sent, failed = await cur.fetchone()
        sent, failed = int(sent or 0), int(failed or 0)
        await db.execute(
            "UPDATE api_announcements SET status=?, sent=?, failed=?, sent_at=?, updated_at=? "
            "WHERE id=?",
            ("sent" if sent else "failed", sent, failed, now_sql(), now_sql(), aid))
        await db.commit()
    if notice_id:
        await q.set_trust_notice_total(notice_id, sent)
    await q.add_log(None, f"API · {ann.get('source') or 'api'}", "api_elon",
                    f"#{aid}: {ann.get('target_label')} — {sent} ta")
    return True


async def send_due_announcements():
    rows = await fetch_all(
        "SELECT id FROM api_announcements WHERE status='scheduled' "
        "AND (scheduled_at IS NULL OR scheduled_at<=?) ORDER BY id", (now_sql(),))
    for r in rows:
        try:
            await send_announcement(r["id"])
        except Exception:
            logger.exception("E'lon #%s yuborilmadi", r["id"])
            await execute("UPDATE api_announcements SET status='failed' WHERE id=?", (r["id"],))
    return len(rows)


NOTIFICATION_MAX_ATTEMPTS = 3


async def send_queued_notifications(limit=100):
    rows = await fetch_all(
        "SELECT * FROM api_notifications WHERE status='queued' ORDER BY id LIMIT ?", (limit,))
    for n in rows:
        text = n["message"] if n.get("is_html") else render(n.get("title"), n["message"])
        ok, mid, err = await telegram.send_text(n["tg_id"], text)
        attempts = int(n["attempts"] or 0) + 1
        if ok:
            status = "sent"
        elif attempts >= NOTIFICATION_MAX_ATTEMPTS or err == "telegram_send_disabled":
            status = "failed" if err != "telegram_send_disabled" else "queued"
        else:
            status = "queued"
        if err == "telegram_send_disabled":
            attempts = n["attempts"] or 0
        await execute(
            "UPDATE api_notifications SET status=?, attempts=?, tg_message_id=?, error=?, sent_at=? "
            "WHERE id=?",
            (status, attempts, mid, err, now_sql() if ok else None, n["id"]))
    return len(rows)
