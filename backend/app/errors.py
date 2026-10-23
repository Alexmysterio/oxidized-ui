from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("oxidized_ui.errors")

ERROR_CODES_PATH = Path(__file__).with_name("data") / "error_codes.json"
ERROR_STATUS: dict[str, int] = json.loads(ERROR_CODES_PATH.read_text(encoding="utf-8"))
ERROR_CODES = frozenset(ERROR_STATUS)


class AppError(Exception):
    def __init__(
        self,
        code: str,
        *,
        status_code: int | None = None,
        params: dict[str, Any] | None = None,
        fields: list[dict[str, Any]] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        if code not in ERROR_CODES:
            raise ValueError(f"Unknown error code: {code}")
        self.code = code
        self.status_code = status_code or ERROR_STATUS.get(code, 400)
        self.params = params or {}
        self.fields = fields or []
        self.headers = headers or {}
        super().__init__(code)

    def payload(self) -> dict[str, Any]:
        error: dict[str, Any] = {"code": self.code, "params": self.params}
        if self.fields:
            error["fields"] = self.fields
        return {"error": error}


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


def _with_request_id(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    request_id = _request_id(request)
    if request_id:
        payload["error"]["request_id"] = request_id
    return payload


def _field_code(error_type: str) -> str:
    mapping = {
        "missing": "validation.required",
        "string_too_long": "validation.too_long",
        "string_too_short": "validation.min",
        "too_long": "validation.too_long",
        "too_short": "validation.min",
        "greater_than_equal": "validation.min",
        "less_than_equal": "validation.max",
        "greater_than": "validation.min",
        "less_than": "validation.max",
        "enum": "validation.invalid_choice",
        "literal_error": "validation.invalid_choice",
        "string_type": "validation.invalid_type",
        "int_type": "validation.invalid_type",
        "bool_type": "validation.invalid_type",
        "list_type": "validation.invalid_type",
        "dict_type": "validation.invalid_type",
        "json_invalid": "validation.invalid_format",
        "value_error": "validation.invalid_format",
        "url_scheme": "validation.invalid_format",
        "url_parsing": "validation.invalid_format",
    }
    return mapping.get(error_type, "validation.failed")


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_with_request_id(exc.payload(), _request),
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        fields: list[dict[str, Any]] = []
        for item in exc.errors():
            loc = [str(part) for part in item.get("loc", []) if part not in {"body", "query", "path"}]
            error_type = item.get("type", "value_error")
            fields.append(
                {
                    "path": ".".join(loc) or "body",
                    "code": _field_code(error_type),
                    "params": {"type": error_type},
                }
            )
        payload = {
            "error": {
                "code": "validation.failed",
                "params": {},
                "fields": fields,
            }
        }
        return JSONResponse(
            status_code=422,
            content=_with_request_id(payload, request),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        if exc.status_code == 404:
            app_error = AppError("app.not_found")
        elif exc.status_code == 403:
            app_error = AppError("auth.forbidden")
        elif exc.status_code == 401:
            app_error = AppError("auth.unauthenticated")
        elif exc.status_code == 429:
            app_error = AppError("app.rate_limited")
        else:
            app_error = AppError("app.internal_error", status_code=exc.status_code)
        return JSONResponse(
            status_code=app_error.status_code,
            content=_with_request_id(app_error.payload(), request),
            headers=exc.headers or {},
        )

    @app.exception_handler(Exception)
    async def _unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error (request_id=%s)", _request_id(request), exc_info=exc)
        return JSONResponse(
            status_code=500,
            content=_with_request_id({"error": {"code": "app.internal_error", "params": {}}}, request),
        )
