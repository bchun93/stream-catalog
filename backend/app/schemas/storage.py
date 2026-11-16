from datetime import datetime

from pydantic import BaseModel, Field


class StorageConfigRead(BaseModel):
    bucket: str
    root_prefix: str


class StorageFolderRead(BaseModel):
    name: str
    prefix: str


class StorageObjectRead(BaseModel):
    key: str
    name: str
    size_bytes: int | None = None
    last_modified: datetime | None = None
    etag: str
    storage_uri: str


class StorageBrowseRead(BaseModel):
    bucket: str
    root_prefix: str
    prefix: str
    folders: list[StorageFolderRead]
    objects: list[StorageObjectRead]
    truncated: bool


class StoragePresignUploadRequest(BaseModel):
    prefix: str = ""
    filename: str = Field(min_length=1)
    content_type: str | None = None


class StoragePresignUploadRead(BaseModel):
    key: str
    storage_uri: str
    upload_url: str
    method: str
    headers: dict[str, str]


class StoragePresignDownloadRead(BaseModel):
    download_url: str
    key: str
    storage_uri: str


class StorageObjectRenameRequest(BaseModel):
    key: str = Field(min_length=1)
    new_name: str = Field(min_length=1, max_length=255)
    expected_etag: str = Field(min_length=1)
    expected_size: int = Field(ge=0)


class StorageObjectMutationRead(BaseModel):
    key: str
    storage_uri: str
