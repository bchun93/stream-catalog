from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.config import settings
from app.deps import require_admin_token, require_ingest_operator_token


def test_admin_token_fails_closed_when_not_configured():
    with patch.object(settings, "admin_api_key", None):
        with pytest.raises(HTTPException) as exc:
            require_admin_token(None)
    assert exc.value.status_code == 503


def test_admin_token_requires_matching_header():
    with patch.object(settings, "admin_api_key", "admin-secret"):
        with pytest.raises(HTTPException) as exc:
            require_admin_token("wrong")
        assert exc.value.status_code == 403
        require_admin_token("admin-secret")


def test_ingest_token_fails_closed_when_s3_is_enabled():
    with (
        patch.object(settings, "ingest_operator_token", None),
        patch.object(settings, "ingest_s3_bucket", "ingest-bucket"),
    ):
        with pytest.raises(HTTPException) as exc:
            require_ingest_operator_token(None)
    assert exc.value.status_code == 503


def test_ingest_token_may_be_unset_when_s3_is_disabled():
    with (
        patch.object(settings, "ingest_operator_token", None),
        patch.object(settings, "ingest_s3_bucket", None),
    ):
        require_ingest_operator_token(None)


def test_ingest_token_requires_matching_header():
    with patch.object(settings, "ingest_operator_token", "ingest-secret"):
        with pytest.raises(HTTPException) as exc:
            require_ingest_operator_token("wrong")
        assert exc.value.status_code == 403
        require_ingest_operator_token("ingest-secret")
