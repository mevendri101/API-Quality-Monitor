"""Run against Docker Compose: python scripts/demo.py."""
import os
from pathlib import Path

import httpx

CHECKS = [
    {"name": "Health", "path": "/health"},
    {"name": "Products contract", "path": "/products", "json_schema": {"type": "array", "items": {"type": "object", "required": ["id", "name", "price"]}}},
    {"name": "Create user", "method": "POST", "path": "/users", "body": {"name": "Alice"}, "expected_status": 201},
    {"name": "Reject missing name", "method": "POST", "path": "/users", "body": {}, "expected_status": 422},
    {"name": "Reject anonymous", "path": "/private", "expected_status": 401},
    {"name": "Accept token", "path": "/private", "headers": {"Authorization": "Bearer demo-token"}},
    {"name": "JSON content type", "path": "/health", "expected_headers": {"content-type": "application/json"}},
    {"name": "BUG: wrong status", "path": "/broken/status", "expected_status": 201},
    {"name": "BUG: missing ID", "path": "/broken/schema", "json_schema": {"type": "object", "required": ["id"]}},
    {"name": "BUG: slow response", "path": "/broken/slow", "max_response_ms": 100},
]


def main():
    with httpx.Client(base_url=os.getenv("MONITOR_URL", "http://localhost:8000"), timeout=60) as client:
        response = client.post("/suites", json={"name": "Demo Shop regression", "base_url": os.getenv("TARGET_URL", "http://demo:8001")})
        response.raise_for_status()
        suite_id = response.json()["id"]
        for check in CHECKS:
            client.post(f"/suites/{suite_id}/checks", json=check).raise_for_status()
        response = client.post(f"/suites/{suite_id}/runs")
        response.raise_for_status()
        run = response.json()
        report = client.get(f'/runs/{run["id"]}/report')
        report.raise_for_status()
        Path("reports").mkdir(exist_ok=True)
        path = Path("reports") / f'run-{run["id"]}.html'
        path.write_text(report.text, encoding="utf-8")
        print(f'{run["passed"]} passed, {run["failed"]} failed. Expected: 7 passed, 3 intentional failures.')
        print(f'Report: {path.resolve()}')


if __name__ == "__main__":
    main()
