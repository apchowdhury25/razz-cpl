"""Create a new record through each major module, as an accounts officer would."""

from sqlalchemy import select

from app.models import (
    Booking,
    ChartOfAccount,
    Customer,
    CustomerInvoice,
    MoneyAccount,
    MoneyReceipt,
    Project,
    Unit,
    Vendor,
    VendorBill,
    VendorPayment,
)
from tests.conftest import extract_csrf, login


def _csrf(client) -> str:
    return extract_csrf(client.get("/").text)


def test_end_to_end_create_entries(client, db):
    login(client, "admin", "admin123")
    csrf = _csrf(client)

    customer = db.execute(select(Customer).where(Customer.code == "CU-0001")).scalar_one()
    vendor = db.execute(select(Vendor).where(Vendor.code == "VE-0001")).scalar_one()
    project = db.execute(select(Project).where(Project.code == "GV")).scalar_one()
    unit = db.execute(select(Unit).where(Unit.project_id == project.id, Unit.status == "UNSOLD")).scalars().first()
    bank = db.execute(select(MoneyAccount).where(MoneyAccount.name == "BRAC Bank - Current")).scalar_one()
    cash = db.execute(select(MoneyAccount).where(MoneyAccount.name == "Petty Cash")).scalar_one()
    cost = db.execute(select(ChartOfAccount).where(ChartOfAccount.system_key == "MATERIALS")).scalar_one()
    cash_gl = db.execute(select(ChartOfAccount).where(ChartOfAccount.system_key == "PETTY_CASH")).scalar_one()
    bank_gl = db.execute(select(ChartOfAccount).where(ChartOfAccount.system_key == "BRAC_BANK")).scalar_one()

    r = client.post(
        "/customers/new",
        data={"csrf": csrf, "name": "E2E Buyer", "name_bn": "ইটুই ক্রেতা", "phone": "01700000001", "address": "Dhaka"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert db.execute(select(Customer).where(Customer.name == "E2E Buyer")).scalar_one_or_none()

    r = client.post(
        "/vendors/new",
        data={"csrf": csrf, "name": "E2E Supplier", "vendor_type": "MATERIAL_SUPPLIER", "default_tds_percent": "2", "address": "Tejgaon"},
        follow_redirects=False,
    )
    assert r.status_code == 303

    r = client.post(
        "/projects/new",
        data={
            "csrf": csrf, "code": "E2E", "name": "E2E Project", "name_bn": "পরীক্ষা",
            "mode": "DEVELOPER", "status": "ACTIVE", "budget": "1000000", "contract_value": "0",
            "retention_percent": "5", "start_date": "01/07/2026",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303

    r = client.post(
        "/units/new",
        data={
            "csrf": csrf, "project_id": str(project.id), "unit_number": "E2E-101",
            "floor": "1", "size_sft": "1000", "base_price": "5000000", "sale_price": "5000000", "status": "UNSOLD",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303

    e2e_unit = db.execute(select(Unit).where(Unit.unit_number == "E2E-101")).scalar_one()
    r = client.post(
        "/bookings/new",
        data={
            "csrf": csrf, "booking_date": "09/03/2026", "customer_id": str(customer.id),
            "unit_id": str(e2e_unit.id), "agreed_price": "5000000", "notes": "E2E booking",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert db.execute(select(Booking).where(Booking.notes == "E2E booking")).scalar_one_or_none()

    r = client.post(
        "/ar/invoices/new",
        data={
            "csrf": csrf, "invoice_date": "09/03/2026", "due_date": "09/04/2026",
            "customer_id": str(customer.id), "project_id": str(project.id),
            "amount": "91670", "vat_percent": "0", "description": "E2E extra demand",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    extra = db.execute(select(CustomerInvoice).where(CustomerInvoice.description == "E2E extra demand")).scalar_one()
    post = client.post(f"/ar/invoices/{extra.id}/post", data={"csrf": csrf}, follow_redirects=False)
    assert post.status_code == 303
    db.refresh(extra)
    assert extra.status in ("POSTED", "PARTIALLY_PAID", "PAID")

    r = client.post(
        "/receipts/new",
        data={
            "csrf": csrf, "receipt_date": "10/03/2026", "customer_id": str(customer.id),
            "project_id": str(project.id), "amount": "1000", "money_account_id": str(bank.id),
            "payment_method": "BANK_TRANSFER", "is_advance": "1", "notes": "E2E receipt",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    receipt = db.execute(select(MoneyReceipt).where(MoneyReceipt.notes == "E2E receipt")).scalar_one()
    client.post(f"/receipts/{receipt.id}/post", data={"csrf": csrf}, follow_redirects=False)
    db.refresh(receipt)
    assert receipt.status == "POSTED"

    r = client.post(
        "/bills/new",
        data={
            "csrf": csrf, "bill_date": "11/03/2026", "due_date": "10/04/2026",
            "vendor_id": str(vendor.id), "project_id": str(project.id),
            "description": "E2E cement", "gross_amount": "100000", "vat_percent": "15",
            "tds_percent": "2", "retention_percent": "0", "cost_account_id": str(cost.id),
            "vendor_bill_ref": "E2E/001", "mushak_ref": "M-E2E-1",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    bill = db.execute(select(VendorBill).where(VendorBill.vendor_bill_ref == "E2E/001")).scalar_one()
    client.post(f"/bills/{bill.id}/post", data={"csrf": csrf}, follow_redirects=False)
    db.refresh(bill)
    assert bill.status in ("POSTED", "PARTIALLY_PAID", "PAID")
    assert str(bill.bill_date) == "2026-03-11"

    r = client.post(
        "/payments/new",
        data={
            "csrf": csrf, "payment_date": "12/03/2026", "vendor_id": str(vendor.id),
            "amount": "1000", "money_account_id": str(bank.id), "payment_method": "BANK_TRANSFER",
            "is_advance": "1", "notes": "E2E payment", f"alloc_{bill.id}": "1000",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    pay = db.execute(select(VendorPayment).where(VendorPayment.notes == "E2E payment")).scalar_one()
    client.post(f"/payments/{pay.id}/post", data={"csrf": csrf}, follow_redirects=False)
    db.refresh(pay)
    assert pay.status == "POSTED"

    r = client.post(
        "/accounting/journals/new",
        data={
            "csrf": csrf, "entry_date": "13/03/2026", "description": "E2E manual journal",
            "post_now": "1", "account_id_0": str(cash_gl.id), "debit_0": "10", "credit_0": "0",
            "account_id_1": str(bank_gl.id), "debit_1": "0", "credit_1": "10",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303

    r = client.post(
        "/cash/transfers/new",
        data={
            "csrf": csrf, "transfer_date": "14/03/2026", "from_account_id": str(bank.id),
            "to_account_id": str(cash.id), "amount": "100", "notes": "E2E transfer",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303

    for path in (
        "/", "/customers", "/vendors", "/projects", "/units", "/bookings",
        "/ar/invoices", "/receipts", "/bills", "/payments",
        "/ar/aging", "/ap/aging", "/accounting/journals", "/cash/transfers",
        "/accounting/trial-balance",
    ):
        page = client.get(path)
        assert page.status_code == 200, path
        assert "Internal Server Error" not in page.text
        if path == "/ar/invoices":
            assert "DD/MM/YYYY" in page.text or "09/03/2026" in page.text or "15/07/2026" in page.text
