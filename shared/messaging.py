"""RabbitMQ publishing helpers. Durable delivery is driven by the SQL outbox."""
import json
import os


def publish_event(event: dict) -> bool:
    url = os.getenv("RABBITMQ_URL", "")
    if not url:
        return False
    connection = None
    try:
        import pika
        params = pika.URLParameters(url)
        params.connection_attempts = 2
        params.retry_delay = 1
        params.socket_timeout = 5
        connection = pika.BlockingConnection(params)
        channel = connection.channel()
        channel.queue_declare(queue="opspulse.events", durable=True)
        channel.confirm_delivery()
        channel.basic_publish(
            exchange="",
            routing_key="opspulse.events",
            body=json.dumps(event, separators=(",", ":"), ensure_ascii=False).encode("utf-8"),
            properties=pika.BasicProperties(delivery_mode=2, content_type="application/json"),
            mandatory=True,
        )
        return True
    except Exception:
        return False
    finally:
        if connection is not None and connection.is_open:
            connection.close()
