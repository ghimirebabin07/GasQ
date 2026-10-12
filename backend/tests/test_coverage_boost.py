import smtplib
from unittest.mock import MagicMock, patch

from services.mail_service import SmtpMailProvider
from services.notification_service import notification_bus
from services.sms_service import ConsoleSmsProvider, get_sms_provider


def test_sms_provider_console():
    provider = ConsoleSmsProvider()
    assert provider.send_sms("+9779841234567", "Your token #101 is called") is True
    factory_provider = get_sms_provider()
    assert factory_provider.send_sms("+9779841234567", "Test") is True


def test_smtp_mail_provider_success():
    provider = SmtpMailProvider()
    provider.settings.smtp_host = "smtp.example.com"
    provider.settings.smtp_port = 587
    provider.settings.smtp_username = "user@example.com"
    provider.settings.smtp_password = "secretpassword"

    with patch("smtplib.SMTP") as mock_smtp:
        instance = MagicMock()
        mock_smtp.return_value.__enter__.return_value = instance
        res = provider.send_email("recipient@example.com", "Test Subject", "Hello body")
        assert res is True
        instance.starttls.assert_called_once()
        instance.login.assert_called_once_with("user@example.com", "secretpassword")
        instance.send_message.assert_called_once()


def test_smtp_mail_provider_failure():
    provider = SmtpMailProvider()
    provider.settings.smtp_host = "invalid.host"
    provider.settings.smtp_port = 587
    with patch("smtplib.SMTP", side_effect=smtplib.SMTPException("Connection error")):
        res = provider.send_email("recipient@example.com", "Subject", "Body")
        assert res is False


def test_notification_bus():
    q = notification_bus.subscribe("customer", "999")
    notification_bus.broadcast("customer", "999", {"msg": "hello"})
    assert not q.empty()
    item = q.get_nowait()
    assert item == {"msg": "hello"}
    notification_bus.unsubscribe("customer", "999", q)


def test_customer_update_duplicate_phone_fails(client):
    # Customer A
    client.post("/customer/register", json={"name": "Alice", "phone": "9841111111", "password": "Password123"})
    # Customer B
    b_resp = client.post("/customer/register", json={"name": "Bob", "phone": "9841222222", "password": "Password123"})
    b_token = b_resp.json()["access_token"]

    # Bob tries to update phone to Alice's phone
    conflict_resp = client.put(
        "/customer/phone",
        json={"phone": "9841111111"},
        headers={"Authorization": f"Bearer {b_token}"},
    )
    assert conflict_resp.status_code == 400


def test_dealer_profile_update_and_deactivate(client):
    reg = client.post(
        "/dealer/register",
        json={
            "username": "profile_gas",
            "email": "profile@gas.com",
            "password": "Password123",
            "name": "Profile Gas",
            "address": "Kathmandu",
            "phone": "9841333333",
            "available_cylinders": 10,
        },
    )
    dealer_token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {dealer_token}"}

    # Update profile
    update_resp = client.put(
        "/dealer/me",
        json={
            "name": "Updated Gas Center",
            "address": "Patan",
            "phone": "9841444444",
            "available_cylinders": 15,
        },
        headers=headers,
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["name"] == "Updated Gas Center"
    assert update_resp.json()["available_cylinders"] == 15

    # Deactivate dealer
    del_resp = client.delete("/dealer/me", headers=headers)
    assert del_resp.status_code == 200
    assert del_resp.json()["is_active"] is False


def test_dealer_skip_token(client):
    # Register dealer
    d_resp = client.post(
        "/dealer/register",
        json={
            "username": "skip_gas",
            "email": "skip@gas.com",
            "password": "Password123",
            "name": "Skip Gas Center",
            "address": "Bhaktapur",
            "phone": "9841555555",
            "available_cylinders": 3,
        },
    )
    dealer_id = d_resp.json()["dealer"]["id"]
    dealer_headers = {"Authorization": f"Bearer {d_resp.json()['access_token']}"}

    # Approve
    admin = client.post("/admin/login", json={"email": "admin@example.com", "password": "Admin12345"})
    client.post(f"/admin/dealers/{dealer_id}/approve", headers={"Authorization": f"Bearer {admin.json()['access_token']}"})

    # Customer joins
    c_resp = client.post("/customer/register", json={"name": "Kiran", "phone": "9841666666", "password": "Password123"})
    client.post("/queue/join", json={"dealer_id": dealer_id}, headers={"Authorization": f"Bearer {c_resp.json()['access_token']}"})

    # Dealer calls
    call_resp = client.post(f"/dealer/{dealer_id}/call-next", headers=dealer_headers)
    token_id = call_resp.json()["id"]

    # Dealer skips token
    skip_resp = client.post(f"/dealer/{dealer_id}/token/{token_id}/skip", headers=dealer_headers)
    assert skip_resp.status_code == 200
    assert skip_resp.json()["status"] == "SKIPPED"


def test_dealer_serve_token(client):
    d_resp = client.post(
        "/dealer/register",
        json={
            "username": "serve_gas",
            "email": "serve@gas.com",
            "password": "Password123",
            "name": "Serve Gas Center",
            "address": "Kavre",
            "phone": "9841777777",
            "available_cylinders": 5,
        },
    )
    dealer_id = d_resp.json()["dealer"]["id"]
    dealer_headers = {"Authorization": f"Bearer {d_resp.json()['access_token']}"}

    # Approve
    admin = client.post("/admin/login", json={"email": "admin@example.com", "password": "Admin12345"})
    client.post(f"/admin/dealers/{dealer_id}/approve", headers={"Authorization": f"Bearer {admin.json()['access_token']}"})

    # Customer joins
    c_resp = client.post("/customer/register", json={"name": "Deepak", "phone": "9841888888", "password": "Password123"})
    client.post("/queue/join", json={"dealer_id": dealer_id}, headers={"Authorization": f"Bearer {c_resp.json()['access_token']}"})

    # Call and Serve
    call_resp = client.post(f"/dealer/{dealer_id}/call-next", headers=dealer_headers)
    token_id = call_resp.json()["id"]

    serve_resp = client.post(f"/dealer/{dealer_id}/token/{token_id}/serve", headers=dealer_headers)
    assert serve_resp.status_code == 200
    assert serve_resp.json()["status"] == "SERVED"


def test_dealer_cannot_call_when_already_called(client):
    d_resp = client.post(
        "/dealer/register",
        json={
            "username": "doublecall_gas",
            "email": "double@gas.com",
            "password": "Password123",
            "name": "Double Gas",
            "address": "Kathmandu",
            "phone": "9841999991",
            "available_cylinders": 5,
        },
    )
    dealer_id = d_resp.json()["dealer"]["id"]
    dealer_headers = {"Authorization": f"Bearer {d_resp.json()['access_token']}"}

    # Approve
    admin = client.post("/admin/login", json={"email": "admin@example.com", "password": "Admin12345"})
    client.post(f"/admin/dealers/{dealer_id}/approve", headers={"Authorization": f"Bearer {admin.json()['access_token']}"})

    # Customers 1 and 2
    c1 = client.post("/customer/register", json={"name": "One", "phone": "9841999992", "password": "Password123"})
    c2 = client.post("/customer/register", json={"name": "Two", "phone": "9841999993", "password": "Password123"})

    client.post("/queue/join", json={"dealer_id": dealer_id}, headers={"Authorization": f"Bearer {c1.json()['access_token']}"})
    client.post("/queue/join", json={"dealer_id": dealer_id}, headers={"Authorization": f"Bearer {c2.json()['access_token']}"})

    # First call succeeds
    client.post(f"/dealer/{dealer_id}/call-next", headers=dealer_headers)

    # Second call before resolving first fails with 400
    second_call = client.post(f"/dealer/{dealer_id}/call-next", headers=dealer_headers)
    assert second_call.status_code == 400
    assert "Resolve current token first" in second_call.text


def test_customer_sse_stream_auth_guards(client):
    # No token -> 401
    resp = client.get("/customer/notifications/stream")
    assert resp.status_code == 401

    # Dealer token -> 403 (Customer required)
    d_resp = client.post(
        "/dealer/register",
        json={
            "username": "sse_gas",
            "email": "sse@gas.com",
            "password": "Password123",
            "name": "SSE Gas",
            "address": "Kathmandu",
            "phone": "9841999994",
            "available_cylinders": 1,
        },
    )
    resp = client.get(
        "/customer/notifications/stream",
        headers={"Authorization": f"Bearer {d_resp.json()['access_token']}"},
    )
    assert resp.status_code == 403


def test_customer_google_login_existing_user(client):
    import importlib
    main = importlib.import_module("main")
    from services.google_auth_service import get_google_verifier

    mock_verifier = MagicMock()
    mock_verifier.return_value = {
        "email": "google_user@example.com",
        "sub": "google-sub-12345",
        "name": "Google User",
        "email_verified": True,
    }
    main.app.dependency_overrides[get_google_verifier] = lambda: mock_verifier
    try:
        # First login creates user
        resp1 = client.post("/customer/auth/google", json={"id_token": "valid-token-1"})
        assert resp1.status_code == 200

        # Second login updates existing user
        resp2 = client.post("/customer/auth/google", json={"id_token": "valid-token-2"})
        assert resp2.status_code == 200
        assert resp2.json()["customer"]["email"] == "google_user@example.com"
    finally:
        main.app.dependency_overrides.pop(get_google_verifier, None)


def test_dealer_google_login_flow(client):
    import importlib
    main = importlib.import_module("main")
    from services.google_auth_service import get_google_verifier

    mock_verifier = MagicMock()
    mock_verifier.return_value = {
        "email": "dealer_google@example.com",
        "sub": "google-sub-dealer-999",
        "name": "Google Dealer",
        "email_verified": True,
    }
    main.app.dependency_overrides[get_google_verifier] = lambda: mock_verifier
    try:
        # Not registered yet -> 404
        fail_resp = client.post("/dealer/auth/google", json={"id_token": "valid-id-token-12345"})
        assert fail_resp.status_code == 404

        # Register dealer with that email
        client.post(
            "/dealer/register",
            json={
                "username": "dealer_goog",
                "email": "dealer_google@example.com",
                "password": "Password123",
                "name": "Google Shop",
                "address": "Lalitpur",
                "phone": "9841999995",
                "available_cylinders": 10,
            },
        )

        # Now Google login succeeds
        success_resp = client.post("/dealer/auth/google", json={"id_token": "valid-id-token-12345"})
        assert success_resp.status_code == 200
        assert success_resp.json()["dealer"]["email"] == "dealer_google@example.com"
    finally:
        main.app.dependency_overrides.pop(get_google_verifier, None)


def test_queue_service_invalid_transitions(client):
    import pytest
    from database import SessionLocal
    from fastapi import HTTPException
    from services import queue_service

    # Register and approve dealer
    d = client.post(
        "/dealer/register",
        json={"username": "edge_dealer", "email": "edge@d.com", "password": "Password123", "name": "Edge D", "address": "Ktm", "phone": "9841001122", "available_cylinders": 5},
    )
    did = d.json()["dealer"]["id"]
    admin = client.post("/admin/login", json={"email": "admin@example.com", "password": "Admin12345"})
    client.post(f"/admin/dealers/{did}/approve", headers={"Authorization": f"Bearer {admin.json()['access_token']}"})

    c = client.post("/customer/register", json={"name": "Edge C", "phone": "9841001133", "password": "Password123"})
    j = client.post("/queue/join", json={"dealer_id": did}, headers={"Authorization": f"Bearer {c.json()['access_token']}"})
    tid = j.json()["token"]["id"]

    with SessionLocal() as db:
        # Negative stock raises 400
        with pytest.raises(HTTPException):
            queue_service.update_stock(db, did, -1)

        # Serve token when still WAITING raises 400
        with pytest.raises(HTTPException):
            queue_service.serve_token(db, did, tid)

        # Skip token when still WAITING raises 400
        with pytest.raises(HTTPException):
            queue_service.skip_token(db, did, tid)

        # Mark no-show when still WAITING raises 400
        with pytest.raises(HTTPException):
            queue_service.mark_no_show_token(db, did, tid)


def test_customer_notification_404(client):
    c = client.post("/customer/register", json={"name": "Notif C", "phone": "9841001144", "password": "Password123"})
    token = c.json()["access_token"]
    resp = client.post("/customer/notifications/999999/read", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 404


def test_dealer_queue_endpoint(client):
    d = client.post(
        "/dealer/register",
        json={"username": "q_dealer", "email": "q@d.com", "password": "Password123", "name": "Q Dealer", "address": "Ktm", "phone": "9841001155", "available_cylinders": 5},
    )
    did = d.json()["dealer"]["id"]
    d_token = d.json()["access_token"]

    admin = client.post("/admin/login", json={"email": "admin@example.com", "password": "Admin12345"})
    client.post(f"/admin/dealers/{did}/approve", headers={"Authorization": f"Bearer {admin.json()['access_token']}"})

    resp = client.get(f"/dealer/{did}/queue", headers={"Authorization": f"Bearer {d_token}"})
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
