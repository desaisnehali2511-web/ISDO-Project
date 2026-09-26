"""
ISDO Lab C2 — Mock Jira REST API (Flask)
  GET /rest/agile/1.0/board/requests   all service requests
  GET /rest/api/2/issue/<key>          one request, Jira-style nested 'fields'
  GET /health                          status
Run: python mcp_server/jira_shim.py   ->  http://localhost:5002
"""
import csv
import os
from flask import Flask, jsonify

app = Flask(__name__)
app.json.sort_keys = False

DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "requests.csv")


def load_requests():
    requests_data = {}
    try:
        with open(DATA_FILE, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                row.pop(None, None)
                requests_data[row["key"]] = row
    except FileNotFoundError:
        print(f"Warning: {DATA_FILE} not found - starting with no requests.")
    return requests_data


REQUESTS = load_requests()


def to_jira(req):
    """Flat CSV row -> Jira issue with nested 'fields' object."""
    return {
        "key": req["key"],
        "fields": {
            "summary": req.get("summary"),
            "issuetype": {"name": req.get("request_type")},
            "priority": {"name": req.get("priority")},
            "status": {"name": req.get("status")},
            "assignee": {"displayName": req.get("assignee")},
            "customfield_sla": req.get("sla"),
        },
    }


@app.get("/rest/agile/1.0/board/requests")
def list_requests():
    results = list(REQUESTS.values())
    return jsonify({"issues": results, "total": len(results)})


@app.get("/rest/api/2/issue/<key>")
def get_request(key):
    req = REQUESTS.get(key)
    if not req:
        return jsonify({"errorMessages": [f"Issue {key} does not exist"]}), 404
    return jsonify(to_jira(req))


@app.get("/health")
def health():
    return jsonify({"status": "ok", "service": "Jira Mock", "requests_loaded": len(REQUESTS)})


if __name__ == "__main__":
    print("Jira Mock API starting on http://localhost:5002")
    print(f"Loaded {len(REQUESTS)} requests from data/requests.csv")
    app.run(host="127.0.0.1", port=5002, debug=True, use_reloader=False)