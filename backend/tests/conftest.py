from __future__ import annotations

import os
import shutil
import stat
import uuid
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet

TEST_ROOT = Path(__file__).resolve().parents[1] / ".testdata" / f"run-{uuid.uuid4().hex[:8]}"


def _remove_tree(path: Path) -> None:
    """Remove test data even when the host marks the generated tree read-only."""
    if not path.exists():
        return
    if os.name == "nt":
        for root, dirs, files in os.walk(path, topdown=False):
            for name in files:
                os.chmod(Path(root) / name, stat.S_IWRITE)
            for name in dirs:
                os.chmod(Path(root) / name, stat.S_IWRITE)
        os.chmod(path, stat.S_IWRITE)
    shutil.rmtree(path)


TEST_ROOT.mkdir(parents=True, exist_ok=True)
os.environ.update(
    {
        "APP_ENV": "test",
        "SECRET_KEY": "test-secret-key-that-is-at-least-32-bytes-long",
        "FERNET_KEY": Fernet.generate_key().decode(),
        "OXIDIZED_SOURCE_TOKEN": "test-source-token-at-least-24-bytes",
        "DATA_DIR": str(TEST_ROOT / "data"),
        "OXIDIZED_CONFIG_DIR": str(TEST_ROOT / "config"),
        "AUTO_MIGRATE": "false",
        "DISABLE_BACKGROUND_TASKS": "true",
        "OXIDIZED_API_URL": "http://oxidized.invalid:8888",
        "DOCKER_PROXY_URL": "http://docker.invalid:2375",
        "BOOTSTRAP_ADMIN_USERNAME": "",
        "BOOTSTRAP_ADMIN_PASSWORD": "",
    }
)

from fastapi.testclient import TestClient  # noqa: E402

from app import (  # noqa: E402
    backup_service,
    config_alert_service,
    config_service,
    docker_api,
    log_service,
    node_service,
    search_service,
    status_service,
    version_service,
)
from app.db import SessionLocal, create_schema, drop_schema  # noqa: E402
from app.docker_api import LogLine  # noqa: E402
from app.main import app  # noqa: E402
from app.oxidized import OxidizedNode, OxidizedVersion  # noqa: E402
from app.routers import status as status_router  # noqa: E402
from app.routers import system as system_router  # noqa: E402
from app.settings import settings  # noqa: E402

ORIGIN = "http://testserver"
ADMIN_PASSWORD = "CorrectHorseBattery9!"


@dataclass
class AutoClient:
    raw: TestClient
    headers: dict[str, str]

    def get(self, path: str, **kwargs):
        return self.raw.get(path, headers={**self.headers, **kwargs.pop("headers", {})}, **kwargs)

    def post(self, path: str, **kwargs):
        return self.raw.post(path, headers={**self.headers, **kwargs.pop("headers", {})}, **kwargs)

    def patch(self, path: str, **kwargs):
        return self.raw.patch(path, headers={**self.headers, **kwargs.pop("headers", {})}, **kwargs)

    def put(self, path: str, **kwargs):
        return self.raw.put(path, headers={**self.headers, **kwargs.pop("headers", {})}, **kwargs)

    def delete(self, path: str, **kwargs):
        return self.raw.delete(path, headers={**self.headers, **kwargs.pop("headers", {})}, **kwargs)


class FakeOxidized:
    def __init__(self) -> None:
        self.nodes: list[OxidizedNode] = []
        self.reload_calls = 0
        self.next_calls: list[str] = []
        self.fail_api = False
        self.fail_reload = False
        self.versions_map: dict[str, list[OxidizedVersion]] = {}
        self.contents: dict[str, str] = {}
        self.current_configs: dict[str, str] = {}
        self.search_results: list[dict[str, str]] = []

    def list_nodes(self):
        if self.fail_api:
            from app.errors import AppError

            raise AppError("oxidized.unavailable")
        return list(self.nodes)

    def reload(self):
        if self.fail_api or self.fail_reload:
            from app.errors import AppError

            raise AppError("oxidized.reload_failed")
        self.reload_calls += 1

    def next_node(self, name: str):
        if self.fail_api:
            from app.errors import AppError

            raise AppError("oxidized.unavailable")
        self.next_calls.append(name)

    def versions(self, name, group=None):
        return list(self.versions_map.get(name, []))

    def fetch_config(self, name, group=None):
        return self.current_configs.get(name, "hostname test\n")

    def version_content(self, name, group, oid, **kwargs):
        return self.contents.get(oid, f"version {oid}\n")

    def search_configs(self, query):
        return list(self.search_results)


class FakeDocker:
    def __init__(self) -> None:
        self.restart_calls = 0
        self.fail_restart = False
        self.lines: list[LogLine] = [
            LogLine(timestamp="2026-10-21T16:00:00+00:00", stream="stdout", level="info", text="Oxidized starting"),
            LogLine(timestamp="2026-10-21T16:00:01+00:00", stream="stderr", level="error", text="connection failed"),
        ]

    def restart(self):
        if self.fail_restart:
            from app.errors import AppError

            raise AppError("oxidized.restart_failed")
        self.restart_calls += 1

    def container_state(self):
        return {"status": "running", "running": True, "restarting": False, "health": "healthy"}

    def inspect(self):
        return {"State": {"Status": "running", "Running": True, "Restarting": False, "Health": {"Status": "healthy"}}}

    def test(self):
        return {"ok": True, "status": "running"}

    def log_snapshot(self, **kwargs):
        return list(self.lines)

    def stream_logs(self, **kwargs):
        yield from self.lines

    def container_state_error(self):  # pragma: no cover - helper for future tests
        from app.errors import AppError

        raise AppError("docker.unavailable")


@pytest.fixture()
def fake_clients(monkeypatch):
    oxidized = FakeOxidized()
    docker = FakeDocker()
    monkeypatch.setattr(node_service, "oxidized_client_for", lambda db=None: oxidized)
    monkeypatch.setattr(node_service, "docker_client_for", lambda db=None: docker)
    monkeypatch.setattr(backup_service, "oxidized_client_for", lambda db=None: oxidized)
    monkeypatch.setattr(status_service, "oxidized_client_for", lambda db=None: oxidized)
    monkeypatch.setattr(status_service, "docker_client_for", lambda db=None: docker)
    monkeypatch.setattr(version_service, "client_for", lambda db=None: oxidized)
    monkeypatch.setattr(config_alert_service, "oxidized_client_for", lambda db=None: oxidized)
    monkeypatch.setattr(search_service, "client_for", lambda db=None: oxidized)
    monkeypatch.setattr(log_service, "client_for", lambda db=None: docker)
    monkeypatch.setattr(config_service, "docker_client_for", lambda db=None: docker)
    monkeypatch.setattr(config_service, "oxidized_client_for", lambda db=None: oxidized)
    monkeypatch.setattr(docker_api, "client_for", lambda db=None: docker)
    monkeypatch.setattr(status_router, "docker_client_for", lambda db=None: docker)
    monkeypatch.setattr(status_router, "oxidized_client_for", lambda db=None: oxidized)
    monkeypatch.setattr(system_router, "docker_client_for", lambda db=None: docker)
    monkeypatch.setattr(system_router, "oxidized_client_for", lambda db=None: oxidized)
    return SimpleNamespace(oxidized=oxidized, docker=docker)


@pytest.fixture()
def client(fake_clients):
    drop_schema()
    create_schema()
    config_dir = settings.oxidized_config_dir
    if config_dir.exists():
        _remove_tree(config_dir)
    config_dir.mkdir(parents=True, exist_ok=True)
    with TestClient(app, base_url="http://testserver") as test_client:
        yield test_client


@pytest.fixture()
def admin(client: TestClient) -> AutoClient:
    response = client.post(
        "/api/setup",
        json={"username": "admin", "password": ADMIN_PASSWORD, "language": "es"},
        headers={"Origin": ORIGIN},
    )
    assert response.status_code == 200, response.text
    csrf = response.json()["csrf_token"]
    return AutoClient(client, {"Origin": ORIGIN, "X-CSRF-Token": csrf})


@pytest.fixture()
def login_as():
    def _login(client: TestClient, username: str, password: str) -> AutoClient:
        response = client.post(
            "/api/auth/login",
            json={"username": username, "password": password},
            headers={"Origin": ORIGIN},
        )
        assert response.status_code == 200, response.text
        csrf = response.json()["csrf_token"]
        return AutoClient(client, {"Origin": ORIGIN, "X-CSRF-Token": csrf})

    return _login


def make_node(**overrides):
    payload = {
        "name": "core-sw-01",
        "address": "10.20.0.11",
        "model": "ios",
        "group_name": None,
        "input": "ssh",
        "port": 22,
        "username": "oxidized",
        "password": "device-password",
        "enable": "enable-password",
        "vars": {"remove_secret": True, "ssh_no_keepalive": True},
    }
    payload.update(overrides)
    return payload


@pytest.fixture()
def db_session():

    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_root():
    yield
    try:
        shutil.rmtree(TEST_ROOT, ignore_errors=True)
    except OSError:
        pass
