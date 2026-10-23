from __future__ import annotations

import os

import httpx
import pytest

URL = os.getenv("OXIDIZED_CONTRACT_URL", "").rstrip("/")

pytestmark = pytest.mark.skipif(not URL, reason="set OXIDIZED_CONTRACT_URL to run the real Oxidized contract test")


def test_real_oxidized_nodes_contract() -> None:
    response = httpx.get(f"{URL}/nodes.json", timeout=15)
    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, list)
    for node in payload:
        assert isinstance(node, dict)
        assert {"name", "ip", "model", "group"} <= set(node)
