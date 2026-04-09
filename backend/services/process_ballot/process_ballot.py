from collections import defaultdict
from datetime import datetime, timedelta
import json
import logging
import os
import uuid

import requests
from flask import Flask, jsonify, request
from flask_cors import CORS
from flasgger import Swagger


BALLOT_AUDIT_SERVICE_URL = os.environ.get("BALLOT_AUDIT_SERVICE_URL", "http://localhost:5000")
BALLOT_SERVICE_URL = os.environ.get("BALLOT_SERVICE_URL", "http://localhost:5005")
APPLICATION_SERVICE_URL = os.environ.get("APPLICATION_SERVICE_URL", "http://localhost:5004")
PROJECT_SERVICE_URL = os.environ.get(
    "PROJECT_SERVICE_URL",
    "https://personal-iu6aefgj.outsystemscloud.com/ProjectsMicroservice/rest/ProjectsAPI",
)
VALIDATE_ELIGIBILITY_SERVICE_URL = os.environ.get("VALIDATE_ELIGIBILITY_SERVICE_URL", "http://localhost:5013")
FLAT_SELECTION_SERVICE_URL = os.environ.get("FLAT_SELECTION_SERVICE_URL", "http://localhost:5002")
NOTIFICATION_SERVICE_URL = os.environ.get("NOTIFICATION_SERVICE_URL", "http://localhost:5000")
NOTIFICATION_QUEUE_NAME = os.environ.get("NOTIFICATION_QUEUE_NAME", "hdb_notification_queue")
REQUEST_TIMEOUT = float(os.environ.get("REQUEST_TIMEOUT_SECONDS", "20"))
VALIDATION_BATCH_SIZE = max(1, int(os.environ.get("VALIDATION_BATCH_SIZE", "25")))
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
ADMIN_ALERT_EMAIL = os.environ.get("ADMIN_ALERT_EMAIL")
ADMIN_ALERT_MOBILE = os.environ.get("ADMIN_ALERT_MOBILE")

QUEUE_SLOT_CAPACITY = max(1, int(os.environ.get("QUEUE_SLOT_CAPACITY", "10")))
QUEUE_SLOT_DURATION_MINUTES = max(1, int(os.environ.get("QUEUE_SLOT_DURATION_MINUTES", "30")))
QUEUE_SLOT_START_HOUR = int(os.environ.get("QUEUE_SLOT_START_HOUR", "9"))
QUEUE_SLOT_END_HOUR = int(os.environ.get("QUEUE_SLOT_END_HOUR", "17"))
QUEUE_SLOT_LUNCH_START_HOUR = int(os.environ.get("QUEUE_SLOT_LUNCH_START_HOUR", "12"))
QUEUE_SLOT_LUNCH_END_HOUR = int(os.environ.get("QUEUE_SLOT_LUNCH_END_HOUR", "13"))

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)s [process_ballot] %(message)s",
)
logger = logging.getLogger("process_ballot")

app = Flask(__name__)
CORS(app)
app.config["SWAGGER"] = {
    "title": "Process Ballot API",
    "version": 1.0,
    "openapi": "3.0.2",
    "description": (
        "Orchestrates BTO ballot processing using Ballot Audit, Project, Applications, "
        "Validate Eligibility, Ballot, and Flat Selection services."
    ),
}
swagger = Swagger(app)


class BallotOrchestrationError(Exception):
    """Raised when an upstream call or orchestration step fails."""

    # Initializes the required data.
    def __init__(self, message, status_code=502, details=None, step=None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.details = details or []
        self.step = step


# Handles now iso.
def now_iso():
    """Return the current UTC timestamp as ISO-8601 string."""
    return datetime.utcnow().isoformat()


# Handles structured service logging.
def log_action(message, level=logging.INFO, **context):
    """Write a structured log line for process-ballot actions."""
    if context:
        logger.log(level, "%s | %s", message, json.dumps(context, default=str, sort_keys=True))
        return
    logger.log(level, "%s", message)


# Handles request json.
def request_json(method, url, *, params=None, json_body=None, allowed_statuses=(200,)):
    """Call an upstream service and return (status_code, parsed_json_payload)."""
    log_action(
        "Upstream request",
        level=logging.DEBUG,
        method=method,
        url=url,
        params=params,
        has_json_body=isinstance(json_body, dict),
    )
    try:
        response = requests.request(
            method,
            url,
            params=params,
            json=json_body,
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException as exc:
        log_action(
            "Upstream request unreachable",
            level=logging.ERROR,
            method=method,
            url=url,
            error=str(exc),
        )
        raise BallotOrchestrationError(
            f"Unable to reach upstream service at {url}: {exc}",
            status_code=502,
            step=f"{method} {url}",
        ) from exc

    log_action(
        "Upstream response",
        level=logging.DEBUG,
        method=method,
        url=url,
        status_code=response.status_code,
    )

    if response.status_code not in allowed_statuses:
        message = f"Upstream call failed ({method} {url}) with status {response.status_code}."
        try:
            payload = response.json()
            upstream_message = payload.get("message") or payload.get("error")
            if isinstance(upstream_message, str) and upstream_message.strip():
                message = f"{message} {upstream_message}"
        except ValueError:
            pass
        log_action(
            "Upstream request failed",
            level=logging.WARNING,
            method=method,
            url=url,
            status_code=response.status_code,
            allowed_statuses=list(allowed_statuses),
        )
        raise BallotOrchestrationError(message, status_code=502, step=f"{method} {url}")

    try:
        payload = response.json()
    except ValueError:
        payload = {}

    if not isinstance(payload, dict):
        payload = {}

    return response.status_code, payload


def publish_event(routing_key: str, payload: dict):
    """Publish a notification event to the notification API."""
    try:
        response = requests.post(
            f"{NOTIFICATION_SERVICE_URL}/publish",
            json={
                "exchange": "bto",
                "exchange_type": "topic",
                "routing_key": routing_key,
                "queue_name": NOTIFICATION_QUEUE_NAME,
                "payload": payload,
            },
            timeout=5,
        )
        response.raise_for_status()
        log_action("Published notification event", routing_key=routing_key)
        return True
    except requests.RequestException as exc:
        log_action(
            "Notification publish failed",
            level=logging.WARNING,
            routing_key=routing_key,
            error=str(exc),
        )
        return False


# Checks whether positive int.
def is_positive_int(value):
    return isinstance(value, int) and value > 0


# Handles normalise nric.
def normalise_nric(value):
    if not isinstance(value, str):
        return None
    cleaned = value.strip().upper()
    return cleaned if cleaned else None


def get_notification_recipients(application):
    members = application.get("members") if isinstance(application, dict) else None
    if not isinstance(members, list):
        return []

    recipients = []
    seen = set()

    for member in members:
        if not isinstance(member, dict):
            continue

        member_role = str(member.get("member_role", "")).upper()
        if member_role not in {"MAIN_APPLICANT", "CO_APPLICANT"}:
            continue

        mobile = member.get("contact_number")
        email = member.get("email")
        full_name = member.get("full_name")
        nric = normalise_nric(member.get("nric_fin"))

        normalized_mobile = mobile.strip() if isinstance(mobile, str) and mobile.strip() else None
        normalized_email = email.strip() if isinstance(email, str) and email.strip() else None
        normalized_name = full_name.strip() if isinstance(full_name, str) and full_name.strip() else "Applicant"

        if not normalized_mobile and not normalized_email:
            continue

        dedupe_key = (
            nric or "",
            normalized_email or "",
            normalized_mobile or "",
        )
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)

        recipients.append(
            {
                "name": normalized_name,
                "role": member_role,
                "nric": nric,
                "email": normalized_email,
                "mobile": normalized_mobile,
            }
        )

    return recipients


def flat_type_sort_key(flat_type):
    """Sort flat types from smallest to largest based on their leading room count."""
    if not isinstance(flat_type, str):
        return (10**9, "")

    cleaned = flat_type.strip().lower()
    number_buffer = ""
    for character in cleaned:
        if character.isdigit():
            number_buffer += character
            continue
        if number_buffer:
            break

    if number_buffer:
        return (int(number_buffer), cleaned)

    return (10**9, cleaned)


def build_queue_slots():
    """Build available 30-minute booking windows, excluding lunch break."""
    if QUEUE_SLOT_START_HOUR >= QUEUE_SLOT_END_HOUR:
        raise BallotOrchestrationError(
            "Invalid queue slot configuration: start hour must be before end hour.",
            step="build_queue_slots",
        )

    slots = []
    current_minutes = QUEUE_SLOT_START_HOUR * 60
    end_minutes = QUEUE_SLOT_END_HOUR * 60
    lunch_start_minutes = QUEUE_SLOT_LUNCH_START_HOUR * 60
    lunch_end_minutes = QUEUE_SLOT_LUNCH_END_HOUR * 60

    while current_minutes + QUEUE_SLOT_DURATION_MINUTES <= end_minutes:
        slot_start = current_minutes
        slot_end = current_minutes + QUEUE_SLOT_DURATION_MINUTES

        overlaps_lunch = slot_start < lunch_end_minutes and slot_end > lunch_start_minutes
        if not overlaps_lunch:
            slots.append((slot_start, slot_end))

        current_minutes += QUEUE_SLOT_DURATION_MINUTES

    if not slots:
        raise BallotOrchestrationError(
            "Invalid queue slot configuration: no valid booking slots generated.",
            status_code=500,
            step="build_queue_slots",
        )

    return slots


QUEUE_SLOTS = build_queue_slots()


def format_minutes_as_hhmm(total_minutes):
    hours = total_minutes // 60
    minutes = total_minutes % 60
    return f"{hours:02d}:{minutes:02d}"


def next_monday_after(input_date):
    """Return the Monday strictly after the provided date."""
    days_ahead = (7 - input_date.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    return input_date + timedelta(days=days_ahead)


def add_business_days(start_date, business_days_to_add):
    """Add business days (Mon-Fri) to a date, skipping weekends."""
    current_date = start_date
    remaining = max(0, int(business_days_to_add))

    while remaining > 0:
        current_date += timedelta(days=1)
        if current_date.weekday() < 5:
            remaining -= 1

    return current_date


def compute_booking_slot(queue_number, first_booking_date):
    if not is_positive_int(queue_number):
        return None

    if not isinstance(first_booking_date, datetime):
        raise BallotOrchestrationError(
            "Booking slot computation requires a valid first booking date.",
            status_code=500,
            step="compute_booking_slot",
        )

    slot_index = (queue_number - 1) // QUEUE_SLOT_CAPACITY
    day_number = (slot_index // len(QUEUE_SLOTS)) + 1
    day_slot_index = slot_index % len(QUEUE_SLOTS)
    slot_start, slot_end = QUEUE_SLOTS[day_slot_index]
    booking_date = add_business_days(first_booking_date.date(), day_number - 1)

    return {
        "day_number": day_number,
        "date": booking_date.isoformat(),
        "start_time": format_minutes_as_hhmm(slot_start),
        "end_time": format_minutes_as_hhmm(slot_end),
        "capacity": QUEUE_SLOT_CAPACITY,
        "duration_minutes": QUEUE_SLOT_DURATION_MINUTES,
        "label": (
            f"Day {day_number} ({booking_date.isoformat()}), "
            f"{format_minutes_as_hhmm(slot_start)}-{format_minutes_as_hhmm(slot_end)}"
        ),
    }


def notify_queue_assignment(
    *,
    project_name,
    town_name,
    flat_type,
    application_id,
    applicant_nric,
    recipient,
    queue_number,
    booking_slot,
):
    email = recipient.get("email") if isinstance(recipient, dict) else None
    mobile = recipient.get("mobile") if isinstance(recipient, dict) else None
    recipient_name = recipient.get("name") if isinstance(recipient, dict) else "Applicant"
    recipient_nric = recipient.get("nric") if isinstance(recipient, dict) else None
    if not email and not mobile:
        return True

    slot_label = booking_slot["label"] if isinstance(booking_slot, dict) else "TBD"
    payload = {
        "eventType": "FlatBookingQueueAssigned",
        "subject": "Flat Selection Queue Number and Appointment Time",
        "applicationId": application_id,
        "applicantId": recipient_nric or applicant_nric,
        "email": email,
        "mobile": mobile,
        "queueNumber": queue_number,
        "bookingSlot": booking_slot,
        "projectName": project_name,
        "townName": town_name,
        "flatType": flat_type,
        "message": (
            f"Hi {recipient_name},\n\n"
            f"Your queue number for {project_name} ({flat_type}) is {queue_number}.\n"
            f"Please head down for flat booking at {slot_label}.\n\n"
            "Regards,\nHDB"
        ),
        "recipientName": recipient_name,
        "recipientRole": "main applicant" if recipient.get("role") == "MAIN_APPLICANT" else "co-applicant",
    }
    return publish_event("application.notify", payload)


def notify_admin_failure(*, exercise_id, audit_id, run_id, trigger_source, error_message, details=None, step=None):
    if not ADMIN_ALERT_EMAIL and not ADMIN_ALERT_MOBILE:
        log_action(
            "Admin alert skipped because admin contact details are not configured",
            level=logging.WARNING,
            exercise_id=exercise_id,
            audit_id=audit_id,
            run_id=run_id,
        )
        return False

    detail_lines = []
    if isinstance(details, list):
        detail_lines = [str(item) for item in details if str(item).strip()]

    message_lines = [
        "Process Ballot encountered a service failure.",
        f"Run ID: {run_id}",
        f"Exercise ID: {exercise_id}",
        f"Audit ID: {audit_id}",
        f"Trigger Source: {trigger_source}",
        f"Failed Step: {step or 'unexpected_error'}",
        f"Error: {error_message}",
    ]
    if detail_lines:
        message_lines.append("Details:")
        message_lines.extend(detail_lines)

    payload = {
        "eventType": "AdminServiceFailure",
        "subject": "Process Ballot Service Failure",
        "applicationId": None,
        "applicantId": None,
        "email": ADMIN_ALERT_EMAIL,
        "mobile": ADMIN_ALERT_MOBILE,
        "message": "\n".join(message_lines),
    }
    return publish_event("application.notify", payload)


def notify_admin_success(
    *,
    exercise_id,
    audit_id,
    run_id,
    trigger_source,
    totals,
    warning_count,
    applicant_notification_sent,
    applicant_notification_failures,
):
    if not ADMIN_ALERT_EMAIL and not ADMIN_ALERT_MOBILE:
        log_action(
            "Admin success alert skipped because admin contact details are not configured",
            level=logging.WARNING,
            exercise_id=exercise_id,
            audit_id=audit_id,
            run_id=run_id,
        )
        return False

    totals = totals if isinstance(totals, dict) else {}
    message_lines = [
        "Process Ballot completed successfully.",
        f"Run ID: {run_id}",
        f"Exercise ID: {exercise_id}",
        f"Audit ID: {audit_id}",
        f"Trigger Source: {trigger_source}",
        "",
        "Run Summary:",
        f"- Projects processed: {totals.get('projects_processed', 0)}",
        f"- Submitted applications considered: {totals.get('submitted_count', 0)}",
        f"- Validated applications: {totals.get('validated_count', 0)}",
        f"- Ineligible after re-validation: {totals.get('ineligible_count', 0)}",
        f"- Eligible after re-validation: {totals.get('eligible_after_validation_count', 0)}",
        f"- Queue numbers assigned: {totals.get('queue_assigned_count', 0)}",
        f"- Flat-selection entries created: {totals.get('flat_selection_entries_created', 0)}",
        "",
        "Notification Summary:",
        f"- Applicant notifications sent: {applicant_notification_sent}",
        f"- Applicant notification publish failures: {applicant_notification_failures}",
        f"- Warnings captured during run: {warning_count}",
    ]

    payload = {
        "eventType": "AdminBallotCompleted",
        "subject": "Process Ballot Completed",
        "applicationId": None,
        "applicantId": None,
        "email": ADMIN_ALERT_EMAIL,
        "mobile": ADMIN_ALERT_MOBILE,
        "message": "\n".join(message_lines),
    }
    return publish_event("application.notify", payload)


def normalize_reason_list(reasons):
    if not isinstance(reasons, list):
        return []
    normalized = []
    seen = set()

    for item in reasons:
        if not isinstance(item, str):
            continue

        for raw_line in item.splitlines():
            cleaned = raw_line.strip()
            if not cleaned:
                continue

            lowered = cleaned.lower()
            if lowered == "ineligibility reasons":
                continue

            # Remove common bullet prefixes.
            if cleaned.startswith("- "):
                cleaned = cleaned[2:].strip()

            # Remove common numbering prefixes such as "1. " or "1) ".
            dot_parts = cleaned.split(". ", 1)
            if len(dot_parts) == 2 and dot_parts[0].isdigit():
                cleaned = dot_parts[1].strip()
            else:
                bracket_parts = cleaned.split(") ", 1)
                if len(bracket_parts) == 2 and bracket_parts[0].isdigit():
                    cleaned = bracket_parts[1].strip()

            if not cleaned:
                continue

            dedupe_key = cleaned.lower()
            if dedupe_key in seen:
                continue

            seen.add(dedupe_key)
            normalized.append(cleaned)

    return normalized


def format_ineligibility_reasons(reasons):
    normalized = normalize_reason_list(reasons)
    if not normalized:
        return "No detailed reason was provided during eligibility re-validation."
    return "\n".join(f"{index}. {reason}" for index, reason in enumerate(normalized, start=1))


def notify_validation_failure(*, application, ineligible_row, project_name):
    if not isinstance(application, dict) or not isinstance(ineligible_row, dict):
        return 0, 0

    recipients = get_notification_recipients(application)
    if not recipients:
        return 0, 0

    reason_text = format_ineligibility_reasons(ineligible_row.get("reasons"))
    sent_count = 0
    failure_count = 0

    for recipient in recipients:
        recipient_name = recipient.get("name") or "Applicant"
        payload = {
            "eventType": "BTOEligibilityFailed",
            "subject": "BTO Eligibility Re-Validation Failed",
            "applicationId": ineligible_row.get("application_id"),
            "applicantId": recipient.get("nric") or ineligible_row.get("main_applicant_nric") or application.get("main_applicant_nric"),
            "email": recipient.get("email"),
            "mobile": recipient.get("mobile"),
            "projectName": project_name,
            "validationStage": "post-application ballot validation",
            "reasons": normalize_reason_list(ineligible_row.get("reasons")),
            "message": (
                f"Hi {recipient_name},\n\n"
                "Your BTO application did not pass the latest eligibility re-validation and cannot proceed to balloting.\n"
                f"Project: {project_name}\n"
                "Reason(s):\n"
                f"{reason_text}\n\n"
                "Regards,\nHDB"
            ),
            "recipientName": recipient_name,
            "recipientRole": "main applicant" if recipient.get("role") == "MAIN_APPLICANT" else "co-applicant",
        }
        if publish_event("application.notify", payload):
            sent_count += 1
        else:
            failure_count += 1

    return sent_count, failure_count


def dispatch_pending_applicant_notifications(pending_notifications):
    if not isinstance(pending_notifications, list):
        return 0, 0

    sent_count = 0
    failure_count = 0

    for notification in pending_notifications:
        if not isinstance(notification, dict):
            continue

        if notification.get("dispatch_status") == "completed":
            continue

        sent_for_notification = 0
        failed_for_notification = 0
        kind = notification.get("kind")
        if kind == "validation_failure":
            sent_for_notification, failed_for_notification = notify_validation_failure(
                application=notification.get("application"),
                ineligible_row=notification.get("ineligible_row"),
                project_name=notification.get("project_name"),
            )
            target_row = notification.get("ineligible_row")
            if isinstance(target_row, dict):
                target_row_notification = target_row.get("notification")
                if not isinstance(target_row_notification, dict):
                    target_row["notification"] = {}
                    target_row_notification = target_row["notification"]
                target_row_notification["sent"] = failed_for_notification == 0 and sent_for_notification > 0
                target_row_notification["sent_count"] = sent_for_notification
                target_row_notification["failed_count"] = failed_for_notification
                target_row_notification["deferred"] = False
        elif kind == "queue_assignment":
            recipients = notification.get("recipients")
            if not isinstance(recipients, list) or not recipients:
                recipients = []
            for recipient in recipients:
                sent = notify_queue_assignment(
                    project_name=notification.get("project_name"),
                    town_name=notification.get("town_name"),
                    flat_type=notification.get("flat_type"),
                    application_id=notification.get("application_id"),
                    applicant_nric=notification.get("applicant_nric"),
                    recipient=recipient,
                    queue_number=notification.get("queue_number"),
                    booking_slot=notification.get("booking_slot"),
                )
                if sent:
                    sent_for_notification += 1
                else:
                    failed_for_notification += 1
            target_entry = notification.get("entry")
            if isinstance(target_entry, dict):
                target_entry_notification = target_entry.get("notification")
                if not isinstance(target_entry_notification, dict):
                    target_entry["notification"] = {}
                    target_entry_notification = target_entry["notification"]
                target_entry_notification["sent"] = failed_for_notification == 0 and sent_for_notification > 0
                target_entry_notification["sent_count"] = sent_for_notification
                target_entry_notification["failed_count"] = failed_for_notification
                target_entry_notification["deferred"] = False
        else:
            notification["dispatch_status"] = "skipped"
            continue

        notification["dispatch_status"] = "completed"
        notification["sent"] = failed_for_notification == 0 and sent_for_notification > 0
        notification["sent_count"] = sent_for_notification
        notification["failed_count"] = failed_for_notification

        sent_count += sent_for_notification
        failure_count += failed_for_notification

    return sent_count, failure_count


# Gets co applicant nric.
def get_co_applicant_nric(application):
    members = application.get("members")
    if not isinstance(members, list):
        return None

    for member in members:
        if not isinstance(member, dict):
            continue
        if member.get("member_role") != "CO_APPLICANT":
            continue
        return normalise_nric(member.get("nric_fin"))

    return None


# Updates audit record.
def update_audit_record(audit_id, status, run_at=None, executed_at=None, error_reason=None):
    """Update an existing audit record status."""
    payload = {"status": status}
    if run_at is not None:
        payload["run_at"] = run_at
    if executed_at is not None:
        payload["executed_at"] = executed_at
    payload["error_reason"] = error_reason

    log_action(
        "Updating ballot audit status",
        audit_id=audit_id,
        status=status,
        run_at=run_at,
        executed_at=executed_at,
        has_error_reason=bool(error_reason),
    )
    request_json(
        "PUT",
        f"{BALLOT_AUDIT_SERVICE_URL}/ballot-audits/{audit_id}",
        json_body=payload,
        allowed_statuses=(200,),
    )
    log_action("Updated ballot audit status", audit_id=audit_id, status=status)


# Fetches projects for exercise.
def fetch_projects_for_exercise(exercise_id):
    """Fetch projects under an exercise."""
    log_action("Fetching projects for exercise", exercise_id=exercise_id)
    status_code, payload = request_json(
        "GET",
        f"{PROJECT_SERVICE_URL}/projects",
        params={"exercise_id": exercise_id},
        allowed_statuses=(200, 404),
    )

    if status_code == 404:
        log_action("No projects found for exercise", exercise_id=exercise_id)
        return []

    rows = payload.get("data")
    if rows is None:
        # Defensive support for alternate envelope casing used by some gateways.
        rows = payload.get("Data")
    if not isinstance(rows, list):
        raise BallotOrchestrationError(
            "Project service returned an invalid project payload.",
            502,
            step="fetch_projects_for_exercise",
        )
    log_action("Fetched projects for exercise", exercise_id=exercise_id, project_count=len(rows))
    return rows


# Fetches ballot candidate applications.
def fetch_ballot_candidate_applications(exercise_id):
    """Fetch ballot candidate applications for the given exercise."""
    log_action("Fetching ballot candidate applications", exercise_id=exercise_id)
    _, payload = request_json(
        "GET",
        f"{APPLICATION_SERVICE_URL}/applications",
        params={"exercise_id": exercise_id, "application_status": "SUCCESSFUL"},
        allowed_statuses=(200,),
    )
    applications = payload.get("applications")
    if not isinstance(applications, list):
        raise BallotOrchestrationError(
            "Applications service returned an invalid payload.",
            502,
            step="fetch_ballot_candidate_applications",
        )

    log_action(
        "Fetched ballot candidate applications",
        exercise_id=exercise_id,
        application_count=len(applications),
        status_filter="SUCCESSFUL",
    )
    return applications


# Fetches ballot chances.
def fetch_ballot_chances(applications, exercise_projects):
    """Fetch ballot chances from flat-selection service using grouped bulk requests."""
    log_action("Preparing ballot chance request", incoming_records=len(applications))
    projects_by_id = {
        item.get("project_id"): item
        for item in exercise_projects
        if isinstance(item, dict) and isinstance(item.get("project_id"), int)
    }

    grouped_rows = defaultdict(list)
    for application in applications:
        if not isinstance(application, dict):
            continue
        application_id = application.get("application_id")
        project_id = application.get("project_id")
        flat_type = application.get("flat_type")
        main_applicant_nric = normalise_nric(application.get("main_applicant_nric"))
        co_applicant_nric = get_co_applicant_nric(application)

        if not is_positive_int(application_id):
            continue
        if not isinstance(project_id, int):
            continue
        if not isinstance(flat_type, str) or not flat_type.strip():
            continue
        if main_applicant_nric is None:
            continue

        project = projects_by_id.get(project_id)
        town_name = str(project.get("town_name") or "").strip() if isinstance(project, dict) else ""
        if not town_name:
            continue

        grouped_rows[(town_name, flat_type.strip())].append(
            {
                "application_id": application_id,
                "applicant_nric": main_applicant_nric,
                "co_applicant_nric": co_applicant_nric,
            }
        )

    groups = [
        {
            "town_name": town_name,
            "flat_type": flat_type,
            "applications": rows,
        }
        for (town_name, flat_type), rows in sorted(grouped_rows.items(), key=lambda item: (item[0][0], item[0][1]))
    ]

    if not groups:
        log_action("No valid applications for chance lookup", chance_request_count=0)
        return {}

    log_action("Fetching ballot chances", chance_group_count=len(groups))
    _, payload = request_json(
        "POST",
        f"{FLAT_SELECTION_SERVICE_URL}/flat-selection/chances",
        json_body={"groups": groups},
        allowed_statuses=(200,),
    )

    data = payload.get("data")
    raw_groups = data.get("groups") if isinstance(data, dict) else None
    if not isinstance(raw_groups, list):
        raise BallotOrchestrationError(
            "Flat selection chance endpoint returned an invalid grouped payload.",
            502,
            step="fetch_ballot_chances",
        )

    chance_map = {}
    for group in raw_groups:
        if not isinstance(group, dict):
            continue
        rows = group.get("results")
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue

            application_id = row.get("application_id")
            base_chance = row.get("base_chance")
            extra_chance = row.get("extra_chance")
            final_chance = row.get("final_chance")

            if not is_positive_int(application_id):
                continue
            if not is_positive_int(final_chance):
                continue

            chance_map[application_id] = {
                "base_chance": base_chance if isinstance(base_chance, int) and base_chance >= 0 else None,
                "extra_chance": extra_chance if isinstance(extra_chance, int) and extra_chance >= 0 else None,
                "final_chance": final_chance,
            }

    log_action("Fetched ballot chances", chance_result_count=len(chance_map))
    return chance_map


def build_validation_skip_result(application, reasons):
    """Build a consistent validation result when a record cannot be sent upstream."""
    application_id = application.get("application_id") if isinstance(application, dict) else None
    main_applicant_nric = normalise_nric(application.get("main_applicant_nric")) if isinstance(application, dict) else None
    co_applicant_nric = get_co_applicant_nric(application) if isinstance(application, dict) else None
    return {
        "application_id": application_id,
        "main_applicant_nric": main_applicant_nric,
        "co_applicant_nric": co_applicant_nric,
        "eligible": False,
        "ineligibility_reasons": reasons,
        "application_update": {
            "attempted": False,
            "updated": False,
            "status_code": 400,
            "message": "Validation skipped due to invalid application payload.",
        },
        "validation_status_code": 400,
    }


def build_validation_groups(applications, projects_by_id):
    """Group validation payload rows by town_name and flat_type for bulk validation."""
    grouped_rows = defaultdict(list)
    local_results = []
    warnings = []

    for application in applications:
        if not isinstance(application, dict):
            warnings.append("Skipped one non-object application record during validation.")
            continue

        application_id = application.get("application_id")
        main_applicant_nric = normalise_nric(application.get("main_applicant_nric"))
        co_applicant_nric = get_co_applicant_nric(application)
        project_id = application.get("project_id")
        flat_type = application.get("flat_type")

        reasons = []
        if not is_positive_int(application_id):
            reasons.append("application_id is missing or invalid.")
        if main_applicant_nric is None:
            reasons.append("main_applicant_nric is missing.")
        if not isinstance(project_id, int):
            reasons.append("project_id is missing or invalid.")
        if not isinstance(flat_type, str) or not flat_type.strip():
            reasons.append("flat_type is missing.")

        project = projects_by_id.get(project_id) if isinstance(project_id, int) else None
        town_name = str(project.get("town_name") or "").strip() if isinstance(project, dict) else ""
        if not town_name:
            reasons.append("town_name could not be resolved from project data.")

        if reasons:
            local_results.append(build_validation_skip_result(application, reasons))
            continue

        grouped_rows[(town_name, flat_type.strip())].append(
            {
                "application_id": application_id,
                "main_applicant_nric": main_applicant_nric,
                "co_applicant_nric": co_applicant_nric,
            }
        )

    groups = [
        {
            "town_name": town_name,
            "flat_type": flat_type,
            "applications": rows,
        }
        for (town_name, flat_type), rows in sorted(grouped_rows.items(), key=lambda item: (item[0][0], item[0][1]))
    ]
    return groups, local_results, warnings


# Validates submitted applications.
def validate_submitted_applications(applications, exercise_projects):
    """Validate all submitted applications in grouped batches and collect ineligible outcomes."""
    log_action("Running validation pass for submitted applications", application_count=len(applications))
    projects_by_id = {
        item.get("project_id"): item
        for item in exercise_projects
        if isinstance(item, dict) and isinstance(item.get("project_id"), int)
    }
    results = []
    ineligible_rows = []
    warnings = []

    groups, local_results, local_warnings = build_validation_groups(applications, projects_by_id)
    results.extend(local_results)
    warnings.extend(local_warnings)

    for start in range(0, len(groups), VALIDATION_BATCH_SIZE):
        batch_groups = groups[start:start + VALIDATION_BATCH_SIZE]
        _, payload = request_json(
            "POST",
            f"{VALIDATE_ELIGIBILITY_SERVICE_URL}/validate-eligibility/bulk",
            json_body={"groups": batch_groups},
            allowed_statuses=(200,),
        )

        bulk_groups = payload.get("groups")
        if not isinstance(bulk_groups, list):
            raise BallotOrchestrationError(
                "Validate-eligibility bulk endpoint returned an invalid grouped payload.",
                502,
                step="validate_submitted_applications",
            )

        top_level_warnings = payload.get("warnings")
        if isinstance(top_level_warnings, list):
            warnings.extend(item for item in top_level_warnings if isinstance(item, str))

        expected_group_keys = {
            (group["town_name"], group["flat_type"])
            for group in batch_groups
        }
        seen_group_keys = set()

        for group in bulk_groups:
            if not isinstance(group, dict):
                continue
            town_name = group.get("town_name")
            flat_type = group.get("flat_type")
            if not isinstance(town_name, str) or not isinstance(flat_type, str):
                continue

            seen_group_keys.add((town_name, flat_type))

            group_warnings = group.get("warnings")
            if isinstance(group_warnings, list):
                warnings.extend(
                    f"[{town_name} / {flat_type}] {item}"
                    for item in group_warnings
                    if isinstance(item, str)
                )

            group_results = group.get("results")
            if not isinstance(group_results, list):
                raise BallotOrchestrationError(
                    "Validate-eligibility bulk endpoint returned an invalid group results payload.",
                    502,
                    step="validate_submitted_applications",
                )

            results.extend(item for item in group_results if isinstance(item, dict))

        missing_groups = sorted(expected_group_keys - seen_group_keys)
        if missing_groups:
            raise BallotOrchestrationError(
                "Validate-eligibility bulk endpoint did not return all requested groups.",
                502,
                details=[f"Missing validation group for town '{town_name}' flat_type '{flat_type}'." for town_name, flat_type in missing_groups],
                step="validate_submitted_applications",
            )


    for result in results:
        if result.get("eligible"):
            continue

        normalized_reasons = normalize_reason_list(result.get("ineligibility_reasons", []))
        # Always ensure a reason is present
        if not normalized_reasons:
            normalized_reasons = ["No eligibility or ballot failure reason was provided by the system."]
            log_action(
                "Eligibility/ballot failure with no reason provided",
                level=logging.WARNING,
                application_id=result.get("application_id"),
                main_applicant_nric=result.get("main_applicant_nric"),
            )

        ineligible_row = {
            "application_id": result.get("application_id"),
            "main_applicant_nric": result.get("main_applicant_nric"),
            "co_applicant_nric": result.get("co_applicant_nric"),
            "reasons": normalized_reasons,
            "reason_summary": " | ".join(normalized_reasons) if normalized_reasons else None,
            "formatted_reasons": format_ineligibility_reasons(normalized_reasons),
            "application_update": result.get("application_update", {}),
        }
        ineligible_rows.append(ineligible_row)

        update_meta = ineligible_row["application_update"]
        attempted = update_meta.get("attempted")
        updated = update_meta.get("updated")
        if attempted and not updated:
            warnings.append(
                f"Failed to update application {ineligible_row['application_id']} to ineligible status: "
                f"{update_meta.get('message') or 'unknown error.'}"
            )
        # Extra debug logging for unsuccessful transitions
        log_action(
            "Application marked as unsuccessful after ballot/validation",
            level=logging.WARNING,
            application_id=ineligible_row["application_id"],
            main_applicant_nric=ineligible_row["main_applicant_nric"],
            reasons=ineligible_row["reasons"],
            reason_summary=ineligible_row["reason_summary"],
        )

    for warning in warnings:
        log_action("Validation warning", level=logging.WARNING, warning=warning)

    log_action(
        "Completed validation pass for submitted applications",
        validated_count=len(results),
        ineligible_count=len(ineligible_rows),
        warning_count=len(warnings),
        batch_size=VALIDATION_BATCH_SIZE,
        validation_group_count=len(groups),
    )

    return results, ineligible_rows, warnings


# Runs ballot for group.
def run_ballot_for_group(group_applications, chance_map, group_context=None):
    """Call ballot service for one town and flat-type group."""
    request_rows = []
    request_ids = []

    for application in group_applications:
        application_id = application.get("application_id")
        if not is_positive_int(application_id):
            continue

        chances = chance_map.get(
            application_id,
            {"final_chance": 2},
        )

        request_rows.append(
            {
                "applicationId": application_id,
                "finalChances": chances["final_chance"],
            }
        )
        request_ids.append(application_id)

    log_action(
        "Prepared ballot group payload",
        group_context=group_context,
        submitted_count=len(group_applications),
        valid_request_count=len(request_rows),
    )

    if not request_rows:
        return [], []

    _, payload = request_json(
        "POST",
        f"{BALLOT_SERVICE_URL}/ballot/run",
        json_body={"applications": request_rows},
        allowed_statuses=(200,),
    )

    data = payload.get("data")
    raw_results = data.get("results") if isinstance(data, dict) else None
    if not isinstance(raw_results, list):
        raise BallotOrchestrationError(
            "Ballot service returned an invalid results payload.",
            502,
            step="run_ballot_for_group",
        )

    log_action(
        "Received ballot service results",
        group_context=group_context,
        raw_result_count=len(raw_results),
    )

    warnings = []
    seen = set()
    ordered_ids = []

    for row in sorted(
        (item for item in raw_results if isinstance(item, dict)),
        key=lambda item: item.get("queueNumber") if isinstance(item.get("queueNumber"), int) else 10**9,
    ):
        application_id = row.get("applicationId")
        if application_id not in request_ids:
            continue
        if application_id in seen:
            continue
        seen.add(application_id)
        ordered_ids.append(application_id)

    missing_ids = [application_id for application_id in request_ids if application_id not in seen]
    if missing_ids:
        warnings.append(
            "Ballot service did not return queue results for some applications. "
            f"Applied deterministic fallback for: {', '.join(str(item) for item in missing_ids)}"
        )
        log_action(
            "Applied queue fallback for missing ballot results",
            level=logging.WARNING,
            group_context=group_context,
            missing_application_ids=missing_ids,
        )
        ordered_ids.extend(sorted(missing_ids))

    normalised_results = [
        {"applicationId": application_id, "queueNumber": index + 1}
        for index, application_id in enumerate(ordered_ids)
    ]

    log_action(
        "Normalised ballot results",
        group_context=group_context,
        queue_assigned_count=len(normalised_results),
    )

    return normalised_results, warnings


# Creates flat selection entries in bulk.
def create_flat_selection_entries_bulk(records, town_name=None, flat_type=None):
    """Create many flat-selection entries in one call and return result map by application_id."""
    if not isinstance(records, list) or not records:
        return {}

    request_payload = {"records": records}
    if isinstance(town_name, str) and town_name.strip():
        request_payload["town_name"] = town_name.strip()
    if isinstance(flat_type, str) and flat_type.strip():
        request_payload["flat_type"] = flat_type.strip()

    _, response_payload = request_json(
        "POST",
        f"{FLAT_SELECTION_SERVICE_URL}/flat-selection/bulk",
        json_body=request_payload,
        allowed_statuses=(200, 201),
    )

    data = response_payload.get("data")
    raw_results = data.get("results") if isinstance(data, dict) else None
    if not isinstance(raw_results, list):
        raise BallotOrchestrationError(
            "Flat selection bulk endpoint returned an invalid payload.",
            502,
            step="create_flat_selection_entries_bulk",
        )

    result_map = {}
    for row in raw_results:
        if not isinstance(row, dict):
            continue

        application_id = row.get("application_id")
        if not is_positive_int(application_id):
            continue

        created = bool(row.get("created"))
        existing = bool(row.get("existing"))
        selection_id = row.get("selection_id")
        message = row.get("message")
        if not isinstance(message, str) or not message.strip():
            if created:
                message = "Flat selection entry created."
            elif existing:
                message = f"Application {application_id} already has a flat-selection record."
            else:
                message = "Flat selection entry was not created."

        result_map[application_id] = {
            "created": created,
            "existing": existing,
            "selection_id": selection_id if isinstance(selection_id, int) else None,
            "message": message,
        }

    return result_map


# Detects incomplete flat-selection writes for one project result.
def project_has_flat_selection_failures(project_result):
    if not isinstance(project_result, dict):
        return False

    entries = project_result.get("entries")
    if not isinstance(entries, list):
        return False

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        flat_selection = entry.get("flat_selection")
        if not isinstance(flat_selection, dict):
            continue
        if flat_selection.get("existing"):
            continue
        if flat_selection.get("created"):
            continue
        return True

    return False


# Processes project.
def process_project(project, applications, chance_map, first_booking_date):
    """Execute ballot processing for a single project."""
    project_id = int(project["project_id"])
    project_name = str(project.get("project_name") or f"Project {project_id}")
    town_name = str(project.get("town_name") or "Unknown")

    log_action(
        "Processing project for ballot",
        project_id=project_id,
        project_name=project_name,
        town_name=town_name,
        submitted_application_count=len(applications),
    )

    grouped = defaultdict(list)
    warnings = []
    for application in applications:
        if not isinstance(application, dict):
            warnings.append(f"Skipped non-object application record in project {project_id}.")
            continue

        application_id = application.get("application_id")
        if not is_positive_int(application_id):
            warnings.append(f"Skipped one application in project {project_id}: invalid application_id.")
            continue

        flat_type = application.get("flat_type")
        if not isinstance(flat_type, str) or not flat_type.strip():
            warnings.append(f"Skipped application {application_id}: missing flat_type.")
            continue

        grouped[(town_name, flat_type.strip())].append(application)

    log_action(
        "Grouped project applications by town and flat_type",
        project_id=project_id,
        group_count=len(grouped),
    )

    entries = []
    ballot_groups = []
    queue_assigned_count = 0
    created_entries = 0
    pending_notifications = []

    for group_key in sorted(grouped.keys(), key=lambda item: (flat_type_sort_key(item[1]), str(item[0]).lower())):
        group_town_name, group_flat_type = group_key
        group_applications = grouped[group_key]

        log_action(
            "Processing ballot group",
            project_id=project_id,
            town_name=group_town_name,
            flat_type=group_flat_type,
            group_application_count=len(group_applications),
        )

        ballot_results, group_warnings = run_ballot_for_group(
            group_applications,
            chance_map,
            group_context={
                "project_id": project_id,
                "town_name": group_town_name,
                "flat_type": group_flat_type,
            },
        )
        warnings.extend(group_warnings)

        group_queue_assigned_count = 0
        group_created_entries = 0
        group_existing_entries = 0
        group_write_failures = 0
        group_entries = []
        group_queue_start = 1 if ballot_results else 0
        group_bulk_records = []
        group_entries_pending_bulk = []

        group_lookup = {
            item.get("application_id"): item
            for item in group_applications
            if is_positive_int(item.get("application_id"))
        }

        for ballot_item in ballot_results:
            application_id = ballot_item["applicationId"]
            queue_number = ballot_item["queueNumber"]

            queue_assigned_count += 1
            group_queue_assigned_count += 1

            application = group_lookup.get(application_id, {})
            main_applicant_nric = normalise_nric(application.get("main_applicant_nric"))
            co_applicant_nric = get_co_applicant_nric(application)
            flat_type = application.get("flat_type")
            chances = chance_map.get(application_id, {"final_chance": 2})

            entry = {
                "application_id": application_id,
                "main_applicant_nric": main_applicant_nric,
                "co_applicant_nric": co_applicant_nric,
                "flat_type": flat_type,
                "town_name": group_town_name,
                "final_chance": chances["final_chance"],
                "ticket_weight": chances["final_chance"],
                "queue_number": queue_number,
                "booking_slot": compute_booking_slot(queue_number, first_booking_date),
                "queue_result": "queued",
                "flat_selection": {
                    "created": False,
                    "existing": False,
                    "selection_id": None,
                    "message": "Skipped because application payload is incomplete.",
                },
            }

            if not main_applicant_nric:
                entry["flat_selection"]["message"] = "Skipped because main_applicant_nric is missing."
                warnings.append(
                    f"Skipped flat-selection write for application {application_id}: main_applicant_nric is missing."
                )
                group_write_failures += 1
            else:
                group_bulk_records.append(
                    {
                        "application_id": application_id,
                        "project_id": project_id,
                        "queue_number": queue_number,
                        "applicant_nric": main_applicant_nric,
                        "co_applicant_nric": co_applicant_nric,
                    }
                )
                group_entries_pending_bulk.append(entry)
                entry["flat_selection"] = {
                    "created": False,
                    "existing": False,
                    "selection_id": None,
                    "message": "Pending flat-selection bulk write.",
                }

            group_entries.append(entry)
            entries.append(entry)

        if group_bulk_records:
            try:
                bulk_results = create_flat_selection_entries_bulk(
                    group_bulk_records,
                    town_name=group_town_name,
                    flat_type=group_flat_type,
                )

                for entry in group_entries_pending_bulk:
                    application_id = entry["application_id"]
                    selection_result = bulk_results.get(application_id)
                    if not isinstance(selection_result, dict):
                        warning = (
                            f"Unable to find flat-selection bulk result for application {application_id} "
                            f"(project {project_id}, queue {entry['queue_number']})."
                        )
                        warnings.append(warning)
                        group_write_failures += 1
                        entry["flat_selection"] = {
                            "created": False,
                            "existing": False,
                            "selection_id": None,
                            "message": warning,
                        }
                        continue

                    if selection_result["created"]:
                        created_entries += 1
                        group_created_entries += 1
                        entry["flat_selection"] = {
                            "created": True,
                            "existing": False,
                            "selection_id": selection_result["selection_id"],
                            "message": "Queue entry created.",
                        }
                    elif selection_result["existing"]:
                        group_existing_entries += 1
                        entry["flat_selection"] = {
                            "created": False,
                            "existing": True,
                            "selection_id": selection_result["selection_id"],
                            "message": selection_result["message"],
                        }
                    else:
                        group_write_failures += 1
                        entry["flat_selection"] = {
                            "created": False,
                            "existing": False,
                            "selection_id": selection_result["selection_id"],
                            "message": selection_result["message"],
                        }
            except BallotOrchestrationError as exc:
                warning = (
                    f"Unable to write flat selection entries in bulk for project {project_id}, "
                    f"town {group_town_name}, flat_type {group_flat_type}: {exc.message}"
                )
                warnings.append(warning)
                group_write_failures += len(group_entries_pending_bulk)
                for entry in group_entries_pending_bulk:
                    entry["flat_selection"] = {
                        "created": False,
                        "existing": False,
                        "selection_id": None,
                        "message": warning,
                    }

        for entry in group_entries:
            application = group_lookup.get(entry["application_id"], {})
            recipients = get_notification_recipients(application)
            is_queued = entry.get("queue_result") == "queued"
            if not is_queued:
                continue

            entry["notification"] = {
                "sent": False,
                "deferred": True,
                "recipient_count": len(recipients),
            }
            pending_notifications.append(
                {
                    "kind": "queue_assignment",
                    "project_name": project_name,
                    "town_name": group_town_name,
                    "flat_type": group_flat_type,
                    "application_id": entry["application_id"],
                    "applicant_nric": entry.get("main_applicant_nric"),
                    "recipients": recipients,
                    "queue_number": entry.get("queue_number"),
                    "booking_slot": entry.get("booking_slot"),
                    "entry": entry,
                }
            )

        group_queue_end = len(ballot_results)

        log_action(
            "Completed ballot group",
            project_id=project_id,
            town_name=group_town_name,
            flat_type=group_flat_type,
            queue_assigned_count=group_queue_assigned_count,
            queue_start=group_queue_start,
            queue_end=group_queue_end,
            flat_selection_created=group_created_entries,
            flat_selection_existing=group_existing_entries,
            flat_selection_failed=group_write_failures,
            warning_count=len(group_warnings),
        )

        ballot_groups.append(
            {
                "town_name": group_town_name,
                "flat_type": group_flat_type,
                "submitted_count": len(group_applications),
                "queue_assigned_count": group_queue_assigned_count,
                "queue_start": group_queue_start,
                "queue_end": group_queue_end,
                "entries": group_entries,
            }
        )

    result = {
        "project_id": project_id,
        "project_name": project_name,
        "town_name": town_name,
        "submitted_count": len(applications),
        "queue_assigned_count": queue_assigned_count,
        "queue_start": 1 if queue_assigned_count > 0 else 0,
        "queue_end": queue_assigned_count,
        "flat_selection_entries_created": created_entries,
        "entries": entries,
        "ballot_groups": ballot_groups,
        "pending_notifications": pending_notifications,
        "warnings": warnings,
    }

    log_action(
        "Completed project ballot processing",
        project_id=project_id,
        submitted_count=result["submitted_count"],
        queue_assigned_count=result["queue_assigned_count"],
        flat_selection_entries_created=result["flat_selection_entries_created"],
        group_count=len(ballot_groups),
        warning_count=len(warnings),
    )
    return result


# Validates run payload.
def validate_run_payload(data):
    """Validate run payload and return (cleaned, errors)."""
    if not isinstance(data, dict):
        return None, ["Request body must be a JSON object."]

    errors = []
    cleaned = {"skip_audit": False, "trigger_source": "manual"}

    exercise_id = data.get("exercise_id")
    if not isinstance(exercise_id, int) or exercise_id <= 0:
        errors.append("exercise_id is required and must be a positive integer.")
    else:
        cleaned["exercise_id"] = exercise_id

    audit_id = data.get("audit_id")
    if audit_id is not None:
        if not isinstance(audit_id, int) or audit_id <= 0:
            errors.append("audit_id must be a positive integer when provided.")
        else:
            cleaned["audit_id"] = audit_id
    else:
        cleaned["audit_id"] = None

    skip_audit = data.get("skip_audit")
    if skip_audit is not None:
        if not isinstance(skip_audit, bool):
            errors.append("skip_audit must be boolean when provided.")
        else:
            cleaned["skip_audit"] = skip_audit

    trigger_source = data.get("trigger_source")
    if trigger_source is not None:
        if not isinstance(trigger_source, str) or not trigger_source.strip():
            errors.append("trigger_source must be a non-empty string when provided.")
        else:
            cleaned["trigger_source"] = trigger_source.strip()

    if not cleaned["skip_audit"] and cleaned["audit_id"] is None:
        errors.append("audit_id is required unless skip_audit is true.")

    return cleaned, errors


# Handles empty totals.
def empty_totals():
    return {
        "submitted_count": 0,
        "queue_assigned_count": 0,
        "projects_processed": 0,
        "flat_selection_entries_created": 0,
        "validated_count": 0,
        "ineligible_count": 0,
        "eligible_after_validation_count": 0,
    }


# Executes ballot run.
def execute_ballot_run(exercise_id, trigger_source="manual", audit_id=None, skip_audit=False):
    """Execute one end-to-end ballot run for an exercise."""
    run_id = str(uuid.uuid4())
    started_at = now_iso()
    ballot_datetime = datetime.utcnow()
    first_booking_date = datetime.combine(next_monday_after(ballot_datetime.date()), datetime.min.time())
    all_warnings = []
    manage_audit = not skip_audit
    pending_applicant_notifications = []
    applicant_notification_sent = 0
    applicant_notification_failures = 0

    log_action(
        "Starting process-ballot run",
        run_id=run_id,
        exercise_id=exercise_id,
        audit_id=audit_id,
        trigger_source=trigger_source,
        manage_audit=manage_audit,
    )

    try:
        if manage_audit:
            if not isinstance(audit_id, int):
                raise BallotOrchestrationError(
                    "audit_id is required when skip_audit is false.",
                    status_code=400,
                    step="execute_ballot_run.validate_audit",
                )
            update_audit_record(
                audit_id,
                "in progress",
                run_at=started_at,
                executed_at=started_at,
                error_reason=None,
            )

        exercise_projects = fetch_projects_for_exercise(exercise_id)
        log_action(
            "Loaded exercise projects",
            run_id=run_id,
            exercise_id=exercise_id,
            project_count=len(exercise_projects),
        )
        if not exercise_projects:
            if manage_audit and isinstance(audit_id, int):
                update_audit_record(audit_id, "completed", executed_at=now_iso(), error_reason=None)
            log_action(
                "No projects to process for run",
                run_id=run_id,
                exercise_id=exercise_id,
            )
            return (
                {
                    "code": 200,
                    "data": {
                        "run_id": run_id,
                        "exercise_id": exercise_id,
                        "audit_id": audit_id,
                        "audit_status": "completed" if manage_audit else "external",
                        "trigger_source": trigger_source,
                        "started_at": started_at,
                        "completed_at": now_iso(),
                        "projects": [],
                        "totals": empty_totals(),
                        "validation": {
                            "validated_applications": [],
                            "ineligible_applications": [],
                        },
                        "warnings": ["No projects found for this exercise. Nothing was processed."],
                    },
                },
                200,
            )

        initial_candidate_applications = fetch_ballot_candidate_applications(exercise_id)
        log_action(
            "Loaded initial ballot candidate applications",
            run_id=run_id,
            application_count=len(initial_candidate_applications),
        )
        validation_results, ineligible_applications, validation_warnings = validate_submitted_applications(
            initial_candidate_applications,
            exercise_projects,
        )
        projects_by_id = {
            item.get("project_id"): item
            for item in exercise_projects
            if isinstance(item, dict) and isinstance(item.get("project_id"), int)
        }
        applications_by_id = {
            item.get("application_id"): item
            for item in initial_candidate_applications
            if isinstance(item, dict) and is_positive_int(item.get("application_id"))
        }

        for ineligible_row in ineligible_applications:
            if not isinstance(ineligible_row, dict):
                continue

            application_id = ineligible_row.get("application_id")
            if not is_positive_int(application_id):
                continue

            source_application = applications_by_id.get(application_id)
            if not isinstance(source_application, dict):
                continue

            project_id = source_application.get("project_id")
            project = projects_by_id.get(project_id) if isinstance(project_id, int) else None
            project_name = (
                str(project.get("project_name") or f"Project {project_id}")
                if isinstance(project, dict)
                else "Unknown Project"
            )

            pending_applicant_notifications.append(
                {
                    "kind": "validation_failure",
                    "application": source_application,
                    "ineligible_row": ineligible_row,
                    "project_name": project_name,
                }
            )
            ineligible_row["notification"] = {
                "sent": False,
                "deferred": True,
                "project_name": project_name,
            }

        all_warnings.extend(validation_warnings)
        log_action(
            "Completed validation stage",
            run_id=run_id,
            validated_count=len(validation_results),
            ineligible_count=len(ineligible_applications),
            validation_warning_count=len(validation_warnings),
            deferred_validation_notification_count=len(ineligible_applications),
        )

        # Filter out ineligible applications from the initial fetch (no second fetch needed)
        ineligible_application_ids = {
            row.get("application_id")
            for row in ineligible_applications
            if isinstance(row, dict) and is_positive_int(row.get("application_id"))
        }
        pre_filter_count = len(initial_candidate_applications)
        candidate_applications = [
            application
            for application in initial_candidate_applications
            if not (
                isinstance(application, dict)
                and is_positive_int(application.get("application_id"))
                and application.get("application_id") in ineligible_application_ids
            )
        ]
        filtered_count = pre_filter_count - len(candidate_applications)
        if filtered_count > 0:
            log_action(
                "Filtered ineligible applications for ballot processing",
                run_id=run_id,
                ineligible_id_count=len(ineligible_application_ids),
                filtered_count=filtered_count,
            )
        chance_map = fetch_ballot_chances(candidate_applications, exercise_projects)
        log_action(
            "Prepared post-validation workload",
            run_id=run_id,
            eligible_candidate_count=len(candidate_applications),
            chance_count=len(chance_map),
        )

        grouped_by_project = defaultdict(list)
        skipped_application_count = 0

        for application in candidate_applications:
            if not isinstance(application, dict):
                skipped_application_count += 1
                continue
            project_id = application.get("project_id")
            if not isinstance(project_id, int):
                skipped_application_count += 1
                continue
            grouped_by_project[project_id].append(application)

        if skipped_application_count > 0:
            all_warnings.append(
                f"Skipped {skipped_application_count} ballot candidate application record(s) with missing or invalid project_id."
            )
            log_action(
                "Skipped invalid ballot candidate records before project grouping",
                level=logging.WARNING,
                run_id=run_id,
                skipped_application_count=skipped_application_count,
            )

        project_results = []
        totals = empty_totals()
        totals["validated_count"] = len(validation_results)
        totals["ineligible_count"] = len(ineligible_applications)
        totals["eligible_after_validation_count"] = len(candidate_applications)
        flat_selection_failure_messages = []

        for project in sorted(exercise_projects, key=lambda item: int(item.get("project_id", 0))):
            project_id = project.get("project_id")
            if not isinstance(project_id, int):
                all_warnings.append("Skipped one project record with invalid project_id.")
                log_action(
                    "Skipped invalid project record",
                    level=logging.WARNING,
                    run_id=run_id,
                    project=str(project),
                )
                continue

            project_applications = grouped_by_project.get(project_id, [])
            project_result = process_project(project, project_applications, chance_map, first_booking_date)
            project_warnings = project_result.pop("warnings", [])
            all_warnings.extend(project_warnings)
            project_results.append(project_result)
            project_notifications = project_result.pop("pending_notifications", [])
            if isinstance(project_notifications, list):
                pending_applicant_notifications.extend(project_notifications)

            if project_has_flat_selection_failures(project_result):
                flat_selection_failure_messages.append(
                    f"Flat-selection writes were incomplete for project {project_id} ({project_result['project_name']})."
                )

            totals["submitted_count"] += project_result["submitted_count"]
            totals["queue_assigned_count"] += project_result["queue_assigned_count"]
            totals["flat_selection_entries_created"] += project_result["flat_selection_entries_created"]
            totals["projects_processed"] += 1
            log_action(
                "Project result aggregated into run totals",
                run_id=run_id,
                project_id=project_id,
                project_submitted_count=project_result["submitted_count"],
                project_queue_assigned_count=project_result["queue_assigned_count"],
                project_flat_selection_entries_created=project_result["flat_selection_entries_created"],
            )

        newly_sent, newly_failed = dispatch_pending_applicant_notifications(pending_applicant_notifications)
        applicant_notification_sent += newly_sent
        applicant_notification_failures += newly_failed

        if applicant_notification_failures > 0:
            all_warnings.append(
                f"Failed to publish {applicant_notification_failures} applicant notification(s)."
            )

        if flat_selection_failure_messages:
            raise BallotOrchestrationError(
                "Ballot run could not be completed because one or more flat-selection queue entries were not created.",
                status_code=502,
                details=flat_selection_failure_messages,
                step="execute_ballot_run.verify_flat_selection_writes",
            )

        if manage_audit and isinstance(audit_id, int):
            update_audit_record(audit_id, "completed", executed_at=now_iso(), error_reason=None)

        admin_notification_sent = notify_admin_success(
            exercise_id=exercise_id,
            audit_id=audit_id,
            run_id=run_id,
            trigger_source=trigger_source,
            totals=totals,
            warning_count=len(all_warnings),
            applicant_notification_sent=applicant_notification_sent,
            applicant_notification_failures=applicant_notification_failures,
        )
        if not admin_notification_sent:
            all_warnings.append("Failed to publish admin completion notification.")

        log_action(
            "Process-ballot run completed",
            run_id=run_id,
            exercise_id=exercise_id,
            totals=totals,
            warning_count=len(all_warnings),
            applicant_notification_sent=applicant_notification_sent,
            applicant_notification_failures=applicant_notification_failures,
            admin_notification_sent=admin_notification_sent,
            audit_status="completed" if manage_audit else "external",
        )

        return (
            {
                "code": 200,
                "data": {
                    "run_id": run_id,
                    "exercise_id": exercise_id,
                    "audit_id": audit_id,
                    "audit_status": "completed" if manage_audit else "external",
                    "trigger_source": trigger_source,
                    "started_at": started_at,
                    "completed_at": now_iso(),
                    "projects": project_results,
                    "totals": totals,
                    "validation": {
                        "validated_applications": validation_results,
                        "ineligible_applications": ineligible_applications,
                    },
                    "notifications": {
                        "admin_notified": bool(admin_notification_sent),
                        "applicant_notifications_sent": applicant_notification_sent,
                        "applicant_notification_failures": applicant_notification_failures,
                    },
                    "warnings": all_warnings,
                },
            },
            200,
        )

    except BallotOrchestrationError as exc:
        newly_sent, newly_failed = dispatch_pending_applicant_notifications(pending_applicant_notifications)
        applicant_notification_sent += newly_sent
        applicant_notification_failures += newly_failed

        failure_details = list(exc.details) if isinstance(exc.details, list) else []
        if newly_sent > 0:
            failure_details.append(
                f"Sent {newly_sent} pending applicant notification(s) before returning the error."
            )
        if newly_failed > 0:
            failure_details.append(
                f"Failed to publish {newly_failed} pending applicant notification(s) while handling the error."
            )

        log_action(
            "Process-ballot run failed with orchestration error",
            level=logging.ERROR,
            run_id=run_id,
            exercise_id=exercise_id,
            audit_id=audit_id,
            error_message=exc.message,
            status_code=exc.status_code,
        )
        if manage_audit and isinstance(audit_id, int):
            try:
                update_audit_record(
                    audit_id,
                    "error",
                    executed_at=now_iso(),
                    error_reason=exc.message,
                )
            except BallotOrchestrationError:
                logger.exception("Failed to update audit status to error")

        notify_admin_failure(
            exercise_id=exercise_id,
            audit_id=audit_id,
            run_id=run_id,
            trigger_source=trigger_source,
            error_message=exc.message,
            details=failure_details,
            step=exc.step,
        )

        return (
            {
                "code": exc.status_code,
                "message": exc.message,
                "details": failure_details,
                "data": {
                    "run_id": run_id,
                    "exercise_id": exercise_id,
                    "audit_id": audit_id,
                    "audit_status": "error" if manage_audit and isinstance(audit_id, int) else "external",
                    "trigger_source": trigger_source,
                    "started_at": started_at,
                    "completed_at": now_iso(),
                    "notifications": {
                        "applicant_notifications_sent": applicant_notification_sent,
                        "applicant_notification_failures": applicant_notification_failures,
                    },
                },
            },
            exc.status_code,
        )
    except Exception as exc:
        newly_sent, newly_failed = dispatch_pending_applicant_notifications(pending_applicant_notifications)
        applicant_notification_sent += newly_sent
        applicant_notification_failures += newly_failed

        failure_details = []
        if newly_sent > 0:
            failure_details.append(
                f"Sent {newly_sent} pending applicant notification(s) before returning the error."
            )
        if newly_failed > 0:
            failure_details.append(
                f"Failed to publish {newly_failed} pending applicant notification(s) while handling the error."
            )

        logger.exception("Unexpected process ballot error")
        log_action(
            "Process-ballot run failed with unexpected error",
            level=logging.ERROR,
            run_id=run_id,
            exercise_id=exercise_id,
            audit_id=audit_id,
            error=str(exc),
        )
        if manage_audit and isinstance(audit_id, int):
            try:
                update_audit_record(
                    audit_id,
                    "error",
                    executed_at=now_iso(),
                    error_reason=str(exc),
                )
            except BallotOrchestrationError:
                logger.exception("Failed to update audit status to error")

        notify_admin_failure(
            exercise_id=exercise_id,
            audit_id=audit_id,
            run_id=run_id,
            trigger_source=trigger_source,
            error_message=str(exc),
            details=failure_details,
            step="execute_ballot_run.unexpected_exception",
        )

        return (
            {
                "code": 500,
                "message": f"Unexpected error while processing ballot: {exc}",
                "details": failure_details,
                "data": {
                    "run_id": run_id,
                    "exercise_id": exercise_id,
                    "audit_id": audit_id,
                    "audit_status": "error" if manage_audit and isinstance(audit_id, int) else "external",
                    "trigger_source": trigger_source,
                    "started_at": started_at,
                    "completed_at": now_iso(),
                    "notifications": {
                        "applicant_notifications_sent": applicant_notification_sent,
                        "applicant_notification_failures": applicant_notification_failures,
                    },
                },
            },
            500,
        )




# Runs process ballot.
@app.route("/process-ballot/run", methods=["POST"])
def run_process_ballot():
    """
    Execute one ballot run
    ---
    tags:
      - Process Ballot
    summary: Run ballot for an exercise
    description: |
      Runs an end-to-end ballot flow for the exercise:
      1) validate current submitted applications,
      2) auto-mark ineligible records,
      3) re-fetch remaining eligible submissions,
      4) compute chances,
      5) call ballot service by town_name + flat_type,
      6) persist queue outcomes in flat-selection.
      Cron scheduling is owned by ballot-audit service.
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            required:
              - exercise_id
            properties:
              exercise_id:
                type: integer
                example: 6
              audit_id:
                type: integer
                nullable: true
                example: 33
              skip_audit:
                type: boolean
                example: false
              trigger_source:
                type: string
                example: manual
    responses:
      200:
        description: Ballot run completed.
      400:
        description: Validation error.
      500:
        description: Internal processing error.
      502:
        description: Upstream dependency error.
    """
    payload = request.get_json(silent=True)
    cleaned, errors = validate_run_payload(payload)
    if errors:
        log_action(
            "Rejected process-ballot run request due to validation errors",
            level=logging.WARNING,
            payload_type=type(payload).__name__,
            error_count=len(errors),
        )
        return jsonify({"code": 400, "message": "Validation error.", "errors": errors}), 400

    log_action(
        "Accepted process-ballot run request",
        exercise_id=cleaned["exercise_id"],
        audit_id=cleaned["audit_id"],
        skip_audit=cleaned["skip_audit"],
        trigger_source=cleaned["trigger_source"],
    )

    response_payload, status_code = execute_ballot_run(
        cleaned["exercise_id"],
        trigger_source=cleaned["trigger_source"],
        audit_id=cleaned["audit_id"],
        skip_audit=cleaned["skip_audit"],
    )
    return jsonify(response_payload), status_code


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5011, debug=False)
