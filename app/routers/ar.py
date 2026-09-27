from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.deps import can_approve, can_reverse, can_write, login_required, verify_csrf
from app.exceptions import ValidationError
from app.helpers import dmy, flash, optional_int, paginate, parse_date, parse_money, require_date
from app.models import Customer, CustomerCreditNote, CustomerInvoice, DocStatus, Unit, User
from app.money import ZERO
from app.services.ar import (
    POSTED_AR,
    ar_aging,
    ar_totals,
    aging_totals,
    cancel_invoice,
    create_invoice,
    customer_ledger,
    post_credit_note,
    post_invoice,
    transition_invoice,
)
from app.services.excel import excel_response
from app.services.numbering import next_number
from app.web import company, render

router = APIRouter()


@router.get("/ar/invoices")
def list_invoices(request: Request, db: Session = Depends(get_db), user: User = Depends(login_required)):
    stmt = (
        select(CustomerInvoice)
        .options(selectinload(CustomerInvoice.customer), selectinload(CustomerInvoice.project), selectinload(CustomerInvoice.unit))
        .order_by(CustomerInvoice.id.desc())
    )
    q = request.query_params.get("q", "").strip()
    status = request.query_params.get("status", "")
    project_id = optional_int(request.query_params.get("project_id"))
    customer_id = optional_int(request.query_params.get("customer_id"))
    date_from = parse_date(request.query_params.get("date_from"))
    date_to = parse_date(request.query_params.get("date_to"))
    if q:
        stmt = stmt.where(CustomerInvoice.invoice_no.ilike(f"%{q}%"))
    if status:
        stmt = stmt.where(CustomerInvoice.status == status)
    if project_id:
        stmt = stmt.where(CustomerInvoice.project_id == project_id)
    if customer_id:
        stmt = stmt.where(CustomerInvoice.customer_id == customer_id)
    if date_from:
        stmt = stmt.where(CustomerInvoice.invoice_date >= date_from)
    if date_to:
        stmt = stmt.where(CustomerInvoice.invoice_date <= date_to)
    page = paginate(db, stmt, int(request.query_params.get("page", 1)))
    totals = ar_totals(db, project_id=project_id, customer_id=customer_id)
    return render(
        request, db, "ar/invoices_list.html", user, nav="invoices", page=page, q=q, status=status,
        project_id=project_id, customer_id=customer_id, date_from=date_from, date_to=date_to, totals=totals,
        customers=db.execute(select(Customer).order_by(Customer.name)).scalars().all(),
    )


@router.get("/ar/invoices/new")
def new_invoice(request: Request, db: Session = Depends(get_db), user: User = Depends(login_required)):
    customers = db.execute(select(Customer).where(Customer.is_active.is_(True)).order_by(Customer.name)).scalars().all()
    units = db.execute(select(Unit).options(selectinload(Unit.project))).scalars().all()
    return render(request, db, "ar/invoice_form.html", user, nav="invoices", item=None, customers=customers, units=units)


@router.post("/ar/invoices/new")
def create(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(login_required),
    csrf: str = Form(""),
    invoice_date: str = Form(...),
    due_date: str = Form(...),
    customer_id: int = Form(...),
    project_id: str = Form(""),
    unit_id: str = Form(""),
    description: str = Form(""),
    amount: str = Form(...),
    vat_percent: str = Form("0"),
):
    verify_csrf(request, csrf)
    if not can_write(user):
        raise ValidationError("You cannot create invoices.")
    unit = db.get(Unit, int(unit_id)) if unit_id else None
    pid = int(project_id) if project_id else (unit.project_id if unit else None)
    item = create_invoice(
        db,
        invoice_date=require_date(invoice_date, "Invoice date"),
        due_date=require_date(due_date, "Due date"),
        customer_id=customer_id,
        project_id=pid,
        unit_id=unit.id if unit else None,
        description=description,
        amount=parse_money(amount, "Amount"),
        vat_percent=parse_money(vat_percent, "VAT %"),
        user=user,
    )
    db.commit()
    flash(request, f"Demand {item.invoice_no} saved as draft.")
    return RedirectResponse(f"/ar/invoices/{item.id}", status_code=303)


@router.get("/ar/invoices/{item_id}")
def invoice_detail(item_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(login_required)):
    item = db.execute(
        select(CustomerInvoice)
        .options(
            selectinload(CustomerInvoice.customer),
            selectinload(CustomerInvoice.project),
            selectinload(CustomerInvoice.unit),
            selectinload(CustomerInvoice.allocations),
        )
        .where(CustomerInvoice.id == item_id)
    ).scalar_one_or_none()
    if not item:
        raise ValidationError("Invoice not found.")
    return render(request, db, "ar/invoice_detail.html", user, nav="invoices", item=item)


@router.post("/ar/invoices/{item_id}/{action}")
def invoice_action(
    item_id: int,
    action: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(login_required),
    csrf: str = Form(""),
):
    verify_csrf(request, csrf)
    item = db.get(CustomerInvoice, item_id)
    if not item:
        raise ValidationError("Invoice not found.")
    if action == "submit":
        if not can_write(user):
            raise ValidationError("Not allowed.")
        transition_invoice(db, item, DocStatus.SUBMITTED.value, user)
    elif action == "approve":
        if not can_approve(user):
            raise ValidationError("Only managers can approve.")
        transition_invoice(db, item, DocStatus.APPROVED.value, user)
    elif action == "post":
        if not can_write(user):
            raise ValidationError("Not allowed.")
        if item.status == DocStatus.DRAFT.value:
            item.status = DocStatus.APPROVED.value
        post_invoice(db, item, user=user)
    elif action == "cancel":
        if not can_reverse(user) and item.status in POSTED_AR:
            raise ValidationError("Only an administrator can reverse a posted invoice.")
        if not can_write(user):
            raise ValidationError("Not allowed.")
        cancel_invoice(db, item, user=user)
    else:
        raise ValidationError("Unknown action.")
    db.commit()
    flash(request, "Action completed.")
    return RedirectResponse(f"/ar/invoices/{item.id}", status_code=303)


@router.get("/ar/aging")
def aging(request: Request, db: Session = Depends(get_db), user: User = Depends(login_required)):
    as_of = parse_date(request.query_params.get("as_of")) or date.today()
    project_id = optional_int(request.query_params.get("project_id"))
    customer_id = optional_int(request.query_params.get("customer_id"))
    rows = ar_aging(db, as_of=as_of, project_id=project_id, customer_id=customer_id)
    totals = aging_totals(rows)
    if request.query_params.get("export") == "1":
        return excel_response(
            title="AR Aging",
            headers=["Customer", "Invoice", "Due date", "Days", "Bucket", "Outstanding"],
            rows=[[r["customer"], r["invoice_no"], dmy(r["due_date"]), r["days"], r["bucket"], r["outstanding"]] for r in rows],
            filename="AR Aging.xlsx",
            company=company(db).name if company(db) else "Razz CNPL",
            filters=f"As of {dmy(as_of)}",
        )
    return render(
        request, db, "ar/aging.html", user, nav="ar_aging", rows=rows, totals=totals, as_of=as_of,
        project_id=project_id, customer_id=customer_id,
        customers=db.execute(select(Customer).order_by(Customer.name)).scalars().all(),
    )


@router.get("/ar/ledger")
def ledger(request: Request, db: Session = Depends(get_db), user: User = Depends(login_required)):
    customer_id = optional_int(request.query_params.get("customer_id"))
    date_from = parse_date(request.query_params.get("date_from"))
    date_to = parse_date(request.query_params.get("date_to"))
    customers = db.execute(select(Customer).order_by(Customer.name)).scalars().all()
    entries = customer_ledger(db, customer_id, date_from=date_from, date_to=date_to) if customer_id else []
    customer = db.get(Customer, customer_id) if customer_id else None
    if request.query_params.get("export") == "1" and customer:
        return excel_response(
            title="Customer Ledger",
            headers=["Date", "Document", "Description", "Debit", "Credit", "Balance"],
            rows=[[dmy(e["date"]), e["document"], e["description"], e["debit"], e["credit"], e["balance"]] for e in entries],
            filename="Customer Ledger.xlsx",
            company=company(db).name if company(db) else "Razz CNPL",
            filters=customer.name,
        )
    return render(
        request, db, "ar/ledger.html", user, nav="customer_ledger", customers=customers, customer=customer,
        entries=entries, customer_id=customer_id, date_from=date_from, date_to=date_to, statement=request.query_params.get("statement") == "1",
    )


@router.get("/ar/outstanding")
def outstanding(request: Request, db: Session = Depends(get_db), user: User = Depends(login_required)):
    as_of = parse_date(request.query_params.get("as_of")) or date.today()
    rows = [r for r in ar_aging(db, as_of=as_of) if r["outstanding"] > ZERO]
    overdue_only = request.query_params.get("overdue") == "1"
    if overdue_only:
        rows = [r for r in rows if r["overdue"]]
    totals = aging_totals(rows)
    return render(request, db, "ar/outstanding.html", user, nav="invoices", rows=rows, totals=totals, as_of=as_of, overdue_only=overdue_only)


@router.get("/ar/advances")
def advances(request: Request, db: Session = Depends(get_db), user: User = Depends(login_required)):
    from app.models import MoneyReceipt

    items = db.execute(
        select(MoneyReceipt)
        .options(selectinload(MoneyReceipt.customer))
        .where(MoneyReceipt.status == DocStatus.POSTED.value, MoneyReceipt.unallocated_amount > 0)
        .order_by(MoneyReceipt.id.desc())
    ).scalars().all()
    return render(request, db, "ar/advances.html", user, nav="receipts", items=items)


@router.get("/ar/credits")
def credits(request: Request, db: Session = Depends(get_db), user: User = Depends(login_required)):
    items = db.execute(
        select(CustomerCreditNote).options(selectinload(CustomerCreditNote.customer)).order_by(CustomerCreditNote.id.desc())
    ).scalars().all()
    customers = db.execute(select(Customer).order_by(Customer.name)).scalars().all()
    invoices = db.execute(select(CustomerInvoice).where(CustomerInvoice.status.in_(POSTED_AR))).scalars().all()
    return render(request, db, "ar/credits.html", user, nav="invoices", items=items, customers=customers, invoices=invoices)


@router.post("/ar/credits/new")
def create_credit(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(login_required),
    csrf: str = Form(""),
    credit_date: str = Form(...),
    customer_id: int = Form(...),
    invoice_id: str = Form(""),
    amount: str = Form(...),
    reason: str = Form(""),
):
    verify_csrf(request, csrf)
    if not can_write(user):
        raise ValidationError("Not allowed.")
    inv_id = int(invoice_id) if invoice_id else None
    inv = db.get(CustomerInvoice, inv_id) if inv_id else None
    note = CustomerCreditNote(
        credit_no=next_number(db, "CN", require_date(credit_date).year),
        credit_date=require_date(credit_date, "Date"),
        customer_id=customer_id,
        invoice_id=inv_id,
        project_id=inv.project_id if inv else None,
        amount=parse_money(amount, "Amount"),
        reason=reason,
        status=DocStatus.DRAFT.value,
        created_by_id=user.id,
    )
    db.add(note)
    db.flush()
    post_credit_note(db, note, user=user)
    db.commit()
    flash(request, f"Credit note {note.credit_no} posted.")
    return RedirectResponse("/ar/credits", status_code=303)
