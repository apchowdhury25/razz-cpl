"""TS-TAX-01..04 — vendor bill VAT / TDS / retention / net payable."""

from decimal import Decimal

from app.services.tax import calculate_vendor_bill

BILL_CASES = [
    ("RC/MTT/2026/001", "2500000", "15", "5", "5", "375000", "125000", "125000", "2625000"),
    ("DS/MTT/2026/002", "850000", "15", "2", "0", "127500", "17000", "0", "960500"),
    ("SE/SM/2026/003", "420000", "15", "7.5", "0", "63000", "31500", "0", "451500"),
    ("KT/WP/2026/004", "310000", "15", "2", "0", "46500", "6200", "0", "350300"),
]


def test_seed_bill_formulas():
    for ref, gross, vat_p, tds_p, ret_p, vat, tds, ret, net in BILL_CASES:
        result = calculate_vendor_bill(gross, vat_p, tds_p, ret_p)
        assert result["vat_amount"] == Decimal(vat), ref
        assert result["tds_amount"] == Decimal(tds), ref
        assert result["retention_amount"] == Decimal(ret), ref
        assert result["net_payable"] == Decimal(net), ref
        assert result["gross_amount"] + result["vat_amount"] == result["net_payable"] + result["tds_amount"] + result["retention_amount"]


def test_example_from_spec():
    result = calculate_vendor_bill("2500000", "15", "5", "5")
    assert result["net_payable"] == Decimal("2625000")


def test_rejects_negative_gross():
    try:
        calculate_vendor_bill("-1", "15", "5", "5")
        assert False, "should have raised"
    except ValueError:
        pass
