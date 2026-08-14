"""Title delete must clear Neon FK dependents (artwork AI, assets, packages)."""

from __future__ import annotations

import unittest

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.artwork_ai import ArtworkClassification, ArtworkRole, ArtworkTrainingExample
from app.models.delivery_package import (
    DeliveryMode,
    DeliveryPackage,
    MonetizationModel,
    PackageStatus,
)
from app.models.delivery_package_title import DeliveryPackageTitle
from app.models.delivery_profile import DeliveryProfile
from app.models.media_asset import AssetStatus, AssetType, MediaAsset
from app.models.title import Title, TitleStatus, TitleType
from app.services import title_service


class DeleteTitleFkTests(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine("sqlite:///:memory:")

        @event.listens_for(engine, "connect")
        def _fk(dbapi_conn, _) -> None:  # noqa: ANN001
            dbapi_conn.execute("PRAGMA foreign_keys=ON")

        Base.metadata.create_all(bind=engine)
        self.Session = sessionmaker(bind=engine)
        self.db = self.Session()

    def tearDown(self) -> None:
        self.db.close()

    def test_delete_clears_artwork_ai_and_assets(self) -> None:
        title = Title(
            slug="gladiator",
            name="Gladiator",
            title_type=TitleType.MOVIE,
            status=TitleStatus.DRAFT,
        )
        self.db.add(title)
        self.db.commit()
        self.db.refresh(title)

        self.db.add(
            MediaAsset(
                title_id=title.id,
                asset_type=AssetType.POSTER,
                status=AssetStatus.READY,
                filename="p.jpg",
                storage_uri="https://example.com/p.jpg",
            )
        )
        self.db.add(
            ArtworkClassification(
                title_id=title.id,
                candidate_uri="https://example.com/p.jpg",
                predicted_role=ArtworkRole.VERTICAL_POSTER,
                confidence=0.9,
            )
        )
        self.db.add(
            ArtworkTrainingExample(
                title_id=title.id,
                candidate_uri="https://example.com/p.jpg",
                assigned_role=ArtworkRole.VERTICAL_POSTER,
            )
        )
        self.db.commit()

        title_service.delete_title(self.db, title)

        self.assertEqual(self.db.query(Title).count(), 0)
        self.assertEqual(self.db.query(MediaAsset).count(), 0)
        self.assertEqual(self.db.query(ArtworkClassification).count(), 0)
        self.assertEqual(self.db.query(ArtworkTrainingExample).count(), 0)

    def test_delete_clears_package_title_links(self) -> None:
        profile = DeliveryProfile(
            slug="test-profile",
            name="Test",
            platform="test",
            channel="svod",
            version=1,
            spec_json="{}",
        )
        self.db.add(profile)
        self.db.commit()
        self.db.refresh(profile)

        title = Title(
            slug="gladiator",
            name="Gladiator",
            title_type=TitleType.MOVIE,
            status=TitleStatus.DRAFT,
        )
        self.db.add(title)
        self.db.commit()
        self.db.refresh(title)

        package = DeliveryPackage(
            name="Pkg",
            slug="pkg",
            buyer_slug="buyer",
            status=PackageStatus.DRAFT,
            delivery_mode=DeliveryMode.VOD,
            monetization=MonetizationModel.SVOD,
            profile_id=profile.id,
        )
        self.db.add(package)
        self.db.commit()
        self.db.refresh(package)
        self.db.add(DeliveryPackageTitle(package_id=package.id, title_id=title.id))
        self.db.commit()

        title_service.delete_title(self.db, title)

        self.assertEqual(self.db.query(Title).count(), 0)
        self.assertEqual(self.db.query(DeliveryPackageTitle).count(), 0)
        self.assertEqual(self.db.query(DeliveryPackage).count(), 1)


if __name__ == "__main__":
    unittest.main()
