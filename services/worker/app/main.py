from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI
from sqlalchemy import select
from shared.config import RABBITMQ_URL
from shared.database import SessionLocal, init_db
from shared.messaging import publish_event
from shared.models import OutboxEvent
from app.tasks import dispatch_due_escalations_once, handle_event

logger = logging.getLogger("opspulse.worker")
app = FastAPI(title="OpsPulse Worker", version="1.0.0")
_started = False
_start_lock = threading.Lock()


@app.on_event("startup")
def startup():
    global _started
    init_db()
    with _start_lock:
        if _started:
            return
        _started = True
    threading.Thread(target=dispatch_outbox_forever, name="outbox-dispatcher", daemon=True).start()
    threading.Thread(target=dispatch_escalations_forever, name="escalation-scheduler", daemon=True).start()
    if RABBITMQ_URL:
        threading.Thread(target=consume_forever, name="event-consumer", daemon=True).start()


def dispatch_outbox_once(batch_size: int = 25) -> int:
    """Publish pending outbox rows. Rows remain pending and back off on failure."""
    sent = 0
    now = datetime.now(timezone.utc)
    for _ in range(max(1, min(batch_size, 100))):
        with SessionLocal() as db:
            try:
                row = db.scalar(
                    select(OutboxEvent)
                    .where(OutboxEvent.published_at.is_(None), OutboxEvent.available_at <= now)
                    .order_by(OutboxEvent.id)
                    .with_for_update(skip_locked=True)
                    .limit(1)
                )
                if row is None:
                    db.rollback()
                    break
                envelope = {"event_id": row.event_key, "topic": row.topic, **(row.payload or {})}
                row.attempts += 1
                if publish_event(envelope):
                    row.published_at = datetime.now(timezone.utc)
                    row.last_error = ""
                    sent += 1
                else:
                    delay = min(300, 2 ** min(row.attempts, 8))
                    row.available_at = datetime.now(timezone.utc) + timedelta(seconds=delay)
                    row.last_error = "RabbitMQ publish failed; retry scheduled"
                db.commit()
            except Exception:
                db.rollback()
                logger.exception("Outbox dispatch failed")
                break
    return sent


def dispatch_outbox_forever():
    while True:
        try:
            sent = dispatch_outbox_once()
            if sent == 0:
                time.sleep(2)
        except Exception:
            logger.exception("Outbox dispatcher loop failed")
            time.sleep(3)



def dispatch_escalations_forever():
    while True:
        try:
            count = dispatch_due_escalations_once()
            if count == 0:
                time.sleep(3)
        except Exception:
            logger.exception("Escalation scheduler loop failed")
            time.sleep(3)


def consume_forever():
    # Reconnect after broker restarts rather than permanently losing the worker.
    while True:
        connection = None
        try:
            import pika
            connection = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))
            channel = connection.channel()
            channel.queue_declare(queue="opspulse.events", durable=True)
            channel.basic_qos(prefetch_count=10)

            def callback(ch, method, properties, body):
                try:
                    handle_event(json.loads(body))
                    ch.basic_ack(delivery_tag=method.delivery_tag)
                except Exception:
                    logger.exception("Event processing failed; message will be retried")
                    ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)

            channel.basic_consume(queue="opspulse.events", on_message_callback=callback)
            channel.start_consuming()
        except Exception:
            logger.exception("RabbitMQ consumer disconnected; retrying")
            time.sleep(3)
        finally:
            if connection is not None and connection.is_open:
                connection.close()


@app.get("/health")
def health():
    return {"status": "ok", "service": "worker"}


@app.post("/process")
def process(event: dict):
    return {"processed": handle_event(event)}
