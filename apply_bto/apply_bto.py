"""Apply BTO orchestration service."""

import io
import json
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

NETS_PAYMENT_SERVICE_URL = os.environ.get("NETS_PAYMENT_SERVICE_URL", "http://localhost:5003")
APPLICATION_SERVICE_URL = os.environ.get("APPLICATION_SERVICE_URL", "http://localhost:5004")
CHECK_ELIGIBILITY_SERVICE_URL = os.environ.get("CHECK_ELIGIBILITY_SERVICE_URL", "http://localhost:5008")
REQUEST_TIMEOUT = float(os.environ.get("REQUEST_TIMEOUT_SECONDS", "20"))
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()

STAGE_PAYMENT_PENDING = "payment_pending"
STAGE_PAYMENT_SUCCESS = "payment_success"
STAGE_PAYMENT_FAILED = "payment_failed"
STAGE_APPLICATION_CREATED = "application_created"
STAGE_ELIGIBILITY_CHECKED = "eligibility_checked"
STAGE_COMPLETED = "completed"
STAGE_ERROR = "error"

PAYMENT_AMOUNT = 10

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)s [apply_bto] %(message)s",
)
logger = logging.getLogger("apply_bto")


app = Flask(__name__)
CORS(app)

app.config["SWAGGER"] = {
    "title": "Apply BTO API",
    "version": 1.0,
    "openapi": "3.0.2",
    "description": (
        "Orchestrates the BTO application flow: start hosted NETS payment, "
        "store the application after payment succeeds, run eligibility checks, "
        "and update the final application outcome."
    ),
}
swagger = Swagger(app)


# In-memory workflow storage keyed by merchant_txn_ref.
workflows = {}


def load_default_application_fee():
    raw_value = os.environ.get("APPLICATION_FEE", "10")
    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        logger.warning(
            "Invalid APPLICATION_FEE '%s'. Falling back to 10.0.",
            raw_value,
        )
        return 10.0

    if value <= 0:
        logger.warning(
            "Non-positive APPLICATION_FEE '%s'. Falling back to 10.0.",
            raw_value,
        )
        return 10.0

    return value


DEFAULT_APPLICATION_FEE = load_default_application_fee()

NOTIFICATION_URL      = os.environ.get('NOTIFICATION_URL',      'http://localhost:5013')
RABBITMQ_HOST    = os.environ.get('RABBITMQ_HOST',    'localhost')
RABBITMQ_PORT    = int(os.environ.get('RABBITMQ_PORT', 5672))
EXCHANGE_NAME    = 'bto_notifications'

def publish_event(routing_key: str, payload: dict):
    """Publish a notification event; falls back to HTTP if RabbitMQ unavailable."""
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
            body=json.dumps(payload),
        )
        connection.close()
        print(f'[AMQP] Published: {routing_key}')
    except Exception as e:
        print(f'[AMQP] Failed ({e}); falling back to HTTP notification.')
        try:
            requests.post(
                f'{NOTIFICATION_URL}/notify',
                json={**payload, 'event_type': routing_key},
                timeout=5
            )
        except Exception as http_e:
            print(f'[HTTP NOTIFY] Also failed: {http_e}')


# ---------------------------------------------------------------------------
# Small utility functions
# ---------------------------------------------------------------------------

#  Handles now iso for this service.
def now_iso():
    return datetime.utcnow().isoformat()


#  Handles log event for this service.
def log_event(message, **context):
    if context:
        logger.info("%s | %s", message, json.dumps(context, default=str, sort_keys=True))
        return

    logger.info("%s", message)


#  Handles error response for this service.
def error_response(message, status_code, details=None):
    payload = {"error": message}
    if details:
        payload["details"] = details
    return jsonify(payload), status_code


#  Handles normalise nric for this service.
def normalise_nric(value):
    return value.strip().upper() if isinstance(value, str) and value.strip() else None


#  Handles parse int for this service.
def parse_int(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None



#  Handles extract error message for this service.
def extract_error_message(response, fallback):
    try:
        payload = response.json()
    except ValueError:
        return fallback

    if not isinstance(payload, dict):
        return fallback

    if isinstance(payload.get("error"), str) and payload["error"].strip():
        return payload["error"]

    if isinstance(payload.get("message"), str) and payload["message"].strip():
        return payload["message"]

    if isinstance(payload.get("details"), list) and payload["details"]:
        return " ".join(str(item) for item in payload["details"])

    return fallback


#  Handles parse application payload for this service.
def parse_application_payload(raw_application):
    if not raw_application:
        return None, ["'application' form field is required."]

    try:
        application = json.loads(raw_application)
    except (TypeError, ValueError):
        return None, ["'application' must be a valid JSON string."]

    if not isinstance(application, dict):
        return None, ["'application' must be a JSON object."]

    errors = []
    cleaned = {}

    for field_name in ("exercise_id", "project_id"):
        value = parse_int(application.get(field_name))
        if value is None:
            errors.append(f"'{field_name}' must be an integer.")
        else:
            cleaned[field_name] = value

    for field_name in ("flat_type", "main_applicant_nric"):
        value = application.get(field_name)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"'{field_name}' is required.")
        else:
            cleaned[field_name] = value.strip()

    members = application.get("members")
    if not isinstance(members, list) or not members:
        errors.append("'members' must be a non-empty array.")
    else:
        cleaned["members"] = members

    return cleaned, errors


#  Handles validate pdf file for this service.
def validate_pdf_file(file_storage, field_name):
    if file_storage is None:
        return f"'{field_name}' file is required."

    filename = (file_storage.filename or "").strip().lower()
    content_type = (file_storage.content_type or "").strip().lower()
    if not filename.endswith(".pdf") and content_type != "application/pdf":
        return f"'{field_name}' must be a PDF."

    return None


#  Handles serialise file for this service.
def serialise_file(file_storage):
    return {
        "filename": file_storage.filename or "document.pdf",
        "content_type": file_storage.content_type or "application/pdf",
        "data": file_storage.read(),
    }


# ---------------------------------------------------------------------------
# HTTP helpers - calls to upstream services
# ---------------------------------------------------------------------------

#  Handles initiate payment for this service.
def initiate_payment(applicant_id, amount, description):
    response = requests.post(
        f"{NETS_PAYMENT_SERVICE_URL}/payment/initiate",
        json={
            "applicant_id": applicant_id,
            "amount": amount,
            "description": description,
        },
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


#  Handles fetch payment status for this service.
def fetch_payment_status(merchant_txn_ref, refresh=True):
    response = requests.get(
        f"{NETS_PAYMENT_SERVICE_URL}/payment/status/{merchant_txn_ref}",
        params={"refresh": "true"} if refresh else None,
        timeout=REQUEST_TIMEOUT,
    )
    return response


#  Handles build application create payload for this service.
def build_application_create_payload(application):
    return {
        "exercise_id": application["exercise_id"],
        "project_id": application["project_id"],
        "flat_type": application["flat_type"],
        "main_applicant_nric": application["main_applicant_nric"],
        "income_document_id": application.get("income_document_id"),
        "hfe_document_id": application.get("hfe_document_id"),
        "members": application["members"],
    }


#  Handles create application record for this service.
def create_application_record(application):
    response = requests.post(
        f"{APPLICATION_SERVICE_URL}/applications",
        json=build_application_create_payload(application),
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


#  Handles update application eligibility for this service.
def update_application_eligibility(application_id, eligible, income_document_id, hfe_document_id):
    response = requests.put(
        f"{APPLICATION_SERVICE_URL}/applications/{application_id}/eligibility",
        json={
            "eligible": eligible,
            "income_document_id": income_document_id,
            "hfe_document_id": hfe_document_id,
        },
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


#  Handles run eligibility check for this service.
def run_eligibility_check(workflow):
    application = workflow["application"]
    application_id = workflow["application_id"]
    income_document = workflow["income_document"]
    hfe_document = workflow["hfe_document"]

    eligibility_application = {
        "application_id": application_id,
        "main_applicant_nric": application["main_applicant_nric"],
        "flat_type": application["flat_type"],
        "members": application["members"],
    }

    response = requests.post(
        f"{CHECK_ELIGIBILITY_SERVICE_URL}/check-eligibility",
        data={"application": json.dumps(eligibility_application)},
        files={
            "income_document": (
                income_document["filename"],
                io.BytesIO(income_document["data"]),
                income_document["content_type"],
            ),
            "hfe_document": (
                hfe_document["filename"],
                io.BytesIO(hfe_document["data"]),
                hfe_document["content_type"],
            ),
        },
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


# ---------------------------------------------------------------------------
# Workflow helpers
# ---------------------------------------------------------------------------

#  Handles cache workflow result for this service.
def cache_workflow_result(workflow, result, status_code):
    workflow["result"] = result
    workflow["result_status_code"] = status_code
    workflow["updated_at"] = now_iso()
    log_event(
        "Cached workflow result",
        merchant_txn_ref=workflow["merchant_txn_ref"],
        stage=workflow["stage"],
        status_code=status_code,
        payment_status=workflow.get("payment_status"),
    )
    return result, status_code


#  Handles get cached workflow result for this service.
def get_cached_workflow_result(workflow):
    result = workflow.get("result")
    status_code = workflow.get("result_status_code")

    if result is None or not isinstance(status_code, int):
        return None

    return result, status_code


#  Handles build completion result for this service.
def build_completion_result(workflow):
    eligibility_result = workflow.get("eligibility_result") or {}
    updated_application = workflow.get("updated_application") or {}

    ineligibility_reasons = eligibility_result.get("ineligibility_reasons")
    if not isinstance(ineligibility_reasons, list):
        ineligibility_reasons = []

    eligible = bool(eligibility_result.get("eligible"))
    summary = (
        eligibility_result.get("summary")
        if isinstance(eligibility_result.get("summary"), str)
        else None
    )

    default_message = (
        "Your payment succeeded and the application passed the eligibility checks."
        if eligible
        else "Your payment succeeded, but the application did not pass the eligibility checks."
    )

    return {
        "merchant_txn_ref": workflow["merchant_txn_ref"],
        "stage": workflow["stage"],
        "payment_status": workflow["payment_status"],
        "application_status": updated_application.get("application_status"),
        "eligible": eligible,
        "summary": summary,
        "ineligibility_reasons": ineligibility_reasons,
        "message": summary or default_message,
    }


#  payment should have been made, 
def finalise_workflow(workflow):
    cached_result = get_cached_workflow_result(workflow)
    if cached_result is not None:
        log_event(
            "Returning cached workflow result",
            merchant_txn_ref=workflow["merchant_txn_ref"],
            stage=workflow["stage"],
            payment_status=workflow.get("payment_status"),
        )
        return cached_result

    payment_response = fetch_payment_status(workflow["merchant_txn_ref"], refresh=True)
    try:
        payment_payload = payment_response.json()
    except ValueError:
        payment_payload = {}

    raw_payment_data = payment_payload.get("data") if isinstance(payment_payload, dict) else None
    payment_data = raw_payment_data if isinstance(raw_payment_data, dict) else {}
    payment_status = payment_data.get("status") or "unknown"

    workflow["payment_status"] = payment_status
    workflow["updated_at"] = now_iso()

    if payment_response.status_code == 202 or payment_status == "pending":
        workflow["stage"] = STAGE_PAYMENT_PENDING
        log_event(
            "Payment still pending",
            merchant_txn_ref=workflow["merchant_txn_ref"],
            payment_status=payment_status,
        )
        return {
            "merchant_txn_ref": workflow["merchant_txn_ref"],
            "stage": workflow["stage"],
            "payment_status": "pending",
            "message": "Payment is still pending. Complete the NETS flow first.",
        }, 202

    if payment_response.status_code == 402 or payment_status in {"failed", "cancelled"}:
        workflow["stage"] = STAGE_PAYMENT_FAILED
        logger.warning(
            "Payment failed or was cancelled | %s",
            json.dumps(
                {
                    "merchant_txn_ref": workflow["merchant_txn_ref"],
                    "payment_status": payment_status,
                },
                sort_keys=True,
            ),
        )
        result = {
            "merchant_txn_ref": workflow["merchant_txn_ref"],
            "stage": workflow["stage"],
            "payment_status": payment_status,
            "message": payment_data.get("message", "Payment did not complete successfully."),
        }
        return cache_workflow_result(workflow, result, 402)

    if payment_response.status_code != 200 or payment_status != "success":
        message = extract_error_message(payment_response, "Unable to confirm the payment outcome.")
        workflow["stage"] = STAGE_ERROR
        workflow["last_error"] = message
        workflow["updated_at"] = now_iso()
        logger.error(
            "Unable to confirm payment outcome | %s",
            json.dumps(
                {
                    "merchant_txn_ref": workflow["merchant_txn_ref"],
                    "payment_status": payment_status,
                    "message": message,
                },
                sort_keys=True,
            ),
        )
        return {
            "merchant_txn_ref": workflow["merchant_txn_ref"],
            "stage": workflow["stage"],
            "payment_status": payment_status,
            "message": message,
        }, 502

    workflow["stage"] = STAGE_PAYMENT_SUCCESS
    workflow["last_error"] = None
    workflow["updated_at"] = now_iso()
    log_event(
        "Payment confirmed successfully",
        merchant_txn_ref=workflow["merchant_txn_ref"],
        payment_status=payment_status,
    )

    if workflow.get("application_id") is None:
        try:
            created_application = create_application_record(workflow["application"])
        except requests.RequestException as exc:
            message = f"Payment succeeded, but application creation failed: {exc}"
            workflow["stage"] = STAGE_ERROR
            workflow["last_error"] = message
            workflow["updated_at"] = now_iso()
            logger.error(
                "Application creation failed after payment success | %s",
                json.dumps(
                    {
                        "merchant_txn_ref": workflow["merchant_txn_ref"],
                        "message": message,
                    },
                    sort_keys=True,
                ),
            )
            return {
                "merchant_txn_ref": workflow["merchant_txn_ref"],
                "stage": workflow["stage"],
                "payment_status": payment_status,
                "message": message,
            }, 502

        workflow["application_id"] = created_application["application_id"]
        workflow["stage"] = STAGE_APPLICATION_CREATED
        workflow["updated_at"] = now_iso()
        log_event(
            "Application record created",
            merchant_txn_ref=workflow["merchant_txn_ref"],
            application_id=workflow["application_id"],
        )

    if workflow.get("eligibility_result") is None:
        try:
            eligibility_result = run_eligibility_check(workflow)
        except requests.RequestException as exc:
            message = f"Application was created, but eligibility checking failed: {exc}"
            workflow["stage"] = STAGE_ERROR
            workflow["last_error"] = message
            workflow["updated_at"] = now_iso()
            logger.error(
                "Eligibility check failed after application creation | %s",
                json.dumps(
                    {
                        "merchant_txn_ref": workflow["merchant_txn_ref"],
                        "application_id": workflow["application_id"],
                        "message": message,
                    },
                    sort_keys=True,
                ),
            )
            return {
                "merchant_txn_ref": workflow["merchant_txn_ref"],
                "stage": workflow["stage"],
                "payment_status": payment_status,
                "application_id": workflow["application_id"],
                "message": message,
            }, 502

        workflow["eligibility_result"] = eligibility_result
        workflow["stage"] = STAGE_ELIGIBILITY_CHECKED
        workflow["updated_at"] = now_iso()
        log_event(
            "Eligibility check completed",
            merchant_txn_ref=workflow["merchant_txn_ref"],
            application_id=workflow["application_id"],
            eligible=bool(eligibility_result.get("eligible")),
        )

    if workflow.get("updated_application") is None:
        eligibility_result = workflow["eligibility_result"]
        try:
            updated_application = update_application_eligibility(
                workflow["application_id"],
                bool(eligibility_result.get("eligible")),
                eligibility_result.get("income_document_id"),
                eligibility_result.get("hfe_document_id"),
            )
        except requests.RequestException as exc:
            message = f"Eligibility was checked, but the application status update failed: {exc}"
            workflow["stage"] = STAGE_ERROR
            workflow["last_error"] = message
            workflow["updated_at"] = now_iso()
            logger.error(
                "Application eligibility update failed | %s",
                json.dumps(
                    {
                        "merchant_txn_ref": workflow["merchant_txn_ref"],
                        "application_id": workflow["application_id"],
                        "message": message,
                    },
                    sort_keys=True,
                ),
            )
            return {
                "merchant_txn_ref": workflow["merchant_txn_ref"],
                "stage": workflow["stage"],
                "payment_status": payment_status,
                "application_id": workflow["application_id"],
                "message": message,
            }, 502

        workflow["updated_application"] = updated_application
        workflow["stage"] = STAGE_COMPLETED
        workflow["updated_at"] = now_iso()
        log_event(
            "Application status updated from eligibility result",
            merchant_txn_ref=workflow["merchant_txn_ref"],
            application_id=workflow["application_id"],
            application_status=updated_application.get("application_status"),
        )

    result = build_completion_result(workflow)
    return cache_workflow_result(workflow, result, 200)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

#  Handles index for this service.
@app.route("/", methods=["GET"])
def index():
    return jsonify(
        {
            "service": "apply-bto",
            "message": (
                "Use POST /apply-bto/initiate to start a submission and "
                "POST /apply-bto/complete/<merchant_txn_ref> after payment succeeds."
            ),
        }
    )


#  Handles initiate apply bto for this service.
@app.route("/apply-bto/initiate", methods=["POST"])
def initiate_apply_bto():
    """
    Start a BTO application payment
    ---
    tags:
      - Apply BTO
    summary: Initiate BTO submission payment
    description: |
      Accepts the application payload and both PDFs, stores them temporarily,
      and creates a hosted NETS payment request. The browser should then submit
      the returned gateway form fields to NETS.
    consumes:
      - multipart/form-data
    requestBody:
      required: true
      content:
        multipart/form-data:
          schema:
            type: object
            required:
              - application
              - income_document
              - hfe_document
            properties:
              application:
                type: string
                description: JSON string with exercise_id, project_id, flat_type, main_applicant_nric, and members.
              income_document:
                type: string
                format: binary
              hfe_document:
                type: string
                format: binary
              payment_amount:
                type: number
                description: Optional override for the application fee.
    responses:
      200:
        description: Hosted NETS payment request created successfully.
      400:
        description: Validation error.
      502:
        description: Upstream payment initiation failed.
    """
    application, validation_errors = parse_application_payload(request.form.get("application"))
    if validation_errors:
        return error_response("Validation error.", 400, validation_errors)

    log_event(
        "Received Apply BTO initiate request",
        main_applicant_nric=application.get("main_applicant_nric"),
        project_id=application.get("project_id"),
        flat_type=application.get("flat_type"),
    )

    income_document = request.files.get("income_document")
    hfe_document = request.files.get("hfe_document")

    file_errors = []
    for field_name, file_storage in (
        ("income_document", income_document),
        ("hfe_document", hfe_document),
    ):
        error = validate_pdf_file(file_storage, field_name)
        if error:
            file_errors.append(error)

    if file_errors:
        return error_response("Validation error.", 400, file_errors)


    applicant_id = normalise_nric(application.get("main_applicant_nric"))
    description = request.form.get("payment_description") or f"BTO Application Fee - {applicant_id}"

    try:
        payment_response = initiate_payment(applicant_id, PAYMENT_AMOUNT, description)
    except requests.RequestException as exc:
        return jsonify({"error": f"Unable to initiate payment via NETS Payment Service: {exc}"}), 502

    raw_payment_data = payment_response.get("data") if isinstance(payment_response, dict) else None
    payment_data = raw_payment_data if isinstance(raw_payment_data, dict) else {}
    merchant_txn_ref = payment_data.get("merchant_txn_ref")
    if not isinstance(merchant_txn_ref, str) or not merchant_txn_ref.strip():
        return jsonify(
            {"error": "NETS Payment Service did not return a merchant transaction reference."}
        ), 502

    timestamp = now_iso()
    workflows[merchant_txn_ref] = {
        "merchant_txn_ref": merchant_txn_ref,
        "stage": STAGE_PAYMENT_PENDING,
        "payment_status": "pending",
        "application": application,
        "income_document": serialise_file(income_document),
        "hfe_document": serialise_file(hfe_document),
        "application_id": None,
        "eligibility_result": None,
        "updated_application": None,
        "result": None,
        "result_status_code": None,
        "last_error": None,
        "created_at": timestamp,
        "updated_at": timestamp,
    }

    log_event(
        "Apply BTO workflow created",
        merchant_txn_ref=merchant_txn_ref,
        stage=STAGE_PAYMENT_PENDING,
        payment_amount=PAYMENT_AMOUNT,
        main_applicant_nric=application.get("main_applicant_nric"),
    )

    return jsonify(
        {
            "merchant_txn_ref": merchant_txn_ref,
            "stage": STAGE_PAYMENT_PENDING,
            "payment": payment_data,
            "message": "Payment initiated. Redirect the applicant to the NETS hosted page.",
        }
    )


#  Handles complete apply bto for this service.
@app.route("/apply-bto/complete/<merchant_txn_ref>", methods=["POST"])
def complete_apply_bto(merchant_txn_ref):
    """
    Complete a paid BTO submission
    ---
    tags:
      - Apply BTO
    summary: Complete a paid BTO application
    description: |
      Verifies the payment outcome for the supplied merchant transaction reference.
      If payment succeeded, this endpoint creates the application, runs eligibility
      checks, updates the final eligibility outcome, and returns the completed result.
    parameters:
      - in: path
        name: merchant_txn_ref
        required: true
        schema:
          type: string
    responses:
      200:
        description: Workflow completed.
      202:
        description: Payment is still pending.
      402:
        description: Payment failed or was cancelled.
      404:
        description: Workflow not found.
      502:
        description: One of the downstream services failed.
    """
    log_event("Received Apply BTO completion request", merchant_txn_ref=merchant_txn_ref)

    workflow = workflows.get(merchant_txn_ref)
    if workflow is None:
        logger.warning(
            "Apply BTO workflow not found during completion | %s",
            json.dumps({"merchant_txn_ref": merchant_txn_ref}, sort_keys=True),
        )
        return jsonify({"error": "Apply BTO workflow not found for this merchant transaction reference."}), 404

    payload, status_code = finalise_workflow(workflow)
    return jsonify(payload), status_code



if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5010, debug=False)
