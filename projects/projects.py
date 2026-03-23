from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from flasgger import Swagger
import os

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
    'DATABASE_URL', 'mysql+mysqlconnector://root@localhost:3306/projects'
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {'pool_recycle': 299}

db = SQLAlchemy(app)

app.config['SWAGGER'] = {
    'title': 'Projects Microservice API',
    'version': 1.0,
    'openapi': '3.0.2',
    'description': 'Manages BTO projects'
}

swagger = Swagger(app)

class Project(db.Model):
    __tablename__ = 'projects'

    project_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    project_name = db.Column(db.String(64), nullable=False)
    town = db.Column(db.String(64), nullable=False)
    exercise_id = db.Column(db.Integer, nullable=False)

    def json(self):
        return {
            "project_id": self.project_id,
            "project_name": self.project_name,
            "town": self.town,
            "exercise_id": self.exercise_id,
        }


@app.route('/projects', methods=['GET'])
def get_all():
    """
    Get all ballot audit records
    ---
    tags:
      - Projects
    responses:
      200:
        description: Project records retrieved successfully
      404:
        description: No project records found
    """

    query = db.select(Project)
    projects = db.session.scalars(query).all()

    if projects:
        return jsonify({
            "code": 200,
            "data": [project.json() for project in projects]
        }), 200

    return jsonify({
        "code": 404,
        "message": "No project records found."
    }), 404

@app.route('/projects/<int:project_id>', methods=['GET'])
def find_by_project_id(project_id):
    """
    Get project by project ID
    ---
    tags:
      - Projects
    responses:
      200:
        description: Project record retrieved successfully
      404:
        description: Project not found
    """

    project = db.session.scalar(db.select(Project).filter_by(project_id=project_id))

    if project:
        return jsonify({
            "code": 200,
            "data": project.json()
        })
    return jsonify({
        "code": 404,
        "message": "Project not found."
    }), 404


@app.route('/exercises/<int:exercise_id>/projects', methods=['GET'])
def find_by_exercise_id(exercise_id):
    """
    Get projects by exercise ID
    ---
    tags:
      - Projects
    responses:
      200:
        description: Projects retrieved successfully
      404:
        description: Projects not found
    """

    query = db.select(Project).filter_by(exercise_id=exercise_id)
    projects = db.session.scalars(query).all()

    if projects:
        return jsonify({
            "code": 200,
            "data": [project.json() for project in projects]
        })
    return jsonify({
        "code": 404,
        "message": "Projects not found."
    }), 404


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
