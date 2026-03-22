"""
ballot_application.py  –  Atomic microservice (port 5010)
Stores and manages BallotApplication records in MySQL.

DB: ballot_application  (MySQL)
Table: ballot_application
"""

from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flasgger import Swagger
from datetime import datetime
import os

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
    'DATABASE_URL',
    'mysql+mysqlconnector://root@localhost:3306/ballot_application'
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {'pool_recycle': 299}

db = SQLAlchemy(app)

app.config['SWAGGER'] = {
    'title': 'Ballot Application Service API',
    'version': '1.0',
    'openapi': '3.0.2',
    'description': 'Atomic service – manages BallotApplication records (Step 5 of Apply-for-BTO scenario).'
}
swagger = Swagger(app)


# ── Model ──────────────────────────────────────────────────────────────────────

class BallotApplication(db.Model):
    __tablename__ = 'ballot_application'

    application_id   = db.Column(db.Integer, primary_key=True, autoincrement=True)
    applicant_id     = db.Column(db.Integer,  nullable=False)
    co_applicant_id  = db.Column(db.Integer,  nullable=True)   # partner's applicant_id
    flat_type        = db.Column(db.String(20), nullable=False)  # e.g. "3-Room", "4-Room"
    bto_project_id   = db.Column(db.Integer,  nullable=False)
    transaction_id   = db.Column(db.String(64), nullable=True)  # filled after payment
    payment_amount   = db.Column(db.Float,    nullable=True)
    # Possible values: PENDING_PAYMENT | SUBMITTED | ELIGIBLE | INELIGIBLE | FORFEITED
    status           = db.Column(db.String(20), nullable=False, default='PENDING_PAYMENT')
    eligibility_result = db.Column(db.String(20), nullable=True)  # ELIGIBLE / INELIGIBLE
    note             = db.Column(db.Text,     nullable=True)
    created_at       = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at       = db.Column(db.DateTime, nullable=False, default=datetime.utcnow,
                                 onupdate=datetime.utcnow)

    def __init__(self, applicant_id, flat_type, bto_project_id,
                 co_applicant_id=None):
        self.applicant_id    = applicant_id
        self.co_applicant_id = co_applicant_id
        self.flat_type       = flat_type
        self.bto_project_id  = bto_project_id

    def json(self):
        return {
            'application_id':     self.application_id,
            'applicant_id':       self.applicant_id,
            'co_applicant_id':    self.co_applicant_id,
            'flat_type':          self.flat_type,
            'bto_project_id':     self.bto_project_id,
            'transaction_id':     self.transaction_id,
            'payment_amount':     self.payment_amount,
            'status':             self.status,
            'eligibility_result': self.eligibility_result,
            'note':               self.note,
            'created_at':         str(self.created_at),
            'updated_at':         str(self.updated_at),
        }


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.route('/ballot-application', methods=['GET'])
def get_all():
    """
    Get all ballot applications
    ---
    responses:
      200:
        description: List of all ballot applications
      404:
        description: No applications found
    """
    records = db.session.scalars(db.select(BallotApplication)).all()
    if records:
        return jsonify({'code': 200, 'data': {'applications': [r.json() for r in records]}})
    return jsonify({'code': 404, 'message': 'No ballot applications found.'}), 404


@app.route('/ballot-application/<int:application_id>', methods=['GET'])
def get_by_id(application_id):
    """
    Get a ballot application by ID
    ---
    parameters:
      - name: application_id
        in: path
        required: true
        schema:
          type: integer
    responses:
      200:
        description: Application found
      404:
        description: Application not found
    """
    record = db.session.get(BallotApplication, application_id)
    if record:
        return jsonify({'code': 200, 'data': record.json()})
    return jsonify({'code': 404, 'message': 'Application not found.'}), 404


@app.route('/ballot-application/applicant/<int:applicant_id>', methods=['GET'])
def get_by_applicant(applicant_id):
    """
    Get all ballot applications for a specific applicant
    ---
    parameters:
      - name: applicant_id
        in: path
        required: true
        schema:
          type: integer
    responses:
      200:
        description: Applications found
      404:
        description: No applications for this applicant
    """
    records = db.session.scalars(
        db.select(BallotApplication).filter_by(applicant_id=applicant_id)
    ).all()
    if records:
        return jsonify({'code': 200, 'data': {'applications': [r.json() for r in records]}})
    return jsonify({'code': 404, 'message': 'No applications found for this applicant.'}), 404


@app.route('/ballot-application/eligible', methods=['GET'])
def get_eligible():
    """
    Get all ELIGIBLE ballot applications (used by Execute Ballot cron job)
    ---
    responses:
      200:
        description: Eligible applications returned
      404:
        description: No eligible applications
    """
    records = db.session.scalars(
        db.select(BallotApplication).filter_by(status='ELIGIBLE')
    ).all()
    if records:
        return jsonify({'code': 200, 'data': {'applications': [r.json() for r in records]}})
    return jsonify({'code': 404, 'message': 'No eligible applications found.'}), 404


@app.route('/ballot-application', methods=['POST'])
def create_application():
    """
    Create a new ballot application (Step 5 – called by Apply for Ballot composite)
    ---
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            required: [applicant_id, flat_type, bto_project_id]
            properties:
              applicant_id:
                type: integer
              co_applicant_id:
                type: integer
              flat_type:
                type: string
              bto_project_id:
                type: integer
    responses:
      201:
        description: Application created
      400:
        description: Missing required fields
      500:
        description: Server error
    """
    data = request.get_json()
    errors = []

    for field in ['applicant_id', 'flat_type', 'bto_project_id']:
        if not data.get(field):
            errors.append(f"'{field}' is required.")

    if errors:
        return jsonify({'code': 400, 'message': errors}), 400

    record = BallotApplication(
        applicant_id=data['applicant_id'],
        flat_type=data['flat_type'],
        bto_project_id=data['bto_project_id'],
        co_applicant_id=data.get('co_applicant_id')
    )

    try:
        db.session.add(record)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({'code': 500, 'message': f'Error creating application: {str(e)}'}), 500

    return jsonify({'code': 201, 'data': record.json()}), 201


@app.route('/ballot-application/<int:application_id>/payment', methods=['PUT'])
def update_payment(application_id):
    """
    Update payment details after NETS payment succeeds (Step 3 callback)
    ---
    parameters:
      - name: application_id
        in: path
        required: true
        schema:
          type: integer
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            required: [transaction_id, payment_amount]
            properties:
              transaction_id:
                type: string
              payment_amount:
                type: number
    responses:
      200:
        description: Payment updated, status set to SUBMITTED
      404:
        description: Application not found
    """
    record = db.session.get(BallotApplication, application_id)
    if not record:
        return jsonify({'code': 404, 'message': 'Application not found.'}), 404

    data = request.get_json()
    record.transaction_id  = data.get('transaction_id')
    record.payment_amount  = data.get('payment_amount')
    record.status          = 'SUBMITTED'

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({'code': 500, 'message': f'Error updating payment: {str(e)}'}), 500

    return jsonify({'code': 200, 'data': record.json()})


@app.route('/ballot-application/<int:application_id>/eligibility', methods=['PUT'])
def update_eligibility(application_id):
    """
    Update eligibility result (Step 12 – called by Check Eligibility composite)
    ---
    parameters:
      - name: application_id
        in: path
        required: true
        schema:
          type: integer
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            required: [eligibility_result]
            properties:
              eligibility_result:
                type: string
                enum: [ELIGIBLE, INELIGIBLE]
              note:
                type: string
    responses:
      200:
        description: Eligibility result saved
      404:
        description: Application not found
    """
    record = db.session.get(BallotApplication, application_id)
    if not record:
        return jsonify({'code': 404, 'message': 'Application not found.'}), 404

    data = request.get_json()
    result = data.get('eligibility_result', '').upper()
    if result not in ('ELIGIBLE', 'INELIGIBLE'):
        return jsonify({'code': 400, 'message': "eligibility_result must be ELIGIBLE or INELIGIBLE."}), 400

    record.eligibility_result = result
    record.status             = result          # ELIGIBLE or INELIGIBLE
    record.note               = data.get('note', record.note)

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({'code': 500, 'message': f'Error updating eligibility: {str(e)}'}), 500

    return jsonify({'code': 200, 'data': record.json()})


@app.route('/ballot-application/<int:application_id>/status', methods=['PUT'])
def update_status(application_id):
    """
    Generic status update (e.g. FORFEITED for no-show applicants)
    ---
    parameters:
      - name: application_id
        in: path
        required: true
        schema:
          type: integer
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            required: [status]
            properties:
              status:
                type: string
              note:
                type: string
    responses:
      200:
        description: Status updated
      404:
        description: Application not found
    """
    record = db.session.get(BallotApplication, application_id)
    if not record:
        return jsonify({'code': 404, 'message': 'Application not found.'}), 404

    data = request.get_json()
    record.status = data.get('status', record.status)
    record.note   = data.get('note', record.note)

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({'code': 500, 'message': f'Error updating status: {str(e)}'}), 500

    return jsonify({'code': 200, 'data': record.json()})


if __name__ == '__main__':
    app.run(port=5010, debug=True)
