from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .errors import AppError
from .models import MaintenanceWindow, Node, User
from .security import AuthContext


def scoped_groups(ctx: AuthContext) -> set[str] | None:
    if ctx.role == "admin":
        return None
    return set(ctx.scope_groups) if ctx.scope_groups else None


def require_group(ctx: AuthContext, group_name: str | None) -> None:
    scope = scoped_groups(ctx)
    if scope is None:
        return
    if not group_name or group_name not in scope:
        raise AppError("auth.forbidden")


def node_ids_in_scope(db: Session, ctx: AuthContext) -> set[int] | None:
    scope = scoped_groups(ctx)
    if scope is None:
        return None
    return {node.id for node in db.scalars(select(Node)).all() if node.group_name in scope}


def require_unscoped(ctx: AuthContext) -> None:
    if ctx.scope_groups is not None:
        raise AppError("auth.forbidden")


def ensure_job_visible(db: Session, ctx: AuthContext, job) -> None:  # noqa: ANN001
    scope = scoped_groups(ctx)
    if scope is None:
        return
    allowed = node_ids_in_scope(db, ctx) or set()
    if job.node_id in allowed:
        return
    payload = job.payload if isinstance(job.payload, dict) else {}
    for value in payload.get("node_ids", []) or []:
        try:
            if int(value) in allowed:
                return
        except (TypeError, ValueError):
            continue
    raise AppError("job.not_found", params={"job_id": job.id})


def ensure_schedule_visible(db: Session, ctx: AuthContext, schedule) -> None:  # noqa: ANN001
    scope = scoped_groups(ctx)
    if scope is None:
        return
    if not schedule.group_name or schedule.group_name not in scope:
        raise AppError("app.not_found", params={"id": schedule.id})


def ensure_priority_rule_visible(ctx: AuthContext, rule) -> None:  # noqa: ANN001
    scope = scoped_groups(ctx)
    if scope is None:
        return
    if rule.scope_type != "group" or rule.scope_key not in scope:
        raise AppError("app.not_found", params={"id": rule.id})


def ensure_compliance_template_visible(ctx: AuthContext, template) -> None:  # noqa: ANN001
    scope = scoped_groups(ctx)
    if scope is None:
        return
    if template.scope_type != "group" or template.scope_value not in scope:
        raise AppError("app.not_found", params={"id": template.id})


def node_visible(ctx: AuthContext, node: Node) -> bool:
    scope = scoped_groups(ctx)
    return scope is None or (node.group_name is not None and node.group_name in scope)


def scoped_node(db: Session, ctx: AuthContext, node_id: int) -> Node:
    from .node_service import get_node

    node = get_node(db, node_id)
    if not node_visible(ctx, node):
        raise AppError("node.not_found", params={"node_id": node_id})
    return node


def visible_groups(ctx: AuthContext) -> list[str] | None:
    scope = scoped_groups(ctx)
    return sorted(scope) if scope is not None else None


def validate_scope_groups(db: Session, groups: list[str] | None) -> list[str] | None:
    if groups is None:
        return None
    cleaned = [group.strip() for group in dict.fromkeys(groups) if group and group.strip()]
    if not cleaned:
        return None
    known = {node.group_name for node in db.scalars(select(Node)).all() if node.group_name}
    unknown = sorted(group for group in cleaned if group not in known)
    if unknown:
        raise AppError("group.not_found", params={"name": unknown[0]})
    return cleaned


def context_scope(user: User) -> list[str] | None:
    scope = user.scope_groups
    if not scope:
        return None
    return [str(group) for group in scope]


def favorite_ids(db: Session, user_id: int) -> set[int]:
    from .models import UserPreference

    row = db.get(UserPreference, user_id)
    if row is None:
        return set()
    return {int(value) for value in (row.favorites or [])}


def ensure_scope_covers_windows(db: Session, ctx: AuthContext, window: MaintenanceWindow) -> None:
    scope = scoped_groups(ctx)
    if scope is None:
        return
    if window.scope_type == "global":
        raise AppError("auth.forbidden")
    if window.scope_type == "group" and window.group_name not in scope:
        raise AppError("auth.forbidden")
    if window.scope_type == "node":
        node = db.get(Node, window.node_id) if window.node_id else None
        if node is None or node.group_name not in scope:
            raise AppError("auth.forbidden")
