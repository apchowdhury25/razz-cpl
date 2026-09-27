# Razz CNPL Accounts — QA Test Scenarios

Executable pack for the transaction-based AR/AP system.

How to run the automated layer:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m pytest -q
```

Browser layer (after `python run.py --init --seed`): open `http://127.0.0.1:8000` as `admin` / `admin123`.

Demo passwords are fixtures only. Change them before any real deployment.

| ID | Priority | Type | Module | Scenario | Expected | Automated test |
|----|----------|------|--------|----------|----------|----------------|
| TS-AUTH-01 | Critical | Auto | Auth | Unauthenticated GET `/` | Redirect to `/login` | `test_unauthenticated_redirects_to_login` |
| TS-AUTH-02 | Critical | Auto | Auth | Login admin / admin123 | 303 then dashboard 200 | `test_admin_login_succeeds` |
| TS-AUTH-03 | High | Auto | Auth | Wrong password | Stays on login with error | `test_invalid_login_rejected` |
| TS-AUTH-04 | High | Auto | Auth | Language toggle EN → বাংলা | Bangla labels appear | `test_language_toggle` |
| TS-SEC-01 | Critical | Auto | Roles | Auditor opens `/admin/users` | Denied | `test_auditor_cannot_open_users` |
| TS-SEC-02 | Critical | Auto | Roles | Auditor POSTs a vendor bill | Denied | `test_auditor_cannot_post_bill` |
| TS-SEC-03 | High | Auto | Roles | Accounts officer opens company settings | Denied | `test_accounts_officer_cannot_open_settings` |
| TS-SEED-01 | Critical | Auto | AR | Booked/demanded value | ৳79,300,000.00 | `test_seed_booking_value` / `test_seed_outstanding_ar` |
| TS-SEED-02 | Critical | Auto | AR | Posted receipts | ৳18,205,000.00 | `test_seed_receipts` |
| TS-SEED-03 | Critical | Auto | AR | Outstanding AR = demands − allocated receipts | ৳61,095,000.00 | `test_seed_outstanding_ar` |
| TS-SEED-04 | Critical | Auto | AR | AR is not `sum(receipts)` | Outstanding ≠ receipts | `test_ar_is_not_sum_of_receipts` |
| TS-SEED-05 | Critical | Auto | AP | Gross / VAT / TDS / retention / net | 4,080,000 / 612,000 / 179,700 / 125,000 / 4,387,300 | `test_seed_vendor_bill_totals` |
| TS-SEED-06 | Critical | Auto | AP | Four seed bills net to spec | RC 2,625,000; DS 960,500; SE 451,500; KT 350,300 | `test_seed_bills_match_vendor_refs` |
| TS-SEED-07 | Critical | Auto | Cash | Opening Petty + BRAC + City | ৳4,350,000.00 | `test_opening_cash_bank` |
| TS-SEED-08 | High | Auto | Cash | Current cash+bank = opening + receipts | ৳22,555,000.00 | `test_current_cash_includes_receipts` |
| TS-TAX-01 | Critical | Auto | Tax | Bill formula RC/MTT/2026/001 | VAT 375,000 TDS 125,000 Ret 125,000 Net 2,625,000 | `test_seed_bill_formulas` |
| TS-TAX-02 | Critical | Auto | Tax | Bill formula DS/MTT/2026/002 | Net 960,500 | `test_seed_bill_formulas` |
| TS-TAX-03 | Critical | Auto | Tax | Bill formula SE/SM/2026/003 | Net 451,500 | `test_seed_bill_formulas` |
| TS-TAX-04 | Critical | Auto | Tax | Bill formula KT/WP/2026/004 | Net 350,300 | `test_seed_bill_formulas` |
| TS-TAX-05 | High | Auto | Tax | Gross + VAT = Net + TDS + Retention | Identity holds | `test_seed_bill_formulas` |
| TS-AR-01 | Critical | Auto | AR | Allocate more than invoice outstanding | `AllocationError` | `test_cannot_allocate_more_than_invoice_outstanding` |
| TS-AR-02 | Critical | Auto | AR | Allocate more than receipt amount | `AllocationError` | `test_cannot_allocate_more_than_receipt` |
| TS-AR-03 | High | Auto | AR | Negative receipt | Rejected | `test_negative_receipt_rejected` |
| TS-AR-04 | High | Auto | AR | Partial receipt sets PARTIALLY_PAID | Status + reduced outstanding | `test_partial_and_paid_status` |
| TS-AR-05 | High | Auto | AR | Aging uses due date, as-of 31-12-2026 | Days = as_of − due_date | `test_overdue_aging_uses_due_date` |
| TS-AP-01 | Critical | Auto | AP | AP outstanding ≠ sum(gross bills) | Outstanding = net − paid | `test_ap_is_outstanding_not_gross_bills` |
| TS-AP-02 | High | Auto | AP | Negative vendor payment | Rejected | `test_negative_payment_rejected` |
| TS-AP-03 | Critical | Auto | AP | Payment over-allocation | `AllocationError` | `test_cannot_overallocate_payment` |
| TS-GL-01 | Critical | Auto | GL | Every journal debit = credit | No unbalanced posted journal | `test_every_journal_is_balanced` |
| TS-GL-02 | Critical | Auto | GL | Manual unbalanced journal | `UnbalancedJournalError` | `test_unbalanced_journal_rejected` |
| TS-TB-01 | Critical | Auto | TB | Trial balance totals | Debit = Credit | `test_trial_balance_balances` |
| TS-UI-01 | Critical | Auto | UI | All major routes | HTTP 200, no placeholder, no traceback | `test_all_major_pages_load` |
| TS-UI-02 | Critical | Auto | Dashboard | Live seed figures on dashboard | ৳ 6,10,95,000.00 and receipts ৳ 1,82,05,000.00 | `test_dashboard_totals_are_live_not_hardcoded_labels_only` |
| TS-UI-03 | High | Auto | Export | Aging, TB, VAT, TDS, Project P&L Excel | `application/vnd.openxmlformats` and ZIP header `PK` | `test_excel_exports` |
| TS-UI-04 | High | Auto | Voucher | Receipt and bill print pages | Title present | `test_vouchers_print` |

## Browser scenarios (manual or gstack browse)

Run against `http://127.0.0.1:8000` with seeded data.

### TS-UI-B01 Login and dashboard
1. Open `/login`.
2. Sign in as admin.
3. Confirm dashboard KPIs: Total Receivable ৳ 6,10,95,000.00, receipts ৳ 1,82,05,000.00, AP net ৳ 43,87,300.00, Cash+Bank ৳ 2,25,55,000.00.
4. Confirm AR is not labelled as collected receipts.

### TS-UI-B02 Receivable walkthrough
1. Open Customers, Bookings, Demands, Receipts, AR Aging, Customer Ledger.
2. Open booking `BK-2026-0001` and confirm four installment demands totalling ৳ 14,500,000.
3. Open customer ledger for Md. Rafiqul Islam: demands debit, MR-2026-0001/0002 credit, running balance.

### TS-UI-B03 Payable walkthrough
1. Open Vendors, Bills, Payments, AP Aging, Vendor Ledger.
2. Open bill `AP-2026-0001` / `RC/MTT/2026/001`.
3. Confirm Gross 2,500,000, VAT 375,000, TDS 125,000, Retention 125,000, Net 2,625,000.
4. Print debit voucher.

### TS-UI-B04 Post a vendor payment
1. Payments → Add.
2. Vendor Rahman Construction, amount 100,000, BRAC Bank, allocate to AP-2026-0001.
3. Save draft, Post.
4. Bill outstanding drops by 100,000; status PARTIALLY_PAID.
5. Trial Balance still balances.
6. Cash+Bank falls by 100,000.

### TS-UI-B05 Reject over-allocation
1. New receipt for 1,000 against an invoice with larger outstanding, allocate 1,001 without Advance.
2. Expect a validation flash, no post.

### TS-UI-B06 Period lock
1. Admin → Periods → lock 2026-07.
2. As accounts officer, try to post a July receipt.
3. Expect locked-period error.
4. Admin can still post.

### TS-UI-B07 Reverse posted document
1. As accounts officer, cancel a posted receipt — denied.
2. As admin, cancel — reversing journal created, invoice outstanding restored, receipt CANCELLED.

### TS-UI-B08 Tax master change does not rewrite history
1. Tax Settings: change Standard VAT to 10%.
2. Open AP-2026-0001 — VAT still 15% and 375,000.
3. New draft bill uses 10% preview; backend recalculates on save.

### TS-UI-B09 Excel and print
1. Export AR Aging, AP Aging, Trial Balance, TDS, VAT, Project P&L.
2. Files open in Excel with company name and timestamp.
3. Print money receipt MR-2026-0001 — amount in words, A5 voucher.

### TS-UI-B10 Roles
1. auditor / auditor123: reports and audit visible; Add/Post hidden or rejected.
2. manager / manager123: can approve; cannot open Users.
3. accounts / accounts123: can create drafts; cannot lock periods.

## Seed acceptance snapshot

After `python run.py --init --seed`:

| Measure | Value |
|---------|-------|
| Booked / demanded | ৳ 7,93,00,000.00 |
| Customer receipts | ৳ 1,82,05,000.00 |
| Outstanding AR | ৳ 6,10,95,000.00 |
| Vendor gross | ৳ 40,80,000.00 |
| Input VAT | ৳ 6,12,000.00 |
| TDS | ৳ 1,79,700.00 |
| Retention | ৳ 1,25,000.00 |
| Net vendor payable | ৳ 43,87,300.00 |
| Opening cash + bank | ৳ 43,50,000.00 |
| Current cash + bank | ৳ 2,25,55,000.00 |
| Trial balance | Debit = Credit |

## Last automated run

```
.\.venv\Scripts\python -m pytest tests -q
.................................  33 passed
```

Date: 2026-09-26

Covered: seed AR/AP/cash totals, bill formulas, allocation guards, journal/trial-balance integrity, login and role denials, every major HTML route, Excel MIME+ZIP header, vouchers, language toggle.

## Out of scope for this pack

Official NBR VAT return XML, Mushak-9.1 statutory layout, and multi-company consolidation.
