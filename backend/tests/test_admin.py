def dealer_payload(username="pendingdealer", email="pending@example.com"):
    return {
        "username": username,
        "email": email,
        "password": "Dealer123",
        "name": "Pending Dealer",
        "address": "Kathmandu 1",
        "phone": "9801234567",
        "available_cylinders": 10,
        "latitude": None,
        "longitude": None,
    }


def admin_token(client):
    response = client.post(
        "/admin/login",
        json={"email": "admin@example.com", "password": "Admin12345"},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def test_admin_can_approve_pending_dealer(client):
    registered = client.post("/dealer/register", json=dealer_payload())
    assert registered.status_code == 201, registered.text
    dealer_id = registered.json()["dealer"]["id"]
    assert registered.json()["dealer"]["status"] == "PENDING"

    public_before = client.get("/dealers")
    assert all(dealer["id"] != dealer_id for dealer in public_before.json())

    token = admin_token(client)
    approved = client.post(
        f"/admin/dealers/{dealer_id}/approve",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "APPROVED"

    public_after = client.get("/dealers")
    assert any(dealer["id"] == dealer_id for dealer in public_after.json())

    audit_logs = client.get(
        "/admin/audit-logs",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert audit_logs.status_code == 200, audit_logs.text
    assert any(
        item["action"] == "DEALER_APPROVED" and item["entity_id"] == str(dealer_id)
        for item in audit_logs.json()
    )


def test_admin_can_suspend_dealer(client):
    registered = client.post("/dealer/register", json=dealer_payload())
    dealer_id = registered.json()["dealer"]["id"]
    token = admin_token(client)
    client.post(f"/admin/dealers/{dealer_id}/approve", headers={"Authorization": f"Bearer {token}"})

    suspended = client.post(
        f"/admin/dealers/{dealer_id}/suspend",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert suspended.status_code == 200, suspended.text
    assert suspended.json()["status"] == "SUSPENDED"
    assert suspended.json()["is_active"] is False

    audit_logs = client.get(
        "/admin/audit-logs",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert any(
        item["action"] == "DEALER_SUSPENDED" and item["entity_id"] == str(dealer_id)
        for item in audit_logs.json()
    )


def test_admin_routes_require_admin_token(client):
    response = client.get("/admin/dealers")

    assert response.status_code == 401


def test_admin_audit_and_notifications_require_admin_token(client):
    audit_response = client.get("/admin/audit-logs")
    notifications_response = client.get("/admin/notifications")

    assert audit_response.status_code == 401
    assert notifications_response.status_code == 401
