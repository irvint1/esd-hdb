from flask import Flask, request, jsonify
from flasgger import Swagger
import random

app = Flask(__name__)

app.config['SWAGGER'] = {
    'title': 'Ballot microservice API',
    'version': 1.0,
    'openapi': '3.0.2',
    'description': 'Runs ballot for one town area and flat type'
}
swagger = Swagger(app)

PRIORITY_QUOTA_RATIO = 0.30
QUEUE_MULTIPLIER = 2

def is_non_empty_list(value):
    return isinstance(value, list) and len(value) > 0

def is_valid_flat_type(flat_type):
    return isinstance(flat_type, str) and flat_type.strip() != ''

def validate_application(app, seen_ids):
    errors = []

    # Need Application ID & cannot have duplication of Application ID
    if 'applicationId' not in app:
        errors.append('applicationId is required for every application.')
    else:
        if app['applicationId'] in seen_ids:
            errors.append(f"Duplicate applicationId found: {app['applicationId']}")
        else:
            seen_ids.add(app['applicationId'])

    # Final Chance need to exist and be valid
    if 'finalChances' not in app:
        errors.append(
            f"finalChances is required for application {app.get('applicationId', 'UNKNOWN')}."
        )
    elif not isinstance(app['finalChances'], int):
        errors.append(
            f"finalChances must be an integer for application {app.get('applicationId', 'UNKNOWN')}."
        )
    elif app['finalChances'] < 1:
        errors.append(
            f"finalChances must be >= 1 for application {app.get('applicationId', 'UNKNOWN')}."
        )

    return errors

def validate_ballot_request(data):
    errors = []

    # check that all fields are valid and the values makes sense then validate every application errors are collated all together
    if not isinstance(data, dict):
        return ['Request body must be valid JSON.']

    if data.get('ballotRunId') is None:
        errors.append('ballotRunId is required.')

    if data.get('exerciseId') is None:
        errors.append('exerciseId is required.')

    if not is_non_empty_list(data.get('projectIds')):
        errors.append('projectIds must be a non-empty list.')

    if not is_valid_flat_type(data.get('flatType')):
        errors.append('flatType is required.')

    available_count = data.get('availableCount')
    if available_count is None:
        errors.append('availableCount is required.')
    elif not isinstance(available_count, int):
        errors.append('availableCount must be an integer.')
    elif available_count < 0:
        errors.append('availableCount must be >= 0.')

    applications = data.get('applications')
    if not is_non_empty_list(applications):
        errors.append('applications must be a non-empty list.')
    else:
        seen_ids = set()
        for app_data in applications:
            errors.extend(validate_application(app_data, seen_ids))

    return errors


def get_priority_group(app):
    if app.get('ballotScheme') is not None:
        return 'PRIORITY'
    return 'NON_PRIORITY'

def split_priority_groups(applications):
    grouped = {
        'PRIORITY': [],
        'NON_PRIORITY': []
    }

    for app in applications:
        grouped[get_priority_group(app)].append(app)
    # grouped the applications into their groups first
    return grouped

def build_weighted_pool(applications):
    weighted_pool = []

    for app in applications:
        for _ in range(app['finalChances']):
            weighted_pool.append(app)

    return weighted_pool

def run_weighted_selection(applications, limit):
    if limit <= 0 or not applications:
        return []

    weighted_pool = build_weighted_pool(applications)
    rng = random.Random()
    rng.shuffle(weighted_pool)

    selected = []
    seen_ids = set()

    for app in weighted_pool:
        app_id = app['applicationId']
        if app_id not in seen_ids:
            seen_ids.add(app_id)
            selected.append(app)

        if len(selected) >= limit:
            break

    return selected

def build_ballot_results(selected_apps, unsuccessful_apps, available_count):
    results = []
    queue_no = 1

    for app in selected_apps:
        results.append({
            'applicationId': app['applicationId'],
            'queueNo': queue_no,
            'status': 'SUCCESS',
        })
        queue_no += 1

    for app in unsuccessful_apps:
        results.append({
            'applicationId': app['applicationId'],
            'queueNo': None,
            'status': 'UNSUCCESSFUL',
        })

    return {
        'status': 'COMPLETED',
        'availableCount': available_count,
        'maxQueueSize': available_count * QUEUE_MULTIPLIER,
        'shortlistedCount': len(selected_apps),
        'unsuccessfulCount': len(unsuccessful_apps),
        'results': results
    }

def run_ballot_bucket_logic(data):
    applications = data['applications']
    available_count = data['availableCount']


    max_queue_size = available_count * QUEUE_MULTIPLIER
    grouped = split_priority_groups(applications)

    priority_apps = grouped['PRIORITY']

    # Round 1: reserved priority quota
    priority_limit = min(round(available_count * PRIORITY_QUOTA_RATIO), max_queue_size)
    priority_selected = run_weighted_selection(priority_apps, priority_limit)

    priority_selected_ids = {app['applicationId'] for app in priority_selected}

    # Round 2: open pool = everyone not already selected 
    remaining_slots = max_queue_size - len(priority_selected)
    remaining_pool = [
        app for app in applications
        if app['applicationId'] not in priority_selected_ids
    ]

    open_selected = run_weighted_selection(remaining_pool, remaining_slots)

    selected_apps = priority_selected + open_selected
    selected_ids = {app['applicationId'] for app in selected_apps}

    unsuccessful_apps = [
        app for app in applications
        if app['applicationId'] not in selected_ids
    ]

    # one final RNG for queue order (priority scheme should only affect whether you get into ballot not your queue number)
    final_queue_apps = selected_apps[:]
    random.shuffle(final_queue_apps)

    response = build_ballot_results(selected_apps, unsuccessful_apps, available_count)
    response['ballotRunId'] = data['ballotRunId']
    response['exerciseId'] = data['exerciseId']
    response['projectIds'] = data['projectIds']
    response['flatType'] = data['flatType']
    response['priorityQuotaRatio'] = PRIORITY_QUOTA_RATIO

    return response

@app.route('/ballot/run-bucket', methods=['GET'])
def run_ballot_bucket():
    """
    Run ballot for one town and flat type
    ---
    tags:
      - Ballot
    responses:
      200:
        description: Ballot completed successfully
      400:
        description: Invalid request input
      500:
        description: Error running ballot
    """
    data = request.get_json()
    errors = validate_ballot_request(data)

    if errors:
        return jsonify({
            'code': 400,
            'message': errors
        }), 400

    try:
        result = run_ballot_bucket_logic(data)
        return jsonify({
            'code': 200,
            'data': result
        })
    except Exception as error:
        return jsonify({
            'code': 500,
            'message': f'Error running ballot: {str(error)}'
        }), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
