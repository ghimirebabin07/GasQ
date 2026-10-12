import hashlib
import hmac
import secrets
from datetime import timedelta

from fastapi import HTTPException, status
from models.email_otp import EmailOtp
from sqlalchemy.orm import Session
from time_utils import utc_now

from services.mail_service import get_mail_provider

OTP_VALIDITY_MINUTES = 5
COOLDOWN_SECONDS = 60
HOURLY_LIMIT = 5
MAX_ATTEMPTS = 5
LOCKOUT_MINUTES = 15


def generate_otp_code() -> str:
    # 6-digit random code
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_otp_code(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def send_email_otp(db: Session, email: str) -> str:
    email = email.strip().lower()
    now = utc_now()

    # Check active lockout
    locked_record = (
        db.query(EmailOtp)
        .filter(EmailOtp.email == email, EmailOtp.lockout_until > now)
        .order_by(EmailOtp.lockout_until.desc())
        .first()
    )
    if locked_record and locked_record.lockout_until:
        remaining_seconds = int((locked_record.lockout_until - now).total_seconds())
        remaining_minutes = max(1, (remaining_seconds + 59) // 60)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many failed attempts. Try again in {remaining_minutes} minutes.",
        )

    # Check 60-second cooldown
    cooldown_cutoff = now - timedelta(seconds=COOLDOWN_SECONDS)
    recent_otp = (
        db.query(EmailOtp)
        .filter(EmailOtp.email == email, EmailOtp.created_at >= cooldown_cutoff)
        .first()
    )
    if recent_otp:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Please wait 60 seconds before requesting another code.",
        )

    # Check hourly limit (max 5 per hour)
    hour_cutoff = now - timedelta(hours=1)
    hourly_count = (
        db.query(EmailOtp)
        .filter(EmailOtp.email == email, EmailOtp.created_at >= hour_cutoff)
        .count()
    )
    if hourly_count >= HOURLY_LIMIT:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Maximum OTP requests reached for this hour. Please try again later.",
        )

    code = generate_otp_code()
    code_hash = hash_otp_code(code)
    expires_at = now + timedelta(minutes=OTP_VALIDITY_MINUTES)

    otp_record = EmailOtp(
        email=email,
        code_hash=code_hash,
        expires_at=expires_at,
        created_at=now,
    )
    db.add(otp_record)
    db.commit()

    # Send email via provider
    mail_provider = get_mail_provider()
    subject = "Your GasQ Login Code"
    body = (
        f"Hello,\n\n"
        f"Your verification code for GasQ is: {code}\n\n"
        f"This code will expire in {OTP_VALIDITY_MINUTES} minutes. If you did not request this code, please ignore this email.\n\n"
        f"— GasQ Team"
    )
    mail_provider.send_email(to_email=email, subject=subject, body=body)
    return code


def verify_email_otp(db: Session, email: str, code: str) -> bool:
    email = email.strip().lower()
    code = code.strip()
    now = utc_now()

    # Check active lockout
    locked_record = (
        db.query(EmailOtp)
        .filter(EmailOtp.email == email, EmailOtp.lockout_until > now)
        .order_by(EmailOtp.lockout_until.desc())
        .first()
    )
    if locked_record and locked_record.lockout_until:
        remaining_seconds = int((locked_record.lockout_until - now).total_seconds())
        remaining_minutes = max(1, (remaining_seconds + 59) // 60)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many failed attempts. Try again in {remaining_minutes} minutes.",
        )

    # Find the latest unused OTP
    otp_record = (
        db.query(EmailOtp)
        .filter(EmailOtp.email == email, EmailOtp.used.is_(False))
        .order_by(EmailOtp.created_at.desc())
        .first()
    )

    if not otp_record:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active OTP found. Please request a new code.",
        )

    if otp_record.expires_at < now:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OTP code has expired. Please request a new code.",
        )

    input_hash = hash_otp_code(code)
    if not hmac.compare_digest(input_hash, otp_record.code_hash):
        otp_record.attempts += 1
        if otp_record.attempts >= MAX_ATTEMPTS:
            otp_record.lockout_until = now + timedelta(minutes=LOCKOUT_MINUTES)
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Too many failed attempts. Account locked for {LOCKOUT_MINUTES} minutes.",
            )
        db.commit()
        remaining = MAX_ATTEMPTS - otp_record.attempts
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Incorrect code. {remaining} attempt(s) remaining.",
        )

    # Valid!
    otp_record.used = True
    db.commit()
    return True
