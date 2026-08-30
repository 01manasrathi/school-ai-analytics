"""JWT + bcrypt authentication, backed by data/users.csv.

Roles: admin, teacher, student. Kept intentionally simple (no OAuth
providers) since this is a self-hosted, file-based system.
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

from . import config, data_store

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return pwd_context.verify(password, password_hash)
    except Exception:
        return False


def create_access_token(username: str, role: str, linked_id: str) -> str:
    expire = dt.datetime.utcnow() + dt.timedelta(minutes=config.JWT_EXPIRE_MINUTES)
    payload = {"sub": username, "role": role, "linked_id": linked_id, "exp": expire}
    return jwt.encode(payload, config.JWT_SECRET, algorithm=config.JWT_ALGORITHM)


def authenticate_user(username: str, password: str) -> Optional[dict]:
    user = data_store.get_row("users", "username", username)
    if not user:
        return None
    if not verify_password(password, user["password_hash"]):
        return None
    return user


def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, config.JWT_SECRET, algorithms=[config.JWT_ALGORITHM])
        username = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    user = data_store.get_row("users", "username", username)
    if user is None:
        raise credentials_exception
    return user


def require_roles(*roles: str):
    def _checker(user: dict = Depends(get_current_user)) -> dict:
        if user["role"] not in roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user
    return _checker
