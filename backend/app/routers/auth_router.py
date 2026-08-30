from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm

from .. import auth, data_store
from ..schemas import Token

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = auth.authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    token = auth.create_access_token(user["username"], user["role"], user.get("linked_id", ""))
    return Token(
        access_token=token,
        role=user["role"],
        username=user["username"],
        full_name=user.get("full_name", user["username"]),
    )


@router.get("/me")
def me(user: dict = Depends(auth.get_current_user)):
    return {k: v for k, v in user.items() if k != "password_hash"}


@router.post("/users")
def create_user(
    username: str,
    password: str,
    role: str,
    full_name: str,
    linked_id: str = "",
    admin: dict = Depends(auth.require_roles("admin")),
):
    if data_store.get_row("users", "username", username):
        raise HTTPException(status_code=400, detail="Username already exists")
    if role not in ("admin", "teacher", "student"):
        raise HTTPException(status_code=400, detail="Invalid role")
    row = {
        "username": username,
        "password_hash": auth.hash_password(password),
        "role": role,
        "full_name": full_name,
        "linked_id": linked_id,
        "created_at": dt.date.today().isoformat(),
    }
    data_store.append_row("users", row)
    return {"status": "created", "username": username}
