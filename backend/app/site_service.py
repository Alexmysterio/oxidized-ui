from __future__ import annotations

import math
from typing import Any

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .audit import add_audit
from .errors import AppError
from .geo import (
    COORDINATE_TAG_KEYS,
    LATITUDE_TAG_KEYS,
    LEGACY_COORDINATE_TAG_KEYS,
    LONGITUDE_TAG_KEYS,
    parse_coordinates,
)
from .models import Node, SiteLocation
from .security import AuthContext
from .timeutil import to_iso, utcnow

SITE_TAG = "site"


def _finite_float(value: object) -> float | None:
    try:
        number = float(str(value).strip().replace(",", "."))
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _site_name(tags: dict[str, Any]) -> str | None:
    for key, value in tags.items():
        if str(key).casefold() == SITE_TAG:
            name = str(value).strip()
            return name or None
    return None


def _coordinates(tags: dict[str, Any]) -> tuple[float, float] | None:
    for key, value in tags.items():
        if str(key).casefold() in COORDINATE_TAG_KEYS:
            parsed = parse_coordinates(value)
            if parsed is not None:
                return parsed
    latitude = next(
        (
            number
            for key, value in tags.items()
            if str(key).casefold() in LATITUDE_TAG_KEYS
            and (number := _finite_float(value)) is not None
        ),
        None,
    )
    longitude = next(
        (
            number
            for key, value in tags.items()
            if str(key).casefold() in LONGITUDE_TAG_KEYS
            and (number := _finite_float(value)) is not None
        ),
        None,
    )
    if latitude is None or longitude is None:
        return None
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        return None
    return latitude, longitude


def migrate_site_coordinates(db: Session) -> int:
    """Move node coordinate tags to the site they belong to and remove them.

    The first node (sorted by name) that carries a valid coordinate for a site
    defines that site's position; existing site positions always win.
    """

    existing = {row.name_key for row in db.scalars(select(SiteLocation)).all()}
    changed = 0
    for node in db.scalars(select(Node).order_by(Node.name)).all():
        tags = node.tags if isinstance(node.tags, dict) else None
        if not tags:
            continue
        coordinate_keys = {
            key
            for key in tags
            if str(key).casefold() in COORDINATE_TAG_KEYS | LEGACY_COORDINATE_TAG_KEYS
        }
        if not coordinate_keys:
            continue
        site_name = _site_name(tags)
        coordinates = _coordinates(tags)
        cleaned = {key: value for key, value in tags.items() if key not in coordinate_keys}
        node.tags = cleaned or None
        node.updated_at = utcnow()
        changed += 1
        if site_name and coordinates and site_name.casefold() not in existing:
            db.add(
                SiteLocation(
                    name=site_name,
                    name_key=site_name.casefold(),
                    latitude=coordinates[0],
                    longitude=coordinates[1],
                )
            )
            existing.add(site_name.casefold())
    if changed:
        db.commit()
    return changed


def update_site(
    db: Session,
    *,
    site: str,
    coordinates: str | None,
    owner: str | None,
    contact: str | None,
    notes: str | None,
    reviewed: bool,
    actor: AuthContext,
    request: Request,
) -> dict[str, Any]:
    name = (site or "").strip()
    if not name:
        raise AppError("validation.required", params={"field": "site"})
    key = name.casefold()
    row = db.scalar(select(SiteLocation).where(SiteLocation.name_key == key))
    raw = (coordinates or "").strip()
    parsed = parse_coordinates(raw) if raw else None
    if raw and parsed is None:
        raise AppError("site.invalid_coordinates")

    def clean(value: str | None) -> str | None:
        text = (value or "").strip()
        return text or None

    owner_value = clean(owner)
    contact_value = clean(contact)
    notes_value = clean(notes)
    has_metadata = bool(owner_value or contact_value or notes_value)

    if row is None:
        if parsed is None and not has_metadata and not reviewed:
            return {
                "site": name,
                "latitude": None,
                "longitude": None,
                "owner": None,
                "contact": None,
                "notes": None,
                "last_reviewed_at": None,
            }
        row = SiteLocation(name=name, name_key=key)
        db.add(row)

    if parsed is None and not has_metadata and not reviewed and row.id is not None:
        db.delete(row)
        row = None
    elif row is not None:
        row.name = name
        row.latitude = parsed[0] if parsed else None
        row.longitude = parsed[1] if parsed else None
        row.owner = owner_value
        row.contact = contact_value
        row.notes = notes_value
        if reviewed:
            row.last_reviewed_at = utcnow()
        row.updated_by_id = actor.user_id

    add_audit(
        db,
        actor=actor,
        action_code="site.updated",
        action_params={
            "site": name,
            "latitude": parsed[0] if parsed else None,
            "longitude": parsed[1] if parsed else None,
            "owner": owner_value,
            "reviewed": reviewed,
        },
        target_type="site",
        target_id=name,
        request=request,
    )
    db.commit()
    return {
        "site": name,
        "latitude": row.latitude if row is not None else None,
        "longitude": row.longitude if row is not None else None,
        "owner": row.owner if row is not None else None,
        "contact": row.contact if row is not None else None,
        "notes": row.notes if row is not None else None,
        "last_reviewed_at": to_iso(row.last_reviewed_at) if row is not None else None,
    }
