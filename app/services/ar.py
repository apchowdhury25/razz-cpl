from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.exceptions import AllocationError, PostedDocumentError, ValidationError
from app.models import (
    Booking,
    Customer,
    CustomerCreditNote,
    CustomerInvoice,
    DocStatus,
    JournalSource,
    MoneyAccount,
    MoneyReceipt,
    PaymentSchedule,
    ReceiptAllocation,
    Unit,
    UnitStatus,
    User,
)
from app.money import ZERO, money
from app.services.accounting import assert_period_open, create_journal, get_system_account, reverse_journal
from app.services.audit import write_audit
from app.services.numbering import assert_unique, next_number
from app.services.tax import calculate_invoice

POSTED_AR = {DocStatus.POSTED.value, DocStatus.PARTIALLY_PAID.value, DocStatus.PAID.value, DocStatus.OVERDUE.value}


def refresh_invoice_outstanding(invoice: CustomerInvoice) -> None:
    allocated = money(invoice.allocated_amount)
    credits = money(invoice.credit_amount)
    invoice.outstanding_amount = money(invoice.total_receivable - allocated - credits)
    if invoice.status in (DocStatus.CANCELLED.value, DocStatus.DRAFT.value, DocStatus.SUBMITTED.value, DocStatus.APPROVED.value):
        return
    if invoice.outstanding_amount <= ZERO:
        invoice.status = DocStatus.PAID.value
        invoice.outstanding_amount = ZERO
    elif allocated > ZERO or credits > ZERO:
        invoice.status = DocStatus.PARTIALLY_PAID.value
    else:
        invoice.status = DocStatus.POSTED.value


def create_booking(
    db: Session,
    *,
    booking_date: date,
    customer_id: int,
    project_id: int,
    unit_id: int,
    agreed_price: Decimal,
    user: User | None,
    notes: str = "",
    booking_no: str | None = None,
    generate_demands: bool = True,
    year: int | None = None,
) -> Booking:
    agreed = money(agreed_price)
    if agreed <= ZERO:
        raise ValidationError("Agreed price must be greater than zero.")
    unit = db.get(Unit, unit_id)
    if not unit:
        raise ValidationError("Unit not found.")
    if unit.project_id != project_id:
        raise ValidationError("Unit does not belong to the selected project.")
    if unit.status in (UnitStatus.BOOKED.value, UnitStatus.SOLD.value):
        raise ValidationError("Unit is already booked or sold.")
    year = year or booking_date.year
    number = booking_no or next_number(db, "BK", year)
    assert_unique(db, Booking, "booking_no", number)
    booking = Booking(
        booking_no=number,
        booking_date=booking_date,
        customer_id=customer_id,
        project_id=project_id,
        unit_id=unit_id,
        agreed_price=agreed,
        status=DocStatus.POSTED.value,
        notes=notes,
        created_by_id=user.id if user else None,
    )
    db.add(booking)
    db.flush()
    unit.status = UnitStatus.BOOKED.value
    unit.buyer_id = customer_id
    unit.booking_id = booking.id
    unit.booking_date = booking_date
    unit.sale_price = agreed

    schedule_defs = [
        (1, "Booking money (10%)", Decimal("10.00"), booking_date),
        (2, "Down payment (15%)", Decimal("15.00"), booking_date + timedelta(days=30)),
        (3, "Construction installment (50%)", Decimal("50.00"), booking_date + timedelta(days=180)),
        (4, "Handover (25%)", Decimal("25.00"), booking_date + timedelta(days=365)),
    ]
    remaining = agreed
    for i, (no, desc, pct, due) in enumerate(schedule_defs):
        if i == len(schedule_defs) - 1:
            amt = remaining
        else:
            amt = money(agreed * pct / Decimal("100"))
            remaining = money(remaining - amt)
        sched = PaymentSchedule(
            booking_id=booking.id,
            installment_no=no,
            description=desc,
            due_date=due,
            percent=pct,
            amount=amt,
        )
        db.add(sched)
        db.flush()
        if generate_demands:
            invoice = create_invoice(
                db,
                invoice_date=booking_date if no <= 2 else due,
                due_date=due,
                customer_id=customer_id,
                project_id=project_id,
                unit_id=unit_id,
                booking_id=booking.id,
                description=f"{booking.booking_no} — {desc}",
                amount=amt,
                vat_percent=ZERO,
                user=user,
                auto_post=True,
                year=year,
            )
            sched.invoice_id = invoice.id
    write_audit(
        db,
        user=user,
        action="CREATE",
        module="bookings",
        record_type="Booking",
        record_id=booking.id,
        document_no=booking.booking_no,
        description=f"Booking {booking.booking_no} for unit {unit.unit_number}",
    )
    db.flush()
    return booking


def create_invoice(
    db: Session,
    *,
    invoice_date: date,
    due_date: date,
    customer_id: int,
    amount: Decimal,
    user: User | None,
    project_id: int | None = None,
    unit_id: int | None = None,
    booking_id: int | None = None,
    description: str = "",
    vat_percent: Decimal = ZERO,
    invoice_no: str | None = None,
    auto_post: bool = False,
    year: int | None = None,
) -> CustomerInvoice:
    if not customer_id:
        raise ValidationError("Customer is required for AR invoices.")
    calc = calculate_invoice(amount, vat_percent)
    year = year or invoice_date.year
    number = invoice_no or next_number(db, "AR", year)
    assert_unique(db, CustomerInvoice, "invoice_no", number)
    invoice = CustomerInvoice(
        invoice_no=number,
        invoice_date=invoice_date,
        due_date=due_date,
        customer_id=customer_id,
        project_id=project_id,
        unit_id=unit_id,
        booking_id=booking_id,
        description=description,
        amount=calc["amount"],
        vat_percent=calc["vat_percent"],
        vat_amount=calc["vat_amount"],
        total_receivable=calc["total_receivable"],
        allocated_amount=ZERO,
        credit_amount=ZERO,
        outstanding_amount=calc["total_receivable"],
        status=DocStatus.DRAFT.value,
        created_by_id=user.id if user else None,
    )
    db.add(invoice)
    db.flush()
    write_audit(
        db,
        user=user,
        action="CREATE",
        module="ar",
        record_type="CustomerInvoice",
        record_id=invoice.id,
        document_no=invoice.invoice_no,
    )
    if auto_post:
        post_invoice(db, invoice, user=user)
    return invoice


def transition_invoice(db: Session, invoice: CustomerInvoice, new_status: str, user: User | None) -> None:
    allowed = {
        DocStatus.DRAFT.value: {DocStatus.SUBMITTED.value, DocStatus.CANCELLED.value},
        DocStatus.SUBMITTED.value: {DocStatus.APPROVED.value, DocStatus.DRAFT.value, DocStatus.CANCELLED.value},
        DocStatus.APPROVED.value: {DocStatus.POSTED.value, DocStatus.SUBMITTED.value, DocStatus.CANCELLED.value},
    }
    if new_status not in allowed.get(invoice.status, set()):
        raise ValidationError(f"Cannot change invoice from {invoice.status} to {new_status}.")
    if new_status == DocStatus.POSTED.value:
        post_invoice(db, invoice, user=user)
        return
    invoice.status = new_status
    if new_status == DocStatus.APPROVED.value and user:
        invoice.approved_by_id = user.id
    write_audit(db, user=user, action=new_status, module="ar", record_type="CustomerInvoice", record_id=invoice.id, document_no=invoice.invoice_no)


def post_invoice(db: Session, invoice: CustomerInvoice, *, user: User | None) -> None:
    if invoice.status in POSTED_AR:
        raise PostedDocumentError("Invoice is already posted.")
    if invoice.status == DocStatus.CANCELLED.value:
        raise PostedDocumentError("Cancelled invoice cannot be posted.")
    assert_period_open(db, invoice.invoice_date, user)
    ar_acc = get_system_account(db, "AR")
    revenue_acc = get_system_account(db, "SALES_REVENUE")
    lines = [
        {"account_id": ar_acc.id, "project_id": invoice.project_id, "debit": invoice.total_receivable, "credit": ZERO, "description": invoice.invoice_no},
    ]
    if invoice.vat_amount > ZERO:
        output_vat = get_system_account(db, "OUTPUT_VAT")
        lines.append({"account_id": revenue_acc.id, "project_id": invoice.project_id, "debit": ZERO, "credit": invoice.amount, "description": invoice.invoice_no})
        lines.append({"account_id": output_vat.id, "project_id": invoice.project_id, "debit": ZERO, "credit": invoice.vat_amount, "description": invoice.invoice_no})
    else:
        lines.append({"account_id": revenue_acc.id, "project_id": invoice.project_id, "debit": ZERO, "credit": invoice.total_receivable, "description": invoice.invoice_no})
    journal = create_journal(
        db,
        entry_date=invoice.invoice_date,
        description=f"AR demand {invoice.invoice_no}",
        lines=lines,
        source_module=JournalSource.AR_INVOICE.value,
        source_document=invoice.invoice_no,
        source_id=invoice.id,
        project_id=invoice.project_id,
        user=user,
    )
    invoice.journal_id = journal.id
    invoice.status = DocStatus.POSTED.value
    invoice.posted_date = invoice.invoice_date
    if user:
        invoice.approved_by_id = invoice.approved_by_id or user.id
    write_audit(db, user=user, action="POST", module="ar", record_type="CustomerInvoice", record_id=invoice.id, document_no=invoice.invoice_no)
    db.flush()


def cancel_invoice(db: Session, invoice: CustomerInvoice, *, user: User | None, cancel_date: date | None = None) -> None:
    if invoice.status == DocStatus.CANCELLED.value:
        raise ValidationError("Invoice is already cancelled.")
    if invoice.allocated_amount > ZERO:
        raise ValidationError("Cannot cancel an invoice that has allocated receipts. Reverse the receipts first.")
    if invoice.status in POSTED_AR and invoice.journal_id:
        from app.models import JournalEntry

        journal = db.get(JournalEntry, invoice.journal_id)
        if journal:
            reverse_journal(db, journal, reversal_date=cancel_date or date.today(), user=user, reason=f"Cancel {invoice.invoice_no}")
    invoice.status = DocStatus.CANCELLED.value
    invoice.outstanding_amount = ZERO
    write_audit(db, user=user, action="CANCEL", module="ar", record_type="CustomerInvoice", record_id=invoice.id, document_no=invoice.invoice_no)


def create_receipt(
    db: Session,
    *,
    receipt_date: date,
    customer_id: int,
    amount: Decimal,
    money_account_id: int,
    user: User | None,
    project_id: int | None = None,
    unit_id: int | None = None,
    payment_method: str = "BANK_TRANSFER",
    reference_no: str = "",
    notes: str = "",
    received_by: str = "",
    is_advance: bool = False,
    receipt_no: str | None = None,
    allocations: list[dict[str, Any]] | None = None,
    auto_post: bool = False,
    year: int | None = None,
) -> MoneyReceipt:
    amt = money(amount)
    if amt <= ZERO:
        raise ValidationError("Receipt amount must be greater than zero.")
    if not customer_id:
        raise ValidationError("Customer is required for receipts.")
    if not money_account_id:
        raise ValidationError("Cash/bank account is required for receipts.")
    if not db.get(MoneyAccount, money_account_id):
        raise ValidationError("Cash/bank account not found.")
    year = year or receipt_date.year
    number = receipt_no or next_number(db, "MR", year)
    assert_unique(db, MoneyReceipt, "receipt_no", number)
    receipt = MoneyReceipt(
        receipt_no=number,
        receipt_date=receipt_date,
        customer_id=customer_id,
        project_id=project_id,
        unit_id=unit_id,
        amount=amt,
        allocated_amount=ZERO,
        unallocated_amount=amt,
        is_advance=is_advance,
        payment_method=payment_method,
        money_account_id=money_account_id,
        reference_no=reference_no,
        notes=notes,
        received_by=received_by,
        status=DocStatus.DRAFT.value,
        created_by_id=user.id if user else None,
    )
    db.add(receipt)
    db.flush()
    if allocations:
        set_receipt_allocations(db, receipt, allocations, allow_advance=is_advance)
    write_audit(db, user=user, action="CREATE", module="receipts", record_type="MoneyReceipt", record_id=receipt.id, document_no=receipt.receipt_no)
    if auto_post:
        post_receipt(db, receipt, user=user)
    return receipt


def set_receipt_allocations(
    db: Session,
    receipt: MoneyReceipt,
    allocations: list[dict[str, Any]],
    *,
    allow_advance: bool = False,
) -> None:
    if receipt.status in POSTED_AR:
        raise PostedDocumentError("Cannot change allocations on a posted receipt.")
    db.execute(ReceiptAllocation.__table__.delete().where(ReceiptAllocation.receipt_id == receipt.id))
    total = ZERO
    for item in allocations:
        amt = money(item.get("amount") or 0)
        if amt <= ZERO:
            continue
        invoice = db.get(CustomerInvoice, int(item["invoice_id"]))
        if not invoice:
            raise AllocationError("Invoice not found for allocation.")
        if invoice.customer_id != receipt.customer_id:
            raise AllocationError("Cannot allocate a receipt to another customer's invoice.")
        if invoice.status not in POSTED_AR:
            raise AllocationError(f"Invoice {invoice.invoice_no} is not posted.")
        available = money(invoice.outstanding_amount)
        if amt > available:
            raise AllocationError(
                f"Allocation {amt} exceeds outstanding {available} on {invoice.invoice_no}."
            )
        total = money(total + amt)
        db.add(ReceiptAllocation(receipt_id=receipt.id, invoice_id=invoice.id, amount=amt))
    if total > receipt.amount:
        raise AllocationError("Total allocation exceeds receipt amount.")
    leftover = money(receipt.amount - total)
    if leftover > ZERO and not allow_advance and not receipt.is_advance:
        raise AllocationError("Unallocated receipt amount requires the Advance Receipt option.")
    receipt.allocated_amount = total
    receipt.unallocated_amount = leftover
    receipt.is_advance = leftover > ZERO or receipt.is_advance
    db.flush()


def post_receipt(db: Session, receipt: MoneyReceipt, *, user: User | None) -> None:
    if receipt.status in POSTED_AR:
        raise PostedDocumentError("Receipt is already posted.")
    assert_period_open(db, receipt.receipt_date, user)
    money_acc = db.get(MoneyAccount, receipt.money_account_id)
    if not money_acc:
        raise ValidationError("Cash/bank account is missing.")
    ar_acc = get_system_account(db, "AR")
    advance_acc = get_system_account(db, "CUSTOMER_ADVANCE")
    lines = [
        {
            "account_id": money_acc.gl_account_id,
            "project_id": receipt.project_id,
            "debit": receipt.amount,
            "credit": ZERO,
            "description": receipt.receipt_no,
        }
    ]
    allocated = money(receipt.allocated_amount)
    unallocated = money(receipt.unallocated_amount)
    if allocated > ZERO:
        lines.append(
            {
                "account_id": ar_acc.id,
                "project_id": receipt.project_id,
                "debit": ZERO,
                "credit": allocated,
                "description": receipt.receipt_no,
            }
        )
    if unallocated > ZERO:
        lines.append(
            {
                "account_id": advance_acc.id,
                "project_id": receipt.project_id,
                "debit": ZERO,
                "credit": unallocated,
                "description": f"{receipt.receipt_no} advance",
            }
        )
        receipt.is_advance = True
    journal = create_journal(
        db,
        entry_date=receipt.receipt_date,
        description=f"Customer receipt {receipt.receipt_no}",
        lines=lines,
        source_module=JournalSource.AR_RECEIPT.value,
        source_document=receipt.receipt_no,
        source_id=receipt.id,
        project_id=receipt.project_id,
        user=user,
    )
    receipt.journal_id = journal.id
    receipt.status = DocStatus.POSTED.value
    receipt.posted_date = receipt.receipt_date
    db.refresh(receipt, attribute_names=["allocations"])
    for alloc in receipt.allocations:
        invoice = db.get(CustomerInvoice, alloc.invoice_id)
        invoice.allocated_amount = money(invoice.allocated_amount + alloc.amount)
        refresh_invoice_outstanding(invoice)
    write_audit(db, user=user, action="POST", module="receipts", record_type="MoneyReceipt", record_id=receipt.id, document_no=receipt.receipt_no)
    db.flush()


def cancel_receipt(db: Session, receipt: MoneyReceipt, *, user: User | None, cancel_date: date | None = None) -> None:
    if receipt.status == DocStatus.CANCELLED.value:
        raise ValidationError("Receipt is already cancelled.")
    if receipt.status in POSTED_AR and receipt.journal_id:
        from app.models import JournalEntry

        journal = db.get(JournalEntry, receipt.journal_id)
        if journal:
            reverse_journal(db, journal, reversal_date=cancel_date or date.today(), user=user, reason=f"Cancel {receipt.receipt_no}")
        db.refresh(receipt, attribute_names=["allocations"])
        for alloc in receipt.allocations:
            invoice = db.get(CustomerInvoice, alloc.invoice_id)
            invoice.allocated_amount = money(invoice.allocated_amount - alloc.amount)
            if invoice.allocated_amount < ZERO:
                invoice.allocated_amount = ZERO
            refresh_invoice_outstanding(invoice)
    receipt.status = DocStatus.CANCELLED.value
    write_audit(db, user=user, action="CANCEL", module="receipts", record_type="MoneyReceipt", record_id=receipt.id, document_no=receipt.receipt_no)


def post_credit_note(db: Session, note: CustomerCreditNote, *, user: User | None) -> None:
    if note.status in POSTED_AR:
        raise PostedDocumentError("Credit note already posted.")
    amt = money(note.amount)
    if amt <= ZERO:
        raise ValidationError("Credit note amount must be greater than zero.")
    assert_period_open(db, note.credit_date, user)
    ar_acc = get_system_account(db, "AR")
    revenue_acc = get_system_account(db, "SALES_REVENUE")
    journal = create_journal(
        db,
        entry_date=note.credit_date,
        description=f"Customer credit {note.credit_no}",
        lines=[
            {"account_id": revenue_acc.id, "project_id": note.project_id, "debit": amt, "credit": ZERO, "description": note.credit_no},
            {"account_id": ar_acc.id, "project_id": note.project_id, "debit": ZERO, "credit": amt, "description": note.credit_no},
        ],
        source_module=JournalSource.AR_CREDIT.value,
        source_document=note.credit_no,
        source_id=note.id,
        project_id=note.project_id,
        user=user,
    )
    note.journal_id = journal.id
    note.status = DocStatus.POSTED.value
    if note.invoice_id:
        invoice = db.get(CustomerInvoice, note.invoice_id)
        if invoice:
            if amt > invoice.outstanding_amount:
                raise AllocationError("Credit exceeds invoice outstanding.")
            invoice.credit_amount = money(invoice.credit_amount + amt)
            refresh_invoice_outstanding(invoice)
    write_audit(db, user=user, action="POST", module="ar", record_type="CustomerCreditNote", record_id=note.id, document_no=note.credit_no)


def ar_totals(db: Session, *, project_id: int | None = None, customer_id: int | None = None) -> dict[str, Decimal]:
    filters = [CustomerInvoice.status.in_(POSTED_AR)]
    if project_id:
        filters.append(CustomerInvoice.project_id == project_id)
    if customer_id:
        filters.append(CustomerInvoice.customer_id == customer_id)
    demanded = money(db.execute(select(func.coalesce(func.sum(CustomerInvoice.total_receivable), 0)).where(*filters)).scalar())
    outstanding = money(db.execute(select(func.coalesce(func.sum(CustomerInvoice.outstanding_amount), 0)).where(*filters)).scalar())
    rfilters = [MoneyReceipt.status == DocStatus.POSTED.value]
    if project_id:
        rfilters.append(MoneyReceipt.project_id == project_id)
    if customer_id:
        rfilters.append(MoneyReceipt.customer_id == customer_id)
    receipts = money(db.execute(select(func.coalesce(func.sum(MoneyReceipt.amount), 0)).where(*rfilters)).scalar())
    return {"demanded": demanded, "receipts": receipts, "outstanding": outstanding}


def ar_aging(db: Session, *, as_of: date, project_id: int | None = None, customer_id: int | None = None) -> list[dict[str, Any]]:
    q = (
        select(CustomerInvoice)
        .options(selectinload(CustomerInvoice.customer), selectinload(CustomerInvoice.project))
        .where(CustomerInvoice.status.in_(POSTED_AR), CustomerInvoice.outstanding_amount > 0)
    )
    if project_id:
        q = q.where(CustomerInvoice.project_id == project_id)
    if customer_id:
        q = q.where(CustomerInvoice.customer_id == customer_id)
    buckets = ["current", "d1_30", "d31_60", "d61_90", "d91_180", "d181_365", "d365p"]
    rows = []
    for inv in db.execute(q).scalars():
        days = (as_of - inv.due_date).days
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
                "invoice": inv,
                "customer": inv.customer.name if inv.customer else "",
                "project": inv.project.code if inv.project else "",
                "invoice_no": inv.invoice_no,
                "due_date": inv.due_date,
                "days": max(days, 0) if days > 0 else 0,
                "outstanding": money(inv.outstanding_amount),
                "bucket": bucket,
                "overdue": days > 0,
            }
        )
    return rows


def aging_totals(rows: list[dict[str, Any]]) -> dict[str, Decimal]:
    totals = {k: ZERO for k in ["current", "d1_30", "d31_60", "d61_90", "d91_180", "d181_365", "d365p", "total", "overdue"]}
    for row in rows:
        totals[row["bucket"]] = money(totals[row["bucket"]] + row["outstanding"])
        totals["total"] = money(totals["total"] + row["outstanding"])
        if row["overdue"]:
            totals["overdue"] = money(totals["overdue"] + row["outstanding"])
    return totals


def customer_ledger(db: Session, customer_id: int, *, date_from: date | None = None, date_to: date | None = None) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    inv_q = select(CustomerInvoice).where(CustomerInvoice.customer_id == customer_id, CustomerInvoice.status.in_(POSTED_AR))
    rec_q = select(MoneyReceipt).where(MoneyReceipt.customer_id == customer_id, MoneyReceipt.status == DocStatus.POSTED.value)
    cn_q = select(CustomerCreditNote).where(CustomerCreditNote.customer_id == customer_id, CustomerCreditNote.status == DocStatus.POSTED.value)
    if date_from:
        inv_q = inv_q.where(CustomerInvoice.invoice_date >= date_from)
        rec_q = rec_q.where(MoneyReceipt.receipt_date >= date_from)
        cn_q = cn_q.where(CustomerCreditNote.credit_date >= date_from)
    if date_to:
        inv_q = inv_q.where(CustomerInvoice.invoice_date <= date_to)
        rec_q = rec_q.where(MoneyReceipt.receipt_date <= date_to)
        cn_q = cn_q.where(CustomerCreditNote.credit_date <= date_to)
    for inv in db.execute(inv_q).scalars():
        entries.append({"date": inv.invoice_date, "document": inv.invoice_no, "description": inv.description or "Demand / Invoice", "debit": money(inv.total_receivable), "credit": ZERO})
    for rec in db.execute(rec_q).scalars():
        entries.append({"date": rec.receipt_date, "document": rec.receipt_no, "description": rec.notes or "Money receipt", "debit": ZERO, "credit": money(rec.amount)})
    for cn in db.execute(cn_q).scalars():
        entries.append({"date": cn.credit_date, "document": cn.credit_no, "description": cn.reason or "Credit note", "debit": ZERO, "credit": money(cn.amount)})
    entries.sort(key=lambda e: (e["date"], e["document"]))
    running = ZERO
    for e in entries:
        running = money(running + e["debit"] - e["credit"])
        e["balance"] = running
    return entries
