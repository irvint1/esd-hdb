"""Singpass and MyInfo mock service backed by the local v3.json dataset."""

import json
import os
from pathlib import Path

from flask import Flask, jsonify, request
from flask_cors import CORS
from flasgger import Swagger

DATA_PATH = Path(os.environ.get("SINGPASS_DATA_PATH", Path(__file__).with_name("v3.json")))

app = Flask(__name__)
CORS(app)

app.config["SWAGGER"] = {
    "title": "Singpass Mock API",
    "version": 1.0,
    "openapi": "3.0.2",
    "description": "Serves mock Singpass login and MyInfo persona data from v3.json",
}
swagger = Swagger(app)


#  Handles load personas for this service.
def load_personas():
    with DATA_PATH.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    personas = payload.get("personas", {})
    if not isinstance(personas, dict):
        personas = {}

    return personas


PERSONAS = load_personas()


#  Handles get persona for this service.
def get_persona(nric):
    return PERSONAS.get(nric.strip().upper())


#  Handles singpass login for this service.
@app.route("/singpass/login", methods=["POST"])
def singpass_login():
    """
    Simulate a Singpass login
    ---
    tags:
      - Singpass
    summary: Sign in with NRIC
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            required:
              - nric
            properties:
              nric:
                type: string
                example: S9812381D
    responses:
      200:
        description: Persona found and login simulated successfully
      400:
        description: Missing or invalid NRIC
      404:
        description: No persona exists for the NRIC
    """
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "Request body must be a JSON object."}), 400

    raw_nric = payload.get("nric")
    if not isinstance(raw_nric, str) or not raw_nric.strip():
        return jsonify({"error": "nric is required."}), 400

    nric = raw_nric.strip().upper()
    persona = get_persona(nric)
    if persona is None:
        return jsonify({"error": "Persona not found."}), 404

    return jsonify(
        {
            "nric": nric,
            "name": persona.get("name", {}).get("value"),
        }
    )


#  Handles get profile for this service.
@app.route("/singpass/profile", methods=["GET"])
def get_profile():
    """
    Retrieve a full MyInfo persona
    ---
    tags:
      - Singpass
    summary: Get MyInfo profile by NRIC
    parameters:
      - in: query
        name: nric
        required: true
        schema:
          type: string
        example: S9812381D
    responses:
      200:
        description: Persona returned successfully
      400:
        description: Missing NRIC
      404:
        description: No persona exists for the NRIC
    """
    raw_nric = request.args.get("nric")
    if not isinstance(raw_nric, str) or not raw_nric.strip():
        return jsonify({"error": "nric is required."}), 400

    nric = raw_nric.strip().upper()
    persona = get_persona(nric)
    if persona is None:
        return jsonify({"error": "Persona not found."}), 404

    return jsonify(persona)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5007, debug=False)
