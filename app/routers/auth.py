from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.rate_limit import limiter
from app.db import get_db
from app.schemas.auth import LoginIn, RefreshIn, RegisterIn, TokenPair
from app.schemas.user import UserOut
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])
AUTH_LIMIT = get_settings().rate_limit_auth


def _unauthorized(msg: str) -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, msg, headers={"WWW-Authenticate": "Bearer"})


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
@limiter.limit(AUTH_LIMIT)
def register(request: Request, body: RegisterIn, db: Session = Depends(get_db)):
    try:
        return auth_service.register(db, body.email, body.password)
    except auth_service.EmailTakenError:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered") from None


@router.post("/login", response_model=TokenPair)
@limiter.limit(AUTH_LIMIT)
def login(request: Request, body: LoginIn, db: Session = Depends(get_db)):
    try:
        return auth_service.login(db, body.email, body.password)
    except auth_service.AuthError as exc:
        raise _unauthorized(str(exc)) from None


@router.post("/refresh", response_model=TokenPair)
@limiter.limit(AUTH_LIMIT)
def refresh(request: Request, body: RefreshIn, db: Session = Depends(get_db)):
    try:
        return auth_service.refresh(db, body.refresh_token)
    except auth_service.AuthError as exc:
        raise _unauthorized(str(exc)) from None


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(AUTH_LIMIT)
def logout(request: Request, body: RefreshIn, db: Session = Depends(get_db)):
    auth_service.logout(db, body.refresh_token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
