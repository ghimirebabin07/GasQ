import logging
from typing import Any

from config import get_settings
from fastapi import HTTPException, status
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

logger = logging.getLogger("gasq.auth.google")


def verify_google_id_token(token_str: str) -> dict[str, Any]:
    settings = get_settings()
    audience = settings.google_client_id.strip() if settings.google_client_id else None

    try:
        request = google_requests.Request()
        id_info = id_token.verify_oauth2_token(token_str, request, audience)

        if id_info.get("iss") not in ["accounts.google.com", "https://accounts.google.com"]:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid Google token issuer",
            )

        if not id_info.get("email_verified", False):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Google account email is not verified",
            )

        return id_info
    except ValueError as exc:
        logger.warning("Google ID token verification failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid Google ID token: {exc}",
        )


def get_google_verifier():
    return verify_google_id_token
