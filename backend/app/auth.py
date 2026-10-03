"""
Password hashing (bcrypt) and JWT issuance/verification, plus the
get_current_user FastAPI dependency used to protect routes.

Kept deliberately simple (no refresh tokens, no email verification) --
a single long-lived access token issued at login/signup, sent as a
Bearer token on every request. That's the right amount of complexity for
an internal tool used by a project team, not a public-facing consumer app.
"""
import re
from datetime import timedelta
from app.utils import utcnow

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app import models

bearer_scheme = HTTPBearer(auto_error=False)


def validate_password_strength(password: str) -> None:
    if len(password) < 8:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Password must be at least 8 characters long.")
    if not re.search(r"[A-Z]", password):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Password must contain at least one uppercase letter (A-Z).")
    if not re.search(r"[a-z]", password):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Password must contain at least one lowercase letter (a-z).")
    if not re.search(r"[0-9]", password):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Password must contain at least one numerical digit (0-9).")
    if not re.search(r"[!?@#$%^&*()_+\-=\[\]{};':\"\\|,.<>\/?~#]", password):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Password must contain at least one special character (e.g. ?, #, /, @, !, $)."
        )



def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(user_id: str) -> str:
    expire = utcnow() + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    payload = {"sub": user_id, "exp": expire}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def create_reset_token(user_id: str) -> str:
    expire = utcnow() + timedelta(minutes=15)
    payload = {"sub": user_id, "scope": "password_reset", "exp": expire}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_reset_token(token: str) -> str:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        if payload.get("scope") != "password_reset":
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid password reset token.")
        return payload["sub"]
    except jwt.ExpiredSignatureError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Password reset link has expired. Please request a new one.")
    except jwt.InvalidTokenError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired password reset link.")


def decode_access_token(token: str) -> str:

    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        return payload["sub"]
    except jwt.ExpiredSignatureError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired, please log in again.")
    except jwt.InvalidTokenError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid authentication token.")


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> models.User:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated.")
    user_id = decode_access_token(credentials.credentials)
    user = db.get(models.User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User no longer exists.")
    return user
