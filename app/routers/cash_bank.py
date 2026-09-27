from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.deps import can_write, login_required, verify_csrf
from app.exceptions import ValidationError
from app.helpers import dmy, flash, optional_int, parse_date, parse_money, require_date
from app.models import BankTransfer, ChartOfAccount, MoneyAccount, OtherCashTxn, User
from app.services.cash_bank import (
    cancel_transfer,
    cash_bank_totals,
    create_other_txn,
    create_transfer,
    money_account_balance,
    post_other_txn,
    post_transfer,
)
from app.services.excel import excel_response
from app.web import company, render

router = APIRouter()


@router.get("/cash/accounts")
def accounts(request: Request, db: Session = Depends(get_db), user: User = Depends(login_required)):
    data = cash_bank_totals(db)
    gls = db.execute(select(ChartOfAccount).where(ChartOfAccount.account_type == "ASSET").order_by(ChartOfAccount.code)).scalars().all()
    return render(request, db, "cash/accounts.html", user, nav="cash", data=data, gls=gls)


@router.post("/cash/accounts/new")
def create_account(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(login_required),
    csrf: str = Form(""),
    name: str = Form(...),
    account_type: str = Form(...),
    bank_name: str = Form(""),
    account_number: str = Form(""),
    gl_account_id: int = Form(...),
    opening_balance: str = Form("0"),
    opening_date: str = Form(...),
):
    verify_csrf(request, csrf)
    if not can_write(user):
        raise ValidationError("Not allowed.")
    db.add(
        MoneyAccount(
            name=name.strip(),
            account_type=account_type,
            bank_name=bank_name.strip(),
            account_number=account_number.strip(),
            gl_account_id=gl_account_id,
            opening_balance=parse_money(opening_balance, "Opening"),
            opening_date=require_date(opening_date, "Opening date"),
            is_active=True,
        )
    )
    db.commit()
    flash(request, "Cash/bank account saved.")
    return RedirectResponse("/cash/accounts", status_code=303)


@router.get("/cash/transfers")
def transfers(request: Request, db: Session = Depends(get_db), user: User = Depends(login_required)):
    items = db.execute(
        select(BankTransfer).options(selectinload(BankTransfer.from_account), selectinload(BankTransfer.to_account)).order_by(BankTransfer.id.desc())
    ).scalars().all()
    accounts = db.execute(select(MoneyAccount).where(MoneyAccount.is_active.is_(True))).scalars().all()
    return render(request, db, "cash/transfers.html", user, nav="cash", items=items, accounts=accounts)


@router.post("/cash/transfers/new")
def new_transfer(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(login_required),
    csrf: str = Form(""),
    transfer_date: str = Form(...),
    from_account_id: int = Form(...),
    to_account_id: int = Form(...),
    amount: str = Form(...),
    reference_no: str = Form(""),
    notes: str = Form(""),
):
    verify_csrf(request, csrf)
    if not can_write(user):
        raise ValidationError("Not allowed.")
    txn = create_transfer(
        db,
        transfer_date=require_date(transfer_date, "Date"),
        from_account_id=from_account_id,
        to_account_id=to_account_id,
        amount=parse_money(amount, "Amount"),
        user=user,
        reference_no=reference_no,
        notes=notes,
        auto_post=True,
    )
    db.commit()
    flash(request, f"Transfer {txn.transfer_no} posted.")
    return RedirectResponse("/cash/transfers", status_code=303)


@router.post("/cash/transfers/{item_id}/cancel")
def cancel(item_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(login_required), csrf: str = Form("")):
    verify_csrf(request, csrf)
    txn = db.get(BankTransfer, item_id)
    cancel_transfer(db, txn, user=user)
    db.commit()
    flash(request, "Transfer cancelled.")
    return RedirectResponse("/cash/transfers", status_code=303)


@router.get("/cash/other")
def other(request: Request, db: Session = Depends(get_db), user: User = Depends(login_required)):
    items = db.execute(
        select(OtherCashTxn).options(selectinload(OtherCashTxn.money_account), selectinload(OtherCashTxn.gl_account)).order_by(OtherCashTxn.id.desc())
    ).scalars().all()
    accounts = db.execute(select(MoneyAccount).where(MoneyAccount.is_active.is_(True))).scalars().all()
    gls = db.execute(select(ChartOfAccount).where(ChartOfAccount.is_active.is_(True)).order_by(ChartOfAccount.code)).scalars().all()
    return render(request, db, "cash/other.html", user, nav="cash", items=items, accounts=accounts, gls=gls)


@router.post("/cash/other/new")
def create_other(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(login_required),
    csrf: str = Form(""),
    txn_date: str = Form(...),
    direction: str = Form(...),
    money_account_id: int = Form(...),
    gl_account_id: int = Form(...),
    amount: str = Form(...),
    payee_name: str = Form(""),
    payment_method: str = Form("CASH"),
    reference_no: str = Form(""),
    description: str = Form(""),
    project_id: str = Form(""),
):
    verify_csrf(request, csrf)
    if not can_write(user):
        raise ValidationError("Not allowed.")
    txn = create_other_txn(
        db,
        txn_date=require_date(txn_date, "Date"),
        direction=direction,
        money_account_id=money_account_id,
        gl_account_id=gl_account_id,
        amount=parse_money(amount, "Amount"),
        user=user,
        project_id=int(project_id) if project_id else None,
        payee_name=payee_name,
        payment_method=payment_method,
        reference_no=reference_no,
        description=description,
        auto_post=True,
    )
    db.commit()
    flash(request, f"{txn.txn_no} posted.")
    return RedirectResponse("/cash/other", status_code=303)


@router.get("/cash/book")
def cash_book(request: Request, db: Session = Depends(get_db), user: User = Depends(login_required)):
    return _book(request, db, user, "CASH", "Cash Book.xlsx", "cash/book.html", "cash_book")


@router.get("/cash/bank-book")
def bank_book(request: Request, db: Session = Depends(get_db), user: User = Depends(login_required)):
    return _book(request, db, user, "BANK", "Bank Book.xlsx", "cash/book.html", "bank_book")


def _book(request, db, user, acc_type, filename, template, nav):
    from app.services.accounting import general_ledger

    accounts = db.execute(select(MoneyAccount).where(MoneyAccount.account_type == acc_type, MoneyAccount.is_active.is_(True))).scalars().all()
    account_id = optional_int(request.query_params.get("account_id")) or (accounts[0].id if accounts else None)
    date_from = parse_date(request.query_params.get("date_from"))
    date_to = parse_date(request.query_params.get("date_to"))
    account = db.get(MoneyAccount, account_id) if account_id else None
    opening, lines = ([], [])
    if account:
        opening, lines = general_ledger(db, account.gl_account_id, date_from=date_from, date_to=date_to)
    if request.query_params.get("export") == "1" and account:
        return excel_response(
            title=f"{acc_type.title()} Book",
            headers=["Date", "Journal", "Document", "Description", "Debit", "Credit", "Balance"],
            rows=[[dmy(l["date"]), l["entry_no"], l["document"], l["description"], l["debit"], l["credit"], l["balance"]] for l in lines],
            filename=filename,
            company=company(db).name if company(db) else "Razz CNPL",
            filters=account.name,
        )
    return render(
        request, db, template, user, nav=nav, accounts=accounts, account=account, opening=opening, lines=lines,
        date_from=date_from, date_to=date_to, title="Cash Book" if acc_type == "CASH" else "Bank Book",
    )
