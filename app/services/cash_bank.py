from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.exceptions import PostedDocumentError, ValidationError
from app.models import (
    BankTransfer,
    DocStatus,
    JournalLine,
    JournalEntry,
    JournalSource,
    MoneyAccount,
    OtherCashTxn,
    User,
)
from app.money import ZERO, money
from app.services.accounting import create_journal, reverse_journal
from app.services.audit import write_audit
from app.services.numbering import assert_unique, next_number


def money_account_balance(db: Session, account: MoneyAccount, *, as_of: date | None = None) -> Decimal:
    filters = [
        JournalLine.account_id == account.gl_account_id,
        JournalEntry.status == DocStatus.POSTED.value,
        JournalLine.entry_id == JournalEntry.id,
    ]
    if as_of:
        filters.append(JournalEntry.entry_date <= as_of)
    debit = money(db.execute(select(func.coalesce(func.sum(JournalLine.debit), 0)).where(*filters)).scalar())
    credit = money(db.execute(select(func.coalesce(func.sum(JournalLine.credit), 0)).where(*filters)).scalar())
    return money(debit - credit)


def cash_bank_totals(db: Session, *, as_of: date | None = None) -> dict[str, Decimal]:
    cash = ZERO
    bank = ZERO
    accounts = db.execute(select(MoneyAccount).where(MoneyAccount.is_active.is_(True))).scalars().all()
    details = []
    for acc in accounts:
        bal = money_account_balance(db, acc, as_of=as_of)
        details.append({"account": acc, "balance": bal})
        if acc.account_type == "CASH":
            cash = money(cash + bal)
        else:
            bank = money(bank + bal)
    return {"cash": cash, "bank": bank, "total": money(cash + bank), "accounts": details}


def create_transfer(
    db: Session,
    *,
    transfer_date: date,
    from_account_id: int,
    to_account_id: int,
    amount: Decimal,
    user: User | None,
    reference_no: str = "",
    notes: str = "",
    transfer_no: str | None = None,
    auto_post: bool = False,
) -> BankTransfer:
    amt = money(amount)
    if amt <= ZERO:
        raise ValidationError("Transfer amount must be greater than zero.")
    if from_account_id == to_account_id:
        raise ValidationError("Source and destination accounts must be different.")
    src = db.get(MoneyAccount, from_account_id)
    dst = db.get(MoneyAccount, to_account_id)
    if not src or not dst:
        raise ValidationError("Cash/bank account not found.")
    number = transfer_no or next_number(db, "TR", transfer_date.year)
    assert_unique(db, BankTransfer, "transfer_no", number)
    txn = BankTransfer(
        transfer_no=number,
        transfer_date=transfer_date,
        from_account_id=from_account_id,
        to_account_id=to_account_id,
        amount=amt,
        reference_no=reference_no,
        notes=notes,
        status=DocStatus.DRAFT.value,
        created_by_id=user.id if user else None,
    )
    db.add(txn)
    db.flush()
    write_audit(db, user=user, action="CREATE", module="cash", record_type="BankTransfer", record_id=txn.id, document_no=txn.transfer_no)
    if auto_post:
        post_transfer(db, txn, user=user)
    return txn


def post_transfer(db: Session, txn: BankTransfer, *, user: User | None) -> None:
    if txn.status == DocStatus.POSTED.value:
        raise PostedDocumentError("Transfer already posted.")
    src = db.get(MoneyAccount, txn.from_account_id)
    dst = db.get(MoneyAccount, txn.to_account_id)
    journal = create_journal(
        db,
        entry_date=txn.transfer_date,
        description=f"Transfer {txn.transfer_no}: {src.name} → {dst.name}",
        lines=[
            {"account_id": dst.gl_account_id, "debit": txn.amount, "credit": ZERO, "description": txn.transfer_no},
            {"account_id": src.gl_account_id, "debit": ZERO, "credit": txn.amount, "description": txn.transfer_no},
        ],
        source_module=JournalSource.TRANSFER.value,
        source_document=txn.transfer_no,
        source_id=txn.id,
        user=user,
    )
    txn.journal_id = journal.id
    txn.status = DocStatus.POSTED.value
    write_audit(db, user=user, action="POST", module="cash", record_type="BankTransfer", record_id=txn.id, document_no=txn.transfer_no)


def cancel_transfer(db: Session, txn: BankTransfer, *, user: User | None, cancel_date: date | None = None) -> None:
    if txn.status == DocStatus.CANCELLED.value:
        raise ValidationError("Already cancelled.")
    if txn.status == DocStatus.POSTED.value and txn.journal_id:
        journal = db.get(JournalEntry, txn.journal_id)
        if journal:
            reverse_journal(db, journal, reversal_date=cancel_date or date.today(), user=user, reason=f"Cancel {txn.transfer_no}")
    txn.status = DocStatus.CANCELLED.value
    write_audit(db, user=user, action="CANCEL", module="cash", record_type="BankTransfer", record_id=txn.id, document_no=txn.transfer_no)


def create_other_txn(
    db: Session,
    *,
    txn_date: date,
    direction: str,
    money_account_id: int,
    gl_account_id: int,
    amount: Decimal,
    user: User | None,
    project_id: int | None = None,
    payee_name: str = "",
    payment_method: str = "CASH",
    reference_no: str = "",
    description: str = "",
    auto_post: bool = False,
) -> OtherCashTxn:
    amt = money(amount)
    if amt <= ZERO:
        raise ValidationError("Amount must be greater than zero.")
    if direction not in ("IN", "OUT"):
        raise ValidationError("Direction must be IN or OUT.")
    doc_type = "OR" if direction == "IN" else "OP"
    number = next_number(db, doc_type, txn_date.year)
    txn = OtherCashTxn(
        txn_no=number,
        txn_date=txn_date,
        direction=direction,
        money_account_id=money_account_id,
        gl_account_id=gl_account_id,
        project_id=project_id,
        payee_name=payee_name,
        amount=amt,
        payment_method=payment_method,
        reference_no=reference_no,
        description=description,
        status=DocStatus.DRAFT.value,
        created_by_id=user.id if user else None,
    )
    db.add(txn)
    db.flush()
    write_audit(db, user=user, action="CREATE", module="cash", record_type="OtherCashTxn", record_id=txn.id, document_no=txn.txn_no)
    if auto_post:
        post_other_txn(db, txn, user=user)
    return txn


def post_other_txn(db: Session, txn: OtherCashTxn, *, user: User | None) -> None:
    if txn.status == DocStatus.POSTED.value:
        raise PostedDocumentError("Already posted.")
    money_acc = db.get(MoneyAccount, txn.money_account_id)
    if txn.direction == "IN":
        lines = [
            {"account_id": money_acc.gl_account_id, "project_id": txn.project_id, "debit": txn.amount, "credit": ZERO, "description": txn.txn_no},
            {"account_id": txn.gl_account_id, "project_id": txn.project_id, "debit": ZERO, "credit": txn.amount, "description": txn.txn_no},
        ]
        source = JournalSource.OTHER_RECEIPT.value
    else:
        lines = [
            {"account_id": txn.gl_account_id, "project_id": txn.project_id, "debit": txn.amount, "credit": ZERO, "description": txn.txn_no},
            {"account_id": money_acc.gl_account_id, "project_id": txn.project_id, "debit": ZERO, "credit": txn.amount, "description": txn.txn_no},
        ]
        source = JournalSource.OTHER_PAYMENT.value
    journal = create_journal(
        db,
        entry_date=txn.txn_date,
        description=txn.description or txn.txn_no,
        lines=lines,
        source_module=source,
        source_document=txn.txn_no,
        source_id=txn.id,
        project_id=txn.project_id,
        user=user,
    )
    txn.journal_id = journal.id
    txn.status = DocStatus.POSTED.value
    write_audit(db, user=user, action="POST", module="cash", record_type="OtherCashTxn", record_id=txn.id, document_no=txn.txn_no)


def cash_book(db: Session, account: MoneyAccount, *, date_from: date | None, date_to: date | None):
    from app.services.accounting import general_ledger

    return general_ledger(db, account.gl_account_id, date_from=date_from, date_to=date_to)
