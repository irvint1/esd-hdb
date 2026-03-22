from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import json
import os
import time

app = Flask(__name__)
CORS(app)

# Service URLs - env vars for Docker, localhost for local dev
FLAT_AVAILABILITY_URL = os.environ.get('FLAT_AVAILABILITY_URL', 'http://localhost:5006')
APPLICANT_URL = os.environ.get('APPLICANT_URL', 'http://localhost:5001')
FLAT_SELECTION_URL = os.environ.get('FLAT_SELECTION_URL', 'http://localhost:5002')
NETS_PAYMENT_URL = os.environ.get('NETS_PAYMENT_URL', 'http://localhost:5003')
NOTIFICATION_URL = os.environ.get('NOTIFICATION_URL', 'http://localhost:5004')

RABBITMQ_HOST = os.environ.get('RABBITMQ_HOST', 'localhost')
RABBITMQ_PORT = int(os.environ.get('RABBITMQ_PORT', 5672))
EXCHANGE_NAME = 'flat_allocation'


def publish_event(routing_key, message):
    """
    Publish an event to RabbitMQ (Steps 16a / 20b).
    Falls back to HTTP notification if RabbitMQ is not available.
    """
    try:
        import pika

        connection = pika.BlockingConnection(
            pika.ConnectionParameters(host=RABBITMQ_HOST, port=RABBITMQ_PORT)
        )
        channel = connection.channel()
        channel.exchange_declare(exchange=EXCHANGE_NAME, exchange_type='topic', durable=True)

        channel.basic_publish(
            exchange=EXCHANGE_NAME,
            routing_key=routing_key,
            body=json.dumps(message),
            properties=pika.BasicProperties(delivery_mode=2)  # persistent
        )

        connection.close()
        print(f"[AMQP] Published event: {routing_key}")
        return True

    except Exception as e:
        print(f"[AMQP] Failed to publish: {e}. Falling back to HTTP notification.")
        try:
            event_type = 'flat.confirmed' if 'confirmed' in routing_key else 'payment.failed'
            requests.post(f"{NOTIFICATION_URL}/notify", json={
                "email": message.get('email', ''),
                "phone": message.get('phone', ''),
                "subject": "Flat Confirmed" if event_type == 'flat.confirmed' else "Payment Failed",
                "message": str(message),
                "event_type": event_type
            })
        except:
            pass
        return False


# ============================================================
# POST /select-flat - The main orchestration endpoint
#
# PHASE 1: Initiate payment, return gateway URL for browser redirect
# PHASE 2: Poll for payment result, then reserve + confirm
#
# This is a LONG-RUNNING request (~3 min timeout).
# The frontend opens eNETS in a new tab while this polls.
#
# Body: {
#   "applicant_id": 1,
#   "selection_id": 1,
#   "flat_id": 1,
#   "payment_amount": 2000.00
# }
# ============================================================
@app.route('/select-flat', methods=['POST'])
def select_flat():
    data = request.get_json()

    # Validate input
    required = ['applicant_id', 'selection_id', 'flat_id', 'payment_amount']
    for field in required:
        if not data or field not in data:
            return jsonify({
                "code": 400,
                "message": f"{field} is required."
            }), 400

    applicant_id = data['applicant_id']
    selection_id = data['selection_id']
    flat_id = data['flat_id']
    payment_amount = float(data['payment_amount'])

    print(f"\n{'='*60}")
    print(f"[ORCHESTRATOR] Starting flat selection")
    print(f"  Applicant: {applicant_id}")
    print(f"  Selection: {selection_id}")
    print(f"  Flat: {flat_id}")
    print(f"  Payment: ${payment_amount}")
    print(f"{'='*60}")

    # ----------------------------------------------------------
    # Step 6: Check if selected flat is still available
    # ----------------------------------------------------------
    print(f"\n[Step 6] Checking flat {flat_id} availability...")
    try:
        flat_response = requests.get(f"{FLAT_AVAILABILITY_URL}/flats/{flat_id}")
        flat_data = flat_response.json()
    except Exception as e:
        return jsonify({
            "code": 503,
            "message": f"Flat Availability Service unavailable: {str(e)}"
        }), 503

    if flat_response.status_code != 200:
        return jsonify({
            "code": flat_data.get('code', 404),
            "message": flat_data.get('message', 'Flat not found.')
        }), flat_response.status_code

    flat_info = flat_data['data']
    if flat_info['status'] != 'available':
        print(f"[Step 7b] Flat {flat_id} is NOT available (status: {flat_info['status']})")
        return jsonify({
            "code": 409,
            "message": f"Flat {flat_id} is no longer available. Status: {flat_info['status']}. Please select another flat."
        }), 409

    print(f"[Step 7a] Flat {flat_id} is available")

    # ----------------------------------------------------------
    # Step 12: Initiate payment via NETS Payment Service
    # If merchant_txn_ref is provided, payment was already initiated
    # by the frontend (which opened eNETS in a new tab).
    # ----------------------------------------------------------
    merchant_txn_ref = data.get('merchant_txn_ref')

    if not merchant_txn_ref:
        # Frontend didn't initiate payment yet — do it here
        print(f"\n[Step 12] Initiating payment of ${payment_amount}...")
        try:
            payment_response = requests.post(
                f"{NETS_PAYMENT_URL}/payment",
                json={
                    "applicant_id": applicant_id,
                    "amount": payment_amount,
                    "description": f"BTO Option Fee for Flat {flat_id}"
                }
            )
            payment_data = payment_response.json()
        except Exception as e:
            return jsonify({
                "code": 503,
                "message": f"Payment Service unavailable: {str(e)}"
            }), 503

        if payment_response.status_code != 200:
            return jsonify({
                "code": 402,
                "data": {
                    "applicant_id": applicant_id,
                    "flat_id": flat_id,
                    "status": "payment_failed",
                    "message": "Payment initiation failed."
                }
            }), 402

        merchant_txn_ref = payment_data['data']['merchant_txn_ref']
    else:
        print(f"\n[Step 12] Payment already initiated by frontend. Ref: {merchant_txn_ref}")

    print(f"[Step 13] Payment ref: {merchant_txn_ref}")
    print(f"[Step 13] Waiting for customer to complete payment at eNETS...")

    # ----------------------------------------------------------
    # Step 13: Poll for payment confirmation (up to 3 minutes)
    # The frontend opens eNETS in a new tab while we poll here.
    # ----------------------------------------------------------
    max_attempts = 90       # poll for up to 3 minutes
    poll_interval = 2       # check every 2 seconds
    payment_status = "pending"
    status_data = None

    for attempt in range(max_attempts):
        time.sleep(poll_interval)
        try:
            status_response = requests.get(
                f"{NETS_PAYMENT_URL}/payment/status/{merchant_txn_ref}"
            )
            status_data = status_response.json()
            payment_status = status_data.get('data', {}).get('status', 'pending')

            if attempt % 5 == 0:
                print(f"[Polling {attempt+1}/{max_attempts}] Status: {payment_status}")

            if payment_status in ('success', 'failed', 'cancelled'):
                break
        except Exception as e:
            print(f"[Polling {attempt+1}] Error checking status: {e}")

    # ----------------------------------------------------------
    # Step 15a: Payment SUCCESS -> Reserve flat -> Confirm
    # ----------------------------------------------------------
    if payment_status == 'success':
        print(f"[Step 15a] Payment confirmed!")
        transaction_id = status_data.get('data', {}).get('transaction_id', merchant_txn_ref)

        # Step 8a: Reserve the flat
        print(f"\n[Step 8a] Reserving flat {flat_id}...")
        try:
            reserve_response = requests.put(
                f"{FLAT_AVAILABILITY_URL}/flats/{flat_id}/reserve",
                json={"applicant_id": applicant_id, "selection_id": selection_id}
            )
            reserve_data = reserve_response.json()
        except Exception as e:
            # Payment succeeded but reservation failed - log for manual resolution
            print(f"[ERROR] Payment succeeded but flat reservation failed: {e}")
            return jsonify({
                "code": 500,
                "data": {
                    "applicant_id": applicant_id,
                    "flat_id": flat_id,
                    "transaction_id": transaction_id,
                    "status": "payment_success_reserve_failed",
                    "message": "Payment was successful but flat reservation failed. Please contact HDB support."
                }
            }), 500

        if reserve_response.status_code != 200:
            print(f"[ERROR] Flat reservation failed: {reserve_data.get('message')}")
            return jsonify({
                "code": 409,
                "data": {
                    "applicant_id": applicant_id,
                    "flat_id": flat_id,
                    "transaction_id": transaction_id,
                    "status": "payment_success_reserve_failed",
                    "message": f"Payment successful but flat is no longer available. Refund will be processed. {reserve_data.get('message', '')}"
                }
            }), 409

        print(f"[Step 9] Flat reserved successfully")

        # Step 10: Update flat selection record
        print(f"\n[Step 10] Updating flat selection {selection_id}...")
        try:
            app_response = requests.put(
                f"{FLAT_SELECTION_URL}/flat-selection/{selection_id}/reserve",
                json={"flat_id": flat_id}
            )
        except Exception as e:
            print(f"[WARNING] Selection update failed: {e}")

        # Get applicant details for notification
        try:
            applicant_resp = requests.get(f"{APPLICANT_URL}/applicant/{applicant_id}")
            applicant_info = applicant_resp.json().get('data', {})
        except:
            applicant_info = {}

        # Step 16a: Publish FlatConfirmed event
        print(f"[Step 16a] Publishing FlatConfirmed event...")
        publish_event('flat.confirmed', {
            "applicant_id": applicant_id,
            "flat_id": flat_id,
            "transaction_id": transaction_id,
            "amount": payment_amount,
            "email": applicant_info.get('email', ''),
            "phone": applicant_info.get('mobile_number', '')
        })

        # Step 17a: Return success
        print(f"\n[Step 17a] Returning success to portal")
        return jsonify({
            "code": 200,
            "data": {
                "applicant_id": applicant_id,
                "flat_id": flat_id,
                "flat_details": flat_info,
                "transaction_id": transaction_id,
                "payment_amount": payment_amount,
                "status": "confirmed",
                "message": "Flat selection confirmed. Payment processed successfully."
            }
        }), 200

    # ----------------------------------------------------------
    # Step 15b: Payment FAILED or TIMEOUT
    # ----------------------------------------------------------
    else:
        reason = "Payment timed out (3 minutes)" if payment_status == "pending" else f"Payment {payment_status}"
        print(f"[Step 15b] {reason}!")

        # Get applicant details for notification
        try:
            applicant_resp = requests.get(f"{APPLICANT_URL}/applicant/{applicant_id}")
            applicant_info = applicant_resp.json().get('data', {})
        except:
            applicant_info = {}

        # Publish PaymentFailed event
        print(f"[Step 20b] Publishing PaymentFailed event...")
        publish_event('payment.failed', {
            "applicant_id": applicant_id,
            "flat_id": flat_id,
            "amount": payment_amount,
            "reason": reason,
            "email": applicant_info.get('email', ''),
            "phone": applicant_info.get('mobile_number', '')
        })

        print(f"\n[Step 21b] Returning failure to portal")
        return jsonify({
            "code": 402,
            "data": {
                "applicant_id": applicant_id,
                "flat_id": flat_id,
                "status": "payment_failed",
                "message": f"{reason}. Please try again."
            }
        }), 402


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5005, debug=True)
