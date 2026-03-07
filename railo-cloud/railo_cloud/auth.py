"""GitHub OAuth 2.0 authentication for Railo Cloud.

Flow:
  1. GET /auth/login/github   -> redirect to github.com/login/oauth/authorize
  2. GitHub redirects back to GET /auth/callback/github?code=...&state=...
  3. We exchange code for access_token, fetch /user and /user/installations
  4. Upsert GitHubUser + InstallationMember rows
  5. Issue a signed JWT in an HttpOnly cookie and redirect to the SPA
"""
from __future__ import annotations

import logging
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import requests as _requests
import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from fastapi.security import APIKeyHeader
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

SECRET_KEY = os.getenv("JWT_SECRET", "super-secret-local-key")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 1 day

GITHUB_CLIENT_ID = os.getenv("GITHUB_OAUTH_CLIENT_ID", "")
GITHUB_CLIENT_SECRET = os.getenv("GITHUB_OAUTH_CLIENT_SECRET", "")
FRONTEND_BASE_URL = os.getenv("FRONTEND_BASE_URL", "http://localhost:5173")
_IS_PRODUCTION = os.getenv("ENVIRONMENT", "").lower() == "production"
_ALLOW_MOCK = os.getenv("ALLOW_MOCK_AUTH", "").lower() in ("1", "true", "yes")

auth_router = APIRouter()
_API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


# ---------------------------------------------------------------------------
# Token helpers
# ---------------------------------------------------------------------------

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=15))
    to_encode["exp"] = expire
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key="railo_session",
        value=token,
        httponly=True,
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        samesite="lax",
        secure=_IS_PRODUCTION,
        path="/",
    )


def verify_token(req: Request) -> dict:
    token = req.cookies.get("railo_session")
    if not token:
        auth_header = req.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header.split(" ", 1)[1]
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except jwt.PyJWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------

async def get_current_user(req: Request, api_key: str | None = Depends(_API_KEY_HEADER)) -> dict:
    from railo_cloud.config import get_settings
    configured_key = get_settings().api_key
    if configured_key and api_key == configured_key:
        return {"sub": "system", "role": "admin", "github_user_id": None, "installation_ids": []}
    return verify_token(req)


async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin privileges required")
    return user


async def require_dev(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") not in ("admin", "developer"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Developer privileges required")
    return user


# ---------------------------------------------------------------------------
# GitHub OAuth helpers
# ---------------------------------------------------------------------------

def _github_oauth_configured() -> bool:
    return bool(GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET)


def _fetch_github_user(access_token: str) -> dict:
    resp = _requests.get(
        "https://api.github.com/user",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def _fetch_user_installations(access_token: str) -> list[dict]:
    """Return all GitHub App installations the user has access to (paginated)."""
    installations: list[dict] = []
    url: str | None = "https://api.github.com/user/installations"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    while url:
        resp = _requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        installations.extend(data.get("installations", []))
        url = resp.links.get("next", {}).get("url") if hasattr(resp, 'links') else None
    return installations


def _upsert_user_and_memberships(session: Session, gh_user: dict, installations: list[dict]) -> list[int]:
    """Upsert GitHubUser and InstallationMember rows. Returns list of installation_ids."""
    from railo_cloud.models import GitHubUser, Installation, InstallationMember

    github_id: int = gh_user["id"]
    now = datetime.now(timezone.utc)

    # Upsert GitHubUser
    user_row = session.query(GitHubUser).filter_by(github_id=github_id).first()
    if user_row is None:
        user_row = GitHubUser(
            id=uuid.uuid4(),
            github_id=github_id,
            login=gh_user.get("login", ""),
            name=gh_user.get("name"),
            avatar_url=gh_user.get("avatar_url"),
            email=gh_user.get("email"),
        )
        session.add(user_row)
    else:
        user_row.login = gh_user.get("login", user_row.login)
        user_row.name = gh_user.get("name", user_row.name)
        user_row.avatar_url = gh_user.get("avatar_url", user_row.avatar_url)
        user_row.email = gh_user.get("email", user_row.email)
        user_row.updated_at = now

    installation_ids: list[int] = []
    for inst in installations:
        inst_id: int = inst["id"]
        installation_ids.append(inst_id)

        # Ensure Installation row exists
        inst_row = session.query(Installation).filter_by(installation_id=inst_id).first()
        if inst_row is None:
            session.add(Installation(
                id=uuid.uuid4(),
                installation_id=inst_id,
                account_login=inst.get("account", {}).get("login"),
                account_type=inst.get("account", {}).get("type"),
            ))

        # Upsert membership
        member = session.query(InstallationMember).filter_by(
            github_user_id=github_id, installation_id=inst_id
        ).first()
        if member is None:
            session.add(InstallationMember(
                id=uuid.uuid4(),
                github_user_id=github_id,
                installation_id=inst_id,
            ))

    session.commit()
    return installation_ids


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@auth_router.get("/login/github")
def login_github():
    """Redirect to GitHub OAuth authorize."""
    if not _github_oauth_configured():
        if _ALLOW_MOCK or not _IS_PRODUCTION:
            return RedirectResponse(url="/auth/callback/github?mock=1", status_code=302)
        raise HTTPException(status_code=503, detail="GitHub OAuth not configured")

    state = secrets.token_urlsafe(32)
    try:
        from railo_cloud.db.base import get_session_factory as _get_session_factory
        _session_make = _get_session_factory()
        from railo_cloud.models import OAuthState
        with _session_make() as session:
            session.add(OAuthState(
                id=uuid.uuid4(),
                state=state,
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
            ))
            session.commit()
    except Exception:
        logger.exception("Failed to persist OAuth state")

    callback_uri = f"{FRONTEND_BASE_URL.rstrip('/')}/auth/callback/github"
    params = (
        f"client_id={GITHUB_CLIENT_ID}"
        f"&redirect_uri={callback_uri}"
        f"&scope=read%3Auser+user%3Aemail"
        f"&state={state}"
    )
    return RedirectResponse(url=f"https://github.com/login/oauth/authorize?{params}", status_code=302)


@auth_router.get("/callback/github")
def callback_github(
    code: str | None = None,
    state: str | None = None,
    mock: str | None = None,
    role: str = "admin",
):
    """Handle GitHub OAuth callback (or mock login in dev)."""
    # --- Mock / dev path ---
    if mock == "1" or (not _github_oauth_configured() and not _IS_PRODUCTION):
        user_info = {
            "sub": "github:mockuser",
            "username": "mockuser",
            "role": role,
            "github_user_id": 0,
            "installation_ids": [],
        }
        token = create_access_token(data=user_info, expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
        redirect = RedirectResponse(url=FRONTEND_BASE_URL, status_code=302)
        _set_session_cookie(redirect, token)
        return redirect

    # --- Real OAuth path ---
    if not code:
        raise HTTPException(status_code=400, detail="Missing OAuth code")

    # Validate CSRF state
    if state:
        try:
            from railo_cloud.db.base import get_session_factory as _get_session_factory
            _session_make = _get_session_factory()
            from railo_cloud.models import OAuthState
            with _session_make() as session:
                state_row = session.query(OAuthState).filter_by(state=state).first()
                if state_row is None:
                    raise HTTPException(status_code=400, detail="Invalid OAuth state")
                if state_row.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
                    raise HTTPException(status_code=400, detail="OAuth state expired")
                session.delete(state_row)
                session.commit()
        except HTTPException:
            raise
        except Exception:
            logger.exception("OAuth state validation error  continuing")

    # Exchange code for access token
    try:
        token_resp = _requests.post(
            "https://github.com/login/oauth/access_token",
            json={"client_id": GITHUB_CLIENT_ID, "client_secret": GITHUB_CLIENT_SECRET, "code": code},
            headers={"Accept": "application/json"},
            timeout=10,
        )
        token_resp.raise_for_status()
        token_data = token_resp.json()
    except Exception as exc:
        logger.exception("GitHub token exchange failed")
        raise HTTPException(status_code=502, detail="GitHub token exchange failed") from exc

    access_token = token_data.get("access_token")
    if not access_token:
        raise HTTPException(status_code=502, detail=f"No access_token from GitHub: {token_data}")

    # Fetch user profile and installations
    try:
        gh_user = _fetch_github_user(access_token)
        installations = _fetch_user_installations(access_token)
    except _requests.RequestException as exc:
        logger.exception("GitHub API call failed")
        raise HTTPException(status_code=502, detail="GitHub API error") from exc

    # Persist to DB
    installation_ids: list[int] = []
    try:
        from railo_cloud.db.base import get_session_factory as _get_session_factory
        _session_make = _get_session_factory()
        with _session_make() as session:
            installation_ids = _upsert_user_and_memberships(session, gh_user, installations)
    except Exception:
        logger.exception("DB upsert failed after GitHub OAuth  continuing")

    user_info = {
        "sub": f"github:{gh_user['login']}",
        "username": gh_user.get("login", ""),
        "role": "admin",
        "github_user_id": gh_user["id"],
        "installation_ids": installation_ids,
    }
    token = create_access_token(data=user_info, expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    redirect = RedirectResponse(url=FRONTEND_BASE_URL, status_code=302)
    _set_session_cookie(redirect, token)
    return redirect


@auth_router.get("/me")
def get_me(user: dict = Depends(get_current_user)):
    return {
        "sub": user.get("sub"),
        "username": user.get("username"),
        "role": user.get("role"),
        "github_user_id": user.get("github_user_id"),
        "installation_ids": user.get("installation_ids", []),
    }


@auth_router.post("/logout")
def logout(response: Response):
    response.delete_cookie("railo_session", path="/")
    return {"message": "Logged out"}
