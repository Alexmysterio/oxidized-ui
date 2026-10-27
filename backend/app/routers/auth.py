from __future__ import annotations

from fastapi import APIRouter, Depends, File, Request, Response, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy.orm import Session

from .. import oidc_service
from ..api_token_service import create_token, list_tokens, revoke_token
from ..audit import add_audit
from ..auth_deps import get_auth_context, require_capability
from ..auth_service import (
    change_password,
    create_session,
    list_user_sessions,
    login,
    revoke_session,
    revoke_user_session,
    setup_admin,
    update_profile,
)
from ..avatar_service import avatar_path, delete_avatar, save_avatar
from ..db import get_db
from ..errors import AppError
from ..image_service import media_type as image_media_type
from ..mfa_service import (
    MfaRequired,
    begin_setup,
    challenge_public,
    generate_recovery_codes,
    remaining_recovery_codes,
    verify_challenge,
    verify_totp,
)
from ..mfa_service import (
    disable as disable_mfa,
)
from ..mfa_service import (
    is_enabled as mfa_is_enabled,
)
from ..models import User
from ..schemas import (
    ApiTokenCreate,
    LoginRequest,
    MfaCodeRequest,
    MfaDisableRequest,
    MfaLoginRequest,
    PasswordChangeRequest,
    ProfileUpdate,
    SetupRequest,
)
from ..security import AuthContext, cookie_max_age, verify_password
from ..serializers import session_public, user_public
from ..settings import settings
from ..timeutil import utcnow

router = APIRouter(tags=["auth"])


def _set_cookie(response: Response, raw_token: str) -> None:
    response.set_cookie(
        key=settings.session_cookie_name,
        value=raw_token,
        max_age=cookie_max_age(),
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )


def _clear_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.session_cookie_name,
        path="/",
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite="lax",
    )


def _session_payload(user, context: AuthContext) -> dict:
    return {
        "user": user_public(user, include_state=False),
        "csrf_token": context.csrf_token,
        "capabilities": context.capabilities,
    }


@router.post("/setup")
def setup(
    payload: SetupRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    user, context, raw = setup_admin(
        db,
        request,
        username=payload.username,
        password=payload.password,
        language=payload.language,
        theme=payload.theme,
    )
    _set_cookie(response, raw)
    return _session_payload(user, context)


@router.post("/auth/login")
def login_route(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    try:
        user, context, raw = login(db, request, payload.username, payload.password)
    except MfaRequired as challenge:
        return challenge_public(challenge)
    _set_cookie(response, raw)
    return _session_payload(user, context)


@router.post("/auth/login/mfa")
def login_mfa_route(
    payload: MfaLoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    user = verify_challenge(db, payload.challenge_token, payload.code)
    raw, context = create_session(db, user, request)
    _set_cookie(response, raw)
    add_audit(
        db,
        actor=context,
        action_code="auth.login_mfa_succeeded",
        target_type="user",
        target_id=user.id,
        request=request,
    )
    db.commit()
    return _session_payload(user, context)


@router.post("/auth/logout", status_code=204)
def logout_route(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    context: AuthContext = Depends(get_auth_context),
):
    revoke_session(db, context.session_id)
    add_audit(
        db,
        actor=context,
        action_code="auth.logout",
        target_type="user",
        target_id=context.user_id,
        request=request,
    )
    db.commit()
    _clear_cookie(response)
    response.status_code = 204
    return response




@router.get("/auth/oidc/login")
def oidc_login():
    try:
        url, state = oidc_service.start_url()
    except AppError:
        return RedirectResponse("/login?oidc_error=1", status_code=303)
    except Exception:  # noqa: BLE001 - provider/network failures must not leak internals
        return RedirectResponse("/login?oidc_error=1", status_code=303)
    response = RedirectResponse(url, status_code=303)
    response.set_cookie(
        key=oidc_service.OIDC_STATE_COOKIE,
        value=state,
        max_age=600,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/api/auth/oidc",
    )
    return response


def _oidc_failure(reason: str = "1") -> RedirectResponse:
    response = RedirectResponse(f"/login?oidc_error={reason}", status_code=303)
    response.delete_cookie(
        key=oidc_service.OIDC_STATE_COOKIE,
        path="/api/auth/oidc",
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite="lax",
    )
    return response


@router.get("/auth/oidc/callback")
def oidc_callback(
    code: str,
    state: str,
    request: Request,
    db: Session = Depends(get_db),
):
    try:
        user, raw, context = oidc_service.complete(db, code, state, request)
    except MfaRequired as challenge:
        response = RedirectResponse(f"/login?mfa_challenge={challenge.token}", status_code=303)
        response.delete_cookie(
            key=oidc_service.OIDC_STATE_COOKIE,
            path="/api/auth/oidc",
            secure=settings.session_cookie_secure,
            httponly=True,
            samesite="lax",
        )
        return response
    except AppError as exc:
        return _oidc_failure("mfa" if exc.code == "auth.mfa_oidc_unsupported" else "1")
    except Exception:  # noqa: BLE001 - provider/network failures must not leak internals
        return _oidc_failure()
    add_audit(
        db,
        actor=context,
        action_code="auth.oidc_login_succeeded",
        target_type="user",
        target_id=user.id,
        request=request,
    )
    db.commit()
    response = RedirectResponse("/", status_code=303)
    _set_cookie(response, raw)
    response.delete_cookie(
        key=oidc_service.OIDC_STATE_COOKIE,
        path="/api/auth/oidc",
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite="lax",
    )
    return response


@router.get("/auth/session")
def session_route(
    db: Session = Depends(get_db),
    context: AuthContext = Depends(get_auth_context),
):
    from ..models import User

    user = db.get(User, context.user_id)
    if user is None:
        raise AppError("auth.unauthenticated")
    return _session_payload(user, context)


@router.get("/auth/sessions")
def sessions_route(
    db: Session = Depends(get_db),
    context: AuthContext = Depends(get_auth_context),
):
    rows = list_user_sessions(db, context.user_id)
    return {"sessions": [session_public(row, current_id=context.session_id) for row in rows]}


@router.delete("/auth/sessions/{session_id}", status_code=204)
def revoke_session_route(
    session_id: int,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    context: AuthContext = Depends(get_auth_context),
):
    row = revoke_user_session(db, context.user_id, session_id)
    add_audit(
        db,
        actor=context,
        action_code="auth.session_revoked",
        action_params={"session_id": row.id, "current": row.id == context.session_id},
        target_type="user",
        target_id=context.user_id,
        request=request,
    )
    db.commit()
    if row.id == context.session_id:
        _clear_cookie(response)
    response.status_code = 204
    return response


@router.get("/auth/mfa")
def mfa_status(
    db: Session = Depends(get_db),
    context: AuthContext = Depends(require_capability("me.write")),
):
    user = db.get(User, context.user_id)
    if user is None:
        raise AppError("auth.unauthenticated")
    enabled = mfa_is_enabled(user)
    return {
        "enabled": enabled,
        "pending": bool(user.mfa_secret_ciphertext and not enabled),
        "recovery_codes_remaining": remaining_recovery_codes(db, user) if enabled else 0,
    }


@router.post("/auth/mfa/setup")
def mfa_setup(
    request: Request,
    db: Session = Depends(get_db),
    context: AuthContext = Depends(require_capability("me.write")),
):
    user = db.get(User, context.user_id)
    if user is None:
        raise AppError("auth.unauthenticated")
    secret, uri = begin_setup(user)
    db.commit()
    add_audit(
        db,
        actor=context,
        action_code="auth.mfa_challenge_issued",
        action_params={"phase": "setup"},
        target_type="user",
        target_id=user.id,
        request=request,
    )
    db.commit()
    return {"secret": secret, "otpauth_uri": uri}


@router.post("/auth/mfa/enable")
def mfa_enable(
    payload: MfaCodeRequest,
    request: Request,
    db: Session = Depends(get_db),
    context: AuthContext = Depends(require_capability("me.write")),
):
    user = db.get(User, context.user_id)
    if user is None:
        raise AppError("auth.unauthenticated")
    if not user.mfa_secret_ciphertext:
        raise AppError("auth.mfa_not_configured")
    if mfa_is_enabled(user):
        raise AppError("auth.mfa_already_enabled")
    if not verify_totp(user, payload.code):
        raise AppError("auth.invalid_mfa_code")
    user.mfa_enabled_at = utcnow()
    codes = generate_recovery_codes(db, user)
    db.commit()
    add_audit(
        db,
        actor=context,
        action_code="auth.mfa_enabled",
        action_params={"recovery_codes": len(codes)},
        target_type="user",
        target_id=user.id,
        request=request,
    )
    db.commit()
    return {"recovery_codes": codes}


@router.post("/auth/mfa/disable", status_code=204)
def mfa_disable(
    payload: MfaDisableRequest,
    request: Request,
    db: Session = Depends(get_db),
    context: AuthContext = Depends(require_capability("me.write")),
):
    user = db.get(User, context.user_id)
    if user is None:
        raise AppError("auth.unauthenticated")
    if not mfa_is_enabled(user):
        raise AppError("auth.mfa_not_configured")
    if not verify_password(payload.password, user.password_hash):
        raise AppError("auth.invalid_current_password")
    if not verify_totp(user, payload.code):
        raise AppError("auth.invalid_mfa_code")
    disable_mfa(db, user)
    add_audit(
        db,
        actor=context,
        action_code="auth.mfa_disabled",
        target_type="user",
        target_id=user.id,
        request=request,
    )
    db.commit()
    return Response(status_code=204)




@router.get("/auth/tokens")
def list_api_tokens(db: Session = Depends(get_db), context: AuthContext = Depends(get_auth_context)):
    return {"items": list_tokens(db, context.user_id)}


@router.post("/auth/tokens", status_code=201)
def create_api_token(
    payload: ApiTokenCreate,
    request: Request,
    db: Session = Depends(get_db),
    context: AuthContext = Depends(get_auth_context),
):
    user = db.get(User, context.user_id)
    if user is None:
        raise AppError("auth.unauthenticated")
    raw, row = create_token(db, user, name=payload.name, role=payload.role, days=payload.days)
    add_audit(
        db,
        actor=context,
        action_code="auth.token_created",
        action_params={"name": payload.name, "role": payload.role, "token_id": row["id"]},
        target_type="user",
        target_id=context.user_id,
        request=request,
    )
    db.commit()
    return {"token": raw, "item": row}


@router.delete("/auth/tokens/{token_id}", status_code=204)
def revoke_api_token(
    token_id: int,
    request: Request,
    db: Session = Depends(get_db),
    context: AuthContext = Depends(get_auth_context),
):
    revoke_token(db, context.user_id, token_id)
    add_audit(
        db,
        actor=context,
        action_code="auth.token_revoked",
        action_params={"token_id": token_id},
        target_type="user",
        target_id=context.user_id,
        request=request,
    )
    db.commit()
    return Response(status_code=204)


@router.patch("/me")
def patch_me(
    payload: ProfileUpdate,
    db: Session = Depends(get_db),
    context: AuthContext = Depends(get_auth_context),
):
    user = update_profile(
        db,
        context,
        changes=payload.model_dump(exclude_unset=True),
    )
    return {
        "user": user_public(user, include_state=False),
        "capabilities": context.capabilities,
    }


@router.post("/me/avatar")
def upload_my_avatar(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    context: AuthContext = Depends(get_auth_context),
):
    user = db.get(User, context.user_id)
    if user is None:
        raise AppError("auth.unauthenticated")
    save_avatar(db, user, file)
    return {"user": user_public(user, include_state=False)}


@router.delete("/me/avatar", status_code=204)
def delete_my_avatar(
    db: Session = Depends(get_db),
    context: AuthContext = Depends(get_auth_context),
):
    user = db.get(User, context.user_id)
    if user is None:
        raise AppError("auth.unauthenticated")
    delete_avatar(db, user)
    return Response(status_code=204)


@router.get("/avatars/{user_id}")
def get_user_avatar(
    user_id: int,
    db: Session = Depends(get_db),
    _context: AuthContext = Depends(get_auth_context),
):
    user = db.get(User, user_id)
    if user is None:
        raise AppError("user.not_found", params={"user_id": user_id})
    path = avatar_path(user)
    if path is None:
        raise AppError("app.not_found")
    return FileResponse(
        path,
        media_type=image_media_type(path),
        headers={"Cache-Control": "private, max-age=300"},
    )


@router.post("/me/password")
def change_my_password(
    payload: PasswordChangeRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    context: AuthContext = Depends(get_auth_context),
):
    raw, new_context = change_password(
        db,
        context,
        request,
        current_password=payload.current_password,
        new_password=payload.new_password,
    )
    from ..models import User

    user = db.get(User, context.user_id)
    _set_cookie(response, raw)
    return _session_payload(user, new_context)
