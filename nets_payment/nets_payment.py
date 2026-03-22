from flask import Flask, request, jsonify, redirect
from flask_cors import CORS
from dotenv import load_dotenv
import hashlib
import hmac
import base64
import json
import requests as http_requests
import os
import uuid
from datetime import datetime

# Load .env file
load_dotenv()

app = Flask(__name__)
CORS(app)

# ============================================================
# NETS Payment Service - eNETS Integration (Transaction Flow 1 - B2S)
#
# This is a WRAPPER service for the external eNETS Payment API.
# It uses Transaction Flow 1 (Browser-to-Server) for Credit Card
# payments, where NETS hosts the card capture page.
#
# Diagram steps:
#   12. Flat Allocation -> NETS Payment Service (HTTP POST)
#   13. NETS Payment Service -> eNETS Gateway (HTTPS redirect)
#   14. eNETS Gateway -> NETS Payment Service (s2sTxnEnd callback)
#   15a/15b. NETS Payment Service -> Flat Allocation (HTTP response)
#
# Environment variables (set in docker-compose.yml or .env):
#   NETS_API_KEY_ID    - API KeyId from NETS
#   NETS_SECRET_KEY    - Secret Key from NETS
#   NETS_MID           - Merchant ID (UMID)
#   NETS_ENVIRONMENT   - 'uat' or 'production'
#   NETS_CALLBACK_BASE - Base URL for callbacks (e.g. http://localhost:5003)
# ============================================================

# ----- Configuration -----
NETS_API_KEY_ID = os.environ.get('NETS_API_KEY_ID', 'your-api-key-id')
NETS_SECRET_KEY = os.environ.get('NETS_SECRET_KEY', 'your-secret-key')
NETS_MID = os.environ.get('NETS_MID', 'your-umid')
NETS_ENVIRONMENT = os.environ.get('NETS_ENVIRONMENT', 'uat')
NETS_CALLBACK_BASE = os.environ.get('NETS_CALLBACK_BASE', 'http://localhost:5003')

# eNETS Gateway URLs
ENETS_URLS = {
    'uat': 'https://uat2.enets.sg/GW2/TxnReqListener',
    'production': 'https://www2.enets.sg/GW2/TxnReqListener'
}

ENETS_QUERY_URLS = {
    'uat': 'https://uat2.enets.sg/GW2/TxnQueryListener',
    'production': 'https://www2.enets.sg/GW2/TxnQueryListener'
}

# In-memory store for payment status tracking
# In production, use a database (Redis, MySQL, etc.)
payment_records = {}


def get_enets_url():
    """Get the eNETS gateway URL based on environment."""
    return ENETS_URLS.get(NETS_ENVIRONMENT, ENETS_URLS['uat'])


def get_enets_query_url():
    """Get the eNETS query URL based on environment."""
    return ENETS_QUERY_URLS.get(NETS_ENVIRONMENT, ENETS_QUERY_URLS['uat'])


def generate_merchant_txn_ref():
    """Generate a unique merchant transaction reference (max 20 chars)."""
    # Format: HDB + timestamp + random suffix
    timestamp = datetime.now().strftime('%y%m%d%H%M%S')
    suffix = uuid.uuid4().hex[:4].upper()
    return f"HDB{timestamp}{suffix}"[:20]


def compute_hmac(payload_json, secret_key):
    hmac_digest = hmac.new(
        secret_key.encode('utf-8'),
        payload_json.encode('utf-8'),
        hashlib.sha256
    ).digest()
    return base64.b64encode(hmac_digest).decode('utf-8')


def build_txn_req(amount_cents, merchant_txn_ref, description, currency='SGD'):
    """
    Build the eNETS TxnReq payload for Transaction Flow 1 (B2S).
    
    Uses Credit Card (CC) payment mode with Browser submission.
    NETS will host the credit card capture page.
    
    Args:
        amount_cents: Amount in cents (e.g., 200000 for $2000.00)
        merchant_txn_ref: Unique transaction reference (max 20 chars)
        description: Payment description
        currency: Currency code (default SGD)
    
    Returns:
        dict with 'payload' (JSON string) and 'hmac' (signature)
    """
    now = datetime.now()

    txn_req = {
        "ss": "1",
        "msg": {
            "netsMid": NETS_MID,
            "tid": "",
            "submissionMode": "B",
            "txnAmount": str(amount_cents),
            "merchantTxnRef": merchant_txn_ref,
            "merchantTxnDtm": now.strftime('%Y%m%d %H:%M:%S.000'),
            "paymentType": "SALE",
            "paymentMode": "",
            "currencyCode": currency,
            "merchantTimeZone": "+8:00",
            "b2sTxnEndURL": f"{NETS_CALLBACK_BASE}/payment/b2s-callback",
            "b2sTxnEndURLParam": "",
            "s2sTxnEndURL": f"{NETS_CALLBACK_BASE}/payment/s2s-callback",
            "s2sTxnEndURLParam": "",
            "clientType": "W",
            "supMsg": "",
            "netsMidIndicator": "U",
            "ipAddress": "",
            "language": "en"
        }
    }

    payload_json = json.dumps(txn_req, separators=(',', ':'))
    signature = compute_hmac(payload_json, NETS_SECRET_KEY)

    return {
        "payload": payload_json,
        "hmac": signature
    }


def parse_txn_end(txn_end_data):
    """
    Parse the TxnEnd response from eNETS (both b2s and s2s callbacks).
    
    Key fields:
        netsTxnStatus: 0=success, 1=failed, 9=cancelled
        stageRespCode: Detailed response code (e.g., 00000=success)
        netsTxnRef: NETS transaction reference
        netsTxnMsg: Human-readable transaction message
        actionCode: Next action (0=none, 1=retry, 2=query, 3=setup error)
    """
    # The TxnEnd data comes as a JSON payload from eNETS
    if isinstance(txn_end_data, str):
        try:
            txn_end_data = json.loads(txn_end_data)
        except json.JSONDecodeError:
            return None

    msg = txn_end_data.get('msg', txn_end_data)

    return {
        "netsMid": msg.get('netsMid', ''),
        "merchantTxnRef": msg.get('merchantTxnRef', ''),
        "netsTxnRef": msg.get('netsTxnRef', ''),
        "netsTxnStatus": msg.get('netsTxnStatus', ''),
        "netsTxnMsg": msg.get('netsTxnMsg', ''),
        "netsTxnDtm": msg.get('netsTxnDtm', ''),
        "stageRespCode": msg.get('stageRespCode', ''),
        "actionCode": msg.get('actionCode', ''),
        "netsAmountDeducted": msg.get('netsAmountDeducted', '0'),
        "currencyCode": msg.get('currencyCode', 'SGD'),
        "paymentMode": msg.get('paymentMode', ''),
        "bankAuthId": msg.get('bankAuthId', ''),
        "maskPan": msg.get('maskPan', '')
    }


# ============================================================
# POST /payment/initiate - Initiate a payment (Step 12)
#
# Called by Flat Allocation Service.
# Returns the eNETS gateway URL and signed payload so the
# HDB Portal can redirect the customer's browser to NETS.
#
# Body: {
#   "applicant_id": "APP-2025-001",
#   "amount": 2000.00,
#   "description": "BTO Option Fee for Flat 101"
# }
# ============================================================
@app.route('/payment/initiate', methods=['POST'])
def initiate_payment():
    data = request.get_json()

    # Validate required fields
    required = ['applicant_id', 'amount']
    for field in required:
        if not data or field not in data:
            return jsonify({
                "code": 400,
                "message": f"{field} is required."
            }), 400

    applicant_id = data['applicant_id']
    amount = float(data['amount'])
    description = data.get('description', 'BTO Option Fee')

    if amount <= 0:
        return jsonify({
            "code": 400,
            "message": "Amount must be greater than 0."
        }), 400

    try:
        # Convert to cents (eNETS uses cents)
        amount_cents = int(amount * 100)
        merchant_txn_ref = generate_merchant_txn_ref()

        # Build the signed TxnReq payload
        txn_data = build_txn_req(amount_cents, merchant_txn_ref, description)

        # Store the payment record for tracking
        payment_records[merchant_txn_ref] = {
            "applicant_id": applicant_id,
            "amount": amount,
            "amount_cents": amount_cents,
            "description": description,
            "merchant_txn_ref": merchant_txn_ref,
            "status": "pending",
            "nets_txn_ref": None,
            "nets_txn_status": None,
            "stage_resp_code": None,
            "created_at": datetime.now().isoformat()
        }

        print(f"[NETS] Payment initiated: {merchant_txn_ref} for ${amount}")

        return jsonify({
            "code": 200,
            "data": {
                "merchant_txn_ref": merchant_txn_ref,
                "gateway_url": get_enets_url(),
                "payload": txn_data['payload'],
                "hmac": txn_data['hmac'],
                "api_key_id": NETS_API_KEY_ID,
                "applicant_id": applicant_id,
                "amount": amount,
                "status": "pending",
                "message": "Payment initiated. Redirect customer to eNETS gateway."
            }
        }), 200

    except Exception as e:
        print(f"[NETS] Error initiating payment: {e}")
        return jsonify({
            "code": 500,
            "message": f"Payment service error: {str(e)}"
        }), 500


# ============================================================
# POST /payment/s2s-callback - Server-to-Server callback (Step 14)
#
# eNETS calls this URL directly (server-to-server) after payment.
# This is the more reliable callback - use this to confirm payment.
# ============================================================
@app.route('/payment/s2s-callback', methods=['POST'])
def s2s_callback():
    try:
        # eNETS sends the TxnEnd data
        raw_data = request.get_data(as_text=True)
        print(f"[NETS s2sTxnEnd] Received: {raw_data}")

        # Parse the callback - could be form data or JSON
        if request.is_json:
            callback_data = request.get_json()
        else:
            # eNETS may send as form-encoded with 'message' field
            message = request.form.get('message', raw_data)
            try:
                callback_data = json.loads(message)
            except:
                callback_data = {"msg": message}

        txn_end = parse_txn_end(callback_data)

        if not txn_end:
            print("[NETS s2sTxnEnd] Failed to parse callback data")
            return "ERROR", 400

        merchant_txn_ref = txn_end['merchantTxnRef']
        nets_txn_status = txn_end['netsTxnStatus']

        print(f"[NETS s2sTxnEnd] Ref: {merchant_txn_ref}, Status: {nets_txn_status}")

        # Update the payment record
        if merchant_txn_ref in payment_records:
            record = payment_records[merchant_txn_ref]

            if nets_txn_status == '0':
                record['status'] = 'success'
            elif nets_txn_status == '1':
                record['status'] = 'failed'
            elif nets_txn_status == '9':
                record['status'] = 'cancelled'
            else:
                record['status'] = 'unknown'

            record['nets_txn_ref'] = txn_end['netsTxnRef']
            record['nets_txn_status'] = nets_txn_status
            record['stage_resp_code'] = txn_end['stageRespCode']
            record['nets_txn_msg'] = txn_end['netsTxnMsg']
            record['bank_auth_id'] = txn_end['bankAuthId']
            record['mask_pan'] = txn_end['maskPan']
            record['updated_at'] = datetime.now().isoformat()

            print(f"[NETS s2sTxnEnd] Updated record: {record['status']}")
        else:
            print(f"[NETS s2sTxnEnd] WARNING: No record found for {merchant_txn_ref}")

        # eNETS expects a simple acknowledgment
        return "OK", 200

    except Exception as e:
        print(f"[NETS s2sTxnEnd] Error: {e}")
        return "ERROR", 500


# ============================================================
# POST /payment/b2s-callback - Browser redirect callback
#
# eNETS redirects the customer's browser here after payment.
# This is a backup - s2sTxnEnd is the primary confirmation.
# We redirect the customer back to the HDB Portal with the result.
# ============================================================
@app.route('/payment/b2s-callback', methods=['POST', 'GET'])
def b2s_callback():
    try:
        # Parse the callback data
        if request.method == 'POST':
            if request.is_json:
                callback_data = request.get_json()
            else:
                message = request.form.get('message', '')
                try:
                    callback_data = json.loads(message)
                except:
                    callback_data = {"msg": message}
        else:
            callback_data = request.args.to_dict()

        txn_end = parse_txn_end(callback_data)
        merchant_txn_ref = txn_end['merchantTxnRef'] if txn_end else 'unknown'
        status = 'unknown'

        if txn_end:
            nets_txn_status = txn_end['netsTxnStatus']
            if nets_txn_status == '0':
                status = 'success'
            elif nets_txn_status == '1':
                status = 'failed'
            elif nets_txn_status == '9':
                status = 'cancelled'

            # Also update record if s2s hasn't arrived yet
            if merchant_txn_ref in payment_records:
                record = payment_records[merchant_txn_ref]
                if record['status'] == 'pending':
                    record['status'] = status
                    record['nets_txn_ref'] = txn_end['netsTxnRef']
                    record['nets_txn_status'] = nets_txn_status
                    record['stage_resp_code'] = txn_end['stageRespCode']
                    record['updated_at'] = datetime.now().isoformat()

        print(f"[NETS b2sTxnEnd] Ref: {merchant_txn_ref}, Status: {status}")

        # Redirect customer back to HDB Portal with result
        portal_url = os.environ.get('HDB_PORTAL_URL', 'http://localhost:3000')
        redirect_url = f"{portal_url}/payment-result?ref={merchant_txn_ref}&status={status}"
        return redirect(redirect_url, code=302)

    except Exception as e:
        print(f"[NETS b2sTxnEnd] Error: {e}")
        portal_url = os.environ.get('HDB_PORTAL_URL', 'http://localhost:3000')
        return redirect(f"{portal_url}/payment-result?status=error", code=302)


# ============================================================
# GET /payment/status/<merchant_txn_ref> - Check payment status
#
# Called by Flat Allocation Service to check if payment completed.
# Since B2S flow is async, the orchestrator needs to poll this.
# ============================================================
@app.route('/payment/status/<merchant_txn_ref>', methods=['GET'])
def check_payment_status(merchant_txn_ref):
    if merchant_txn_ref not in payment_records:
        return jsonify({
            "code": 404,
            "message": "Payment record not found."
        }), 404

    record = payment_records[merchant_txn_ref]

    # Map to the response format flat_allocation.py expects
    if record['status'] == 'success':
        return jsonify({
            "code": 200,
            "data": {
                "applicant_id": record['applicant_id'],
                "amount": record['amount'],
                "transaction_id": record.get('nets_txn_ref', ''),
                "merchant_txn_ref": merchant_txn_ref,
                "status": "success",
                "stage_resp_code": record.get('stage_resp_code', ''),
                "bank_auth_id": record.get('bank_auth_id', ''),
                "mask_pan": record.get('mask_pan', ''),
                "message": record.get('nets_txn_msg', 'Payment processed successfully.')
            }
        }), 200
    elif record['status'] == 'failed':
        return jsonify({
            "code": 402,
            "data": {
                "applicant_id": record['applicant_id'],
                "amount": record['amount'],
                "transaction_id": None,
                "merchant_txn_ref": merchant_txn_ref,
                "status": "failed",
                "stage_resp_code": record.get('stage_resp_code', ''),
                "message": record.get('nets_txn_msg', 'Payment declined.')
            }
        }), 402
    elif record['status'] == 'cancelled':
        return jsonify({
            "code": 402,
            "data": {
                "applicant_id": record['applicant_id'],
                "amount": record['amount'],
                "transaction_id": None,
                "merchant_txn_ref": merchant_txn_ref,
                "status": "cancelled",
                "message": "Payment cancelled by customer."
            }
        }), 402
    else:
        # Still pending
        return jsonify({
            "code": 202,
            "data": {
                "applicant_id": record['applicant_id'],
                "amount": record['amount'],
                "merchant_txn_ref": merchant_txn_ref,
                "status": "pending",
                "message": "Payment is being processed. Please wait."
            }
        }), 202


# ============================================================
# POST /payment/query - Query transaction status from eNETS
#
# Uses TxnQueryReq to check a transaction's status directly
# with the eNETS gateway. Useful if callbacks were missed.
# ============================================================
@app.route('/payment/query', methods=['POST'])
def query_transaction():
    data = request.get_json()

    merchant_txn_ref = data.get('merchant_txn_ref')
    if not merchant_txn_ref:
        return jsonify({
            "code": 400,
            "message": "merchant_txn_ref is required."
        }), 400

    try:
        query_payload = {
            "ss": "1",
            "msg": {
                "netsMid": NETS_MID,
                "merchantTxnRef": merchant_txn_ref,
                "netsMidIndicator": "U"
            }
        }

        payload_json = json.dumps(query_payload, separators=(',', ':'))
        signature = compute_hmac(payload_json, NETS_SECRET_KEY)

        # Call the eNETS TxnQuery API
        headers = {
            'Content-Type': 'application/json',
            'KeyId': NETS_API_KEY_ID,
            'hmac': signature
        }

        response = http_requests.post(
            get_enets_query_url(),
            data=payload_json,
            headers=headers,
            timeout=30
        )

        print(f"[NETS Query] Status: {response.status_code}, Body: {response.text}")

        if response.status_code == 200:
            query_result = response.json()
            return jsonify({
                "code": 200,
                "data": query_result
            }), 200
        else:
            return jsonify({
                "code": response.status_code,
                "message": f"eNETS query failed: {response.text}"
            }), response.status_code

    except Exception as e:
        return jsonify({
            "code": 500,
            "message": f"Query error: {str(e)}"
        }), 500


# ============================================================
# POST /payment - Legacy endpoint (backward compatible)
#
# Keeps the same interface as the old simulated version so
# flat_allocation.py can work without changes during migration.
# This initiates the payment and returns immediately.
# ============================================================
@app.route('/payment', methods=['POST'])
def process_payment_legacy():
    data = request.get_json()

    required = ['applicant_id', 'amount']
    for field in required:
        if not data or field not in data:
            return jsonify({
                "code": 400,
                "message": f"{field} is required."
            }), 400

    applicant_id = data['applicant_id']
    amount = float(data['amount'])
    description = data.get('description', 'BTO Option Fee')

    if amount <= 0:
        return jsonify({
            "code": 400,
            "message": "Amount must be greater than 0."
        }), 400

    try:
        amount_cents = int(amount * 100)
        merchant_txn_ref = generate_merchant_txn_ref()

        txn_data = build_txn_req(amount_cents, merchant_txn_ref, description)

        payment_records[merchant_txn_ref] = {
            "applicant_id": applicant_id,
            "amount": amount,
            "amount_cents": amount_cents,
            "description": description,
            "merchant_txn_ref": merchant_txn_ref,
            "status": "pending",
            "nets_txn_ref": None,
            "created_at": datetime.now().isoformat()
        }

        print(f"[NETS] Legacy payment initiated: {merchant_txn_ref}")

        # Return gateway redirect info
        # The flat_allocation service or portal will handle the redirect
        return jsonify({
            "code": 200,
            "data": {
                "applicant_id": applicant_id,
                "amount": amount,
                "transaction_id": merchant_txn_ref,
                "merchant_txn_ref": merchant_txn_ref,
                "status": "pending",
                "gateway_url": get_enets_url(),
                "payload": txn_data['payload'],
                "hmac": txn_data['hmac'],
                "api_key_id": NETS_API_KEY_ID,
                "message": "Payment initiated. Customer must complete payment at eNETS gateway."
            }
        }), 200

    except Exception as e:
        return jsonify({
            "code": 500,
            "message": f"Payment service error: {str(e)}"
        }), 500


# ============================================================
# GET /payment/records - List all payment records (debug/admin)
# ============================================================
@app.route('/payment/records', methods=['GET'])
def list_records():
    return jsonify({
        "code": 200,
        "data": list(payment_records.values())
    }), 200


if __name__ == '__main__':
    print(f"[NETS Payment Service] Starting...")
    print(f"  Environment: {NETS_ENVIRONMENT}")
    print(f"  MID: {NETS_MID}")
    print(f"  Gateway: {get_enets_url()}")
    print(f"  Callback base: {NETS_CALLBACK_BASE}")
    app.run(host='0.0.0.0', port=5003, debug=True)
