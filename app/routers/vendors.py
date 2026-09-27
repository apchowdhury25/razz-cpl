from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import can_write, login_required, verify_csrf
from app.exceptions import ValidationError
from app.helpers import flash, paginate, parse_money
from app.models import TaxCategory, User, Vendor
from app.services.ap import vendor_ledger
from app.services.audit import write_audit
from app.services.numbering import next_number
from app.web import render

router = APIRouter(prefix="/vendors")


@router.get("")
def list_vendors(request: Request, db: Session = Depends(get_db), user: User = Depends(login_required)):
    stmt = select(Vendor).order_by(Vendor.code)
    q = request.query_params.get("q", "").strip()
    if q:
        like = f"%{q}%"
        stmt = stmt.where(Vendor.code.ilike(like) | Vendor.name.ilike(like))
    page = paginate(db, stmt, int(request.query_params.get("page", 1)))
    return render(request, db, "vendors/list.html", user, nav="vendors", page=page, q=q)


@router.get("/new")
def new_form(request: Request, db: Session = Depends(get_db), user: User = Depends(login_required)):
    cats = db.execute(select(TaxCategory).where(TaxCategory.tax_type == "TDS", TaxCategory.is_active.is_(True))).scalars().all()
    return render(request, db, "vendors/form.html", user, nav="vendors", item=None, tds_categories=cats)


@router.post("/new")
def create_vendor(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(login_required),
    csrf: str = Form(""),
    name: str = Form(...),
    name_bn: str = Form(""),
    vendor_type: str = Form("OTHER"),
    tin: str = Form(""),
    bin_number: str = Form(""),
    phone: str = Form(""),
    email: str = Form(""),
    address: str = Form(""),
    default_tds_percent: str = Form("0"),
    default_tds_category_id: str = Form(""),
    notes: str = Form(""),
):
    verify_csrf(request, csrf)
    if not can_write(user):
        raise ValidationError("You cannot create vendors.")
    code = next_number(db, "VE", date.today().year)
    cat_id = int(default_tds_category_id) if default_tds_category_id else None
    item = Vendor(
        code=code,
        name=name.strip(),
        name_bn=name_bn.strip(),
        vendor_type=vendor_type,
        tin=tin.strip(),
        bin_number=bin_number.strip(),
        phone=phone.strip(),
        email=email.strip(),
        address=address.strip(),
        default_tds_percent=parse_money(default_tds_percent, "TDS %"),
        default_tds_category_id=cat_id,
        notes=notes.strip(),
        is_active=True,
    )
    db.add(item)
    db.flush()
    write_audit(db, user=user, action="CREATE", module="vendors", record_type="Vendor", record_id=item.id, document_no=item.code)
    db.commit()
    flash(request, "Vendor saved.")
    return RedirectResponse("/vendors", status_code=303)


@router.get("/{item_id}")
def detail(item_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(login_required)):
    item = db.get(Vendor, item_id)
    if not item:
        raise ValidationError("Vendor not found.")
    ledger = vendor_ledger(db, item.id)
    return render(request, db, "vendors/detail.html", user, nav="vendors", item=item, ledger=ledger)


@router.get("/{item_id}/edit")
def edit_form(item_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(login_required)):
    item = db.get(Vendor, item_id)
    if not item:
        raise ValidationError("Vendor not found.")
    cats = db.execute(select(TaxCategory).where(TaxCategory.tax_type == "TDS")).scalars().all()
    return render(request, db, "vendors/form.html", user, nav="vendors", item=item, tds_categories=cats)


@router.post("/{item_id}/edit")
async def update_vendor(item_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(login_required)):
    form = await request.form()
    verify_csrf(request, form.get("csrf"))
    if not can_write(user):
        raise ValidationError("You cannot edit vendors.")
    item = db.get(Vendor, item_id)
    if not item:
        raise ValidationError("Vendor not found.")
    item.name = str(form.get("name") or "").strip()
    item.name_bn = str(form.get("name_bn") or "").strip()
    item.vendor_type = str(form.get("vendor_type") or item.vendor_type)
    item.tin = str(form.get("tin") or "").strip()
    item.bin_number = str(form.get("bin_number") or "").strip()
    item.phone = str(form.get("phone") or "").strip()
    item.email = str(form.get("email") or "").strip()
    item.address = str(form.get("address") or "").strip()
    item.default_tds_percent = parse_money(str(form.get("default_tds_percent") or "0"), "TDS %")
    cat = str(form.get("default_tds_category_id") or "")
    item.default_tds_category_id = int(cat) if cat else None
    item.notes = str(form.get("notes") or "").strip()
    item.is_active = form.get("is_active") == "1"
    write_audit(db, user=user, action="EDIT", module="vendors", record_type="Vendor", record_id=item.id, document_no=item.code)
    db.commit()
    flash(request, "Vendor updated.")
    return RedirectResponse(f"/vendors/{item.id}", status_code=303)
