import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from html import escape

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

from .models import Check, Suite
from .runner import execute


def create_app(db_path=None, transport=None):
    db_path = str(db_path or os.getenv("MONITOR_DB", "monitor.db"))

    @contextmanager
    def database():
        connection = sqlite3.connect(db_path, timeout=10)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    with database() as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS suites (id INTEGER PRIMARY KEY, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS checks (id INTEGER PRIMARY KEY, suite_id INTEGER NOT NULL, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS runs (id INTEGER PRIMARY KEY, suite_id INTEGER NOT NULL, data TEXT NOT NULL);
        """)

    app = FastAPI(title="API Quality Monitor", version="0.1.0")

    def get_suite(db, suite_id):
        row = db.execute("SELECT data FROM suites WHERE id=?", (suite_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "Suite not found")
        return Suite.model_validate_json(row["data"])

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.post("/suites", status_code=201)
    def add_suite(suite: Suite):
        with database() as db:
            cursor = db.execute("INSERT INTO suites(data) VALUES (?)", (suite.model_dump_json(),))
            return {"id": cursor.lastrowid, **suite.model_dump()}

    @app.get("/suites")
    def list_suites():
        with database() as db:
            return [{"id": r["id"], **json.loads(r["data"])} for r in db.execute("SELECT * FROM suites ORDER BY id")]

    @app.post("/suites/{suite_id}/checks", status_code=201)
    def add_check(suite_id: int, check: Check):
        with database() as db:
            get_suite(db, suite_id)
            cursor = db.execute("INSERT INTO checks(suite_id,data) VALUES (?,?)", (suite_id, check.model_dump_json()))
            return {"id": cursor.lastrowid, **check.model_dump()}

    @app.get("/suites/{suite_id}/checks")
    def list_checks(suite_id: int):
        with database() as db:
            get_suite(db, suite_id)
            return [{"id": r["id"], **json.loads(r["data"])} for r in db.execute("SELECT * FROM checks WHERE suite_id=? ORDER BY id", (suite_id,))]

    @app.post("/suites/{suite_id}/runs", status_code=201)
    async def start_run(suite_id: int):
        with database() as db:
            suite = get_suite(db, suite_id)
            checks = db.execute("SELECT data FROM checks WHERE suite_id=? ORDER BY id", (suite_id,)).fetchall()
        if not checks:
            raise HTTPException(409, "Add at least one check before running the suite")
        started = datetime.now(timezone.utc).isoformat()
        async with httpx.AsyncClient(transport=transport, trust_env=False) as client:
            results = [await execute(client, suite.base_url, Check.model_validate_json(c["data"])) for c in checks]
        run = {"suite_id": suite_id, "suite_name": suite.name, "started_at": started,
               "total": len(results), "passed": sum(r["passed"] for r in results), "results": results}
        run["failed"] = run["total"] - run["passed"]
        with database() as db:
            cursor = db.execute("INSERT INTO runs(suite_id,data) VALUES (?,?)", (suite_id, json.dumps(run)))
            return {"id": cursor.lastrowid, **run}

    @app.get("/runs/{run_id}")
    def get_run(run_id: int):
        with database() as db:
            row = db.execute("SELECT data FROM runs WHERE id=?", (run_id,)).fetchone()
            if row is None:
                raise HTTPException(404, "Run not found")
            return {"id": run_id, **json.loads(row["data"])}

    @app.get("/suites/{suite_id}/runs")
    def history(suite_id: int):
        with database() as db:
            get_suite(db, suite_id)
            return [{"id": r["id"], **json.loads(r["data"])} for r in db.execute("SELECT * FROM runs WHERE suite_id=? ORDER BY id DESC", (suite_id,))]

    @app.get("/runs/{run_id}/report", response_class=HTMLResponse)
    def report(run_id: int):
        run = get_run(run_id)
        rows = "".join(
            f'<tr><td>{escape(r["name"])}</td><td class="{"pass" if r["passed"] else "fail"}">'
            f'{"PASS" if r["passed"] else "FAIL"}</td><td>{r["status_code"]}</td>'
            f'<td>{r["elapsed_ms"]}</td><td>{escape("; ".join(r["errors"]))}</td></tr>' for r in run["results"])
        return f'''<!doctype html><html lang="en"><meta charset="utf-8">
        <meta name="viewport" content="width=device-width,initial-scale=1"><title>API Quality Report</title>
        <style>body{{font:16px system-ui;margin:40px;background:#f4f7fb;color:#17243b}}table{{border-collapse:collapse;width:100%;background:white}}td,th{{padding:14px;text-align:left;border-bottom:1px solid #ddd}}.pass{{color:#14783b}}.fail{{color:#b42318}}.table{{overflow:auto}}</style>
        <h1>{escape(run["suite_name"])}</h1><p>Run #{run_id} · {escape(run["started_at"])}</p>
        <p>{run["passed"]} passed / {run["failed"]} failed / {run["total"]} total</p>
        <div class="table"><table><tr><th>Check</th><th>Result</th><th>HTTP</th><th>Time, ms</th><th>Details</th></tr>{rows}</table></div></html>'''

    return app
