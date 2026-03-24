from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from flasgger import Swagger
from datetime import datetime
from sqlalchemy import select, update, func
import os

app = Flask(__name__)
CORS(app)

app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
    'DATABASE_URL', 'mysql+mysqlconnector://root@localhost:3306/flats'
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {'pool_recycle': 299}

db = SQLAlchemy(app)


app.config['SWAGGER'] = {
    'title': 'Flats Microservice API',
    'version': 1.0,
    'openapi': '3.0.2',
    'description': 'Manages flats and reservations'
}

swagger = Swagger(app)


class Flat(db.Model):
    __tablename__ = 'flat'

    flat_id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, nullable=False)
    block = db.Column(db.String(16), nullable=False)
    street_name = db.Column(db.String(128), nullable=False)
    floor_number = db.Column(db.Integer, nullable=False)
    unit_number = db.Column(db.String(8), nullable=False)
    flat_type = db.Column(db.String(32), nullable=False)
    area_sqm = db.Column(db.Numeric(10, 2), nullable=False)
    price = db.Column(db.Numeric(12, 2), nullable=False)
    status = db.Column(db.String(32), nullable=False)
    reserved_by = db.Column(db.String(64), nullable=True)
    reserved_at = db.Column(db.DateTime, nullable=True)

    def json(self):
        return {
            "flat_id": self.flat_id,
            "project_id": self.project_id,
            "block": self.block,
            "street_name": self.street_name,
            "floor_number": self.floor_number,
            "unit_number": self.unit_number,
            "flat_type": self.flat_type,
            "area_sqm": float(self.area_sqm) if self.area_sqm is not None else None,
            "price": float(self.price) if self.price is not None else None,
            "status": self.status,
            "reserved_by": self.reserved_by,
            "reserved_at": self.reserved_at.isoformat() if self.reserved_at else None,
        }


def is_positive_int(value):
    return isinstance(value, int) and value > 0


def is_non_empty_int_list(values):
    return isinstance(values, list) and len(values) > 0 and all(is_positive_int(value) for value in values)


def is_valid_flat_type(value):
    return isinstance(value, str) and value.strip() != ''


def parse_optional_positive_int(value, field_name):
    if value is None:
        return None

    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a positive integer.") from exc

    if parsed <= 0:
        raise ValueError(f"{field_name} must be a positive integer.")

    return parsed




def get_available_counts_query(project_ids=None, project_id=None, flat_type=None):
    query = (
        select(
            Flat.project_id.label('project_id'),
            Flat.flat_type.label('flat_type'),
            func.count(Flat.flat_id).label('available_count')
        )
        .where(
            Flat.status == 'available'
        )
        .group_by(Flat.project_id, Flat.flat_type)
        .order_by(Flat.project_id, Flat.flat_type)
    )

    if project_id is not None:
        query = query.where(Flat.project_id == project_id)

    if project_ids is not None:
        query = query.where(Flat.project_id.in_(project_ids))

    if flat_type is not None:
        query = query.where(Flat.flat_type == flat_type)

    return query


def rows_to_counts(rows):
    return [
        {
            "projectId": row.project_id,
            "flatType": row.flat_type,
            "availableCount": row.available_count
        }
        for row in rows
    ]


def group_counts_by_project(rows, project_ids=None):
    grouped = {}
    ordered_project_ids = project_ids[:] if project_ids is not None else []

    for row in rows:
        if row.project_id not in grouped:
            grouped[row.project_id] = []
            if project_ids is None:
                ordered_project_ids.append(row.project_id)

        grouped[row.project_id].append({
            "flatType": row.flat_type,
            "availableCount": row.available_count
        })

    return [
        {
            "projectId": current_project_id,
            "counts": grouped.get(current_project_id, [])
        }
        for current_project_id in ordered_project_ids
    ]


@app.route('/flats', methods=['GET'])
def get_available_flats():
    """
    Get available flats
    ---
    tags:
      - Flat Availability
    responses:
      200:
        description: Flats retrieved successfully
      500:
        description: Error retrieving flats
    """
    flat_type = request.args.get('flat_type')
    project_id = request.args.get('project_id')

    try:
        parsed_project_id = parse_optional_positive_int(project_id, 'project_id')
    except ValueError as error:
        return jsonify({
            "code": 400,
            "message": str(error)
        }), 400

    try:
        query = select(Flat).where(Flat.status == 'available')
        if flat_type:
            query = query.where(Flat.flat_type == flat_type)
        if parsed_project_id is not None:
            query = query.where(Flat.project_id == parsed_project_id)

        query = query.order_by(Flat.block, Flat.floor_number, Flat.unit_number)

        flats = db.session.scalars(query).all()
        if not flats:
            return jsonify({
                "code": 200,
                "data": []
            }), 200

        flats_payload = [flat.json() for flat in flats]

        return jsonify({
            "code": 200,
            "data": flats_payload
        }), 200

    except Exception as e:
        return jsonify({
            "code": 500,
            "message": f"Error retrieving flats: {str(e)}"
        }), 500


@app.route('/flats/<int:flat_id>', methods=['GET'])
def get_flat(flat_id):
    """
    Get flat details by flat ID
    ---
    tags:
      - Flat Availability
    responses:
      200:
        description: Flat retrieved successfully
      404:
        description: Flat not found
      500:
        description: Error retrieving flat
    """
    try:
        flat = db.session.get(Flat, flat_id)

        if not flat:
            return jsonify({
                "code": 404,
                "message": f"Flat {flat_id} not found."
            }), 404

        return jsonify({
            "code": 200,
            "data": flat.json()
        }), 200

    except Exception as e:
        return jsonify({
            "code": 500,
            "message": f"Error retrieving flat: {str(e)}"
        }), 500


@app.route('/flats/<int:flat_id>/reserve', methods=['PUT'])
def reserve_flat(flat_id):
    """
    Reserve a flat
    ---
    tags:
      - Flat Availability
    responses:
      200:
        description: Flat reserved successfully
      400:
        description: Missing applicant_id
      404:
        description: Flat not found
      409:
        description: Flat not available
      500:
        description: Error reserving flat
    """
    data = request.get_json()

    if not data or 'applicant_id' not in data:
        return jsonify({
            "code": 400,
            "message": "applicant_id is required."
        }), 400

    applicant_id = data['applicant_id']

    try:
        flat = db.session.get(Flat, flat_id)

        if not flat:
            return jsonify({
                "code": 404,
                "message": f"Flat {flat_id} not found."
            }), 404

        if flat.status != 'available':
            return jsonify({
                "code": 409,
                "message": f"Flat {flat_id} is not available. Current status: {flat.status}"
            }), 409

        update_stmt = (
            update(Flat)
            .where(Flat.flat_id == flat_id, Flat.status == 'available')
            .values(status='reserved', reserved_by=applicant_id, reserved_at=datetime.now())
        )
        result = db.session.execute(update_stmt)
        db.session.commit()

        if result.rowcount == 0:
            return jsonify({
                "code": 409,
                "message": f"Flat {flat_id} was just reserved by another applicant."
            }), 409

        return jsonify({
            "code": 200,
            "message": f"Flat {flat_id} reserved successfully for applicant {applicant_id}."
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({
            "code": 500,
            "message": f"Error reserving flat: {str(e)}"
        }), 500


@app.route('/flats/<int:flat_id>/unreserve', methods=['PUT'])
def unreserve_flat(flat_id):
    """
    Unreserve a flat
    ---
    tags:
      - Flat Availability
    responses:
      200:
        description: Flat unreserved successfully
      404:
        description: Flat not found
      409:
        description: Flat not reserved
      500:
        description: Error unreserving flat
    """
    try:
        flat = db.session.get(Flat, flat_id)

        if not flat:
            return jsonify({
                "code": 404,
                "message": f"Flat {flat_id} not found."
            }), 404

        if flat.status != 'reserved':
            return jsonify({
                "code": 409,
                "message": f"Flat {flat_id} is not reserved. Current status: {flat.status}"
            }), 409

        update_stmt = (
            update(Flat)
            .where(Flat.flat_id == flat_id, Flat.status == 'reserved')
            .values(status='available', reserved_by=None, reserved_at=None)
        )
        db.session.execute(update_stmt)
        db.session.commit()

        return jsonify({
            "code": 200,
            "message": f"Flat {flat_id} unreserved successfully."
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({
            "code": 500,
            "message": f"Error unreserving flat: {str(e)}"
        }), 500


@app.route('/flats/available-counts', methods=['GET'])
def get_all_available_flat_counts():
    """
    Get available flat counts for all projects
    ---
    tags:
      - Flat Availability
    responses:
      200:
        description: Available flat counts retrieved successfully
      500:
        description: Error retrieving flat counts
    """
    try:
        rows = db.session.execute(get_available_counts_query()).all()

        return jsonify({
            "code": 200,
            "data": {
                "counts": rows_to_counts(rows)
            }
        }), 200

    except Exception as e:
        return jsonify({
            "code": 500,
            "message": f"Error retrieving flat counts: {str(e)}"
        }), 500




@app.route('/flats/available-counts/projects', methods=['GET'])
def get_multiple_projects_available_flat_counts():
    """
    Get available flat counts for multiple projects
    ---
    tags:
      - Flat Availability
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
    responses:
      200:
        description: Available flat counts for the projects retrieved successfully
      400:
        description: Invalid request body
      500:
        description: Error retrieving flat counts
    """
    data = request.get_json()

    if not isinstance(data, dict):
        return jsonify({
            "code": 400,
            "message": ["Request body must be valid JSON."]
        }), 400

    project_ids = data.get('projectIds')
    if not is_non_empty_int_list(project_ids):
        return jsonify({
            "code": 400,
            "message": ["projectIds must be a non-empty list of positive integers."]
        }), 400

    try:
        rows = db.session.execute(get_available_counts_query(project_ids=project_ids)).all()

        return jsonify({
            "code": 200,
            "data": {
                "projects": group_counts_by_project(rows, project_ids)
            }
        }), 200

    except Exception as e:
        return jsonify({
            "code": 500,
            "message": f"Error retrieving flat counts: {str(e)}"
        }), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5006, debug=True)
    
