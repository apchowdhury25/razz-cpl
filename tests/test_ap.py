"""TS-AP / TS-SEED — vendor bills, payables, payments, allocations."""

from datetime import date
from decimal import Decimal

from sqlalchemy import select

from app.exceptions import AllocationError, ValidationError
from app.models import DocStatus, VendorBill, VendorPayment
from app.money import money
from app.services.ap import POSTED_AP, ap_totals, create_payment, set_payment_allocations


def test_seed_vendor_bill_totals(db):
    totals = ap_totals(db)
    assert totals["gross"] == Decimal("4080000.00")
    assert totals["vat"] == Decimal("612000.00")
    assert totals["tds"] == Decimal("179700.00")
    assert totals["retention"] == Decimal("125000.00")
    assert totals["net_payable"] == Decimal("4387300.00")
    assert totals["gross"] + totals["vat"] == totals["net_payable"] + totals["tds"] + totals["retention"]


def test_ap_is_outstanding_not_gross_bills(db):
    totals = ap_totals(db)
    assert totals["outstanding"] == totals["net_payable"] - totals["paid"]
    assert totals["outstanding"] != totals["gross"]


def test_seed_bills_match_vendor_refs(db):
    refs = {b.vendor_bill_ref: b for b in db.execute(select(VendorBill).where(VendorBill.status.in_(POSTED_AP))).scalars()}
    assert refs["RC/MTT/2026/001"].net_payable == Decimal("2625000.00")
    assert refs["DS/MTT/2026/002"].net_payable == Decimal("960500.00")
    assert refs["SE/SM/2026/003"].net_payable == Decimal("451500.00")
    assert refs["KT/WP/2026/004"].net_payable == Decimal("350300.00")


def test_negative_payment_rejected(db):
    from app.models import MoneyAccount, User, Vendor

    vendor = db.execute(select(Vendor)).scalars().first()
    account = db.execute(select(MoneyAccount)).scalars().first()
    user = db.execute(select(User)).scalars().first()
    try:
        create_payment(
            db,
            payment_date=date(2026, 9, 24),
            vendor_id=vendor.id,
            amount=Decimal("-1"),
            money_account_id=account.id,
            user=user,
        )
        assert False
    except ValidationError:
        db.rollback()


def test_cannot_overallocate_payment(db):
    from app.models import MoneyAccount, User

    bill = db.execute(select(VendorBill).where(VendorBill.status.in_(POSTED_AP), VendorBill.outstanding_amount > 0)).scalars().first()
    account = db.execute(select(MoneyAccount)).scalars().first()
    user = db.execute(select(User)).scalars().first()
    payment = create_payment(
        db,
        payment_date=date(2026, 9, 25),
        vendor_id=bill.vendor_id,
        amount=Decimal("50.00"),
        money_account_id=account.id,
        user=user,
        is_advance=True,
    )
    try:
        set_payment_allocations(db, payment, [{"bill_id": bill.id, "amount": Decimal("51.00")}], allow_advance=True)
        assert False
    except AllocationError:
        db.rollback()
