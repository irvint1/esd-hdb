"""Ballot audit service with scheduler ownership for ballot cron jobs."""

import atexit
from datetime import datetime
import logging
import os

from apscheduler.jobstores.base import JobLookupError
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from flasgger import Swagger
import requests


DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "mysql+mysqlconnector://root@localhost:3306/ballot_audits",
)
PROCESS_BALLOT_SERVICE_URL = os.environ.get(
    "PROCESS_BALLOT_SERVICE_URL",
    "http://localhost:5011",
)
REQUEST_TIMEOUT = float(os.environ.get("REQUEST_TIMEOUT_SECONDS", "20"))
SCHEDULER_TIMEZONE = os.environ.get("SCHEDULER_TIMEZONE", "Asia/Singapore")
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()

VALID_STATUSES = ("scheduled", "in progress", "completed", "error", "cancelled")

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)s [ballot_audit] %(message)s",
)
logger = logging.getLogger("ballot_audit")

app = Flask(__name__)
CORS(app)
app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_recycle": 299}
db = SQLAlchemy(app)

app.config["SWAGGER"] = {
    "title": "Ballot Audit Microservice API",
    "version": 1.0,
    "openapi": "3.0.2",
    "description": "Stores ballot audit records and owns ballot cron scheduling.",
}
swagger = Swagger(app)

scheduler = BackgroundScheduler(timezone=SCHEDULER_TIMEZONE)
scheduler.start()
atexit.register(lambda: scheduler.shutdown(wait=False))


class BallotAudit(db.Model):
    __tablename__ = "ballot_audits"

    audit_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    exercise_id = db.Column(db.Integer, nullable=False)
    run_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    executed_at = db.Column(db.DateTime, nullable=True)
    cron_expression = db.Column(db.String(100), nullable=True)
    error_reason = db.Column(db.Text, nullable=True)
    status = db.Column(
        db.Enum(*VALID_STATUSES, name="ballot_audit_status_enum"),
        nullable=False,
        default="in progress",
    )
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    # Handles to dict.
    def to_dict(self):
        payload = {
            "audit_id": self.audit_id,
            "exercise_id": self.exercise_id,
            "run_at": self.run_at.isoformat() if self.run_at else None,
            "executed_at": self.executed_at.isoformat() if self.executed_at else None,
            "cron_expression": self.cron_expression,
            "error_reason": self.error_reason,
            "status": self.status,
        }
        payload["next_run_at"] = get_next_run_iso(self.audit_id)
        return payload


# Parses iso datetime.
def parse_iso_datetime(value, field_name):
    if value is None:
        return None, None
    if not isinstance(value, str) or not value.strip():
        return None, f"{field_name} must be an ISO datetime string."
    try:
        return datetime.fromisoformat(value.strip()), None
    except ValueError:
        return None, f"{field_name} must be a valid ISO datetime string."


# Parses cron expression.
def parse_cron_expression(value):
    if value is None:
        return None, None
    if not isinstance(value, str):
        return None, "cron_expression must be a string."

    expression = value.strip()
    if expression == "":
        return "", None

    parts = expression.split()
    if len(parts) < 5:
        return None, "cron_expression must contain at least 5 cron fields."

    # Accept full crontab-style lines (e.g. "0 9 1 2 * /path/to/script.sh")
    # but only persist the 5 scheduling fields.
    schedule_expression = " ".join(parts[:5])

    try:
        CronTrigger.from_crontab(schedule_expression, timezone=SCHEDULER_TIMEZONE)
    except Exception:
        return None, "cron_expression must be a valid 5-field crontab expression."

    return schedule_expression, None


# Handles job id for.
def job_id_for(audit_id):
    return f"ballot-audit-{audit_id}"


# Gets next run iso.
def get_next_run_iso(audit_id):
    job = scheduler.get_job(job_id_for(audit_id))
    if not job or not job.next_run_time:
        return None
    return job.next_run_time.isoformat()


# Removes schedule.
def remove_schedule(audit_id):
    try:
        scheduler.remove_job(job_id_for(audit_id))
    except JobLookupError:
        return


# Handles add or update schedule.
def add_or_update_schedule(audit):
    if not audit.cron_expression:
        return
    trigger = CronTrigger.from_crontab(audit.cron_expression, timezone=SCHEDULER_TIMEZONE)
    scheduler.add_job(
        run_scheduled_ballot,
        trigger=trigger,
        args=[audit.audit_id],
        id=job_id_for(audit.audit_id),
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )


# Runs scheduled ballot.
def run_scheduled_ballot(audit_id):
    with app.app_context():
        audit = db.session.get(BallotAudit, audit_id)
        if audit is None:
            remove_schedule(audit_id)
            return

        if not audit.cron_expression or audit.status != "scheduled":
            remove_schedule(audit_id)
            return

        try:
            response = requests.post(
                f"{PROCESS_BALLOT_SERVICE_URL}/process-ballot/run",
                json={
                    "exercise_id": audit.exercise_id,
                    "audit_id": audit.audit_id,
                    "trigger_source": f"scheduled:{audit.audit_id}",
                },
                timeout=REQUEST_TIMEOUT,
            )
            if response.status_code != 200:
                error_message = f"Process ballot returned HTTP {response.status_code}."
                try:
                    payload = response.json()
                    upstream_message = payload.get("message") or payload.get("error")
                    if isinstance(upstream_message, str) and upstream_message.strip():
                        error_message = upstream_message
                except ValueError:
                    pass

                logger.warning(
                    "Scheduled ballot run for audit %s failed with status %s",
                    audit.audit_id,
                    response.status_code,
                )
                audit.status = "error"
                audit.executed_at = datetime.utcnow()
                audit.error_reason = error_message
                audit.cron_expression = None
                db.session.commit()
                remove_schedule(audit.audit_id)
        except requests.RequestException as exc:
            logger.exception("Scheduled ballot run for audit %s failed: %s", audit.audit_id, exc)
            audit.status = "error"
            audit.executed_at = datetime.utcnow()
            audit.error_reason = str(exc)
            audit.cron_expression = None
            db.session.commit()
            remove_schedule(audit.audit_id)


# Loads existing schedules.
def load_existing_schedules():
    with app.app_context():
        records = db.session.scalars(
            db.select(BallotAudit).where(
                BallotAudit.cron_expression.is_not(None),
                BallotAudit.status == "scheduled",
            )
        ).all()
        for record in records:
            try:
                add_or_update_schedule(record)
            except Exception:
                logger.exception("Failed to restore schedule for audit_id=%s", record.audit_id)


# Lists audits.
@app.route("/ballot-audits", methods=["GET"])
def list_audits():
    query = db.select(BallotAudit)
    errors = []

    exercise_id = request.args.get("exercise_id")
    if exercise_id is not None:
        if not exercise_id.isdigit():
            errors.append("exercise_id must be an integer.")
        else:
            query = query.where(BallotAudit.exercise_id == int(exercise_id))

    status = request.args.get("status")
    if status is not None:
        if status not in VALID_STATUSES:
            errors.append(f"status must be one of: {', '.join(VALID_STATUSES)}.")
        else:
            query = query.where(BallotAudit.status == status)

    if errors:
        return jsonify({"code": 400, "message": "Validation error.", "errors": errors}), 400

    rows = db.session.scalars(query.order_by(BallotAudit.audit_id.desc())).all()
    if not rows:
        return jsonify({"code": 404, "message": "No ballot audit records found."}), 404
    return jsonify({"code": 200, "data": [row.to_dict() for row in rows]}), 200


# Creates audit.
@app.route("/ballot-audits", methods=["POST"])
def create_audit():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"code": 400, "message": "Request body must be valid JSON."}), 400

    errors = []

    exercise_id = data.get("exercise_id")
    if not isinstance(exercise_id, int):
        errors.append("exercise_id is required and must be an integer.")

    run_at, run_at_error = parse_iso_datetime(data.get("run_at"), "run_at")
    if run_at_error:
        errors.append(run_at_error)

    executed_at, executed_at_error = parse_iso_datetime(data.get("executed_at"), "executed_at")
    if executed_at_error:
        errors.append(executed_at_error)

    cron_expression, cron_error = parse_cron_expression(data.get("cron_expression"))
    if cron_error:
        errors.append(cron_error)

    error_reason = data.get("error_reason")
    if error_reason is not None and not isinstance(error_reason, str):
        errors.append("error_reason must be a string when provided.")

    status = data.get("status")
    if status is None:
        status = "scheduled" if cron_expression else "in progress"
    elif status not in VALID_STATUSES:
        errors.append(f"status must be one of: {', '.join(VALID_STATUSES)}.")

    if status in ("completed", "error", "cancelled"):
        cron_expression = None

    if status == "scheduled" and not cron_expression:
        errors.append("status 'scheduled' requires cron_expression.")

    if errors:
        return jsonify({"code": 400, "message": "Validation error.", "errors": errors}), 400

    audit = BallotAudit(
        exercise_id=exercise_id,
        run_at=run_at or datetime.utcnow(),
        executed_at=executed_at,
        status=status,
        cron_expression=cron_expression or None,
        error_reason=error_reason,
    )

    try:
        db.session.add(audit)
        db.session.commit()
        if audit.cron_expression and audit.status == "scheduled":
            add_or_update_schedule(audit)
    except Exception as exc:
        db.session.rollback()
        remove_schedule(audit.audit_id if audit.audit_id else -1)
        return jsonify({"code": 500, "message": f"Error creating ballot audit: {exc}"}), 500

    return jsonify({"code": 201, "data": audit.to_dict()}), 201


# Updates audit.
@app.route("/ballot-audits/<int:audit_id>", methods=["PUT"])
def update_audit(audit_id):
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"code": 400, "message": "Request body must be valid JSON."}), 400

    audit = db.session.get(BallotAudit, audit_id)
    if audit is None:
        return jsonify({"code": 404, "message": f"Ballot audit {audit_id} not found."}), 404

    allowed_fields = {"status", "run_at", "executed_at", "cron_expression", "error_reason"}
    unexpected_fields = [key for key in data if key not in allowed_fields]
    if unexpected_fields:
        return (
            jsonify(
                {
                    "code": 400,
                    "message": "Validation error.",
                    "errors": [f"Unexpected fields: {', '.join(unexpected_fields)}."],
                }
            ),
            400,
        )

    errors = []
    should_schedule = False

    if "run_at" in data:
        parsed_run_at, run_at_error = parse_iso_datetime(data.get("run_at"), "run_at")
        if run_at_error:
            errors.append(run_at_error)
        else:
            audit.run_at = parsed_run_at

    if "executed_at" in data:
        parsed_executed_at, executed_at_error = parse_iso_datetime(data.get("executed_at"), "executed_at")
        if executed_at_error:
            errors.append(executed_at_error)
        else:
            audit.executed_at = parsed_executed_at

    if "cron_expression" in data:
        raw_cron = data.get("cron_expression")
        parsed_cron, cron_error = parse_cron_expression(raw_cron)
        if cron_error:
            errors.append(cron_error)
        elif raw_cron is None or parsed_cron == "":
            audit.cron_expression = None
            remove_schedule(audit.audit_id)
            if "status" not in data and audit.status == "scheduled":
                audit.status = "cancelled"
        else:
            audit.cron_expression = parsed_cron
            should_schedule = True
            if "status" not in data:
                audit.status = "scheduled"

    if "status" in data:
        status = data.get("status")
        if status not in VALID_STATUSES:
            errors.append(f"status must be one of: {', '.join(VALID_STATUSES)}.")
        else:
            audit.status = status
            if status in ("cancelled", "completed", "error"):
                audit.cron_expression = None
                remove_schedule(audit.audit_id)
            elif status == "scheduled":
                if not audit.cron_expression:
                    errors.append("status 'scheduled' requires cron_expression.")
                else:
                    should_schedule = True

    if "error_reason" in data:
        error_reason = data.get("error_reason")
        if error_reason is not None and not isinstance(error_reason, str):
            errors.append("error_reason must be a string when provided.")
        else:
            audit.error_reason = error_reason

    if errors:
        return jsonify({"code": 400, "message": "Validation error.", "errors": errors}), 400

    try:
        db.session.commit()
        if should_schedule and audit.cron_expression and audit.status == "scheduled":
            add_or_update_schedule(audit)
    except Exception as exc:
        db.session.rollback()
        return jsonify({"code": 500, "message": f"Error updating ballot audit: {exc}"}), 500

    return jsonify({"code": 200, "data": audit.to_dict()}), 200


if __name__ == "__main__":
    load_existing_schedules()
    app.run(host="0.0.0.0", port=5000, debug=False)
