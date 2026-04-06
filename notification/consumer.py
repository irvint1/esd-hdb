from __future__ import annotations

import json
import os

import pika
from dotenv import load_dotenv
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
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
    api_key = os.getenv("SENDGRID_API_KEY")
    from_email = os.getenv("SENDGRID_FROM_EMAIL")

    if not api_key or not from_email:
        raise ValueError("Missing SendGrid environment variables.")

    message = Mail(
        from_email=from_email,
        to_emails=to_email,
        subject=subject,
        plain_text_content=body
    )

    sg = SendGridAPIClient(api_key)
    response = sg.send(message)
    print(f"[EMAIL ✓] Sent to {to_email} | Status: {response.status_code}")


def send_sms(to_mobile: str, message: str) -> None:
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    from_number = os.getenv("TWILIO_FROM_NUMBER")

    client = Client(account_sid, auth_token)
    formatted_mobile = normalize_mobile_for_twilio(to_mobile)
    client.messages.create(
        body=message,
        from_=from_number,
        to=formatted_mobile
    )
    print(f"[SMS ✓] Sent to {formatted_mobile}")


def normalize_mobile_for_twilio(raw_mobile: str) -> str:
    mobile = (raw_mobile or "").strip().replace(" ", "")
    if not mobile:
        raise ValueError("Mobile number is empty.")

    if mobile.startswith("+"):
        return mobile

    if mobile.startswith("65") and len(mobile) == 10 and mobile.isdigit():
        return f"+{mobile}"

    if len(mobile) == 8 and mobile.isdigit():
        return f"+65{mobile}"

    return mobile


def should_skip_external_delivery(email: str | None, mobile: str | None) -> bool:
    normalized_email = (email or "").strip().lower()
    normalized_mobile = (mobile or "").strip().replace(" ", "")
    if normalized_mobile.startswith("+65"):
        normalized_mobile = normalized_mobile[3:]

    return normalized_email == "demo@gmail.com" and normalized_mobile == "00000000"


def callback(ch, method, properties, body):
    try:
        message = json.loads(body.decode("utf-8"))

        event_type = message.get("eventType")
        email = message.get("email")
        mobile = message.get("mobile")
        text = message.get("message", "Notification received.")

        print(
            "[NOTIFY] Received event "
            f"event_type={event_type} "
            f"email={'present' if email else 'missing'} "
            f"mobile={'present' if mobile else 'missing'}"
        )

        custom_subject = message.get("subject")
        if event_type == "FlatConfirmed":
            subject = custom_subject or "Flat Selection Confirmed"
        elif event_type == "PaymentFailed":
            subject = custom_subject or "Payment Failed - Please Retry"
        elif event_type == "FlatBookingQueueAssigned":
            subject = custom_subject or "Flat Selection Queue Number and Appointment Time"
        elif event_type in {"BTOEligibilityPassed", "BTOEligibilityFailed"}:
            subject = custom_subject or "BTO Notification"
        else:
            subject = custom_subject or "BTO Notification"

        # This is so that it does not overwhelm the external API.
        if should_skip_external_delivery(email, mobile):
            print("[NOTIFY] Demo contact values detected; skipping external email/SMS delivery.")
            print(f"[✓] Processed event: {event_type}")
            ch.basic_ack(delivery_tag=method.delivery_tag)
            return

        if not email and not mobile:
            print("[NOTIFY] No email/mobile recipient in payload; nothing to deliver externally.")

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
    channel.queue_bind(exchange=exchange, queue=queue_name, routing_key="application.notify")

    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue=queue_name, on_message_callback=callback)

    print(f"[*] Waiting for messages on '{queue_name}'... Press CTRL+C to stop.")
    channel.start_consuming()


if __name__ == "__main__":
    main()
