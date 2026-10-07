from typing import Any, Literal
from urllib.parse import urlsplit

from jsonschema import Draft202012Validator, SchemaError
from pydantic import BaseModel, Field, field_validator


class Suite(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    base_url: str

    @field_validator("base_url")
    @classmethod
    def valid_url(cls, value):
        parts = urlsplit(value)
        if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
            raise ValueError("Use an HTTP(S) base URL without credentials, query or fragment")
        return value.rstrip("/")


class Check(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"] = "GET"
    path: str
    headers: dict[str, str] = Field(default_factory=dict)
    body: Any = None
    expected_status: int = Field(default=200, ge=100, le=599)
    expected_headers: dict[str, str] = Field(default_factory=dict)
    json_schema: dict[str, Any] | None = None
    max_response_ms: float | None = Field(default=None, gt=0)
    timeout_seconds: float = Field(default=5, gt=0, le=30)

    @field_validator("path")
    @classmethod
    def relative_path(cls, value):
        if not value.startswith("/") or value.startswith("//") or "\\" in value or "#" in value:
            raise ValueError("Path must begin with one slash and contain no fragment or backslash")
        return value

    @field_validator("json_schema")
    @classmethod
    def valid_schema(cls, value):
        if value is not None:
            try:
                Draft202012Validator.check_schema(value)
            except SchemaError as exc:
                raise ValueError(exc.message) from exc
            def reject_refs(node):
                if isinstance(node, dict):
                    if "$ref" in node and not str(node["$ref"]).startswith("#"):
                        raise ValueError("Only local JSON schema references are supported")
                    if "$dynamicRef" in node:
                        raise ValueError("Dynamic references are not supported")
                    for child in node.values():
                        reject_refs(child)
                elif isinstance(node, list):
                    for child in node:
                        reject_refs(child)
            reject_refs(value)
        return value
