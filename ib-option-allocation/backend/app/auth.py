"""Very small local auth: PBKDF2 password hashes + HMAC-signed bearer tokens (stdlib only, no external service)."""
import base64
import hashlib
import hmac
import json
import os
import time

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models
from .config import PBKDF2_ITERATIONS, SECRET_KEY, TOKEN_TTL_HOURS
from .database import get_db

_bearer = HTTPBearer(auto_error=False)


def hash_password(password: str, salt: bytes | None = None, iterations: int | None = None) -> str:
    salt = salt or os.urandom(16)
    iterations = iterations or PBKDF2_ITERATIONS
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return f"{iterations}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    iterations, salt_hex, _ = stored.split("$", 2)
    return hmac.compare_digest(hash_password(password, bytes.fromhex(salt_hex), int(iterations)), stored)


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def create_token(username: str, role: str) -> str:
    payload = _b64(json.dumps({"u": username, "r": role, "exp": int(time.time()) + TOKEN_TTL_HOURS * 3600}).encode())
    sig = _b64(hmac.new(SECRET_KEY.encode(), payload.encode(), hashlib.sha256).digest())
    return f"{payload}.{sig}"


def decode_token(token: str) -> dict | None:
    try:
        payload, sig = token.split(".", 1)
        expected = _b64(hmac.new(SECRET_KEY.encode(), payload.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expected):
            return None
        data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        return data if data["exp"] > time.time() else None
    except Exception:
        return None


class CurrentUser:
    def __init__(self, username: str, role: str):
        self.username, self.role = username, role

    @property
    def is_admin(self) -> bool:
        return self.role == models.Role.ADMIN


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer), db: Session = Depends(get_db)
) -> CurrentUser:
    data = decode_token(creds.credentials) if creds else None
    if not data:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    user = db.scalar(select(models.User).where(models.User.username == data["u"]))
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unknown user")
    return CurrentUser(user.username, user.role)


def require_admin(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin / Timetabler role required")
    return user
