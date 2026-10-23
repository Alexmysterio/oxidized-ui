from __future__ import annotations

import ast
import json
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1] / "app"


def test_error_codes_and_audit_actions_are_catalogued():
    error_codes = set(json.loads((APP_DIR / "data" / "error_codes.json").read_text(encoding="utf-8")))
    audit_actions = set(json.loads((APP_DIR / "data" / "audit_actions.json").read_text(encoding="utf-8")))
    used_errors: set[str] = set()
    used_audits: set[str] = set()
    for path in APP_DIR.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "AppError"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                used_errors.add(node.args[0].value)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "add_audit":
                for keyword in node.keywords:
                    if (
                        keyword.arg == "action_code"
                        and isinstance(keyword.value, ast.Constant)
                        and isinstance(keyword.value.value, str)
                    ):
                        used_audits.add(keyword.value.value)
    assert used_errors
    assert used_audits
    assert used_errors <= error_codes, f"Missing error translations/catalog entries: {used_errors - error_codes}"
    assert used_audits <= audit_actions, f"Missing audit translations/catalog entries: {used_audits - audit_actions}"


def test_catalog_exposes_labels_for_every_ui_field():
    from app.catalog import catalog

    body = catalog()
    paths = [item["path"] for item in body["fields"]]
    assert len(paths) == len(set(paths))
    for item in body["fields"]:
        assert item["label_code"].startswith("oxidized.fields.")
        assert item["help_code"].startswith("oxidized.fields.")
    for item in body["vars"]:
        assert item["label_code"].startswith("oxidized.vars.")
    for hook in body["hook_types"].values():
        assert hook["label_code"].startswith("oxidized.hooks.")
        for item in hook["fields"]:
            assert item["label_code"].startswith("oxidized.fields.")


def test_default_config_is_renderable_and_roundtrips():
    from app.config_model import default_config, editable_yaml, load_editable_yaml, validate_config

    config = default_config()
    normalized = validate_config(config)
    yaml_text = editable_yaml(normalized)
    parsed = load_editable_yaml(yaml_text)
    assert parsed["output"]["default"] == "git"
    assert parsed["interval"] == 3600
