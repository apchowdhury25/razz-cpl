from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import can_config, can_write, login_required, verify_csrf
from app.exceptions import ValidationError
from app.helpers import flash, optional_int, parse_date, parse_money, require_date
from app.models import CompanySettings, TaxCategory, User
from app.money import money
from app.services.excel import excel_response
from app.services.reports import tds_rows, vat_rows
from app.web import company, render

router = APIRouter()


@router.get("/tax/settings")
def settings(request: Request, db: Session = Depends(get_db), user: User = Depends(login_required)):
    items = db.execute(select(TaxCategory).order_by(TaxCategory.tax_type, TaxCategory.code)).scalars().all()
    return render(request, db, "tax/settings.html", user, nav="tax_settings", items=items)


@router.post("/tax/settings/new")
def create_tax(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(login_required),
    csrf: str = Form(""),
    code: str = Form(...),
    name: str = Form(...),
    tax_type: str = Form(...),
    percent: str = Form(...),
    effective_date: str = Form(...),
    description: str = Form(""),
):
    verify_csrf(request, csrf)
    if not can_config(user) and not can_write(user):
        raise ValidationError("Not allowed.")
    if not can_config(user):
        raise ValidationError("Only administrators can change tax settings.")
    db.add(
        TaxCategory(
            code=code.strip().upper(),
            name=name.strip(),
            tax_type=tax_type,
            percent=parse_money(percent, "Percent"),
            effective_date=require_date(effective_date, "Effective date"),
            description=description,
            is_active=True,
        )
    )
    db.commit()
    flash(request, "Tax category saved. Historical transactions keep their original rates.")
    return RedirectResponse("/tax/settings", status_code=303)


@router.post("/tax/settings/{item_id}")
async def update_tax(item_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(login_required)):
    form = await request.form()
    verify_csrf(request, form.get("csrf"))
    if not can_config(user):
        raise ValidationError("Only administrators can change tax settings.")
    item = db.get(TaxCategory, item_id)
    if not item:
        raise ValidationError("Not found.")
    item.name = str(form.get("name") or item.name)
    item.percent = parse_money(str(form.get("percent") or item.percent), "Percent")
    item.description = str(form.get("description") or "")
    item.is_active = form.get("is_active") == "1"
    if form.get("effective_date"):
        item.effective_date = require_date(str(form.get("effective_date")), "Effective date")
    settings = db.execute(select(CompanySettings)).scalar_one_or_none()
    if settings and item.code == "VAT-STD":
        settings.default_vat_percent = item.percent
    if settings and item.code == "RET-STD":
        settings.default_retention_percent = item.percent
    db.commit()
    flash(request, "Tax category updated. Posted bills are unchanged.")
    return RedirectResponse("/tax/settings", status_code=303)


@router.get("/tax/vat")
def vat_report(request: Request, db: Session = Depends(get_db), user: User = Depends(login_required)):
    date_from = parse_date(request.query_params.get("date_from"))
    date_to = parse_date(request.query_params.get("date_to"))
    project_id = optional_int(request.query_params.get("project_id"))
    rows = vat_rows(db, date_from=date_from, date_to=date_to, project_id=project_id)
    total = money(sum((r.vat_amount for r in rows), 0))
    if request.query_params.get("export") == "1":
        return excel_response(
            title="VAT / Input VAT",
            headers=["Date", "Vendor", "Bill", "Mushak", "Taxable", "VAT %", "VAT"],
            rows=[[r.bill_date.strftime("%d-%m-%Y"), r.vendor.name if r.vendor else "", r.bill_no, r.mushak_ref, r.gross_amount, r.vat_percent, r.vat_amount] for r in rows],
            filename="VAT Report.xlsx",
            company=company(db).name if company(db) else "Razz CNPL",
        )
    return render(request, db, "tax/vat.html", user, nav="vat", rows=rows, total=total, date_from=date_from, date_to=date_to, project_id=project_id)


@router.get("/tax/tds")
def tds_report(request: Request, db: Session = Depends(get_db), user: User = Depends(login_required)):
    date_from = parse_date(request.query_params.get("date_from"))
    date_to = parse_date(request.query_params.get("date_to"))
    project_id = optional_int(request.query_params.get("project_id"))
    rows = tds_rows(db, date_from=date_from, date_to=date_to, project_id=project_id)
    total = money(sum((r.tds_amount for r in rows), 0))
    if request.query_params.get("export") == "1":
        return excel_response(
            title="TDS Payable",
            headers=["Date", "Vendor", "Bill", "Gross", "TDS %", "TDS", "Remitted", "Certificate"],
            rows=[[r.bill_date.strftime("%d-%m-%Y"), r.vendor.name if r.vendor else "", r.bill_no, r.gross_amount, r.tds_percent, r.tds_amount, "Yes" if r.tds_remitted else "No", r.tds_certificate_no] for r in rows],
            filename="TDS Payable.xlsx",
            company=company(db).name if company(db) else "Razz CNPL",
        )
    return render(request, db, "tax/tds.html", user, nav="tds", rows=rows, total=total, date_from=date_from, date_to=date_to, project_id=project_id)
