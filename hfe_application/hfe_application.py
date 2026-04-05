"""HFE application service."""

import os
from datetime import date

from flask import Flask, jsonify, request
from flask_cors import CORS
from flasgger import Swagger
from flask_sqlalchemy import SQLAlchemy

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "mysql+mysqlconnector://root:root@hfe-application-db:3306/hfe_applications",
)

app = Flask(__name__)
CORS(app)

app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_recycle": 299}

app.config["SWAGGER"] = {
    "title": "HFE Application API",
    "version": 1.0,
    "openapi": "3.0.2",
    "description": "Stores authoritative HFE application results for eligibility checks.",
}
swagger = Swagger(app)

db = SQLAlchemy(app)

SCENARIO_HFE_RECORDS = (
    {
        "main_applicant_nric": "S9401234L",
        "main_applicant_name": "LENA ONG JIA HUI",
        "co_applicant_nric": "S9601234S",
        "co_applicant_name": "SARAH LIM MEI YEN",
        "total_household_income": 5500.00,
        "assessment_outcome": "ELIGIBLE",
        "eligible_flat_types": "3-Room",
        "application_scheme": "Public Scheme (Married Couple / Singapore Citizen)",
        "hdb_loan_ceiling": 120000.00,
        "total_grants_eligible": 55000.00,
        "date_of_issue": "2026-01-15",
        "valid_until": "2026-12-31",
    },
    {
        "main_applicant_nric": "S9501234R",
        "main_applicant_name": "RYAN TAN JIAN HUI",
        "co_applicant_nric": "S9601234S",
        "co_applicant_name": "SARAH LIM MEI YEN",
        "total_household_income": 9800.00,
        "assessment_outcome": "ELIGIBLE",
        "eligible_flat_types": "4-Room, 5-Room",
        "application_scheme": "Public Scheme (Married Couple / Singapore Citizen)",
        "hdb_loan_ceiling": 270000.00,
        "total_grants_eligible": 80000.00,
        "date_of_issue": "2026-01-15",
        "valid_until": "2026-12-31",
    },
    {
        "main_applicant_nric": "S8901234D",
        "main_applicant_name": "DANIEL GOH WEI MING",
        "co_applicant_nric": "S9101234M",
        "co_applicant_name": "MARCUS LIM CHENG WEI",
        "total_household_income": 8500.00,
        "assessment_outcome": "ELIGIBLE (3-Room only)",
        "eligible_flat_types": "3-Room",
        "application_scheme": "Public Scheme (Married Couple / Singapore Citizen)",
        "hdb_loan_ceiling": 180000.00,
        "total_grants_eligible": 35000.00,
        "date_of_issue": "2026-01-15",
        "valid_until": "2026-12-31",
    },
    {
        "main_applicant_nric": "S9001234J",
        "main_applicant_name": "JASMINE TAN SHU MIN",
        "co_applicant_nric": "S9101234M",
        "co_applicant_name": "MARCUS LIM CHENG WEI",
        "total_household_income": 11000.00,
        "assessment_outcome": "ELIGIBLE",
        "eligible_flat_types": "4-Room, 5-Room",
        "application_scheme": "Public Scheme (Married Couple / Singapore Citizen)",
        "hdb_loan_ceiling": 270000.00,
        "total_grants_eligible": 80000.00,
        "date_of_issue": "2023-11-15",
        "valid_until": "2024-06-30",
    },
    {
        "main_applicant_nric": "S9201234W",
        "main_applicant_name": "WENDY CHEN XIN HUI",
        "co_applicant_nric": "S9501234R",
        "co_applicant_name": "RYAN TAN JIAN HUI",
        "total_household_income": 4200.00,
        "assessment_outcome": "ELIGIBLE",
        "eligible_flat_types": "2-Room Flexi, 3-Room",
        "application_scheme": "Public Scheme (Married Couple / Singapore Citizen)",
        "hdb_loan_ceiling": 135000.00,
        "total_grants_eligible": 55000.00,
        "date_of_issue": "2026-01-15",
        "valid_until": "2026-12-31",
    },
)


class HfeApplication(db.Model):
    __tablename__ = "hfe_application"

    hfe_application_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    main_applicant_nric = db.Column(db.String(20), nullable=False)
    main_applicant_name = db.Column(db.String(255), nullable=False)
    co_applicant_nric = db.Column(db.String(20), nullable=True)
    co_applicant_name = db.Column(db.String(255), nullable=True)
    total_household_income = db.Column(db.Numeric(12, 2), nullable=True)
    assessment_outcome = db.Column(db.String(255), nullable=False)
    eligible_flat_types = db.Column(db.String(255), nullable=False)
    application_scheme = db.Column(db.String(100), nullable=True)
    hdb_loan_ceiling = db.Column(db.Numeric(12, 2), nullable=True)
    total_grants_eligible = db.Column(db.Numeric(12, 2), nullable=True)
    date_of_issue = db.Column(db.Date, nullable=True)
    valid_until = db.Column(db.Date, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.current_timestamp())
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        server_default=db.func.current_timestamp(),
        onupdate=db.func.current_timestamp(),
    )

    #  Handles to dict for this service.
    def to_dict(self):
        return {
            "hfe_application_id": self.hfe_application_id,
            "main_applicant_nric": self.main_applicant_nric,
            "main_applicant_name": self.main_applicant_name,
            "co_applicant_nric": self.co_applicant_nric,
            "co_applicant_name": self.co_applicant_name,
            "total_household_income": float(self.total_household_income) if self.total_household_income is not None else None,
            "assessment_outcome": self.assessment_outcome,
            "eligible_flat_types": self.eligible_flat_types,
            "application_scheme": self.application_scheme,
            "hdb_loan_ceiling": float(self.hdb_loan_ceiling) if self.hdb_loan_ceiling is not None else None,
            "total_grants_eligible": float(self.total_grants_eligible) if self.total_grants_eligible is not None else None,
            "date_of_issue": self.date_of_issue.isoformat() if self.date_of_issue else None,
            "valid_until": self.valid_until.isoformat() if self.valid_until else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


#  Handles upsert scenario hfe records for this service.
def upsert_scenario_hfe_records():
    for seed in SCENARIO_HFE_RECORDS:
        query = db.select(HfeApplication).where(
            HfeApplication.main_applicant_nric == seed["main_applicant_nric"]
        )
        record = db.session.scalar(query)

        if record is None:
            record = HfeApplication(main_applicant_nric=seed["main_applicant_nric"])
            db.session.add(record)

        record.main_applicant_name = seed["main_applicant_name"]
        record.co_applicant_nric = seed["co_applicant_nric"]
        record.co_applicant_name = seed["co_applicant_name"]
        record.total_household_income = seed["total_household_income"]
        record.assessment_outcome = seed["assessment_outcome"]
        record.eligible_flat_types = seed["eligible_flat_types"]
        record.application_scheme = seed["application_scheme"]
        record.hdb_loan_ceiling = seed["hdb_loan_ceiling"]
        record.total_grants_eligible = seed["total_grants_eligible"]
        record.date_of_issue = date.fromisoformat(seed["date_of_issue"])
        record.valid_until = date.fromisoformat(seed["valid_until"])

    db.session.commit()


#  Handles get hfe applications for this service.
@app.route("/hfe-applications", methods=["GET"])
def get_hfe_applications():
    """
    Retrieve HFE application 
    ---
    tags:
      - HFE Applications
    summary: Get a HFE application by main applicant NRIC
    parameters:
      - in: query
        name: main_applicant_nric
        required: true
        schema:
          type: string
        example: S9812381D
    responses:
      200:
        description: HFE application returned successfully
      400:
        description: Missing NRIC
      404:
        description: No HFE application record exists
    """
    raw_nric = request.args.get("main_applicant_nric")
    if not isinstance(raw_nric, str) or not raw_nric.strip():
        return jsonify({"error": "main_applicant_nric is required."}), 400

    nric = raw_nric.strip().upper()
    query = db.select(HfeApplication).where(HfeApplication.main_applicant_nric == nric)
    row = db.session.scalar(query)
    if row is None:
        return jsonify({"error": "HFE application not found."}), 404

    return jsonify(row.to_dict())


if __name__ == "__main__":
    with app.app_context():
        upsert_scenario_hfe_records()

    app.run(host="0.0.0.0", port=5009, debug=False)
