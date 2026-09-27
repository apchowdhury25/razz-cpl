from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import can_write, login_required, verify_csrf
from app.exceptions import ValidationError
from app.helpers import flash, paginate
from app.models import Customer, User
from app.services.ar import customer_ledger
from app.services.audit import write_audit
from app.services.numbering import next_number
from app.web import render

router = APIRouter(prefix="/customers")


@router.get("")
def list_customers(request: Request, db: Session = Depends(get_db), user: User = Depends(login_required)):
    stmt = select(Customer).order_by(Customer.code)
    q = request.query_params.get("q", "").strip()
    if q:
        like = f"%{q}%"
        stmt = stmt.where(Customer.code.ilike(like) | Customer.name.ilike(like) | Customer.phone.ilike(like))
    page = paginate(db, stmt, int(request.query_params.get("page", 1)))
    return render(request, db, "buyers/list.html", user, nav="customers", page=page, q=q)


@router.get("/new")
def new_form(request: Request, db: Session = Depends(get_db), user: User = Depends(login_required)):
    return render(request, db, "buyers/form.html", user, nav="customers", item=None)


@router.post("/new")
def create_customer(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(login_required),
    csrf: str = Form(""),
    name: str = Form(...),
    name_bn: str = Form(""),
    father_name: str = Form(""),
    nid: str = Form(""),
    phone: str = Form(""),
    email: str = Form(""),
    address: str = Form(""),
    notes: str = Form(""),
):
    verify_csrf(request, csrf)
    if not can_write(user):
        raise ValidationError("You cannot create customers.")
    from datetime import date

    code = next_number(db, "CU", date.today().year)
    item = Customer(
        code=code,
        name=name.strip(),
        name_bn=name_bn.strip(),
        father_name=father_name.strip(),
        nid=nid.strip(),
        phone=phone.strip(),
        email=email.strip(),
        address=address.strip(),
        notes=notes.strip(),
        is_active=True,
    )
    db.add(item)
    db.flush()
    write_audit(db, user=user, action="CREATE", module="customers", record_type="Customer", record_id=item.id, document_no=item.code)
    db.commit()
    flash(request, "Customer saved.")
    return RedirectResponse("/customers", status_code=303)


@router.get("/{item_id}")
def detail(item_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(login_required)):
    item = db.get(Customer, item_id)
    if not item:
        raise ValidationError("Customer not found.")
    ledger = customer_ledger(db, item.id)
    return render(request, db, "buyers/detail.html", user, nav="customers", item=item, ledger=ledger)


@router.get("/{item_id}/edit")
def edit_form(item_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(login_required)):
    item = db.get(Customer, item_id)
    if not item:
        raise ValidationError("Customer not found.")
    return render(request, db, "buyers/form.html", user, nav="customers", item=item)


@router.post("/{item_id}/edit")
async def update_customer(item_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(login_required)):
    form = await request.form()
    verify_csrf(request, form.get("csrf"))
    if not can_write(user):
        raise ValidationError("You cannot edit customers.")
    item = db.get(Customer, item_id)
    if not item:
        raise ValidationError("Customer not found.")
    item.name = str(form.get("name") or "").strip()
    item.name_bn = str(form.get("name_bn") or "").strip()
    item.father_name = str(form.get("father_name") or "").strip()
    item.nid = str(form.get("nid") or "").strip()
    item.phone = str(form.get("phone") or "").strip()
    item.email = str(form.get("email") or "").strip()
    item.address = str(form.get("address") or "").strip()
    item.notes = str(form.get("notes") or "").strip()
    item.is_active = form.get("is_active") == "1"
    write_audit(db, user=user, action="EDIT", module="customers", record_type="Customer", record_id=item.id, document_no=item.code)
    db.commit()
    flash(request, "Customer updated.")
    return RedirectResponse(f"/customers/{item.id}", status_code=303)
