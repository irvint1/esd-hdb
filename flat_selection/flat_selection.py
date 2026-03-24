from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from flasgger import Swagger
import os

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
    'DATABASE_URL', 'mysql+mysqlconnector://root@localhost:3306/flat_selection'
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {'pool_recycle': 299}

db = SQLAlchemy(app)

app.config['SWAGGER'] = {
    'title': 'Flat Selection Microservice API',
    'version': 1.0,
    'openapi': '3.0.2',
    'description': 'Manages BTO flat selection applications'
}
swagger = Swagger(app)


class FlatSelection(db.Model):
    __tablename__ = 'flat_selection'

    selection_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    applicant_id = db.Column(db.Integer, nullable=False)
    co_applicant_id = db.Column(db.Integer, nullable=True)
    project_id = db.Column(db.Integer, nullable=False)
    queue_number = db.Column(db.Integer, nullable=False)
    flat_id = db.Column(db.Integer, nullable=True)
    status = db.Column(
        db.Enum('balloted', 'selecting', 'reserved', 'paid', 'forfeited'),
        nullable=False,
        default='balloted'
    )
    reserved_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    def json(self):
        return {
            "selection_id": self.selection_id,
            "applicant_id": self.applicant_id,
            "co_applicant_id": self.co_applicant_id,
            "project_id": self.project_id,
            "queue_number": self.queue_number,
            "flat_id": self.flat_id,
            "status": self.status,
            "reserved_at": self.reserved_at.isoformat() if self.reserved_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# ============================================================
# GET /flat-selection - Get all selections
# Optional query params: status, project_id
# ============================================================
@app.route('/flat-selection', methods=['GET'])
def get_all():
    """
    Get all flat selections
    ---
    responses:
        200:
            description: Return all flat selections
        404:
            description: No flat selections found
    """
    status = request.args.get('status')
    project_id = request.args.get('project_id')

    query = db.select(FlatSelection)

    if status:
        query = query.filter_by(status=status)
    if project_id:
        query = query.filter_by(project_id=int(project_id))

    selections = db.session.scalars(query).all()

    if selections:
        return jsonify({
            "code": 200,
            "data": [s.json() for s in selections]
        }), 200

    return jsonify({
        "code": 404,
        "message": "No flat selections found."
    }), 404


# ============================================================
# GET /flat-selection/<selection_id> - Get a specific selection
# ============================================================
@app.route('/flat-selection/<int:selection_id>', methods=['GET'])
def get_selection(selection_id):
    selection = db.session.get(FlatSelection, selection_id)

    if selection:
        return jsonify({
            "code": 200,
            "data": selection.json()
        }), 200

    return jsonify({
        "code": 404,
        "message": "Flat selection not found."
    }), 404


# ============================================================
# POST /flat-selection - Create a new flat selection application
# Body: { "applicant_id": 1, "co_applicant_id": 2, "project_id": 1, "queue_number": 5 }
# co_applicant_id is optional
# ============================================================
@app.route('/flat-selection', methods=['POST'])
def create_selection():
    """
    Create a new flat selection application
    ---
    responses:
        201:
            description: Flat selection created
        400:
            description: Validation error
    """
    data = request.get_json()

    required = ['applicant_id', 'project_id', 'queue_number']
    for field in required:
        if not data or field not in data:
            return jsonify({
                "code": 400,
                "message": f"{field} is required."
            }), 400

    # Check for duplicate queue number within the same project
    existing = db.session.scalar(
        db.select(FlatSelection).filter_by(
            project_id=data['project_id'],
            queue_number=data['queue_number']
        )
    )
    if existing:
        return jsonify({
            "code": 409,
            "message": f"Queue number {data['queue_number']} already exists for project {data['project_id']}."
        }), 409

    selection = FlatSelection(
        applicant_id=data['applicant_id'],
        co_applicant_id=data.get('co_applicant_id'),
        project_id=data['project_id'],
        queue_number=data['queue_number'],
        status='submitted'
    )

    try:
        db.session.add(selection)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({
            "code": 500,
            "message": f"Error creating flat selection: {str(e)}"
        }), 500

    return jsonify({
        "code": 201,
        "data": selection.json()
    }), 201


# ============================================================
# PUT /flat-selection/<selection_id>/reserve - Reserve a flat (Step 10)
# Called by Flat Allocation Service after flat availability is confirmed
# Body: { "flat_id": 1 }
# ============================================================
@app.route('/flat-selection/<int:selection_id>/reserve', methods=['PUT'])
def reserve_selection(selection_id):
    selection = db.session.get(FlatSelection, selection_id)

    if not selection:
        return jsonify({
            "code": 404,
            "message": "Flat selection not found."
        }), 404

    data = request.get_json()
    if not data or 'flat_id' not in data:
        return jsonify({
            "code": 400,
            "message": "flat_id is required."
        }), 400

    if selection.status not in ('balloted', 'selecting'):
        return jsonify({
            "code": 409,
            "message": f"Cannot reserve. Current status: {selection.status}"
        }), 409

    selection.flat_id = data['flat_id']
    selection.status = 'reserved'
    selection.reserved_at = datetime.now()

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({
            "code": 500,
            "message": f"Error reserving flat selection: {str(e)}"
        }), 500

    return jsonify({
        "code": 200,
        "message": f"Selection {selection_id} reserved with flat {data['flat_id']}.",
        "data": selection.json()
    }), 200


# ============================================================
# PUT /flat-selection/<selection_id>/undo-reserve - Undo reservation (Step 18b compensation)
# ============================================================
@app.route('/flat-selection/<int:selection_id>/undo-reserve', methods=['PUT'])
def undo_reserve(selection_id):
    selection = db.session.get(FlatSelection, selection_id)

    if not selection:
        return jsonify({
            "code": 404,
            "message": "Flat selection not found."
        }), 404

    if selection.status != 'reserved':
        return jsonify({
            "code": 409,
            "message": f"Cannot undo reserve. Current status: {selection.status}"
        }), 409

    selection.flat_id = None
    selection.status = 'balloted'
    selection.reserved_at = None

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({
            "code": 500,
            "message": f"Error undoing reservation: {str(e)}"
        }), 500

    return jsonify({
        "code": 200,
        "message": f"Selection {selection_id} reservation undone.",
        "data": selection.json()
    }), 200


# ============================================================
# PUT /flat-selection/<selection_id>/status - Update status
# Body: { "status": "paid" }
# ============================================================
@app.route('/flat-selection/<int:selection_id>/status', methods=['PUT'])
def update_status(selection_id):
    selection = db.session.get(FlatSelection, selection_id)

    if not selection:
        return jsonify({
            "code": 404,
            "message": "Flat selection not found."
        }), 404

    data = request.get_json()
    valid_statuses = ('submitted', 'balloted', 'selecting', 'reserved', 'paid', 'forfeited')

    if not data or 'status' not in data or data['status'] not in valid_statuses:
        return jsonify({
            "code": 400,
            "message": f"Valid statuses are: {', '.join(valid_statuses)}"
        }), 400

    selection.status = data['status']

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({
            "code": 500,
            "message": f"Error updating status: {str(e)}"
        }), 500

    return jsonify({
        "code": 200,
        "data": selection.json()
    }), 200


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5002, debug=True)