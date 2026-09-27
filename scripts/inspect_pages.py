from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parent.parent / "data" / "qa-shots"
OUT.mkdir(parents=True, exist_ok=True)

PAGES = [
    ("login", "http://127.0.0.1:8000/login"),
    ("dashboard", "http://127.0.0.1:8000/"),
    ("projects", "http://127.0.0.1:8000/projects"),
    ("invoices", "http://127.0.0.1:8000/ar/invoices"),
    ("receipts", "http://127.0.0.1:8000/receipts"),
    ("bills", "http://127.0.0.1:8000/bills"),
    ("payments", "http://127.0.0.1:8000/payments"),
    ("aging", "http://127.0.0.1:8000/ar/aging"),
    ("tb", "http://127.0.0.1:8000/accounting/trial-balance"),
    ("coa", "http://127.0.0.1:8000/accounting/coa"),
]

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.on("pageerror", lambda exc: print("JSERROR", exc))
    page.on("console", lambda msg: print("CONSOLE", msg.type, msg.text) if msg.type == "error" else None)
    page.goto("http://127.0.0.1:8000/login", wait_until="networkidle")
    page.evaluate("() => { localStorage.clear(); }")
    page.screenshot(path=str(OUT / "login.png"), full_page=True)
    page.fill("input[name=username]", "admin")
    page.fill("input[name=password]", "admin123")
    page.click("button[type=submit]")
    page.wait_for_url("http://127.0.0.1:8000/", timeout=15000)
    for name, url in PAGES[1:]:
        resp = page.goto(url, wait_until="networkidle")
        print(name, resp.status if resp else "none", "title=", page.title())
        page.screenshot(path=str(OUT / f"{name}.png"), full_page=False)
        layout = page.evaluate(
            """() => {
              const s = document.querySelector('.sidebar');
              const m = document.querySelector('.main');
              const l = document.querySelector('.layout');
              const r = (el) => el ? el.getBoundingClientRect() : null;
              return {
                sidebar: r(s),
                main: r(m),
                layout: r(l),
                innerWidth: window.innerWidth,
                overflow: document.body.scrollWidth
              };
            }"""
        )
        print(name, "layout", layout)
    browser.close()
print("DONE")
