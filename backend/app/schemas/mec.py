from pydantic import BaseModel, Field


class MecGenerateResponse(BaseModel):
    title_id: int
    filename: str
    storage_uri: str
    content_type: str = "application/xml"
    xml: str = Field(description="UTF-8 MEC XML document for browser download")
