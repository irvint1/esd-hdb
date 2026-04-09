"""HFE application service."""

import os

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
    app.run(host="0.0.0.0", port=5009, debug=False)
