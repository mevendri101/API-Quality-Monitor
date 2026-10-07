from time import perf_counter

import httpx
from jsonschema import Draft202012Validator

from .models import Check


async def execute(client: httpx.AsyncClient, base_url: str, check: Check) -> dict:
    started = perf_counter()
    errors = []
    status = None
    try:
        response = await client.request(
            check.method, base_url + check.path, headers=check.headers,
            json=check.body, timeout=check.timeout_seconds, follow_redirects=False,
        )
        elapsed = (perf_counter() - started) * 1000
        status = response.status_code
        if status != check.expected_status:
            errors.append(f"Status: expected {check.expected_status}, received {status}")
        for key, value in check.expected_headers.items():
            if response.headers.get(key) != value:
                errors.append(f"Header {key}: value does not match expectation")
        if check.json_schema is not None:
            try:
                payload = response.json()
            except ValueError:
                errors.append("Response is not valid JSON")
            else:
                try:
                    for error in Draft202012Validator(check.json_schema).iter_errors(payload):
                        location = "/".join(map(str, error.absolute_path)) or "$"
                        errors.append(f"JSON schema at {location}: {error.message}")
                except Exception:
                    errors.append("JSON schema could not be evaluated; check local references")
    except httpx.RequestError as exc:
        elapsed = (perf_counter() - started) * 1000
        errors.append(f"Request failed: {type(exc).__name__}")
    if check.max_response_ms is not None and elapsed > check.max_response_ms:
        errors.append(f"Response time {elapsed:.1f} ms exceeds {check.max_response_ms:g} ms")
    return {"name": check.name, "passed": not errors, "status_code": status,
            "elapsed_ms": round(elapsed, 2), "errors": errors}
