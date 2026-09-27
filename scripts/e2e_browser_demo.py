"""Visible Chrome demo: 20 consistent records on every major entry screen."""

from __future__ import annotations

import re
import time
from datetime import datetime

from playwright.sync_api import Page, sync_playwright

BASE = "http://127.0.0.1:8000"
STAMP = datetime.now().strftime("%H%M%S")
N = 20
PREFIX = f"E20-{STAMP}"

VENDOR_TYPES = [
    ("CONTRACTOR", "5", "5"),
    ("MATERIAL_SUPPLIER", "2", "0"),
    ("SERVICE_PROVIDER", "7.5", "0"),
    ("CONSULTANT", "10", "0"),
]


def log(msg: str) -> None:
    print(msg, flush=True)


def fill_date(page: Page, name: str, value: str) -> None:
    text = page.locator(f'input.date-input[name="{name}"]')
    if text.count():
        text.first.fill(value)
        text.first.dispatch_event("change")
        return
    native = page.locator(f'input[name="{name}"]')
    if native.count():
        native.first.fill(value)


def submit(page: Page) -> None:
    page.locator("form button.btn:not(.danger):not(.ghost)").first.click()
    page.wait_for_load_state("networkidle")


def post_if_shown(page: Page) -> None:
    post = page.locator('form[action*="/post"] button')
    if post.count():
        post.first.click()
        page.wait_for_load_state("networkidle")


def login(page: Page) -> None:
    page.goto(f"{BASE}/login", wait_until="networkidle")
    page.fill('input[name="username"]', "admin")
    page.fill('input[name="password"]', "admin123")
    page.click('button[type="submit"]')
    page.wait_for_url(re.compile(r"http://127\.0\.0\.1:8000/?$"), timeout=20000)


def first_select_value(page: Page, name: str) -> str:
    return page.locator(f'select[name="{name}"] option[value]:not([value=""])').first.get_attribute("value") or ""


def select_label(page: Page, name: str, fragment: str) -> None:
    options = page.locator(f'select[name="{name}"] option')
    for i in range(options.count()):
        text = options.nth(i).inner_text()
        value = options.nth(i).get_attribute("value") or ""
        if fragment in text and value:
            page.select_option(f'select[name="{name}"]', value)
            return
    raise RuntimeError(f'No {name} option containing "{fragment}"')


def day(i: int) -> str:
    return f"{i:02d}/09/2026"


def customers(page: Page) -> None:
    for i in range(1, N + 1):
        page.goto(f"{BASE}/customers/new", wait_until="networkidle")
        page.fill('input[name="name"]', f"{PREFIX} Buyer {i:02d}")
        page.fill('input[name="name_bn"]', f"ক্রেতা {i:02d}")
        page.fill('input[name="phone"]', f"0171{STAMP[-4:]}{i:02d}"[:11])
        page.fill('input[name="nid"]', f"1980{STAMP}{i:02d}"[:13])
        page.fill('textarea[name="address"]', f"House {i}, Dhanmondi, Dhaka")
        submit(page)
        log(f"  customer {i}/{N}")


def vendors(page: Page) -> None:
    for i in range(1, N + 1):
        vtype, tds, _ret = VENDOR_TYPES[(i - 1) % 4]
        page.goto(f"{BASE}/vendors/new", wait_until="networkidle")
        page.fill('input[name="name"]', f"{PREFIX} Vendor {i:02d}")
        page.select_option('select[name="vendor_type"]', vtype)
        page.fill('input[name="default_tds_percent"]', tds)
        page.fill('input[name="tin"]', f"TIN-{STAMP}-{i:02d}")
        page.fill('textarea[name="address"]', f"Plot {i}, Tejgaon, Dhaka")
        submit(page)
        log(f"  vendor {i}/{N} {vtype} TDS {tds}%")


def projects(page: Page) -> str:
    home_code = f"H{STAMP[-4:]}"
    for i in range(1, N + 1):
        page.goto(f"{BASE}/projects/new", wait_until="networkidle")
        code = home_code if i == 1 else f"P{STAMP[-3:]}{i:02d}"[:8]
        page.fill('input[name="code"]', code)
        page.fill('input[name="name"]', f"{PREFIX} Project {i:02d}")
        page.fill('input[name="name_bn"]', f"প্রকল্প {i:02d}")
        page.select_option('select[name="mode"]', "DEVELOPER" if i != 20 else "CONTRACTOR")
        if i == 20:
            page.fill('input[name="client_name"]', "BDRCS Demo")
            page.fill('input[name="contract_value"]', "5000000")
        fill_date(page, "start_date", "01/07/2026")
        page.fill('input[name="budget"]', str(5_000_000 + i * 100_000))
        page.fill('input[name="retention_percent"]', "5")
        submit(page)
        log(f"  project {i}/{N} {code}")
    page.goto(f"{BASE}/units/new", wait_until="networkidle")
    try:
        select_label(page, "project_id", rf"{PREFIX} Project 01")
    except Exception:
        select_label(page, "project_id", home_code)
    return page.locator('select[name="project_id"]').input_value()


def units(page: Page, project_id: str) -> list[str]:
    created = []
    for i in range(1, N + 1):
        page.goto(f"{BASE}/units/new", wait_until="networkidle")
        page.select_option('select[name="project_id"]', project_id)
        unum = f"{PREFIX}-U{i:02d}"
        page.fill('input[name="unit_number"]', unum)
        page.fill('input[name="floor"]', str((i % 10) + 1))
        page.fill('input[name="size_sft"]', str(1000 + i * 10))
        price = str(2_500_000 + i * 10_000)
        page.fill('input[name="base_price"]', price)
        page.fill('input[name="sale_price"]', price)
        submit(page)
        created.append(unum)
        log(f"  unit {i}/{N} {unum} ৳{price}")
    return created


def bookings(page: Page, unit_numbers: list[str]) -> None:
    for i, unum in enumerate(unit_numbers, start=1):
        page.goto(f"{BASE}/bookings/new", wait_until="networkidle")
        select_label(page, "customer_id", rf"{PREFIX} Buyer {i:02d}")
        select_label(page, "unit_id", unum)
        fill_date(page, "booking_date", day(i))
        page.fill('input[name="agreed_price"]', str(2_500_000 + i * 10_000))
        page.fill('textarea[name="notes"]', f"Booking {PREFIX} buyer {i:02d} -> {unum}")
        submit(page)
        log(f"  booking {i}/{N} buyer {i:02d} / {unum}")


def invoices(page: Page, project_id: str) -> None:
    for i in range(1, N + 1):
        page.goto(f"{BASE}/ar/invoices/new", wait_until="networkidle")
        fill_date(page, "invoice_date", day(i))
        fill_date(page, "due_date", f"{i:02d}/10/2026")
        select_label(page, "customer_id", rf"{PREFIX} Buyer {i:02d}")
        page.select_option('select[name="project_id"]', project_id)
        page.fill('input[name="amount"]', str(5_000 * i))
        page.fill('textarea[name="description"]', f"{PREFIX} extra demand {i:02d}")
        submit(page)
        post_if_shown(page)
        log(f"  invoice {i}/{N}")


def receipts(page: Page) -> None:
    for i in range(1, N + 1):
        page.goto(f"{BASE}/receipts/new", wait_until="networkidle")
        fill_date(page, "receipt_date", day(min(i + 1, 28)))
        select_label(page, "customer_id", rf"{PREFIX} Buyer {i:02d}")
        page.fill('input[name="amount"]', str(1_000 * i))
        page.check('input[name="is_advance"]')
        page.fill('textarea[name="notes"]', f"{PREFIX} receipt {i:02d} from buyer {i:02d}")
        submit(page)
        post_if_shown(page)
        log(f"  receipt {i}/{N}")


def bills(page: Page, project_id: str) -> None:
    for i in range(1, N + 1):
        _vtype, tds, ret = VENDOR_TYPES[(i - 1) % 4]
        page.goto(f"{BASE}/bills/new", wait_until="networkidle")
        fill_date(page, "bill_date", day(i))
        fill_date(page, "due_date", f"{i:02d}/10/2026")
        select_label(page, "vendor_id", rf"{PREFIX} Vendor {i:02d}")
        page.select_option('select[name="project_id"]', project_id)
        page.fill('input[name="gross_amount"]', str(10_000 * i))
        page.fill('input[name="vat_percent"]', "15")
        page.fill('input[name="tds_percent"]', tds)
        page.fill('input[name="retention_percent"]', ret)
        page.fill('input[name="vendor_bill_ref"]', f"{PREFIX}/BILL/{i:02d}")
        page.fill('input[name="mushak_ref"]', f"Mushak-6.3/{PREFIX}/{i:02d}")
        page.fill('textarea[name="description"]', f"{PREFIX} bill {i:02d} {_vtype}")
        submit(page)
        post_if_shown(page)
        log(f"  bill {i}/{N} {_vtype}")


def payments(page: Page) -> None:
    for i in range(1, N + 1):
        page.goto(f"{BASE}/payments/new", wait_until="networkidle")
        fill_date(page, "payment_date", day(min(i + 2, 28)))
        select_label(page, "vendor_id", rf"{PREFIX} Vendor {i:02d}")
        page.fill('input[name="amount"]', str(500 * i))
        page.check('input[name="is_advance"]')
        page.fill('textarea[name="notes"]', f"{PREFIX} payment {i:02d} to vendor {i:02d}")
        submit(page)
        post_if_shown(page)
        log(f"  payment {i}/{N}")


def journals(page: Page) -> None:
    for i in range(1, N + 1):
        page.goto(f"{BASE}/accounting/journals/new", wait_until="networkidle")
        fill_date(page, "entry_date", day(i))
        page.fill('input[name="description"]', f"{PREFIX} journal {i:02d} petty to bank")
        acc0 = page.locator('select[name="account_id_0"] option[value]:not([value=""])').nth(1).get_attribute("value")
        acc1 = page.locator('select[name="account_id_1"] option[value]:not([value=""])').nth(2).get_attribute("value")
        page.select_option('select[name="account_id_0"]', acc0)
        page.fill('input[name="debit_0"]', "50")
        page.select_option('select[name="account_id_1"]', acc1)
        page.fill('input[name="credit_1"]', "50")
        page.check('input[name="post_now"]')
        submit(page)
        log(f"  journal {i}/{N}")


def transfers(page: Page) -> None:
    page.goto(f"{BASE}/cash/transfers", wait_until="networkidle")
    from_id = first_select_value(page, "from_account_id")
    to_opts = page.locator('select[name="to_account_id"] option[value]:not([value=""])')
    to_id = to_opts.nth(min(1, to_opts.count() - 1)).get_attribute("value")
    for i in range(1, N + 1):
        page.goto(f"{BASE}/cash/transfers", wait_until="networkidle")
        fill_date(page, "transfer_date", day(i))
        src, dst = (from_id, to_id) if i % 2 else (to_id, from_id)
        page.select_option('select[name="from_account_id"]', src)
        page.select_option('select[name="to_account_id"]', dst)
        page.fill('input[name="amount"]', "2")
        page.fill('textarea[name="notes"]', f"{PREFIX} transfer {i:02d}")
        page.locator('form[action="/cash/transfers/new"] button.btn').click()
        page.wait_for_load_state("networkidle")
        log(f"  transfer {i}/{N}")


def other_cash(page: Page) -> None:
    for i in range(1, N + 1):
        page.goto(f"{BASE}/cash/other", wait_until="networkidle")
        fill_date(page, "txn_date", day(i))
        page.select_option('select[name="direction"]', "OUT" if i % 2 else "IN")
        page.fill('input[name="amount"]', "20")
        page.fill('input[name="payee_name"]', f"{PREFIX} payee {i:02d}")
        page.fill('textarea[name="description"]', f"{PREFIX} other {'expense' if i % 2 else 'income'} {i:02d}")
        page.locator('form[action="/cash/other/new"] button.btn').click()
        page.wait_for_load_state("networkidle")
        log(f"  other cash {i}/{N}")


def coa(page: Page) -> None:
    for i in range(1, N + 1):
        page.goto(f"{BASE}/accounting/coa", wait_until="networkidle")
        page.fill('input[name="code"]', f"8{STAMP[-3:]}{i:02d}"[:8])
        page.fill('input[name="name"]', f"{PREFIX} expense {i:02d}")
        page.select_option('select[name="account_type"]', "EXPENSE")
        page.locator('form[action="/accounting/coa/new"] button.btn').click()
        page.wait_for_load_state("networkidle")
        log(f"  coa {i}/{N}")


def employees(page: Page) -> None:
    for i in range(1, N + 1):
        page.goto(f"{BASE}/admin/employees", wait_until="networkidle")
        page.fill('input[name="code"]', f"EM-{STAMP}-{i:02d}")
        page.fill('input[name="name"]', f"{PREFIX} Employee {i:02d}")
        page.fill('input[name="designation"]', "Accounts Officer" if i % 2 else "Site Engineer")
        page.locator('form[action="/admin/employees/new"] button.btn').click()
        page.wait_for_load_state("networkidle")
        log(f"  employee {i}/{N}")


def tax_rows(page: Page) -> None:
    for i in range(1, N + 1):
        page.goto(f"{BASE}/tax/settings", wait_until="networkidle")
        page.fill('input[name="code"]', f"X{STAMP[-3:]}{i:02d}")
        page.fill('input[name="name"]', f"{PREFIX} TDS {i:02d}")
        page.select_option('select[name="tax_type"]', "TDS")
        page.fill('input[name="percent"]', str(1 + (i % 10)))
        fill_date(page, "effective_date", "01/07/2026")
        page.locator('form[action="/tax/settings/new"] button.btn').click()
        page.wait_for_load_state("networkidle")
        log(f"  tax {i}/{N}")


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
    "/cash/accounts",
    "/accounting/journals",
    "/accounting/trial-balance",
    "/reports/project-pnl",
    "/tax/tds",
    "/admin/audit",
]


def main() -> None:
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(
                headless=False,
                channel="chrome",
                slow_mo=140,
                args=["--start-maximized"],
            )
        except Exception:
            browser = p.chromium.launch(headless=False, slow_mo=140, args=["--start-maximized"])
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.set_default_timeout(60000)
        login(page)
        log(f"DEMO20_START prefix={PREFIX}")
        customers(page)
        vendors(page)
        project_id = projects(page)
        unit_numbers = units(page, project_id)
        bookings(page, unit_numbers)
        invoices(page, project_id)
        receipts(page)
        bills(page, project_id)
        payments(page)
        journals(page)
        transfers(page)
        other_cash(page)
        coa(page)
        employees(page)
        tax_rows(page)
        for path in REVIEW:
            page.goto(f"{BASE}{path}", wait_until="networkidle")
            time.sleep(0.8)
        page.goto(f"{BASE}/", wait_until="networkidle")
        log("DEMO20_DONE")
        time.sleep(600)
        browser.close()


if __name__ == "__main__":
    main()
