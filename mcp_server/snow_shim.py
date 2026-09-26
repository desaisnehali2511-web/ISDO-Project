"""
ISDO Lab C2 — Mock ServiceNow Table API (Flask Shim)
Mimics the ServiceNow Table API so the MCP server / agents can make real
HTTP calls without touching a production system.

Endpoints:
  GET   /api/now/table/incident            — list incidents
        filters: ?category= ?priority= ?state= ?assignment_group=
                 ?sysparm_query=priority=P1^state=Open   ?sysparm_limit=5
  GET   /api/now/table/incident/<number>   — get one incident
  PATCH /api/now/table/incident/<number>   — update fields in memory
  POST  /api/now/table/incident            — create an incident
  GET   /health                            — health check

Run with:  python mcp_server/snow_shim.py      (port 5001)
"""
import csv
import os
from flask import Flask, jsonify, request

app = Flask(__name__)
app.json.sort_keys = False  # keep CSV column order in responses

DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "incidents.csv")
FILTER_FIELDS = ["category", "priority", "state", "assignment_group"]


def load_incidents():
    incidents = {}
    try:
        with open(DATA_FILE, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                row.pop(None, None)  # drop overflow columns from a malformed row
                incidents[row["number"]] = {k: (v or "") for k, v in row.items()}
    except FileNotFoundError:
        print(f"Warning: {DATA_FILE} not found. Starting with empty dataset.")
    return incidents


INCIDENTS = load_incidents()  # in-memory store (the "ServiceNow DB" for this session)


def parse_sysparm_query(q):
    """'priority=P1^state=Open' -> {'priority': 'P1', 'state': 'Open'}"""
    return dict(part.split("=", 1) for part in q.split("^") if "=" in part)


@app.route("/api/now/table/incident", methods=["GET"])
def list_incidents():
    filters = {k: request.args[k] for k in FILTER_FIELDS if request.args.get(k)}
    filters.update(parse_sysparm_query(request.args.get("sysparm_query", "")))
    results = [r for r in INCIDENTS.values()
               if all(r.get(k, "").lower() == v.lower() for k, v in filters.items())]
    total = len(results)
    limit = request.args.get("sysparm_limit", type=int)
    if limit:
        results = results[:limit]
    return jsonify({"result": results, "total": total})


@app.route("/api/now/table/incident/<number>", methods=["GET"])
def get_incident(number):
    incident = INCIDENTS.get(number)
    if not incident:
        return jsonify({"error": f"Incident {number} not found"}), 404
    return jsonify({"result": incident})


@app.route("/api/now/table/incident/<number>", methods=["PATCH"])
def update_incident(number):
    if number not in INCIDENTS:
        return jsonify({"error": f"Incident {number} not found"}), 404
    updates = request.get_json(silent=True)
    if not isinstance(updates, dict) or not updates:
        return jsonify({"error": "Request body must be a non-empty JSON object"}), 400
    updates.pop("number", None)  # the record key cannot be changed
    INCIDENTS[number].update({k: str(v) for k, v in updates.items()})
    print(f"[ServiceNow Mock] Updated {number}: {updates}")
    return jsonify({"result": INCIDENTS[number], "message": "Updated successfully"})


@app.route("/api/now/table/incident", methods=["POST"])
def create_incident():
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not data.get("number"):
        return jsonify({"error": "Missing required field: number"}), 400
    if data["number"] in INCIDENTS:
        return jsonify({"error": f"Incident {data['number']} already exists"}), 409
    data.setdefault("state", "Open")
    INCIDENTS[data["number"]] = {k: str(v) for k, v in data.items()}
    print(f"[ServiceNow Mock] Created incident: {data['number']}")
    return jsonify({"result": INCIDENTS[data["number"]], "message": "Incident created"}), 201


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "ServiceNow Mock", "incidents_loaded": len(INCIDENTS)})


if __name__ == "__main__":
    print("ServiceNow Mock API starting on http://localhost:5001")
    print(f"Loaded {len(INCIDENTS)} incidents from data/incidents.csv")
    print("Endpoints: GET /api/now/table/incident  |  GET /health")
    # use_reloader=False: a code-change reload would silently wipe PATCHed data
    app.run(host="127.0.0.1", port=5001, debug=True, use_reloader=False)
