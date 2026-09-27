"""TS-GL / TS-TB / TS-CASH — journals, trial balance, opening cash."""

from decimal import Decimal

from sqlalchemy import func, select

from app.exceptions import UnbalancedJournalError
from app.models import DocStatus, JournalEntry, JournalLine, MoneyAccount
from app.money import ZERO, money
from app.services.accounting import assert_all_journals_balanced, create_journal, trial_balance
from app.services.cash_bank import cash_bank_totals, money_account_balance


def test_every_journal_is_balanced(db):
    assert_all_journals_balanced(db)
    rows = db.execute(select(JournalEntry).where(JournalEntry.status != DocStatus.CANCELLED.value)).scalars()
    for entry in rows:
        assert money(entry.total_debit) == money(entry.total_credit)
        line_dr = money(db.execute(select(func.coalesce(func.sum(JournalLine.debit), 0)).where(JournalLine.entry_id == entry.id)).scalar())
        line_cr = money(db.execute(select(func.coalesce(func.sum(JournalLine.credit), 0)).where(JournalLine.entry_id == entry.id)).scalar())
        assert line_dr == line_cr == money(entry.total_debit)


def test_trial_balance_balances(db):
    rows = trial_balance(db)
    total_dr = money(sum((r["debit"] for r in rows), ZERO))
    total_cr = money(sum((r["credit"] for r in rows), ZERO))
    assert total_dr == total_cr
    assert total_dr > ZERO


def test_unbalanced_journal_rejected(db):
    from app.models import ChartOfAccount, User

    cash = db.execute(select(ChartOfAccount).where(ChartOfAccount.system_key == "PETTY_CASH")).scalar_one()
    user = db.execute(select(User)).scalars().first()
    from datetime import date

    try:
        create_journal(
            db,
            entry_date=date(2026, 9, 1),
            description="Unbalanced test",
            lines=[
                {"account_id": cash.id, "debit": Decimal("10.00"), "credit": ZERO},
                {"account_id": cash.id, "debit": ZERO, "credit": Decimal("9.00")},
            ],
            user=user,
        )
        assert False
    except UnbalancedJournalError:
        db.rollback()


def test_opening_cash_bank(db):
    accounts = {a.name: a for a in db.execute(select(MoneyAccount)).scalars()}
    assert accounts["Petty Cash"].opening_balance == Decimal("50000.00")
    assert accounts["BRAC Bank - Current"].opening_balance == Decimal("2500000.00")
    assert accounts["City Bank - Project"].opening_balance == Decimal("1800000.00")
    opening = sum((a.opening_balance for a in accounts.values()), ZERO)
    assert money(opening) == Decimal("4350000.00")


def test_current_cash_includes_receipts(db):
    totals = cash_bank_totals(db)
    assert totals["total"] == Decimal("4350000.00") + Decimal("18205000.00")
    brac = db.execute(select(MoneyAccount).where(MoneyAccount.name == "BRAC Bank - Current")).scalar_one()
    assert money_account_balance(db, brac) == Decimal("2500000.00") + Decimal("18205000.00")
