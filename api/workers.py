"""Fon ishchilari: webhook tarqatish/yetkazish, e'lon va bildirishnoma yuborish."""
import asyncio
import logging

from api import messaging, settings, telegram, webhooks
from api.core import execute

logger = logging.getLogger("hrbot.api.workers")


async def run_once():
    """Bitta sikl (testlar ham shuni chaqiradi)."""
    await webhooks.fanout_events()
    await webhooks.deliver_due()
    can_send = settings.API_TELEGRAM_SEND_ENABLED or telegram._custom_sender is not None
    if can_send:
        await messaging.send_due_announcements()
        await messaging.send_queued_notifications()


async def _cleanup():
    # 24 soatdan eski idempotency yozuvlari va 30 kunlik yetkazilgan webhooklar
    await execute("DELETE FROM api_idempotency WHERE created_at < datetime('now','+5 hours','-1 day')")
    await execute("DELETE FROM api_webhook_deliveries WHERE status='success' "
                  "AND delivered_at < datetime('now','+5 hours','-30 days')")


async def worker_loop(stop: asyncio.Event):
    tick = 0
    while not stop.is_set():
        try:
            await run_once()
            if tick % 720 == 0:
                await _cleanup()
        except Exception:
            logger.exception("API worker xatosi")
        tick += 1
        try:
            await asyncio.wait_for(stop.wait(), timeout=settings.API_WORKER_INTERVAL_SECONDS)
        except asyncio.TimeoutError:
            pass
