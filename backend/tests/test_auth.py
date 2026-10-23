from __future__ import annotations

import pyotp
from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import ADMIN_PASSWORD, ORIGIN


def test_meta_and_health(client: TestClient):
    meta = client.get("/api/meta")
    assert meta.status_code == 200
    assert meta.json()["setup_required"] is True
    assert meta.json()["available_languages"] == ["es", "en"]
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["database"] == "ok"


def test_setup_session_cookie_and_duplicate_setup(client: TestClient):
    response = client.post(
        "/api/setup",
        json={"username": "admin", "password": ADMIN_PASSWORD, "language": "es"},
        headers={"Origin": ORIGIN},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["user"]["role"] == "admin"
    cookie = response.headers.get("set-cookie", "")
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie
    assert client.get("/api/meta").json()["setup_required"] is False
    second = client.post(
        "/api/setup",
        json={"username": "other", "password": ADMIN_PASSWORD, "language": "es"},
        headers={"Origin": ORIGIN},
    )
    assert second.status_code == 403
    assert second.json()["error"]["code"] == "setup.completed"


def test_login_logout_and_csrf(client: TestClient, admin):
    session = admin.get("/api/auth/session")
    assert session.status_code == 200
    assert session.json()["user"]["username"] == "admin"
    assert session.json()["csrf_token"] == admin.headers["X-CSRF-Token"]

    no_csrf = client.post("/api/oxidized/reload", headers={"Origin": ORIGIN})
    assert no_csrf.status_code == 403
    assert no_csrf.json()["error"]["code"] == "auth.csrf_failed"

    no_origin = client.post(
        "/api/oxidized/reload",
        headers={"X-CSRF-Token": admin.headers["X-CSRF-Token"]},
    )
    assert no_origin.status_code == 403
    assert no_origin.json()["error"]["code"] == "auth.origin_rejected"

    logout = admin.post("/api/auth/logout")
    assert logout.status_code == 204
    assert client.get("/api/auth/session").status_code == 401


def test_login_rate_limit(client: TestClient, admin):
    client.post("/api/auth/logout", headers=admin.headers)
    for _ in range(5):
        response = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "wrong-password"},
            headers={"Origin": ORIGIN},
        )
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "auth.invalid_credentials"
    blocked = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": ADMIN_PASSWORD},
        headers={"Origin": ORIGIN},
    )
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "auth.too_many_attempts"
    assert "Retry-After" in blocked.headers


def test_invalid_password_and_username_are_stable(client: TestClient):
    bad_password = client.post(
        "/api/setup",
        json={"username": "admin", "password": "short", "language": "es"},
        headers={"Origin": ORIGIN},
    )
    assert bad_password.status_code == 422
    assert bad_password.json()["error"]["code"] == "auth.weak_password"
    bad_username = client.post(
        "/api/setup",
        json={"username": "a b", "password": ADMIN_PASSWORD, "language": "es"},
        headers={"Origin": ORIGIN},
    )
    assert bad_username.status_code == 422
    assert bad_username.json()["error"]["code"] == "validation.invalid_format"


def test_password_change_rotates_session_and_revokes_old(client: TestClient, admin):
    new_password = "AnotherCorrectHorse9!"
    response = admin.post(
        "/api/me/password",
        json={"current_password": ADMIN_PASSWORD, "new_password": new_password},
    )
    assert response.status_code == 200, response.text
    new_csrf = response.json()["csrf_token"]
    assert new_csrf != admin.headers["X-CSRF-Token"]
    admin.headers["X-CSRF-Token"] = new_csrf
    assert admin.get("/api/auth/session").status_code == 200

    logout = admin.post("/api/auth/logout")
    assert logout.status_code == 204
    old_login = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": ADMIN_PASSWORD},
        headers={"Origin": ORIGIN},
    )
    assert old_login.status_code == 401
    new_login = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": new_password},
        headers={"Origin": ORIGIN},
    )
    assert new_login.status_code == 200


def test_list_and_revoke_other_session(client: TestClient, admin):
    second = TestClient(app)
    login = second.post(
        "/api/auth/login",
        json={"username": "admin", "password": ADMIN_PASSWORD},
        headers={"Origin": ORIGIN},
    )
    assert login.status_code == 200, login.text

    listed = admin.get("/api/auth/sessions")
    assert listed.status_code == 200
    sessions = listed.json()["sessions"]
    assert sum(1 for item in sessions if item["current"]) == 1
    other = next(item for item in sessions if not item["current"])
    deleted = admin.delete(f"/api/auth/sessions/{other['id']}")
    assert deleted.status_code == 204
    assert second.get("/api/auth/session").status_code == 401


def test_mfa_setup_challenge_and_recovery_code(client: TestClient, admin):
    status = admin.get("/api/auth/mfa")
    assert status.status_code == 200
    assert status.json()["enabled"] is False

    setup = admin.post("/api/auth/mfa/setup")
    assert setup.status_code == 200, setup.text
    secret = setup.json()["secret"]
    code = pyotp.TOTP(secret).now()
    enabled = admin.post("/api/auth/mfa/enable", json={"code": code})
    assert enabled.status_code == 200, enabled.text
    recovery = enabled.json()["recovery_codes"]
    assert len(recovery) == 10

    assert admin.get("/api/auth/mfa").json()["enabled"] is True

    assert admin.post("/api/auth/logout").status_code == 204
    first = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": ADMIN_PASSWORD},
        headers={"Origin": ORIGIN},
    )
    assert first.status_code == 200, first.text
    assert first.json()["mfa_required"] is True
    assert "set-cookie" not in first.headers

    challenge = client.post(
        "/api/auth/login/mfa",
        json={"challenge_token": first.json()["challenge_token"], "code": pyotp.TOTP(secret).now()},
        headers={"Origin": ORIGIN},
    )
    assert challenge.status_code == 200, challenge.text
    session = client.get("/api/auth/session")
    assert session.status_code == 200
    admin.headers["X-CSRF-Token"] = session.json()["csrf_token"]

    # A recovery code is single-use and can complete a later challenge.
    assert client.post("/api/auth/logout", headers=admin.headers).status_code == 204
    second = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": ADMIN_PASSWORD},
        headers={"Origin": ORIGIN},
    )
    recovery_login = client.post(
        "/api/auth/login/mfa",
        json={"challenge_token": second.json()["challenge_token"], "code": recovery[0]},
        headers={"Origin": ORIGIN},
    )
    assert recovery_login.status_code == 200, recovery_login.text


def test_password_policy_and_reuse(admin):
    policy = admin.patch("/api/system/settings", json={"password_min_length": 20, "password_history_count": 5})
    assert policy.status_code == 200, policy.text
    weak = admin.post(
        "/api/me/password",
        json={"current_password": ADMIN_PASSWORD, "new_password": "Short9!pass"},
    )
    assert weak.status_code == 422
    assert weak.json()["error"]["code"] == "auth.weak_password"

    new_password = "AnotherCorrectHorse9!"
    changed = admin.post(
        "/api/me/password",
        json={"current_password": ADMIN_PASSWORD, "new_password": new_password},
    )
    assert changed.status_code == 200, changed.text
    admin.headers["X-CSRF-Token"] = changed.json()["csrf_token"]

    reused = admin.post(
        "/api/me/password",
        json={"current_password": new_password, "new_password": ADMIN_PASSWORD},
    )
    assert reused.status_code == 422
    assert reused.json()["error"]["code"] == "auth.password_reused"


def test_invalid_allowlist_is_rejected(admin):
    response = admin.patch("/api/system/settings", json={"ip_allowlist": "not-a-cidr"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "system.invalid_setting"


def test_allowlist_rejects_unlisted_client(client, admin):
    response = admin.patch("/api/system/settings", json={"ip_allowlist": "10.0.0.0/8"})
    assert response.status_code == 200, response.text
    blocked = client.get("/api/meta")
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "auth.ip_not_allowed"


def test_metrics_endpoint(client: TestClient):
    response = client.get("/api/metrics")
    assert response.status_code == 200
    assert "oxidized_ui_backups_total" in response.text
