"""
GasQ RFC 6238 TOTP (Time-Based One-Time Password) Service.
Standard zero-dependency implementation compatible with Google Authenticator,
Microsoft Authenticator, and 1Password.
"""

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote


def generate_totp_secret(length: int = 32) -> str:
    """Generate a random base32 encoded secret key."""
    raw_bytes = secrets.token_bytes((length * 5) // 8)
    return base64.b32encode(raw_bytes).decode("ascii").rstrip("=")


def _generate_totp_code_at(secret: str, counter: int, digits: int = 6) -> str:
    """Compute the HMAC-SHA1 TOTP code for a specific counter step."""
    # Base32 decode with proper padding
    clean_secret = secret.strip().upper()
    padded_secret = clean_secret + "=" * (-len(clean_secret) % 8)
    key = base64.b32decode(padded_secret.encode("ascii"))

    # Counter packed as 8-byte big-endian unsigned integer
    msg = struct.pack(">Q", counter)
    digest = hmac.new(key, msg, hashlib.sha1).digest()

    # Dynamic truncation
    offset = digest[-1] & 0x0F
    code_int = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    code = code_int % (10**digits)
    return str(code).zfill(digits)


def generate_current_totp(secret: str, interval: int = 30, digits: int = 6) -> str:
    """Generate the current valid TOTP code for the secret."""
    counter = int(time.time() // interval)
    return _generate_totp_code_at(secret, counter, digits)


def verify_totp(
    secret: str,
    code: str,
    window: int = 1,
    interval: int = 30,
    digits: int = 6,
) -> bool:
    """
    Verify a user-supplied TOTP code.
    Allows a time window of +/- 1 interval (default 30 seconds drift tolerance).
    Uses constant-time comparison to prevent timing side channels.
    """
    if not secret or not code:
        return False

    clean_code = str(code).strip()
    if len(clean_code) != digits or not clean_code.isdigit():
        return False

    current_counter = int(time.time() // interval)

    for offset in range(-window, window + 1):
        expected_code = _generate_totp_code_at(secret, current_counter + offset, digits)
        if hmac.compare_digest(expected_code, clean_code):
            return True

    return False


def build_totp_provisioning_uri(
    secret: str,
    account_name: str,
    issuer: str = "GasQ LPG",
) -> str:
    """Build otpauth:// URI for scanning with Google Authenticator or authenticator apps."""
    clean_account = quote(account_name)
    clean_issuer = quote(issuer)
    clean_secret = secret.strip().upper()
    return f"otpauth://totp/{clean_issuer}:{clean_account}?secret={clean_secret}&issuer={clean_issuer}&algorithm=SHA1&digits=6&period=30"
