"""Process Ballot orchestration service."""

from collections import defaultdict
from datetime import datetime
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
PROJECT_SERVICE_URL = os.environ.get("PROJECT_SERVICE_URL", "http://localhost:5012")
VALIDATE_ELIGIBILITY_SERVICE_URL = os.environ.get(
    "VALIDATE_ELIGIBILITY_SERVICE_URL",
    "http://localhost:5013",
)
FLAT_SELECTION_SERVICE_URL = os.environ.get("FLAT_SELECTION_SERVICE_URL", "http://localhost:5002")
REQUEST_TIMEOUT = float(os.environ.get("REQUEST_TIMEOUT_SECONDS", "20"))
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()

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
    def __init__(self, message, status_code=502, details=None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.details = details or []


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
        raise BallotOrchestrationError(message, status_code=502)

    try:
        payload = response.json()
    except ValueError:
        payload = {}

    if not isinstance(payload, dict):
        payload = {}

    return response.status_code, payload


# Checks whether positive int.
def is_positive_int(value):
    return isinstance(value, int) and value > 0


# Handles normalise nric.
def normalise_nric(value):
    if not isinstance(value, str):
        return None
    cleaned = value.strip().upper()
    return cleaned if cleaned else None


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
    if not isinstance(rows, list):
        raise BallotOrchestrationError("Project service returned an invalid project payload.", 502)
    log_action("Fetched projects for exercise", exercise_id=exercise_id, project_count=len(rows))
    return rows


# Fetches ballot candidate applications.
def fetch_ballot_candidate_applications(exercise_id):
    """Fetch ballot candidate applications for the given exercise."""
    log_action("Fetching ballot candidate applications", exercise_id=exercise_id)
    _, payload = request_json(
        "GET",
        f"{APPLICATION_SERVICE_URL}/applications",
        params={"exercise_id": exercise_id},
        allowed_statuses=(200,),
    )
    applications = payload.get("applications")
    if not isinstance(applications, list):
        raise BallotOrchestrationError("Applications service returned an invalid payload.", 502)

    ballot_statuses = {"SUCCESSFUL"}
    candidates = [
        application
        for application in applications
        if isinstance(application, dict) and application.get("application_status") in ballot_statuses
    ]

    log_action(
        "Fetched ballot candidate applications",
        exercise_id=exercise_id,
        application_count=len(candidates),
        total_exercise_application_count=len(applications),
    )
    return candidates


# Fetches ballot chances.
def fetch_ballot_chances(applications):
    """Fetch ballot chances from flat-selection service."""
    log_action("Preparing ballot chance request", incoming_records=len(applications))
    payload_rows = []
    for application in applications:
        if not isinstance(application, dict):
            continue
        application_id = application.get("application_id")
        main_applicant_nric = normalise_nric(application.get("main_applicant_nric"))
        co_applicant_nric = get_co_applicant_nric(application)

        if not is_positive_int(application_id):
            continue
        if main_applicant_nric is None:
            continue

        payload_rows.append(
            {
                "application_id": application_id,
                "applicant_nric": main_applicant_nric,
                "co_applicant_nric": co_applicant_nric,
            }
        )

    if not payload_rows:
        log_action("No valid applications for chance lookup", chance_request_count=0)
        return {}

    log_action("Fetching ballot chances", chance_request_count=len(payload_rows))
    _, payload = request_json(
        "GET",
        f"{FLAT_SELECTION_SERVICE_URL}/flat-selection/chances",
        params={"applications": json.dumps(payload_rows, separators=(",", ":"))},
        allowed_statuses=(200,),
    )

    rows = payload.get("data")
    if not isinstance(rows, list):
        raise BallotOrchestrationError(
            "Flat selection chance endpoint returned an invalid payload.",
            502,
        )

    chance_map = {}
    for row in rows:
        if not isinstance(row, dict):
            continue

        application_id = row.get("application_id")
        final_chance = row.get("final_chance")

        if not is_positive_int(application_id):
            continue
        if not is_positive_int(final_chance):
            continue

        chance_map[application_id] = {
            "final_chance": final_chance,
        }

    log_action("Fetched ballot chances", chance_result_count=len(chance_map))
    return chance_map


# Validates application record.
def validate_application_record(application):
    """Validate one submitted application via validate-eligibility service."""
    application_id = application.get("application_id")
    main_applicant_nric = normalise_nric(application.get("main_applicant_nric"))
    co_applicant_nric = get_co_applicant_nric(application)

    reasons = []
    if not is_positive_int(application_id):
        reasons.append("application_id is missing or invalid.")
    if main_applicant_nric is None:
        reasons.append("main_applicant_nric is missing.")

    if reasons:
        log_action(
            "Skipped validate-eligibility call due to invalid application payload",
            level=logging.WARNING,
            application_id=application_id,
            reason_count=len(reasons),
        )
        return {
            "application_id": application_id,
            "main_applicant_nric": main_applicant_nric,
            "co_applicant_nric": co_applicant_nric,
            "eligible": False,
            "ineligibility_reasons": reasons,
            "application_update": {
                "attempted": False,
                "updated": False,
                "status_code": None,
                "message": "Validation skipped due to invalid application payload.",
            },
            "validation_status_code": 400,
        }

    status_code, payload = request_json(
        "GET",
        f"{VALIDATE_ELIGIBILITY_SERVICE_URL}/validate-eligibility",
        params={
            "application_id": application_id,
            "main_applicant_nric": main_applicant_nric,
            "co_applicant_nric": co_applicant_nric,
        },
        allowed_statuses=(200, 400, 404),
    )

    if status_code in (400, 404):
        error_message = payload.get("error") or payload.get("message") or "Validation request rejected."
        details = payload.get("details") if isinstance(payload.get("details"), list) else []
        reasons = [error_message] if isinstance(error_message, str) else ["Validation request rejected."]
        reasons.extend(item for item in details if isinstance(item, str))
        log_action(
            "Validate-eligibility request was rejected",
            level=logging.WARNING,
            application_id=application_id,
            status_code=status_code,
            reason_count=len(reasons),
        )

        return {
            "application_id": application_id,
            "main_applicant_nric": main_applicant_nric,
            "co_applicant_nric": co_applicant_nric,
            "eligible": False,
            "ineligibility_reasons": reasons,
            "application_update": {
                "attempted": False,
                "updated": False,
                "status_code": status_code,
                "message": "Validate-eligibility request failed for this application.",
            },
            "validation_status_code": status_code,
        }

    eligible = payload.get("eligible")
    if not isinstance(eligible, bool):
        raise BallotOrchestrationError(
            f"Validate-eligibility service returned an invalid payload for application {application_id}.",
            502,
        )

    ineligibility_reasons = payload.get("ineligibility_reasons")
    if not isinstance(ineligibility_reasons, list):
        ineligibility_reasons = []
    ineligibility_reasons = [reason for reason in ineligibility_reasons if isinstance(reason, str)]

    application_update = payload.get("application_update")
    if not isinstance(application_update, dict):
        application_update = {
            "attempted": False,
            "updated": False,
            "status_code": None,
            "message": "No application update metadata returned.",
        }

    log_action(
        "Validated submitted application",
        level=logging.DEBUG,
        application_id=application_id,
        eligible=eligible,
        ineligibility_reason_count=len(ineligibility_reasons),
        application_update_attempted=bool(application_update.get("attempted")),
        application_update_updated=bool(application_update.get("updated")),
    )

    return {
        "application_id": application_id,
        "main_applicant_nric": main_applicant_nric,
        "co_applicant_nric": co_applicant_nric,
        "eligible": eligible,
        "ineligibility_reasons": ineligibility_reasons,
        "application_update": application_update,
        "validation_status_code": status_code,
    }


# Validates submitted applications.
def validate_submitted_applications(applications):
    """Validate all submitted applications and collect ineligible outcomes."""
    log_action("Running validation pass for submitted applications", application_count=len(applications))
    results = []
    ineligible_rows = []
    warnings = []

    for application in applications:
        if not isinstance(application, dict):
            warnings.append("Skipped one non-object application record during validation.")
            continue

        result = validate_application_record(application)
        results.append(result)

        if result["eligible"]:
            continue

        ineligible_row = {
            "application_id": result.get("application_id"),
            "main_applicant_nric": result.get("main_applicant_nric"),
            "co_applicant_nric": result.get("co_applicant_nric"),
            "reasons": result.get("ineligibility_reasons", []),
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

    for warning in warnings:
        log_action("Validation warning", level=logging.WARNING, warning=warning)

    log_action(
        "Completed validation pass for submitted applications",
        validated_count=len(results),
        ineligible_count=len(ineligible_rows),
        warning_count=len(warnings),
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


# Processes project.
def process_project(project, applications, chance_map):
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

    for group_key in sorted(grouped.keys(), key=lambda item: (item[0], item[1])):
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
                "queue_result": "queued",
                "flat_selection": {
                    "created": False,
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
                            "selection_id": None,
                            "message": warning,
                        }
                        continue

                    if selection_result["created"]:
                        created_entries += 1
                        group_created_entries += 1
                        entry["flat_selection"] = {
                            "created": True,
                            "selection_id": selection_result["selection_id"],
                            "message": "Queue entry created.",
                        }
                    elif selection_result["existing"]:
                        group_existing_entries += 1
                        entry["flat_selection"] = {
                            "created": False,
                            "selection_id": selection_result["selection_id"],
                            "message": selection_result["message"],
                        }
                    else:
                        group_write_failures += 1
                        entry["flat_selection"] = {
                            "created": False,
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
                        "selection_id": None,
                        "message": warning,
                    }

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
    all_warnings = []
    manage_audit = not skip_audit

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
            initial_candidate_applications
        )
        all_warnings.extend(validation_warnings)
        log_action(
            "Completed validation stage",
            run_id=run_id,
            validated_count=len(validation_results),
            ineligible_count=len(ineligible_applications),
            validation_warning_count=len(validation_warnings),
        )

        # After validation updates ineligible records via application service,
        # fetch ballot candidates again to continue only with eligible applications.
        candidate_applications = fetch_ballot_candidate_applications(exercise_id)
        ineligible_application_ids = {
            row.get("application_id")
            for row in ineligible_applications
            if isinstance(row, dict) and is_positive_int(row.get("application_id"))
        }
        if ineligible_application_ids:
            pre_filter_count = len(candidate_applications)
            candidate_applications = [
                application
                for application in candidate_applications
                if not (
                    isinstance(application, dict)
                    and is_positive_int(application.get("application_id"))
                    and application.get("application_id") in ineligible_application_ids
                )
            ]
            filtered_count = pre_filter_count - len(candidate_applications)
            if filtered_count > 0:
                log_action(
                    "Filtered ineligible applications from post-validation ballot candidates",
                    run_id=run_id,
                    ineligible_id_count=len(ineligible_application_ids),
                    filtered_count=filtered_count,
                )
        chance_map = fetch_ballot_chances(candidate_applications)
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
            project_result = process_project(project, project_applications, chance_map)
            project_warnings = project_result.pop("warnings", [])
            all_warnings.extend(project_warnings)
            project_results.append(project_result)

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

        if manage_audit and isinstance(audit_id, int):
            update_audit_record(audit_id, "completed", executed_at=now_iso(), error_reason=None)

        log_action(
            "Process-ballot run completed",
            run_id=run_id,
            exercise_id=exercise_id,
            totals=totals,
            warning_count=len(all_warnings),
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
                    "warnings": all_warnings,
                },
            },
            200,
        )

    except BallotOrchestrationError as exc:
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

        return (
            {
                "code": exc.status_code,
                "message": exc.message,
                "details": exc.details,
                "data": {
                    "run_id": run_id,
                    "exercise_id": exercise_id,
                    "audit_id": audit_id,
                    "audit_status": "error" if manage_audit and isinstance(audit_id, int) else "external",
                    "trigger_source": trigger_source,
                    "started_at": started_at,
                    "completed_at": now_iso(),
                },
            },
            exc.status_code,
        )
    except Exception as exc:
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

        return (
            {
                "code": 500,
                "message": f"Unexpected error while processing ballot: {exc}",
                "data": {
                    "run_id": run_id,
                    "exercise_id": exercise_id,
                    "audit_id": audit_id,
                    "audit_status": "error" if manage_audit and isinstance(audit_id, int) else "external",
                    "trigger_source": trigger_source,
                    "started_at": started_at,
                    "completed_at": now_iso(),
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
