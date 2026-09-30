"""API testlari uchun umumiy fixture'lar.

Har bir test alohida vaqtinchalik SQLite bazada ishlaydi (haqiqiy hrbot.db ga
tegilmaydi). Telegram yuborish va webhook HTTP so'rovlari mock qilinadi.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# config.py import qilinishidan OLDIN — haqiqiy token/adminlar ishlatilmasin
os.environ["BOT_TOKEN"] = "123456:TEST-TOKEN"
os.environ["SUPER_ADMINS"] = "999000111"
os.environ["API_WORKERS_ENABLED"] = "0"
os.environ["API_TELEGRAM_SEND_ENABLED"] = "0"
os.environ["INTEGRATION_INBOUND_SECRET"] = "inbound-test-secret"
os.environ["WEBHOOK_BACKOFF_BASE_SECONDS"] = "30"
os.environ["WEBHOOK_MAX_ATTEMPTS"] = "3"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


class Sent:
    def __init__(self):
        self.messages = []
        self.fail_ids = set()

    async def __call__(self, chat_id, text, reply_markup=None):
        if chat_id in self.fail_ids:
            raise RuntimeError("Forbidden: bot was blocked by the user")
        self.messages.append({"chat_id": chat_id, "text": text, "markup": reply_markup})
        return 1000 + len(self.messages)


@pytest.fixture
def env(tmp_path, monkeypatch):
    import config
    from database import db as botdb
    from database import queries as q
    dbfile = str(tmp_path / "test.db")
    for mod in (config, botdb, q):
        monkeypatch.setattr(mod, "DB_PATH", dbfile)
    monkeypatch.setattr(config, "SUPER_ADMINS", [999000111])
    monkeypatch.setattr(botdb, "SUPER_ADMINS", [999000111])
    monkeypatch.setattr(q, "SUPER_ADMINS", [999000111])
    from api import services, security, telegram, webhooks
    monkeypatch.setattr(services, "SUPER_ADMINS", [999000111])
    security.rate_limiter.reset()
    security._last_used_cache.clear()
    sent = Sent()
    telegram.set_sender(sent)
    from api.main import create_app
    app = create_app()
    with TestClient(app) as client:
        client.sent = sent
        client.dbfile = dbfile
        yield client
    telegram.set_sender(None)
    webhooks.set_http_client(None)


def make_key(client, scopes, name="staffora", **kw):
    from api.security import create_api_key
    row, raw = client.portal.call(lambda: create_api_key(name, scopes, **kw))
    return raw, row


@pytest.fixture
def admin_headers(env):
    raw, _ = make_key(env, ["admin"], name="admin")
    return {"Authorization": f"Bearer {raw}"}


def run(client, coro_fn, *args):
    return client.portal.call(coro_fn, *args)


def sql(client, query, params=()):
    import sqlite3
    con = sqlite3.connect(client.dbfile)
    con.row_factory = sqlite3.Row
    try:
        cur = con.execute(query, params)
        rows = [dict(r) for r in cur.fetchall()]
        con.commit()
        return rows
    finally:
        con.close()
