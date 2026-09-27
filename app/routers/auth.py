from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import csrf_token, current_user, login_required, verify_csrf
from app.helpers import flash, t
from app.models import User
from app.security import verify_password
from app.services.audit import write_audit
from app.web import render

router = APIRouter()


@router.get("/login")
def login_form(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if user:
        return RedirectResponse("/", status_code=303)
    csrf_token(request)
    return render(request, db, "login.html", None, nav="login")


@router.post("/login")
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    csrf: str = Form(""),
    db: Session = Depends(get_db),
):
    verify_csrf(request, csrf)
    user = db.execute(select(User).where(User.username == username.strip())).scalar_one_or_none()
    if not user or not user.is_active or not verify_password(password, user.password_hash):
        flash(request, t(request, "invalid_login"), "error")
        return RedirectResponse("/login", status_code=303)
    request.session["user_id"] = user.id
    write_audit(db, user=user, action="LOGIN", module="auth", description=f"User {user.username} signed in")
    db.commit()
    return RedirectResponse("/", status_code=303)


@router.post("/logout")
def logout(request: Request, csrf: str = Form(""), db: Session = Depends(get_db), user: User = Depends(login_required)):
    verify_csrf(request, csrf)
    write_audit(db, user=user, action="LOGOUT", module="auth", description=f"User {user.username} signed out")
    db.commit()
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@router.get("/lang/{code}")
def set_lang(code: str, request: Request):
    code = "bn" if code == "bn" else "en"
    request.session["lang"] = code
    response = RedirectResponse(request.headers.get("referer") or "/", status_code=303)
    response.set_cookie("lang", code, max_age=86400 * 365)
    return response
