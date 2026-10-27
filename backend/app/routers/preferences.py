from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..auth_deps import get_auth_context
from ..db import get_db
from ..errors import AppError
from ..models import UserPreference
from ..schemas import PreferenceUpdate
from ..security import AuthContext
from ..timeutil import utcnow

router = APIRouter(prefix="/me", tags=["preferences"])

MAX_FAVORITES = 500
MAX_FILTERS = 50
MAX_FILTER_NAME = 60
MAX_FILTER_QUERY = 1000


def _row(db: Session, user_id: int) -> UserPreference:
    row = db.get(UserPreference, user_id)
    if row is None:
        row = UserPreference(user_id=user_id, favorites=[], saved_filters=[])
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def _public(row: UserPreference) -> dict:
    return {
        "favorites": list(row.favorites or []),
        "saved_filters": list(row.saved_filters or []),
    }


@router.get("/preferences")
def read_preferences(db: Session = Depends(get_db), context: AuthContext = Depends(get_auth_context)):
    return _public(_row(db, context.user_id))


@router.patch("/preferences")
def update_preferences(
    payload: PreferenceUpdate,
    db: Session = Depends(get_db),
    context: AuthContext = Depends(get_auth_context),
):
    row = _row(db, context.user_id)
    data = payload.model_dump(exclude_unset=True)
    if "favorites" in data and data["favorites"] is not None:
        favorites = [int(value) for value in data["favorites"]]
        if len(favorites) > MAX_FAVORITES:
            raise AppError("validation.too_long", params={"field": "favorites"})
        row.favorites = list(dict.fromkeys(favorites))
    if "saved_filters" in data and data["saved_filters"] is not None:
        filters = data["saved_filters"]
        if len(filters) > MAX_FILTERS:
            raise AppError("validation.too_long", params={"field": "saved_filters"})
        cleaned = []
        for item in filters:
            name = str(item.get("name") or "").strip()
            query = str(item.get("query") or "").strip()
            if not name or not query:
                raise AppError("validation.required", params={"field": "saved_filters"})
            cleaned.append({"name": name[:MAX_FILTER_NAME], "query": query[:MAX_FILTER_QUERY]})
        row.saved_filters = cleaned
    row.updated_at = utcnow()
    db.commit()
    db.refresh(row)
    return _public(row)
