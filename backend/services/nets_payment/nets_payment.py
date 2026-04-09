"""NETS hosted-payment wrapper used by the local HDB demo app."""

from flask import Flask, request, jsonify, redirect, has_request_context
from flask_cors import CORS
from dotenv import load_dotenv
from flasgger import Swagger
import hashlib
import base64
import json
import requests as http_requests
import os
import uuid
import ipaddress
from datetime import datetime
from urllib.parse import parse_qs, unquote_plus

load_dotenv()

app = Flask(__name__)
CORS(app)

app.config['SWAGGER'] = {
    'title': 'NETS Payment Service API',
    'version': 1.0,
    'openapi': '3.0.2',
    'description': (
        'Hosted eNETS payment wrapper for the HDB demo app. '
        'Use /payment/initiate to start a payment, /payment/status/{merchant_txn_ref} '
        'to read the current outcome, and /payment/abandon/{merchant_txn_ref} '
        'to locally cancel an unfinished hosted-payment attempt.'
    ),
}
swagger = Swagger(app)

NETS_API_KEY_ID = os.environ.get('NETS_API_KEY_ID', 'your-api-key-id')
NETS_SECRET_KEY = os.environ.get('NETS_SECRET_KEY', 'your-secret-key')
NETS_MID = os.environ.get('NETS_MID', 'your-umid')
NETS_ENVIRONMENT = os.environ.get('NETS_ENVIRONMENT', 'uat')
NETS_CALLBACK_BASE = os.environ.get('NETS_CALLBACK_BASE', 'http://localhost:5003')
NETS_B2S_CALLBACK_URL = os.environ.get('NETS_B2S_CALLBACK_URL', '').strip()
NETS_S2S_CALLBACK_URL = os.environ.get('NETS_S2S_CALLBACK_URL', '').strip()
NETS_QUERY_URL = os.environ.get('NETS_QUERY_URL', '').strip()
NETS_IP_ADDRESS = os.environ.get('NETS_IP_ADDRESS', '').strip()
NETS_MERCHANT_TIMEZONE = os.environ.get('NETS_MERCHANT_TIMEZONE', '+8:00').strip() or '+8:00'

ENETS_URLS = {
    'uat': 'https://uat2.enets.sg/GW2/TxnReqListenerToHost',
    'production': 'https://www2.enets.sg/GW2/TxnReqListenerToHost'
}

ENETS_QUERY_URLS = {
    'uat': 'https://test2.enets.sg/txnquery/TxnStatus',
    'production': 'https://admin.enets.sg/txnquery/TxnStatus'
}

payment_records = {}


#  Handles get enets url for this service.
def get_enets_url():
    """Get the eNETS gateway URL based on environment."""
    return ENETS_URLS.get(NETS_ENVIRONMENT, ENETS_URLS['uat'])


#  Handles get enets query url for this service.
def get_enets_query_url():
    """Get the eNETS query URL based on environment."""
    if NETS_QUERY_URL:
        return NETS_QUERY_URL
    return ENETS_QUERY_URLS.get(NETS_ENVIRONMENT, ENETS_QUERY_URLS['uat'])


#  Handles get b2s callback url for this service.
def get_callback_base_url():
    """Resolve callback base URL for local direct and Kong-proxied requests."""
    configured = (NETS_CALLBACK_BASE or '').strip().rstrip('/')

    # Respect explicit non-default callback base from env.
    if configured and configured not in {'http://localhost:5003', 'http://127.0.0.1:5003'}:
        return configured

    if has_request_context():
        forwarded_host = request.headers.get('X-Forwarded-Host', '').strip()
        forwarded_proto = request.headers.get('X-Forwarded-Proto', '').strip() or request.scheme
        if forwarded_host:
            return f"{forwarded_proto}://{forwarded_host}"

    return configured or 'http://localhost:5003'


#  Handles get b2s callback url for this service.
def get_b2s_callback_url():
    """Get the browser callback URL used in the hosted payment request."""
    return NETS_B2S_CALLBACK_URL or f"{get_callback_base_url()}/payment/b2s-callback"


#  Handles get s2s callback url for this service.
def get_s2s_callback_url():
    """Get the server callback URL used in the hosted payment request."""
    return NETS_S2S_CALLBACK_URL or f"{get_callback_base_url()}/payment/s2s-callback"


#  Handles get request client ip for this service.
def get_request_client_ip():
    """
    Best-effort client IP for the hosted payment payload.

    NETS' sample payload includes a loopback IP in UAT, so fall back to
    127.0.0.1 when we do not have a reliable upstream address.
    """
    if NETS_IP_ADDRESS:
        return NETS_IP_ADDRESS

    forwarded_for = request.headers.get('X-Forwarded-For', '')
    client_ip = forwarded_for.split(',', 1)[0].strip() if forwarded_for else ''
    if not client_ip:
        client_ip = request.remote_addr or ''

    # NETS' public UAT sample payload uses 127.0.0.1. When we're running
    # locally in Docker, request.remote_addr is often just a private bridge
    # address like 172.x, which is not useful to the gateway.
    if client_ip and NETS_ENVIRONMENT == 'uat':
        try:
            parsed_ip = ipaddress.ip_address(client_ip)
            if parsed_ip.is_private or parsed_ip.is_loopback or parsed_ip.is_link_local:
                return '127.0.0.1'
        except ValueError:
            pass

    return client_ip or '127.0.0.1'


#  Handles get query mid for this service.
def get_query_mid():
    """
    NETS' transaction query API expects the numeric MID.

    Our runtime config uses the hosted-flow UMID format, so strip the prefix
    when present and fall back to the configured value otherwise.
    """
    if NETS_MID.startswith('UMID_'):
        return NETS_MID.split('UMID_', 1)[1]
    return NETS_MID


#  Handles generate merchant txn ref for this service.
def generate_merchant_txn_ref():
    """Generate a unique merchant transaction reference (max 20 chars)."""
    timestamp = datetime.now().strftime('%y%m%d%H%M%S')
    suffix = uuid.uuid4().hex[:4].upper()
    return f"HDB{timestamp}{suffix}"[:20]


#  Handles compute hmac for this service.
def compute_hmac(payload_json, secret_key):
    """
    eNETS expects a Base64-encoded SHA-256 digest of payload + secret key.

    Despite the field name being `hmac`, the UAT gateway rejects a true
    HMAC-SHA256 signature for TxnReqListener/TxnReqListenerToHost.
    """
    digest = hashlib.sha256(f"{payload_json}{secret_key}".encode('utf-8')).digest()
    return base64.b64encode(digest).decode('utf-8')


#  Handles build txn req for this service.
def build_txn_req(amount_cents, merchant_txn_ref, description, currency='SGD', client_ip='127.0.0.1'):
    """Build the hosted-payment request payload expected by NETS."""
    now = datetime.now()
    merchant_txn_dtm = now.strftime('%Y%m%d %H:%M:%S.') + f"{now.microsecond // 1000:03d}"

    txn_req = {
        "ss": "1",
        "msg": {
            "netsMid": NETS_MID,
            "tid": "",
            "submissionMode": "B",
            "txnAmount": str(amount_cents),
            "merchantTxnRef": merchant_txn_ref,
            "merchantTxnDtm": merchant_txn_dtm,
            "paymentType": "SALE",
            "paymentMode": "",
            "currencyCode": currency,
            "merchantTimeZone": NETS_MERCHANT_TIMEZONE,
            "b2sTxnEndURL": get_b2s_callback_url(),
            "b2sTxnEndURLParam": f"merchantTxnRef={merchant_txn_ref}",
            "s2sTxnEndURL": get_s2s_callback_url(),
            "s2sTxnEndURLParam": f"merchantTxnRef={merchant_txn_ref}",
            "clientType": "W",
            "supMsg": "",
            "netsMidIndicator": "U",
            "ipAddress": client_ip,
            "language": "en"
        }
    }

    payload_json = json.dumps(txn_req, separators=(',', ':'))
    signature = compute_hmac(payload_json, NETS_SECRET_KEY)

    return {
        "payload": payload_json,
        "hmac": signature
    }


#  Handles parse structured payload for this service.
def parse_structured_payload(payload):
    """Parse JSON or form-encoded callback payloads into a dictionary."""
    if isinstance(payload, dict):
        return payload

    if not isinstance(payload, str):
        return None

    candidates = []
    for candidate in (payload, unquote_plus(payload)):
        candidate = candidate.strip()
        if candidate and candidate not in candidates:
            candidates.append(candidate)

    # Try JSON decoding first across all candidates. This avoids misreading
    # URL-encoded JSON as a query-string key.
    for candidate in candidates:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    # Only treat the string as form/query data when it actually looks like one.
    for candidate in candidates:
        if '=' not in candidate and '&' not in candidate:
            continue

        parsed = {
            key: values[0] if len(values) == 1 else values
            for key, values in parse_qs(candidate, keep_blank_values=True).items()
        }
        if parsed:
            return parsed

    return None


#  Handles unwrap callback message for this service.
def unwrap_callback_message(payload):
    """
    Recursively unwrap common NETS callback wrappers until we reach the
    transaction fields.
    """
    structured = parse_structured_payload(payload)
    if not isinstance(structured, dict):
        return None

    for key in ('msg', 'message', 'rawMsg', 'payload'):
        value = structured.get(key)
        unwrapped = unwrap_callback_message(value)
        if isinstance(unwrapped, dict):
            return unwrapped

    return structured


#  Handles get callback payload for this service.
def get_callback_payload():
    """Read callback data from GET params, JSON, or form-encoded POSTs."""
    if request.method == 'GET':
        return request.args.to_dict()

    if request.is_json:
        payload = request.get_json(silent=True) or {}
        return unwrap_callback_message(payload) or payload

    form_data = request.form.to_dict()
    if form_data:
        for key in ('message', 'rawMsg', 'payload'):
            wrapped = form_data.get(key)
            if wrapped:
                return unwrap_callback_message(wrapped) or form_data
        return form_data

    raw_data = request.get_data(as_text=True)
    return unwrap_callback_message(raw_data) or parse_structured_payload(raw_data) or {}


#  Handles extract merchant txn ref for this service.
def extract_merchant_txn_ref(payload):
    """Best-effort extraction of merchantTxnRef from nested callback payloads."""
    structured = unwrap_callback_message(payload) or parse_structured_payload(payload)
    if not isinstance(structured, dict):
        return ''

    if structured.get('merchantTxnRef'):
        return str(structured['merchantTxnRef'])

    if 'msg' in structured:
        return extract_merchant_txn_ref(structured['msg'])

    for value in structured.values():
        nested_ref = extract_merchant_txn_ref(value)
        if nested_ref:
            return nested_ref

    return ''


#  Handles parse txn end for this service.
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
    txn_end_data = unwrap_callback_message(txn_end_data) or parse_structured_payload(txn_end_data)
    if not isinstance(txn_end_data, dict):
        return None

    msg = unwrap_callback_message(txn_end_data.get('msg', txn_end_data)) or parse_structured_payload(txn_end_data.get('msg', txn_end_data))
    if not isinstance(msg, dict):
        return None

    txn_end = {
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

    has_core_fields = any([
        txn_end["merchantTxnRef"],
        txn_end["netsTxnRef"],
        txn_end["netsTxnStatus"],
        txn_end["stageRespCode"],
        txn_end["netsTxnMsg"],
        txn_end["actionCode"],
    ])

    return txn_end if has_core_fields else None


#  Handles map nets status for this service.
def map_nets_status(nets_txn_status):
    """Map NETS status codes to the local record status."""
    return {
        '0': 'success',
        '1': 'failed',
        '9': 'cancelled',
    }.get(nets_txn_status, 'unknown')


#  Handles apply txn end to record for this service.
def apply_txn_end_to_record(record, txn_end, source):
    """Update a payment record from a parsed NETS transaction payload."""
    record['status'] = map_nets_status(txn_end['netsTxnStatus'])
    record['nets_txn_ref'] = txn_end['netsTxnRef']
    record['nets_txn_status'] = txn_end['netsTxnStatus']
    record['stage_resp_code'] = txn_end['stageRespCode']
    record['action_code'] = txn_end['actionCode']
    record['nets_txn_msg'] = txn_end['netsTxnMsg']
    record['bank_auth_id'] = txn_end['bankAuthId']
    record['mask_pan'] = txn_end['maskPan']
    record['verification_source'] = source
    record['updated_at'] = datetime.now().isoformat()


#  Handles mark record abandoned for this service.
def mark_record_abandoned(record):
    """Treat an unfinished hosted payment as cancelled after a manual return."""
    if record['status'] != 'pending':
        return

    record['status'] = 'cancelled'
    record['nets_txn_status'] = '9'
    record['stage_resp_code'] = 'LOCAL-ABANDONED'
    record['action_code'] = '0'
    record['nets_txn_msg'] = (
        'Payment was not completed at the NETS gateway and has been treated as cancelled.'
    )
    record['verification_source'] = 'abandon'
    record['updated_at'] = datetime.now().isoformat()


#  Handles mark record successful for demo mode for this service.
def mark_record_demo_success(record):
    """Force a successful payment outcome for demo recovery flows."""
    record['status'] = 'success'
    record['nets_txn_ref'] = record.get('nets_txn_ref') or f"DEMO{datetime.now().strftime('%Y%m%d%H%M%S%f')}"[:20]
    record['nets_txn_status'] = '0'
    record['stage_resp_code'] = 'DEMO-SUCCESS'
    record['action_code'] = '0'
    record['nets_txn_msg'] = 'Payment marked as successful via demo override.'
    record['bank_auth_id'] = record.get('bank_auth_id', '')
    record['mask_pan'] = record.get('mask_pan', '')
    record['query_raw_status'] = 'DEMO_OVERRIDE'
    record['query_latest_code'] = 'DEMO-SUCCESS'
    record['query_checked_at'] = datetime.now().isoformat()
    record['verification_source'] = 'demo_override'
    record['updated_at'] = datetime.now().isoformat()


#  Handles interpret query status for this service.
def interpret_query_status(raw_status):
    """
    Interpret the plain-text status returned by NETS' transaction query API.

    The official guide identifies these as successful/settled:
      - 1003_00 (credit)
      - 000008_000000 (debit)
      - 000004_000000 (debit)

    Any other code means the payment is not confirmed as settled yet.
    """
    codes = [code.strip() for code in raw_status.split(';') if code.strip()]
    latest_code = codes[-1] if codes else ''
    normalized_code = latest_code.replace('-', '_')

    success_codes = {
        '1003_00',
        '1003_00000',
        '000008_000000',
        '000004_000000'
    }

    if normalized_code in success_codes:
        return {
            "status": "success",
            "latest_code": latest_code,
            "normalized_code": normalized_code,
            "confirmed": True
        }

    return {
        "status": "pending",
        "latest_code": latest_code,
        "normalized_code": normalized_code,
        "confirmed": False
    }


#  Handles query enets transaction for this service.
def query_enets_transaction(merchant_txn_ref, nets_txn_ref=None):
    """
    Query NETS directly for the latest transaction state.

    Prefer nets_txn_ref when available; otherwise fall back to MID +
    merchantTxnRef as documented by NETS' transaction query guide.
    """
    query_data = {}

    if nets_txn_ref:
        query_data['nets_txn_ref'] = nets_txn_ref
    else:
        query_data['mid'] = get_query_mid()
        query_data['merch_txn_ref'] = merchant_txn_ref

    response = http_requests.post(
        get_enets_query_url(),
        data=query_data,
        timeout=30
    )

    raw_status = response.text.strip()

    if response.status_code != 200:
        raise RuntimeError(
            f"NETS query failed with HTTP {response.status_code}: {raw_status or 'empty response'}"
        )

    interpreted = interpret_query_status(raw_status)

    return {
        "query_url": get_enets_query_url(),
        "query_data": query_data,
        "raw_status": raw_status,
        **interpreted
    }


#  Handles refresh record from query for this service.
def refresh_record_from_query(record):
    """Refresh a local payment record using NETS' transaction query API."""
    merchant_txn_ref = record['merchant_txn_ref']
    nets_txn_ref = record.get('nets_txn_ref')
    query_result = query_enets_transaction(merchant_txn_ref, nets_txn_ref=nets_txn_ref)

    record['query_raw_status'] = query_result['raw_status']
    record['query_latest_code'] = query_result['latest_code']
    record['query_checked_at'] = datetime.now().isoformat()

    # Only upgrade to a confirmed success from the query response.
    # Otherwise preserve any callback-derived terminal state we already have.
    if query_result['status'] == 'success':
        record['status'] = 'success'
        record['stage_resp_code'] = query_result['normalized_code']
        record['nets_txn_msg'] = 'Payment confirmed via NETS transaction query.'
        record['verification_source'] = 'query'

    return query_result


#  Handles initiate payment for this service.
@app.route('/payment/initiate', methods=['POST'])
def initiate_payment():
    """
    Create a hosted NETS payment request
    ---
    tags:
      - Payment
    summary: Start a hosted eNETS payment
    description: |
      This is the main entry point another internal service or the frontend should call
      to start a payment.

      The response does not charge the card directly. Instead, it returns the hosted
      eNETS gateway URL plus the signed form fields needed for the browser to submit the
      payment request to NETS.
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            required:
              - applicant_id
              - amount
            properties:
              applicant_id:
                type: string
                description: Applicant identifier or NRIC used by the calling flow.
                example: S1234567A
              amount:
                type: number
                description: Payment amount in SGD dollars.
                example: 10
              description:
                type: string
                description: Merchant-facing description shown in logs and payload generation.
                example: BTO Option Fee
    responses:
      200:
        description: Hosted NETS payment request created successfully.
      400:
        description: Missing required fields or invalid amount.
      500:
        description: Unexpected payment service error while building the NETS request.
    """
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

        txn_data = build_txn_req(
            amount_cents,
            merchant_txn_ref,
            description,
            client_ip=get_request_client_ip()
        )

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
            "action_code": None,
            "verification_source": "initiate",
            "created_at": datetime.now().isoformat()
        }

        print(f"[NETS] Payment initiated: {merchant_txn_ref} for ${amount}")
        print(f"[NETS] MID: {NETS_MID} | KeyId: {NETS_API_KEY_ID}")
        print(f"[NETS] Payload: {txn_data['payload']}")
        print(f"[NETS] HMAC: {txn_data['hmac']}")

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


#  Handles s2s callback for this service.
@app.route('/payment/s2s-callback', methods=['POST'])
def s2s_callback():
    """
    Receive the NETS server-to-server callback
    ---
    tags:
      - NETS Callback
    summary: Receive a direct backend callback from NETS
    description: |
      This route is for NETS to call after hosted checkout. Your frontend or internal
      application services should not call it directly.

      The service accepts the callback in NETS' form-encoded or wrapped JSON formats,
      updates the in-memory payment record, and returns a simple acknowledgement.
    requestBody:
      required: false
      content:
        application/x-www-form-urlencoded:
          schema:
            type: object
            additionalProperties: true
        application/json:
          schema:
            type: object
            additionalProperties: true
    responses:
      200:
        description: Callback accepted and processed.
      400:
        description: Callback payload could not be parsed into a NETS transaction result.
      500:
        description: Unexpected callback processing error.
    """
    try:
        raw_data = request.get_data(as_text=True)
        print(f"[NETS s2sTxnEnd] Received: {raw_data}")

        callback_data = get_callback_payload()
        print(f"[NETS s2sTxnEnd] Parsed payload: {callback_data}")

        txn_end = parse_txn_end(callback_data)

        if not txn_end:
            print("[NETS s2sTxnEnd] Failed to parse callback data")
            return "ERROR", 400

        merchant_txn_ref = txn_end['merchantTxnRef']
        nets_txn_status = txn_end['netsTxnStatus']

        print(f"[NETS s2sTxnEnd] Ref: {merchant_txn_ref}, Status: {nets_txn_status}")

        if merchant_txn_ref in payment_records:
            record = payment_records[merchant_txn_ref]
            apply_txn_end_to_record(record, txn_end, source='s2s')

            print(f"[NETS s2sTxnEnd] Updated record: {record['status']}")
        else:
            print(f"[NETS s2sTxnEnd] WARNING: No record found for {merchant_txn_ref}")

        return "OK", 200

    except Exception as e:
        print(f"[NETS s2sTxnEnd] Error: {e}")
        return "ERROR", 500


#  Handles b2s callback for this service.
@app.route('/payment/b2s-callback', methods=['POST', 'GET'])
def b2s_callback():
    """
    Receive the browser callback from hosted NETS checkout
    ---
    tags:
      - NETS Callback
    summary: Receive the browser return from NETS hosted checkout
    description: |
      This route is the browser-facing return URL used by hosted checkout.
      NETS posts or redirects the customer back here after they finish, cancel,
      or leave the payment page.

      The service updates the payment record when possible and then redirects the
      browser to the frontend payment-result page.
    parameters:
      - in: query
        name: merchantTxnRef
        required: false
        schema:
          type: string
        description: Optional fallback transaction reference when NETS sends it as a query parameter.
    requestBody:
      required: false
      content:
        application/x-www-form-urlencoded:
          schema:
            type: object
            additionalProperties: true
        application/json:
          schema:
            type: object
            additionalProperties: true
    responses:
      302:
        description: Browser is redirected back to the frontend payment-result page.
      500:
        description: Unexpected callback processing error before redirect.
    """
    try:
        raw_data = request.get_data(as_text=True)
        print(f"[NETS b2sTxnEnd] Received: {raw_data}", flush=True)

        callback_data = get_callback_payload()
        print(f"[NETS b2sTxnEnd] Parsed payload: {callback_data}", flush=True)
        txn_end = parse_txn_end(callback_data)
        merchant_txn_ref = (
            (txn_end or {}).get('merchantTxnRef')
            or request.args.get('merchantTxnRef')
            or request.form.get('merchantTxnRef')
            or extract_merchant_txn_ref(callback_data)
            or 'unknown'
        )
        status = 'unknown'

        if txn_end:
            status = map_nets_status(txn_end['netsTxnStatus'])

            if merchant_txn_ref in payment_records:
                record = payment_records[merchant_txn_ref]
                if record['status'] == 'pending':
                    apply_txn_end_to_record(record, txn_end, source='b2s')

        print(
            f"[NETS b2sTxnEnd] Ref: {merchant_txn_ref}, Status: {status}, "
            f"Stage: {(txn_end or {}).get('stageRespCode', '')}, Action: {(txn_end or {}).get('actionCode', '')}",
            flush=True
        )

        portal_url = os.environ.get('HDB_PORTAL_URL', 'http://localhost:3000')
        if merchant_txn_ref and merchant_txn_ref != 'unknown':
            redirect_url = f"{portal_url}/payment-result?ref={merchant_txn_ref}&status={status}"
        else:
            redirect_url = f"{portal_url}/payment-result?status={status}"
        return redirect(redirect_url, code=302)

    except Exception as e:
        print(f"[NETS b2sTxnEnd] Error: {e}")
        portal_url = os.environ.get('HDB_PORTAL_URL', 'http://localhost:3000')
        fallback_ref = (
            request.args.get('merchantTxnRef')
            or request.form.get('merchantTxnRef')
            or extract_merchant_txn_ref(request.get_data(as_text=True))
        )
        if fallback_ref:
            return redirect(f"{portal_url}/payment-result?ref={fallback_ref}&status=error", code=302)
        return redirect(f"{portal_url}/payment-result?status=error", code=302)


#  Handles check payment status for this service.
@app.route('/payment/status/<merchant_txn_ref>', methods=['GET'])
def check_payment_status(merchant_txn_ref):
    """
    Read the current payment outcome
    ---
    tags:
      - Payment
    summary: Check the current status of a payment attempt
    description: |
      Returns the current local payment state for a merchant transaction reference.

      By default this reads the locally stored record only. If `refresh=true` is supplied
      and the payment is still pending, the service will also ask NETS' transaction query
      endpoint for a fresh status before responding.
    parameters:
      - in: path
        name: merchant_txn_ref
        required: true
        schema:
          type: string
        description: Merchant transaction reference originally returned by /payment/initiate.
      - in: query
        name: refresh
        required: false
        schema:
          type: string
          enum: ['true', 'false', '1', '0', 'yes', 'no']
        description: |
          When true, query NETS directly, but only if the current local record is still pending.
    responses:
      200:
        description: Payment was confirmed as successful.
      202:
        description: Payment is still pending or could not yet be verified.
      402:
        description: Payment failed or was cancelled.
      404:
        description: No local payment record exists for the supplied merchant transaction reference.
    """
    if merchant_txn_ref not in payment_records:
        return jsonify({
            "code": 404,
            "message": "Payment record not found."
        }), 404

    record = payment_records[merchant_txn_ref]
    refresh_requested = request.args.get('refresh', '').lower() in ('1', 'true', 'yes')
    query_error = None
    should_refresh_from_query = refresh_requested and record['status'] == 'pending'

    if should_refresh_from_query:
        try:
            refresh_record_from_query(record)
        except Exception as e:
            query_error = str(e)
            print(f"[NETS Query] Refresh failed for {merchant_txn_ref}: {query_error}")

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
                "action_code": record.get('action_code', ''),
                "bank_auth_id": record.get('bank_auth_id', ''),
                "mask_pan": record.get('mask_pan', ''),
                "message": record.get('nets_txn_msg', 'Payment processed successfully.'),
                "query_raw_status": record.get('query_raw_status', ''),
                "verification_source": record.get('verification_source', '')
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
                "action_code": record.get('action_code', ''),
                "message": record.get('nets_txn_msg', 'Payment declined.'),
                "query_raw_status": record.get('query_raw_status', ''),
                "verification_source": record.get('verification_source', '')
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
                "action_code": record.get('action_code', ''),
                "message": "Payment cancelled by customer.",
                "query_raw_status": record.get('query_raw_status', ''),
                "verification_source": record.get('verification_source', '')
            }
        }), 402
    else:
        message = "Payment is being processed. Please wait."
        if query_error:
            message = "Unable to verify payment with NETS right now. Please try again shortly."

        return jsonify({
            "code": 202,
            "data": {
                "applicant_id": record['applicant_id'],
                "amount": record['amount'],
                "merchant_txn_ref": merchant_txn_ref,
                "status": "pending",
                "action_code": record.get('action_code', ''),
                "message": message,
                "query_raw_status": record.get('query_raw_status', ''),
                "verification_source": record.get('verification_source', ''),
                "query_error": query_error or ""
            }
        }), 202


#  Handles abandon payment for this service.
@app.route('/payment/abandon/<merchant_txn_ref>', methods=['POST'])
def abandon_payment(merchant_txn_ref):
    """
    Mark an unfinished hosted payment as cancelled locally
    ---
    tags:
      - Payment Recovery
    summary: Locally cancel an abandoned hosted-payment attempt
    description: |
      This route exists for the frontend recovery flow. If the user leaves the NETS hosted
      page and comes back without a callback result, the frontend can call this endpoint to
      mark a still-pending payment attempt as cancelled instead of leaving it hanging forever.

      This does not call NETS. It only updates the local record when the current status is pending.
    parameters:
      - in: path
        name: merchant_txn_ref
        required: true
        schema:
          type: string
        description: Merchant transaction reference originally returned by /payment/initiate.
    responses:
      200:
        description: Payment was marked as cancelled locally.
      404:
        description: No local payment record exists for the supplied merchant transaction reference.
    """
    record = payment_records.get(merchant_txn_ref)
    if not record:
        return jsonify({
            "code": 404,
            "message": "Payment record not found."
        }), 404

    mark_record_abandoned(record)

    return jsonify({
        "code": 200,
        "data": {
            "merchant_txn_ref": merchant_txn_ref,
            "status": record['status'],
            "stage_resp_code": record.get('stage_resp_code', ''),
            "action_code": record.get('action_code', ''),
            "message": record.get('nets_txn_msg', ''),
            "verification_source": record.get('verification_source', ''),
        }
    }), 200


#  Handles demo payment success override for this service.
@app.route('/payment/demo-force-success/<merchant_txn_ref>', methods=['POST'])
def demo_force_success(merchant_txn_ref):
    """
    Force a local payment record into success for demo use
    ---
    tags:
      - Payment Recovery
    summary: Force a successful payment outcome locally for demo mode
    description: |
      This route exists only for demo recovery. It does not call NETS. Instead,
      it marks the local in-memory payment record as successful so downstream
      services can continue through the normal completion flow.
    parameters:
      - in: path
        name: merchant_txn_ref
        required: true
        schema:
          type: string
    responses:
      200:
        description: Payment record marked as successful locally.
      404:
        description: No local payment record exists for the supplied merchant transaction reference.
    """
    record = payment_records.get(merchant_txn_ref)
    if not record:
        return jsonify({
            "code": 404,
            "message": "Payment record not found."
        }), 404

    mark_record_demo_success(record)

    return jsonify({
        "code": 200,
        "data": {
            "applicant_id": record['applicant_id'],
            "amount": record['amount'],
            "transaction_id": record.get('nets_txn_ref', ''),
            "merchant_txn_ref": merchant_txn_ref,
            "status": "success",
            "stage_resp_code": record.get('stage_resp_code', ''),
            "action_code": record.get('action_code', ''),
            "message": record.get('nets_txn_msg', 'Payment marked as successful via demo override.'),
            "verification_source": record.get('verification_source', '')
        }
    }), 200


if __name__ == '__main__':
    print(f"[NETS Payment Service] Starting...")
    print(f"  Environment: {NETS_ENVIRONMENT}")
    print(f"  MID: {NETS_MID}")
    print(f"  Gateway: {get_enets_url()}")
    print(f"  Callback base: {NETS_CALLBACK_BASE}")
    print(f"  B2S callback: {get_b2s_callback_url()}")
    print(f"  S2S callback: {get_s2s_callback_url()}")
    print(f"  Query URL: {get_enets_query_url()}")
    print(f"  Merchant timezone: {NETS_MERCHANT_TIMEZONE}")
    if 'localhost' in get_s2s_callback_url() or '127.0.0.1' in get_s2s_callback_url():
        print("  WARNING: s2s callback points to localhost, so NETS' servers cannot reach it.")
    app.run(host='0.0.0.0', port=5003, debug=True)
