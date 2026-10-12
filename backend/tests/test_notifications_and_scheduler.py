import sys
from datetime import timedelta


def get_test_db():
    return sys.modules["database"].SessionLocal()


def get_models():
    return sys.modules["models"]


def get_scheduler():
    import importlib
    return importlib.import_module("workers.scheduler")


def get_time_utils():
    import importlib
    return importlib.import_module("time_utils")


def test_no_show_expiry_releases_stock_and_creates_notification(client):
    db = get_test_db()
    models = get_models()
    scheduler = get_scheduler()
    time_utils = get_time_utils()

    dealer = db.query(models.Dealer).filter(models.Dealer.name == "ABC LPG Dealer").first()
    dealer.available_cylinders = 10
    db.commit()

    # Create customer with valid foreign key
    cust = models.Customer(name="NoShow User", phone="9899999999")
    db.add(cust)
    db.commit()
    db.refresh(cust)

    # Create a called token with called_at in the past (> 15 minutes ago)
    token = models.Token(
        dealer_id=dealer.id,
        customer_id=cust.id,
        customer_phone=cust.phone,
        token_number=999,
        status=models.TokenStatus.CALLED,
        called_at=time_utils.utc_now() - timedelta(minutes=20),
    )
    db.add(token)
    db.commit()
    db.refresh(token)

    # Run background job
    expired_count = scheduler.expire_no_show_tokens(db, expiry_minutes=15)
    assert expired_count >= 1

    # Verify status changed and stock released
    db.refresh(token)
    db.refresh(dealer)
    assert token.status == models.TokenStatus.NO_SHOW
    assert dealer.available_cylinders == 11

    # Verify notification created for customer
    notif = (
        db.query(models.Notification)
        .filter(models.Notification.related_token_id == token.id, models.Notification.notification_type == "TOKEN_EXPIRED")
        .first()
    )
    assert notif is not None
    assert "expired" in notif.message.lower()
    db.close()


def test_position_reminder_triggered_at_three_ahead(client):
    db = get_test_db()
    models = get_models()
    scheduler = get_scheduler()

    dealer = db.query(models.Dealer).filter(models.Dealer.name == "ABC LPG Dealer").first()

    # Clean existing tokens for this dealer for clean count
    db.query(models.Token).filter(models.Token.dealer_id == dealer.id).delete()
    db.commit()

    # Create customer 4 with valid foreign key
    cust4 = models.Customer(name="User Four", phone="9844444444")
    db.add(cust4)
    db.commit()
    db.refresh(cust4)

    # Add 4 waiting tokens with 4 distinct customers (token numbers 101, 102, 103, 104)
    # Token 104 has 3 people ahead (101, 102, 103)
    t1 = models.Token(dealer_id=dealer.id, customer_id=1, customer_phone="9811111111", token_number=101, status=models.TokenStatus.WAITING)
    t2 = models.Token(dealer_id=dealer.id, customer_id=2, customer_phone="9822222222", token_number=102, status=models.TokenStatus.WAITING)
    t3 = models.Token(dealer_id=dealer.id, customer_id=3, customer_phone="9833333333", token_number=103, status=models.TokenStatus.WAITING)
    t4 = models.Token(dealer_id=dealer.id, customer_id=cust4.id, customer_phone=cust4.phone, token_number=104, status=models.TokenStatus.WAITING)
    db.add_all([t1, t2, t3, t4])
    db.commit()

    # Run check
    sent = scheduler.check_and_send_position_reminders(db)
    assert sent == 1

    # Verify notification for customer 4
    notif = (
        db.query(models.Notification)
        .filter(models.Notification.user_id == str(cust4.id), models.Notification.notification_type == "QUEUE_REMINDER")
        .first()
    )
    assert notif is not None
    assert "3rd in line" in notif.message

    # Running a second time is idempotent (no duplicate notification)
    sent_second = scheduler.check_and_send_position_reminders(db)
    assert sent_second == 0
    db.close()


def test_notification_unread_count_and_mark_as_read(client):
    # Register customer
    reg_resp = client.post(
        "/customer/register",
        json={"name": "Notif User", "phone": "9844556677", "password": "Password123"},
    )
    assert reg_resp.status_code == 201
    token = reg_resp.json()["access_token"]
    customer_id = reg_resp.json()["customer"]["id"]

    # Insert a test notification for this customer into the test database
    db = get_test_db()
    models = get_models()
    notif = models.Notification(
        user_type="customer",
        user_id=str(customer_id),
        notification_type="CALL",
        title="Token Called",
        message="Please proceed to counter",
    )
    db.add(notif)
    db.commit()
    db.refresh(notif)
    notif_id = notif.id
    db.close()

    # Check unread count
    count_resp = client.get("/customer/notifications/unread-count", headers={"Authorization": f"Bearer {token}"})
    assert count_resp.status_code == 200
    assert count_resp.json()["unread_count"] == 1

    # Mark as read
    read_resp = client.post(f"/customer/notifications/{notif_id}/read", headers={"Authorization": f"Bearer {token}"})
    assert read_resp.status_code == 200
    assert read_resp.json()["status"] == "ok"

    # Check unread count again
    count_resp2 = client.get("/customer/notifications/unread-count", headers={"Authorization": f"Bearer {token}"})
    assert count_resp2.status_code == 200
    assert count_resp2.json()["unread_count"] == 0
