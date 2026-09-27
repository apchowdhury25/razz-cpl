from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.exceptions import AllocationError, PostedDocumentError, ValidationError
from app.models import (
    DocStatus,
    JournalSource,
    MoneyAccount,
    PaymentAllocation,
    User,
    VendorBill,
    VendorCreditNote,
    VendorPayment,
)
from app.money import ZERO, money
from app.services.accounting import assert_period_open, create_journal, get_system_account, reverse_journal
from app.services.audit import write_audit
from app.services.numbering import assert_unique, next_number
from app.services.tax import calculate_vendor_bill

POSTED_AP = {DocStatus.POSTED.value, DocStatus.PARTIALLY_PAID.value, DocStatus.PAID.value, DocStatus.OVERDUE.value}


def refresh_bill_outstanding(bill: VendorBill) -> None:
    bill.outstanding_amount = money(bill.net_payable - bill.allocated_amount - bill.credit_amount)
    if bill.status in (DocStatus.CANCELLED.value, DocStatus.DRAFT.value, DocStatus.SUBMITTED.value, DocStatus.APPROVED.value):
        return
    if bill.outstanding_amount <= ZERO:
        bill.status = DocStatus.PAID.value
        bill.outstanding_amount = ZERO
    elif bill.allocated_amount > ZERO or bill.credit_amount > ZERO:
        bill.status = DocStatus.PARTIALLY_PAID.value
    else:
        bill.status = DocStatus.POSTED.value


def create_bill(
    db: Session,
    *,
    bill_date: date,
    due_date: date,
    vendor_id: int,
    gross_amount: Decimal,
    cost_account_id: int,
    user: User | None,
    project_id: int | None = None,
    description: str = "",
    vat_percent: Decimal = ZERO,
    tds_percent: Decimal = ZERO,
    retention_percent: Decimal = ZERO,
    mushak_ref: str = "",
    vendor_bill_ref: str = "",
    notes: str = "",
    bill_no: str | None = None,
    tds_category_id: int | None = None,
    auto_post: bool = False,
    year: int | None = None,
) -> VendorBill:
    if not vendor_id:
        raise ValidationError("Vendor is required for bills.")
    if not cost_account_id:
        raise ValidationError("Cost / expense account is required.")
    calc = calculate_vendor_bill(gross_amount, vat_percent, tds_percent, retention_percent)
    year = year or bill_date.year
    number = bill_no or next_number(db, "AP", year)
    assert_unique(db, VendorBill, "bill_no", number)
    bill = VendorBill(
        bill_no=number,
        vendor_bill_ref=vendor_bill_ref,
        bill_date=bill_date,
        due_date=due_date,
        vendor_id=vendor_id,
        project_id=project_id,
        description=description,
        gross_amount=calc["gross_amount"],
        vat_percent=calc["vat_percent"],
        vat_amount=calc["vat_amount"],
        tds_percent=calc["tds_percent"],
        tds_amount=calc["tds_amount"],
        retention_percent=calc["retention_percent"],
        retention_amount=calc["retention_amount"],
        net_payable=calc["net_payable"],
        allocated_amount=ZERO,
        credit_amount=ZERO,
        outstanding_amount=calc["net_payable"],
        mushak_ref=mushak_ref,
        cost_account_id=cost_account_id,
        tds_category_id=tds_category_id,
        notes=notes,
        status=DocStatus.DRAFT.value,
        created_by_id=user.id if user else None,
    )
    db.add(bill)
    db.flush()
    write_audit(db, user=user, action="CREATE", module="bills", record_type="VendorBill", record_id=bill.id, document_no=bill.bill_no)
    if auto_post:
        post_bill(db, bill, user=user)
    return bill


def transition_bill(db: Session, bill: VendorBill, new_status: str, user: User | None) -> None:
    allowed = {
        DocStatus.DRAFT.value: {DocStatus.SUBMITTED.value, DocStatus.CANCELLED.value},
        DocStatus.SUBMITTED.value: {DocStatus.APPROVED.value, DocStatus.DRAFT.value, DocStatus.CANCELLED.value},
        DocStatus.APPROVED.value: {DocStatus.POSTED.value, DocStatus.SUBMITTED.value, DocStatus.CANCELLED.value},
    }
    if new_status not in allowed.get(bill.status, set()):
        raise ValidationError(f"Cannot change bill from {bill.status} to {new_status}.")
    if new_status == DocStatus.POSTED.value:
        post_bill(db, bill, user=user)
        return
    bill.status = new_status
    if new_status == DocStatus.APPROVED.value and user:
        bill.approved_by_id = user.id
    write_audit(db, user=user, action=new_status, module="bills", record_type="VendorBill", record_id=bill.id, document_no=bill.bill_no)


def post_bill(db: Session, bill: VendorBill, *, user: User | None) -> None:
    if bill.status in POSTED_AP:
        raise PostedDocumentError("Bill is already posted.")
    assert_period_open(db, bill.bill_date, user)
    calc = calculate_vendor_bill(bill.gross_amount, bill.vat_percent, bill.tds_percent, bill.retention_percent)
    bill.vat_amount = calc["vat_amount"]
    bill.tds_amount = calc["tds_amount"]
    bill.retention_amount = calc["retention_amount"]
    bill.net_payable = calc["net_payable"]
    bill.outstanding_amount = calc["net_payable"]

    ap_acc = get_system_account(db, "AP")
    input_vat = get_system_account(db, "INPUT_VAT")
    tds_acc = get_system_account(db, "TDS_PAYABLE")
    ret_acc = get_system_account(db, "RETENTION_PAYABLE")

    lines = [
        {"account_id": bill.cost_account_id, "project_id": bill.project_id, "debit": bill.gross_amount, "credit": ZERO, "description": bill.bill_no},
    ]
    if bill.vat_amount > ZERO:
        lines.append({"account_id": input_vat.id, "project_id": bill.project_id, "debit": bill.vat_amount, "credit": ZERO, "description": bill.bill_no})
    lines.append({"account_id": ap_acc.id, "project_id": bill.project_id, "debit": ZERO, "credit": bill.net_payable, "description": bill.bill_no})
    if bill.tds_amount > ZERO:
        lines.append({"account_id": tds_acc.id, "project_id": bill.project_id, "debit": ZERO, "credit": bill.tds_amount, "description": bill.bill_no})
    if bill.retention_amount > ZERO:
        lines.append({"account_id": ret_acc.id, "project_id": bill.project_id, "debit": ZERO, "credit": bill.retention_amount, "description": bill.bill_no})

    journal = create_journal(
        db,
        entry_date=bill.bill_date,
        description=f"Vendor bill {bill.bill_no}",
        lines=lines,
        source_module=JournalSource.AP_BILL.value,
        source_document=bill.bill_no,
        source_id=bill.id,
        project_id=bill.project_id,
        user=user,
    )
    bill.journal_id = journal.id
    bill.status = DocStatus.POSTED.value
    bill.posted_date = bill.bill_date
    if user:
        bill.approved_by_id = bill.approved_by_id or user.id
    write_audit(db, user=user, action="POST", module="bills", record_type="VendorBill", record_id=bill.id, document_no=bill.bill_no)
    db.flush()


def cancel_bill(db: Session, bill: VendorBill, *, user: User | None, cancel_date: date | None = None) -> None:
    if bill.status == DocStatus.CANCELLED.value:
        raise ValidationError("Bill is already cancelled.")
    if bill.allocated_amount > ZERO:
        raise ValidationError("Cannot cancel a bill that has allocated payments.")
    if bill.status in POSTED_AP and bill.journal_id:
        from app.models import JournalEntry

        journal = db.get(JournalEntry, bill.journal_id)
        if journal:
            reverse_journal(db, journal, reversal_date=cancel_date or date.today(), user=user, reason=f"Cancel {bill.bill_no}")
    bill.status = DocStatus.CANCELLED.value
    bill.outstanding_amount = ZERO
    write_audit(db, user=user, action="CANCEL", module="bills", record_type="VendorBill", record_id=bill.id, document_no=bill.bill_no)


def create_payment(
    db: Session,
    *,
    payment_date: date,
    vendor_id: int,
    amount: Decimal,
    money_account_id: int,
    user: User | None,
    project_id: int | None = None,
    payment_method: str = "BANK_TRANSFER",
    reference_no: str = "",
    notes: str = "",
    is_advance: bool = False,
    payment_no: str | None = None,
    allocations: list[dict[str, Any]] | None = None,
    auto_post: bool = False,
    year: int | None = None,
) -> VendorPayment:
    amt = money(amount)
    if amt <= ZERO:
        raise ValidationError("Payment amount must be greater than zero.")
    if not vendor_id:
        raise ValidationError("Vendor is required for payments.")
    if not money_account_id:
        raise ValidationError("Cash/bank account is required for payments.")
    if not db.get(MoneyAccount, money_account_id):
        raise ValidationError("Cash/bank account not found.")
    year = year or payment_date.year
    number = payment_no or next_number(db, "VP", year)
    assert_unique(db, VendorPayment, "payment_no", number)
    payment = VendorPayment(
        payment_no=number,
        payment_date=payment_date,
        vendor_id=vendor_id,
        project_id=project_id,
        amount=amt,
        allocated_amount=ZERO,
        unallocated_amount=amt,
        is_advance=is_advance,
        payment_method=payment_method,
        money_account_id=money_account_id,
        reference_no=reference_no,
        notes=notes,
        status=DocStatus.DRAFT.value,
        created_by_id=user.id if user else None,
    )
    db.add(payment)
    db.flush()
    if allocations:
        set_payment_allocations(db, payment, allocations, allow_advance=is_advance)
    write_audit(db, user=user, action="CREATE", module="payments", record_type="VendorPayment", record_id=payment.id, document_no=payment.payment_no)
    if auto_post:
        post_payment(db, payment, user=user)
    return payment


def set_payment_allocations(
    db: Session,
    payment: VendorPayment,
    allocations: list[dict[str, Any]],
    *,
    allow_advance: bool = False,
) -> None:
    if payment.status in POSTED_AP:
        raise PostedDocumentError("Cannot change allocations on a posted payment.")
    db.execute(PaymentAllocation.__table__.delete().where(PaymentAllocation.payment_id == payment.id))
    total = ZERO
    for item in allocations:
        amt = money(item.get("amount") or 0)
        if amt <= ZERO:
            continue
        bill = db.get(VendorBill, int(item["bill_id"]))
        if not bill:
            raise AllocationError("Bill not found for allocation.")
        if bill.vendor_id != payment.vendor_id:
            raise AllocationError("Cannot allocate a payment to another vendor's bill.")
        if bill.status not in POSTED_AP:
            raise AllocationError(f"Bill {bill.bill_no} is not posted.")
        if amt > money(bill.outstanding_amount):
            raise AllocationError(f"Allocation {amt} exceeds outstanding {bill.outstanding_amount} on {bill.bill_no}.")
        total = money(total + amt)
        db.add(PaymentAllocation(payment_id=payment.id, bill_id=bill.id, amount=amt))
    if total > payment.amount:
        raise AllocationError("Total allocation exceeds payment amount.")
    leftover = money(payment.amount - total)
    if leftover > ZERO and not allow_advance and not payment.is_advance:
        raise AllocationError("Unallocated payment requires the Vendor Advance option.")
    payment.allocated_amount = total
    payment.unallocated_amount = leftover
    payment.is_advance = leftover > ZERO or payment.is_advance
    db.flush()


def post_payment(db: Session, payment: VendorPayment, *, user: User | None) -> None:
    if payment.status in POSTED_AP:
        raise PostedDocumentError("Payment is already posted.")
    assert_period_open(db, payment.payment_date, user)
    money_acc = db.get(MoneyAccount, payment.money_account_id)
    ap_acc = get_system_account(db, "AP")
    lines = [
        {"account_id": ap_acc.id, "project_id": payment.project_id, "debit": payment.amount, "credit": ZERO, "description": payment.payment_no},
        {"account_id": money_acc.gl_account_id, "project_id": payment.project_id, "debit": ZERO, "credit": payment.amount, "description": payment.payment_no},
    ]
    journal = create_journal(
        db,
        entry_date=payment.payment_date,
        description=f"Vendor payment {payment.payment_no}",
        lines=lines,
        source_module=JournalSource.AP_PAYMENT.value,
        source_document=payment.payment_no,
        source_id=payment.id,
        project_id=payment.project_id,
        user=user,
    )
    payment.journal_id = journal.id
    payment.status = DocStatus.POSTED.value
    payment.posted_date = payment.payment_date
    if user:
        payment.approved_by_id = payment.approved_by_id or user.id
    db.refresh(payment, attribute_names=["allocations"])
    for alloc in payment.allocations:
        bill = db.get(VendorBill, alloc.bill_id)
        bill.allocated_amount = money(bill.allocated_amount + alloc.amount)
        refresh_bill_outstanding(bill)
    write_audit(db, user=user, action="POST", module="payments", record_type="VendorPayment", record_id=payment.id, document_no=payment.payment_no)
    db.flush()


def cancel_payment(db: Session, payment: VendorPayment, *, user: User | None, cancel_date: date | None = None) -> None:
    if payment.status == DocStatus.CANCELLED.value:
        raise ValidationError("Payment is already cancelled.")
    if payment.status in POSTED_AP and payment.journal_id:
        from app.models import JournalEntry

        journal = db.get(JournalEntry, payment.journal_id)
        if journal:
            reverse_journal(db, journal, reversal_date=cancel_date or date.today(), user=user, reason=f"Cancel {payment.payment_no}")
        db.refresh(payment, attribute_names=["allocations"])
        for alloc in payment.allocations:
            bill = db.get(VendorBill, alloc.bill_id)
            bill.allocated_amount = money(bill.allocated_amount - alloc.amount)
            if bill.allocated_amount < ZERO:
                bill.allocated_amount = ZERO
            refresh_bill_outstanding(bill)
    payment.status = DocStatus.CANCELLED.value
    write_audit(db, user=user, action="CANCEL", module="payments", record_type="VendorPayment", record_id=payment.id, document_no=payment.payment_no)


def settle_retention(db: Session, bill: VendorBill, *, settle_date: date, money_account_id: int, user: User | None) -> None:
    if bill.status not in POSTED_AP:
        raise ValidationError("Bill must be posted.")
    if bill.retention_amount <= ZERO:
        raise ValidationError("No retention on this bill.")
    if bill.retention_settled:
        raise ValidationError("Retention already settled.")
    money_acc = db.get(MoneyAccount, money_account_id)
    ret_acc = get_system_account(db, "RETENTION_PAYABLE")
    create_journal(
        db,
        entry_date=settle_date,
        description=f"Retention settlement {bill.bill_no}",
        lines=[
            {"account_id": ret_acc.id, "project_id": bill.project_id, "debit": bill.retention_amount, "credit": ZERO, "description": bill.bill_no},
            {"account_id": money_acc.gl_account_id, "project_id": bill.project_id, "debit": ZERO, "credit": bill.retention_amount, "description": bill.bill_no},
        ],
        source_module=JournalSource.RETENTION_SETTLEMENT.value,
        source_document=bill.bill_no,
        source_id=bill.id,
        project_id=bill.project_id,
        user=user,
    )
    bill.retention_settled = True
    write_audit(db, user=user, action="POST", module="bills", record_type="RetentionSettlement", record_id=bill.id, document_no=bill.bill_no)


def remit_tds(db: Session, bill: VendorBill, *, remit_date: date, money_account_id: int, user: User | None, certificate_no: str = "") -> None:
    if bill.status not in POSTED_AP:
        raise ValidationError("Bill must be posted.")
    if bill.tds_amount <= ZERO:
        raise ValidationError("No TDS on this bill.")
    if bill.tds_remitted:
        raise ValidationError("TDS already remitted.")
    money_acc = db.get(MoneyAccount, money_account_id)
    tds_acc = get_system_account(db, "TDS_PAYABLE")
    create_journal(
        db,
        entry_date=remit_date,
        description=f"TDS remittance {bill.bill_no}",
        lines=[
            {"account_id": tds_acc.id, "project_id": bill.project_id, "debit": bill.tds_amount, "credit": ZERO, "description": bill.bill_no},
            {"account_id": money_acc.gl_account_id, "project_id": bill.project_id, "debit": ZERO, "credit": bill.tds_amount, "description": bill.bill_no},
        ],
        source_module=JournalSource.TDS_REMITTANCE.value,
        source_document=bill.bill_no,
        source_id=bill.id,
        project_id=bill.project_id,
        user=user,
    )
    bill.tds_remitted = True
    bill.tds_certificate_no = certificate_no
    write_audit(db, user=user, action="POST", module="tax", record_type="TDSRemittance", record_id=bill.id, document_no=bill.bill_no)


def post_vendor_credit(db: Session, note: VendorCreditNote, *, user: User | None) -> None:
    if note.status in POSTED_AP:
        raise PostedDocumentError("Credit note already posted.")
    amt = money(note.amount)
    if amt <= ZERO:
        raise ValidationError("Credit note amount must be greater than zero.")
    ap_acc = get_system_account(db, "AP")
    cost_acc = get_system_account(db, "PROJECT_COST")
    journal = create_journal(
        db,
        entry_date=note.credit_date,
        description=f"Vendor credit {note.credit_no}",
        lines=[
            {"account_id": ap_acc.id, "project_id": note.project_id, "debit": amt, "credit": ZERO, "description": note.credit_no},
            {"account_id": cost_acc.id, "project_id": note.project_id, "debit": ZERO, "credit": amt, "description": note.credit_no},
        ],
        source_module=JournalSource.AP_CREDIT.value,
        source_document=note.credit_no,
        source_id=note.id,
        project_id=note.project_id,
        user=user,
    )
    note.journal_id = journal.id
    note.status = DocStatus.POSTED.value
    if note.bill_id:
        bill = db.get(VendorBill, note.bill_id)
        if bill:
            if amt > bill.outstanding_amount:
                raise AllocationError("Credit exceeds bill outstanding.")
            bill.credit_amount = money(bill.credit_amount + amt)
            refresh_bill_outstanding(bill)
    write_audit(db, user=user, action="POST", module="bills", record_type="VendorCreditNote", record_id=note.id, document_no=note.credit_no)


def ap_totals(db: Session, *, project_id: int | None = None, vendor_id: int | None = None) -> dict[str, Decimal]:
    filters = [VendorBill.status.in_(POSTED_AP)]
    if project_id:
        filters.append(VendorBill.project_id == project_id)
    if vendor_id:
        filters.append(VendorBill.vendor_id == vendor_id)
    gross = money(db.execute(select(func.coalesce(func.sum(VendorBill.gross_amount), 0)).where(*filters)).scalar())
    vat = money(db.execute(select(func.coalesce(func.sum(VendorBill.vat_amount), 0)).where(*filters)).scalar())
    tds = money(db.execute(select(func.coalesce(func.sum(VendorBill.tds_amount), 0)).where(*filters)).scalar())
    retention = money(db.execute(select(func.coalesce(func.sum(VendorBill.retention_amount), 0)).where(*filters)).scalar())
    net = money(db.execute(select(func.coalesce(func.sum(VendorBill.net_payable), 0)).where(*filters)).scalar())
    outstanding = money(db.execute(select(func.coalesce(func.sum(VendorBill.outstanding_amount), 0)).where(*filters)).scalar())
    pfilters = [VendorPayment.status == DocStatus.POSTED.value]
    if project_id:
        pfilters.append(VendorPayment.project_id == project_id)
    if vendor_id:
        pfilters.append(VendorPayment.vendor_id == vendor_id)
    paid = money(db.execute(select(func.coalesce(func.sum(VendorPayment.amount), 0)).where(*pfilters)).scalar())
    return {
        "gross": gross,
        "vat": vat,
        "tds": tds,
        "retention": retention,
        "net_payable": net,
        "outstanding": outstanding,
        "paid": paid,
    }


def ap_aging(db: Session, *, as_of: date, project_id: int | None = None, vendor_id: int | None = None) -> list[dict[str, Any]]:
    q = (
        select(VendorBill)
        .options(selectinload(VendorBill.vendor), selectinload(VendorBill.project))
        .where(VendorBill.status.in_(POSTED_AP), VendorBill.outstanding_amount > 0)
    )
    if project_id:
        q = q.where(VendorBill.project_id == project_id)
    if vendor_id:
        q = q.where(VendorBill.vendor_id == vendor_id)
    rows = []
    for bill in db.execute(q).scalars():
        days = (as_of - bill.due_date).days
        bucket = (
            "current" if days <= 0 else
            "d1_30" if days <= 30 else
            "d31_60" if days <= 60 else
            "d61_90" if days <= 90 else
            "d91_180" if days <= 180 else
            "d181_365" if days <= 365 else
            "d365p"
        )
        rows.append(
            {
                "bill": bill,
                "vendor": bill.vendor.name if bill.vendor else "",
                "project": bill.project.code if bill.project else "",
                "bill_no": bill.bill_no,
                "due_date": bill.due_date,
                "days": max(days, 0) if days > 0 else 0,
                "outstanding": money(bill.outstanding_amount),
                "bucket": bucket,
                "overdue": days > 0,
            }
        )
    return rows


def vendor_ledger(db: Session, vendor_id: int, *, date_from: date | None = None, date_to: date | None = None) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    bq = select(VendorBill).where(VendorBill.vendor_id == vendor_id, VendorBill.status.in_(POSTED_AP))
    pq = select(VendorPayment).where(VendorPayment.vendor_id == vendor_id, VendorPayment.status == DocStatus.POSTED.value)
    cq = select(VendorCreditNote).where(VendorCreditNote.vendor_id == vendor_id, VendorCreditNote.status == DocStatus.POSTED.value)
    if date_from:
        bq = bq.where(VendorBill.bill_date >= date_from)
        pq = pq.where(VendorPayment.payment_date >= date_from)
        cq = cq.where(VendorCreditNote.credit_date >= date_from)
    if date_to:
        bq = bq.where(VendorBill.bill_date <= date_to)
        pq = pq.where(VendorPayment.payment_date <= date_to)
        cq = cq.where(VendorCreditNote.credit_date <= date_to)
    for bill in db.execute(bq).scalars():
        entries.append({"date": bill.bill_date, "document": bill.bill_no, "description": bill.description or "Vendor bill", "debit": ZERO, "credit": money(bill.net_payable)})
    for pay in db.execute(pq).scalars():
        entries.append({"date": pay.payment_date, "document": pay.payment_no, "description": pay.notes or "Vendor payment", "debit": money(pay.amount), "credit": ZERO})
    for cn in db.execute(cq).scalars():
        entries.append({"date": cn.credit_date, "document": cn.credit_no, "description": cn.reason or "Credit note", "debit": money(cn.amount), "credit": ZERO})
    entries.sort(key=lambda e: (e["date"], e["document"]))
    running = ZERO
    for e in entries:
        running = money(running + e["credit"] - e["debit"])
        e["balance"] = running
    return entries
