from pydantic import BaseModel, Field


class MecGenerateResponse(BaseModel):
    title_id: int
    filename: str
    storage_uri: str | None = Field(
        default=None,
        description="s3:// URI when stored in the ingest bucket; null if download-only",
    )
    content_type: str = "application/xml"
    xml: str = Field(description="UTF-8 MEC XML document for browser download")
    stored: bool = Field(
        default=True,
        description="True when the XML was written to the ingest S3 bucket",
    )
    warning: str | None = Field(
        default=None,
        description="Non-fatal note (e.g. S3 not configured — XML still returned for download)",
    )
