

def test_auth_config_returns_expected_fields(client):
    response = client.get("/auth/config")
    assert response.status_code == 200
    data = response.json()
    assert "google_client_id" in data
    assert "phone_otp_enabled" in data


def test_customer_tokens_and_active_token(client):
    # Register and approve dealer
    d_resp = client.post(
        "/dealer/register",
        json={
            "username": "active_gas",
            "email": "active@gas.com",
            "password": "Dealer12345",
            "name": "Active Gas Center",
            "address": "Kathmandu",
            "phone": "9841000001",
            "available_cylinders": 5,
        },
    )
    assert d_resp.status_code == 201
    dealer_id = d_resp.json()["dealer"]["id"]

    # Admin approve
    admin_resp = client.post(
        "/admin/login",
        json={"email": "admin@example.com", "password": "Admin12345"},
    )
    client.post(
        f"/admin/dealers/{dealer_id}/approve",
        headers={"Authorization": f"Bearer {admin_resp.json()['access_token']}"},
    )

    # Register customer
    c_resp = client.post(
        "/customer/register",
        json={"name": "Sita Devi", "phone": "9841000002", "password": "Customer12345"},
    )
    assert c_resp.status_code == 201
    cust_headers = {"Authorization": f"Bearer {c_resp.json()['access_token']}"}

    # Initially no active token
    active_resp = client.get("/customer/tokens/active", headers=cust_headers)
    assert active_resp.status_code == 200
    assert active_resp.json()["has_active_token"] is False

    # Join queue
    join_resp = client.post("/queue/join", json={"dealer_id": dealer_id}, headers=cust_headers)
    assert join_resp.status_code == 200
    token_id = join_resp.json()["token"]["id"]

    # Now active token is true
    active_resp = client.get("/customer/tokens/active", headers=cust_headers)
    assert active_resp.status_code == 200
    assert active_resp.json()["has_active_token"] is True
    assert active_resp.json()["token"]["token"]["id"] == token_id

    # List token history
    history_resp = client.get("/customer/tokens", headers=cust_headers)
    assert history_resp.status_code == 200
    tokens = history_resp.json()
    assert len(tokens) == 1
    assert tokens[0]["id"] == token_id


def test_dealer_mark_no_show_releases_stock(client):
    d_resp = client.post(
        "/dealer/register",
        json={
            "username": "noshow_gas",
            "email": "noshow@gas.com",
            "password": "Dealer12345",
            "name": "NoShow Gas Center",
            "address": "Lalitpur",
            "phone": "9841000003",
            "available_cylinders": 2,
        },
    )
    assert d_resp.status_code == 201
    dealer_id = d_resp.json()["dealer"]["id"]
    dealer_token = d_resp.json()["access_token"]
    dealer_headers = {"Authorization": f"Bearer {dealer_token}"}

    # Admin approve
    admin_resp = client.post(
        "/admin/login",
        json={"email": "admin@example.com", "password": "Admin12345"},
    )
    client.post(
        f"/admin/dealers/{dealer_id}/approve",
        headers={"Authorization": f"Bearer {admin_resp.json()['access_token']}"},
    )

    # Customer joins queue
    c_resp = client.post(
        "/customer/register",
        json={"name": "Hari Prasad", "phone": "9841000004", "password": "Customer12345"},
    )
    client.post(
        "/queue/join",
        json={"dealer_id": dealer_id},
        headers={"Authorization": f"Bearer {c_resp.json()['access_token']}"},
    )

    # Check dealer dashboard stock is now 1
    dash_resp = client.get(f"/dealer/{dealer_id}/dashboard", headers=dealer_headers)
    assert dash_resp.status_code == 200
    assert dash_resp.json()["available_cylinders"] == 1

    # Call next
    call_resp = client.post(f"/dealer/{dealer_id}/call-next", headers=dealer_headers)
    assert call_resp.status_code == 200
    token_id = call_resp.json()["id"]

    # Mark as NO-SHOW
    no_show_resp = client.post(f"/dealer/{dealer_id}/token/{token_id}/no-show", headers=dealer_headers)
    assert no_show_resp.status_code == 200
    assert no_show_resp.json()["status"] == "NO_SHOW"

    # Stock should be restored to 2
    dash_resp = client.get(f"/dealer/{dealer_id}/dashboard", headers=dealer_headers)
    assert dash_resp.status_code == 200
    assert dash_resp.json()["available_cylinders"] == 2
