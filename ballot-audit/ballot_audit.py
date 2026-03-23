from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from flasgger import Swagger
import os

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
    'DATABASE_URL', 'mysql+mysqlconnector://root@localhost:3306/ballot_audit'
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {'pool_recycle': 299}

db = SQLAlchemy(app)

app.config['SWAGGER'] = {
    'title': 'Ballot Audit Microservice API',
    'version': 1.0,
    'openapi': '3.0.2',
    'description': 'Manages BTO ballot run records for audit purposes'
}
swagger = Swagger(app)

class BallotAudit(db.Model):
    __tablename__ = 'ballot_audit'

    audit_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    exercise_id = db.Column(db.Integer, nullable=False)
    run_at = db.Column(db.DateTime, nullable=False)
    status = db.Column(
        db.Enum('in progress', 'completed', 'failed', 'cancelled'),
        nullable=False,
        default='in progress'
    )

    def json(self):
        return {
            "audit_id": self.audit_id,
            "exercise_id": self.exercise_id,
            "run_at": self.run_at.isoformat() if self.run_at else None,
            "status": self.status,
        }


@app.route('/ballot-audit', methods=['GET'])
def get_all():
    """
    Get all ballot audit records
    ---
    tags:
      - Ballot Audit
    responses:
      200:
        description: Ballot audit records retrieved successfully
      404:
        description: No ballot audit records found
    """

    query = db.select(BallotAudit)

    selections = db.session.scalars(query).all()

    if selections:
        return jsonify({
            "code": 200,
            "data": [s.json() for s in selections]
        }), 200

    return jsonify({
        "code": 404,
        "message": "No ballot audit records found."
    }), 404


@app.route('/ballot-audit', methods=['POST'])
def create_audit():
    """
    Create a new ballot audit record
    ---
    tags:
      - Ballot Audit
    responses:
      201:
        description: Ballot audit created successfully
      400:
        description: Validation error or invalid JSON body
      500:
        description: Internal server error
    """
    data = request.get_json()

    if not isinstance(data, dict):
        return jsonify({
            "code": 400,
            "message": "Request body must be valid JSON."
        }), 400

    errors = []
    valid_statuses = ['in progress', 'completed', 'failed', 'cancelled']

    if data.get('exercise_id') is None:
        errors.append('exercise_id is required.')
    elif not isinstance(data['exercise_id'], int):
        errors.append('exercise_id must be an integer.')

    if data.get('run_at') is None:
        errors.append('run_at is required.')
    elif not isinstance(data['run_at'], str):
        errors.append('run_at must be a string in YYYY-MM-DDTHH:MM:SS format.')
    else:
        try:
            datetime.fromisoformat(data['run_at'])
        except ValueError:
            errors.append('run_at must be a valid datetime in YYYY-MM-DDTHH:MM:SS format.')

    if data.get('status') is None:
        errors.append('status is required.')
    elif not isinstance(data['status'], str):
        errors.append('status must be a string.')
    elif data['status'] not in valid_statuses:
        errors.append(f"status must be one of: {', '.join(valid_statuses)}.")

    if errors:
        return jsonify({
            "code": 400,
            "message": "Validation error.",
            "errors": errors
        }), 400

    audit = BallotAudit(
        exercise_id=data['exercise_id'],
        run_at=datetime.fromisoformat(data['run_at']),
        status=data['status']
    )

    try:
        db.session.add(audit)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({
            "code": 500,
            "message": f"Error creating ballot audit: {str(e)}"
        }), 500

    return jsonify({
        "code": 201,
        "data": audit.json()
    }), 201


@app.route('/ballot-audit/<int:audit_id>', methods=['PUT'])
def update_audit_status(audit_id):
    """
    Update ballot audit status
    ---
    tags:
      - Ballot Audit
    responses:
      200:
        description: Ballot audit status updated successfully
      400:
        description: Validation error or invalid JSON body
      404:
        description: Audit not found
      500:
        description: Internal server error
    """
    
    data = request.get_json()

    if not isinstance(data, dict):
        return jsonify({
            "code": 400,
            "message": "Request body must be valid JSON."
        }), 400

    audit = db.session.get(BallotAudit, audit_id)
    if not audit:
        return jsonify({
            "code": 404,
            "message": f"Ballot audit {audit_id} not found."
        }), 404

    errors = []
    valid_statuses = ['in progress', 'completed', 'failed', 'cancelled']

    if 'status' not in data:
        errors.append('status is required.')
    elif not isinstance(data['status'], str):
        errors.append('status must be a string.')
    elif data['status'] not in valid_statuses:
        errors.append(f"status must be one of: {', '.join(valid_statuses)}.")

    extra_fields = [key for key in data.keys() if key != 'status']
    if extra_fields:
        errors.append(f"Only status can be updated. Unexpected fields: {', '.join(extra_fields)}.")

    if errors:
        return jsonify({
            "code": 400,
            "message": "Validation error.",
            "errors": errors
        }), 400

    audit.status = data['status']

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({
            "code": 500,
            "message": f"Error updating ballot audit status: {str(e)}"
        }), 500

    return jsonify({
        "code": 200,
        "data": audit.json()
    }), 200


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)