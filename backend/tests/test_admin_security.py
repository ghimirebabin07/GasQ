import time

from auth import create_access_token, decode_access_token, hash_password
from fastapi import HTTPException
from services.totp_service import (
    build_totp_provisioning_uri,
    generate_current_totp,
    generate_totp_secret,
    verify_totp,
)


def test_password_hash_cost_and_verification():
    raw_pass = "ComplexAdminPass123!"
    hashed = hash_password(raw_pass)
    assert hashed.startswith("$2b$12$") or hashed.startswith("$2b$")
    from auth import verify_password
    assert verify_password(raw_pass, hashed) is True
    assert verify_password("WrongPassword123!", hashed) is False


def test_generic_invalid_credentials_error_message(client):
    # Non-existent email
    res1 = client.post("/admin/login", json={"email": "nobody@example.com", "password": "WrongPassword123!"})
    assert res1.status_code == 401
    assert res1.json()["detail"] == "Invalid credentials"

    # Real admin, wrong password
    res2 = client.post("/admin/login", json={"email": "admin@example.com", "password": "WrongPassword123!"})
    assert res2.status_code == 401
    assert res2.json()["detail"] == "Invalid credentials"


def test_brute_force_lockout_after_five_failed_attempts(client):
    target_email = "admin@example.com"

    # Fire 4 failed attempts
    for _ in range(4):
        r = client.post("/admin/login", json={"email": target_email, "password": "BadPassword123!"})
        assert r.status_code == 401
        assert r.json()["detail"] == "Invalid credentials"

    # 5th attempt triggers lockout
    r5 = client.post("/admin/login", json={"email": target_email, "password": "BadPassword123!"})
    assert r5.status_code == 429
    assert "temporarily locked" in r5.json()["detail"]

    # Even with correct password now, it should remain locked
    r6 = client.post("/admin/login", json={"email": target_email, "password": "Admin12345"})
    assert r6.status_code == 429
    assert "temporarily locked" in r6.json()["detail"]


def test_admin_idle_and_absolute_session_expiry():
    # 1. Normal valid access token
    token = create_access_token("admin@example.com", role="admin")
    role, sub = decode_access_token(token)
    assert role == "admin"
    assert sub == "admin@example.com"

    # 2. Absolute timeout expired
    past_auth_time = int(time.time()) - (5 * 3600)  # 5 hours ago (> 4 hr max)
    expired_token = create_access_token("admin@example.com", role="admin", auth_time=past_auth_time)
    try:
        decode_access_token(expired_token)
        assert False, "Should have raised HTTPException for absolute session timeout"
    except HTTPException as exc:
        assert exc.status_code == 401
        assert "Session expired" in exc.detail


def test_refresh_token_rotation_and_reuse_detection(client):
    # Login to obtain tokens
    login_res = client.post("/admin/login", json={"email": "admin@example.com", "password": "Admin12345"})
    assert login_res.status_code == 200
    ref_token_1 = login_res.json()["refresh_token"]

    # Rotate refresh token
    rotate_res = client.post("/auth/refresh", json={"refresh_token": ref_token_1})
    assert rotate_res.status_code == 200
    ref_token_2 = rotate_res.json()["refresh_token"]
    assert ref_token_1 != ref_token_2

    # REUSE ATTACK: Attempt to use ref_token_1 again!
    reuse_res = client.post("/auth/refresh", json={"refresh_token": ref_token_1})
    assert reuse_res.status_code == 401
    assert "reuse detected" in reuse_res.json()["detail"].lower()

    # ref_token_2 should also be invalidated now because of breach detection
    invalidated_res = client.post("/auth/refresh", json={"refresh_token": ref_token_2})
    assert invalidated_res.status_code == 401


def test_admin_refresh_preserves_absolute_session_timeout(client):
    login_res = client.post("/admin/login", json={"email": "admin@example.com", "password": "Admin12345"})
    assert login_res.status_code == 200
    refresh_token = login_res.json()["refresh_token"]

    import database
    from models.refresh_token import RefreshToken

    db = database.SessionLocal()
    record = db.query(RefreshToken).filter(RefreshToken.token_hash.is_not(None)).first()
    assert record is not None
    from datetime import timedelta
    from time_utils import utc_now
    record.created_at = utc_now() - timedelta(hours=5)
    db.commit()
    db.close()

    refresh_res = client.post("/auth/refresh", json={"refresh_token": refresh_token})
    assert refresh_res.status_code == 401
    assert "absolute timeout" in refresh_res.json()["detail"].lower()


def test_logout_invalidates_refresh_token_and_cookies(client):
    login_res = client.post("/admin/login", json={"email": "admin@example.com", "password": "Admin12345"})
    assert login_res.status_code == 200
    ref_token = login_res.json()["refresh_token"]

    # Verify cookies were set
    assert "gasq_admin_access" in login_res.cookies or "gasq_csrf" in login_res.cookies

    # Logout
    logout_res = client.post("/auth/logout", json={"refresh_token": ref_token})
    assert logout_res.status_code == 200
    assert logout_res.json()["message"] == "Logged out successfully"

    # Refresh should now fail
    ref_fail = client.post("/auth/refresh", json={"refresh_token": ref_token})
    assert ref_fail.status_code == 401


def test_rfc6238_totp_2fa_generation_and_verification():
    secret = generate_totp_secret()
    assert len(secret) >= 16

    current_code = generate_current_totp(secret)
    assert len(current_code) == 6
    assert current_code.isdigit()

    assert verify_totp(secret, current_code) is True
    assert verify_totp(secret, "000000" if current_code != "000000" else "111111") is False

    uri = build_totp_provisioning_uri(secret, "admin@example.com")
    assert "otpauth://totp/" in uri
    assert secret in uri


def test_security_headers_present_on_responses(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.headers["X-Frame-Options"] == "DENY"
    assert res.headers["X-Content-Type-Options"] == "nosniff"
    assert "Content-Security-Policy" in res.headers
    assert res.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"


def test_reauth_password_on_sensitive_admin_actions(client):
    login_res = client.post("/admin/login", json={"email": "admin@example.com", "password": "Admin12345"})
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Wrong confirmation password in header
    fail_res = client.post(
        "/admin/dealers/1/suspend",
        headers={**headers, "X-Admin-Password": "WrongAdminPassword!"},
    )
    assert fail_res.status_code == 401
    assert "Invalid confirmation password" in fail_res.json()["detail"]

    # Valid confirmation password in header
    ok_res = client.post(
        "/admin/dealers/1/suspend",
        headers={**headers, "X-Admin-Password": "Admin12345"},
    )
    assert ok_res.status_code == 200
    assert ok_res.json()["status"] == "SUSPENDED"
