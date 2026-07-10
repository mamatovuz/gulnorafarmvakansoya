"""Konfiguratsiya - .env fayldan sozlamalarni o'qiydi."""
import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

_admins_raw = os.getenv("SUPER_ADMINS", "").strip()
SUPER_ADMINS = [
    int(x) for x in _admins_raw.replace(" ", "").split(",") if x.strip().isdigit()
]

DB_PATH = os.getenv("DB_PATH", "hrbot.db").strip()

if not BOT_TOKEN:
    raise RuntimeError(
        "BOT_TOKEN topilmadi! .env faylni yarating (.env.example dan nusxa oling) "
        "va BOT_TOKEN qiymatini kiriting."
    )
