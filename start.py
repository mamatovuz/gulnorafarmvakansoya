"""Railway / production uchun yagona Start Command:  python start.py

Bitta servisda ikkita alohida jarayon ishga tushadi:
  * bot   — python bot.py      (avvalgidek, o'zgarishsiz)
  * API   — python -m api      (REST API, Railway $PORT da)

Qoidalar (bot ishiga ta'sir qilmaslik uchun):
  1. Avval DB migratsiyasi BIR MARTA shu yerda bajariladi (bot va API bir vaqtda
     ALTER TABLE qilib to'qnashmasligi uchun). Xato bo'lsa — bot baribir ishga
     tushadi, faqat API o'tkazib yuboriladi.
  2. API yiqilsa — faqat API qayta ishga tushiriladi (kechikish bilan), bot to'xtamaydi.
  3. Bot jarayoni tugasa — start.py ham o'sha kod bilan chiqadi, Railway servisni
     qayta ishga tushiradi (avvalgi `python bot.py` xatti-harakati bilan bir xil).
  4. SIGTERM (Railway deploy/stop) — ikkala jarayon ham to'g'ri to'xtatiladi.

O'chirib-yoqish (kod o'zgartirmasdan, Railway Variables orqali):
  START_API=0  — faqat bot ishlaydi (avvalgi holat)
  START_BOT=0  — faqat API (test uchun)
"""
import asyncio
import logging
import os
import signal
import subprocess
import sys
import time

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s | %(levelname)s | start | %(message)s")
log = logging.getLogger("start")

PY = sys.executable
BOT_CMD = [PY, "bot.py"]
API_CMD = [PY, "-m", "api"]


def _flag(name, default=True):
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def migrate():
    """Bot + API sxemasini ketma-ket, bir marta yaratadi/yangilaydi."""
    from api.migrations import run_migrations
    from config import DB_PATH
    asyncio.run(run_migrations(DB_PATH))


class Supervisor:
    def __init__(self, run_bot, run_api):
        self.run_bot = run_bot
        self.run_api = run_api
        self.bot = None
        self.api = None
        self.stopping = False
        self.api_failures = 0
        self.api_next_start = 0.0

    def start_bot(self):
        log.info("Bot ishga tushirilmoqda: %s", " ".join(BOT_CMD[1:]))
        self.bot = subprocess.Popen(BOT_CMD)

    def start_api(self):
        log.info("REST API ishga tushirilmoqda (port=%s)", os.getenv("PORT") or os.getenv("API_PORT") or 8090)
        self.api = subprocess.Popen(API_CMD)
        self.api_started_at = time.monotonic()

    def stop(self, *_):
        if self.stopping:
            return
        self.stopping = True
        log.info("To'xtatish signali — jarayonlar yopilmoqda...")
        for proc in (self.api, self.bot):
            if proc and proc.poll() is None:
                proc.terminate()
        deadline = time.monotonic() + 20
        for proc in (self.api, self.bot):
            if proc:
                try:
                    proc.wait(timeout=max(0.1, deadline - time.monotonic()))
                except subprocess.TimeoutExpired:
                    proc.kill()

    def loop(self):
        if self.run_bot:
            self.start_bot()
        if self.run_api:
            self.start_api()
        while not self.stopping:
            time.sleep(1)
            if self.bot and self.bot.poll() is not None:
                code = self.bot.returncode
                log.error("Bot jarayoni tugadi (kod=%s) — servis qayta ishga tushadi.", code)
                self.stop()
                return code or 1
            if self.api and self.api.poll() is not None and not self.stopping:
                code = self.api.returncode
                if time.monotonic() - self.api_started_at > 120:
                    self.api_failures = 0  # uzoq ishlagan — hisobni nollaymiz
                self.api_failures += 1
                delay = min(300, 5 * 2 ** (self.api_failures - 1))
                log.error("API jarayoni tugadi (kod=%s). %s s dan keyin qayta ishga tushadi. "
                          "Bot ishlashda davom etadi.", code, delay)
                self.api = None
                self.api_next_start = time.monotonic() + delay
            if self.run_api and self.api is None and time.monotonic() >= self.api_next_start:
                self.start_api()
            if not self.run_bot and self.api is None and not self.run_api:
                return 0
        return 0


def main():
    run_bot = _flag("START_BOT", True)
    run_api = _flag("START_API", True)
    if run_api:
        try:
            migrate()
            log.info("DB migratsiya tayyor.")
        except Exception:
            log.exception("DB migratsiyada xato — API o'tkazib yuboriladi, bot ishga tushadi.")
            run_api = False
    sup = Supervisor(run_bot, run_api)
    signal.signal(signal.SIGTERM, sup.stop)
    signal.signal(signal.SIGINT, sup.stop)
    sys.exit(sup.loop())


if __name__ == "__main__":
    main()
