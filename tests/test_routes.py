"""TS-UI — every major page must load after login. No placeholder, no 500."""

from tests.conftest import login

PAGES = [
    ("/", "dashboard"),
    ("/projects", "projects"),
    ("/units", "units"),
    ("/customers", "customers"),
    ("/vendors", "vendors"),
    ("/bookings", "bookings"),
    ("/ar/invoices", "invoices"),
    ("/receipts", "receipts"),
    ("/bills", "bills"),
    ("/payments", "payments"),
    ("/ar/aging", "aging"),
    ("/ap/aging", "aging"),
    ("/ar/ledger", "ledger"),
    ("/ap/ledger", "ledger"),
    ("/ar/outstanding", "outstanding"),
    ("/ap/outstanding", "outstanding"),
    ("/ar/advances", "advance"),
    ("/ar/credits", "credit"),
    ("/cash/accounts", "cash"),
    ("/cash/transfers", "transfer"),
    ("/cash/other", "other"),
    ("/cash/book", "cash"),
    ("/cash/bank-book", "bank"),
    ("/accounting/coa", "chart"),
    ("/accounting/journals", "journal"),
    ("/accounting/gl", "ledger"),
    ("/accounting/trial-balance", "trial"),
    ("/tax/vat", "vat"),
    ("/tax/tds", "tds"),
    ("/tax/settings", "tax"),
    ("/reports", "reports"),
    ("/reports/project-pnl", "project"),
    ("/reports/project-cost", "cost"),
    ("/reports/project-cashflow", "cash"),
    ("/reports/daily", "daily"),
    ("/reports/monthly", "monthly"),
    ("/admin/users", "user"),
    ("/admin/roles", "role"),
    ("/admin/settings", "setting"),
    ("/admin/periods", "period"),
    ("/admin/numbering", "number"),
    ("/admin/audit", "audit"),
    ("/admin/backup", "backup"),
    ("/admin/employees", "employee"),
]


def test_all_major_pages_load(client):
    login(client, "admin", "admin123")
    failures = []
    for path, _hint in PAGES:
        response = client.get(path)
        if response.status_code != 200:
            failures.append(f"{path} -> {response.status_code}")
            continue
        text = response.text.lower()
        if "coming soon" in text or "todo" in text or "not implemented" in text:
            failures.append(f"{path} contains placeholder")
        if "internal server error" in text or "traceback" in text:
            failures.append(f"{path} leaked a server error")
    assert not failures, "\n".join(failures)


def test_dashboard_totals_are_live_not_hardcoded_labels_only(client):
    login(client, "admin", "admin123")
    page = client.get("/")
    assert "6,10,95,000.00" in page.text
    assert "43,87,300.00" in page.text
    assert "1,82,05,000.00" in page.text
    assert "61,095,000.00" not in page.text
    assert "18,205,000.00" not in page.text


def test_excel_exports(client):
    login(client, "admin", "admin123")
    for path in ("/ar/aging?export=1", "/ap/aging?export=1", "/accounting/trial-balance?export=1", "/tax/tds?export=1", "/tax/vat?export=1", "/reports/project-pnl?export=1"):
        response = client.get(path)
        assert response.status_code == 200, path
        assert "spreadsheet" in response.headers.get("content-type", "")
        assert response.content[:2] == b"PK"


def test_vouchers_print(client):
    login(client, "admin", "admin123")
    receipt = client.get("/receipts/1/voucher")
    assert receipt.status_code == 200
    assert "MONEY RECEIPT" in receipt.text
    bill = client.get("/bills/1/voucher")
    assert bill.status_code == 200
    assert "VOUCHER" in bill.text


def test_logo_on_login_and_dashboard(client):
    login_page = client.get("/login")
    assert login_page.status_code == 200
    assert "/static/img/razz-cpl-logo.jpg" in login_page.text
    logo = client.get("/static/img/razz-cpl-logo.jpg")
    assert logo.status_code == 200
    assert logo.content[:3] == b"\xff\xd8\xff"
    login(client, "admin", "admin123")
    dash = client.get("/")
    assert dash.status_code == 200
    assert "/static/img/razz-cpl-logo.jpg" in dash.text
    assert "6,10,95,000.00" in dash.text


def test_language_toggle(client):
    login(client, "admin", "admin123")
    client.get("/lang/bn")
    page = client.get("/")
    assert "ড্যাশবোর্ড" in page.text or "প্রাপ্য" in page.text
    client.get("/lang/en")
