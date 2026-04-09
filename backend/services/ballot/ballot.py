"""Ballot service — weighted random queue-number assignment."""

from flask import Flask, request, jsonify
from flasgger import Swagger
import random

app = Flask(__name__)

app.config['SWAGGER'] = {
    'title': 'Ballot microservice API',
    'version': 1.0,
    'openapi': '3.0.2',
    'description': (
        'Assigns a queue number to every submitted application via random '
        'draw. All applicants receive a queue number — there is no '
        'UNSUCCESSFUL outcome. Lower queue numbers get to select flats first.'
    ),
}
swagger = Swagger(app)


# Validates application.
def validate_application(app_data, seen_ids):
    errors = []

    if 'applicationId' not in app_data:
        errors.append('applicationId is required for every application.')
    else:
        if app_data['applicationId'] in seen_ids:
            errors.append(f"Duplicate applicationId: {app_data['applicationId']}")
        else:
            seen_ids.add(app_data['applicationId'])

    final_chances = app_data.get('finalChances')
    app_label = app_data.get('applicationId', 'UNKNOWN')
    if final_chances is None:
        errors.append(f"finalChances is required for application {app_label}.")
    elif not isinstance(final_chances, int) or final_chances < 1:
        errors.append(f"finalChances must be a positive integer for application {app_label}.")

    return errors


# Validates request.
def validate_request(data):
    if not isinstance(data, dict):
        return ['Request body must be valid JSON.']

    errors = []
    applications = data.get('applications')
    if not isinstance(applications, list) or not applications:
        errors.append('applications must be a non-empty list.')
    else:
        seen_ids = set()
        for app_data in applications:
            errors.extend(validate_application(app_data, seen_ids))

    return errors


# Runs ballot.
def run_ballot(applications):
    """
    Weighted random draw using finalChances as ticket count.
    Every applicant still receives a queue number (1-indexed).
    """
    ticket_pool = []
    for app in applications:
        app_id = app["applicationId"]
        final_chances = app["finalChances"]
        for _ in range(final_chances):
            ticket_pool.append(app_id)

    random.shuffle(ticket_pool)

    seen = set()
    app_ids = []
    for app_id in ticket_pool:
        if app_id in seen:
            continue
        seen.add(app_id)
        app_ids.append(app_id)

    return [
        {'applicationId': app_id, 'queueNumber': i + 1}
        for i, app_id in enumerate(app_ids)
    ]


# Runs ballot endpoint.
@app.route('/ballot/run', methods=['POST'])
def run_ballot_endpoint():
    """
    Assign queue numbers to all applications
    ---
    tags:
      - Ballot
    summary: Run ballot and assign queue numbers
    description: |
      Accepts a list of applications. Every application receives a queue
      number — there is no unsuccessful outcome. The draw is weighted by
      finalChances, so a higher value increases chance of a lower queue number.
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            required:
              - applications
            properties:
              applications:
                type: array
                items:
                  type: object
                  required:
                    - applicationId
                    - finalChances
                  properties:
                    applicationId:
                      type: integer
                      example: 42
                    finalChances:
                      type: integer
                      minimum: 1
                      example: 2
    responses:
      200:
        description: Queue numbers assigned to all applications.
      400:
        description: Invalid request input.
      500:
        description: Unexpected ballot error.
    """
    data = request.get_json(silent=True)
    errors = validate_request(data)
    if errors:
        return jsonify({'code': 400, 'message': errors}), 400

    try:
        results = run_ballot(data['applications'])
        return jsonify({
            'code': 200,
            'data': {
                'total': len(results),
                'results': results,
            },
        }), 200
    except Exception as exc:
        return jsonify({'code': 500, 'message': f'Error running ballot: {str(exc)}'}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5005, debug=True)
