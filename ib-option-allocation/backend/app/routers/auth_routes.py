from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..auth import CurrentUser, create_token, get_current_user, verify_password
from ..database import get_db

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginIn(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(models.User).where(models.User.username == body.username))
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Invalid username or password")
    return {"token": create_token(user.username, user.role), "username": user.username, "role": user.role}


@router.get("/me")
def me(user: CurrentUser = Depends(get_current_user)):
    return {"username": user.username, "role": user.role}
