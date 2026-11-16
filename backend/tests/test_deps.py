from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.config import settings
from app.deps import require_admin_token
from app.routers import ingest, storage, titles


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


def _requires_admin(route) -> bool:
    return any(
        getattr(dep, "call", None) is require_admin_token
        for dep in route.dependant.dependencies
    )


def test_storage_routes_require_admin_token():
    assert storage.router.routes
    for route in storage.router.routes:
        assert _requires_admin(route), route.path


def test_ingest_routes_require_admin_token():
    assert ingest.router.routes
    for route in ingest.router.routes:
        assert _requires_admin(route), route.path


def test_mec_generate_requires_admin_token():
    route = next(r for r in titles.router.routes if r.path.endswith("/mec/generate"))
    assert _requires_admin(route)
