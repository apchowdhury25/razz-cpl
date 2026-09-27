from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.deps import can_reverse, can_write, login_required, verify_csrf
from app.exceptions import ValidationError
from app.helpers import flash, optional_int, paginate, parse_date, parse_money, require_date
from app.models import MoneyAccount, User, Vendor, VendorBill, VendorPayment
from app.money import money
from app.services.ap import POSTED_AP, cancel_payment, create_payment, post_payment, set_payment_allocations
from app.services.excel import excel_response
from app.web import company, render

router = APIRouter(prefix="/payments")


@router.get("")
def list_payments(request: Request, db: Session = Depends(get_db), user: User = Depends(login_required)):
    stmt = (
        select(VendorPayment)
        .options(selectinload(VendorPayment.vendor), selectinload(VendorPayment.money_account), selectinload(VendorPayment.project))
        .order_by(VendorPayment.id.desc())
    )
    q = request.query_params.get("q", "").strip()
    status = request.query_params.get("status", "")
    project_id = optional_int(request.query_params.get("project_id"))
    vendor_id = optional_int(request.query_params.get("vendor_id"))
    date_from = parse_date(request.query_params.get("date_from"))
    date_to = parse_date(request.query_params.get("date_to"))
    if q:
        stmt = stmt.where(VendorPayment.payment_no.ilike(f"%{q}%") | VendorPayment.reference_no.ilike(f"%{q}%"))
    if status:
        stmt = stmt.where(VendorPayment.status == status)
    if project_id:
        stmt = stmt.where(VendorPayment.project_id == project_id)
    if vendor_id:
        stmt = stmt.where(VendorPayment.vendor_id == vendor_id)
    if date_from:
        stmt = stmt.where(VendorPayment.payment_date >= date_from)
    if date_to:
        stmt = stmt.where(VendorPayment.payment_date <= date_to)
    page = paginate(db, stmt, int(request.query_params.get("page", 1)))
    if request.query_params.get("export") == "1":
        rows = db.execute(stmt).scalars().all()
        return excel_response(
            title="Payments Register",
            headers=["Payment", "Date", "Vendor", "Amount", "Method", "Status"],
            rows=[[r.payment_no, r.payment_date.strftime("%d-%m-%Y"), r.vendor.name if r.vendor else "", r.amount, r.payment_method, r.status] for r in rows],
            filename="Payments Register.xlsx",
            company=company(db).name if company(db) else "Razz CNPL",
        )
    return render(
        request, db, "payments/list.html", user, nav="payments", page=page, q=q, status=status,
        project_id=project_id, vendor_id=vendor_id, date_from=date_from, date_to=date_to,
        vendors=db.execute(select(Vendor).order_by(Vendor.name)).scalars().all(),
    )


@router.get("/new")
def new_form(request: Request, db: Session = Depends(get_db), user: User = Depends(login_required)):
    vendors = db.execute(select(Vendor).where(Vendor.is_active.is_(True)).order_by(Vendor.name)).scalars().all()
    accounts = db.execute(select(MoneyAccount).where(MoneyAccount.is_active.is_(True))).scalars().all()
    bills = db.execute(
        select(VendorBill).options(selectinload(VendorBill.vendor)).where(VendorBill.status.in_(POSTED_AP), VendorBill.outstanding_amount > 0)
    ).scalars().all()
    return render(request, db, "payments/form.html", user, nav="payments", vendors=vendors, accounts=accounts, bills=bills)


@router.post("/new")
async def create(request: Request, db: Session = Depends(get_db), user: User = Depends(login_required)):
    form = await request.form()
    verify_csrf(request, form.get("csrf"))
    if not can_write(user):
        raise ValidationError("Not allowed.")
    allocations = []
    for key in form.keys():
        if key.startswith("alloc_"):
            amt = money(form.get(key) or 0)
            if amt > 0:
                allocations.append({"bill_id": int(key.split("_", 1)[1]), "amount": amt})
    payment = create_payment(
        db,
        payment_date=require_date(str(form.get("payment_date")), "Payment date"),
        vendor_id=int(form.get("vendor_id")),
        amount=parse_money(str(form.get("amount")), "Amount"),
        money_account_id=int(form.get("money_account_id")),
        user=user,
        project_id=int(form.get("project_id")) if form.get("project_id") else None,
        payment_method=str(form.get("payment_method") or "BANK_TRANSFER"),
        reference_no=str(form.get("reference_no") or ""),
        notes=str(form.get("notes") or ""),
        is_advance=form.get("is_advance") == "1",
        allocations=allocations or None,
    )
    db.commit()
    flash(request, f"Payment {payment.payment_no} saved as draft.")
    return RedirectResponse(f"/payments/{payment.id}", status_code=303)


@router.get("/{item_id}")
def detail(item_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(login_required)):
    item = db.execute(
        select(VendorPayment)
        .options(
            selectinload(VendorPayment.vendor),
            selectinload(VendorPayment.project),
            selectinload(VendorPayment.money_account),
            selectinload(VendorPayment.allocations),
        )
        .where(VendorPayment.id == item_id)
    ).scalar_one_or_none()
    if not item:
        raise ValidationError("Payment not found.")
    open_bills = db.execute(
        select(VendorBill).where(
            VendorBill.vendor_id == item.vendor_id,
            VendorBill.status.in_(POSTED_AP),
            VendorBill.outstanding_amount > 0,
        )
    ).scalars().all()
    return render(request, db, "payments/detail.html", user, nav="payments", item=item, open_bills=open_bills)


@router.post("/{item_id}/allocate")
async def allocate(item_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(login_required)):
    form = await request.form()
    verify_csrf(request, form.get("csrf"))
    if not can_write(user):
        raise ValidationError("Not allowed.")
    item = db.get(VendorPayment, item_id)
    allocations = []
    for key in form.keys():
        if key.startswith("alloc_"):
            amt = money(form.get(key) or 0)
            if amt > 0:
                allocations.append({"bill_id": int(key.split("_", 1)[1]), "amount": amt})
    set_payment_allocations(db, item, allocations, allow_advance=form.get("is_advance") == "1")
    db.commit()
    flash(request, "Allocations saved.")
    return RedirectResponse(f"/payments/{item.id}", status_code=303)


@router.post("/{item_id}/post")
def post(item_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(login_required), csrf: str = Form("")):
    verify_csrf(request, csrf)
    if not can_write(user):
        raise ValidationError("Not allowed.")
    item = db.get(VendorPayment, item_id)
    post_payment(db, item, user=user)
    db.commit()
    flash(request, f"Payment {item.payment_no} posted.")
    return RedirectResponse(f"/payments/{item.id}", status_code=303)


@router.post("/{item_id}/cancel")
def cancel(item_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(login_required), csrf: str = Form("")):
    verify_csrf(request, csrf)
    item = db.get(VendorPayment, item_id)
    if item.status == "POSTED" and not can_reverse(user):
        raise ValidationError("Only an administrator can reverse a posted payment.")
    if not can_write(user):
        raise ValidationError("Not allowed.")
    cancel_payment(db, item, user=user)
    db.commit()
    flash(request, "Payment cancelled.")
    return RedirectResponse(f"/payments/{item.id}", status_code=303)


@router.get("/{item_id}/voucher")
def voucher(item_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(login_required)):
    item = db.execute(
        select(VendorPayment)
        .options(selectinload(VendorPayment.vendor), selectinload(VendorPayment.money_account), selectinload(VendorPayment.allocations))
        .where(VendorPayment.id == item_id)
    ).scalar_one_or_none()
    if not item:
        raise ValidationError("Payment not found.")
    return render(request, db, "vouchers/payment.html", user, nav="payments", item=item)
