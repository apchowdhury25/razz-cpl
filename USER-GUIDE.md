# Razz CNPL Accounts — Step-by-step user guide

**বাংলা সংস্করণ:** [USER-GUIDE.bn.md](USER-GUIDE.bn.md)

This is the day-to-day handbook for accounts staff. Technical setup is also included at the end.

Open the app at [http://127.0.0.1:8000](http://127.0.0.1:8000).

**Money** is shown as Bangladeshi Taka: `৳ 1,00,000.00`  
**Dates** are shown and typed as **DD/MM/YYYY**. Example: `09/03/2026` means **9 March 2026**, not 3 September.

---

## 1. Sign in

| Username | Password | Role |
|----------|----------|------|
| `admin` | `admin123` | Full access (demo only — change this) |
| `accounts` | `accounts123` | Create drafts, post routine work |
| `manager` | `manager123` | Approve and post |
| `auditor` | `auditor123` | View only |

Use **EN · বাংলা** in the top bar for language. Use **☰** to hide the left menu when you need a wider screen. Drag the thin bar between the menu and the page to resize the menu.

---

## 2. How to enter a date

Every date field looks like this:

`[  DD/MM/YYYY  ][📅]`

1. Type `09/03/2026`, or
2. Click the calendar icon and pick a day.

The field always shows day/month/year with slashes and leading zeros (`01/08/2026`).

Invalid dates (for example `31/02/2026`) are rejected.

---

## 3. Daily work, in order

### A. Developer sale (flat / plot)

1. **Customers / Buyers → Add** — name, phone, NID, address. Save.
2. **Units → Add** — project, unit number, size, prices, status Unsold.
3. **Bookings → Add** — date, buyer, unit, agreed price. Save.  
   The system posts four demands (10% / 15% / 50% / 25%) that add up to the agreed price. That is the receivable, not the cash collected.
4. **Money Receipts → Add** — date, buyer, amount, bank/cash, allocate to outstanding demands. Save, then **Post**. Print the voucher.

### B. Extra demand / invoice

**Demands / Invoices → Add** — date, due date, customer, amount. Save as draft, then **Post**.

### C. Pay a contractor or supplier

1. **Vendors → Add** if they are new (set default TDS %).
2. **Vendor Bills → Add** — bill date, due date, vendor, project, gross amount, VAT %, TDS %, retention %, cost account, Mushak reference.  
   Net payable = Gross + VAT − TDS − Retention. Save, **Submit / Approve / Post**.
3. **Vendor Payments → Add** — amount, bank, allocate to the bill. Save, **Post**. Print the voucher.

### D. Cash movement

**Cash & Bank → Transfers** — date, from account, to account, amount. Posts immediately.

**Other receipts / payments** — office expense or miscellaneous income against a ledger account.

### E. Manual journal

**Accounting → Journal Entries → Add** — date, description, debit and credit lines that must balance. Tick post immediately.

---

## 4. What the dashboard numbers mean

| Figure | Meaning |
|--------|---------|
| Total receivable | Posted demands minus allocated receipts |
| Receipts / collected | Cash already in |
| Total payable | Posted vendor bills (net) minus allocated payments |
| Cash + Bank | Opening + receipts − payments ± transfers |
| AR/AP aging | Outstanding split by **due date**, as of a chosen date |

Do not type totals on the dashboard. If a figure looks wrong, open the matching register.

---

## 5. Reports and Excel

Open **Reports** or the register itself. Set **From / To** or **As of** using DD/MM/YYYY. Click **Export Excel** for a real `.xlsx` file. Click **Print** on vouchers.

Aging, ledgers, trial balance, VAT, TDS, and project P&L all export.

---

## 6. Month-end (administrator)

1. Check **Trial Balance** — debit must equal credit.
2. **Administration → Accounting periods → Lock** the finished month so ordinary users cannot post into it.
3. **Administration → Backup → Create backup now**. Copy the file off the PC.

---

## 7. Database

| Item | Location |
|------|----------|
| Live SQLite file | `data/razz_accounts.db` next to the project |
| WAL helpers (if present) | `data/razz_accounts.db-wal`, `.db-shm` |
| Application backups | `backups/razz_accounts_YYYYMMDD_HHMMSS.db` |
| Demo seed | Loaded with `python run.py --init --seed` |

SQLite stores dates as real date values (ISO internally), not as `09/03/2026` text. The slash format is display and typing only.

Do **not** delete `data/razz_accounts.db` while the app is running. The app does not wipe the database on start.

### Useful SQL (read-only)

```powershell
.\.venv\Scripts\python -c "import sqlite3; c=sqlite3.connect('data/razz_accounts.db'); print(c.execute('select invoice_no, invoice_date from customer_invoices limit 5').fetchall())"
```

---

## 8. How to start and stop the app

```powershell
cd C:\Users\anwar\.grok\worktrees\accounting-razz
.\.venv\Scripts\activate
python run.py --init --seed
```

Then browse to http://127.0.0.1:8000

| Flag | Meaning |
|------|---------|
| `--init` | Create tables if missing |
| `--seed` | Load sample company data (safe to repeat; it will not duplicate) |
| `--host 127.0.0.1 --port 8000` | Bind address |

Stop the server with Ctrl+C in that window.

Command-line backup:

```powershell
.\.venv\Scripts\python -m app.backup
```

---

## 9. Troubleshooting

| Problem | What to try |
|---------|-------------|
| Chrome shows a clipped dashboard or old date boxes | Press **Ctrl+F5**. CSS/JS is versioned; a hard refresh loads the new files. |
| Page will not open | Confirm the server window is running. Try http://127.0.0.1:8000/login |
| “Port 8000 in use” | Close the other `python run.py` window, or use `--port 8001` |
| Login fails | Check Caps Lock. Demo users are listed on the login page. |
| “Use DD/MM/YYYY” | Type day/month/year, e.g. `09/03/2026`. Do not type US month/day. |
| “Accounting period is locked” | An admin must unlock **Administration → Periods**, or post as admin. |
| Unbalanced journal | Debits must equal credits. The server will refuse the save. |
| Cannot allocate a receipt | Amount cannot exceed the receipt or the invoice outstanding. Tick Advance for leftover cash. |
| Dashboard totals look wrong | They are calculated from posted documents. Check Demands, Receipts, Bills, Payments. |
| Excel will not download | Sign in first. Use **Export Excel** on that report, not the browser’s File menu. |
| Database locked / “database is locked” | Stop extra copies of the app. Only one writer should use the SQLite file. |
| Need a clean demo again | Stop the app, move `data/razz_accounts.db` aside, then `python run.py --init --seed` |
| Git / backup | Copy `data/razz_accounts.db` to USB. Git does not store the live database. |

---

## 10. Security notes

- Change every demo password before real books.
- Do not publish this app on the public internet without HTTPS.
- Posted vouchers cannot be silently edited; reverse them as an administrator.
- The GitHub token and demo passwords must never be committed into the project.

For a shorter overview see [README.md](README.md).
