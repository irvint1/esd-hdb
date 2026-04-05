from __future__ import annotations

import json
import os

import pika
from dotenv import load_dotenv
from twilio.rest import Client

load_dotenv()


def get_rabbitmq_connection() -> pika.BlockingConnection:
    host = os.getenv("RABBITMQ_HOST")
    port = int(os.getenv("RABBITMQ_PORT", "5672"))
    username = os.getenv("RABBITMQ_USERNAME")
    password = os.getenv("RABBITMQ_PASSWORD")
    vhost = os.getenv("RABBITMQ_VHOST", "/")

    credentials = pika.PlainCredentials(username, password)
    parameters = pika.ConnectionParameters(
        host=host,
        port=port,
        virtual_host=vhost,
        credentials=credentials,
        heartbeat=600,
        blocked_connection_timeout=300,
    )
    return pika.BlockingConnection(parameters)


def send_email(to_email: str, subject: str, body: str) -> None:
    print(f"[EMAIL] To: {to_email} | Subject: {subject} | Body: {body}")


def send_sms(to_mobile: str, message: str) -> None:
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    from_number = os.getenv("TWILIO_FROM_NUMBER")

    client = Client(account_sid, auth_token)
    client.messages.create(
        body=message,
        from_=from_number,
        to=to_mobile
    )
    print(f"[SMS ✓] Sent to {to_mobile}")


def callback(ch, method, properties, body):
    try:
        message = json.loads(body.decode("utf-8"))

        event_type = message.get("eventType")
        email = message.get("email")
        mobile = message.get("mobile")
        text = message.get("message", "Notification received.")

        if event_type == "FlatConfirmed":
            subject = "Flat Selection Confirmed"
        elif event_type == "PaymentFailed":
            subject = "Payment Failed – Please Retry"
        else:
            subject = "BTO Notification"

        if email:
            send_email(email, subject, text)
        if mobile:
            send_sms(mobile, text)

        print(f"[✓] Processed event: {event_type}")
        ch.basic_ack(delivery_tag=method.delivery_tag)

    except Exception as e:
        print(f"[X] Failed: {e}")
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)


def main():
    connection = get_rabbitmq_connection()
    channel = connection.channel()

    exchange = "bto"
    queue_name = "hdb_notification_queue"

    channel.exchange_declare(exchange=exchange, exchange_type="topic", durable=True)
    channel.queue_declare(queue=queue_name, durable=True)
    channel.queue_bind(exchange=exchange, queue=queue_name, routing_key="flat.confirmed")
    channel.queue_bind(exchange=exchange, queue=queue_name, routing_key="payment.failed")

    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue=queue_name, on_message_callback=callback)

    print(f"[*] Waiting for messages on '{queue_name}'... Press CTRL+C to stop.")
    channel.start_consuming()


if __name__ == "__main__":
    main()