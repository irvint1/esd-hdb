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
    responses:
        200:
            description: Return all ballot audit records
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
        "message": "No ballot audit recordsfound."
    }), 404





if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)