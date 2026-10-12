import sys

from fastapi import HTTPException


def get_active_google_verifier():
    return sys.modules["services.google_auth_service"].get_google_verifier


def test_google_login_customer_success(client):
    mock_payload = {
        "iss": "https://accounts.google.com",
        "sub": "google-user-12345",
        "email": "customer.google@example.com",
        "email_verified": True,
        "name": "Google Customer",
    }
    verifier_dep = get_active_google_verifier()
    client.app.dependency_overrides[verifier_dep] = lambda: (lambda token: mock_payload)
    try:
        response = client.post("/customer/auth/google", json={"id_token": "valid-google-token-string"})
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["customer"]["email"] == "customer.google@example.com"
        assert data["customer"]["name"] == "Google Customer"
        assert data["customer"]["is_phone_verified"] is False
    finally:
        client.app.dependency_overrides.pop(verifier_dep, None)


def test_google_login_rejects_unverified_email(client):
    def bad_verifier(token):
        raise HTTPException(status_code=400, detail="Google account email is not verified")

    verifier_dep = get_active_google_verifier()
    client.app.dependency_overrides[verifier_dep] = lambda: bad_verifier
    try:
        response = client.post("/customer/auth/google", json={"id_token": "unverified-google-token"})
        assert response.status_code == 400
        assert "Google account email is not verified" in response.json()["detail"]
    finally:
        client.app.dependency_overrides.pop(verifier_dep, None)


def test_email_otp_flow_complete(client):
    email = "otpuser@example.com"

    # Step 1: Send OTP
    send_resp = client.post("/customer/auth/otp/send", json={"email": email})
    assert send_resp.status_code == 200
    assert "Verification code sent" in send_resp.json()["message"]

    # Step 2: Requesting again immediately should hit 60s cooldown (429)
    cooldown_resp = client.post("/customer/auth/otp/send", json={"email": email})
    assert cooldown_resp.status_code == 429
    assert "60 seconds" in cooldown_resp.json()["detail"]

    # Fetch the code directly from test DB to simulate email receipt
    import database
    from models.email_otp import EmailOtp
    from services.otp_service import hash_otp_code

    db = database.SessionLocal()
    otp_record = db.query(EmailOtp).filter(EmailOtp.email == email).first()
    assert otp_record is not None
    db.close()

    # Step 3: Wrong code attempts
    wrong_resp = client.post("/customer/auth/otp/verify", json={"email": email, "code": "000000"})
    assert wrong_resp.status_code == 400
    assert "Incorrect code" in wrong_resp.json()["detail"]

    # Step 4: Verify with correct code
    test_code = "654321"
    db = database.SessionLocal()
    otp_record = db.query(EmailOtp).filter(EmailOtp.email == email).first()
    otp_record.code_hash = hash_otp_code(test_code)
    otp_record.attempts = 0
    db.commit()
    db.close()

    verify_resp = client.post("/customer/auth/otp/verify", json={"email": email, "code": test_code})
    assert verify_resp.status_code == 200
    verify_data = verify_resp.json()
    assert "access_token" in verify_data
    assert "refresh_token" in verify_data
    assert verify_data["customer"]["email"] == email


def test_email_otp_lockout_after_max_attempts(client):
    email = "lockout@example.com"
    client.post("/customer/auth/otp/send", json={"email": email})

    for attempt in range(1, 5):
        resp = client.post("/customer/auth/otp/verify", json={"email": email, "code": "999999"})
        assert resp.status_code == 400

    # 5th failed attempt triggers lockout
    resp5 = client.post("/customer/auth/otp/verify", json={"email": email, "code": "999999"})
    assert resp5.status_code == 429
    assert "Account locked" in resp5.json()["detail"]

    # Further attempts are blocked by lockout
    resp6 = client.post("/customer/auth/otp/verify", json={"email": email, "code": "999999"})
    assert resp6.status_code == 429
    assert "Try again in" in resp6.json()["detail"]


def test_nepal_phone_validation_and_update(client):
    email = "phoneuser@example.com"
    mock_payload = {
        "iss": "https://accounts.google.com",
        "sub": "google-user-phone-test",
        "email": email,
        "email_verified": True,
        "name": "Phone Test User",
    }
    verifier_dep = get_active_google_verifier()
    client.app.dependency_overrides[verifier_dep] = lambda: (lambda token: mock_payload)
    try:
        login_resp = client.post("/customer/auth/google", json={"id_token": "dummy-token"})
        assert login_resp.status_code == 200
        token = login_resp.json()["access_token"]

        # Invalid Nepal phone format rejected
        bad_phone_resp = client.put(
            "/customer/phone",
            json={"phone": "1234567890"},  # does not start with 97 or 98
            headers={"Authorization": f"Bearer {token}"},
        )
        assert bad_phone_resp.status_code == 422

        # Valid Nepal phone accepted (+977 9812345678)
        good_phone_resp = client.put(
            "/customer/phone",
            json={"phone": "+9779812345678"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert good_phone_resp.status_code == 200
        assert good_phone_resp.json()["phone"] == "9812345678"
        assert good_phone_resp.json()["is_phone_verified"] is False
    finally:
        client.app.dependency_overrides.pop(verifier_dep, None)


def test_refresh_token_rotation_and_revocation(client):
    # Register customer to get tokens
    reg_resp = client.post(
        "/customer/register",
        json={"name": "Refresh Tester", "phone": "9811223344", "password": "Password123"},
    )
    assert reg_resp.status_code == 201
    initial_refresh = reg_resp.json()["refresh_token"]

    # Use refresh token to rotate
    rotate_resp = client.post("/auth/refresh", json={"refresh_token": initial_refresh})
    assert rotate_resp.status_code == 200
    rotate_data = rotate_resp.json()
    assert bool(rotate_data["access_token"])
    new_refresh = rotate_data["refresh_token"]
    assert new_refresh != initial_refresh
    assert rotate_data["user"]["role"] == "customer"

    # Old refresh token is now revoked and cannot be reused
    reuse_resp = client.post("/auth/refresh", json={"refresh_token": initial_refresh})
    assert reuse_resp.status_code == 401

    # Logout with the new refresh token
    logout_resp = client.post("/auth/logout", json={"refresh_token": new_refresh})
    assert logout_resp.status_code == 200

    # Using the logged-out refresh token fails
    after_logout_resp = client.post("/auth/refresh", json={"refresh_token": new_refresh})
    assert after_logout_resp.status_code == 401


def test_rbac_endpoint_protection(client):
    # Create customer token
    cust_resp = client.post(
        "/customer/register",
        json={"name": "RBAC Customer", "phone": "9899887766", "password": "Password123"},
    )
    cust_token = cust_resp.json()["access_token"]

    # Customer trying to access admin endpoints gets 403
    admin_access = client.get("/admin/dealers", headers={"Authorization": f"Bearer {cust_token}"})
    assert admin_access.status_code == 403

    # Customer trying to access dealer private profile gets 403
    dealer_access = client.get("/dealer/me", headers={"Authorization": f"Bearer {cust_token}"})
    assert dealer_access.status_code == 403
