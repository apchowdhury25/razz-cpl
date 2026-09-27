# Razz CNPL Accounts — User Guide

**বাংলা সংস্করণ:** [README.bn.md](README.bn.md)

For a full step-by-step handbook (including database location and troubleshooting), see **[USER-GUIDE.md](USER-GUIDE.md)**.

Internal accounting system for **Razz CNPL**, Dhaka. Use it for day-to-day accounts receivable (money customers owe), accounts payable (money owed to vendors), project tracking, cash/bank, VAT/TDS, and management reports.

This is a server-rendered web app. Open it in a browser on the office PC or on the company VPS. There is no mobile app and no cloud login.

English is the default language. Use **EN · বাংলা** in the top bar to switch labels.

---

## 1. Open the application

On the office PC, after the system has been started:

1. Open a browser (Chrome or Edge).
2. Go to [http://127.0.0.1:8000](http://127.0.0.1:8000).
3. Sign in with the username and password given to you.

If the page does not load, the application is not running. Ask the administrator to start it (see [First-time setup](#12-first-time-setup-it-administrator)).

---

## 2. Sign in and roles

| Role | Typical user | What they can do |
|------|----------------|------------------|
| **ADMIN** | System owner / head of accounts | Everything, including users, tax rates, period lock, backup, and reversing posted documents |
| **MANAGER** | Finance manager | Review, approve, post, and all reports. Cannot change company settings or users |
| **ACCOUNTS_OFFICER** | Accounts staff | Create and edit drafts, receipts, bills, and payments. Cannot reverse a posted voucher or change configuration |
| **AUDITOR** | Internal auditor | View reports, ledgers, and the audit log. Cannot create or edit transactions |

### Demo logins (sample database only)

These exist only on a seeded demo database. **Change them before any real use.**

| Username | Password | Role |
|----------|----------|------|
| `admin` | `admin123` | ADMIN |
| `accounts` | `accounts123` | ACCOUNTS_OFFICER |
| `manager` | `manager123` | MANAGER |
| `auditor` | `auditor123` | AUDITOR |

Sign out with **Sign out** in the top right when you leave the desk.

---

## 3. What the numbers mean

Do not mix these up. The dashboard is built from posted transactions, not from typed totals.

| Term | Meaning |
|------|---------|
| **Receivable (AR)** | What customers still owe: posted demands minus allocated receipts minus credit notes |
| **Receipts** | Money already collected into cash or bank |
| **Payable (AP)** | What the company still owes vendors: posted bills minus allocated payments minus vendor credits |
| **Vendor payments** | Money already paid out of cash or bank |
| **TDS payable** | Tax withheld from vendors, not yet remitted |
| **Retention payable** | Amount held back from a contractor bill |
| **Input VAT** | VAT recorded on eligible vendor bills |
| **Cash + Bank** | Opening balance + posted receipts − posted payments ± transfers |

A booking or demand **increases revenue and receivable**. A money receipt **increases cash and reduces receivable**. A vendor bill **increases cost, input VAT, and liabilities**. A vendor payment **reduces cash and AP**.

Project P&L is **recognised revenue minus recognised cost**. It is not “receipts minus vendor bills”.

---

## 4. Dashboard

After login you land on the dashboard. It shows:

- Total receivable, overdue AR, and aging buckets
- Total payable, overdue AP, and aging buckets
- Cash, bank, and cash + bank
- TDS payable, input VAT, output VAT, retention
- Per-project revenue, cost, result, receivable, and payable
- Recent receipts, bills, payments, and journals

If a figure looks wrong, open the matching register (Demands, Receipts, Bills, Trial Balance) rather than editing the dashboard. There is nothing to type here.

---

## 5. Everyday work — receivables

Typical developer flow: **Customer → Unit → Booking → Demands → Money receipt → Allocate → Post → Print voucher**.

### 5.1 Customers / buyers

**Receivables → Customers / Buyers**

- Add a buyer (name, বাংলা name, NID, phone, address).
- Open a customer to see their ledger.
- Use **Statement** for a printable / Excel customer statement.

### 5.2 Units (developer projects)

**Projects → Units**

- Record unit number, floor, size (sft), base price, and sale price.
- Status: Unsold, Reserved, Booked, Sold, Cancelled.
- A unit becomes **Booked** automatically when you save a booking.

### 5.3 Bookings

**Receivables → Bookings → Add**

1. Choose date, customer, and unsold unit.
2. Enter the agreed price.
3. Save.

The system posts four installment **demands** (10% booking money, 15% down payment, 50% construction, 25% handover) that add up to the agreed price. Those demands are the receivable, not the receipts.

### 5.4 Demands / invoices

**Receivables → Demands / Invoices**

Use this for extra demands (or contractor billing) that did not come from a booking.

Lifecycle:

`Draft → Submit → Approve → Post`

Only a **posted** demand counts as AR. From the demand screen you can Submit, Approve, Post, or Cancel according to your role.

You cannot cancel a posted demand that already has allocated receipts. Reverse the receipts first (admin).

### 5.5 Money receipts

**Receivables → Money Receipts → Add**

1. Date, customer, amount, cash/bank account, method (Cash, Cheque, Bank Transfer, Mobile Banking, Other).
2. Reference (cheque / TT number).
3. Allocate the amount against outstanding invoices. You may split one receipt across several invoices.
4. Tick **Advance / allow unallocated remainder** only if money is received before it is applied to a demand.
5. Save (draft), then **Post**.

Rules the system will not bend:

- Amount must be greater than zero.
- You cannot allocate more than the receipt.
- You cannot allocate more than an invoice’s outstanding balance.
- Unallocated remainder requires the Advance option.

After posting, use **Print voucher** for an A5 money receipt (amount in words, English and Bangla).

### 5.6 AR aging and ledgers

- **AR Aging** — outstanding by due date, as of a chosen date. Buckets: Current, 1–30, 31–60, 61–90, 91–180, 181–365, over 365 days.
- **Customer Ledger** — debit = demand, credit = receipt / credit note, running balance.
- **Outstanding** / **Overdue** — shortcuts from the demands list.
- **Advances** — posted receipts with unallocated remainder.

---

## 6. Everyday work — payables

Typical flow: **Vendor → Bill (draft) → Submit → Approve → Post → Payment → Allocate → Post → Print voucher**.

### 6.1 Vendors

**Payables → Vendors**

Record name, type (contractor, material supplier, service provider, consultant), TIN/BIN, and default TDS %. Open a vendor for their ledger or statement.

### 6.2 Vendor bills

**Payables → Vendor Bills → Add**

Enter:

- Bill date and due date
- Vendor and project
- Vendor’s own bill number and Mushak-6.3 reference
- **Gross amount**
- VAT %, TDS %, Retention % (stored on the bill; later tax-master changes do not rewrite history)
- Cost account (construction, materials, professional fees, etc.)

The form shows a live preview. The **server recalculates** on save:

```
VAT        = Gross × VAT %
TDS        = Gross × TDS %
Retention  = Gross × Retention %
Net payable = Gross + VAT − TDS − Retention
```

Example: gross ৳ 25,00,000.00 at 15% VAT, 5% TDS, 5% retention → net payable ৳ 26,25,000.00.

Then **Submit → Approve → Post** (roles apply). Posted bills create a balanced journal:

- Debit project cost (gross) and input VAT
- Credit AP (net), TDS payable, and retention payable

On a posted bill you can:

- **Remit TDS** — pay the withheld tax from a bank account
- **Settle retention** — release retention to the vendor
- **Print** the debit voucher

### 6.3 Vendor payments

**Payables → Vendor Payments → Add**

1. Date, vendor, amount, cash/bank account, method, cheque/reference.
2. Allocate against outstanding bills (full, partial, or several bills).
3. Tick **Vendor Advance** only if you are paying more than current outstanding.
4. Save, then **Post**.

Posting reduces AP and cash/bank. Print the payment voucher when needed.

### 6.4 AP aging and ledgers

Same idea as AR: aging is by **due date**, as of a date you choose. Vendor ledger: credit = bill, debit = payment.

---

## 7. Projects

Seeded projects:

| Code | Name | Mode | Client |
|------|------|------|--------|
| MTT | Mermaid Twin Tower | Developer | — |
| M72 | Mermaid 72.72 Katha | Developer | — |
| WP | White Place | Developer | — |
| GV | Green View | Developer | — |
| SM | Saint Martin | Contractor | BDRCS |
| JR | Joldighi Reserve | Developer | — |

Open a project for revenue, cost, gross result, receivable, payable, cash collected, cash paid, and budget utilisation.

- **Developer** projects also show units (unsold / booked / sold) and sales value.
- **Contractor** projects also show contract value, billed, collected, and vendor cost.

**Project P&L** is under Reports. Cash collected and cash paid are shown separately. They are not the profit figure.

---

## 8. Cash and bank

**Cash & Bank → Cash & Bank** lists petty cash and bank accounts with opening and **current** balance.

Current balance = opening + posted receipts − posted payments ± transfers. Opening is not shown as the live total.

- **Transfers** — move money between cash/bank accounts (for example BRAC Bank → City Bank). No P&L effect.
- **Other receipts / payments** — office expenses, miscellaneous income. Choose the cash/bank account and the offset ledger account.
- **Cash Book** / **Bank Book** — date range, running balance, Excel and print.

---

## 9. Accounting and tax

### Journals and ledgers

- **Chart of Accounts** — asset, liability, equity, revenue, expense codes.
- **Journal Entries** — every posted AR/AP/cash document creates a journal. You can also enter a manual journal (debits must equal credits).
- **General Ledger** — one account, date range, running balance.
- **Trial Balance** — debit column must equal credit column. If it does not, stop and tell the administrator.

Posted journals cannot be silently edited. Cancel / reverse through the original document (admin). That writes a reversing journal and an audit line.

### Tax

**Tax → Tax Settings** (admin): VAT %, TDS categories, retention default, effective date, active/inactive.

Defaults in the sample company (configurable, **not legal advice**):

- Standard VAT 15%
- Construction / civil works TDS 5%
- Cement / iron / steel 2%
- Professional / advisory (non-individual) 7.5%, (individual) 15%
- Technical services (non-individual) 10%
- Office / warehouse rent 10%
- Default retention 5% (also overridable on the project and on each bill)

**VAT report** and **TDS report** are internal registers (vendor, bill, Mushak, amounts, remittance). They are not an official NBR return.

---

## 10. Reports, Excel, and print

**Reports** lists every register. Most screens accept:

- Date from / date to (or **As of** for aging)
- Project
- Customer or vendor where it applies

Click **Export Excel** for a real `.xlsx` file (company name, filters, timestamp, totals). Click **Print** or open a voucher and use the browser print dialog (A5-style CSS).

| Report | Where |
|--------|--------|
| AR / AP aging | Receivables / Payables menus |
| Customer / vendor ledger and statement | Ledgers, or from the customer/vendor page |
| Outstanding / overdue | Demands and bills lists |
| Project P&L, cost, cash flow | Reports and Projects |
| Cash book, bank book | Cash & Bank |
| General ledger, trial balance | Accounting |
| TDS payable, VAT / input VAT | Tax |
| Receipts / payments register | Export on those lists |
| Daily / monthly transactions | Reports |

Currency displays in Bangladeshi grouping with two decimals, for example `৳ 12,50,000.00` and `৳ 1,00,000.00` (not `100,000.00`). Dates display as **DD/MM/YYYY** (for example `09/03/2026` is 9 March 2026).

---

## 11. Administration (ADMIN)

Visible in the left menu only for administrators.

| Screen | Use |
|--------|-----|
| **Users** | Create users, set role, reset password, deactivate |
| **Roles** | Reminder of what each role may do |
| **Settings** | Company name, address, BIN/TIN, financial year dates, current period |
| **Accounting periods** | Lock a month so ordinary users cannot post into it. Admin can still post |
| **Document numbering** | Prefixes such as `MR-2026-0001`, `AP-2026-0001`. Do not reuse posted numbers |
| **Audit log** | Create, edit, approve, post, cancel, reverse, login, configuration. Cannot be deleted by normal users |
| **Backup** | Safe SQLite copy into the `backups/` folder; download from the same page |
| **Employees / payees** | Names for “received by” / payee lists |

Financial year on the sample company: **FY 2026-27** (1 July 2026 – 30 June 2027). Change it in Settings; it is not hard-coded forever.

---

## 12. First-time setup (IT / administrator)

Requirements: Python 3.10 or later, Windows PC or a small Linux VPS. SQLite is included. No cloud account.

```powershell
cd path\to\accounting-razz
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
python run.py --init --seed
```

Then browse to [http://127.0.0.1:8000](http://127.0.0.1:8000).

| Flag | Effect |
|------|--------|
| `--init` | Create tables if missing. Does **not** wipe data |
| `--seed` | Load sample projects, buyers, bills, and receipts. Safe to run again; it will not duplicate |
| `--host 0.0.0.0` | Listen on the LAN (use only behind a trusted office network) |
| `--port 8000` | Change the port if 8000 is taken |

Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python run.py --init --seed --host 127.0.0.1 --port 8000
```

`--seed` is for training and demonstration. For live books, run `--init` only, then create your own company data.

To confirm the sample figures after seeding:

```powershell
.\.venv\Scripts\python -m pytest tests -q
```

---

## 13. Database location and backup

| Item | Location |
|------|----------|
| Live SQLite file | `data/razz_accounts.db` |
| Backups | `backups/` |

**From the app (admin):** Administration → Backup → **Create backup now**. Download the file and copy it to a USB drive or the office file server.

**From the command line** (stop the app first, or use the built-in backup which uses SQLite’s online backup API):

```powershell
.\.venv\Scripts\python -m app.backup
```

Keep at least one copy off the same PC. Do not delete `data/razz_accounts.db` while the app is running.

The application does **not** destroy the database on startup.

---

## 14. Production notes

For a small office deployment:

1. Install Python, create the virtual environment, run `--init` (no seed on live data).
2. Set a strong secret: environment variable `RAZZ_SECRET_KEY`.
3. Change every demo password immediately.
4. Bind to localhost or an internal IP; do not publish this app on the public internet without HTTPS and a reverse proxy.
5. Lock completed accounting periods after month-end.
6. Take a backup before any Windows update or PC move.
7. Run behind a dedicated Windows user account if several people share the machine.

Optional environment variables:

| Variable | Purpose |
|----------|---------|
| `RAZZ_DATABASE_URL` | Override SQLite path |
| `RAZZ_DATA_DIR` | Data folder |
| `RAZZ_BACKUP_DIR` | Backup folder |
| `RAZZ_SECRET_KEY` | Session signing key |

---

## 15. Security

- Passwords are hashed. They are never stored in plain text.
- Every accounting screen requires login. Reports require login too.
- Posted amounts and document numbers cannot be edited in place.
- Negative payments and duplicate document numbers are rejected.
- Unbalanced journals are rejected.
- Tax percentages on a posted bill stay as they were on the posting date.
- Demo credentials on the login page are a warning, not a production password policy.

If you see a validation message (locked period, over-allocation, duplicate number), read it and correct the form. Ordinary users are not shown Python error traces.

---

## 16. Quick “what should I click?” map

| I want to… | Go to |
|------------|--------|
| Record a flat booking | Bookings → Add |
| Collect money from a buyer | Money Receipts → Add → allocate → Post → Print |
| Enter a contractor / supplier bill | Vendor Bills → Add → Submit/Approve/Post |
| Pay a vendor | Vendor Payments → Add → allocate → Post |
| See who is overdue | AR Aging or AP Aging, set **As of** today |
| Print a customer balance | Customer Ledger → choose customer → Print / Excel |
| Check the books still balance | Accounting → Trial Balance |
| Move money between banks | Cash & Bank → Transfers |
| Change VAT or TDS rates | Tax Settings (admin) |
| Close a month | Accounting periods → Lock (admin) |
| Save a copy of the books | Administration → Backup (admin) |

For a worked list of test cases and expected seed totals, see `tests/QA-TEST-SCENARIOS.md`.
