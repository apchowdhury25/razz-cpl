from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.config import SECRET_KEY, SESSION_COOKIE
from app.database import SessionLocal, init_db
from app.exceptions import AppError, UnauthorizedError
from app.helpers import flash
from app.routers import (
    accounting,
    admin,
    ar,
    auth,
    bills,
    bookings,
    buyers,
    cash_bank,
    dashboard,
    payments,
    projects,
    receipts,
    reports,
    tax,
    units,
    vendors,
)
from app.web import render, templates

app = FastAPI(title="Razz CNPL Accounts", docs_url=None, redoc_url=None)
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, session_cookie=SESSION_COOKIE, same_site="lax")
app.mount("/static", StaticFiles(directory="app/static"), name="static")

for module in (
    auth,
    dashboard,
    projects,
    units,
    buyers,
    vendors,
    bookings,
    ar,
    receipts,
    bills,
    payments,
    accounting,
    cash_bank,
    tax,
    reports,
    admin,
):
    app.include_router(module.router)


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.exception_handler(UnauthorizedError)
async def unauthorized_handler(request: Request, exc: UnauthorizedError):
    if exc.status_code == 401:
        flash(request, exc.message, "error")
        return RedirectResponse("/login", status_code=303)
    db = SessionLocal()
    try:
        return render(request, db, "errors/403.html", None, nav="", message=exc.message, status_code=403)
    finally:
        db.close()


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    flash(request, exc.message, "error")
    referer = request.headers.get("referer") or "/"
    if request.method == "GET":
        db = SessionLocal()
        try:
            template = {
                "not_found": "errors/404.html",
                "unauthorized": "errors/403.html",
                "unbalanced_journal": "errors/accounting.html",
                "locked_period": "errors/accounting.html",
                "allocation": "errors/accounting.html",
                "duplicate": "errors/accounting.html",
            }.get(exc.code, "errors/validation.html")
            return render(request, db, template, None, nav="", message=exc.message, code=exc.code)
        finally:
            db.close()
    return RedirectResponse(referer, status_code=303)


@app.exception_handler(404)
async def not_found_handler(request: Request, _exc):
    db = SessionLocal()
    try:
        return render(request, db, "errors/404.html", None, nav="", message="The page was not found.")
    finally:
        db.close()


@app.exception_handler(500)
async def server_error_handler(request: Request, _exc):
    db = SessionLocal()
    try:
        return render(request, db, "errors/500.html", None, nav="", message="An unexpected error occurred. The technical details have been withheld.")
    finally:
        db.close()


@app.get("/health")
def health():
    return {"status": "ok"}
