from flask import Flask, request, jsonify
from flask_cors import CORS
import mysql.connector
from datetime import datetime
import os
import asyncio
import websockets
import json
import threading

app = Flask(__name__)
CORS(app)

# Track connected WebSocket clients
connected_clients = set()

db_config = {
    'host': os.environ.get('DB_HOST', 'localhost'),
    'port': int(os.environ.get('DB_PORT', 3306)),
    'user': os.environ.get('DB_USER', 'root'),
    'password': os.environ.get('DB_PASSWORD', ''),
    'database': os.environ.get('DB_NAME', 'flat_availability')
}

def get_db():
    return mysql.connector.connect(**db_config)


# ============================================================
# WebSocket server (raw)
# ============================================================
async def ws_handler(websocket):
    connected_clients.add(websocket)
    try:
        await websocket.wait_closed()
    finally:
        connected_clients.discard(websocket)

async def broadcast(message: dict):
    if connected_clients:
        data = json.dumps(message)
        await asyncio.gather(*[ws.send(data) for ws in connected_clients], return_exceptions=True)

def emit_flat_update(flat_id, status):
    """Called from Flask routes to broadcast via WebSocket."""
    if ws_loop:
        asyncio.run_coroutine_threadsafe(broadcast({'flat_id': flat_id, 'status': status}), ws_loop)

def start_ws_server():
    global ws_loop
    ws_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(ws_loop)
    async def run():
        async with websockets.serve(ws_handler, '0.0.0.0', 5017):
            await asyncio.Future()
    ws_loop.run_until_complete(run())

# Start WS server in background thread
ws_thread = threading.Thread(target=start_ws_server, daemon=True)
ws_thread.start()


# ============================================================
# GET /flats
# ============================================================
@app.route('/flats', methods=['GET'])
def get_available_flats():
    town = request.args.get('town')
    flat_type = request.args.get('flat_type')
    project_id = request.args.get('project_id')
    conn = None
    cursor = None

    try:
        conn = get_db()
        cursor = conn.cursor(dictionary=True)

        query = """
            SELECT f.flat_id, f.block, f.street_name, f.floor_number, 
                   f.unit_number, f.flat_type, f.area_sqm, f.price, f.status,
                   p.project_name, p.town
            FROM flat f
            JOIN bto_project p ON f.project_id = p.project_id
            WHERE f.status = 'available'
        """
        params = []
        if town:
            query += " AND p.town = %s"
            params.append(town)
        if flat_type:
            query += " AND f.flat_type = %s"
            params.append(flat_type)
        if project_id:
            query += " AND f.project_id = %s"
            params.append(project_id)
        query += " ORDER BY p.town, f.block, f.floor_number, f.unit_number"

        cursor.execute(query, params)
        flats = cursor.fetchall()
        for flat in flats:
            flat['area_sqm'] = float(flat['area_sqm'])
            flat['price'] = float(flat['price'])

        return jsonify({"code": 200, "count": len(flats), "data": flats}), 200

    except Exception as e:
        return jsonify({"code": 500, "message": f"Error retrieving flats: {str(e)}"}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


# ============================================================
# GET /flats/<flat_id>
# ============================================================
@app.route('/flats/<int:flat_id>', methods=['GET'])
def get_flat(flat_id):
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT f.flat_id, f.block, f.street_name, f.floor_number, 
                   f.unit_number, f.flat_type, f.area_sqm, f.price, f.status,
                   f.reserved_by, f.reserved_at,
                   p.project_name, p.town
            FROM flat f
            JOIN bto_project p ON f.project_id = p.project_id
            WHERE f.flat_id = %s
        """, (flat_id,))
        flat = cursor.fetchone()

        if not flat:
            return jsonify({"code": 404, "message": f"Flat {flat_id} not found."}), 404

        flat['area_sqm'] = float(flat['area_sqm'])
        flat['price'] = float(flat['price'])
        if flat['reserved_at']:
            flat['reserved_at'] = flat['reserved_at'].isoformat()

        return jsonify({"code": 200, "data": flat}), 200

    except Exception as e:
        return jsonify({"code": 500, "message": f"Error retrieving flat: {str(e)}"}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


# ============================================================
# PUT /flats/<flat_id>/reserve
# ============================================================
@app.route('/flats/<int:flat_id>/reserve', methods=['PUT'])
def reserve_flat(flat_id):
    data = request.get_json()
    conn = None
    cursor = None

    if not data or 'applicant_id' not in data:
        return jsonify({"code": 400, "message": "applicant_id is required."}), 400

    applicant_id = data['applicant_id']

    try:
        conn = get_db()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT flat_id, status FROM flat WHERE flat_id = %s", (flat_id,))
        flat = cursor.fetchone()

        if not flat:
            return jsonify({"code": 404, "message": f"Flat {flat_id} not found."}), 404
        if flat['status'] != 'available':
            return jsonify({"code": 409, "message": f"Flat {flat_id} is not available. Current status: {flat['status']}"}), 409

        cursor.execute("""
            UPDATE flat 
            SET status = 'reserved', reserved_by = %s, reserved_at = %s
            WHERE flat_id = %s AND status = 'available'
        """, (applicant_id, datetime.now(), flat_id))
        conn.commit()

        if cursor.rowcount == 0:
            return jsonify({"code": 409, "message": f"Flat {flat_id} was just reserved by another applicant."}), 409

        emit_flat_update(flat_id, 'reserved')

        return jsonify({"code": 200, "message": f"Flat {flat_id} reserved successfully for applicant {applicant_id}."}), 200

    except Exception as e:
        if conn: conn.rollback()
        return jsonify({"code": 500, "message": f"Error reserving flat: {str(e)}"}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


# ============================================================
# PUT /flats/<flat_id>/unreserve
# ============================================================
@app.route('/flats/<int:flat_id>/unreserve', methods=['PUT'])
def unreserve_flat(flat_id):
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT flat_id, status FROM flat WHERE flat_id = %s", (flat_id,))
        flat = cursor.fetchone()

        if not flat:
            return jsonify({"code": 404, "message": f"Flat {flat_id} not found."}), 404
        if flat['status'] != 'reserved':
            return jsonify({"code": 409, "message": f"Flat {flat_id} is not reserved. Current status: {flat['status']}"}), 409

        cursor.execute("""
            UPDATE flat 
            SET status = 'available', reserved_by = NULL, reserved_at = NULL
            WHERE flat_id = %s AND status = 'reserved'
        """, (flat_id,))
        conn.commit()

        emit_flat_update(flat_id, 'available')

        return jsonify({"code": 200, "message": f"Flat {flat_id} unreserved successfully."}), 200

    except Exception as e:
        if conn: conn.rollback()
        return jsonify({"code": 500, "message": f"Error unreserving flat: {str(e)}"}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5006, debug=False)