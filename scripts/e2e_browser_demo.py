"""Visible Chrome demo: create 10 records on every major entry screen."""

from __future__ import annotations

import re
import time
from datetime import datetime

from playwright.sync_api import Page, sync_playwright

BASE = "http://127.0.0.1:8000"
STAMP = datetime.now().strftime("%H%M%S")
N = 10


def fill_date(page: Page, name: str, value: str) -> None:
    text = page.locator(f'input.date-input[name="{name}"]')
    if text.count():
        text.first.fill(value)
        text.first.blur()
        return
    native = page.locator(f'input[name="{name}"]')
    if native.count():
        native.first.fill(value)


def submit(page: Page) -> None:
    btn = page.locator("form button.btn:not(.danger):not(.ghost)").first
    btn.click()
    page.wait_for_load_state("networkidle")


def login(page: Page) -> None:
    page.goto(f"{BASE}/login", wait_until="networkidle")
    page.fill('input[name="username"]', "admin")
    page.fill('input[name="password"]', "admin123")
    page.click('button[type="submit"]')
    page.wait_for_url(re.compile(r"http://127\.0\.0\.1:8000/?$"), timeout=20000)


def first_select_value(page: Page, name: str) -> str:
    return page.locator(f'select[name="{name}"] option[value]:not([value=""])').first.get_attribute("value") or ""


def customers(page: Page) -> None:
    for i in range(1, N + 1):
        page.goto(f"{BASE}/customers/new", wait_until="networkidle")
        page.fill('input[name="name"]', f"Demo Buyer {STAMP}-{i:02d}")
        page.fill('input[name="phone"]', f"01711{STAMP[-4:]}{i:02d}"[:11])
        page.fill('textarea[name="address"]', "Dhaka")
        submit(page)


def vendors(page: Page) -> None:
    for i in range(1, N + 1):
        page.goto(f"{BASE}/vendors/new", wait_until="networkidle")
        page.fill('input[name="name"]', f"Demo Vendor {STAMP}-{i:02d}")
        page.select_option('select[name="vendor_type"]', "MATERIAL_SUPPLIER")
        page.fill('input[name="default_tds_percent"]', "2")
        submit(page)


def projects(page: Page) -> None:
    for i in range(1, N + 1):
        page.goto(f"{BASE}/projects/new", wait_until="networkidle")
        page.fill('input[name="code"]', f"D{STAMP[-3:]}{i:02d}"[:8].upper())
        page.fill('input[name="name"]', f"Demo Project {STAMP}-{i:02d}")
        page.select_option('select[name="mode"]', "DEVELOPER")
        fill_date(page, "start_date", f"{i:02d}/07/2026")
        page.fill('input[name="budget"]', "1000000")
        page.fill('input[name="retention_percent"]', "5")
        submit(page)


def units(page: Page) -> list[str]:
    page.goto(f"{BASE}/units/new", wait_until="networkidle")
    project_id = first_select_value(page, "project_id")
    created = []
    for i in range(1, N + 1):
        page.goto(f"{BASE}/units/new", wait_until="networkidle")
        page.select_option('select[name="project_id"]', project_id)
        unum = f"DM-{STAMP}-{i:02d}"
        page.fill('input[name="unit_number"]', unum)
        page.fill('input[name="floor"]', str(i))
        page.fill('input[name="size_sft"]', "1000")
        page.fill('input[name="base_price"]', "2500000")
        page.fill('input[name="sale_price"]', "2500000")
        submit(page)
        created.append(unum)
    return created


def bookings(page: Page) -> None:
    for i in range(1, N + 1):
        page.goto(f"{BASE}/bookings/new", wait_until="networkidle")
        page.select_option('select[name="customer_id"]', index=0)
        # last unsold unit options
        opts = page.locator('select[name="unit_id"] option[value]:not([value=""])')
        count = opts.count()
        page.select_option('select[name="unit_id"]', index=max(0, count - 1))
        fill_date(page, "booking_date", f"{i:02d}/09/2026")
        page.fill('input[name="agreed_price"]', "2500000")
        submit(page)


def invoices(page: Page) -> None:
    for i in range(1, N + 1):
        page.goto(f"{BASE}/ar/invoices/new", wait_until="networkidle")
        fill_date(page, "invoice_date", f"{i:02d}/09/2026")
        fill_date(page, "due_date", f"{i:02d}/10/2026")
        page.select_option('select[name="customer_id"]', index=0)
        page.fill('input[name="amount"]', "5000")
        page.fill('textarea[name="description"]', f"Demo demand {STAMP}-{i:02d}")
        submit(page)
        post = page.locator('form[action*="/post"] button')
        if post.count():
            post.first.click()
            page.wait_for_load_state("networkidle")


def receipts(page: Page) -> None:
    for i in range(1, N + 1):
        page.goto(f"{BASE}/receipts/new", wait_until="networkidle")
        fill_date(page, "receipt_date", f"{i:02d}/09/2026")
        page.select_option('select[name="customer_id"]', index=0)
        page.fill('input[name="amount"]', "1000")
        page.check('input[name="is_advance"]')
        page.fill('textarea[name="notes"]', f"Demo receipt {STAMP}-{i:02d}")
        submit(page)
        post = page.locator('form[action*="/post"] button')
        if post.count():
            post.first.click()
            page.wait_for_load_state("networkidle")


def bills(page: Page) -> None:
    for i in range(1, N + 1):
        page.goto(f"{BASE}/bills/new", wait_until="networkidle")
        fill_date(page, "bill_date", f"{i:02d}/09/2026")
        fill_date(page, "due_date", f"{i:02d}/10/2026")
        page.select_option('select[name="vendor_id"]', index=0)
        page.fill('input[name="gross_amount"]', "10000")
        page.fill('input[name="vat_percent"]', "15")
        page.fill('input[name="tds_percent"]', "2")
        page.fill('input[name="retention_percent"]', "0")
        page.fill('input[name="vendor_bill_ref"]', f"DEMO/{STAMP}/{i:02d}")
        page.fill('textarea[name="description"]', f"Demo bill {STAMP}-{i:02d}")
        submit(page)
        post = page.locator('form[action*="/post"] button')
        if post.count():
            post.first.click()
            page.wait_for_load_state("networkidle")


def payments(page: Page) -> None:
    for i in range(1, N + 1):
        page.goto(f"{BASE}/payments/new", wait_until="networkidle")
        fill_date(page, "payment_date", f"{i:02d}/09/2026")
        page.select_option('select[name="vendor_id"]', index=0)
        page.fill('input[name="amount"]', "500")
        page.check('input[name="is_advance"]')
        page.fill('textarea[name="notes"]', f"Demo payment {STAMP}-{i:02d}")
        submit(page)
        post = page.locator('form[action*="/post"] button')
        if post.count():
            post.first.click()
            page.wait_for_load_state("networkidle")


def journals(page: Page) -> None:
    for i in range(1, N + 1):
        page.goto(f"{BASE}/accounting/journals/new", wait_until="networkidle")
        fill_date(page, "entry_date", f"{i:02d}/09/2026")
        page.fill('input[name="description"]', f"Demo journal {STAMP}-{i:02d}")
        acc0 = page.locator('select[name="account_id_0"] option[value]:not([value=""])').nth(1).get_attribute("value")
        acc1 = page.locator('select[name="account_id_1"] option[value]:not([value=""])').nth(2).get_attribute("value")
        page.select_option('select[name="account_id_0"]', acc0)
        page.fill('input[name="debit_0"]', "25")
        page.select_option('select[name="account_id_1"]', acc1)
        page.fill('input[name="credit_1"]', "25")
        page.check('input[name="post_now"]')
        submit(page)


def transfers(page: Page) -> None:
    page.goto(f"{BASE}/cash/transfers", wait_until="networkidle")
    from_id = first_select_value(page, "from_account_id")
    to_opts = page.locator('select[name="to_account_id"] option[value]:not([value=""])')
    to_id = to_opts.nth(min(1, to_opts.count() - 1)).get_attribute("value")
    for i in range(1, N + 1):
        page.goto(f"{BASE}/cash/transfers", wait_until="networkidle")
        fill_date(page, "transfer_date", f"{i:02d}/09/2026")
        src, dst = (from_id, to_id) if i % 2 else (to_id, from_id)
        page.select_option('select[name="from_account_id"]', src)
        page.select_option('select[name="to_account_id"]', dst)
        page.fill('input[name="amount"]', "1")
        page.fill('textarea[name="notes"]', f"Demo transfer {STAMP}-{i:02d}")
        page.locator('form[action="/cash/transfers/new"] button.btn').click()
        page.wait_for_load_state("networkidle")


def other_cash(page: Page) -> None:
    for i in range(1, N + 1):
        page.goto(f"{BASE}/cash/other", wait_until="networkidle")
        fill_date(page, "txn_date", f"{i:02d}/09/2026")
        page.select_option('select[name="direction"]', "OUT" if i % 2 else "IN")
        page.fill('input[name="amount"]', "10")
        page.fill('input[name="payee_name"]', f"Demo payee {i:02d}")
        page.fill('textarea[name="description"]', f"Demo other {STAMP}-{i:02d}")
        page.locator('form[action="/cash/other/new"] button.btn').click()
        page.wait_for_load_state("networkidle")


def coa(page: Page) -> None:
    for i in range(1, N + 1):
        page.goto(f"{BASE}/accounting/coa", wait_until="networkidle")
        page.fill('input[name="code"]', f"9{STAMP[-3:]}{i:02d}"[:8])
        page.fill('input[name="name"]', f"Demo account {STAMP}-{i:02d}")
        page.select_option('select[name="account_type"]', "EXPENSE")
        page.locator('form[action="/accounting/coa/new"] button.btn').click()
        page.wait_for_load_state("networkidle")


def employees(page: Page) -> None:
    for i in range(1, N + 1):
        page.goto(f"{BASE}/admin/employees", wait_until="networkidle")
        page.fill('input[name="code"]', f"EM-{STAMP}-{i:02d}")
        page.fill('input[name="name"]', f"Demo Employee {STAMP}-{i:02d}")
        page.fill('input[name="designation"]', "Accounts")
        page.locator('form[action="/admin/employees/new"] button.btn').click()
        page.wait_for_load_state("networkidle")


def tax_rows(page: Page) -> None:
    for i in range(1, N + 1):
        page.goto(f"{BASE}/tax/settings", wait_until="networkidle")
        page.fill('input[name="code"]', f"T{STAMP[-3:]}{i:02d}")
        page.fill('input[name="name"]', f"Demo tax {STAMP}-{i:02d}")
        page.select_option('select[name="tax_type"]', "TDS")
        page.fill('input[name="percent"]', "3")
        fill_date(page, "effective_date", "01/07/2026")
        page.locator('form[action="/tax/settings/new"] button.btn').click()
        page.wait_for_load_state("networkidle")


REVIEW = [
    "/",
    "/customers",
    "/vendors",
    "/projects",
    "/units",
    "/bookings",
    "/ar/invoices",
    "/receipts",
    "/bills",
    "/payments",
    "/ar/aging",
    "/ap/aging",
    "/ar/ledger",
    "/ap/ledger",
    "/cash/accounts",
    "/cash/book",
    "/cash/bank-book",
    "/accounting/journals",
    "/accounting/gl",
    "/accounting/trial-balance",
    "/reports",
    "/reports/project-pnl",
    "/tax/vat",
    "/tax/tds",
    "/admin/audit",
]


def main() -> None:
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(
                headless=False,
                channel="chrome",
                slow_mo=180,
                args=["--start-maximized"],
            )
        except Exception:
            browser = p.chromium.launch(headless=False, slow_mo=180, args=["--start-maximized"])
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.set_default_timeout(45000)
        login(page)
        print(f"DEMO_START stamp={STAMP}", flush=True)
        customers(page)
        print("customers 10", flush=True)
        vendors(page)
        print("vendors 10", flush=True)
        projects(page)
        print("projects 10", flush=True)
        units(page)
        print("units 10", flush=True)
        bookings(page)
        print("bookings 10", flush=True)
        invoices(page)
        print("invoices 10", flush=True)
        receipts(page)
        print("receipts 10", flush=True)
        bills(page)
        print("bills 10", flush=True)
        payments(page)
        print("payments 10", flush=True)
        journals(page)
        print("journals 10", flush=True)
        transfers(page)
        print("transfers 10", flush=True)
        other_cash(page)
        print("other cash 10", flush=True)
        coa(page)
        print("coa 10", flush=True)
        employees(page)
        print("employees 10", flush=True)
        tax_rows(page)
        print("tax 10", flush=True)
        for path in REVIEW:
            page.goto(f"{BASE}{path}", wait_until="networkidle")
            time.sleep(0.6)
        page.goto(f"{BASE}/", wait_until="networkidle")
        print("DEMO_DONE", flush=True)
        time.sleep(600)
        browser.close()


if __name__ == "__main__":
    main()
