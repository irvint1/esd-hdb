from __future__ import annotations

import json
import os
from typing import Any, Dict

from flask import Flask, jsonify, request
import pika

app = Flask(__name__)


def get_rabbitmq_connection() -> pika.BlockingConnection:
    """
    Create and return a RabbitMQ connection using CloudAMQP credentials.
    Environment variables:
      RABBITMQ_HOST
      RABBITMQ_PORT
      RABBITMQ_USERNAME
      RABBITMQ_PASSWORD
      RABBITMQ_VHOST
    """
    host = os.getenv("RABBITMQ_HOST")
    port = int(os.getenv("RABBITMQ_PORT", "5672"))
    username = os.getenv("RABBITMQ_USERNAME")
    password = os.getenv("RABBITMQ_PASSWORD")
    vhost = os.getenv("RABBITMQ_VHOST", "/")

    if not all([host, username, password]):
        raise ValueError("Missing RabbitMQ environment variables.")

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


@app.route("/health", methods=["GET"])
def health() -> Any:
    return jsonify({"status": "ok"}), 200


@app.route("/publish", methods=["POST"])
def publish_message() -> Any:
    """
    Expected JSON body:
    {
    "exchange": "bto",
    "exchange_type": "topic",
    "routing_key": "flat.confirmed",
    "queue_name": "hdb_notification_queue",
    "payload": {
        "eventType": "FlatConfirmed",
        "applicationId": "A12345",
        "applicantId": "CUST001",
        "email": "user@example.com",
        "mobile": "+6591234567",
        "flatId": "BTO-1001",
        "projectName": "Toa Payoh Ridge",
        "message": "Your flat selection has been confirmed."
    }
    }
    """
    try:
        data: Dict[str, Any] = request.get_json(force=True)

        exchange = data.get("exchange", "bto")
        exchange_type = data.get("exchange_type", "topic")
        routing_key = data.get("routing_key", "flat.confirmed")
        queue_name = data.get("queue_name")
        payload = data.get("payload")

        if payload is None:
            return jsonify({"error": "Missing 'payload' field."}), 400

        # Convert payload into JSON string if object was passed
        if isinstance(payload, (dict, list)):
            body = json.dumps(payload)
        else:
            body = str(payload)

        connection = get_rabbitmq_connection()
        channel = connection.channel()

        # Declare exchange
        channel.exchange_declare(
            exchange=exchange,
            exchange_type=exchange_type,
            durable=True
        )

        # Queue declare + bind
        if queue_name:
            channel.queue_declare(queue=queue_name, durable=True)
            channel.queue_bind(
                exchange=exchange,
                queue=queue_name,
                routing_key=routing_key
            )

        channel.basic_publish(
            exchange=exchange,
            routing_key=routing_key,
            body=body,
            properties=pika.BasicProperties(
                delivery_mode=2,  # make message persistent
                content_type="application/json"
            )
        )

        connection.close()

        return jsonify({
            "status": "success",
            "message": "Message published successfully."
        }), 200

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)