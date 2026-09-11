from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from app.api.deps import CurrentUser, DbSession, UserRepo
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User
from app.schemas.auth import Token, UserCreate, UserOut

router = APIRouter()


@router.post("/register", response_model=UserOut, status_code=201)
def register(payload: UserCreate, db: DbSession, users: UserRepo) -> User:
    if users.by_email(payload.email):
        raise HTTPException(status.HTTP_409_CONFLICT, "email already registered")
    user = users.add(User(
        email=payload.email,
        full_name=payload.full_name,
        hashed_password=hash_password(payload.password),
    ))
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=Token)
def login(users: UserRepo, form: OAuth2PasswordRequestForm = Depends()) -> Token:  # noqa: B008
    user = users.by_email(form.username)
    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "bad credentials")
    return Token(access_token=create_access_token(user.id))


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> User:
    return user
