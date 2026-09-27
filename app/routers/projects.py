from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.deps import can_write, login_required, verify_csrf
from app.exceptions import ValidationError
from app.helpers import flash, optional_int, paginate, parse_date, parse_money, require_date
from app.models import Project, Unit, User
from app.money import ZERO, money
from app.services.audit import write_audit
from app.services.reports import project_accounting
from app.web import render

router = APIRouter(prefix="/projects")


@router.get("")
def list_projects(request: Request, db: Session = Depends(get_db), user: User = Depends(login_required)):
    q = request.query_params.get("q", "").strip()
    stmt = select(Project).order_by(Project.code)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(Project.code.ilike(like) | Project.name.ilike(like))
    page = paginate(db, stmt, int(request.query_params.get("page", 1)))
    return render(request, db, "projects/list.html", user, nav="projects", page=page, q=q)


@router.get("/new")
def new_form(request: Request, db: Session = Depends(get_db), user: User = Depends(login_required)):
    return render(request, db, "projects/form.html", user, nav="projects", item=None)


@router.post("/new")
def create_project(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(login_required),
    csrf: str = Form(""),
    code: str = Form(...),
    name: str = Form(...),
    name_bn: str = Form(""),
    mode: str = Form("DEVELOPER"),
    client_name: str = Form(""),
    address: str = Form(""),
    start_date: str = Form(""),
    expected_completion: str = Form(""),
    status: str = Form("ACTIVE"),
    budget: str = Form("0"),
    contract_value: str = Form("0"),
    retention_percent: str = Form("5"),
    notes: str = Form(""),
):
    verify_csrf(request, csrf)
    if not can_write(user):
        raise ValidationError("You cannot create projects.")
    code = code.strip().upper()
    if db.execute(select(Project).where(Project.code == code)).scalar_one_or_none():
        raise ValidationError(f"Project code {code} already exists.")
    item = Project(
        code=code,
        name=name.strip(),
        name_bn=name_bn.strip(),
        mode=mode,
        client_name=client_name.strip(),
        address=address.strip(),
        start_date=parse_date(start_date, "Start date"),
        expected_completion=parse_date(expected_completion, "Completion date"),
        status=status,
        budget=parse_money(budget, "Budget") if budget else ZERO,
        contract_value=parse_money(contract_value, "Contract value") if contract_value else ZERO,
        retention_percent=parse_money(retention_percent, "Retention %"),
        notes=notes.strip(),
    )
    db.add(item)
    db.flush()
    write_audit(db, user=user, action="CREATE", module="projects", record_type="Project", record_id=item.id, document_no=item.code)
    db.commit()
    flash(request, "Project saved.")
    return RedirectResponse("/projects", status_code=303)


@router.get("/{item_id}")
def detail(item_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(login_required)):
    item = db.get(Project, item_id)
    if not item:
        raise ValidationError("Project not found.")
    summary = project_accounting(db, item)
    units = db.execute(select(Unit).where(Unit.project_id == item.id).order_by(Unit.unit_number)).scalars().all()
    return render(request, db, "projects/detail.html", user, nav="projects", item=item, summary=summary, units=units)


@router.get("/{item_id}/edit")
def edit_form(item_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(login_required)):
    item = db.get(Project, item_id)
    if not item:
        raise ValidationError("Project not found.")
    return render(request, db, "projects/form.html", user, nav="projects", item=item)


@router.post("/{item_id}/edit")
async def update_project(item_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(login_required)):
    verify_csrf(request, (await request.form()).get("csrf"))
    if not can_write(user):
        raise ValidationError("You cannot edit projects.")
    item = db.get(Project, item_id)
    if not item:
        raise ValidationError("Project not found.")
    form = await request.form()
    item.name = str(form.get("name") or "").strip()
    item.name_bn = str(form.get("name_bn") or "").strip()
    item.mode = str(form.get("mode") or item.mode)
    item.client_name = str(form.get("client_name") or "").strip()
    item.address = str(form.get("address") or "").strip()
    item.start_date = parse_date(str(form.get("start_date") or ""), "Start date")
    item.expected_completion = parse_date(str(form.get("expected_completion") or ""), "Completion")
    item.status = str(form.get("status") or item.status)
    item.budget = parse_money(str(form.get("budget") or "0"), "Budget")
    item.contract_value = parse_money(str(form.get("contract_value") or "0"), "Contract")
    item.retention_percent = parse_money(str(form.get("retention_percent") or "0"), "Retention")
    item.notes = str(form.get("notes") or "").strip()
    write_audit(db, user=user, action="EDIT", module="projects", record_type="Project", record_id=item.id, document_no=item.code)
    db.commit()
    flash(request, "Project updated.")
    return RedirectResponse(f"/projects/{item.id}", status_code=303)
