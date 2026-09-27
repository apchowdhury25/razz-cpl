from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import BACKUP_DIR, DATABASE_URL
from app.database import get_db
from app.deps import can_config, login_required, verify_csrf
from app.exceptions import UnauthorizedError, ValidationError
from app.helpers import flash, paginate, parse_date, require_date
from app.models import AccountingPeriod, AuditLog, CompanySettings, DocumentSequence, Employee, User, UserRole
from app.security import hash_password
from app.services.audit import write_audit
from app.web import render

router = APIRouter()


def _admin(user: User) -> None:
    if not can_config(user):
        raise UnauthorizedError("Only administrators can access this area.")


@router.get("/admin/users")
def users(request: Request, db: Session = Depends(get_db), user: User = Depends(login_required)):
    _admin(user)
    items = db.execute(select(User).order_by(User.username)).scalars().all()
    return render(request, db, "admin/users.html", user, nav="users", items=items, roles=list(UserRole))


@router.post("/admin/users/new")
def create_user(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(login_required),
    csrf: str = Form(""),
    username: str = Form(...),
    full_name: str = Form(...),
    email: str = Form(""),
    role: str = Form(...),
    password: str = Form(...),
):
    verify_csrf(request, csrf)
    _admin(user)
    if db.execute(select(User).where(User.username == username.strip())).scalar_one_or_none():
        raise ValidationError("Username already exists.")
    if role not in {r.value for r in UserRole}:
        raise ValidationError("Invalid role.")
    item = User(username=username.strip(), full_name=full_name.strip(), email=email.strip(), role=role, password_hash=hash_password(password), is_active=True)
    db.add(item)
    db.flush()
    write_audit(db, user=user, action="CREATE", module="admin", record_type="User", record_id=item.id, document_no=item.username)
    db.commit()
    flash(request, "User created.")
    return RedirectResponse("/admin/users", status_code=303)


@router.post("/admin/users/{item_id}")
async def update_user(item_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(login_required)):
    form = await request.form()
    verify_csrf(request, form.get("csrf"))
    _admin(user)
    item = db.get(User, item_id)
    if not item:
        raise ValidationError("User not found.")
    item.full_name = str(form.get("full_name") or item.full_name)
    item.email = str(form.get("email") or "")
    item.role = str(form.get("role") or item.role)
    item.is_active = form.get("is_active") == "1"
    if form.get("password"):
        item.password_hash = hash_password(str(form.get("password")))
    write_audit(db, user=user, action="EDIT", module="admin", record_type="User", record_id=item.id, document_no=item.username)
    db.commit()
    flash(request, "User updated.")
    return RedirectResponse("/admin/users", status_code=303)


@router.get("/admin/roles")
def roles(request: Request, db: Session = Depends(get_db), user: User = Depends(login_required)):
    _admin(user)
    return render(request, db, "admin/roles.html", user, nav="roles")


@router.get("/admin/settings")
def settings_form(request: Request, db: Session = Depends(get_db), user: User = Depends(login_required)):
    _admin(user)
    settings = db.execute(select(CompanySettings)).scalar_one_or_none()
    return render(request, db, "admin/settings.html", user, nav="settings", item=settings)


@router.post("/admin/settings")
async def save_settings(request: Request, db: Session = Depends(get_db), user: User = Depends(login_required)):
    form = await request.form()
    verify_csrf(request, form.get("csrf"))
    _admin(user)
    item = db.execute(select(CompanySettings)).scalar_one_or_none()
    if not item:
        item = CompanySettings()
        db.add(item)
    item.name = str(form.get("name") or item.name)
    item.name_bn = str(form.get("name_bn") or "")
    item.address = str(form.get("address") or "")
    item.address_bn = str(form.get("address_bn") or "")
    item.phone = str(form.get("phone") or "")
    item.email = str(form.get("email") or "")
    item.bin_number = str(form.get("bin_number") or "")
    item.tin_number = str(form.get("tin_number") or "")
    item.fy_code = str(form.get("fy_code") or item.fy_code)
    if form.get("fy_start"):
        item.fy_start = require_date(str(form.get("fy_start")), "FY start")
    if form.get("fy_end"):
        item.fy_end = require_date(str(form.get("fy_end")), "FY end")
    item.current_period = str(form.get("current_period") or item.current_period)
    write_audit(db, user=user, action="EDIT", module="admin", record_type="CompanySettings", record_id=item.id, description="Company settings updated")
    db.commit()
    flash(request, "Settings saved.")
    return RedirectResponse("/admin/settings", status_code=303)


@router.get("/admin/periods")
def periods(request: Request, db: Session = Depends(get_db), user: User = Depends(login_required)):
    _admin(user)
    items = db.execute(select(AccountingPeriod).order_by(AccountingPeriod.start_date)).scalars().all()
    return render(request, db, "admin/periods.html", user, nav="periods", items=items)


@router.post("/admin/periods/{item_id}/lock")
def lock_period(item_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(login_required), csrf: str = Form(""), locked: str = Form("1")):
    verify_csrf(request, csrf)
    _admin(user)
    item = db.get(AccountingPeriod, item_id)
    item.is_locked = locked == "1"
    item.locked_at = datetime.utcnow() if item.is_locked else None
    item.locked_by_id = user.id if item.is_locked else None
    write_audit(db, user=user, action="EDIT", module="admin", record_type="AccountingPeriod", record_id=item.id, document_no=item.code, description="lock" if item.is_locked else "unlock")
    db.commit()
    flash(request, f"Period {item.code} {'locked' if item.is_locked else 'unlocked'}.")
    return RedirectResponse("/admin/periods", status_code=303)


@router.get("/admin/numbering")
def numbering(request: Request, db: Session = Depends(get_db), user: User = Depends(login_required)):
    _admin(user)
    items = db.execute(select(DocumentSequence).order_by(DocumentSequence.doc_type, DocumentSequence.year)).scalars().all()
    return render(request, db, "admin/numbering.html", user, nav="numbering", items=items)


@router.post("/admin/numbering/{item_id}")
async def update_numbering(item_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(login_required)):
    form = await request.form()
    verify_csrf(request, form.get("csrf"))
    _admin(user)
    item = db.get(DocumentSequence, item_id)
    item.prefix = str(form.get("prefix") or item.prefix)
    item.next_number = int(form.get("next_number") or item.next_number)
    item.padding = int(form.get("padding") or item.padding)
    db.commit()
    flash(request, "Numbering updated.")
    return RedirectResponse("/admin/numbering", status_code=303)


@router.get("/admin/audit")
def audit(request: Request, db: Session = Depends(get_db), user: User = Depends(login_required)):
    stmt = select(AuditLog).order_by(AuditLog.id.desc())
    q = request.query_params.get("q", "").strip()
    if q:
        stmt = stmt.where(AuditLog.description.ilike(f"%{q}%") | AuditLog.document_no.ilike(f"%{q}%") | AuditLog.username.ilike(f"%{q}%"))
    page = paginate(db, stmt, int(request.query_params.get("page", 1)), per_page=50)
    return render(request, db, "admin/audit.html", user, nav="audit", page=page, q=q)


@router.get("/admin/employees")
def employees(request: Request, db: Session = Depends(get_db), user: User = Depends(login_required)):
    items = db.execute(select(Employee).order_by(Employee.code)).scalars().all()
    return render(request, db, "admin/employees.html", user, nav="employees", items=items)


@router.post("/admin/employees/new")
def create_employee(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(login_required),
    csrf: str = Form(""),
    code: str = Form(...),
    name: str = Form(...),
    designation: str = Form(""),
    phone: str = Form(""),
):
    verify_csrf(request, csrf)
    if not can_config(user) and user.role not in ("ADMIN", "ACCOUNTS_OFFICER", "MANAGER"):
        raise UnauthorizedError("Not allowed.")
    db.add(Employee(code=code.strip(), name=name.strip(), designation=designation.strip(), phone=phone.strip(), is_active=True))
    db.commit()
    flash(request, "Employee saved.")
    return RedirectResponse("/admin/employees", status_code=303)


@router.get("/admin/backup")
def backup_page(request: Request, db: Session = Depends(get_db), user: User = Depends(login_required)):
    _admin(user)
    files = sorted(BACKUP_DIR.glob("*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
    return render(request, db, "admin/backup.html", user, nav="backup", files=files, db_url=DATABASE_URL)


@router.post("/admin/backup")
def run_backup(request: Request, db: Session = Depends(get_db), user: User = Depends(login_required), csrf: str = Form("")):
    verify_csrf(request, csrf)
    _admin(user)
    path = backup_sqlite()
    write_audit(db, user=user, action="CREATE", module="admin", record_type="Backup", description=str(path))
    db.commit()
    flash(request, f"Backup created: {path.name}")
    return RedirectResponse("/admin/backup", status_code=303)


@router.get("/admin/backup/download/{name}")
def download_backup(name: str, user: User = Depends(login_required)):
    _admin(user)
    path = BACKUP_DIR / Path(name).name
    if not path.exists():
        raise ValidationError("Backup file not found.")
    return FileResponse(path, filename=path.name)


def backup_sqlite() -> Path:
    import sqlite3

    if not DATABASE_URL.startswith("sqlite:///"):
        raise ValidationError("Backup is implemented for SQLite only.")
    src = DATABASE_URL.replace("sqlite:///", "")
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    dest = BACKUP_DIR / f"razz_accounts_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    source = sqlite3.connect(src)
    dest_conn = sqlite3.connect(dest)
    try:
        source.backup(dest_conn)
    finally:
        dest_conn.close()
        source.close()
    return dest
