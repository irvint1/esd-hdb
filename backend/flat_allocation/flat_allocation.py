"""Flat Allocation Service - Composite orchestrator for Scenario 3 flat selection and payment."""

import logging
import os
from datetime import datetime

import requests
from flask import Flask, jsonify, request
from flask_cors import CORS
from flasgger import Swagger


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

FLAT_SERVICE_URL = os.environ.get('FLAT_AVAILABILITY_URL', os.environ.get('FLAT_SERVICE_URL', 'http://localhost:5006'))
APPLICATION_SERVICE_URL = os.environ.get('APPLICANT_URL', os.environ.get('APPLICATION_SERVICE_URL', 'http://localhost:5004'))
FLAT_SELECTION_URL = os.environ.get('FLAT_SELECTION_URL', 'http://localhost:5002')
NETS_PAYMENT_URL = os.environ.get('NETS_PAYMENT_URL', 'http://localhost:5003')
NOTIFICATION_URL = os.environ.get('NOTIFICATION_URL', 'http://localhost:5000')
NOTIFICATION_QUEUE_NAME = os.environ.get('NOTIFICATION_QUEUE_NAME', 'hdb_notification_queue')
REQUEST_TIMEOUT = float(os.environ.get('REQUEST_TIMEOUT_SECONDS', '20'))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s [flat_allocation] %(message)s',
)
logger = logging.getLogger('flat_allocation')

app = Flask(__name__)
CORS(app)

app.config['SWAGGER'] = {
    'title': 'Flat Allocation API',
    'version': 1.0,
    'openapi': '3.0.2',
    'description': (
        'Orchestrates Scenario 3: flat selection, NETS payment, flat reservation, '
        'and notification via two-phase initiate/complete flow.'
    ),
}
swagger = Swagger(app)

# In-memory workflow storage keyed by merchant_txn_ref
workflows = {}

STAGE_PAYMENT_PENDING = 'payment_pending'
STAGE_PAYMENT_SUCCESS = 'payment_success'
STAGE_PAYMENT_FAILED = 'payment_failed'
STAGE_FLAT_RESERVED = 'flat_reserved'
STAGE_COMPLETED = 'completed'
STAGE_ERROR = 'error'


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def now_iso():
    return datetime.utcnow().isoformat()


def format_readable_date(iso_value):
    if not iso_value:
        return ''

    try:
        parsed = datetime.fromisoformat(str(iso_value).replace('Z', '+00:00'))
        return f"{parsed.day} {parsed.strftime('%b %Y')}"
    except Exception:
        return str(iso_value)


def publish_event(routing_key, message):
    """Publish event via notification service HTTP endpoint."""
    try:
        resp = requests.post(
            f'{NOTIFICATION_URL}/publish',
            json={
                'exchange': 'bto',
                'exchange_type': 'topic',
                'routing_key': routing_key,
                'queue_name': NOTIFICATION_QUEUE_NAME,
                'payload': message,
            },
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        logger.info('[NOTIFY] Published event: %s', routing_key)
        return True
    except Exception as e:
        logger.warning('[NOTIFY] Failed to publish event %s: %s', routing_key, e)
        return False


def _extract_main_contact(application_payload):
    members = application_payload.get('members', []) if isinstance(application_payload, dict) else []
    main = next((m for m in members if m.get('member_role') == 'MAIN_APPLICANT'), {})
    return main.get('email', ''), main.get('contact_number', '')


def _lookup_application_id_from_selection(selection_id):
    try:
        resp = requests.get(
            f'{FLAT_SELECTION_URL}/flat-selection/{selection_id}',
            timeout=REQUEST_TIMEOUT,
        )
        if resp.status_code != 200:
            return None

        payload = resp.json()
        data = payload.get('data') if isinstance(payload, dict) else None
        if not isinstance(data, dict):
            return None

        application_id = data.get('application_id')
        return int(application_id) if application_id is not None else None
    except Exception:
        return None


def get_applicant_contact(applicant_id, selection_id=None):
    """Get main applicant email and phone from application-service."""
    application_id = _lookup_application_id_from_selection(selection_id) if selection_id else None

    if application_id is not None:
        try:
            resp = requests.get(
                f'{APPLICATION_SERVICE_URL}/applications/{application_id}',
                timeout=REQUEST_TIMEOUT,
            )
            if resp.status_code == 200:
                return _extract_main_contact(resp.json())
        except Exception:
            pass

    # Fallback for legacy flows where only NRIC was captured as applicant_id
    try:
        resp = requests.get(
            f'{APPLICATION_SERVICE_URL}/applications',
            params={'nric': applicant_id},
            timeout=REQUEST_TIMEOUT,
        )
        if resp.status_code != 200:
            return '', ''

        payload = resp.json()
        rows = payload.get('applications', []) if isinstance(payload, dict) else []
        if not rows:
            return '', ''

        first = rows[0] if isinstance(rows[0], dict) else {}
        return _extract_main_contact(first)
    except Exception:
        return '', ''


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route('/', methods=['GET'])
def index():
    return jsonify({
        'service': 'flat-allocation',
        'message': (
            'Use POST /select-flat/initiate to start flat selection and '
            'POST /select-flat/complete/<merchant_txn_ref> after payment.'
        ),
    })


@app.route('/select-flat', methods=['POST'])
@app.route('/select-flat/initiate', methods=['POST'])
def initiate_select_flat():
    """
    Initiate flat selection and payment
    ---
    tags:
      - Flat Allocation
    summary: Initiate flat selection payment
    description: |
      Checks flat availability and initiates a NETS hosted payment.
      Returns gateway payload for the frontend to submit to eNETS.
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            required:
              - applicant_id
              - selection_id
              - flat_id
              - payment_amount
            properties:
              applicant_id:
                type: integer
              selection_id:
                type: integer
              flat_id:
                type: integer
              payment_amount:
                type: number
    responses:
      200:
        description: Payment initiated, gateway payload returned.
      400:
        description: Validation error.
      409:
        description: Flat is not available.
      502:
        description: Payment service did not return a transaction reference.
      503:
        description: Upstream service unavailable.
    """
    data = request.get_json()
    for field in ('applicant_id', 'selection_id', 'flat_id', 'payment_amount'):
        if not data or field not in data:
            return jsonify({'error': f'{field} is required.'}), 400

    applicant_id = data['applicant_id']
    selection_id = data['selection_id']
    flat_id = data['flat_id']
    payment_amount = float(data['payment_amount'])

    logger.info(
        'Initiate flat selection | applicant=%s flat=%s selection=%s amount=%s',
        applicant_id, flat_id, selection_id, payment_amount,
    )

    # Step 6: Check flat availability
    try:
        flat_resp = requests.get(f'{FLAT_SERVICE_URL}/flats/{flat_id}', timeout=REQUEST_TIMEOUT)
        flat_data = flat_resp.json()
    except Exception as e:
        return jsonify({'error': f'Flat Service unavailable: {e}'}), 503

    if flat_resp.status_code != 200:
        return jsonify({'error': flat_data.get('message', 'Flat not found.')}), flat_resp.status_code

    if flat_data['data']['status'] != 'available':
        return jsonify({
            'error': (
                f"Flat {flat_id} is not available. "
                f"Status: {flat_data['data']['status']}. Please select another flat."
            ),
        }), 409

    # Initiate NETS payment
    try:
        payment_resp = requests.post(
            f'{NETS_PAYMENT_URL}/payment/initiate',
            json={
                'applicant_id': applicant_id,
                'amount': payment_amount,
                'description': f'BTO Option Fee for Flat {flat_id}',
            },
            timeout=REQUEST_TIMEOUT,
        )
        payment_resp.raise_for_status()
        payment_data = payment_resp.json()
    except Exception as e:
        return jsonify({'error': f'Payment Service unavailable: {e}'}), 503

    raw = payment_data.get('data') if isinstance(payment_data, dict) else None
    pay = raw if isinstance(raw, dict) else {}
    merchant_txn_ref = pay.get('merchant_txn_ref')
    if not merchant_txn_ref:
        return jsonify({'error': 'NETS Payment Service did not return a merchant transaction reference.'}), 502

    timestamp = now_iso()
    workflows[merchant_txn_ref] = {
        'merchant_txn_ref': merchant_txn_ref,
        'stage': STAGE_PAYMENT_PENDING,
        'applicant_id': applicant_id,
        'selection_id': selection_id,
        'flat_id': flat_id,
        'payment_amount': payment_amount,
        'result': None,
        'result_status_code': None,
        'created_at': timestamp,
        'updated_at': timestamp,
    }

    logger.info('Flat allocation workflow created | ref=%s', merchant_txn_ref)

    return jsonify({
        'merchant_txn_ref': merchant_txn_ref,
        'stage': STAGE_PAYMENT_PENDING,
        'gateway_url': pay.get('gateway_url', ''),
        'payload': pay.get('payload', ''),
        'hmac': pay.get('hmac', ''),
        'api_key_id': pay.get('api_key_id', ''),
        'payment': pay,
        'message': 'Payment initiated. Redirect applicant to the NETS hosted page.',
    })


@app.route('/select-flat/complete/<merchant_txn_ref>', methods=['POST'])
def complete_select_flat(merchant_txn_ref):
    """
    Complete flat selection after payment
    ---
    tags:
      - Flat Allocation
    summary: Complete flat selection after NETS payment
    description: |
      Verifies payment outcome. On success, reserves the flat and sends confirmation.
      On failure, publishes a payment failure notification.
    parameters:
      - in: path
        name: merchant_txn_ref
        required: true
        schema:
          type: string
    responses:
      200:
        description: Flat selection confirmed.
      202:
        description: Payment still pending.
      402:
        description: Payment failed or cancelled.
      404:
        description: Workflow not found.
      409:
        description: Flat reservation failed after successful payment.
      502:
        description: Downstream service error.
      503:
        description: Payment service unavailable.
    """
    workflow = workflows.get(merchant_txn_ref)
    if workflow is None:
        return jsonify({'error': 'Workflow not found for this merchant transaction reference.'}), 404

    # Return cached result if already completed
    if workflow.get('result') is not None:
        return jsonify(workflow['result']), workflow['result_status_code']

    applicant_id = workflow['applicant_id']
    selection_id = workflow['selection_id']
    flat_id = workflow['flat_id']
    payment_amount = workflow['payment_amount']

    # Check payment status
    try:
        status_resp = requests.get(
            f'{NETS_PAYMENT_URL}/payment/status/{merchant_txn_ref}',
            params={'refresh': 'true'},
            timeout=REQUEST_TIMEOUT,
        )
        status_data = status_resp.json()
    except Exception as e:
        return jsonify({'error': f'Payment Service unavailable: {e}'}), 503

    pay_data = status_data.get('data', {}) if isinstance(status_data, dict) else {}
    payment_status = pay_data.get('status', 'unknown')

    if status_resp.status_code == 202 or payment_status == 'pending':
        workflow['stage'] = STAGE_PAYMENT_PENDING
        return jsonify({
            'merchant_txn_ref': merchant_txn_ref,
            'stage': STAGE_PAYMENT_PENDING,
            'message': 'Payment is still pending. Complete the NETS flow first.',
        }), 202

    if status_resp.status_code == 402 or payment_status in ('failed', 'cancelled'):
        workflow['stage'] = STAGE_PAYMENT_FAILED
        workflow['updated_at'] = now_iso()

        email, phone = get_applicant_contact(applicant_id, selection_id)
        publish_event('payment.failed', {
            'eventType': 'PaymentFailed',
            'subject': 'Payment Failed - Please Retry',
            'applicantId': applicant_id,
            'flat_id': flat_id,
            'amount': payment_amount,
            'email': email,
            'mobile': phone,
            'message': f'Your payment of ${payment_amount} for Flat {flat_id} has failed. Please try again.',
        })

        result = {
            'merchant_txn_ref': merchant_txn_ref,
            'stage': STAGE_PAYMENT_FAILED,
            'payment_status': payment_status,
            'message': pay_data.get('message', 'Payment did not complete successfully.'),
        }
        workflow['result'] = result
        workflow['result_status_code'] = 402
        return jsonify(result), 402

    if status_resp.status_code != 200 or payment_status != 'success':
        workflow['stage'] = STAGE_ERROR
        workflow['updated_at'] = now_iso()
        return jsonify({
            'merchant_txn_ref': merchant_txn_ref,
            'stage': STAGE_ERROR,
            'payment_status': payment_status,
            'message': 'Unable to confirm payment outcome.',
        }), 502

    # Payment succeeded — reserve the flat
    transaction_id = pay_data.get('transaction_id', merchant_txn_ref)
    workflow['stage'] = STAGE_PAYMENT_SUCCESS
    workflow['updated_at'] = now_iso()

    try:
        reserve_resp = requests.put(
            f'{FLAT_SERVICE_URL}/flats/{flat_id}/reserve',
            json={'applicant_id': applicant_id},
            timeout=REQUEST_TIMEOUT,
        )
        reserve_data = reserve_resp.json()
    except Exception as e:
        logger.error('Payment succeeded but flat reservation failed: %s', e)
        return jsonify({
            'merchant_txn_ref': merchant_txn_ref,
            'stage': STAGE_ERROR,
            'transaction_id': transaction_id,
            'message': 'Payment was successful but flat reservation failed. Please contact HDB support.',
        }), 500

    if reserve_resp.status_code != 200:
        logger.error('Flat reservation failed: %s', reserve_data.get('message'))
        return jsonify({
            'merchant_txn_ref': merchant_txn_ref,
            'stage': STAGE_ERROR,
            'transaction_id': transaction_id,
            'message': (
                f"Payment successful but flat is no longer available. Refund will be processed. "
                f"{reserve_data.get('message', '')}"
            ),
        }), 409

    workflow['stage'] = STAGE_FLAT_RESERVED
    workflow['updated_at'] = now_iso()

    # Update flat selection record
    selection_reserved_at = ''
    try:
        selection_resp = requests.put(
            f'{FLAT_SELECTION_URL}/flat-selection/{selection_id}/reserve',
            json={'flat_id': flat_id},
            timeout=REQUEST_TIMEOUT,
        )
        selection_data = selection_resp.json() if selection_resp.content else {}
        if isinstance(selection_data, dict):
            selection_reserved_at = (
                (selection_data.get('data') or {}).get('reserved_at')
                if isinstance(selection_data.get('data'), dict)
                else ''
            )
    except Exception as e:
        logger.warning('Flat selection update failed: %s', e)

    # Retrieve display details for notification message
    unit_number = ''
    project_name = ''
    flat_type = ''
    reserved_date = ''
    try:
        flat_resp = requests.get(
            f'{FLAT_SERVICE_URL}/flats/{flat_id}',
            timeout=REQUEST_TIMEOUT,
        )
        if flat_resp.status_code == 200:
            flat_data = flat_resp.json().get('data', {}) if isinstance(flat_resp.json(), dict) else {}
            if isinstance(flat_data, dict):
                unit_number = str(flat_data.get('unit_number', '') or '')
                project_name = str(flat_data.get('project_name', '') or '')
                flat_type = str(flat_data.get('flat_type', '') or '')
                reserved_date = format_readable_date(flat_data.get('reserved_at', ''))
    except Exception as e:
        logger.warning('Flat detail lookup failed for notification: %s', e)

    if not reserved_date:
        reserved_date = format_readable_date(selection_reserved_at)

    confirmation_message = (
        f'Congratulations! Your selection of Flat {flat_id} has been confirmed. '
        f'Transaction ID: {transaction_id}.\n\n'
        f'Booked Unit Details:\n'
        f'Unit / Flat ID: {unit_number or flat_id}\n'
        f'Project: {project_name or "N/A"}\n'
        f'Flat Type: {flat_type or "N/A"}\n'
        f'Reserved Date: {reserved_date or "N/A"}'
    )

    # Get applicant contact details for notification
    email, phone = get_applicant_contact(applicant_id, selection_id)

    # Publish confirmation event
    publish_event('flat.confirmed', {
        'eventType': 'FlatConfirmed',
        'subject': 'Flat Selection Confirmed',
        'applicantId': applicant_id,
        'flat_id': flat_id,
        'unit_number': unit_number,
        'project_name': project_name,
        'flat_type': flat_type,
        'reserved_date': reserved_date,
        'transaction_id': transaction_id,
        'amount': payment_amount,
        'email': email,
        'mobile': phone,
        'message': confirmation_message,
    })

    result = {
        'merchant_txn_ref': merchant_txn_ref,
        'stage': STAGE_COMPLETED,
        'payment_status': 'success',
        'transaction_id': transaction_id,
        'applicant_id': applicant_id,
        'flat_id': flat_id,
        'payment_amount': payment_amount,
        'message': 'Flat selection confirmed. Payment processed successfully.',
    }
    workflow['stage'] = STAGE_COMPLETED
    workflow['result'] = result
    workflow['result_status_code'] = 200
    workflow['updated_at'] = now_iso()

    logger.info('Flat selection completed | ref=%s flat=%s', merchant_txn_ref, flat_id)
    return jsonify(result), 200


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5005, debug=False)
