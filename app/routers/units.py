from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.deps import can_write, login_required, verify_csrf
from app.exceptions import ValidationError
from app.helpers import flash, optional_int, paginate, parse_money
from app.models import Customer, Project, Unit, User
from app.money import ZERO
from app.services.audit import write_audit
from app.web import render

router = APIRouter(prefix="/units")


@router.get("")
def list_units(request: Request, db: Session = Depends(get_db), user: User = Depends(login_required)):
    stmt = select(Unit).options(selectinload(Unit.project), selectinload(Unit.buyer)).order_by(Unit.id.desc())
    project_id = optional_int(request.query_params.get("project_id"))
    status = request.query_params.get("status", "")
    q = request.query_params.get("q", "").strip()
    if project_id:
        stmt = stmt.where(Unit.project_id == project_id)
    if status:
        stmt = stmt.where(Unit.status == status)
    if q:
        stmt = stmt.where(Unit.unit_number.ilike(f"%{q}%"))
    page = paginate(db, stmt, int(request.query_params.get("page", 1)))
    return render(request, db, "units/list.html", user, nav="units", page=page, q=q, status=status, project_id=project_id)


@router.get("/new")
def new_form(request: Request, db: Session = Depends(get_db), user: User = Depends(login_required)):
    customers = db.execute(select(Customer).where(Customer.is_active.is_(True)).order_by(Customer.name)).scalars().all()
    return render(request, db, "units/form.html", user, nav="units", item=None, customers=customers)


@router.post("/new")
def create_unit(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(login_required),
    csrf: str = Form(""),
    project_id: int = Form(...),
    unit_number: str = Form(...),
    floor: str = Form(""),
    size_sft: str = Form("0"),
    base_price: str = Form("0"),
    sale_price: str = Form("0"),
    status: str = Form("UNSOLD"),
    notes: str = Form(""),
):
    verify_csrf(request, csrf)
    if not can_write(user):
        raise ValidationError("You cannot create units.")
    existing = db.execute(select(Unit).where(Unit.project_id == project_id, Unit.unit_number == unit_number.strip())).scalar_one_or_none()
    if existing:
        raise ValidationError("Unit number already exists in this project.")
    item = Unit(
        project_id=project_id,
        unit_number=unit_number.strip(),
        floor=floor.strip(),
        size_sft=parse_money(size_sft, "Size"),
        base_price=parse_money(base_price, "Base price"),
        sale_price=parse_money(sale_price, "Sale price") if sale_price else parse_money(base_price, "Base price"),
        status=status,
        notes=notes.strip(),
    )
    db.add(item)
    db.flush()
    write_audit(db, user=user, action="CREATE", module="units", record_type="Unit", record_id=item.id, document_no=item.unit_number)
    db.commit()
    flash(request, "Unit saved.")
    return RedirectResponse("/units", status_code=303)


@router.get("/{item_id}/edit")
def edit_form(item_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(login_required)):
    item = db.get(Unit, item_id)
    if not item:
        raise ValidationError("Unit not found.")
    customers = db.execute(select(Customer).order_by(Customer.name)).scalars().all()
    return render(request, db, "units/form.html", user, nav="units", item=item, customers=customers)


@router.post("/{item_id}/edit")
async def update_unit(item_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(login_required)):
    form = await request.form()
    verify_csrf(request, form.get("csrf"))
    if not can_write(user):
        raise ValidationError("You cannot edit units.")
    item = db.get(Unit, item_id)
    if not item:
        raise ValidationError("Unit not found.")
    item.unit_number = str(form.get("unit_number") or item.unit_number).strip()
    item.floor = str(form.get("floor") or "").strip()
    item.size_sft = parse_money(str(form.get("size_sft") or "0"), "Size")
    item.base_price = parse_money(str(form.get("base_price") or "0"), "Base price")
    item.sale_price = parse_money(str(form.get("sale_price") or "0"), "Sale price")
    if item.status in ("UNSOLD", "RESERVED"):
        item.status = str(form.get("status") or item.status)
    item.notes = str(form.get("notes") or "").strip()
    write_audit(db, user=user, action="EDIT", module="units", record_type="Unit", record_id=item.id, document_no=item.unit_number)
    db.commit()
    flash(request, "Unit updated.")
    return RedirectResponse("/units", status_code=303)
