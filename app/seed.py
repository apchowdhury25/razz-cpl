from __future__ import annotations

from calendar import monthrange
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import SessionLocal, init_db
from app.models import (
    AccountingPeriod,
    ChartOfAccount,
    CompanySettings,
    Customer,
    DocumentSequence,
    Employee,
    JournalSource,
    MoneyAccount,
    Project,
    TaxCategory,
    Unit,
    User,
    UserRole,
    Vendor,
)
from app.money import ZERO, money
from app.security import hash_password
from app.services.accounting import create_journal, get_system_account
from app.services.ap import create_bill
from app.services.ar import create_booking, create_receipt
from app.services.numbering import ensure_sequence

FY_START = date(2026, 7, 1)
FY_END = date(2027, 6, 30)


COA = [
    ("1000", "Cash", "নগদ", "ASSET", "CASH_CONTROL"),
    ("1010", "Petty Cash", "পেটি ক্যাশ", "ASSET", "PETTY_CASH"),
    ("1100", "Bank", "ব্যাংক", "ASSET", "BANK_CONTROL"),
    ("1110", "BRAC Bank - Current", "ব্র্যাক ব্যাংক", "ASSET", "BRAC_BANK"),
    ("1120", "City Bank - Project", "সিটি ব্যাংক", "ASSET", "CITY_BANK"),
    ("1200", "Accounts Receivable", "প্রাপ্য হিসাব", "ASSET", "AR"),
    ("1300", "Input VAT", "ইনপুট ভ্যাট", "ASSET", "INPUT_VAT"),
    ("1400", "Project Work in Progress", "চলমান কাজ", "ASSET", "WIP"),
    ("2000", "Accounts Payable", "প্রদেয় হিসাব", "LIABILITY", "AP"),
    ("2100", "TDS Payable", "টিডিএস প্রদেয়", "LIABILITY", "TDS_PAYABLE"),
    ("2200", "Retention Payable", "রিটেনশন প্রদেয়", "LIABILITY", "RETENTION_PAYABLE"),
    ("2300", "Customer Advances", "গ্রাহক অগ্রিম", "LIABILITY", "CUSTOMER_ADVANCE"),
    ("2400", "Output VAT", "আউটপুট ভ্যাট", "LIABILITY", "OUTPUT_VAT"),
    ("3000", "Opening Balance Equity", "প্রারম্ভিক মূলধন", "EQUITY", "OPENING_EQUITY"),
    ("3100", "Retained Earnings", "সংরক্ষিত মুনাফা", "EQUITY", "RETAINED"),
    ("4000", "Sales Revenue", "বিক্রয় আয়", "REVENUE", "SALES_REVENUE"),
    ("4100", "Contract Revenue", "ঠিকাদারি আয়", "REVENUE", "CONTRACT_REVENUE"),
    ("5000", "Project Construction Cost", "নির্মাণ ব্যয়", "EXPENSE", "PROJECT_COST"),
    ("5100", "Materials", "মালামাল", "EXPENSE", "MATERIALS"),
    ("5200", "Subcontractor Cost", "সাবকন্ট্রাক্টর ব্যয়", "EXPENSE", "SUBCONTRACTOR"),
    ("5300", "Professional Fees", "পেশাগত ফি", "EXPENSE", "PROFESSIONAL"),
    ("5400", "Utilities", "ইউটিলিটি", "EXPENSE", "UTILITIES"),
    ("5500", "Administrative Expense", "প্রশাসনিক ব্যয়", "EXPENSE", "ADMIN_EXPENSE"),
]

TDS_CATEGORIES = [
    ("TDS-CIVIL", "Construction / Civil Works", Decimal("5.00")),
    ("TDS-STEEL", "Cement / Iron / Steel Supply", Decimal("2.00")),
    ("TDS-GOODS", "General Goods Supply", Decimal("5.00")),
    ("TDS-ADV-NI", "Professional / Advisory — non-individual", Decimal("7.50")),
    ("TDS-ADV-I", "Professional / Advisory — individual", Decimal("15.00")),
    ("TDS-TECH-NI", "Technical Services — non-individual", Decimal("10.00")),
    ("TDS-RENT", "Office / Warehouse Rent", Decimal("10.00")),
]


def already_seeded(db: Session) -> bool:
    count = db.execute(select(func.count(Project.id))).scalar() or 0
    return count > 0


def seed_users(db: Session) -> User:
    users = [
        ("admin", "System Administrator", UserRole.ADMIN.value, "admin123"),
        ("accounts", "Accounts Officer", UserRole.ACCOUNTS_OFFICER.value, "accounts123"),
        ("manager", "Finance Manager", UserRole.MANAGER.value, "manager123"),
        ("auditor", "Internal Auditor", UserRole.AUDITOR.value, "auditor123"),
    ]
    admin = None
    for username, name, role, password in users:
        existing = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
        if existing:
            if username == "admin":
                admin = existing
            continue
        user = User(
            username=username,
            full_name=name,
            email=f"{username}@razzcnpl.local",
            password_hash=hash_password(password),
            role=role,
            is_active=True,
        )
        db.add(user)
        if username == "admin":
            admin = user
    db.flush()
    return admin


def seed_settings(db: Session) -> None:
    if db.execute(select(CompanySettings)).scalar_one_or_none():
        return
    db.add(
        CompanySettings(
            name="Razz CNPL",
            name_bn="রাজ সিএনপিএল",
            address="House 12, Road 7, Dhanmondi, Dhaka 1205, Bangladesh",
            address_bn="বাড়ি ১২, রোড ৭, ধানমন্ডি, ঢাকা ১২০৫, বাংলাদেশ",
            phone="+880 2 55000000",
            email="accounts@razzcnpl.com",
            bin_number="000000000-0000",
            tin_number="000000000000",
            default_vat_percent=Decimal("15.00"),
            default_retention_percent=Decimal("5.00"),
            fy_code="FY 2026-27",
            fy_start=FY_START,
            fy_end=FY_END,
            current_period="2026-07",
        )
    )


def seed_periods(db: Session) -> None:
    if db.execute(select(AccountingPeriod)).first():
        return
    year, month = FY_START.year, FY_START.month
    while True:
        last = monthrange(year, month)[1]
        start = date(year, month, 1)
        end = date(year, month, last)
        db.add(
            AccountingPeriod(
                code=f"{year}-{month:02d}",
                name=start.strftime("%B %Y"),
                start_date=start,
                end_date=end,
                is_locked=False,
            )
        )
        if end >= FY_END:
            break
        month += 1
        if month > 12:
            month = 1
            year += 1


def seed_coa(db: Session) -> dict[str, ChartOfAccount]:
    by_key: dict[str, ChartOfAccount] = {}
    for code, name, name_bn, acc_type, key in COA:
        acc = db.execute(select(ChartOfAccount).where(ChartOfAccount.code == code)).scalar_one_or_none()
        if not acc:
            acc = ChartOfAccount(
                code=code,
                name=name,
                name_bn=name_bn,
                account_type=acc_type,
                is_active=True,
                is_system=True,
                system_key=key,
            )
            db.add(acc)
            db.flush()
        by_key[key] = acc
    db.flush()
    return by_key


def seed_tax(db: Session) -> dict[str, TaxCategory]:
    if not db.execute(select(TaxCategory).where(TaxCategory.code == "VAT-STD")).scalar_one_or_none():
        db.add(
            TaxCategory(
                code="VAT-STD",
                name="Standard VAT",
                tax_type="VAT",
                percent=Decimal("15.00"),
                effective_date=FY_START,
                description="Configurable company setting — not legal advice.",
                is_active=True,
            )
        )
    if not db.execute(select(TaxCategory).where(TaxCategory.code == "RET-STD")).scalar_one_or_none():
        db.add(
            TaxCategory(
                code="RET-STD",
                name="Standard Retention",
                tax_type="RETENTION",
                percent=Decimal("5.00"),
                effective_date=FY_START,
                description="Default retention 5%. Overridable per project and bill.",
                is_active=True,
            )
        )
    by_code = {}
    for code, name, pct in TDS_CATEGORIES:
        cat = db.execute(select(TaxCategory).where(TaxCategory.code == code)).scalar_one_or_none()
        if not cat:
            cat = TaxCategory(
                code=code,
                name=name,
                tax_type="TDS",
                percent=pct,
                effective_date=FY_START,
                description="Configurable TDS category — not legal advice.",
                is_active=True,
            )
            db.add(cat)
            db.flush()
        by_code[code] = cat
    db.flush()
    return by_code


def seed_masters(db: Session, coa: dict[str, ChartOfAccount], tax: dict[str, TaxCategory]) -> dict:
    projects_data = [
        ("MTT", "Mermaid Twin Tower", "মারমেইড টুইন টাওয়ার", "DEVELOPER", "", "Uttara, Dhaka", date(2024, 1, 15), date(2027, 12, 31), Decimal("850000000"), ZERO),
        ("M72", "Mermaid 72.72 Katha", "মারমেইড ৭২.৭২ কাঠা", "DEVELOPER", "", "Purbachal, Dhaka", date(2024, 6, 1), date(2028, 6, 30), Decimal("1200000000"), ZERO),
        ("WP", "White Place", "হোয়াইট প্লেস", "DEVELOPER", "", "Gulshan, Dhaka", date(2023, 11, 1), date(2026, 12, 31), Decimal("420000000"), ZERO),
        ("GV", "Green View", "গ্রিন ভিউ", "DEVELOPER", "", "Bashundhara, Dhaka", date(2025, 2, 1), date(2028, 12, 31), Decimal("310000000"), ZERO),
        ("SM", "Saint Martin", "সেন্ট মার্টিন", "CONTRACTOR", "BDRCS", "Saint Martin Island", date(2025, 7, 1), date(2027, 6, 30), Decimal("95000000"), Decimal("95000000")),
        ("JR", "Joldighi Reserve", "জলদিঘি রিজার্ভ", "DEVELOPER", "", "Joldighi, Dhaka", date(2025, 1, 10), date(2028, 3, 31), Decimal("275000000"), ZERO),
    ]
    projects = {}
    for code, name, name_bn, mode, client, address, start, end, budget, contract in projects_data:
        p = db.execute(select(Project).where(Project.code == code)).scalar_one_or_none()
        if not p:
            p = Project(
                code=code,
                name=name,
                name_bn=name_bn,
                mode=mode,
                client_name=client,
                address=address,
                start_date=start,
                expected_completion=end,
                status="ACTIVE",
                budget=budget,
                contract_value=contract,
                retention_percent=Decimal("5.00"),
            )
            db.add(p)
            db.flush()
        projects[code] = p

    customers_data = [
        ("CU-0001", "Md. Rafiqul Islam", "মো. রফিকুল ইসলাম", "Late Abdur Rahman", "1985123456789", "01711-111111", "House 18, Road 4, Banani, Dhaka"),
        ("CU-0002", "Mrs. Nasrin Akter", "নাসরিন আক্তার", "Md. Abdul Malek", "1990123456789", "01712-222222", "Plot 22, Sector 7, Uttara, Dhaka"),
        ("CU-0003", "Engr. Kamal Hossain", "কামাল হোসেন", "Late Nurul Islam", "1978123456789", "01713-333333", "Apt 5B, Road 11, Dhanmondi, Dhaka"),
    ]
    customers = {}
    for code, name, name_bn, father, nid, phone, address in customers_data:
        c = db.execute(select(Customer).where(Customer.code == code)).scalar_one_or_none()
        if not c:
            c = Customer(code=code, name=name, name_bn=name_bn, father_name=father, nid=nid, phone=phone, address=address, is_active=True)
            db.add(c)
            db.flush()
        customers[code] = c

    vendors_data = [
        ("VE-0001", "Rahman Construction", "রহমান কনস্ট্রাকশন", "CONTRACTOR", Decimal("5.00"), "TDS-CIVIL", "TIN-RC-001", "House 9, Mirpur, Dhaka"),
        ("VE-0002", "Dhaka Steel House", "ঢাকা স্টিল হাউস", "MATERIAL_SUPPLIER", Decimal("2.00"), "TDS-STEEL", "TIN-DS-002", "Nawabpur, Dhaka"),
        ("VE-0003", "Shahin Electricals", "শাহিন ইলেকট্রিক্যালস", "SERVICE_PROVIDER", Decimal("7.50"), "TDS-ADV-NI", "TIN-SE-003", "Elephant Road, Dhaka"),
        ("VE-0004", "Karim Traders (Cement)", "করিম ট্রেডার্স (সিমেন্ট)", "MATERIAL_SUPPLIER", Decimal("2.00"), "TDS-STEEL", "TIN-KT-004", "Tejgaon, Dhaka"),
    ]
    vendors = {}
    for code, name, name_bn, vtype, tds, tds_code, tin, address in vendors_data:
        v = db.execute(select(Vendor).where(Vendor.code == code)).scalar_one_or_none()
        if not v:
            v = Vendor(
                code=code,
                name=name,
                name_bn=name_bn,
                vendor_type=vtype,
                tin=tin,
                address=address,
                default_tds_percent=tds,
                default_tds_category_id=tax[tds_code].id,
                is_active=True,
            )
            db.add(v)
            db.flush()
        vendors[code] = v

    units_data = [
        ("MTT", "A-501", "5", Decimal("1450"), Decimal("14500000")),
        ("MTT", "A-502", "5", Decimal("1450"), Decimal("14500000")),
        ("MTT", "B-801", "8", Decimal("1800"), Decimal("19800000")),
        ("M72", "P-01", "G", Decimal("3600"), Decimal("54000000")),
        ("WP", "A-301", "3", Decimal("1200"), Decimal("10800000")),
    ]
    units = {}
    for pcode, unum, floor, size, price in units_data:
        u = db.execute(select(Unit).where(Unit.project_id == projects[pcode].id, Unit.unit_number == unum)).scalar_one_or_none()
        if not u:
            u = Unit(
                project_id=projects[pcode].id,
                unit_number=unum,
                floor=floor,
                size_sft=size,
                base_price=price,
                sale_price=price,
                status="UNSOLD",
            )
            db.add(u)
            db.flush()
        units[f"{pcode}:{unum}"] = u

    money_accounts = {}
    for name, atype, bank, number, gl_key, opening in [
        ("Petty Cash", "CASH", "", "", "PETTY_CASH", Decimal("50000")),
        ("BRAC Bank - Current", "BANK", "BRAC Bank", "1501200000123", "BRAC_BANK", Decimal("2500000")),
        ("City Bank - Project", "BANK", "City Bank", "1502200000456", "CITY_BANK", Decimal("1800000")),
    ]:
        acc = db.execute(select(MoneyAccount).where(MoneyAccount.name == name)).scalar_one_or_none()
        if not acc:
            acc = MoneyAccount(
                name=name,
                account_type=atype,
                bank_name=bank,
                account_number=number,
                gl_account_id=coa[gl_key].id,
                opening_balance=opening,
                opening_date=FY_START,
                is_active=True,
            )
            db.add(acc)
            db.flush()
        money_accounts[name] = acc

    if not db.execute(select(Employee)).first():
        db.add(Employee(code="EM-0001", name="Fatema Khatun", designation="Accounts Officer", phone="01714-444444"))
        db.add(Employee(code="EM-0002", name="Jahangir Alam", designation="Site Engineer", phone="01715-555555"))

    db.flush()
    return {
        "projects": projects,
        "customers": customers,
        "vendors": vendors,
        "units": units,
        "money_accounts": money_accounts,
    }


def seed_opening(db: Session, coa: dict[str, ChartOfAccount], money_accounts: dict, user: User) -> None:
    from app.models import JournalEntry

    existing = db.execute(select(JournalEntry).where(JournalEntry.source_module == JournalSource.OPENING.value)).first()
    if existing:
        return
    petty = money_accounts["Petty Cash"]
    brac = money_accounts["BRAC Bank - Current"]
    city = money_accounts["City Bank - Project"]
    create_journal(
        db,
        entry_date=FY_START,
        description="Opening cash and bank balances FY 2026-27",
        lines=[
            {"account_id": petty.gl_account_id, "debit": petty.opening_balance, "credit": ZERO, "description": "Opening Petty Cash"},
            {"account_id": brac.gl_account_id, "debit": brac.opening_balance, "credit": ZERO, "description": "Opening BRAC Bank"},
            {"account_id": city.gl_account_id, "debit": city.opening_balance, "credit": ZERO, "description": "Opening City Bank"},
            {"account_id": coa["OPENING_EQUITY"].id, "debit": ZERO, "credit": money("4350000"), "description": "Opening equity"},
        ],
        source_module=JournalSource.OPENING.value,
        source_document="OB-2026-0001",
        user=user,
        year=2026,
    )


def seed_transactions(db: Session, masters: dict, user: User) -> None:
    from app.models import Booking, MoneyReceipt, VendorBill

    if db.execute(select(Booking)).first():
        return

    projects = masters["projects"]
    customers = masters["customers"]
    vendors = masters["vendors"]
    units = masters["units"]
    brac = masters["money_accounts"]["BRAC Bank - Current"]

    b1 = create_booking(
        db,
        booking_date=date(2026, 7, 15),
        customer_id=customers["CU-0001"].id,
        project_id=projects["MTT"].id,
        unit_id=units["MTT:A-501"].id,
        agreed_price=Decimal("14500000"),
        user=user,
        notes="Seed booking MTT A-501",
        booking_no="BK-2026-0001",
        generate_demands=True,
        year=2026,
    )
    b2 = create_booking(
        db,
        booking_date=date(2026, 8, 1),
        customer_id=customers["CU-0002"].id,
        project_id=projects["M72"].id,
        unit_id=units["M72:P-01"].id,
        agreed_price=Decimal("54000000"),
        user=user,
        notes="Seed booking M72 P-01",
        booking_no="BK-2026-0002",
        generate_demands=True,
        year=2026,
    )
    b3 = create_booking(
        db,
        booking_date=date(2026, 8, 20),
        customer_id=customers["CU-0003"].id,
        project_id=projects["WP"].id,
        unit_id=units["WP:A-301"].id,
        agreed_price=Decimal("10800000"),
        user=user,
        notes="Seed booking WP A-301",
        booking_no="BK-2026-0003",
        generate_demands=True,
        year=2026,
    )
    db.refresh(b1, attribute_names=["schedules"])
    db.refresh(b2, attribute_names=["schedules"])
    db.refresh(b3, attribute_names=["schedules"])

    def first_invoices(booking, n=2):
        rows = sorted(booking.schedules, key=lambda s: s.installment_no)
        return [s.invoice_id for s in rows[:n]]

    inv_b1 = first_invoices(b1)
    inv_b2 = first_invoices(b2)
    inv_b3 = first_invoices(b3)

    receipts = [
        ("MR-2026-0001", date(2026, 7, 16), customers["CU-0001"].id, projects["MTT"].id, units["MTT:A-501"].id, Decimal("1450000"), inv_b1[0], "Booking money MTT A-501"),
        ("MR-2026-0002", date(2026, 8, 14), customers["CU-0001"].id, projects["MTT"].id, units["MTT:A-501"].id, Decimal("2175000"), inv_b1[1], "Down payment MTT A-501"),
        ("MR-2026-0003", date(2026, 8, 2), customers["CU-0002"].id, projects["M72"].id, units["M72:P-01"].id, Decimal("5400000"), inv_b2[0], "Booking money M72 P-01"),
        ("MR-2026-0004", date(2026, 9, 1), customers["CU-0002"].id, projects["M72"].id, units["M72:P-01"].id, Decimal("8100000"), inv_b2[1], "Down payment M72 P-01"),
        ("MR-2026-0005", date(2026, 8, 21), customers["CU-0003"].id, projects["WP"].id, units["WP:A-301"].id, Decimal("1080000"), inv_b3[0], "Booking money WP A-301"),
    ]
    for no, rdate, cid, pid, uid, amt, invoice_id, notes in receipts:
        create_receipt(
            db,
            receipt_date=rdate,
            customer_id=cid,
            amount=amt,
            money_account_id=brac.id,
            user=user,
            project_id=pid,
            unit_id=uid,
            payment_method="BANK_TRANSFER",
            reference_no=no.replace("MR", "TT"),
            notes=notes,
            received_by="Accounts",
            receipt_no=no,
            allocations=[{"invoice_id": invoice_id, "amount": amt}],
            auto_post=True,
            year=2026,
        )

    from app.models import ChartOfAccount

    sub = db.execute(select(ChartOfAccount).where(ChartOfAccount.system_key == "SUBCONTRACTOR")).scalar_one()
    mat = db.execute(select(ChartOfAccount).where(ChartOfAccount.system_key == "MATERIALS")).scalar_one()
    prof = db.execute(select(ChartOfAccount).where(ChartOfAccount.system_key == "PROFESSIONAL")).scalar_one()

    bills = [
        {
            "bill_no": "AP-2026-0001",
            "vendor_bill_ref": "RC/MTT/2026/001",
            "bill_date": date(2026, 7, 20),
            "due_date": date(2026, 8, 20),
            "vendor_id": vendors["VE-0001"].id,
            "project_id": projects["MTT"].id,
            "description": "Civil works progress bill — MTT podium",
            "gross_amount": Decimal("2500000"),
            "vat_percent": Decimal("15.00"),
            "tds_percent": Decimal("5.00"),
            "retention_percent": Decimal("5.00"),
            "cost_account_id": sub.id,
            "mushak_ref": "Mushak-6.3/RC/001",
        },
        {
            "bill_no": "AP-2026-0002",
            "vendor_bill_ref": "DS/MTT/2026/002",
            "bill_date": date(2026, 8, 10),
            "due_date": date(2026, 9, 10),
            "vendor_id": vendors["VE-0002"].id,
            "project_id": projects["MTT"].id,
            "description": "MS rod supply — MTT",
            "gross_amount": Decimal("850000"),
            "vat_percent": Decimal("15.00"),
            "tds_percent": Decimal("2.00"),
            "retention_percent": Decimal("0.00"),
            "cost_account_id": mat.id,
            "mushak_ref": "Mushak-6.3/DS/002",
        },
        {
            "bill_no": "AP-2026-0003",
            "vendor_bill_ref": "SE/SM/2026/003",
            "bill_date": date(2026, 9, 1),
            "due_date": date(2026, 10, 1),
            "vendor_id": vendors["VE-0003"].id,
            "project_id": projects["SM"].id,
            "description": "Electrical consultancy — Saint Martin / BDRCS",
            "gross_amount": Decimal("420000"),
            "vat_percent": Decimal("15.00"),
            "tds_percent": Decimal("7.50"),
            "retention_percent": Decimal("0.00"),
            "cost_account_id": prof.id,
            "mushak_ref": "Mushak-6.3/SE/003",
        },
        {
            "bill_no": "AP-2026-0004",
            "vendor_bill_ref": "KT/WP/2026/004",
            "bill_date": date(2026, 9, 15),
            "due_date": date(2026, 10, 15),
            "vendor_id": vendors["VE-0004"].id,
            "project_id": projects["WP"].id,
            "description": "Cement supply — White Place",
            "gross_amount": Decimal("310000"),
            "vat_percent": Decimal("15.00"),
            "tds_percent": Decimal("2.00"),
            "retention_percent": Decimal("0.00"),
            "cost_account_id": mat.id,
            "mushak_ref": "Mushak-6.3/KT/004",
        },
    ]
    for payload in bills:
        create_bill(db, user=user, auto_post=True, year=2026, **payload)

    for doc_type, nxt in [("BK", 4), ("AR", 13), ("MR", 6), ("AP", 5), ("VP", 1), ("JV", 20)]:
        seq = ensure_sequence(db, doc_type, 2026)
        if seq.next_number < nxt:
            seq.next_number = nxt
    db.flush()


def seed_all(db: Session | None = None) -> None:
    close = False
    if db is None:
        init_db()
        db = SessionLocal()
        close = True
    try:
        admin = seed_users(db)
        seed_settings(db)
        seed_periods(db)
        coa = seed_coa(db)
        tax = seed_tax(db)
        db.flush()
        masters = seed_masters(db, coa, tax)
        seed_opening(db, coa, masters["money_accounts"], admin)
        seed_transactions(db, masters, admin)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        if close:
            db.close()


if __name__ == "__main__":
    seed_all()
    print("Seed complete.")
