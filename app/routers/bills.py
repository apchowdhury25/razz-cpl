from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.deps import can_approve, can_reverse, can_write, login_required, verify_csrf
from app.exceptions import ValidationError
from app.helpers import flash, optional_int, paginate, parse_date, parse_money, require_date
from app.models import ChartOfAccount, DocStatus, TaxCategory, User, Vendor, VendorBill
from app.money import ZERO
from app.services.ap import (
    POSTED_AP,
    ap_aging,
    ap_totals,
    cancel_bill,
    create_bill,
    post_bill,
    remit_tds,
    settle_retention,
    transition_bill,
    vendor_ledger,
)
from app.services.ar import aging_totals
from app.services.excel import excel_response
from app.web import company, render

router = APIRouter()


@router.get("/bills")
def list_bills(request: Request, db: Session = Depends(get_db), user: User = Depends(login_required)):
    stmt = (
        select(VendorBill)
        .options(selectinload(VendorBill.vendor), selectinload(VendorBill.project))
        .order_by(VendorBill.id.desc())
    )
    q = request.query_params.get("q", "").strip()
    status = request.query_params.get("status", "")
    project_id = optional_int(request.query_params.get("project_id"))
    vendor_id = optional_int(request.query_params.get("vendor_id"))
    date_from = parse_date(request.query_params.get("date_from"))
    date_to = parse_date(request.query_params.get("date_to"))
    if q:
        stmt = stmt.where(VendorBill.bill_no.ilike(f"%{q}%") | VendorBill.vendor_bill_ref.ilike(f"%{q}%"))
    if status:
        stmt = stmt.where(VendorBill.status == status)
    if project_id:
        stmt = stmt.where(VendorBill.project_id == project_id)
    if vendor_id:
        stmt = stmt.where(VendorBill.vendor_id == vendor_id)
    if date_from:
        stmt = stmt.where(VendorBill.bill_date >= date_from)
    if date_to:
        stmt = stmt.where(VendorBill.bill_date <= date_to)
    page = paginate(db, stmt, int(request.query_params.get("page", 1)))
    totals = ap_totals(db, project_id=project_id, vendor_id=vendor_id)
    return render(
        request, db, "bills/list.html", user, nav="bills", page=page, q=q, status=status,
        project_id=project_id, vendor_id=vendor_id, date_from=date_from, date_to=date_to, totals=totals,
        vendors=db.execute(select(Vendor).order_by(Vendor.name)).scalars().all(),
    )


@router.get("/bills/new")
def new_form(request: Request, db: Session = Depends(get_db), user: User = Depends(login_required)):
    vendors = db.execute(select(Vendor).where(Vendor.is_active.is_(True)).order_by(Vendor.name)).scalars().all()
    accounts = db.execute(select(ChartOfAccount).where(ChartOfAccount.account_type == "EXPENSE", ChartOfAccount.is_active.is_(True)).order_by(ChartOfAccount.code)).scalars().all()
    cats = db.execute(select(TaxCategory).where(TaxCategory.tax_type == "TDS", TaxCategory.is_active.is_(True))).scalars().all()
    return render(request, db, "bills/form.html", user, nav="bills", vendors=vendors, accounts=accounts, tds_categories=cats, item=None)


@router.post("/bills/new")
def create(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(login_required),
    csrf: str = Form(""),
    bill_date: str = Form(...),
    due_date: str = Form(...),
    vendor_id: int = Form(...),
    project_id: str = Form(""),
    description: str = Form(""),
    gross_amount: str = Form(...),
    vat_percent: str = Form("15"),
    tds_percent: str = Form("0"),
    retention_percent: str = Form("0"),
    mushak_ref: str = Form(""),
    vendor_bill_ref: str = Form(""),
    cost_account_id: int = Form(...),
    tds_category_id: str = Form(""),
    notes: str = Form(""),
):
    verify_csrf(request, csrf)
    if not can_write(user):
        raise ValidationError("Not allowed.")
    item = create_bill(
        db,
        bill_date=require_date(bill_date, "Bill date"),
        due_date=require_date(due_date, "Due date"),
        vendor_id=vendor_id,
        project_id=int(project_id) if project_id else None,
        description=description,
        gross_amount=parse_money(gross_amount, "Gross"),
        vat_percent=parse_money(vat_percent, "VAT %"),
        tds_percent=parse_money(tds_percent, "TDS %"),
        retention_percent=parse_money(retention_percent, "Retention %"),
        mushak_ref=mushak_ref,
        vendor_bill_ref=vendor_bill_ref,
        cost_account_id=cost_account_id,
        tds_category_id=int(tds_category_id) if tds_category_id else None,
        notes=notes,
        user=user,
    )
    db.commit()
    flash(request, f"Bill {item.bill_no} saved as draft.")
    return RedirectResponse(f"/bills/{item.id}", status_code=303)


@router.get("/bills/{item_id}")
def detail(item_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(login_required)):
    item = db.execute(
        select(VendorBill)
        .options(selectinload(VendorBill.vendor), selectinload(VendorBill.project), selectinload(VendorBill.cost_account), selectinload(VendorBill.allocations))
        .where(VendorBill.id == item_id)
    ).scalar_one_or_none()
    if not item:
        raise ValidationError("Bill not found.")
    from app.models import MoneyAccount

    accounts = db.execute(select(MoneyAccount).where(MoneyAccount.is_active.is_(True))).scalars().all()
    return render(request, db, "bills/detail.html", user, nav="bills", item=item, accounts=accounts)


@router.get("/bills/{item_id}/voucher")
def voucher(item_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(login_required)):
    item = db.execute(
        select(VendorBill).options(selectinload(VendorBill.vendor), selectinload(VendorBill.project)).where(VendorBill.id == item_id)
    ).scalar_one_or_none()
    if not item:
        raise ValidationError("Bill not found.")
    return render(request, db, "vouchers/bill.html", user, nav="bills", item=item)


@router.post("/bills/{item_id}/{action}")
async def action(
    item_id: int,
    action: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(login_required),
):
    form = await request.form()
    verify_csrf(request, form.get("csrf"))
    item = db.get(VendorBill, item_id)
    if not item:
        raise ValidationError("Bill not found.")
    if action == "submit":
        if not can_write(user):
            raise ValidationError("Not allowed.")
        transition_bill(db, item, DocStatus.SUBMITTED.value, user)
    elif action == "approve":
        if not can_approve(user):
            raise ValidationError("Only managers can approve.")
        transition_bill(db, item, DocStatus.APPROVED.value, user)
    elif action == "post":
        if not can_write(user):
            raise ValidationError("Not allowed.")
        if item.status == DocStatus.DRAFT.value:
            item.status = DocStatus.APPROVED.value
        post_bill(db, item, user=user)
    elif action == "cancel":
        if item.status in POSTED_AP and not can_reverse(user):
            raise ValidationError("Only an administrator can reverse a posted bill.")
        if not can_write(user):
            raise ValidationError("Not allowed.")
        cancel_bill(db, item, user=user)
    elif action == "remit-tds":
        if not can_write(user):
            raise ValidationError("Not allowed.")
        remit_tds(
            db, item,
            remit_date=require_date(str(form.get("remit_date") or date.today().isoformat()), "Date"),
            money_account_id=int(form.get("money_account_id")),
            user=user,
            certificate_no=str(form.get("certificate_no") or ""),
        )
    elif action == "settle-retention":
        if not can_write(user):
            raise ValidationError("Not allowed.")
        settle_retention(
            db, item,
            settle_date=require_date(str(form.get("settle_date") or date.today().isoformat()), "Date"),
            money_account_id=int(form.get("money_account_id")),
            user=user,
        )
    else:
        raise ValidationError("Unknown action.")
    db.commit()
    flash(request, "Action completed.")
    return RedirectResponse(f"/bills/{item.id}", status_code=303)


@router.get("/ap/aging")
def aging(request: Request, db: Session = Depends(get_db), user: User = Depends(login_required)):
    as_of = parse_date(request.query_params.get("as_of")) or date.today()
    project_id = optional_int(request.query_params.get("project_id"))
    vendor_id = optional_int(request.query_params.get("vendor_id"))
    rows = ap_aging(db, as_of=as_of, project_id=project_id, vendor_id=vendor_id)
    totals = aging_totals(rows)
    if request.query_params.get("export") == "1":
        return excel_response(
            title="AP Aging",
            headers=["Vendor", "Bill", "Due date", "Days", "Bucket", "Outstanding"],
            rows=[[r["vendor"], r["bill_no"], r["due_date"].strftime("%d-%m-%Y"), r["days"], r["bucket"], r["outstanding"]] for r in rows],
            filename="AP Aging.xlsx",
            company=company(db).name if company(db) else "Razz CNPL",
            filters=f"As of {as_of.strftime('%d-%m-%Y')}",
        )
    return render(
        request, db, "bills/aging.html", user, nav="ap_aging", rows=rows, totals=totals, as_of=as_of,
        project_id=project_id, vendor_id=vendor_id,
        vendors=db.execute(select(Vendor).order_by(Vendor.name)).scalars().all(),
    )


@router.get("/ap/ledger")
def ledger(request: Request, db: Session = Depends(get_db), user: User = Depends(login_required)):
    vendor_id = optional_int(request.query_params.get("vendor_id"))
    date_from = parse_date(request.query_params.get("date_from"))
    date_to = parse_date(request.query_params.get("date_to"))
    vendors = db.execute(select(Vendor).order_by(Vendor.name)).scalars().all()
    entries = vendor_ledger(db, vendor_id, date_from=date_from, date_to=date_to) if vendor_id else []
    vendor = db.get(Vendor, vendor_id) if vendor_id else None
    if request.query_params.get("export") == "1" and vendor:
        return excel_response(
            title="Vendor Ledger",
            headers=["Date", "Document", "Description", "Debit", "Credit", "Balance"],
            rows=[[e["date"].strftime("%d-%m-%Y"), e["document"], e["description"], e["debit"], e["credit"], e["balance"]] for e in entries],
            filename="Vendor Ledger.xlsx",
            company=company(db).name if company(db) else "Razz CNPL",
            filters=vendor.name,
        )
    return render(
        request, db, "bills/ledger.html", user, nav="vendor_ledger", vendors=vendors, vendor=vendor,
        entries=entries, vendor_id=vendor_id, date_from=date_from, date_to=date_to,
        statement=request.query_params.get("statement") == "1",
    )


@router.get("/ap/outstanding")
def outstanding(request: Request, db: Session = Depends(get_db), user: User = Depends(login_required)):
    as_of = parse_date(request.query_params.get("as_of")) or date.today()
    rows = ap_aging(db, as_of=as_of)
    if request.query_params.get("overdue") == "1":
        rows = [r for r in rows if r["overdue"]]
    totals = aging_totals(rows)
    return render(request, db, "bills/outstanding.html", user, nav="bills", rows=rows, totals=totals, as_of=as_of)
