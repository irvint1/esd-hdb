"""Application service for BTO applications and nested members."""

from datetime import datetime
from decimal import Decimal, InvalidOperation
import os
import re

from flask import Flask, jsonify, request
from flask_cors import CORS
from flasgger import Swagger
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import inspect, or_, text
from sqlalchemy.orm import selectinload

ALLOWED_APPLICATION_STATUSES = (
    "SUBMITTED",
    "SUCCESSFUL",
    "UNSUCCESSFUL",
    "CANCELLED",
)

ALLOWED_MEMBER_ROLES = (
    "MAIN_APPLICANT",
    "CO_APPLICANT",
    "OCCUPANT",
)

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    db_host = os.environ.get("DB_HOST", "localhost")
    db_port = os.environ.get("DB_PORT", "3306")
    db_name = os.environ.get("DB_NAME", "applications")
    db_user = os.environ.get("DB_USER", "root")
    db_password = os.environ.get("DB_PASSWORD", "")
    credentials = f"{db_user}:{db_password}" if db_password else db_user
    DATABASE_URL = f"mysql+mysqlconnector://{credentials}@{db_host}:{db_port}/{db_name}"

app = Flask(__name__)
CORS(app)
app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_recycle": 299}

app.config["SWAGGER"] = {
    "title": "Applications Microservice API",
    "version": 1.0,
    "openapi": "3.0.2",
    "description": "Manages BTO applications and nested application members",
}
swagger = Swagger(app)

db = SQLAlchemy(app)
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class Application(db.Model):
    __tablename__ = "application"

    application_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    exercise_id = db.Column(db.Integer, nullable=False)
    project_id = db.Column(db.Integer, nullable=False)
    flat_type = db.Column(db.String(50), nullable=False)
    main_applicant_nric = db.Column(db.String(20), nullable=False)
    income_document_id = db.Column(db.BigInteger, nullable=True)
    hfe_document_id = db.Column(db.BigInteger, nullable=True)
    application_status = db.Column(
        db.Enum(*ALLOWED_APPLICATION_STATUSES, name="application_status_enum"),
        nullable=False,
        default="SUBMITTED",
    )
    submitted_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.now,
        onupdate=datetime.now,
    )

    members = db.relationship(
        "ApplicationMember",
        back_populates="application",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ApplicationMember.member_id",
    )

    #  Handles to dict for this service.
    def to_dict(self, include_members=True):
        payload = {
            "application_id": self.application_id,
            "exercise_id": self.exercise_id,
            "project_id": self.project_id,
            "flat_type": self.flat_type,
            "main_applicant_nric": self.main_applicant_nric,
            "income_document_id": self.income_document_id,
            "hfe_document_id": self.hfe_document_id,
            "application_status": self.application_status,
            "submitted_at": self.submitted_at.isoformat() if self.submitted_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

        if include_members:
            payload["members"] = [member.to_dict() for member in self.members]

        return payload


class ApplicationMember(db.Model):
    __tablename__ = "application_member"

    member_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    application_id = db.Column(
        db.Integer,
        db.ForeignKey("application.application_id", ondelete="CASCADE"),
        nullable=False,
    )
    member_role = db.Column(
        db.Enum(*ALLOWED_MEMBER_ROLES, name="application_member_role_enum"),
        nullable=False,
    )
    nric_fin = db.Column(db.String(20), nullable=False)
    full_name = db.Column(db.String(255), nullable=False)
    relationship_to_main = db.Column(db.String(50), nullable=False)
    date_of_birth = db.Column(db.Date, nullable=False)
    citizenship_status = db.Column(db.String(20), nullable=False)
    marital_status = db.Column(db.String(20), nullable=True)
    contact_number = db.Column(db.String(30), nullable=True)
    email = db.Column(db.String(255), nullable=True)
    income_amount = db.Column(db.Numeric(12, 2), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.now,
        onupdate=datetime.now,
    )

    application = db.relationship("Application", back_populates="members")

    #  Handles to dict for this service.
    def to_dict(self):
        return {
            "member_id": self.member_id,
            "member_role": self.member_role,
            "nric_fin": self.nric_fin,
            "full_name": self.full_name,
            "relationship_to_main": self.relationship_to_main,
            "date_of_birth": self.date_of_birth.isoformat() if self.date_of_birth else None,
            "citizenship_status": self.citizenship_status,
            "marital_status": self.marital_status,
            "contact_number": self.contact_number,
            "email": self.email,
            "income_amount": float(self.income_amount) if self.income_amount is not None else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


#  Handles is non empty string for this service.
def is_non_empty_string(value):
    return isinstance(value, str) and value.strip() != ""


#  Handles is valid email for this service.
def is_valid_email(value):
    return is_non_empty_string(value) and EMAIL_PATTERN.match(value.strip()) is not None


#  Handles parse date for this service.
def parse_date(value):
    if not is_non_empty_string(value):
        return None

    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


#  Handles parse int for this service.
def parse_int(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


#  Handles parse optional int for this service.
def parse_optional_int(value):
    if value is None:
        return None, None

    parsed = parse_int(value)
    if parsed is None:
        return None, "must be an integer or null."

    return parsed, None


#  Handles parse decimal for this service.
def parse_decimal(value):
    if value is None or isinstance(value, bool):
        return None

    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


#  Handles ensure application member schema for this service.
def ensure_application_member_schema():
    inspector = inspect(db.engine)
    if not inspector.has_table("application_member"):
        return

    existing_columns = {column["name"] for column in inspector.get_columns("application_member")}
    statements = []

    if "contact_number" not in existing_columns:
        statements.append(
            "ALTER TABLE application_member ADD COLUMN contact_number VARCHAR(30) DEFAULT NULL AFTER marital_status"
        )

    if "email" not in existing_columns:
        after_column = "contact_number" if "contact_number" in existing_columns or statements else "marital_status"
        statements.append(
            f"ALTER TABLE application_member ADD COLUMN email VARCHAR(255) DEFAULT NULL AFTER {after_column}"
        )

    if "is_pregnant" in existing_columns:
        statements.append("ALTER TABLE application_member DROP COLUMN is_pregnant")

    for statement in statements:
        db.session.execute(text(statement))

    if statements:
        db.session.commit()


with app.app_context():
    ensure_application_member_schema()


#  Handles get application record for this service.
def get_application_record(application_id):
    query = (
        db.select(Application)
        .options(selectinload(Application.members))
        .where(Application.application_id == application_id)
    )
    return db.session.scalar(query)


#  Handles build member models for this service.
def build_member_models(members_payload):
    return [
        ApplicationMember(
            member_role=member_payload["member_role"],
            nric_fin=member_payload["nric_fin"],
            full_name=member_payload["full_name"],
            relationship_to_main=member_payload["relationship_to_main"],
            date_of_birth=member_payload["date_of_birth"],
            citizenship_status=member_payload["citizenship_status"],
            marital_status=member_payload["marital_status"],
            contact_number=member_payload["contact_number"],
            email=member_payload["email"],
            income_amount=member_payload["income_amount"],
        )
        for member_payload in members_payload
    ]


#  Handles validate member for this service.
def validate_member(member, index):
    if not isinstance(member, dict):
        return None, [f"members[{index}] must be an object."]

    errors = []
    cleaned = {}

    required_string_fields = (
        "member_role",
        "nric_fin",
        "full_name",
        "relationship_to_main",
        "citizenship_status",
    )

    for field_name in required_string_fields:
        if not is_non_empty_string(member.get(field_name)):
            errors.append(f"members[{index}].{field_name} is required.")
        else:
            cleaned[field_name] = member[field_name].strip()

    if "member_role" in cleaned and cleaned["member_role"] not in ALLOWED_MEMBER_ROLES:
        errors.append(
            "members[{index}].member_role must be one of: {roles}.".format(
                index=index,
                roles=", ".join(ALLOWED_MEMBER_ROLES),
            )
        )

    date_of_birth = parse_date(member.get("date_of_birth"))
    if date_of_birth is None:
        errors.append(f"members[{index}].date_of_birth must be a valid date in YYYY-MM-DD format.")
    else:
        cleaned["date_of_birth"] = date_of_birth

    marital_status = member.get("marital_status")
    if marital_status is not None and not is_non_empty_string(marital_status):
        errors.append(f"members[{index}].marital_status must be a non-empty string or null.")
    else:
        cleaned["marital_status"] = marital_status.strip() if isinstance(marital_status, str) else None

    if not is_non_empty_string(member.get("contact_number")):
        errors.append(f"members[{index}].contact_number is required.")
    else:
        cleaned["contact_number"] = member["contact_number"].strip()

    if not is_non_empty_string(member.get("email")):
        errors.append(f"members[{index}].email is required.")
    elif not is_valid_email(member.get("email")):
        errors.append(f"members[{index}].email must be a valid email address.")
    else:
        cleaned["email"] = member["email"].strip()

    income_amount = parse_decimal(member.get("income_amount"))
    if member.get("income_amount") is not None and income_amount is None:
        errors.append(f"members[{index}].income_amount must be a valid number.")
    else:
        cleaned["income_amount"] = income_amount

    return cleaned, errors


#  Handles validate application payload for this service.
def validate_application_payload(data):
    if not isinstance(data, dict):
        return None, ["Request body must be a JSON object."]

    errors = []
    cleaned = {}

    for field_name in ("exercise_id", "project_id"):
        value = parse_int(data.get(field_name))
        if value is None:
            errors.append(f"{field_name} is required and must be an integer.")
        else:
            cleaned[field_name] = value

    for field_name in ("income_document_id", "hfe_document_id"):
        value, field_error = parse_optional_int(data.get(field_name))
        if field_error:
            errors.append(f"{field_name} {field_error}")
        else:
            cleaned[field_name] = value

    for field_name in ("flat_type", "main_applicant_nric"):
        if not is_non_empty_string(data.get(field_name)):
            errors.append(f"{field_name} is required.")
        else:
            cleaned[field_name] = data[field_name].strip()

    members = data.get("members")
    if not isinstance(members, list) or not members:
        errors.append("members is required and must be a non-empty array.")
        return cleaned, errors

    cleaned_members = []
    seen_nric_fin = set()
    main_applicant_count = 0
    main_applicant_member_nric = None

    for index, member in enumerate(members):
        cleaned_member, member_errors = validate_member(member, index)
        errors.extend(member_errors)

        if cleaned_member is None:
            continue

        nric_fin = cleaned_member["nric_fin"]
        if nric_fin in seen_nric_fin:
            errors.append(f"Duplicate nric_fin found in members: {nric_fin}.")
        else:
            seen_nric_fin.add(nric_fin)

        if cleaned_member["member_role"] == "MAIN_APPLICANT":
            main_applicant_count += 1
            main_applicant_member_nric = nric_fin

        cleaned_members.append(cleaned_member)

    if main_applicant_count != 1:
        errors.append("There must be exactly one member with member_role MAIN_APPLICANT.")

    main_applicant_nric = cleaned.get("main_applicant_nric")
    if main_applicant_nric and main_applicant_member_nric and main_applicant_nric != main_applicant_member_nric:
        errors.append("MAIN_APPLICANT member nric_fin must match main_applicant_nric.")

    cleaned["members"] = cleaned_members
    return cleaned, errors


#  Handles create application for this service.
@app.route("/applications", methods=["POST"])
def create_application():
    """
    Create a new application with nested members
    ---
    tags:
      - Applications
    summary: Create application
    description: Creates one application record and all nested application members in a single transaction.
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            required:
              - exercise_id
              - project_id
              - flat_type
              - main_applicant_nric
              - members
            properties:
              exercise_id:
                type: integer
                example: 6
              project_id:
                type: integer
                example: 1
              flat_type:
                type: string
                example: 4-Room
              main_applicant_nric:
                type: string
                example: S9501234R
              income_document_id:
                type: integer
                nullable: true
                example: 41
              hfe_document_id:
                type: integer
                nullable: true
                example: 42
              members:
                type: array
                items:
                  type: object
                  required:
                    - member_role
                    - nric_fin
                    - full_name
                    - relationship_to_main
                    - date_of_birth
                    - citizenship_status
                    - contact_number
                    - email
    responses:
      201:
        description: Application created successfully
      400:
        description: Validation error
      500:
        description: Internal server error
    """
    payload = request.get_json(silent=True)
    cleaned, errors = validate_application_payload(payload)
    if errors:
        return jsonify({"error": "Validation error.", "details": errors}), 400

    application = Application(
        exercise_id=cleaned["exercise_id"],
        project_id=cleaned["project_id"],
        flat_type=cleaned["flat_type"],
        main_applicant_nric=cleaned["main_applicant_nric"],
        income_document_id=cleaned["income_document_id"],
        hfe_document_id=cleaned["hfe_document_id"],
        application_status="SUBMITTED",
        submitted_at=datetime.now(),
    )
    application.members = build_member_models(cleaned["members"])

    try:
        db.session.add(application)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return jsonify({"error": f"Error creating application: {exc}"}), 500

    row = get_application_record(application.application_id)
    return jsonify(row.to_dict(include_members=True)), 201


#  Handles update eligibility for this service.
@app.route("/applications/<int:application_id>/eligibility", methods=["PUT"])
def update_eligibility(application_id):
    """
    Update application eligibility result
    ---
    tags:
      - Applications
    summary: Update eligibility
    description: Sets the application status to SUCCESSFUL or UNSUCCESSFUL based on the eligibility result and can persist extracted document IDs.
    parameters:
      - in: path
        name: application_id
        required: true
        schema:
          type: integer
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            required:
              - eligible
            properties:
              eligible:
                type: boolean
                example: true
              income_document_id:
                type: integer
                nullable: true
                example: 12
              hfe_document_id:
                type: integer
                nullable: true
                example: 13
            example:
              eligible: true
    responses:
      200:
        description: Eligibility updated successfully
      400:
        description: Validation error
      404:
        description: Application not found
      500:
        description: Internal server error
    """
    row = get_application_record(application_id)
    if row is None:
        return jsonify({"error": "Application not found."}), 404

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be a JSON object."}), 400

    eligible = data.get("eligible")
    if not isinstance(eligible, bool):
        return jsonify({"error": "eligible is required and must be a boolean."}), 400

    income_document_id, income_document_error = parse_optional_int(data.get("income_document_id"))
    if income_document_error:
        return jsonify({"error": f"income_document_id {income_document_error}"}), 400

    hfe_document_id, hfe_document_error = parse_optional_int(data.get("hfe_document_id"))
    if hfe_document_error:
        return jsonify({"error": f"hfe_document_id {hfe_document_error}"}), 400

    row.application_status = "SUCCESSFUL" if eligible else "UNSUCCESSFUL"
    if "income_document_id" in data:
        row.income_document_id = income_document_id
    if "hfe_document_id" in data:
        row.hfe_document_id = hfe_document_id

    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return jsonify({"error": f"Error updating eligibility: {exc}"}), 500

    updated_row = get_application_record(application_id)
    return jsonify(updated_row.to_dict(include_members=True))


#  Handles get application for this service.
@app.route("/applications/<int:application_id>", methods=["GET"])
def get_application(application_id):
    """
    Get one application with nested members
    ---
    tags:
      - Applications
    summary: Get application by id
    description: Returns a single application and all of its members.
    responses:
      200:
        description: Application retrieved successfully
      404:
        description: Application not found
    """
    row = get_application_record(application_id)
    if row is None:
        return jsonify({"error": "Application not found."}), 404

    return jsonify(row.to_dict(include_members=True))


#  Handles list applications for this service.
@app.route("/applications", methods=["GET"])
def list_applications():
    """
    List or search applications
    ---
    tags:
      - Applications
    summary: List applications
    description: Returns applications filtered by any provided query parameters.
    parameters:
      - in: query
        name: nric
        required: false
        schema:
          type: string
        description: Returns all applications linked to this NRIC, whether as the main applicant or a member.
      - in: query
        name: main_applicant_nric
        required: false
        schema:
          type: string
        description: Filters by main applicant NRIC only.
      - in: query
        name: exercise_id
        required: false
        schema:
          type: integer
      - in: query
        name: project_id
        required: false
        schema:
          type: integer
      - in: query
        name: application_status
        required: false
        schema:
          type: string
        description: Filters by application status.
    responses:
      200:
        description: Applications retrieved successfully
      400:
        description: Invalid query parameters
    """
    query = db.select(Application).options(selectinload(Application.members))
    errors = []

    nric = request.args.get("nric")
    if nric is not None:
        nric = nric.strip().upper()
        if not nric:
            errors.append("nric must be a non-empty string.")
        else:
            query = query.outerjoin(ApplicationMember).where(
                or_(
                    Application.main_applicant_nric == nric,
                    ApplicationMember.nric_fin == nric,
                )
            )

    main_applicant_nric = request.args.get("main_applicant_nric")
    if main_applicant_nric:
        query = query.where(Application.main_applicant_nric == main_applicant_nric.strip().upper())

    exercise_id = request.args.get("exercise_id")
    if exercise_id is not None:
        if not exercise_id.isdigit():
            errors.append("exercise_id must be an integer.")
        else:
            query = query.where(Application.exercise_id == int(exercise_id))

    project_id = request.args.get("project_id")
    if project_id is not None:
        if not project_id.isdigit():
            errors.append("project_id must be an integer.")
        else:
            query = query.where(Application.project_id == int(project_id))

    application_status = request.args.get("application_status")
    if application_status:
        if application_status not in ALLOWED_APPLICATION_STATUSES:
            errors.append(
                "application_status must be one of: {statuses}.".format(
                    statuses=", ".join(ALLOWED_APPLICATION_STATUSES)
                )
            )
        else:
            query = query.where(Application.application_status == application_status)

    if errors:
        return jsonify({"error": "Validation error.", "details": errors}), 400

    query = query.order_by(Application.created_at.desc(), Application.application_id.desc())
    rows = db.session.scalars(query).unique().all()
    response_payload = {"applications": [row.to_dict(include_members=True) for row in rows]}
    if nric:
        response_payload["nric"] = nric
    return jsonify(response_payload)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5004, debug=False)
