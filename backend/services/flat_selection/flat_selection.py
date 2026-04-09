from datetime import datetime, timedelta
import os

from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from flasgger import Swagger
from sqlalchemy import and_, or_

FLAT_SELECTION_STATUSES = (
    "balloted",
    "selecting",
    "reserved",
    "paid",
    "forfeited",
    "not_called",
    "no_flat_selected",
)
CALLED_DOWN_STATUSES = {"selecting", "reserved", "paid", "forfeited", "no_flat_selected"}
NOT_CALLED_STATUSES = {"not_called"}

app = Flask(__name__)
CORS(app)
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
    "DATABASE_URL", "mysql+mysqlconnector://root@localhost:3306/flat_selection"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_recycle": 299}

db = SQLAlchemy(app)

app.config["SWAGGER"] = {
    "title": "Flat Selection Microservice API",
    "version": 1.0,
    "openapi": "3.0.2",
    "description": (
        "Manages flat-selection records, forfeiture penalties, and ballot chance calculation."
    ),
}
swagger = Swagger(app)


# Handles normalise nric.
def normalise_nric(value):
    if not isinstance(value, str):
        return None
    value = value.strip().upper()
    return value if value else None


# Parses positive int.
def parse_positive_int(value):
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if value > 0 else None


# Validates one selection payload.
def validate_selection_payload(data, field_prefix=""):
    if not isinstance(data, dict):
        label = field_prefix[:-1] if field_prefix.endswith(".") else field_prefix or "record"
        return None, [f"{label} must be an object."]

    application_id = parse_positive_int(data.get("application_id"))
    project_id = parse_positive_int(data.get("project_id"))
    queue_number = parse_positive_int(data.get("queue_number"))
    applicant_nric = normalise_nric(data.get("applicant_nric"))
    co_applicant_nric = normalise_nric(data.get("co_applicant_nric"))

    errors = []
    if application_id is None:
        errors.append(
            f"{field_prefix}application_id is required and must be a positive integer."
        )
    if project_id is None:
        errors.append(
            f"{field_prefix}project_id is required and must be a positive integer."
        )
    if queue_number is None:
        errors.append(
            f"{field_prefix}queue_number is required and must be a positive integer."
        )
    if applicant_nric is None:
        errors.append(
            f"{field_prefix}applicant_nric is required and must be a non-empty string."
        )

    if errors:
        return None, errors

    return {
        "application_id": application_id,
        "project_id": project_id,
        "queue_number": queue_number,
        "applicant_nric": applicant_nric,
        "co_applicant_nric": co_applicant_nric,
    }, []


# Handles to boolean.
def to_boolean(value):
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    lowered = value.strip().lower()
    if lowered in ("true", "1", "yes"):
        return True
    if lowered in ("false", "0", "no"):
        return False
    return None


class FlatSelection(db.Model):
    __tablename__ = "flat_selection"

    selection_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    application_id = db.Column(db.Integer, nullable=False, index=True)
    applicant_nric = db.Column(db.String(20), nullable=False, index=True)
    co_applicant_nric = db.Column(db.String(20), nullable=True, index=True)
    project_id = db.Column(db.Integer, nullable=False, index=True)
    queue_number = db.Column(db.Integer, nullable=False)
    flat_id = db.Column(db.Integer, nullable=True)
    status = db.Column(
        db.Enum(*FLAT_SELECTION_STATUSES, name="flat_selection_status_enum"),
        nullable=False,
        default="balloted",
    )
    reserved_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    # Handles json.
    def json(self):
        return {
            "selection_id": self.selection_id,
            "application_id": self.application_id,
            "applicant_nric": self.applicant_nric,
            "co_applicant_nric": self.co_applicant_nric,
            "project_id": self.project_id,
            "queue_number": self.queue_number,
            "flat_id": self.flat_id,
            "status": self.status,
            "reserved_at": self.reserved_at.isoformat() if self.reserved_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class ForfeitPenalty(db.Model):
    __tablename__ = "flat_selection_forfeit_penalty"

    penalty_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    selection_id = db.Column(
        db.Integer,
        db.ForeignKey("flat_selection.selection_id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    selection = db.relationship("FlatSelection", lazy="joined")
    forfeited_at = db.Column(db.DateTime, nullable=False)
    penalty_start_at = db.Column(db.DateTime, nullable=False)
    penalty_end_at = db.Column(db.DateTime, nullable=False, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    # Checks whether active.
    def is_active(self, now=None):
        now = now or datetime.utcnow()
        return self.penalty_end_at > now

    # Handles json.
    def json(self, now=None):
        applicant_nric = self.selection.applicant_nric if self.selection else None
        co_applicant_nric = self.selection.co_applicant_nric if self.selection else None
        return {
            "penalty_id": self.penalty_id,
            "selection_id": self.selection_id,
            "applicant_nric": applicant_nric,
            "co_applicant_nric": co_applicant_nric,
            "forfeited_at": self.forfeited_at.isoformat(),
            "penalty_start_at": self.penalty_start_at.isoformat(),
            "penalty_end_at": self.penalty_end_at.isoformat(),
            "active": self.is_active(now=now),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# Builds pair condition.
def build_pair_condition(model, applicant_nric, co_applicant_nric):
    if co_applicant_nric:
        return or_(
            and_(
                model.applicant_nric == applicant_nric,
                model.co_applicant_nric == co_applicant_nric,
            ),
            and_(
                model.applicant_nric == co_applicant_nric,
                model.co_applicant_nric == applicant_nric,
            ),
        )

    return or_(
        model.applicant_nric == applicant_nric,
        model.co_applicant_nric == applicant_nric,
    )


# Handles upsert forfeit penalty.
def upsert_forfeit_penalty(selection, now=None):
    now = now or datetime.utcnow()
    penalty_end = now + timedelta(days=365)

    existing = db.session.scalar(
        db.select(ForfeitPenalty).where(ForfeitPenalty.selection_id == selection.selection_id)
    )
    if existing:
        existing.forfeited_at = now
        existing.penalty_start_at = now
        existing.penalty_end_at = penalty_end
        return existing

    record = ForfeitPenalty(
        selection_id=selection.selection_id,
        forfeited_at=now,
        penalty_start_at=now,
        penalty_end_at=penalty_end,
    )
    db.session.add(record)
    return record


# Computes ballot chances.
def compute_ballot_chances(application_id, applicant_nric, co_applicant_nric=None, now=None):
    now = now or datetime.utcnow()

    pair_condition = build_pair_condition(FlatSelection, applicant_nric, co_applicant_nric)
    history_rows = db.session.scalars(
        db.select(FlatSelection)
        .where(pair_condition)
        .order_by(FlatSelection.created_at.desc(), FlatSelection.selection_id.desc())
    ).all()

    latest_penalty = db.session.scalar(
        db.select(ForfeitPenalty)
        .join(
            FlatSelection,
            FlatSelection.selection_id == ForfeitPenalty.selection_id,
        )
        .where(build_pair_condition(FlatSelection, applicant_nric, co_applicant_nric))
        .order_by(ForfeitPenalty.penalty_start_at.desc(), ForfeitPenalty.penalty_id.desc())
    )
    penalty_active = bool(latest_penalty and latest_penalty.penalty_end_at > now)
    penalty_applied_at = latest_penalty.penalty_start_at if latest_penalty else None

    has_called_down_before = any(
        row.application_id != application_id and row.status in CALLED_DOWN_STATUSES
        for row in history_rows
    )

    not_called_streak = 0
    for row in history_rows:
        if row.application_id == application_id:
            continue

        if penalty_applied_at and row.created_at and row.created_at <= penalty_applied_at:
            break

        if row.status in CALLED_DOWN_STATUSES:
            break

        if row.status in NOT_CALLED_STATUSES:
            not_called_streak += 1

    base_chance = 1 if has_called_down_before else 2
    extra_chance = 0 if penalty_active else min(not_called_streak, 2)
    final_chance = base_chance + extra_chance

    return {
        "application_id": application_id,
        "base_chance": base_chance,
        "extra_chance": extra_chance,
        "final_chance": final_chance,
    }


# Gets all.
@app.route("/flat-selection", methods=["GET"])
def get_all():
    status = request.args.get("status")
    project_id_raw = request.args.get("project_id")
    applicant_nric = normalise_nric(request.args.get("applicant_nric"))

    if status is not None and status not in FLAT_SELECTION_STATUSES:
        return jsonify({
            "code": 400,
            "message": f"Valid statuses are: {', '.join(FLAT_SELECTION_STATUSES)}",
        }), 400

    query = db.select(FlatSelection)

    if status:
        query = query.where(FlatSelection.status == status)

    if project_id_raw is not None:
        if not project_id_raw.isdigit() or int(project_id_raw) <= 0:
            return jsonify({"code": 400, "message": "project_id must be a positive integer."}), 400
        query = query.where(FlatSelection.project_id == int(project_id_raw))

    if applicant_nric:
        query = query.where(
            or_(
                FlatSelection.applicant_nric == applicant_nric,
                FlatSelection.co_applicant_nric == applicant_nric,
            )
        )

    query = query.order_by(
        FlatSelection.project_id.asc(),
        FlatSelection.queue_number.asc(),
    )
    selections = db.session.scalars(query).all()

    if not selections:
        return jsonify({"code": 200, "data": []}), 200

    return jsonify({"code": 200, "data": [selection.json() for selection in selections]}), 200


# Gets selection.
@app.route("/flat-selection/<int:selection_id>", methods=["GET"])
def get_selection(selection_id):
    selection = db.session.get(FlatSelection, selection_id)
    if selection is None:
        return jsonify({"code": 404, "message": "Flat selection not found."}), 404
    return jsonify({"code": 200, "data": selection.json()}), 200


# Creates selection.
@app.route("/flat-selection", methods=["POST"])
def create_selection():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"code": 400, "message": "Request body must be a JSON object."}), 400

    cleaned, errors = validate_selection_payload(data)
    if errors:
        return jsonify({"code": 400, "message": errors[0]}), 400

    application_id = cleaned["application_id"]
    project_id = cleaned["project_id"]
    queue_number = cleaned["queue_number"]
    applicant_nric = cleaned["applicant_nric"]
    co_applicant_nric = cleaned["co_applicant_nric"]

    existing = db.session.scalar(
        db.select(FlatSelection).where(
            FlatSelection.application_id == application_id,
        )
    )
    if existing:
        return jsonify({
            "code": 409,
            "message": f"Application {application_id} already has a flat-selection record.",
        }), 409

    selection = FlatSelection(
        application_id=application_id,
        applicant_nric=applicant_nric,
        co_applicant_nric=co_applicant_nric,
        project_id=project_id,
        queue_number=queue_number,
        status="balloted",
    )

    try:
        db.session.add(selection)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return jsonify({"code": 500, "message": f"Error creating flat selection: {exc}"}), 500

    return jsonify({"code": 201, "data": selection.json()}), 201


# Bulk creates selections.
@app.route("/flat-selection/bulk", methods=["POST"])
def create_selection_bulk():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"code": 400, "message": "Request body must be a JSON object."}), 400

    records = data.get("records")
    if not isinstance(records, list) or not records:
        return jsonify({"code": 400, "message": "records is required and must be a non-empty array."}), 400

    errors = []
    cleaned_records = []
    seen_application_ids = set()
    for index, record in enumerate(records):
        cleaned, record_errors = validate_selection_payload(record, f"records[{index}].")
        if record_errors:
            errors.extend(record_errors)
            continue

        application_id = cleaned["application_id"]
        if application_id in seen_application_ids:
            errors.append(f"Duplicate application_id found in request records: {application_id}.")
            continue

        seen_application_ids.add(application_id)
        cleaned_records.append(cleaned)

    if errors:
        return jsonify({"code": 400, "message": "Validation error.", "errors": errors}), 400

    existing_rows = db.session.scalars(
        db.select(FlatSelection).where(FlatSelection.application_id.in_(seen_application_ids))
    ).all()
    existing_by_application_id = {
        row.application_id: row
        for row in existing_rows
    }

    result_by_application_id = {}
    rows_to_create = []
    created_pairs = []

    for record in cleaned_records:
        application_id = record["application_id"]
        existing = existing_by_application_id.get(application_id)
        if existing:
            result_by_application_id[application_id] = {
                "application_id": application_id,
                "project_id": record["project_id"],
                "queue_number": record["queue_number"],
                "created": False,
                "existing": True,
                "selection_id": existing.selection_id,
                "message": f"Application {application_id} already has a flat-selection record.",
            }
            continue

        row = FlatSelection(
            application_id=application_id,
            applicant_nric=record["applicant_nric"],
            co_applicant_nric=record["co_applicant_nric"],
            project_id=record["project_id"],
            queue_number=record["queue_number"],
            status="balloted",
        )
        rows_to_create.append(row)
        created_pairs.append((record, row))
        db.session.add(row)

    try:
        if rows_to_create:
            db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return jsonify({"code": 500, "message": f"Error creating flat selections in bulk: {exc}"}), 500

    for record, row in created_pairs:
        application_id = record["application_id"]
        result_by_application_id[application_id] = {
            "application_id": application_id,
            "project_id": record["project_id"],
            "queue_number": record["queue_number"],
            "created": True,
            "existing": False,
            "selection_id": row.selection_id,
            "message": "Flat selection entry created.",
        }

    ordered_results = [
        result_by_application_id[record["application_id"]]
        for record in cleaned_records
        if record["application_id"] in result_by_application_id
    ]

    created_count = sum(1 for row in ordered_results if row["created"])
    existing_count = sum(1 for row in ordered_results if row["existing"])
    status_code = 201 if created_count > 0 else 200

    return jsonify({
        "code": status_code,
        "data": {
            "town_name": data.get("town_name"),
            "flat_type": data.get("flat_type"),
            "total": len(cleaned_records),
            "created_count": created_count,
            "existing_count": existing_count,
            "results": ordered_results,
        },
    }), status_code


# Handles reserve selection.
@app.route("/flat-selection/<int:selection_id>/reserve", methods=["PUT"])
def reserve_selection(selection_id):
    selection = db.session.get(FlatSelection, selection_id)
    if selection is None:
        return jsonify({"code": 404, "message": "Flat selection not found."}), 404

    data = request.get_json(silent=True)
    flat_id = data.get("flat_id") if isinstance(data, dict) else None
    if parse_positive_int(flat_id) is None:
        return jsonify({"code": 400, "message": "flat_id is required and must be a positive integer."}), 400

    if selection.status not in ("balloted", "selecting"):
        return jsonify({
            "code": 409,
            "message": f"Cannot reserve. Current status: {selection.status}",
        }), 409

    selection.flat_id = int(flat_id)
    selection.status = "reserved"
    selection.reserved_at = datetime.now()

    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return jsonify({"code": 500, "message": f"Error reserving flat selection: {exc}"}), 500

    return jsonify({
        "code": 200,
        "message": f"Selection {selection_id} reserved with flat {flat_id}.",
        "data": selection.json(),
    }), 200


# Handles undo reserve.
@app.route("/flat-selection/<int:selection_id>/undo-reserve", methods=["PUT"])
def undo_reserve(selection_id):
    selection = db.session.get(FlatSelection, selection_id)
    if selection is None:
        return jsonify({"code": 404, "message": "Flat selection not found."}), 404

    if selection.status != "reserved":
        return jsonify({
            "code": 409,
            "message": f"Cannot undo reserve. Current status: {selection.status}",
        }), 409

    selection.flat_id = None
    selection.status = "selecting"
    selection.reserved_at = None

    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return jsonify({"code": 500, "message": f"Error undoing reservation: {exc}"}), 500

    return jsonify({
        "code": 200,
        "message": f"Selection {selection_id} reservation undone.",
        "data": selection.json(),
    }), 200


# Updates status.
@app.route("/flat-selection/<int:selection_id>/status", methods=["PUT"])
def update_status(selection_id):
    selection = db.session.get(FlatSelection, selection_id)
    if selection is None:
        return jsonify({"code": 404, "message": "Flat selection not found."}), 404

    data = request.get_json(silent=True)
    next_status = data.get("status") if isinstance(data, dict) else None
    if next_status not in FLAT_SELECTION_STATUSES:
        return jsonify({
            "code": 400,
            "message": f"Valid statuses are: {', '.join(FLAT_SELECTION_STATUSES)}",
        }), 400

    selection.status = next_status
    if next_status != "reserved":
        selection.reserved_at = None if next_status in (
            "selecting",
            "forfeited",
            "not_called",
            "balloted",
            "no_flat_selected",
        ) else selection.reserved_at

    try:
        if next_status == "forfeited":
            upsert_forfeit_penalty(selection, now=datetime.utcnow())
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return jsonify({"code": 500, "message": f"Error updating status: {exc}"}), 500

    return jsonify({"code": 200, "data": selection.json()}), 200


# Gets ballot chances.
@app.route("/flat-selection/chances", methods=["POST"])
def get_ballot_chances():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"code": 400, "message": "Request body must be a JSON object."}), 400

    groups = payload.get("groups")
    if not isinstance(groups, list) or not groups:
        return jsonify({"code": 400, "message": "groups is required and must be a non-empty array."}), 400

    top_level_warnings = []
    grouped_results = []
    now = datetime.utcnow()

    for group_index, group in enumerate(groups):
        if not isinstance(group, dict):
            top_level_warnings.append(f"groups[{group_index}] must be an object.")
            continue

        town_name = group.get("town_name")
        flat_type = group.get("flat_type")
        applications = group.get("applications")
        if not isinstance(applications, list) or not applications:
            top_level_warnings.append(f"groups[{group_index}].applications must be a non-empty array.")
            continue

        errors = []
        cleaned = []
        seen_application_ids = set()
        for index, item in enumerate(applications):
            if not isinstance(item, dict):
                errors.append(f"applications[{index}] must be an object.")
                continue

            application_id = parse_positive_int(item.get("application_id"))
            applicant_nric = normalise_nric(item.get("applicant_nric") or item.get("main_applicant_nric"))
            co_applicant_nric = normalise_nric(item.get("co_applicant_nric"))

            if application_id is None:
                errors.append(f"applications[{index}].application_id must be a positive integer.")
            if applicant_nric is None:
                errors.append(
                    f"applications[{index}] must include applicant_nric (or main_applicant_nric) as a non-empty string."
                )
            if application_id in seen_application_ids:
                errors.append(f"Duplicate application_id found: {application_id}.")

            if application_id is not None and applicant_nric is not None and application_id not in seen_application_ids:
                seen_application_ids.add(application_id)
                cleaned.append(
                    {
                        "application_id": application_id,
                        "applicant_nric": applicant_nric,
                        "co_applicant_nric": co_applicant_nric,
                    }
                )

        if errors:
            return jsonify({"code": 400, "message": "Validation error.", "errors": errors}), 400

        grouped_results.append(
            {
                "town_name": town_name if isinstance(town_name, str) else None,
                "flat_type": flat_type if isinstance(flat_type, str) else None,
                "count": len(cleaned),
                "results": [
                    compute_ballot_chances(
                        application_id=item["application_id"],
                        applicant_nric=item["applicant_nric"],
                        co_applicant_nric=item["co_applicant_nric"],
                        now=now,
                    )
                    for item in cleaned
                ],
            }
        )

    return jsonify({
        "code": 200,
        "data": {
            "count": sum(group["count"] for group in grouped_results),
            "warnings": top_level_warnings,
            "groups": grouped_results,
        },
    }), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5002, debug=True)
