import os
from datetime import datetime, timedelta
from typing import Optional

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import APIKeyHeader

SECRET_KEY = os.getenv("JWT_SECRET", "super-secret-local-key")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 1 day

auth_router = APIRouter()

# For legacy endpoints, they can still use API key and bypassing JWT if they provide valid key, 
# or we can enforce JWT for the UI.
_API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def verify_token(req: Request) -> dict:
    token = req.cookies.get("railo_session")
    if not token:
        # fallback to Authorization header if present
        auth_header = req.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
            
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except jwt.PyJWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


async def get_current_user(req: Request, api_key: str | None = Depends(_API_KEY_HEADER)):
    from railo_cloud.config import get_settings
    
    # Allow API Key bypass based on existing require_api_key logic
    configured_key = get_settings().api_key
    if configured_key and api_key == configured_key:
        return {"sub": "system", "role": "admin"}
    elif not configured_key and get_settings().environment.lower() != "production":
        # Dev mode no-key bypass loosely allows admin, but for UI testing we want cookie fallback
        pass
        
    return verify_token(req)


async def require_admin(user: dict = Depends(get_current_user)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin privileges required")
    return user


async def require_dev(user: dict = Depends(get_current_user)):
    role = user.get("role")
    if role not in ("admin", "developer"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Developer privileges required")
    return user


@auth_router.get("/login/github")
def mock_login_github():
    # In a real scenario, this would redirect to GitHub OAuth authorize URL
    return {"url": "http://localhost:8000/auth/callback/github?code=mock_code"}


FRONTEND_BASE_URL = os.getenv("FRONTEND_BASE_URL", "https://www.railo.dev")
_IS_PRODUCTION = os.getenv("ENVIRONMENT", "").lower() == "production"


@auth_router.get("/callback/github")
def mock_callback_github(response: Response, code: str | None = None, role: str = "admin"):
    # Mocking GitHub token exchange and user info fetching
    # We allow passing ?role=dev or ?role=admin for testing
    user_info = {
        "sub": "github_user_123",
        "username": "mockuser",
        "role": role
    }
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    token = create_access_token(data=user_info, expires_delta=access_token_expires)
    
    # Set HttpOnly cookie
    response.set_cookie(
        key="railo_session",
        value=token,
        httponly=True,
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        samesite="lax",
        secure=_IS_PRODUCTION,
    )
    
    # Redirect back to frontend (sets cookie + Location header)
    response.status_code = status.HTTP_302_FOUND
    response.headers["Location"] = FRONTEND_BASE_URL
    return response

@auth_router.get("/me")
def get_me(user: dict = Depends(get_current_user)):
    return user

@auth_router.post("/logout")
def logout(response: Response):
    response.delete_cookie("railo_session")
    return {"message": "Logged out"}
