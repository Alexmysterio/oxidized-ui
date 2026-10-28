from __future__ import annotations

import hmac
import ipaddress
import logging
import uuid
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import delete
from sqlalchemy.orm import Session

from . import __version__
from .auth_service import bootstrap_admin, cleanup_sessions
from .config_service import bootstrap_configuration
from .db import SessionLocal
from .errors import AppError, install_error_handlers
from .jobs import interrupt_incomplete_jobs, shutdown_jobs
from .models import AuditLog, Job, LoginAttempt, SystemSettings
from .poller import start_poller, stop_poller
from .request_limit import check_rate_limit
from .routers import (
    audit,
    auth,
    compliance,
    config,
    groups,
    internal,
    logs,
    maintenance,
    map,
    meta,
    metrics,
    nodes,
    preferences,
    reconciliation,
    search,
    status,
    system,
    templates,
    users,
    versions,
)
from .security import csrf_token_for, get_client_ip, origin_is_allowed, request_scheme
from .settings import settings
from .system_service import ensure_system_settings, ensure_system_state
from .timeutil import utcnow

logger = logging.getLogger("oxidized_ui")
logging.basicConfig(
    level=getattr(logging, settings.ui_log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
CSRF_EXEMPT = {"/api/auth/login", "/api/auth/login/mfa", "/api/setup"}
MAX_REQUEST_BODY = 8 * 1024 * 1024


def _static_cache_headers(relative: str) -> dict[str, str]:
    """Keep hashed assets immutable but force revalidation of the SPA shell.

    Locale files and ``index.html`` change without a hashed filename, so a
    heuristically cached copy can keep showing raw i18n keys (for example a new
    sidebar entry such as ``nav.sites``) until the browser decides to refresh.
    """

    if relative.startswith("assets/"):
        return {"Cache-Control": "public, max-age=31536000, immutable"}
    if relative == "index.html" or relative.startswith("locales/"):
        return {"Cache-Control": "no-cache"}
    return {}


def _ip_allowed(request: Request) -> bool:
    # The Oxidized container calls the inventory source over the private Docker
    # network. That endpoint has its own token and must not depend on the LAN
    # allowlist.
    if request.url.path.startswith("/api/internal/"):
        return True
    with SessionLocal() as db:
        row = db.get(SystemSettings, 1)
        if row is None or not (row.ip_allowlist or "").strip():
            return True
        try:
            address = ipaddress.ip_address(get_client_ip(request))
            if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
                address = address.ipv4_mapped
        except ValueError:
            return False
        if address.is_loopback:
            return True
        for entry in (row.ip_allowlist or "").splitlines():
            try:
                if address in ipaddress.ip_network(entry.strip(), strict=False):
                    return True
            except ValueError:
                continue
        return False


def _environment_error(code: str, request: Request, status_code: int = 403) -> JSONResponse:
    payload = {"error": {"code": code, "params": {}, "request_id": getattr(request.state, "request_id", None)}}
    response = JSONResponse(status_code=status_code, content=payload)
    response.headers["X-Request-ID"] = str(getattr(request.state, "request_id", ""))
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    return response


def _run_migrations() -> None:
    if not settings.auto_migrate:
        return
    from alembic.config import Config

    from alembic import command

    backend_dir = Path(__file__).resolve().parents[1]
    ini_path = backend_dir / "alembic.ini"
    if not ini_path.exists():
        raise RuntimeError(f"Alembic config not found at {ini_path}")
    config = Config(str(ini_path))
    config.set_main_option("script_location", str(backend_dir / "alembic"))
    config.set_main_option("sqlalchemy.url", settings.effective_database_url.replace("%", "%%"))
    command.upgrade(config, "head")


def _cleanup_retention(db: Session) -> None:
    now = utcnow()
    retention = ensure_system_settings(db).audit_retention_days or 180
    db.execute(delete(AuditLog).where(AuditLog.created_at < now - timedelta(days=retention)))
    db.execute(delete(Job).where(Job.finished_at.is_not(None), Job.finished_at < now - timedelta(days=30)))
    db.execute(delete(LoginAttempt).where(LoginAttempt.created_at < now - timedelta(days=30)))
    db.commit()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings.ensure_directories()
    _run_migrations()
    with SessionLocal() as db:
        from .compliance_service import encrypt_legacy_templates
        from .node_service import migrate_legacy_coordinate_tags, normalize_all_tags
        from .site_service import migrate_site_coordinates
        from .template_service import encrypt_legacy_vars

        ensure_system_state(db)
        ensure_system_settings(db)
        cleanup_sessions(db)
        interrupt_incomplete_jobs(db)
        bootstrap_admin(db)
        bootstrap_configuration(db)
        migrate_legacy_coordinate_tags(db)
        migrate_site_coordinates(db)
        normalize_all_tags(db)
        encrypt_legacy_vars(db)
        encrypt_legacy_templates(db)
        _cleanup_retention(db)
    if not settings.disable_background_tasks:
        start_poller()
    try:
        yield
    finally:
        from .routers.map import close_client

        await close_client()
        if not settings.disable_background_tasks:
            stop_poller()
        shutdown_jobs()


def create_app() -> FastAPI:
    development = settings.app_env == "development"
    app = FastAPI(
        title="Oxidized UI",
        version=__version__,
        docs_url="/api/docs" if development else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if development else None,
        lifespan=lifespan,
    )
    install_error_handlers(app)

    @app.middleware("http")
    async def _security_middleware(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        request.state.request_id = request_id
        path = request.url.path
        if not _ip_allowed(request):
            return _environment_error("auth.ip_not_allowed", request, 403)
        if path.startswith("/api/") and not path.startswith("/api/internal/"):
            retry_after = check_rate_limit(path, get_client_ip(request))
            if retry_after is not None:
                response = _environment_error("app.rate_limited", request, 429)
                response.headers["Retry-After"] = str(retry_after)
                return response
        bearer_auth = request.headers.get("authorization", "").lower().startswith("bearer ")
        if (
            request.method in UNSAFE_METHODS
            and path.startswith("/api/")
            and not bearer_auth
            and not path.startswith("/api/hooks/")
        ):
            content_length = request.headers.get("content-length")
            if content_length:
                try:
                    if int(content_length) > MAX_REQUEST_BODY:
                        return _environment_error("app.payload_too_large", request, 413)
                except ValueError:
                    return _environment_error("validation.invalid_format", request, 422)
            if not origin_is_allowed(request):
                return _environment_error("auth.origin_rejected", request, 403)
            if path.rstrip("/") not in CSRF_EXEMPT:
                raw = request.cookies.get(settings.session_cookie_name)
                supplied = request.headers.get("x-csrf-token")
                if not raw or not supplied or not hmac.compare_digest(csrf_token_for(raw), supplied):
                    return _environment_error("auth.csrf_failed", request, 403)
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; font-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; "
            "base-uri 'self'; form-action 'self'"
        )
        if settings.session_cookie_secure or request_scheme(request) == "https":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

    api_prefix = "/api"
    app.include_router(meta.router, prefix=api_prefix)
    app.include_router(auth.router, prefix=api_prefix)
    app.include_router(users.router, prefix=api_prefix)
    app.include_router(nodes.router, prefix=api_prefix)
    app.include_router(versions.router, prefix=api_prefix)
    app.include_router(groups.router, prefix=api_prefix)
    app.include_router(config.router, prefix=api_prefix)
    app.include_router(status.router, prefix=api_prefix)
    app.include_router(maintenance.router, prefix=api_prefix)
    app.include_router(compliance.router, prefix=api_prefix)
    app.include_router(preferences.router, prefix=api_prefix)
    app.include_router(templates.router, prefix=api_prefix)
    app.include_router(reconciliation.router, prefix=api_prefix)
    app.include_router(logs.router, prefix=api_prefix)
    app.include_router(map.router, prefix=api_prefix)
    app.include_router(metrics.router, prefix=api_prefix)
    app.include_router(audit.router, prefix=api_prefix)
    app.include_router(system.router, prefix=api_prefix)
    app.include_router(search.router, prefix=api_prefix)
    app.include_router(internal.router, prefix=api_prefix)

    @app.get("/", include_in_schema=False)
    def root():
        index = settings.static_dir / "index.html"
        if index.exists():
            return FileResponse(index, headers=_static_cache_headers("index.html"))
        return JSONResponse(
            status_code=200,
            content={"app": "Oxidized UI", "version": __version__, "api": "/api/meta"},
        )

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa_fallback(full_path: str):
        if full_path.startswith("api/"):
            raise AppError("app.not_found")
        static_root = settings.static_dir.resolve()
        target = (settings.static_dir / full_path).resolve()
        if target.is_file() and (target == static_root or static_root in target.parents):
            return FileResponse(target, headers=_static_cache_headers(full_path))
        index = settings.static_dir / "index.html"
        if index.exists():
            return FileResponse(index, headers=_static_cache_headers("index.html"))
        raise AppError("app.not_found")

    return app


app = create_app()
