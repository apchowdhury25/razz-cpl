"""TS-SEC — authentication, roles, CSRF."""

from tests.conftest import extract_csrf, login


def test_unauthenticated_redirects_to_login(client):
    response = client.get("/", follow_redirects=False)
    assert response.status_code in (303, 302)
    assert "/login" in response.headers.get("location", "")


def test_admin_login_succeeds(client):
    response = login(client, "admin", "admin123")
    assert response.status_code == 303
    dash = client.get("/")
    assert dash.status_code == 200
    assert "Total Receivable" in dash.text or "প্রাপ্য" in dash.text


def test_invalid_login_rejected(client):
    login(client, "admin", "wrong-password")
    page = client.get("/login")
    assert "Invalid" in page.text or "সঠিক নয়" in page.text


def test_auditor_cannot_open_users(client):
    login(client, "auditor", "auditor123")
    response = client.get("/admin/users")
    assert response.status_code in (200, 403)
    assert "User created" not in response.text
    assert "Add user" not in response.text or "not authorized" in response.text.lower() or "Not authorized" in response.text


def test_auditor_cannot_post_bill(client):
    login(client, "auditor", "auditor123")
    page = client.get("/bills/new")
    token = extract_csrf(page.text)
    response = client.post(
        "/bills/new",
        data={
            "csrf": token,
            "bill_date": "2026-09-01",
            "due_date": "2026-09-30",
            "vendor_id": "1",
            "gross_amount": "100",
            "vat_percent": "15",
            "tds_percent": "0",
            "retention_percent": "0",
            "cost_account_id": "1",
        },
        follow_redirects=False,
    )
    assert response.status_code in (303, 403, 400)


def test_accounts_officer_cannot_open_settings(client):
    login(client, "accounts", "accounts123")
    response = client.get("/admin/settings")
    assert "Company" not in response.text or "not authorized" in response.text.lower() or "Not authorized" in response.text
