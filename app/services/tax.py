from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.money import money, pct_amount


def calculate_vendor_bill(
    gross_amount: Any,
    vat_percent: Any,
    tds_percent: Any,
    retention_percent: Any,
) -> dict[str, Decimal]:
    gross = money(gross_amount)
    vat_p = money(vat_percent)
    tds_p = money(tds_percent)
    ret_p = money(retention_percent)
    if gross < 0:
        raise ValueError("Gross amount cannot be negative.")
    for label, pct in (("VAT", vat_p), ("TDS", tds_p), ("Retention", ret_p)):
        if pct < 0 or pct > 100:
            raise ValueError(f"{label} percent must be between 0 and 100.")
    vat = pct_amount(gross, vat_p)
    tds = pct_amount(gross, tds_p)
    retention = pct_amount(gross, ret_p)
    net = money(gross + vat - tds - retention)
    return {
        "gross_amount": gross,
        "vat_percent": vat_p,
        "vat_amount": vat,
        "tds_percent": tds_p,
        "tds_amount": tds,
        "retention_percent": ret_p,
        "retention_amount": retention,
        "net_payable": net,
    }


def calculate_invoice(amount: Any, vat_percent: Any = 0) -> dict[str, Decimal]:
    base = money(amount)
    vat_p = money(vat_percent)
    if base < 0:
        raise ValueError("Amount cannot be negative.")
    vat = pct_amount(base, vat_p)
    total = money(base + vat)
    return {
        "amount": base,
        "vat_percent": vat_p,
        "vat_amount": vat,
        "total_receivable": total,
    }
