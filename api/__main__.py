"""python -m api  — API serverini ishga tushiradi (bot alohida: python bot.py)."""
import logging

import uvicorn

from api import settings

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    uvicorn.run("api.main:app", host=settings.API_HOST, port=settings.API_PORT,
                proxy_headers=True, forwarded_allow_ips="*",  # Railway proxy ortida real IP/proto
                server_header=False, access_log=True)
