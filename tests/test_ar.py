"""TS-AR / TS-SEED — receivables, receipts, allocations, aging."""

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select

from app.exceptions import AllocationError, ValidationError
from app.models import Booking, CustomerInvoice, DocStatus, MoneyReceipt
from app.money import money
from app.services.ar import (
    POSTED_AR,
    ar_aging,
    ar_totals,
    create_invoice,
    create_receipt,
    set_receipt_allocations,
)


def test_seed_booking_value(db):
    total = money(db.execute(select(func.coalesce(func.sum(Booking.agreed_price), 0)).where(Booking.status != DocStatus.CANCELLED.value)).scalar())
    assert total == Decimal("79300000.00")


def test_seed_receipts(db):
    total = money(db.execute(select(func.coalesce(func.sum(MoneyReceipt.amount), 0)).where(MoneyReceipt.status == DocStatus.POSTED.value)).scalar())
    assert total == Decimal("18205000.00")


def test_seed_outstanding_ar(db):
    totals = ar_totals(db)
    assert totals["demanded"] == Decimal("79300000.00")
    assert totals["receipts"] == Decimal("18205000.00")
    assert totals["outstanding"] == Decimal("61095000.00")


def test_ar_is_not_sum_of_receipts(db):
    totals = ar_totals(db)
    assert totals["outstanding"] != totals["receipts"]
    assert totals["outstanding"] == totals["demanded"] - totals["receipts"]


def test_cannot_allocate_more_than_invoice_outstanding(db):
    invoice = db.execute(select(CustomerInvoice).where(CustomerInvoice.status.in_(POSTED_AR), CustomerInvoice.outstanding_amount > 0)).scalars().first()
    receipt = db.execute(select(MoneyReceipt).where(MoneyReceipt.status == DocStatus.DRAFT.value)).scalars().first()
    from app.models import Customer, MoneyAccount, User

    customer = db.execute(select(Customer)).scalars().first()
    account = db.execute(select(MoneyAccount)).scalars().first()
    user = db.execute(select(User)).scalars().first()
    draft = create_receipt(
        db,
        receipt_date=date(2026, 9, 20),
        customer_id=invoice.customer_id,
        amount=Decimal("1.00"),
        money_account_id=account.id,
        user=user,
        is_advance=False,
    )
    try:
        set_receipt_allocations(db, draft, [{"invoice_id": invoice.id, "amount": invoice.outstanding_amount + Decimal("1.00")}])
        assert False, "over-allocation should fail"
    except AllocationError:
        db.rollback()


def test_cannot_allocate_more_than_receipt(db):
    from app.models import MoneyAccount, User

    invoice = db.execute(select(CustomerInvoice).where(CustomerInvoice.status.in_(POSTED_AR), CustomerInvoice.outstanding_amount > 0)).scalars().first()
    account = db.execute(select(MoneyAccount)).scalars().first()
    user = db.execute(select(User)).scalars().first()
    draft = create_receipt(
        db,
        receipt_date=date(2026, 9, 21),
        customer_id=invoice.customer_id,
        amount=Decimal("100.00"),
        money_account_id=account.id,
        user=user,
        is_advance=True,
    )
    try:
        set_receipt_allocations(db, draft, [{"invoice_id": invoice.id, "amount": Decimal("101.00")}], allow_advance=True)
        assert False, "receipt over-allocation should fail"
    except AllocationError:
        db.rollback()


def test_negative_receipt_rejected(db):
    from app.models import Customer, MoneyAccount, User

    customer = db.execute(select(Customer)).scalars().first()
    account = db.execute(select(MoneyAccount)).scalars().first()
    user = db.execute(select(User)).scalars().first()
    try:
        create_receipt(
            db,
            receipt_date=date(2026, 9, 22),
            customer_id=customer.id,
            amount=Decimal("-10"),
            money_account_id=account.id,
            user=user,
        )
        assert False
    except ValidationError:
        db.rollback()


def test_partial_and_paid_status(db):
    from app.models import Customer, MoneyAccount, User
    from app.services.ar import post_receipt, refresh_invoice_outstanding

    invoice = db.execute(
        select(CustomerInvoice).where(CustomerInvoice.status.in_(POSTED_AR), CustomerInvoice.outstanding_amount > 1000)
    ).scalars().first()
    account = db.execute(select(MoneyAccount)).scalars().first()
    user = db.execute(select(User)).scalars().first()
    original = invoice.outstanding_amount
    receipt = create_receipt(
        db,
        receipt_date=date(2026, 9, 23),
        customer_id=invoice.customer_id,
        amount=Decimal("100.00"),
        money_account_id=account.id,
        user=user,
        allocations=[{"invoice_id": invoice.id, "amount": Decimal("100.00")}],
        auto_post=True,
    )
    db.refresh(invoice)
    assert invoice.status == DocStatus.PARTIALLY_PAID.value
    assert invoice.outstanding_amount == original - Decimal("100.00")
    db.rollback()


def test_overdue_aging_uses_due_date(db):
    as_of = date(2026, 12, 31)
    rows = ar_aging(db, as_of=as_of)
    assert rows, "seed invoices should age"
    for row in rows:
        expected_days = (as_of - row["invoice"].due_date).days
        if expected_days > 0:
            assert row["days"] == expected_days
            assert row["overdue"] is True
