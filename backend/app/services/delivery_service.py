import re
from datetime import date

from sqlalchemy.orm import Session, joinedload

from app.models.delivery_package import DeliveryPackage, DeliveryMode, MonetizationModel, PackageStatus
from app.models.delivery_package_title import DeliveryPackageTitle
from app.models.delivery_profile import DeliveryProfile
from app.models.title import Title, TitleType
from app.schemas.delivery_package import (
    DeliveryPackageCreate,
    DeliveryPackageRead,
    DeliveryPackageTitleSummary,
)
from app.schemas.delivery_profile import DeliveryProfileSummary
from app.services import delivery_profile_service

_PACKAGE_TITLE_TYPES = {TitleType.MOVIE, TitleType.SERIES}


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


def _normalize_package_enums(package: DeliveryPackage) -> None:
    if package.delivery_mode is None:
        package.delivery_mode = DeliveryMode.VOD
    if package.monetization is None:
        package.monetization = MonetizationModel.SVOD


def _title_summaries(package: DeliveryPackage) -> list[DeliveryPackageTitleSummary]:
    summaries: list[DeliveryPackageTitleSummary] = []
    for link in package.package_titles:
        if not link.title:
            continue
        summaries.append(
            DeliveryPackageTitleSummary(
                id=link.title.id,
                name=link.title.name,
                title_type=link.title.title_type,
            )
        )
    summaries.sort(key=lambda item: item.name.lower())
    return summaries


def package_to_read(package: DeliveryPackage) -> DeliveryPackageRead:
    _normalize_package_enums(package)
    titles = _title_summaries(package)
    profile_summary = None
    if package.profile is not None:
        profile_summary = DeliveryProfileSummary.model_validate(package.profile)
    read = DeliveryPackageRead.model_validate(package)
    return read.model_copy(
        update={
            "titles": titles,
            "title_count": len(titles),
            "profile": profile_summary,
            "profile_id": package.profile_id,
        }
    )


def _package_load_options():
    return (
        joinedload(DeliveryPackage.profile),
        joinedload(DeliveryPackage.package_titles).joinedload(DeliveryPackageTitle.title),
    )


def list_packages(
    db: Session,
    *,
    skip: int = 0,
    limit: int = 100,
) -> list[DeliveryPackageRead]:
    packages = (
        db.query(DeliveryPackage)
        .options(*_package_load_options())
        .order_by(DeliveryPackage.updated_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return [package_to_read(package) for package in packages]


def get_package(db: Session, package_id: int) -> DeliveryPackageRead | None:
    package = (
        db.query(DeliveryPackage)
        .options(*_package_load_options())
        .filter(DeliveryPackage.id == package_id)
        .first()
    )
    if not package:
        return None
    return package_to_read(package)


def create_package(db: Session, payload: DeliveryPackageCreate) -> DeliveryPackageRead:
    name = payload.name.strip()
    if not name:
        raise ValueError("Package name is required")

    profile = db.query(DeliveryProfile).filter(DeliveryProfile.id == payload.profile_id).first()
    if not profile:
        raise ValueError(f"Unknown delivery profile id: {payload.profile_id}")
    if not profile.enabled:
        raise ValueError(f"Delivery profile '{profile.slug}' is disabled")

    buyer_slug = payload.buyer_slug.strip() if payload.buyer_slug else None
    if buyer_slug:
        buyer_slug = _slugify(buyer_slug)
    slug = _unique_slug(db, _slugify(name))

    monetization = payload.monetization
    if monetization is None:
        monetization = delivery_profile_service.channel_to_monetization(profile.channel)

    package = DeliveryPackage(
        name=name,
        slug=slug,
        buyer_slug=buyer_slug,
        deal_date=payload.deal_date,
        delivery_mode=payload.delivery_mode or DeliveryMode.VOD,
        monetization=monetization,
        status=PackageStatus.DRAFT,
        profile_id=profile.id,
    )
    db.add(package)
    db.flush()

    title_ids = list(dict.fromkeys(payload.title_ids))
    if title_ids:
        titles = db.query(Title).filter(Title.id.in_(title_ids)).all()
        found_ids = {title.id for title in titles}
        missing = [title_id for title_id in title_ids if title_id not in found_ids]
        if missing:
            db.rollback()
            raise ValueError(f"Unknown title id(s): {', '.join(str(i) for i in missing)}")
        invalid = [
            title.id
            for title in titles
            if title.title_type not in _PACKAGE_TITLE_TYPES
        ]
        if invalid:
            db.rollback()
            raise ValueError(
                "Only movie and series titles can be added to a package "
                f"(invalid id(s): {', '.join(str(i) for i in invalid)})"
            )
        for title_id in title_ids:
            db.add(DeliveryPackageTitle(package_id=package.id, title_id=title_id))

    db.commit()
    db.refresh(package)
    package = (
        db.query(DeliveryPackage)
        .options(*_package_load_options())
        .filter(DeliveryPackage.id == package.id)
        .first()
    )
    if not package:
        raise ValueError("Package could not be loaded after create")
    return package_to_read(package)
