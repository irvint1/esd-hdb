from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
import re
from datetime import datetime

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+mysqlconnector://root@localhost:3306/applicant'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {'pool_recycle': 299}

db = SQLAlchemy(app)

class Applicant(db.Model):
    __tablename__ = 'applicant'

    applicant_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    nric = db.Column(db.String(9), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    date_of_birth = db.Column(db.Date, nullable=False)
    mobile_number = db.Column(db.String(8), unique=True, nullable=False)
    email = db.Column(db.String(64), unique=True, nullable=False)
    address = db.Column(db.String(128), nullable=False)
    place_of_birth = db.Column(db.String(64), nullable=False)
    race = db.Column(db.String(32), nullable=False)
    nationality = db.Column(db.String(32), nullable=False)
    sex = db.Column(db.String(10), nullable=False)

    def __init__(self, nric, name, date_of_birth, mobile_number, email,
                 address, place_of_birth, race, nationality, sex):
        self.nric = nric
        self.name = name
        self.date_of_birth = date_of_birth
        self.mobile_number = mobile_number
        self.email = email
        self.address = address
        self.place_of_birth = place_of_birth
        self.race = race
        self.nationality = nationality
        self.sex = sex

    def json(self):
        return {
            "applicant_id": self.applicant_id,
            "nric": self.nric,
            "name": self.name,
            "date_of_birth": str(self.date_of_birth),
            "mobile_number": self.mobile_number,
            "email": self.email,
            "address": self.address,
            "place_of_birth": self.place_of_birth,
            "race": self.race,
            "nationality": self.nationality,
            "sex": self.sex
        }

# GET all applicants
@app.route("/applicant")
def get_all():
    applicants = db.session.scalars(db.select(Applicant)).all()

    if applicants:
        return jsonify({
            "code": 200,
            "data": {
                "applicants": [a.json() for a in applicants]
            }
        })
    return jsonify({
        "code": 404,
        "message": "There are no applicants."
    }), 404

# GET specific applicant
@app.route("/applicant/<int:applicant_id>")
def find_by_id(applicant_id):
    applicant = db.session.scalar(db.select(Applicant).filter_by(applicant_id=applicant_id))

    if applicant:
        return jsonify({
            "code": 200,
            "data": applicant.json()
        })
    return jsonify({
        "code": 404,
        "message": "Applicant not found."
    }), 404

def is_valid_nric(nric):
    pattern = r'^[ST]\d{7}[A-Z]$'
    return re.match(pattern, nric) is not None

def is_valid_email(email):
    pattern = r'^[\w\.-]+@[\w\.-]+\.\w+$'
    return re.match(pattern, email) is not None

def is_valid_mobile(number):
    return number.isdigit() and len(number) == 8

def is_valid_sex(sex):
    return sex in ["Male", "Female"]

def is_valid_date(date_text):
    try:
        datetime.strptime(date_text, '%Y-%m-%d')
        return True
    except:
        return False

# CREATE applicant
@app.route("/applicant", methods=['POST'])
def create_applicant():
    data = request.get_json()
    errors = []

    # NRIC validation
    if not is_valid_nric(data.get('nric', '')):
        errors.append("Invalid NRIC format.")

    # Email validation
    if not is_valid_email(data.get('email', '')):
        errors.append("Invalid email format.")
    
    # Mobile validation
    if not is_valid_mobile(data.get('mobile_number', '')):
        errors.append("Invalid mobile number.")
    
    # Date validation
    if not is_valid_date(data.get('date_of_birth', '')):
        errors.append("Invalid date format (YYYY-MM-DD).")
    
    # Sex validation
    if not is_valid_sex(data.get('sex', '')):
        errors.append("Sex must be Male or Female.")

    # Check duplicate NRIC
    if db.session.scalar(db.select(Applicant).filter_by(nric=data['nric'])):
        errors.append("Applicant with this NRIC already exists.")
    
    # Check duplicate Email
    if db.session.scalar(db.select(Applicant).filter_by(email=data['email'])):
        errors.append("Applicant with this email already exists.")
    
    # Check duplicate Mobile
    if db.session.scalar(db.select(Applicant).filter_by(mobile_number=data['mobile_number'])):
        errors.append("Applicant with this mobile number already exists.")

    if errors:
        return jsonify({
            "code": 400,
            "message": errors
        }), 400
    
    applicant = Applicant(**data)

    try:
        db.session.add(applicant)
        db.session.commit()
    except:
        return jsonify({
            "code": 500,
            "message": "Error creating applicant."
        }), 500

    return jsonify({
        "code": 201,
        "data": applicant.json()
    }), 201

# UPDATE applicant
@app.route("/applicant/<int:applicant_id>", methods=['PUT'])
def update_applicant(applicant_id):
    applicant = db.session.get(Applicant, applicant_id)

    if not applicant:
        return jsonify({
            "code": 404,
            "message": "Applicant not found."
        }), 404

    data = request.get_json()
    errors = []

    # Validate mobile number 
    if 'mobile_number' in data:
        if not is_valid_mobile(data['mobile_number']):
            errors.append("Invalid mobile number.")

        # Check duplicate mobile
        existing = db.session.scalar(
            db.select(Applicant).filter_by(mobile_number=data['mobile_number'])
        )
        if existing and existing.applicant_id != applicant_id:
            errors.append("Mobile number already exists.")

    # Validate NRIC if provided
    if 'nric' in data:
        if not is_valid_nric(data['nric']):
            errors.append("Invalid NRIC format.")

        existing = db.session.scalar(
            db.select(Applicant).filter_by(nric=data['nric'])
        )
        if existing and existing.applicant_id != applicant_id:
            errors.append("NRIC already exists.")

    # Validate email if provided
    if 'email' in data:
        if not is_valid_email(data['email']):
            errors.append("Invalid email format.")

        existing = db.session.scalar(
            db.select(Applicant).filter_by(email=data['email'])
        )
        if existing and existing.applicant_id != applicant_id:
           errors.append("Email already exists.")

    # Validate data if provided
    if 'date_of_birth' in data:
        if not is_valid_date(data['date_of_birth']):
            errors.append("Invalid date format.")

    # Validate sex if provided
    if 'sex' in data:
        if not is_valid_sex(data['sex']):
            errors.append("Sex must be Male or Female.")

    if errors:
        return jsonify({
            "code": 400,
            "message": errors
        }), 400

    for key, value in data.items():
        setattr(applicant, key, value)

    try:
        db.session.commit()
    except:
        return jsonify({
            "code": 500,
            "message": "Error updating applicant."
        }), 500

    return jsonify({
        "code": 200,
        "data": applicant.json()
    })

# DELETE applicant
@app.route("/applicant/<int:applicant_id>", methods=['DELETE'])
def delete_applicant(applicant_id):
    applicant = db.session.get(Applicant, applicant_id)

    if not applicant:
        return jsonify({
            "code": 404,
            "message": "Applicant not found."
        }), 404

    try:
        db.session.delete(applicant)
        db.session.commit()
    except:
        return jsonify({
            "code": 500,
            "message": "Error deleting applicant."
        }), 500

    return jsonify({
        "code": 200,
        "message": "Applicant deleted."
    })

## Search by NRIC????
@app.route("/applicant/nric/<string:nric>")
def find_by_nric(nric):
    applicant = db.session.scalar(
        db.select(Applicant).filter_by(nric=nric)
    )

    if applicant:
        return jsonify({
            "code": 200,
            "data": applicant.json()
        })

    return jsonify({
        "code": 404,
        "message": "Applicant not found."
    }), 404

if __name__ == '__main__':
    app.run(port=5001, debug=True)