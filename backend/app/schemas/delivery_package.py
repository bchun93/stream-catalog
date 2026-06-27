from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.delivery_package import DeliveryMode, MonetizationModel, PackageStatus


class DeliveryPackageBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    buyer_slug: str | None = Field(default=None, max_length=120)
    deal_date: date | None = None
    delivery_mode: DeliveryMode = DeliveryMode.VOD
    monetization: MonetizationModel = MonetizationModel.SVOD
    status: PackageStatus = PackageStatus.DRAFT

    @field_validator("delivery_mode", mode="before")
    @classmethod
    def default_delivery_mode(cls, value: object) -> DeliveryMode:
        if value is None or value == "":
            return DeliveryMode.VOD
        if isinstance(value, DeliveryMode):
            return value
        return DeliveryMode(str(value).lower())

    @field_validator("monetization", mode="before")
    @classmethod
    def default_monetization(cls, value: object) -> MonetizationModel:
        if value is None or value == "":
            return MonetizationModel.SVOD
        if isinstance(value, MonetizationModel):
            return value
        return MonetizationModel(str(value).lower())


class DeliveryPackageCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    buyer_slug: str | None = Field(default=None, max_length=120)
    deal_date: date | None = None
    delivery_mode: DeliveryMode = DeliveryMode.VOD
    monetization: MonetizationModel = MonetizationModel.SVOD


class DeliveryPackageRead(DeliveryPackageBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    created_at: datetime
    updated_at: datetime
