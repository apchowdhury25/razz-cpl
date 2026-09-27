from __future__ import annotations

import secrets
from typing import Callable

from fastapi import Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.exceptions import UnauthorizedError
from app.models import User, UserRole

ROLE_RANK = {
    UserRole.AUDITOR.value: 1,
    UserRole.ACCOUNTS_OFFICER.value: 2,
    UserRole.MANAGER.value: 3,
    UserRole.ADMIN.value: 4,
}

WRITE_ROLES = {UserRole.ADMIN.value, UserRole.ACCOUNTS_OFFICER.value, UserRole.MANAGER.value}
APPROVE_ROLES = {UserRole.ADMIN.value, UserRole.MANAGER.value}
ADMIN_ROLES = {UserRole.ADMIN.value}
POST_ROLES = {UserRole.ADMIN.value, UserRole.MANAGER.value, UserRole.ACCOUNTS_OFFICER.value}
CONFIG_ROLES = {UserRole.ADMIN.value}
REVERSE_ROLES = {UserRole.ADMIN.value}


def current_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    uid = request.session.get("user_id")
    if not uid:
        return None
    user = db.get(User, uid)
    if not user or not user.is_active:
        request.session.clear()
        return None
    return user


def login_required(request: Request, db: Session = Depends(get_db)) -> User:
    user = current_user(request, db)
    if not user:
        raise UnauthorizedError("Please sign in to continue.", status_code=401)
    return user


def require_roles(*roles: str) -> Callable:
    allowed = set(roles)

    def _inner(user: User = Depends(login_required)) -> User:
        if user.role not in allowed:
            raise UnauthorizedError("You are not authorized to perform this action.")
        return user

    return _inner


def can_write(user: User) -> bool:
    return user.role in WRITE_ROLES


def can_approve(user: User) -> bool:
    return user.role in APPROVE_ROLES


def can_config(user: User) -> bool:
    return user.role in CONFIG_ROLES


def can_reverse(user: User) -> bool:
    return user.role in REVERSE_ROLES


def csrf_token(request: Request) -> str:
    token = request.session.get("csrf")
    if not token:
        token = secrets.token_hex(16)
        request.session["csrf"] = token
    return token


def verify_csrf(request: Request, token: str | None) -> None:
    expected = request.session.get("csrf")
    if not expected or not token or not secrets.compare_digest(str(token), str(expected)):
        raise UnauthorizedError("Invalid security token. Please reload the form and try again.")


class AuthRedirect(Exception):
    def __init__(self, url: str):
        self.url = url


def redirect_login() -> RedirectResponse:
    return RedirectResponse("/login", status_code=303)
