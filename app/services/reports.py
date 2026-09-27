from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    Booking,
    CustomerInvoice,
    DocStatus,
    JournalEntry,
    JournalLine,
    MoneyReceipt,
    Project,
    Unit,
    VendorBill,
    VendorPayment,
)
from app.money import ZERO, money
from app.services.accounting import get_system_account, trial_balance
from app.services.ap import POSTED_AP, ap_aging, ap_totals
from app.services.ar import POSTED_AR, ar_aging, ar_totals
from app.services.cash_bank import cash_bank_totals


def dashboard_data(db: Session, as_of: date) -> dict[str, Any]:
    ar_rows = ar_aging(db, as_of=as_of)
    ap_rows = ap_aging(db, as_of=as_of)
    from app.services.ar import aging_totals

    ar_age = aging_totals(ar_rows)
    ap_age = aging_totals(ap_rows)
    ar = ar_totals(db)
    ap = ap_totals(db)
    cash = cash_bank_totals(db, as_of=as_of)

    try:
        tds_acc = get_system_account(db, "TDS_PAYABLE")
        input_vat_acc = get_system_account(db, "INPUT_VAT")
        output_vat_acc = get_system_account(db, "OUTPUT_VAT")
        from app.services.accounting import account_balance

        tds_bal = account_balance(db, tds_acc.id, as_of=as_of)
        input_vat_bal = account_balance(db, input_vat_acc.id, as_of=as_of)
        output_vat_bal = account_balance(db, output_vat_acc.id, as_of=as_of)
        tds_payable = money(tds_bal["credit"] - tds_bal["debit"])
        input_vat = money(input_vat_bal["debit"] - input_vat_bal["credit"])
        output_vat = money(output_vat_bal["credit"] - output_vat_bal["debit"])
    except Exception:
        tds_payable = ap["tds"]
        input_vat = ap["vat"]
        output_vat = ZERO

    projects = project_summaries(db)
    recent_receipts = db.execute(
        select(MoneyReceipt).options(selectinload(MoneyReceipt.customer)).where(MoneyReceipt.status == DocStatus.POSTED.value).order_by(MoneyReceipt.id.desc()).limit(8)
    ).scalars().all()
    recent_bills = db.execute(
        select(VendorBill).options(selectinload(VendorBill.vendor)).where(VendorBill.status.in_(POSTED_AP)).order_by(VendorBill.id.desc()).limit(8)
    ).scalars().all()
    recent_payments = db.execute(
        select(VendorPayment).options(selectinload(VendorPayment.vendor)).where(VendorPayment.status == DocStatus.POSTED.value).order_by(VendorPayment.id.desc()).limit(8)
    ).scalars().all()
    recent_journals = db.execute(
        select(JournalEntry).where(JournalEntry.status == DocStatus.POSTED.value).order_by(JournalEntry.id.desc()).limit(8)
    ).scalars().all()

    return {
        "ar": ar,
        "ap": ap,
        "ar_age": ar_age,
        "ap_age": ap_age,
        "cash": cash,
        "tds_payable": tds_payable,
        "input_vat": input_vat,
        "output_vat": output_vat,
        "projects": projects,
        "recent_receipts": recent_receipts,
        "recent_bills": recent_bills,
        "recent_payments": recent_payments,
        "recent_journals": recent_journals,
        "as_of": as_of,
    }


def project_summaries(db: Session) -> list[dict[str, Any]]:
    projects = db.execute(select(Project).order_by(Project.code)).scalars().all()
    result = []
    for p in projects:
        result.append(project_accounting(db, p))
    return result


def project_accounting(db: Session, project: Project) -> dict[str, Any]:
    revenue_keys = {"SALES_REVENUE", "CONTRACT_REVENUE"}
    revenue_ids = [a.id for a in db.execute(select(__import__("app.models", fromlist=["ChartOfAccount"]).ChartOfAccount)).scalars() if a.system_key in revenue_keys or a.account_type == "REVENUE"]
    from app.models import ChartOfAccount

    revenue_ids = [a.id for a in db.execute(select(ChartOfAccount).where(ChartOfAccount.account_type == "REVENUE")).scalars()]
    expense_ids = [a.id for a in db.execute(select(ChartOfAccount).where(ChartOfAccount.account_type == "EXPENSE")).scalars()]

    def _sum(account_ids, side: str) -> Any:
        if not account_ids:
            return ZERO
        filters = [
            JournalLine.account_id.in_(account_ids),
            JournalLine.project_id == project.id,
            JournalEntry.status == DocStatus.POSTED.value,
            JournalLine.entry_id == JournalEntry.id,
        ]
        debit = money(db.execute(select(func.coalesce(func.sum(JournalLine.debit), 0)).where(*filters)).scalar())
        credit = money(db.execute(select(func.coalesce(func.sum(JournalLine.credit), 0)).where(*filters)).scalar())
        if side == "revenue":
            return money(credit - debit)
        return money(debit - credit)

    revenue = _sum(revenue_ids, "revenue")
    cost = _sum(expense_ids, "cost")
    ar = ar_totals(db, project_id=project.id)
    ap = ap_totals(db, project_id=project.id)
    units = db.execute(select(Unit).where(Unit.project_id == project.id)).scalars().all()
    unit_stats = {
        "total": len(units),
        "unsold": sum(1 for u in units if u.status == "UNSOLD"),
        "booked": sum(1 for u in units if u.status == "BOOKED"),
        "sold": sum(1 for u in units if u.status == "SOLD"),
        "reserved": sum(1 for u in units if u.status == "RESERVED"),
        "sales_value": money(sum((u.sale_price or ZERO) for u in units if u.status in ("BOOKED", "SOLD"))),
    }
    booked_value = money(
        db.execute(select(func.coalesce(func.sum(Booking.agreed_price), 0)).where(Booking.project_id == project.id, Booking.status != DocStatus.CANCELLED.value)).scalar()
    )
    budget_util = ZERO
    if project.budget and project.budget > 0:
        budget_util = money(cost * 100 / project.budget)
    return {
        "project": project,
        "revenue": revenue,
        "cost": cost,
        "gross_result": money(revenue - cost),
        "receivable": ar["outstanding"],
        "payable": ap["outstanding"],
        "cash_collected": ar["receipts"],
        "cash_paid": ap["paid"],
        "budget": money(project.budget),
        "budget_util": budget_util,
        "contract_value": money(project.contract_value),
        "units": unit_stats,
        "booked_value": booked_value,
        "billed": ar["demanded"],
        "vendor_costs": ap["gross"],
    }


def vat_rows(db: Session, *, date_from: date | None = None, date_to: date | None = None, project_id: int | None = None):
    q = select(VendorBill).options(selectinload(VendorBill.vendor), selectinload(VendorBill.project)).where(
        VendorBill.status.in_(POSTED_AP), VendorBill.vat_amount > 0
    )
    if date_from:
        q = q.where(VendorBill.bill_date >= date_from)
    if date_to:
        q = q.where(VendorBill.bill_date <= date_to)
    if project_id:
        q = q.where(VendorBill.project_id == project_id)
    return db.execute(q.order_by(VendorBill.bill_date, VendorBill.id)).scalars().all()


def tds_rows(db: Session, *, date_from: date | None = None, date_to: date | None = None, project_id: int | None = None):
    q = select(VendorBill).options(selectinload(VendorBill.vendor), selectinload(VendorBill.project)).where(
        VendorBill.status.in_(POSTED_AP), VendorBill.tds_amount > 0
    )
    if date_from:
        q = q.where(VendorBill.bill_date >= date_from)
    if date_to:
        q = q.where(VendorBill.bill_date <= date_to)
    if project_id:
        q = q.where(VendorBill.project_id == project_id)
    return db.execute(q.order_by(VendorBill.bill_date, VendorBill.id)).scalars().all()


def daily_transactions(db: Session, txn_date: date, project_id: int | None = None):
    rec_q = select(MoneyReceipt).options(selectinload(MoneyReceipt.customer)).where(MoneyReceipt.receipt_date == txn_date, MoneyReceipt.status == DocStatus.POSTED.value)
    bill_q = select(VendorBill).options(selectinload(VendorBill.vendor)).where(VendorBill.bill_date == txn_date, VendorBill.status.in_(POSTED_AP))
    pay_q = select(VendorPayment).options(selectinload(VendorPayment.vendor)).where(VendorPayment.payment_date == txn_date, VendorPayment.status == DocStatus.POSTED.value)
    je_q = select(JournalEntry).where(JournalEntry.entry_date == txn_date, JournalEntry.status == DocStatus.POSTED.value)
    if project_id:
        rec_q = rec_q.where(MoneyReceipt.project_id == project_id)
        bill_q = bill_q.where(VendorBill.project_id == project_id)
        pay_q = pay_q.where(VendorPayment.project_id == project_id)
        je_q = je_q.where(JournalEntry.project_id == project_id)
    return {
        "receipts": db.execute(rec_q).scalars().all(),
        "bills": db.execute(bill_q).scalars().all(),
        "payments": db.execute(pay_q).scalars().all(),
        "journals": db.execute(je_q).scalars().all(),
    }


def monthly_transactions(db: Session, year: int, month: int, project_id: int | None = None):
    start = date(year, month, 1)
    if month == 12:
        end = date(year + 1, 1, 1)
        from datetime import timedelta

        end = end - timedelta(days=1)
    else:
        from datetime import timedelta

        end = date(year, month + 1, 1) - timedelta(days=1)
    rec_q = select(MoneyReceipt).options(selectinload(MoneyReceipt.customer)).where(
        MoneyReceipt.receipt_date >= start, MoneyReceipt.receipt_date <= end, MoneyReceipt.status == DocStatus.POSTED.value
    )
    bill_q = select(VendorBill).options(selectinload(VendorBill.vendor)).where(
        VendorBill.bill_date >= start, VendorBill.bill_date <= end, VendorBill.status.in_(POSTED_AP)
    )
    pay_q = select(VendorPayment).options(selectinload(VendorPayment.vendor)).where(
        VendorPayment.payment_date >= start, VendorPayment.payment_date <= end, VendorPayment.status == DocStatus.POSTED.value
    )
    if project_id:
        rec_q = rec_q.where(MoneyReceipt.project_id == project_id)
        bill_q = bill_q.where(VendorBill.project_id == project_id)
        pay_q = pay_q.where(VendorPayment.project_id == project_id)
    return {
        "start": start,
        "end": end,
        "receipts": db.execute(rec_q.order_by(MoneyReceipt.receipt_date)).scalars().all(),
        "bills": db.execute(bill_q.order_by(VendorBill.bill_date)).scalars().all(),
        "payments": db.execute(pay_q.order_by(VendorPayment.payment_date)).scalars().all(),
    }


def trial_balance_ok(db: Session) -> bool:
    rows = trial_balance(db)
    total_dr = money(sum((r["debit"] for r in rows), ZERO))
    total_cr = money(sum((r["credit"] for r in rows), ZERO))
    return total_dr == total_cr
