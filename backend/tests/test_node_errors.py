from __future__ import annotations

from types import SimpleNamespace

from app import node_error_service


def test_classify_auth_failure_with_user() -> None:
    code, params = node_error_service._classify(
        "Net::SSH::AuthenticationFailed",
        "Authentication failed for user backup@10.255.3.1",
    )
    assert code == "node.auth_failed"
    assert params == {"user": "backup"}


def test_latest_error_matches_job_and_ignores_other_nodes(monkeypatch) -> None:
    lines = [
        SimpleNamespace(
            timestamp="2026-10-22T18:15:51Z",
            text="W [16:Job 'N4-Panata'] Oxidized::Node -- 10.255.4.1 raised Net::SSH::AuthenticationFailed "
            'with msg "Authentication failed for user backup@10.255.4.1"',
        ),
        SimpleNamespace(
            timestamp="2026-10-22T18:16:00Z",
            text="W [16:Job 'N1-Alex'] Oxidized::Node -- 10.255.1.1 raised Net::SSH::HostKeyUnknown "
            'with msg "fingerprint is unknown"',
        ),
    ]
    monkeypatch.setattr(
        node_error_service,
        "client_for",
        lambda db: SimpleNamespace(log_snapshot=lambda **kwargs: lines),
    )
    result = node_error_service.latest_error(SimpleNamespace(), SimpleNamespace(name="N4-Panata", address="10.255.4.1"))
    assert result is not None
    assert result["code"] == "node.auth_failed"
    assert result["params"] == {"user": "backup"}
    assert result["at"] == "2026-10-22T18:15:51.000Z"
