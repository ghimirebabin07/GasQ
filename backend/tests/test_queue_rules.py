from concurrent.futures import ThreadPoolExecutor


def dealer_payload(username, name, stock):
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


def register_dealer(client, username, name, stock):
    response = client.post("/dealer/register", json=dealer_payload(username, name, stock))
    assert response.status_code == 201, response.text
    dealer = response.json()["dealer"]
    admin = client.post(
        "/admin/login",
        json={"email": "admin@example.com", "password": "Admin12345"},
    )
    assert admin.status_code == 200, admin.text
    approve = client.post(
        f"/admin/dealers/{dealer['id']}/approve",
        headers={"Authorization": f"Bearer {admin.json()['access_token']}"},
    )
    assert approve.status_code == 200, approve.text
    return approve.json()


def create_customer(client, name="Ram Sharma", phone="9812345678"):
    response = client.post(
        "/customer/register",
        json={"name": name, "phone": phone, "password": "Customer123"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def customer_headers(customer):
    return {"Authorization": f"Bearer {customer['access_token']}"}


def join_queue(client, dealer_id, customer):
    return client.post(
        "/queue/join",
        json={"dealer_id": dealer_id},
        headers=customer_headers(customer),
    )


def test_customer_can_have_only_one_active_token_across_shops(client):
    dealer_a = register_dealer(client, "dealera", "Dealer A", 5)
    dealer_b = register_dealer(client, "dealerb", "Dealer B", 5)
    customer = create_customer(client)

    first = join_queue(client, dealer_a["id"], customer)
    assert first.status_code == 200, first.text

    second = join_queue(client, dealer_b["id"], customer)
    assert second.status_code == 400
    assert second.json()["detail"] == "You already have an active token at Dealer A"


def test_customer_can_take_new_token_after_cancel(client):
    dealer_a = register_dealer(client, "dealera", "Dealer A", 5)
    dealer_b = register_dealer(client, "dealerb", "Dealer B", 5)
    customer = create_customer(client)

    first = join_queue(client, dealer_a["id"], customer)
    assert first.status_code == 200, first.text
    token_id = first.json()["token"]["id"]

    cancel = client.post(f"/queue/{token_id}/cancel", headers=customer_headers(customer))
    assert cancel.status_code == 200, cancel.text

    second = join_queue(client, dealer_b["id"], customer)
    assert second.status_code == 200, second.text


def test_no_token_when_dealer_has_zero_stock(client):
    dealer = register_dealer(client, "emptydealer", "Empty Dealer", 0)
    customer = create_customer(client)

    response = join_queue(client, dealer["id"], customer)

    assert response.status_code == 400
    assert response.json()["detail"] == "No cylinders available at this dealer"


def test_token_creation_reserves_and_cancel_releases_stock(client):
    dealer = register_dealer(client, "stockdealer", "Stock Dealer", 1)
    customer = create_customer(client)

    token_response = join_queue(client, dealer["id"], customer)
    assert token_response.status_code == 200, token_response.text
    token_id = token_response.json()["token"]["id"]

    after_join = client.get(f"/dealers/{dealer['id']}")
    assert after_join.status_code == 200
    assert after_join.json()["available_cylinders"] == 0

    cancel = client.post(f"/queue/{token_id}/cancel", headers=customer_headers(customer))
    assert cancel.status_code == 200

    after_cancel = client.get(f"/dealers/{dealer['id']}")
    assert after_cancel.status_code == 200
    assert after_cancel.json()["available_cylinders"] == 1


def test_queue_actions_create_audit_logs_and_call_notification(client):
    dealer = register_dealer(client, "auditdealer", "Audit Dealer", 3)
    customer = create_customer(client)
    dealer_login = client.post(
        "/dealer/login",
        json={"username": "auditdealer", "password": "Dealer123"},
    )
    admin_login = client.post(
        "/admin/login",
        json={"email": "admin@example.com", "password": "Admin12345"},
    )
    assert dealer_login.status_code == 200, dealer_login.text
    assert admin_login.status_code == 200, admin_login.text

    token_response = join_queue(client, dealer["id"], customer)
    assert token_response.status_code == 200, token_response.text
    token_id = token_response.json()["token"]["id"]

    called = client.post(
        f"/dealer/{dealer['id']}/call-next",
        headers={"Authorization": f"Bearer {dealer_login.json()['access_token']}"},
    )
    assert called.status_code == 200, called.text

    admin_headers = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}
    audit_logs = client.get("/admin/audit-logs", headers=admin_headers)
    notifications = client.get("/admin/notifications", headers=admin_headers)

    assert audit_logs.status_code == 200, audit_logs.text
    actions = {item["action"] for item in audit_logs.json() if item["entity_id"] == str(token_id)}
    assert {"TOKEN_CREATED", "TOKEN_CALLED"}.issubset(actions)

    assert notifications.status_code == 200, notifications.text
    assert any(
        item["notification_type"] == "TOKEN_CALLED"
        and item["related_token_id"] == token_id
        and item["user_id"] == str(customer["customer"]["id"])
        for item in notifications.json()
    )


def test_queue_status_and_cancel_require_token_owner(client):
    dealer = register_dealer(client, "ownerdealer", "Owner Dealer", 2)
    owner = create_customer(client, phone="9812345678")
    other_customer = create_customer(client, name="Sita Sharma", phone="9812345679")

    token_response = join_queue(client, dealer["id"], owner)
    assert token_response.status_code == 200, token_response.text
    token_id = token_response.json()["token"]["id"]

    missing_auth = client.get(f"/queue/{token_id}")
    wrong_owner = client.post(
        f"/queue/{token_id}/cancel",
        headers=customer_headers(other_customer),
    )
    right_owner = client.get(f"/queue/{token_id}", headers=customer_headers(owner))

    assert missing_auth.status_code == 401
    assert wrong_owner.status_code == 404
    assert right_owner.status_code == 200


def test_parallel_queue_join_creates_only_one_active_token(client):
    dealer = register_dealer(client, "racedealer", "Race Dealer", 20)
    customer = create_customer(client)

    def request_token():
        return join_queue(client, dealer["id"], customer).status_code

    with ThreadPoolExecutor(max_workers=10) as executor:
        statuses = list(executor.map(lambda _: request_token(), range(20)))

    assert statuses.count(200) == 1
    assert statuses.count(400) == 19
