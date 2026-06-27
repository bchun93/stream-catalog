import re
from datetime import date

from sqlalchemy.orm import Session

from app.models.delivery_package import DeliveryPackage, DeliveryMode, MonetizationModel, PackageStatus
from app.schemas.delivery_package import DeliveryPackageCreate


def _slugify(value: str) -> str:
    slug = value.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")[:120] or "package"


def _unique_slug(db: Session, slug: str) -> str:
    base = slug[:120] or "package"
    candidate = base
    counter = 2
    while db.query(DeliveryPackage).filter(DeliveryPackage.slug == candidate).first():
        suffix = f"-{counter}"
        candidate = f"{base[: 120 - len(suffix)]}{suffix}"
        counter += 1
    return candidate


def suggest_package_name(buyer_slug: str | None, deal_date: date | None) -> str:
    buyer = _slugify(buyer_slug or "buyer")
    when = deal_date.isoformat() if deal_date else date.today().isoformat()
    return f"{buyer}-{when}"


def list_packages(
    db: Session,
    *,
    skip: int = 0,
    limit: int = 100,
) -> list[DeliveryPackage]:
    packages = (
        db.query(DeliveryPackage)
        .order_by(DeliveryPackage.updated_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    for package in packages:
        if package.delivery_mode is None:
            package.delivery_mode = DeliveryMode.VOD
        if package.monetization is None:
            package.monetization = MonetizationModel.SVOD
    return packages


def create_package(db: Session, payload: DeliveryPackageCreate) -> DeliveryPackage:
    name = payload.name.strip()
    if not name:
        raise ValueError("Package name is required")
    buyer_slug = payload.buyer_slug.strip() if payload.buyer_slug else None
    if buyer_slug:
        buyer_slug = _slugify(buyer_slug)
    slug = _unique_slug(db, _slugify(name))
    package = DeliveryPackage(
        name=name,
        slug=slug,
        buyer_slug=buyer_slug,
        deal_date=payload.deal_date,
        delivery_mode=payload.delivery_mode or DeliveryMode.VOD,
        monetization=payload.monetization or MonetizationModel.SVOD,
        status=PackageStatus.DRAFT,
    )
    db.add(package)
    db.commit()
    db.refresh(package)
    return package
