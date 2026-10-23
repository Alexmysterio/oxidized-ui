from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

from .errors import AppError
from .settings import settings

REGEXP_MARKER = "$rubyRegexp"
REGEXP_TAG = "!ruby/regexp"
RUBY_REGEXP_RE = re.compile(r"^/(.*)/([imxouesn]*)$", re.DOTALL)

MAP_SECTIONS = ("group_map", "model_map")


@dataclass(frozen=True, slots=True)
class RubyRegexp:
    value: str

    def __str__(self) -> str:
        return self.value


def _construct_regexp(loader, node):  # noqa: ANN001, ANN202
    value = loader.construct_scalar(node)
    if not isinstance(value, str) or not RUBY_REGEXP_RE.match(value):
        raise ValueError("invalid !ruby/regexp scalar")
    return RubyRegexp(value)


def _represent_regexp(representer, data: RubyRegexp):  # noqa: ANN001, ANN202
    return representer.represent_scalar(REGEXP_TAG, data.value)


def _new_yaml() -> YAML:
    yaml = YAML(typ="rt")
    yaml.width = 4096
    yaml.indent(mapping=2, sequence=4, offset=2)
    yaml.allow_duplicate_keys = False
    yaml.representer.add_representer(RubyRegexp, _represent_regexp)
    yaml.constructor.add_constructor(REGEXP_TAG, _construct_regexp)
    return yaml


def load_yaml(text: str) -> Any:
    if len(text.encode("utf-8")) > settings.max_config_bytes:
        raise AppError("config.content_too_large")
    yaml = _new_yaml()
    try:
        documents = list(yaml.load_all(text))
    except (YAMLError, ValueError, TypeError) as exc:
        raise AppError(
            "config.invalid_yaml",
            params={"reason": str(exc)[:300]},
        ) from exc
    if len(documents) != 1:
        raise AppError("config.invalid_yaml", params={"reason": "multiple_documents"})
    data = documents[0]
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise AppError("config.invalid_yaml", params={"reason": "root_not_mapping"})
    return _to_jsonable(data, path="", depth=0)


def _to_jsonable(value: Any, *, path: str, depth: int) -> Any:
    if depth > 30:
        raise AppError("config.validation_failed", params={"reason": "too_deep", "path": path})
    if isinstance(value, RubyRegexp):
        return {REGEXP_MARKER: value.value}
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            if isinstance(key, RubyRegexp):
                key = f"__regexp__:{key.value}"
            elif not isinstance(key, str):
                key = str(key)
            if key in result:
                raise AppError("config.validation_failed", params={"reason": "duplicate_key", "path": child_path})
            result[key] = _to_jsonable(item, path=child_path, depth=depth + 1)
        return result
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(item, path=f"{path}[]", depth=depth + 1) for item in value]
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise AppError("config.validation_failed", params={"reason": "unsupported_value", "path": path})


def _maps_to_lists(data: dict[str, Any]) -> dict[str, Any]:
    for section in MAP_SECTIONS:
        mapping = data.get(section)
        if mapping is None:
            data[section] = []
            continue
        if isinstance(mapping, list):
            continue
        if not isinstance(mapping, dict):
            raise AppError("config.validation_failed", params={"reason": "map_not_mapping", "path": section})
        entries: list[dict[str, Any]] = []
        for key, target in mapping.items():
            is_regex = False
            if isinstance(key, str) and key.startswith("__regexp__:"):
                key = key[len("__regexp__:") :]
                is_regex = True
            if isinstance(key, dict) and REGEXP_MARKER in key:
                key = key[REGEXP_MARKER]
                is_regex = True
            if not isinstance(key, str) or not isinstance(target, str):
                raise AppError("config.validation_failed", params={"reason": "invalid_map_entry", "path": section})
            if is_regex and not RUBY_REGEXP_RE.match(key):
                raise AppError("config.validation_failed", params={"reason": "invalid_regexp", "path": section})
            entries.append({"match": key, "is_regex": is_regex, "target": target})
        data[section] = entries
    return data


def _regexp_to_marker(value: str) -> RubyRegexp:
    if not RUBY_REGEXP_RE.match(value):
        raise AppError("config.validation_failed", params={"reason": "invalid_regexp"})
    return RubyRegexp(value)


def _lists_to_maps(data: dict[str, Any]) -> dict[str, Any]:
    for section in MAP_SECTIONS:
        entries = data.get(section, [])
        if entries is None:
            entries = []
        if isinstance(entries, dict):
            entries = [{"match": key, "is_regex": False, "target": target} for key, target in entries.items()]
        if not isinstance(entries, list):
            raise AppError("config.validation_failed", params={"reason": "map_not_list", "path": section})
        mapping: dict[Any, str] = {}
        for entry in entries:
            if not isinstance(entry, dict):
                raise AppError("config.validation_failed", params={"reason": "invalid_map_entry", "path": section})
            match = entry.get("match")
            target = entry.get("target")
            is_regex = bool(entry.get("is_regex", False))
            if not isinstance(match, str) or not isinstance(target, str):
                raise AppError("config.validation_failed", params={"reason": "invalid_map_entry", "path": section})
            key: Any = _regexp_to_marker(match) if is_regex else match
            mapping[key] = target
        data[section] = mapping
    return data


def _replace_markers(value: Any) -> Any:
    if isinstance(value, dict):
        if set(value.keys()) == {REGEXP_MARKER}:
            marker = value[REGEXP_MARKER]
            if not isinstance(marker, str):
                raise AppError("config.validation_failed", params={"reason": "invalid_regexp"})
            return _regexp_to_marker(marker)
        return {key: _replace_markers(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_replace_markers(item) for item in value]
    return value


def dump_yaml(data: dict[str, Any], *, include_tags: bool = True) -> str:
    """Serialize canonical config to YAML.

    Callers pass a fully rendered config with group_map/model_map already in
    list form and prompt/tag values as strings or marker dicts.
    """
    import io

    prepared = dict(data)
    _lists_to_maps(prepared)
    if isinstance(prepared.get("prompt"), str):
        prompt = prepared["prompt"]
        if not RUBY_REGEXP_RE.match(prompt):
            prompt = f"/{prompt}/"
        prepared["prompt"] = _regexp_to_marker(prompt)
    prepared = _replace_markers(prepared)
    if not include_tags:
        # Redaction previews still need the same structure but should not carry
        # Ruby objects; convert backed to strings with the tag prefix.
        prepared = _stringify_tags(prepared)
    yaml = _new_yaml()
    stream = io.StringIO()
    try:
        yaml.dump(prepared, stream)
    except (YAMLError, ValueError, TypeError) as exc:
        raise AppError("config.invalid_yaml", params={"reason": str(exc)[:300]}) from exc
    return stream.getvalue()


def _stringify_tags(value: Any) -> Any:
    if isinstance(value, RubyRegexp):
        return str(value)
    if isinstance(value, dict):
        return {(_stringify_tags(k) if not isinstance(k, str) else k): _stringify_tags(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_stringify_tags(item) for item in value]
    return value


def parse_config_yaml(text: str) -> dict[str, Any]:
    data = load_yaml(text)
    return _maps_to_lists(data)
