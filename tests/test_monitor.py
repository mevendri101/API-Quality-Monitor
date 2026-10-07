import asyncio

import httpx
import pytest
from fastapi.testclient import TestClient

from monitor.app import create_app
from monitor.demo import app as demo
from monitor.models import Check
from monitor.runner import execute
from scripts.demo import CHECKS


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / "test.db", httpx.ASGITransport(app=demo))) as client:
        yield client


def suite(client, name="Demo"):
    return client.post("/suites", json={"name": name, "base_url": "http://demo"}).json()["id"]


def test_regression_report_history_and_persistence(client, tmp_path):
    sid = suite(client, "<script>alert(1)</script>")
    for check in CHECKS:
        assert client.post(f"/suites/{sid}/checks", json=check).status_code == 201
    response = client.post(f"/suites/{sid}/runs")
    assert response.status_code == 201
    run = response.json()
    assert (run["total"], run["passed"], run["failed"]) == (10, 7, 3)
    assert all(r["errors"] for r in run["results"][-3:])
    assert client.get(f"/suites/{sid}/runs").json() == [run]
    report = client.get(f'/runs/{run["id"]}/report').text
    assert "<script>" not in report and "&lt;script&gt;" in report
    with TestClient(create_app(tmp_path / "test.db")) as reopened:
        assert reopened.get(f'/runs/{run["id"]}').json() == run


def test_missing_and_empty(client):
    assert client.get("/runs/999").status_code == 404
    assert client.post("/suites/999/runs").status_code == 404
    sid = suite(client)
    assert client.post(f"/suites/{sid}/runs").status_code == 409


@pytest.mark.parametrize("changes", [
    {"path": "https://other.test"}, {"path": "//other.test"},
    {"json_schema": {"type": "invalid"}},
    {"json_schema": {"$ref": "https://other.test/schema"}},
    {"timeout_seconds": 0}, {"expected_status": 999},
])
def test_reject_invalid_checks(client, changes):
    sid = suite(client)
    assert client.post(f"/suites/{sid}/checks", json={"name": "Test", "path": "/", **changes}).status_code == 422


@pytest.mark.parametrize("failure", [httpx.ConnectError, httpx.ReadTimeout])
def test_network_errors_are_results(failure):
    def handler(request):
        raise failure("simulated", request=request)
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await execute(client, "http://demo", Check(name="Network", path="/"))
    result = asyncio.run(run())
    assert not result["passed"] and failure.__name__ in result["errors"][0]


def test_header_and_non_json_failures(client):
    sid = suite(client)
    client.post(f"/suites/{sid}/checks", json={"name": "Bad contract", "path": "/text", "json_schema": {"type": "object"}, "expected_headers": {"x-missing": "yes"}})
    errors = client.post(f"/suites/{sid}/runs").json()["results"][0]["errors"]
    assert len(errors) == 2


def test_suite_isolation(client):
    first, second = suite(client), suite(client)
    client.post(f"/suites/{first}/checks", json={"name": "Health", "path": "/health"})
    assert client.get(f"/suites/{second}/checks").json() == []
    assert client.post(f"/suites/{second}/runs").status_code == 409
