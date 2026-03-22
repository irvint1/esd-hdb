from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flasgger import Swagger
from datetime import datetime
import requests
import os

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+mysqlconnector://root@localhost:3306/eligibility_service'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {'pool_recycle': 299}

db = SQLAlchemy(app)

app.config['SWAGGER'] = {
    'title': 'Eligibility Service API',
    'version': 1.0,
    "openapi": "3.0.2",
    'description': 'Checks BTO applicant eligibility by calling ICA, IRAS, CPF Board, and SLA APIs (Steps 7-9)'
}
swagger = Swagger(app)

# ---------------------------------------------------------------------------
# External Government API URLs (Steps 7, 8a, 8b, 8c, 8d, 9)
# ---------------------------------------------------------------------------
ICA_API_URL  = os.environ.get("ICA_API_URL",  "https://api.ica.gov.sg")
IRAS_API_URL = os.environ.get("IRAS_API_URL", "https://api.iras.gov.sg")
CPF_API_URL  = os.environ.get("CPF_API_URL",  "https://api.cpf.gov.sg")
SLA_API_URL  = os.environ.get("SLA_API_URL",  "https://api.sla.gov.sg")
HFE_SERVICE_URL = os.environ.get("HFE_SERVICE_URL", "http://localhost:5005")


class EligibilityCheck(db.Model):
    __tablename__ = 'eligibility_check'

    check_id         = db.Column(db.Integer,   primary_key=True, autoincrement=True)
    application_id   = db.Column(db.Integer,   nullable=False)
    applicant_nric   = db.Column(db.String(9), nullable=False)
    co_applicant_nric= db.Column(db.String(9), nullable=True)
    flat_type        = db.Column(db.String(20),nullable=False)
    ica_pass         = db.Column(db.Boolean,   nullable=True)
    iras_pass        = db.Column(db.Boolean,   nullable=True)
    cpf_pass         = db.Column(db.Boolean,   nullable=True)
    sla_pass         = db.Column(db.Boolean,   nullable=True)
    hfe_pass         = db.Column(db.Boolean,   nullable=True)
    is_eligible      = db.Column(db.Boolean,   nullable=True)
    note             = db.Column(db.Text,      nullable=True)
    created_at       = db.Column(db.DateTime,  nullable=False, default=datetime.utcnow)

    def __init__(self, application_id, applicant_nric, flat_type, co_applicant_nric=None):
        self.application_id    = application_id
        self.applicant_nric    = applicant_nric
        self.co_applicant_nric = co_applicant_nric
        self.flat_type         = flat_type

    def json(self):
        return {
            "check_id":          self.check_id,
            "application_id":    self.application_id,
            "applicant_nric":    self.applicant_nric,
            "co_applicant_nric": self.co_applicant_nric,
            "flat_type":         self.flat_type,
            "ica_pass":          self.ica_pass,
            "iras_pass":         self.iras_pass,
            "cpf_pass":          self.cpf_pass,
            "sla_pass":          self.sla_pass,
            "hfe_pass":          self.hfe_pass,
            "is_eligible":       self.is_eligible,
            "note":              self.note,
            "created_at":        str(self.created_at),
        }


# ---------------------------------------------------------------------------
# External API helpers (Steps 7–9)
# ---------------------------------------------------------------------------
def check_ica(nric):
    """Step 7 / 8a – Verify Citizenship / PR Status via ICA API (HTTP GET)."""
    try:
        resp = requests.get(f"{ICA_API_URL}/citizenship/verify/{nric}", timeout=10)
        if resp.status_code == 200:
            return resp.json().get("is_citizen_or_pr", True)
        return True   # default pass for dev
    except:
        return True


def check_iras(nric):
    """Step 8b – Verify Income via IRAS API (HTTP GET)."""
    try:
        resp = requests.get(f"{IRAS_API_URL}/income/verify/{nric}", timeout=10)
        if resp.status_code == 200:
            return resp.json().get("income_eligible", True)
        return True
    except:
        return True


def check_cpf(nric):
    """Step 8c – Verify CPF Withdrawals / Previous Housing Grants via CPF Board API (HTTP GET)."""
    try:
        resp = requests.get(f"{CPF_API_URL}/housing_grants/verify/{nric}", timeout=10)
        if resp.status_code == 200:
            return resp.json().get("cpf_eligible", True)
        return True
    except:
        return True


def check_sla(nric):
    """Step 8d – Check for Existing Properties via SLA API (HTTP GET)."""
    try:
        resp = requests.get(f"{SLA_API_URL}/property/verify/{nric}", timeout=10)
        if resp.status_code == 200:
            return resp.json().get("no_existing_property", True)
        return True
    except:
        return True


def check_hfe(application_id, nric, flat_type):
    """Step 9 – Check HFE matches information stored in official classes (HTTP GET)."""
    try:
        resp = requests.get(
            f"{HFE_SERVICE_URL}/hfe/verify",
            params={"application_id": application_id, "nric": nric, "flat_type": flat_type},
            timeout=10
        )
        if resp.status_code == 200:
            return resp.json().get("data", {}).get("hfe_eligible", True)
        return True
    except:
        return True


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.route("/eligibility")
def get_all():
    """
    Get all eligibility checks
    ---
    responses:
        200:
            description: Return all eligibility checks
        404:
            description: No records found
    """
    records = db.session.scalars(db.select(EligibilityCheck)).all()
    if records:
        return jsonify({"code": 200, "data": {"checks": [r.json() for r in records]}})
    return jsonify({"code": 404, "message": "No eligibility checks found."}), 404


@app.route("/eligibility/<int:check_id>")
def find_by_id(check_id):
    """
    Get eligibility check by ID
    ---
    parameters:
      - name: check_id
        in: path
        required: true
        schema:
            type: integer
    responses:
        200:
            description: Record found
        404:
            description: Record not found
    """
    record = db.session.get(EligibilityCheck, check_id)
    if record:
        return jsonify({"code": 200, "data": record.json()})
    return jsonify({"code": 404, "message": "Eligibility check not found."}), 404


@app.route("/eligibility/check", methods=['POST'])
def check_eligibility():
    """
    Run full eligibility check for a BTO ballot application (Steps 6-11)
    Calls ICA (8a), IRAS (8b), CPF Board (8c), SLA (8d), HFEApplication (9) internally.
    ---
    requestBody:
        required: true
        content:
            application/json:
                schema:
                    type: object
                    required: [application_id, applicant_nric, flat_type]
                    properties:
                        application_id:
                            type: integer
                        applicant_nric:
                            type: string
                        co_applicant_nric:
                            type: string
                        flat_type:
                            type: string
    responses:
        200:
            description: Eligibility check completed
        400:
            description: Missing required fields
        500:
            description: Server error
    """
    data = request.get_json()
    errors = []

    for field in ['application_id', 'applicant_nric', 'flat_type']:
        if not data.get(field):
            errors.append(f"'{field}' is required.")

    if errors:
        return jsonify({"code": 400, "message": errors}), 400

    application_id    = data['application_id']
    applicant_nric    = data['applicant_nric']
    co_applicant_nric = data.get('co_applicant_nric')
    flat_type         = data['flat_type']

    record = EligibilityCheck(
        application_id    = application_id,
        applicant_nric    = applicant_nric,
        co_applicant_nric = co_applicant_nric,
        flat_type         = flat_type
    )

    try:
        db.session.add(record)
        db.session.commit()
    except:
        return jsonify({"code": 500, "message": "Error creating eligibility check."}), 500

    # Run all external checks
    failed_checks = []

    record.ica_pass = check_ica(applicant_nric)
    if not record.ica_pass:
        failed_checks.append("Failed ICA check: applicant is not a citizen or PR.")

    record.iras_pass = check_iras(applicant_nric)
    if not record.iras_pass:
        failed_checks.append("Failed IRAS check: income ceiling exceeded.")

    record.cpf_pass = check_cpf(applicant_nric)
    if not record.cpf_pass:
        failed_checks.append("Failed CPF check: previous housing grant usage detected.")

    record.sla_pass = check_sla(applicant_nric)
    if not record.sla_pass:
        failed_checks.append("Failed SLA check: existing property ownership detected.")

    record.hfe_pass = check_hfe(application_id, applicant_nric, flat_type)
    if not record.hfe_pass:
        failed_checks.append("Failed HFE check: HFE letter requirements not met.")

    record.is_eligible = len(failed_checks) == 0
    record.note        = "All checks passed." if record.is_eligible else " | ".join(failed_checks)

    try:
        db.session.commit()
    except:
        return jsonify({"code": 500, "message": "Error saving eligibility result."}), 500

    return jsonify({
        "code": 200,
        "data": record.json()
    })


if __name__ == '__main__':
    app.run(port=5004, debug=True)
