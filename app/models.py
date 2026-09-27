from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.money import ZERO

Money = Numeric(18, 2)


def utcnow() -> datetime:
    return datetime.utcnow()


class UserRole(str, Enum):
    ADMIN = "ADMIN"
    ACCOUNTS_OFFICER = "ACCOUNTS_OFFICER"
    MANAGER = "MANAGER"
    AUDITOR = "AUDITOR"


class ProjectMode(str, Enum):
    DEVELOPER = "DEVELOPER"
    CONTRACTOR = "CONTRACTOR"


class AccountType(str, Enum):
    ASSET = "ASSET"
    LIABILITY = "LIABILITY"
    EQUITY = "EQUITY"
    REVENUE = "REVENUE"
    EXPENSE = "EXPENSE"


class DocStatus(str, Enum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    APPROVED = "APPROVED"
    POSTED = "POSTED"
    PARTIALLY_PAID = "PARTIALLY_PAID"
    PAID = "PAID"
    OVERDUE = "OVERDUE"
    CANCELLED = "CANCELLED"


class UnitStatus(str, Enum):
    UNSOLD = "UNSOLD"
    RESERVED = "RESERVED"
    BOOKED = "BOOKED"
    SOLD = "SOLD"
    CANCELLED = "CANCELLED"


class PaymentMethod(str, Enum):
    CASH = "CASH"
    CHEQUE = "CHEQUE"
    BANK_TRANSFER = "BANK_TRANSFER"
    MOBILE_BANKING = "MOBILE_BANKING"
    OTHER = "OTHER"


class MoneyAccountType(str, Enum):
    CASH = "CASH"
    BANK = "BANK"


class VendorType(str, Enum):
    CONTRACTOR = "CONTRACTOR"
    MATERIAL_SUPPLIER = "MATERIAL_SUPPLIER"
    SERVICE_PROVIDER = "SERVICE_PROVIDER"
    CONSULTANT = "CONSULTANT"
    OTHER = "OTHER"


class JournalSource(str, Enum):
    OPENING = "OPENING"
    MANUAL = "MANUAL"
    AR_INVOICE = "AR_INVOICE"
    AR_RECEIPT = "AR_RECEIPT"
    AR_CREDIT = "AR_CREDIT"
    AR_ADVANCE_APPLY = "AR_ADVANCE_APPLY"
    AP_BILL = "AP_BILL"
    AP_PAYMENT = "AP_PAYMENT"
    AP_CREDIT = "AP_CREDIT"
    TRANSFER = "TRANSFER"
    OTHER_RECEIPT = "OTHER_RECEIPT"
    OTHER_PAYMENT = "OTHER_PAYMENT"
    TDS_REMITTANCE = "TDS_REMITTANCE"
    RETENTION_SETTLEMENT = "RETENTION_SETTLEMENT"
    REVERSAL = "REVERSAL"


# ---------------------------------------------------------------------------
# Auth / admin
# ---------------------------------------------------------------------------


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    email: Mapped[str] = mapped_column(String(160), default="")
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(40), nullable=False, default=UserRole.ACCOUNTS_OFFICER.value)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class CompanySettings(Base):
    __tablename__ = "company_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), default="Razz CNPL")
    name_bn: Mapped[str] = mapped_column(String(200), default="রাজ সিএনপিএল")
    address: Mapped[str] = mapped_column(Text, default="Dhaka, Bangladesh")
    address_bn: Mapped[str] = mapped_column(Text, default="ঢাকা, বাংলাদেশ")
    phone: Mapped[str] = mapped_column(String(80), default="")
    email: Mapped[str] = mapped_column(String(160), default="")
    bin_number: Mapped[str] = mapped_column(String(80), default="")
    tin_number: Mapped[str] = mapped_column(String(80), default="")
    currency: Mapped[str] = mapped_column(String(8), default="BDT")
    currency_symbol: Mapped[str] = mapped_column(String(8), default="৳")
    default_vat_percent: Mapped[Decimal] = mapped_column(Money, default=Decimal("15.00"))
    default_retention_percent: Mapped[Decimal] = mapped_column(Money, default=Decimal("5.00"))
    fy_code: Mapped[str] = mapped_column(String(40), default="FY 2026-27")
    fy_start: Mapped[date] = mapped_column(Date, default=date(2026, 7, 1))
    fy_end: Mapped[date] = mapped_column(Date, default=date(2027, 6, 30))
    current_period: Mapped[str] = mapped_column(String(20), default="2026-07")
    notes: Mapped[str] = mapped_column(Text, default="")


class AccountingPeriod(Base):
    __tablename__ = "accounting_periods"
    __table_args__ = (UniqueConstraint("code", name="uq_period_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False)
    locked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    locked_by_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)


class DocumentSequence(Base):
    __tablename__ = "document_sequences"
    __table_args__ = (UniqueConstraint("doc_type", "year", name="uq_doc_seq_type_year"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    doc_type: Mapped[str] = mapped_column(String(20), nullable=False)
    prefix: Mapped[str] = mapped_column(String(20), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    next_number: Mapped[int] = mapped_column(Integer, default=1)
    padding: Mapped[int] = mapped_column(Integer, default=4)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    username: Mapped[str] = mapped_column(String(80), default="")
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    action: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    module: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    record_type: Mapped[str] = mapped_column(String(60), default="")
    record_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    document_no: Mapped[str] = mapped_column(String(60), default="")
    old_values: Mapped[str] = mapped_column(Text, default="")
    new_values: Mapped[str] = mapped_column(Text, default="")
    ip_address: Mapped[str] = mapped_column(String(80), default="")
    description: Mapped[str] = mapped_column(Text, default="")


# ---------------------------------------------------------------------------
# Masters
# ---------------------------------------------------------------------------


class ChartOfAccount(Base):
    __tablename__ = "chart_of_accounts"
    __table_args__ = (UniqueConstraint("code", name="uq_coa_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    name_bn: Mapped[str] = mapped_column(String(160), default="")
    account_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    parent_id: Mapped[Optional[int]] = mapped_column(ForeignKey("chart_of_accounts.id"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)
    system_key: Mapped[str] = mapped_column(String(40), default="", index=True)
    notes: Mapped[str] = mapped_column(Text, default="")

    parent: Mapped[Optional["ChartOfAccount"]] = relationship(remote_side="ChartOfAccount.id")


class TaxCategory(Base):
    __tablename__ = "tax_categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    tax_type: Mapped[str] = mapped_column(String(20), nullable=False)  # VAT / TDS / RETENTION
    percent: Mapped[Decimal] = mapped_column(Money, nullable=False)
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (UniqueConstraint("code", name="uq_project_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    name_bn: Mapped[str] = mapped_column(String(160), default="")
    mode: Mapped[str] = mapped_column(String(20), nullable=False, default=ProjectMode.DEVELOPER.value)
    client_name: Mapped[str] = mapped_column(String(160), default="")
    address: Mapped[str] = mapped_column(Text, default="")
    start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    expected_completion: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="ACTIVE")
    budget: Mapped[Decimal] = mapped_column(Money, default=ZERO)
    contract_value: Mapped[Decimal] = mapped_column(Money, default=ZERO)
    retention_percent: Mapped[Decimal] = mapped_column(Money, default=Decimal("5.00"))
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    units: Mapped[list["Unit"]] = relationship(back_populates="project")


class Unit(Base):
    __tablename__ = "units"
    __table_args__ = (
        UniqueConstraint("project_id", "unit_number", name="uq_unit_project_number"),
        Index("ix_units_project", "project_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    unit_number: Mapped[str] = mapped_column(String(40), nullable=False)
    floor: Mapped[str] = mapped_column(String(40), default="")
    size_sft: Mapped[Decimal] = mapped_column(Money, default=ZERO)
    base_price: Mapped[Decimal] = mapped_column(Money, default=ZERO)
    sale_price: Mapped[Decimal] = mapped_column(Money, default=ZERO)
    status: Mapped[str] = mapped_column(String(20), default=UnitStatus.UNSOLD.value, index=True)
    buyer_id: Mapped[Optional[int]] = mapped_column(ForeignKey("customers.id"), nullable=True)
    booking_id: Mapped[Optional[int]] = mapped_column(ForeignKey("bookings.id"), nullable=True)
    booking_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")

    project: Mapped["Project"] = relationship(back_populates="units")
    buyer: Mapped[Optional["Customer"]] = relationship(foreign_keys=[buyer_id])


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    name_bn: Mapped[str] = mapped_column(String(160), default="")
    father_name: Mapped[str] = mapped_column(String(160), default="")
    nid: Mapped[str] = mapped_column(String(40), default="")
    phone: Mapped[str] = mapped_column(String(40), default="")
    email: Mapped[str] = mapped_column(String(160), default="")
    address: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Vendor(Base):
    __tablename__ = "vendors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    name_bn: Mapped[str] = mapped_column(String(160), default="")
    vendor_type: Mapped[str] = mapped_column(String(40), default=VendorType.OTHER.value)
    tin: Mapped[str] = mapped_column(String(40), default="")
    bin_number: Mapped[str] = mapped_column(String(40), default="")
    phone: Mapped[str] = mapped_column(String(40), default="")
    email: Mapped[str] = mapped_column(String(160), default="")
    address: Mapped[str] = mapped_column(Text, default="")
    default_tds_percent: Mapped[Decimal] = mapped_column(Money, default=ZERO)
    default_tds_category_id: Mapped[Optional[int]] = mapped_column(ForeignKey("tax_categories.id"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Employee(Base):
    __tablename__ = "employees"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    designation: Mapped[str] = mapped_column(String(120), default="")
    phone: Mapped[str] = mapped_column(String(40), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class MoneyAccount(Base):
    __tablename__ = "money_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    account_type: Mapped[str] = mapped_column(String(20), nullable=False)
    bank_name: Mapped[str] = mapped_column(String(160), default="")
    account_number: Mapped[str] = mapped_column(String(80), default="")
    gl_account_id: Mapped[int] = mapped_column(ForeignKey("chart_of_accounts.id"), nullable=False)
    opening_balance: Mapped[Decimal] = mapped_column(Money, default=ZERO)
    opening_date: Mapped[date] = mapped_column(Date, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    gl_account: Mapped["ChartOfAccount"] = relationship()


# ---------------------------------------------------------------------------
# Bookings / AR
# ---------------------------------------------------------------------------


class Booking(Base):
    __tablename__ = "bookings"
    __table_args__ = (UniqueConstraint("booking_no", name="uq_booking_no"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    booking_no: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    booking_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), nullable=False, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id"), nullable=False)
    agreed_price: Mapped[Decimal] = mapped_column(Money, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default=DocStatus.POSTED.value, index=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_by_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    customer: Mapped["Customer"] = relationship()
    project: Mapped["Project"] = relationship()
    unit: Mapped["Unit"] = relationship(foreign_keys=[unit_id])
    schedules: Mapped[list["PaymentSchedule"]] = relationship(back_populates="booking")


class PaymentSchedule(Base):
    __tablename__ = "payment_schedules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    booking_id: Mapped[int] = mapped_column(ForeignKey("bookings.id"), nullable=False, index=True)
    installment_no: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(String(200), nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    percent: Mapped[Decimal] = mapped_column(Money, default=ZERO)
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    invoice_id: Mapped[Optional[int]] = mapped_column(ForeignKey("customer_invoices.id"), nullable=True)

    booking: Mapped["Booking"] = relationship(back_populates="schedules")


class CustomerInvoice(Base):
    __tablename__ = "customer_invoices"
    __table_args__ = (
        UniqueConstraint("invoice_no", name="uq_ar_invoice_no"),
        Index("ix_ar_customer_status", "customer_id", "status"),
        Index("ix_ar_due_date", "due_date"),
        Index("ix_ar_project", "project_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    invoice_no: Mapped[str] = mapped_column(String(40), nullable=False)
    invoice_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), nullable=False)
    project_id: Mapped[Optional[int]] = mapped_column(ForeignKey("projects.id"), nullable=True)
    unit_id: Mapped[Optional[int]] = mapped_column(ForeignKey("units.id"), nullable=True)
    booking_id: Mapped[Optional[int]] = mapped_column(ForeignKey("bookings.id"), nullable=True)
    description: Mapped[str] = mapped_column(Text, default="")
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    vat_percent: Mapped[Decimal] = mapped_column(Money, default=ZERO)
    vat_amount: Mapped[Decimal] = mapped_column(Money, default=ZERO)
    total_receivable: Mapped[Decimal] = mapped_column(Money, nullable=False)
    allocated_amount: Mapped[Decimal] = mapped_column(Money, default=ZERO)
    credit_amount: Mapped[Decimal] = mapped_column(Money, default=ZERO)
    outstanding_amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default=DocStatus.DRAFT.value, index=True)
    posted_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    journal_id: Mapped[Optional[int]] = mapped_column(ForeignKey("journal_entries.id"), nullable=True)
    created_by_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_by_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    customer: Mapped["Customer"] = relationship()
    project: Mapped[Optional["Project"]] = relationship()
    unit: Mapped[Optional["Unit"]] = relationship()
    booking: Mapped[Optional["Booking"]] = relationship(foreign_keys=[booking_id])
    allocations: Mapped[list["ReceiptAllocation"]] = relationship(back_populates="invoice")


class MoneyReceipt(Base):
    __tablename__ = "money_receipts"
    __table_args__ = (
        UniqueConstraint("receipt_no", name="uq_receipt_no"),
        Index("ix_mr_customer", "customer_id"),
        Index("ix_mr_date", "receipt_date"),
        Index("ix_mr_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    receipt_no: Mapped[str] = mapped_column(String(40), nullable=False)
    receipt_date: Mapped[date] = mapped_column(Date, nullable=False)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), nullable=False)
    project_id: Mapped[Optional[int]] = mapped_column(ForeignKey("projects.id"), nullable=True)
    unit_id: Mapped[Optional[int]] = mapped_column(ForeignKey("units.id"), nullable=True)
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    allocated_amount: Mapped[Decimal] = mapped_column(Money, default=ZERO)
    unallocated_amount: Mapped[Decimal] = mapped_column(Money, default=ZERO)
    is_advance: Mapped[bool] = mapped_column(Boolean, default=False)
    payment_method: Mapped[str] = mapped_column(String(30), default=PaymentMethod.BANK_TRANSFER.value)
    money_account_id: Mapped[int] = mapped_column(ForeignKey("money_accounts.id"), nullable=False)
    reference_no: Mapped[str] = mapped_column(String(80), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    received_by: Mapped[str] = mapped_column(String(160), default="")
    status: Mapped[str] = mapped_column(String(20), default=DocStatus.DRAFT.value)
    posted_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    journal_id: Mapped[Optional[int]] = mapped_column(ForeignKey("journal_entries.id"), nullable=True)
    created_by_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    customer: Mapped["Customer"] = relationship()
    project: Mapped[Optional["Project"]] = relationship()
    unit: Mapped[Optional["Unit"]] = relationship()
    money_account: Mapped["MoneyAccount"] = relationship()
    allocations: Mapped[list["ReceiptAllocation"]] = relationship(back_populates="receipt")


class ReceiptAllocation(Base):
    __tablename__ = "receipt_allocations"
    __table_args__ = (Index("ix_ralloc_receipt", "receipt_id"), Index("ix_ralloc_invoice", "invoice_id"))

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    receipt_id: Mapped[int] = mapped_column(ForeignKey("money_receipts.id"), nullable=False)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("customer_invoices.id"), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)

    receipt: Mapped["MoneyReceipt"] = relationship(back_populates="allocations")
    invoice: Mapped["CustomerInvoice"] = relationship(back_populates="allocations")


class CustomerCreditNote(Base):
    __tablename__ = "customer_credit_notes"
    __table_args__ = (UniqueConstraint("credit_no", name="uq_ar_credit_no"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    credit_no: Mapped[str] = mapped_column(String(40), nullable=False)
    credit_date: Mapped[date] = mapped_column(Date, nullable=False)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), nullable=False)
    invoice_id: Mapped[Optional[int]] = mapped_column(ForeignKey("customer_invoices.id"), nullable=True)
    project_id: Mapped[Optional[int]] = mapped_column(ForeignKey("projects.id"), nullable=True)
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    reason: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default=DocStatus.DRAFT.value)
    journal_id: Mapped[Optional[int]] = mapped_column(ForeignKey("journal_entries.id"), nullable=True)
    created_by_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    customer: Mapped["Customer"] = relationship()
    invoice: Mapped[Optional["CustomerInvoice"]] = relationship()


# ---------------------------------------------------------------------------
# AP
# ---------------------------------------------------------------------------


class VendorBill(Base):
    __tablename__ = "vendor_bills"
    __table_args__ = (
        UniqueConstraint("bill_no", name="uq_bill_no"),
        Index("ix_bill_vendor", "vendor_id"),
        Index("ix_bill_date", "bill_date"),
        Index("ix_bill_due", "due_date"),
        Index("ix_bill_status", "status"),
        Index("ix_bill_project", "project_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bill_no: Mapped[str] = mapped_column(String(40), nullable=False)
    vendor_bill_ref: Mapped[str] = mapped_column(String(80), default="")
    bill_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    vendor_id: Mapped[int] = mapped_column(ForeignKey("vendors.id"), nullable=False)
    project_id: Mapped[Optional[int]] = mapped_column(ForeignKey("projects.id"), nullable=True)
    description: Mapped[str] = mapped_column(Text, default="")
    gross_amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    vat_percent: Mapped[Decimal] = mapped_column(Money, default=ZERO)
    vat_amount: Mapped[Decimal] = mapped_column(Money, default=ZERO)
    tds_percent: Mapped[Decimal] = mapped_column(Money, default=ZERO)
    tds_amount: Mapped[Decimal] = mapped_column(Money, default=ZERO)
    retention_percent: Mapped[Decimal] = mapped_column(Money, default=ZERO)
    retention_amount: Mapped[Decimal] = mapped_column(Money, default=ZERO)
    net_payable: Mapped[Decimal] = mapped_column(Money, nullable=False)
    allocated_amount: Mapped[Decimal] = mapped_column(Money, default=ZERO)
    credit_amount: Mapped[Decimal] = mapped_column(Money, default=ZERO)
    outstanding_amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    mushak_ref: Mapped[str] = mapped_column(String(80), default="")
    cost_account_id: Mapped[int] = mapped_column(ForeignKey("chart_of_accounts.id"), nullable=False)
    tds_category_id: Mapped[Optional[int]] = mapped_column(ForeignKey("tax_categories.id"), nullable=True)
    tds_certificate_no: Mapped[str] = mapped_column(String(80), default="")
    tds_remitted: Mapped[bool] = mapped_column(Boolean, default=False)
    retention_settled: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default=DocStatus.DRAFT.value)
    notes: Mapped[str] = mapped_column(Text, default="")
    posted_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    journal_id: Mapped[Optional[int]] = mapped_column(ForeignKey("journal_entries.id"), nullable=True)
    created_by_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_by_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    vendor: Mapped["Vendor"] = relationship()
    project: Mapped[Optional["Project"]] = relationship()
    cost_account: Mapped["ChartOfAccount"] = relationship()
    allocations: Mapped[list["PaymentAllocation"]] = relationship(back_populates="bill")


class VendorPayment(Base):
    __tablename__ = "vendor_payments"
    __table_args__ = (
        UniqueConstraint("payment_no", name="uq_payment_no"),
        Index("ix_vp_vendor", "vendor_id"),
        Index("ix_vp_date", "payment_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    payment_no: Mapped[str] = mapped_column(String(40), nullable=False)
    payment_date: Mapped[date] = mapped_column(Date, nullable=False)
    vendor_id: Mapped[int] = mapped_column(ForeignKey("vendors.id"), nullable=False)
    project_id: Mapped[Optional[int]] = mapped_column(ForeignKey("projects.id"), nullable=True)
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    allocated_amount: Mapped[Decimal] = mapped_column(Money, default=ZERO)
    unallocated_amount: Mapped[Decimal] = mapped_column(Money, default=ZERO)
    is_advance: Mapped[bool] = mapped_column(Boolean, default=False)
    payment_method: Mapped[str] = mapped_column(String(30), default=PaymentMethod.BANK_TRANSFER.value)
    money_account_id: Mapped[int] = mapped_column(ForeignKey("money_accounts.id"), nullable=False)
    reference_no: Mapped[str] = mapped_column(String(80), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default=DocStatus.DRAFT.value)
    posted_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    journal_id: Mapped[Optional[int]] = mapped_column(ForeignKey("journal_entries.id"), nullable=True)
    created_by_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_by_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    vendor: Mapped["Vendor"] = relationship()
    project: Mapped[Optional["Project"]] = relationship()
    money_account: Mapped["MoneyAccount"] = relationship()
    allocations: Mapped[list["PaymentAllocation"]] = relationship(back_populates="payment")


class PaymentAllocation(Base):
    __tablename__ = "payment_allocations"
    __table_args__ = (Index("ix_palloc_payment", "payment_id"), Index("ix_palloc_bill", "bill_id"))

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    payment_id: Mapped[int] = mapped_column(ForeignKey("vendor_payments.id"), nullable=False)
    bill_id: Mapped[int] = mapped_column(ForeignKey("vendor_bills.id"), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)

    payment: Mapped["VendorPayment"] = relationship(back_populates="allocations")
    bill: Mapped["VendorBill"] = relationship(back_populates="allocations")


class VendorCreditNote(Base):
    __tablename__ = "vendor_credit_notes"
    __table_args__ = (UniqueConstraint("credit_no", name="uq_ap_credit_no"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    credit_no: Mapped[str] = mapped_column(String(40), nullable=False)
    credit_date: Mapped[date] = mapped_column(Date, nullable=False)
    vendor_id: Mapped[int] = mapped_column(ForeignKey("vendors.id"), nullable=False)
    bill_id: Mapped[Optional[int]] = mapped_column(ForeignKey("vendor_bills.id"), nullable=True)
    project_id: Mapped[Optional[int]] = mapped_column(ForeignKey("projects.id"), nullable=True)
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    reason: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default=DocStatus.DRAFT.value)
    journal_id: Mapped[Optional[int]] = mapped_column(ForeignKey("journal_entries.id"), nullable=True)
    created_by_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    vendor: Mapped["Vendor"] = relationship()
    bill: Mapped[Optional["VendorBill"]] = relationship()


# ---------------------------------------------------------------------------
# Cash / other / journals
# ---------------------------------------------------------------------------


class BankTransfer(Base):
    __tablename__ = "bank_transfers"
    __table_args__ = (UniqueConstraint("transfer_no", name="uq_transfer_no"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    transfer_no: Mapped[str] = mapped_column(String(40), nullable=False)
    transfer_date: Mapped[date] = mapped_column(Date, nullable=False)
    from_account_id: Mapped[int] = mapped_column(ForeignKey("money_accounts.id"), nullable=False)
    to_account_id: Mapped[int] = mapped_column(ForeignKey("money_accounts.id"), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    reference_no: Mapped[str] = mapped_column(String(80), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default=DocStatus.DRAFT.value)
    journal_id: Mapped[Optional[int]] = mapped_column(ForeignKey("journal_entries.id"), nullable=True)
    created_by_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    from_account: Mapped["MoneyAccount"] = relationship(foreign_keys=[from_account_id])
    to_account: Mapped["MoneyAccount"] = relationship(foreign_keys=[to_account_id])


class OtherCashTxn(Base):
    __tablename__ = "other_cash_txns"
    __table_args__ = (UniqueConstraint("txn_no", name="uq_other_txn_no"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    txn_no: Mapped[str] = mapped_column(String(40), nullable=False)
    txn_date: Mapped[date] = mapped_column(Date, nullable=False)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)  # IN / OUT
    money_account_id: Mapped[int] = mapped_column(ForeignKey("money_accounts.id"), nullable=False)
    gl_account_id: Mapped[int] = mapped_column(ForeignKey("chart_of_accounts.id"), nullable=False)
    project_id: Mapped[Optional[int]] = mapped_column(ForeignKey("projects.id"), nullable=True)
    payee_name: Mapped[str] = mapped_column(String(160), default="")
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    payment_method: Mapped[str] = mapped_column(String(30), default=PaymentMethod.CASH.value)
    reference_no: Mapped[str] = mapped_column(String(80), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default=DocStatus.DRAFT.value)
    journal_id: Mapped[Optional[int]] = mapped_column(ForeignKey("journal_entries.id"), nullable=True)
    created_by_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    money_account: Mapped["MoneyAccount"] = relationship()
    gl_account: Mapped["ChartOfAccount"] = relationship()
    project: Mapped[Optional["Project"]] = relationship()


class JournalEntry(Base):
    __tablename__ = "journal_entries"
    __table_args__ = (
        UniqueConstraint("entry_no", name="uq_journal_no"),
        Index("ix_je_date", "entry_date"),
        Index("ix_je_source", "source_module"),
        Index("ix_je_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entry_no: Mapped[str] = mapped_column(String(40), nullable=False)
    entry_date: Mapped[date] = mapped_column(Date, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    source_module: Mapped[str] = mapped_column(String(40), default=JournalSource.MANUAL.value)
    source_document: Mapped[str] = mapped_column(String(60), default="")
    source_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    project_id: Mapped[Optional[int]] = mapped_column(ForeignKey("projects.id"), nullable=True)
    total_debit: Mapped[Decimal] = mapped_column(Money, default=ZERO)
    total_credit: Mapped[Decimal] = mapped_column(Money, default=ZERO)
    status: Mapped[str] = mapped_column(String(20), default=DocStatus.DRAFT.value)
    reversal_of_id: Mapped[Optional[int]] = mapped_column(ForeignKey("journal_entries.id"), nullable=True)
    created_by_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    posted_by_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    posted_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    project: Mapped[Optional["Project"]] = relationship()
    lines: Mapped[list["JournalLine"]] = relationship(back_populates="entry", cascade="all, delete-orphan")


class JournalLine(Base):
    __tablename__ = "journal_lines"
    __table_args__ = (Index("ix_jl_account", "account_id"), Index("ix_jl_entry", "entry_id"))

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entry_id: Mapped[int] = mapped_column(ForeignKey("journal_entries.id"), nullable=False)
    account_id: Mapped[int] = mapped_column(ForeignKey("chart_of_accounts.id"), nullable=False)
    project_id: Mapped[Optional[int]] = mapped_column(ForeignKey("projects.id"), nullable=True)
    debit: Mapped[Decimal] = mapped_column(Money, default=ZERO)
    credit: Mapped[Decimal] = mapped_column(Money, default=ZERO)
    description: Mapped[str] = mapped_column(String(255), default="")

    entry: Mapped["JournalEntry"] = relationship(back_populates="lines")
    account: Mapped["ChartOfAccount"] = relationship()
    project: Mapped[Optional["Project"]] = relationship()
