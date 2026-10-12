def dealer_payload(username="dealerone", name="Dealer One", stock=10):
    return {
        "username": username,
        "email": f"{username}@example.com",
        "password": "Dealer123",
        "name": name,
        "address": "Kathmandu 1",
        "phone": "9801234567",
        "available_cylinders": stock,
        "latitude": None,
        "longitude": None,
    }


def register_dealer(client, username="dealerone", name="Dealer One", stock=10):
    response = client.post("/dealer/register", json=dealer_payload(username, name, stock))
    assert response.status_code == 201, response.text
    return response.json()


def approve_dealer(client, dealer_id):
    admin = client.post(
        "/admin/login",
        json={"email": "admin@example.com", "password": "Admin12345"},
    )
    assert admin.status_code == 200, admin.text
    response = client.post(
        f"/admin/dealers/{dealer_id}/approve",
        headers={"Authorization": f"Bearer {admin.json()['access_token']}"},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_health_and_ready(client):
    health = client.get("/health")
    ready = client.get("/ready")

    assert health.status_code == 200
    assert health.json() == {"status": "ok"}
    assert ready.status_code == 200
    assert ready.json() == {"status": "ready"}


def test_dealer_register_login_and_me(client):
    registered = register_dealer(client)

    assert registered["token_type"] == "bearer"
    assert registered["access_token"]
    assert registered["dealer"]["username"] == "dealerone"
    assert registered["dealer"]["status"] == "PENDING"
    assert registered["dealer"]["name"] == "Dealer One"

    login = client.post(
        "/dealer/login",
        json={"username": "dealerone", "password": "Dealer123"},
    )
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]

    me = client.get("/dealer/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["username"] == "dealerone"


def test_pending_dealer_cannot_access_dashboard(client):
    registered = register_dealer(client)
    token = registered["access_token"]

    dashboard = client.get("/dealer/me/dashboard", headers={"Authorization": f"Bearer {token}"})

    assert dashboard.status_code == 403
    assert dashboard.json()["detail"] == "Dealer is not approved yet"


def test_dealer_me_requires_authentication(client):
    response = client.get("/dealer/me")

    assert response.status_code == 401
    assert response.json()["detail"] == "Dealer login required"


def test_dealer_cannot_access_another_dealer_dashboard(client):
    first = register_dealer(client, "dealerone", "Dealer One")
    second = register_dealer(client, "dealertwo", "Dealer Two")
    approve_dealer(client, first["dealer"]["id"])
    approve_dealer(client, second["dealer"]["id"])
    first_token = first["access_token"]
    second_dealer_id = second["dealer"]["id"]

    response = client.get(
        f"/dealer/{second_dealer_id}/dashboard",
        headers={"Authorization": f"Bearer {first_token}"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "You can only manage your own dealer account"


def test_customer_create_validates_phone(client):
    response = client.post("/customers", json={"name": "Ram Sharma", "phone": "abc"})

    assert response.status_code == 422
