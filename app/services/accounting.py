from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.exceptions import LockedPeriodError, UnbalancedJournalError, ValidationError
from app.models import (
    AccountingPeriod,
    ChartOfAccount,
    DocStatus,
    JournalEntry,
    JournalLine,
    JournalSource,
    User,
    UserRole,
)
from app.money import ZERO, money
from app.services.numbering import next_number


def get_system_account(db: Session, key: str) -> ChartOfAccount:
    acc = db.execute(select(ChartOfAccount).where(ChartOfAccount.system_key == key)).scalar_one_or_none()
    if not acc:
        raise ValidationError(f"System account '{key}' is not configured.")
    return acc


def assert_period_open(db: Session, txn_date: date, user: User | None) -> None:
    period = db.execute(
        select(AccountingPeriod).where(
            AccountingPeriod.start_date <= txn_date,
            AccountingPeriod.end_date >= txn_date,
        )
    ).scalar_one_or_none()
    if period and period.is_locked:
        if user is None or user.role != UserRole.ADMIN.value:
            raise LockedPeriodError(
                f"Accounting period {period.code} is locked. Transactions cannot be posted."
            )


def create_journal(
    db: Session,
    *,
    entry_date: date,
    description: str,
    lines: Iterable[dict[str, Any]],
    source_module: str = JournalSource.MANUAL.value,
    source_document: str = "",
    source_id: int | None = None,
    project_id: int | None = None,
    user: User | None = None,
    status: str = DocStatus.POSTED.value,
    year: int | None = None,
) -> JournalEntry:
    prepared: list[dict[str, Any]] = []
    total_dr = ZERO
    total_cr = ZERO
    for raw in lines:
        debit = money(raw.get("debit") or 0)
        credit = money(raw.get("credit") or 0)
        if debit < 0 or credit < 0:
            raise ValidationError("Journal line amounts cannot be negative.")
        if debit > 0 and credit > 0:
            raise ValidationError("A journal line cannot have both debit and credit.")
        if debit == 0 and credit == 0:
            continue
        account_id = raw.get("account_id")
        if not account_id:
            raise ValidationError("Journal line is missing an account.")
        prepared.append(
            {
                "account_id": int(account_id),
                "project_id": raw.get("project_id"),
                "debit": debit,
                "credit": credit,
                "description": raw.get("description") or "",
            }
        )
        total_dr = money(total_dr + debit)
        total_cr = money(total_cr + credit)

    if not prepared:
        raise UnbalancedJournalError("Journal entry has no lines.")
    if total_dr != total_cr:
        raise UnbalancedJournalError(
            f"Unbalanced journal: debit {total_dr} does not equal credit {total_cr}."
        )

    if status == DocStatus.POSTED.value:
        assert_period_open(db, entry_date, user)

    year = year or entry_date.year
    entry = JournalEntry(
        entry_no=next_number(db, "JV", year),
        entry_date=entry_date,
        description=description,
        source_module=source_module,
        source_document=source_document,
        source_id=source_id,
        project_id=project_id,
        total_debit=total_dr,
        total_credit=total_cr,
        status=status,
        created_by_id=user.id if user else None,
        posted_by_id=user.id if user and status == DocStatus.POSTED.value else None,
        posted_date=entry_date if status == DocStatus.POSTED.value else None,
    )
    db.add(entry)
    db.flush()
    for line in prepared:
        db.add(JournalLine(entry_id=entry.id, **line))
    db.flush()
    return entry


def reverse_journal(
    db: Session,
    original: JournalEntry,
    *,
    reversal_date: date,
    user: User | None,
    reason: str = "",
) -> JournalEntry:
    if original.status == DocStatus.CANCELLED.value:
        raise ValidationError("Journal is already reversed.")
    db.refresh(original, attribute_names=["lines"])
    lines = [
        {
            "account_id": line.account_id,
            "project_id": line.project_id,
            "debit": line.credit,
            "credit": line.debit,
            "description": f"Reversal of {original.entry_no}",
        }
        for line in original.lines
    ]
    reversal = create_journal(
        db,
        entry_date=reversal_date,
        description=reason or f"Reversal of {original.entry_no}",
        lines=lines,
        source_module=JournalSource.REVERSAL.value,
        source_document=original.entry_no,
        source_id=original.id,
        project_id=original.project_id,
        user=user,
    )
    reversal.reversal_of_id = original.id
    original.status = DocStatus.CANCELLED.value
    db.flush()
    return reversal


def account_balance(
    db: Session,
    account_id: int,
    *,
    as_of: date | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    project_id: int | None = None,
) -> dict[str, Decimal]:
    filters = [
        JournalLine.account_id == account_id,
        JournalEntry.status == DocStatus.POSTED.value,
        JournalLine.entry_id == JournalEntry.id,
    ]
    if as_of:
        filters.append(JournalEntry.entry_date <= as_of)
    if date_from:
        filters.append(JournalEntry.entry_date >= date_from)
    if date_to:
        filters.append(JournalEntry.entry_date <= date_to)
    if project_id:
        filters.append(JournalLine.project_id == project_id)
    debit = db.execute(select(func.coalesce(func.sum(JournalLine.debit), 0)).where(*filters)).scalar()
    credit = db.execute(select(func.coalesce(func.sum(JournalLine.credit), 0)).where(*filters)).scalar()
    return {"debit": money(debit), "credit": money(credit), "balance": money(Decimal(str(debit)) - Decimal(str(credit)))}


def trial_balance(
    db: Session,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    project_id: int | None = None,
) -> list[dict[str, Any]]:
    filters = [JournalEntry.status == DocStatus.POSTED.value, JournalLine.entry_id == JournalEntry.id]
    if date_from:
        filters.append(JournalEntry.entry_date >= date_from)
    if date_to:
        filters.append(JournalEntry.entry_date <= date_to)
    if project_id:
        filters.append(JournalLine.project_id == project_id)
    rows = db.execute(
        select(
            ChartOfAccount.id,
            ChartOfAccount.code,
            ChartOfAccount.name,
            ChartOfAccount.account_type,
            func.coalesce(func.sum(JournalLine.debit), 0),
            func.coalesce(func.sum(JournalLine.credit), 0),
        )
        .join(JournalLine, JournalLine.account_id == ChartOfAccount.id)
        .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
        .where(*filters)
        .group_by(ChartOfAccount.id, ChartOfAccount.code, ChartOfAccount.name, ChartOfAccount.account_type)
        .order_by(ChartOfAccount.code)
    ).all()
    result = []
    for acc_id, code, name, acc_type, debit, credit in rows:
        dr = money(debit)
        cr = money(credit)
        if dr == 0 and cr == 0:
            continue
        net_dr = money(dr - cr) if dr >= cr else ZERO
        net_cr = money(cr - dr) if cr > dr else ZERO
        result.append(
            {
                "account_id": acc_id,
                "code": code,
                "name": name,
                "account_type": acc_type,
                "debit": net_dr,
                "credit": net_cr,
                "raw_debit": dr,
                "raw_credit": cr,
            }
        )
    return result


def general_ledger(
    db: Session,
    account_id: int,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    project_id: int | None = None,
) -> tuple[Decimal, list[dict[str, Any]]]:
    opening_filters = [
        JournalLine.account_id == account_id,
        JournalEntry.status == DocStatus.POSTED.value,
        JournalLine.entry_id == JournalEntry.id,
    ]
    if date_from:
        opening_filters.append(JournalEntry.entry_date < date_from)
    if project_id:
        opening_filters.append(JournalLine.project_id == project_id)
    if date_from:
        open_dr = money(db.execute(select(func.coalesce(func.sum(JournalLine.debit), 0)).where(*opening_filters)).scalar())
        open_cr = money(db.execute(select(func.coalesce(func.sum(JournalLine.credit), 0)).where(*opening_filters)).scalar())
        opening = money(open_dr - open_cr)
    else:
        opening = ZERO

    q = (
        select(JournalLine, JournalEntry)
        .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
        .options(selectinload(JournalLine.account))
        .where(
            JournalLine.account_id == account_id,
            JournalEntry.status == DocStatus.POSTED.value,
        )
        .order_by(JournalEntry.entry_date, JournalEntry.id, JournalLine.id)
    )
    if date_from:
        q = q.where(JournalEntry.entry_date >= date_from)
    if date_to:
        q = q.where(JournalEntry.entry_date <= date_to)
    if project_id:
        q = q.where(JournalLine.project_id == project_id)

    running = opening
    lines = []
    for line, entry in db.execute(q).all():
        running = money(running + line.debit - line.credit)
        lines.append(
            {
                "date": entry.entry_date,
                "entry_no": entry.entry_no,
                "document": entry.source_document,
                "description": line.description or entry.description,
                "debit": money(line.debit),
                "credit": money(line.credit),
                "balance": running,
            }
        )
    return opening, lines


def assert_all_journals_balanced(db: Session) -> None:
    rows = db.execute(
        select(JournalEntry.id, JournalEntry.entry_no, JournalEntry.total_debit, JournalEntry.total_credit)
        .where(JournalEntry.status != DocStatus.CANCELLED.value)
    ).all()
    for _id, no, dr, cr in rows:
        if money(dr) != money(cr):
            raise UnbalancedJournalError(f"Journal {no} is unbalanced.")
        line_dr = db.execute(
            select(func.coalesce(func.sum(JournalLine.debit), 0)).where(JournalLine.entry_id == _id)
        ).scalar()
        line_cr = db.execute(
            select(func.coalesce(func.sum(JournalLine.credit), 0)).where(JournalLine.entry_id == _id)
        ).scalar()
        if money(line_dr) != money(line_cr):
            raise UnbalancedJournalError(f"Journal {no} lines are unbalanced.")
