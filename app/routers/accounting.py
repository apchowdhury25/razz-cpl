from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.deps import can_write, login_required, verify_csrf
from app.exceptions import ValidationError
from app.helpers import dmy, flash, optional_int, paginate, parse_date, parse_money, require_date
from app.models import ChartOfAccount, DocStatus, JournalEntry, JournalLine, User
from app.money import ZERO, money
from app.services.accounting import create_journal, general_ledger, trial_balance
from app.services.excel import excel_response
from app.web import company, render

router = APIRouter()


@router.get("/accounting/coa")
def coa(request: Request, db: Session = Depends(get_db), user: User = Depends(login_required)):
    items = db.execute(select(ChartOfAccount).order_by(ChartOfAccount.code)).scalars().all()
    return render(request, db, "accounting/coa.html", user, nav="coa", items=items)


@router.post("/accounting/coa/new")
def create_account(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(login_required),
    csrf: str = Form(""),
    code: str = Form(...),
    name: str = Form(...),
    name_bn: str = Form(""),
    account_type: str = Form(...),
    notes: str = Form(""),
):
    verify_csrf(request, csrf)
    if not can_write(user):
        raise ValidationError("Not allowed.")
    if db.execute(select(ChartOfAccount).where(ChartOfAccount.code == code.strip())).scalar_one_or_none():
        raise ValidationError("Account code already exists.")
    db.add(ChartOfAccount(code=code.strip(), name=name.strip(), name_bn=name_bn.strip(), account_type=account_type, notes=notes, is_active=True))
    db.commit()
    flash(request, "Account created.")
    return RedirectResponse("/accounting/coa", status_code=303)


@router.get("/accounting/journals")
def journals(request: Request, db: Session = Depends(get_db), user: User = Depends(login_required)):
    stmt = select(JournalEntry).options(selectinload(JournalEntry.project)).order_by(JournalEntry.id.desc())
    q = request.query_params.get("q", "").strip()
    status = request.query_params.get("status", "")
    date_from = parse_date(request.query_params.get("date_from"))
    date_to = parse_date(request.query_params.get("date_to"))
    if q:
        stmt = stmt.where(JournalEntry.entry_no.ilike(f"%{q}%") | JournalEntry.description.ilike(f"%{q}%"))
    if status:
        stmt = stmt.where(JournalEntry.status == status)
    if date_from:
        stmt = stmt.where(JournalEntry.entry_date >= date_from)
    if date_to:
        stmt = stmt.where(JournalEntry.entry_date <= date_to)
    page = paginate(db, stmt, int(request.query_params.get("page", 1)))
    return render(request, db, "accounting/journals.html", user, nav="journals", page=page, q=q, status=status, date_from=date_from, date_to=date_to)


@router.get("/accounting/journals/new")
def new_journal(request: Request, db: Session = Depends(get_db), user: User = Depends(login_required)):
    accounts = db.execute(select(ChartOfAccount).where(ChartOfAccount.is_active.is_(True)).order_by(ChartOfAccount.code)).scalars().all()
    return render(request, db, "accounting/journal_form.html", user, nav="journals", accounts=accounts)


@router.post("/accounting/journals/new")
async def create_manual(request: Request, db: Session = Depends(get_db), user: User = Depends(login_required)):
    form = await request.form()
    verify_csrf(request, form.get("csrf"))
    if not can_write(user):
        raise ValidationError("Not allowed.")
    lines = []
    i = 0
    while True:
        acc = form.get(f"account_id_{i}")
        if acc is None:
            break
        if acc:
            lines.append(
                {
                    "account_id": int(acc),
                    "project_id": int(form.get(f"project_id_{i}")) if form.get(f"project_id_{i}") else None,
                    "debit": parse_money(str(form.get(f"debit_{i}") or "0"), "Debit") if form.get(f"debit_{i}") else ZERO,
                    "credit": parse_money(str(form.get(f"credit_{i}") or "0"), "Credit") if form.get(f"credit_{i}") else ZERO,
                    "description": str(form.get(f"desc_{i}") or ""),
                }
            )
        i += 1
    entry = create_journal(
        db,
        entry_date=require_date(str(form.get("entry_date")), "Date"),
        description=str(form.get("description") or "Manual journal"),
        lines=lines,
        project_id=int(form.get("project_id")) if form.get("project_id") else None,
        user=user,
        status=DocStatus.POSTED.value if form.get("post_now") == "1" else DocStatus.DRAFT.value,
    )
    db.commit()
    flash(request, f"Journal {entry.entry_no} saved.")
    return RedirectResponse(f"/accounting/journals/{entry.id}", status_code=303)


@router.get("/accounting/journals/{item_id}")
def journal_detail(item_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(login_required)):
    item = db.execute(
        select(JournalEntry).options(selectinload(JournalEntry.lines).selectinload(JournalLine.account), selectinload(JournalEntry.project)).where(JournalEntry.id == item_id)
    ).scalar_one_or_none()
    if not item:
        raise ValidationError("Journal not found.")
    return render(request, db, "accounting/journal_detail.html", user, nav="journals", item=item)


@router.get("/accounting/gl")
def gl(request: Request, db: Session = Depends(get_db), user: User = Depends(login_required)):
    account_id = optional_int(request.query_params.get("account_id"))
    date_from = parse_date(request.query_params.get("date_from"))
    date_to = parse_date(request.query_params.get("date_to"))
    project_id = optional_int(request.query_params.get("project_id"))
    accounts = db.execute(select(ChartOfAccount).order_by(ChartOfAccount.code)).scalars().all()
    opening, lines = (ZERO, [])
    account = None
    if account_id:
        account = db.get(ChartOfAccount, account_id)
        opening, lines = general_ledger(db, account_id, date_from=date_from, date_to=date_to, project_id=project_id)
    if request.query_params.get("export") == "1" and account:
        return excel_response(
            title="General Ledger",
            headers=["Date", "Journal", "Document", "Description", "Debit", "Credit", "Balance"],
            rows=[[dmy(l["date"]), l["entry_no"], l["document"], l["description"], l["debit"], l["credit"], l["balance"]] for l in lines],
            filename="General Ledger.xlsx",
            company=company(db).name if company(db) else "Razz CNPL",
            filters=f"{account.code} {account.name}",
        )
    return render(
        request, db, "accounting/gl.html", user, nav="gl", accounts=accounts, account=account, account_id=account_id,
        opening=opening, lines=lines, date_from=date_from, date_to=date_to, project_id=project_id,
    )


@router.get("/accounting/trial-balance")
def tb(request: Request, db: Session = Depends(get_db), user: User = Depends(login_required)):
    date_from = parse_date(request.query_params.get("date_from"))
    date_to = parse_date(request.query_params.get("date_to"))
    project_id = optional_int(request.query_params.get("project_id"))
    rows = trial_balance(db, date_from=date_from, date_to=date_to, project_id=project_id)
    total_dr = money(sum((r["debit"] for r in rows), ZERO))
    total_cr = money(sum((r["credit"] for r in rows), ZERO))
    if request.query_params.get("export") == "1":
        data = [[r["code"], r["name"], r["debit"], r["credit"]] for r in rows]
        data.append(["", "TOTAL", total_dr, total_cr])
        return excel_response(
            title="Trial Balance",
            headers=["Code", "Account", "Debit", "Credit"],
            rows=data,
            filename="Trial Balance.xlsx",
            company=company(db).name if company(db) else "Razz CNPL",
        )
    return render(
        request, db, "accounting/trial_balance.html", user, nav="trial_balance", rows=rows,
        total_dr=total_dr, total_cr=total_cr, balanced=total_dr == total_cr,
        date_from=date_from, date_to=date_to, project_id=project_id,
    )
