import secrets

from fastapi import Header, HTTPException, Request

from app.config import settings


def _token_matches(provided: str | None, expected: str) -> bool:
    supplied = (provided or "").strip()
    if not supplied or len(supplied) != len(expected):
        return False
    return secrets.compare_digest(supplied, expected)


def require_admin_token(x_admin_token: str | None = Header(default=None)) -> None:
    """Mutating routes require a configured ADMIN_API_KEY and matching header."""
    expected = (settings.admin_api_key or "").strip()
    if not expected:
        raise HTTPException(
            status_code=503,
            detail=(
                "ADMIN_API_KEY is required for mutating routes. "
                "Set it in the service environment and restart the API."
            ),
        )
    if not _token_matches(x_admin_token, expected):
        raise HTTPException(
            status_code=403,
            detail="Missing or invalid admin token.",
        )


def require_ingest_operator_token(x_ingest_token: str | None = Header(default=None)) -> None:
    token = (settings.ingest_operator_token or "").strip()
    if not token:
        if (settings.ingest_s3_bucket or "").strip():
            raise HTTPException(
                status_code=503,
                detail=(
                    "INGEST_OPERATOR_TOKEN is required when S3 ingest is enabled. "
                    "Set it in the service environment and restart the API."
                ),
            )
        return
    if not _token_matches(x_ingest_token, token):
        raise HTTPException(
            status_code=403,
            detail="Missing or invalid ingest operator token.",
        )


def require_consumer_secret(
    x_rekognition_consumer_secret: str | None = Header(default=None),
) -> None:
    """Protect the SQS consumer endpoint. Unlike the optional admin token, this REQUIRES the
    secret to be configured — a cost/AWS-touching endpoint must never be publicly callable."""
    expected = (settings.rekognition_consumer_secret or "").strip()
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="REKOGNITION_CONSUMER_SECRET is not configured on the server.",
        )
    if not _token_matches(x_rekognition_consumer_secret, expected):
        raise HTTPException(
            status_code=403, detail="Missing or invalid consumer secret."
        )


def require_db(request: Request) -> None:
    if not getattr(request.app.state, "db_ready", False):
        raise HTTPException(
            status_code=503,
            detail=(
                "Database not configured. On Render, set DATABASE_URL to your "
                "Neon PostgreSQL URL (Dashboard → Environment)."
            ),
        )
