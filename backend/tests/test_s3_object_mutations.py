from unittest.mock import patch

import pytest
from botocore.exceptions import ClientError

from app.services import s3_service


class FakeS3Client:
    def __init__(self, keys: set[str], *, size: int = 1):
        self.objects = {
            key: {"ETag": f'"etag-{index}"', "ContentLength": size, "Metadata": {}}
            for index, key in enumerate(sorted(keys), start=1)
        }
        self.copy_parts: list[tuple[str, str, str]] = []
        self.deletes: list[str] = []
        self.aborts: list[str] = []
        self.pending_destination: str | None = None
        self.pending_metadata: dict[str, str] = {}

    def head_object(self, *, Bucket: str, Key: str):
        if Key not in self.objects:
            raise ClientError(
                {"Error": {"Code": "404", "Message": "Not Found"}},
                "HeadObject",
            )
        return self.objects[Key]

    def create_multipart_upload(self, **kwargs):
        self.pending_destination = kwargs["Key"]
        self.pending_metadata = kwargs.get("Metadata", {})
        return {"UploadId": "upload-1"}

    def upload_part_copy(self, **kwargs):
        self.copy_parts.append(
            (
                kwargs["CopySource"]["Key"],
                kwargs["Key"],
                kwargs["CopySourceRange"],
            )
        )
        return {"CopyPartResult": {"ETag": f'"part-{kwargs["PartNumber"]}"'}}

    def complete_multipart_upload(self, **kwargs):
        assert kwargs["IfNoneMatch"] == "*"
        if kwargs["Key"] in self.objects:
            raise ClientError(
                {"Error": {"Code": "PreconditionFailed", "Message": "Exists"}},
                "CompleteMultipartUpload",
            )
        self.objects[kwargs["Key"]] = {
            "ETag": '"destination-etag"',
            "ContentLength": 1,
            "Metadata": self.pending_metadata,
        }
        return {"ETag": '"destination-etag"'}

    def abort_multipart_upload(self, **kwargs):
        self.aborts.append(kwargs["Key"])
        return {}

    def put_object(self, **kwargs):
        assert kwargs["IfNoneMatch"] == "*"
        self.objects[kwargs["Key"]] = {
            "ETag": '"empty-etag"',
            "ContentLength": 0,
            "Metadata": kwargs.get("Metadata", {}),
        }
        return {"ETag": '"empty-etag"'}

    def delete_object(self, *, Bucket: str, Key: str, IfMatch: str | None = None):
        if IfMatch and self.objects[Key]["ETag"] != IfMatch:
            raise ClientError(
                {"Error": {"Code": "PreconditionFailed", "Message": "Changed"}},
                "DeleteObject",
            )
        self.deletes.append(Key)
        self.objects.pop(Key, None)
        return {}


@pytest.fixture
def configured_s3():
    with (
        patch.object(s3_service.settings, "ingest_s3_bucket", "bucket"),
        patch.object(s3_service.settings, "ingest_s3_prefix", "deliveries"),
        patch.object(s3_service.settings, "aspera_drop_prefix", "inbound"),
        patch.object(s3_service.settings, "s3_mutation_secret", "s" * 32),
    ):
        yield


def test_rename_object_copies_then_deletes_in_same_folder(configured_s3):
    source = "deliveries/inbound/original.mov"
    client = FakeS3Client({source})
    etag = client.objects[source]["ETag"]
    with patch.object(s3_service, "s3_client", return_value=client):
        key, uri = s3_service.rename_object(source, "renamed video.mov", etag, 1)

    assert key == "deliveries/inbound/renamed video.mov"
    assert uri == "s3://bucket/deliveries/inbound/renamed video.mov"
    assert client.copy_parts == [(source, key, "bytes=0-0")]
    assert client.deletes == [source]


def test_rename_object_does_not_overwrite_existing_key(configured_s3):
    source = "deliveries/inbound/original.mov"
    destination = "deliveries/inbound/existing.mov"
    client = FakeS3Client({source, destination})
    etag = client.objects[source]["ETag"]
    with (
        patch.object(s3_service, "s3_client", return_value=client),
        pytest.raises(FileExistsError),
    ):
        s3_service.rename_object(source, "existing.mov", etag, 1)

    assert client.copy_parts == []
    assert client.deletes == []


def test_delete_object_removes_existing_key(configured_s3):
    key = "deliveries/inbound/delete-me.mov"
    client = FakeS3Client({key})
    etag = client.objects[key]["ETag"]
    with patch.object(s3_service, "s3_client", return_value=client):
        s3_service.delete_object(key, etag)

    assert client.deletes == [key]


@pytest.mark.parametrize(
    "key",
    [
        "outside/file.mov",
        "/deliveries/inbound/file.mov",
        "deliveries/inbound/file.mov ",
        "deliveries/inbound/../file.mov",
        "deliveries/inbound/folder/",
    ],
)
def test_mutations_reject_keys_outside_managed_files(configured_s3, key):
    with pytest.raises(ValueError):
        s3_service.delete_object(key, '"etag"')


@pytest.mark.parametrize("name", ["", "../file.mov", "folder/file.mov", "bad\x00.mov"])
def test_rename_rejects_invalid_names(configured_s3, name):
    source = "deliveries/inbound/original.mov"
    client = FakeS3Client({source})
    with (
        patch.object(s3_service, "s3_client", return_value=client),
        pytest.raises(ValueError),
    ):
        s3_service.rename_object(source, name, client.objects[source]["ETag"], 1)


def test_delete_rejects_stale_etag(configured_s3):
    key = "deliveries/inbound/changed.mov"
    client = FakeS3Client({key})
    with (
        patch.object(s3_service, "s3_client", return_value=client),
        pytest.raises(s3_service.StaleObjectError),
    ):
        s3_service.delete_object(key, '"old-etag"')
    assert client.deletes == []


def test_large_rename_uses_multiple_server_side_copy_parts(configured_s3):
    source = "deliveries/inbound/large.mov"
    size = s3_service._COPY_PART_SIZE + 1
    client = FakeS3Client({source}, size=size)
    etag = client.objects[source]["ETag"]
    with patch.object(s3_service, "s3_client", return_value=client):
        s3_service.rename_object(source, "renamed.mov", etag, size)

    assert [part[2] for part in client.copy_parts] == [
        f"bytes=0-{s3_service._COPY_PART_SIZE - 1}",
        f"bytes={s3_service._COPY_PART_SIZE}-{size - 1}",
    ]


def test_rename_aborts_when_atomic_destination_check_fails(configured_s3):
    source = "deliveries/inbound/source.mov"
    client = FakeS3Client({source})
    etag = client.objects[source]["ETag"]

    original_complete = client.complete_multipart_upload

    def destination_created_during_copy(**kwargs):
        client.objects[kwargs["Key"]] = {
            "ETag": '"racer"',
            "ContentLength": 1,
            "Metadata": {},
        }
        return original_complete(**kwargs)

    client.complete_multipart_upload = destination_created_during_copy
    with (
        patch.object(s3_service, "s3_client", return_value=client),
        pytest.raises(FileExistsError),
    ):
        s3_service.rename_object(source, "raced.mov", etag, 1)

    assert client.aborts == ["deliveries/inbound/raced.mov"]
    assert source in client.objects


def test_rename_treats_lost_delete_response_as_success(configured_s3):
    source = "deliveries/inbound/source.mov"
    client = FakeS3Client({source})
    etag = client.objects[source]["ETag"]
    original_delete = client.delete_object

    def delete_then_lose_response(**kwargs):
        original_delete(**kwargs)
        raise ClientError(
            {"Error": {"Code": "PreconditionFailed", "Message": "Already deleted"}},
            "DeleteObject",
        )

    client.delete_object = delete_then_lose_response
    with patch.object(s3_service, "s3_client", return_value=client):
        key, _ = s3_service.rename_object(source, "renamed.mov", etag, 1)

    assert key == "deliveries/inbound/renamed.mov"
    assert source not in client.objects
    assert key in client.objects


def test_delete_treats_lost_response_then_precondition_as_success(configured_s3):
    key = "deliveries/inbound/delete-me.mov"
    client = FakeS3Client({key})
    etag = client.objects[key]["ETag"]
    original_delete = client.delete_object

    def delete_then_precondition(**kwargs):
        original_delete(**kwargs)
        raise ClientError(
            {"Error": {"Code": "PreconditionFailed", "Message": "Already deleted"}},
            "DeleteObject",
        )

    client.delete_object = delete_then_precondition
    with patch.object(s3_service, "s3_client", return_value=client):
        s3_service.delete_object(key, etag)

    assert key not in client.objects


def test_delete_treats_lost_transport_response_as_success(configured_s3):
    key = "deliveries/inbound/delete-me.mov"
    client = FakeS3Client({key})
    etag = client.objects[key]["ETag"]
    original_delete = client.delete_object

    def delete_then_disconnect(**kwargs):
        original_delete(**kwargs)
        raise ConnectionError("response lost")

    client.delete_object = delete_then_disconnect
    with patch.object(s3_service, "s3_client", return_value=client):
        s3_service.delete_object(key, etag)

    assert key not in client.objects


def test_rename_retry_reconciles_marked_destination(configured_s3):
    source = "deliveries/inbound/source.mov"
    client = FakeS3Client({source})
    etag = client.objects[source]["ETag"]
    original_delete = client.delete_object
    failures = 1

    def fail_first_delete(**kwargs):
        nonlocal failures
        if failures:
            failures -= 1
            raise ConnectionError("temporary failure")
        return original_delete(**kwargs)

    client.delete_object = fail_first_delete
    with (
        patch.object(s3_service, "s3_client", return_value=client),
        pytest.raises(ConnectionError),
    ):
        s3_service.rename_object(source, "renamed.mov", etag, 1)

    with patch.object(s3_service, "s3_client", return_value=client):
        key, _ = s3_service.rename_object(source, "renamed.mov", etag, 1)

    assert key == "deliveries/inbound/renamed.mov"
    assert source not in client.objects
