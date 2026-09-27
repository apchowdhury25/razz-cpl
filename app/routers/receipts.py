from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.deps import can_reverse, can_write, login_required, verify_csrf
from app.exceptions import ValidationError
from app.helpers import dmy, flash, optional_int, paginate, parse_date, parse_money, require_date
from app.models import Customer, CustomerInvoice, DocStatus, MoneyAccount, MoneyReceipt, User
from app.money import money
from app.services.ar import POSTED_AR, cancel_receipt, create_receipt, post_receipt, set_receipt_allocations
from app.services.excel import excel_response
from app.web import company, render

router = APIRouter(prefix="/receipts")


@router.get("")
def list_receipts(request: Request, db: Session = Depends(get_db), user: User = Depends(login_required)):
    stmt = (
        select(MoneyReceipt)
        .options(selectinload(MoneyReceipt.customer), selectinload(MoneyReceipt.project), selectinload(MoneyReceipt.money_account))
        .order_by(MoneyReceipt.id.desc())
    )
    q = request.query_params.get("q", "").strip()
    status = request.query_params.get("status", "")
    project_id = optional_int(request.query_params.get("project_id"))
    customer_id = optional_int(request.query_params.get("customer_id"))
    date_from = parse_date(request.query_params.get("date_from"))
    date_to = parse_date(request.query_params.get("date_to"))
    method = request.query_params.get("payment_method", "")
    if q:
        stmt = stmt.where(MoneyReceipt.receipt_no.ilike(f"%{q}%") | MoneyReceipt.reference_no.ilike(f"%{q}%"))
    if status:
        stmt = stmt.where(MoneyReceipt.status == status)
    if project_id:
        stmt = stmt.where(MoneyReceipt.project_id == project_id)
    if customer_id:
        stmt = stmt.where(MoneyReceipt.customer_id == customer_id)
    if date_from:
        stmt = stmt.where(MoneyReceipt.receipt_date >= date_from)
    if date_to:
        stmt = stmt.where(MoneyReceipt.receipt_date <= date_to)
    if method:
        stmt = stmt.where(MoneyReceipt.payment_method == method)
    page = paginate(db, stmt, int(request.query_params.get("page", 1)))
    if request.query_params.get("export") == "1":
        rows = db.execute(stmt).scalars().all()
        return excel_response(
            title="Receipts Register",
            headers=["Receipt", "Date", "Customer", "Amount", "Method", "Status"],
            rows=[[r.receipt_no, dmy(r.receipt_date), r.customer.name if r.customer else "", r.amount, r.payment_method, r.status] for r in rows],
            filename="Receipts Register.xlsx",
            company=company(db).name if company(db) else "Razz CNPL",
        )
    return render(
        request, db, "receipts/list.html", user, nav="receipts", page=page, q=q, status=status,
        project_id=project_id, customer_id=customer_id, date_from=date_from, date_to=date_to, method=method,
        customers=db.execute(select(Customer).order_by(Customer.name)).scalars().all(),
    )


@router.get("/new")
def new_form(request: Request, db: Session = Depends(get_db), user: User = Depends(login_required)):
    customers = db.execute(select(Customer).where(Customer.is_active.is_(True)).order_by(Customer.name)).scalars().all()
    accounts = db.execute(select(MoneyAccount).where(MoneyAccount.is_active.is_(True))).scalars().all()
    invoices = db.execute(
        select(CustomerInvoice).options(selectinload(CustomerInvoice.customer)).where(CustomerInvoice.status.in_(POSTED_AR), CustomerInvoice.outstanding_amount > 0)
    ).scalars().all()
    return render(request, db, "receipts/form.html", user, nav="receipts", customers=customers, accounts=accounts, invoices=invoices)


@router.post("/new")
async def create(request: Request, db: Session = Depends(get_db), user: User = Depends(login_required)):
    form = await request.form()
    verify_csrf(request, form.get("csrf"))
    if not can_write(user):
        raise ValidationError("Not allowed.")
    customer_id = int(form.get("customer_id"))
    allocations = []
    for key in form.keys():
        if key.startswith("alloc_"):
            inv_id = int(key.split("_", 1)[1])
            amt = money(form.get(key) or 0)
            if amt > 0:
                allocations.append({"invoice_id": inv_id, "amount": amt})
    is_advance = form.get("is_advance") == "1"
    receipt = create_receipt(
        db,
        receipt_date=require_date(str(form.get("receipt_date")), "Receipt date"),
        customer_id=customer_id,
        amount=parse_money(str(form.get("amount")), "Amount"),
        money_account_id=int(form.get("money_account_id")),
        user=user,
        project_id=int(form.get("project_id")) if form.get("project_id") else None,
        payment_method=str(form.get("payment_method") or "BANK_TRANSFER"),
        reference_no=str(form.get("reference_no") or ""),
        notes=str(form.get("notes") or ""),
        received_by=str(form.get("received_by") or user.full_name),
        is_advance=is_advance,
        allocations=allocations or None,
    )
    db.commit()
    flash(request, f"Receipt {receipt.receipt_no} saved as draft.")
    return RedirectResponse(f"/receipts/{receipt.id}", status_code=303)


@router.get("/{item_id}")
def detail(item_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(login_required)):
    item = db.execute(
        select(MoneyReceipt)
        .options(
            selectinload(MoneyReceipt.customer),
            selectinload(MoneyReceipt.project),
            selectinload(MoneyReceipt.money_account),
            selectinload(MoneyReceipt.allocations),
        )
        .where(MoneyReceipt.id == item_id)
    ).scalar_one_or_none()
    if not item:
        raise ValidationError("Receipt not found.")
    open_invoices = db.execute(
        select(CustomerInvoice).where(
            CustomerInvoice.customer_id == item.customer_id,
            CustomerInvoice.status.in_(POSTED_AR),
            CustomerInvoice.outstanding_amount > 0,
        )
    ).scalars().all()
    return render(request, db, "receipts/detail.html", user, nav="receipts", item=item, open_invoices=open_invoices)


@router.post("/{item_id}/allocate")
async def allocate(item_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(login_required)):
    form = await request.form()
    verify_csrf(request, form.get("csrf"))
    if not can_write(user):
        raise ValidationError("Not allowed.")
    item = db.get(MoneyReceipt, item_id)
    allocations = []
    for key in form.keys():
        if key.startswith("alloc_"):
            amt = money(form.get(key) or 0)
            if amt > 0:
                allocations.append({"invoice_id": int(key.split("_", 1)[1]), "amount": amt})
    set_receipt_allocations(db, item, allocations, allow_advance=form.get("is_advance") == "1")
    db.commit()
    flash(request, "Allocations saved.")
    return RedirectResponse(f"/receipts/{item.id}", status_code=303)


@router.post("/{item_id}/post")
def post(item_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(login_required), csrf: str = Form("")):
    verify_csrf(request, csrf)
    if not can_write(user):
        raise ValidationError("Not allowed.")
    item = db.get(MoneyReceipt, item_id)
    post_receipt(db, item, user=user)
    db.commit()
    flash(request, f"Receipt {item.receipt_no} posted.")
    return RedirectResponse(f"/receipts/{item.id}", status_code=303)


@router.post("/{item_id}/cancel")
def cancel(item_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(login_required), csrf: str = Form("")):
    verify_csrf(request, csrf)
    item = db.get(MoneyReceipt, item_id)
    if item.status == DocStatus.POSTED.value and not can_reverse(user):
        raise ValidationError("Only an administrator can reverse a posted receipt.")
    if not can_write(user):
        raise ValidationError("Not allowed.")
    cancel_receipt(db, item, user=user)
    db.commit()
    flash(request, "Receipt cancelled.")
    return RedirectResponse(f"/receipts/{item.id}", status_code=303)


@router.get("/{item_id}/voucher")
def voucher(item_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(login_required)):
    item = db.execute(
        select(MoneyReceipt)
        .options(selectinload(MoneyReceipt.customer), selectinload(MoneyReceipt.project), selectinload(MoneyReceipt.unit), selectinload(MoneyReceipt.money_account))
        .where(MoneyReceipt.id == item_id)
    ).scalar_one_or_none()
    if not item:
        raise ValidationError("Receipt not found.")
    return render(request, db, "vouchers/receipt.html", user, nav="receipts", item=item)
