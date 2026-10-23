from __future__ import annotations

import difflib
import re
from typing import Any


def _segments(old: str | None, new: str | None) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    token = re.compile(r"\w+|\s+|[^\w\s]+")
    old_tokens = token.findall(old or "")
    new_tokens = token.findall(new or "")
    matcher = difflib.SequenceMatcher(a=old_tokens, b=new_tokens, autojunk=False)
    left: list[dict[str, object]] = []
    right: list[dict[str, object]] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        changed = tag != "equal"
        if i1 != i2:
            left.append({"text": "".join(old_tokens[i1:i2]), "changed": changed})
        if j1 != j2:
            right.append({"text": "".join(new_tokens[j1:j2]), "changed": changed})
    return left, right


def build_diff(old: str, new: str) -> dict[str, Any]:
    old_lines = old.splitlines()
    new_lines = new.splitlines()
    matcher = difflib.SequenceMatcher(a=old_lines, b=new_lines, autojunk=False)
    rows: list[dict[str, Any]] = []
    additions = 0
    deletions = 0
    left_no = 0
    right_no = 0

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for old_line, new_line in zip(old_lines[i1:i2], new_lines[j1:j2], strict=False):
                left_no += 1
                right_no += 1
                rows.append(
                    {
                        "left": {"line": left_no, "text": old_line},
                        "right": {"line": right_no, "text": new_line},
                        "type": "same",
                    }
                )
            continue
        if tag == "delete":
            for line in old_lines[i1:i2]:
                left_no += 1
                deletions += 1
                rows.append(
                    {
                        "left": {"line": left_no, "text": line},
                        "right": None,
                        "type": "removed",
                    }
                )
            continue
        if tag == "insert":
            for line in new_lines[j1:j2]:
                right_no += 1
                additions += 1
                rows.append(
                    {
                        "left": None,
                        "right": {"line": right_no, "text": line},
                        "type": "added",
                    }
                )
            continue

        old_chunk = old_lines[i1:i2]
        new_chunk = new_lines[j1:j2]
        for index in range(max(len(old_chunk), len(new_chunk))):
            left = old_chunk[index] if index < len(old_chunk) else None
            right = new_chunk[index] if index < len(new_chunk) else None
            if left is not None:
                left_no += 1
                deletions += 1
            if right is not None:
                right_no += 1
                additions += 1
            left_segments, right_segments = _segments(left, right)
            rows.append(
                {
                    "left": (
                        {"line": left_no, "text": left, "segments": left_segments}
                        if left is not None
                        else None
                    ),
                    "right": (
                        {"line": right_no, "text": right, "segments": right_segments}
                        if right is not None
                        else None
                    ),
                    "type": "changed"
                    if left is not None and right is not None
                    else ("removed" if left is not None else "added"),
                }
            )

    unified = "\n".join(
        difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile="applied",
            tofile="draft",
            lineterm="",
            n=3,
        )
    )
    if unified:
        unified += "\n"
    return {
        "unified": unified,
        "side_by_side": rows,
        "stats": {"additions": additions, "deletions": deletions},
    }


def diff_texts(old: str, new: str, *, from_name: str = "from", to_name: str = "to") -> dict[str, Any]:
    diff = build_diff(old, new)
    diff["from_name"] = from_name
    diff["to_name"] = to_name
    return diff
