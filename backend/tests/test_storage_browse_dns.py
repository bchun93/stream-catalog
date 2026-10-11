from unittest.mock import patch

import pytest
from botocore.exceptions import EndpointConnectionError
from fastapi import HTTPException

from app.routers.storage import browse_storage
from app.services.s3_service import _refresh_darwin_resolver


def test_refresh_darwin_resolver_does_not_raise():
    _refresh_darwin_resolver()


def test_browse_storage_maps_endpoint_connection_error_to_503():
    with patch(
        "app.routers.storage.s3_service.browse_objects",
        side_effect=EndpointConnectionError(endpoint_url="https://s3.amazonaws.com"),
    ):
        with pytest.raises(HTTPException) as exc:
            browse_storage(prefix="", max_keys=500)

    assert exc.value.status_code == 503
    assert (
        "S3 is unreachable from this API process (DNS or network). "
        "Restart the backend after sleep, VPN, or Wi-Fi changes."
    ) == exc.value.detail
