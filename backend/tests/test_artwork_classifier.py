import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.artwork_ai import ArtworkRole, ArtworkTrainingDecision
from app.models.media_asset import AssetType
from app.models.title import Title, TitleStatus, TitleType
from app.schemas.artwork import ArtworkItem, ArtworkSpecs
from app.schemas.artwork_ai import ArtworkLabelRequest
from app.services import artwork_classifier


class ArtworkClassifierTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=engine)
        self.SessionLocal = sessionmaker(bind=engine)
        self.db = self.SessionLocal()
        self.title = Title(
            slug="test-title",
            name="Test Title",
            title_type=TitleType.SERIES,
            status=TitleStatus.DRAFT,
        )
        self.db.add(self.title)
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def _backdrop(self, path: str = "hero.jpg") -> ArtworkItem:
        return ArtworkItem(
            asset_type=AssetType.BACKDROP,
            storage_uri=f"https://image.tmdb.org/t/p/w780/{path}",
            filename=path,
            mime_type="image/jpeg",
            specs=ArtworkSpecs(
                width=1920,
                height=1080,
                aspect_ratio=1.778,
                aspect_ratio_label="16:9",
            ),
        )

    def test_baseline_classifies_backdrop_as_hero_image(self):
        predictions = artwork_classifier.classify_candidates(
            self.db, self.title, [self._backdrop()], persist=False
        )

        self.assertEqual(len(predictions), 1)
        self.assertEqual(predictions[0].predicted_role, ArtworkRole.HERO_IMAGE)
        self.assertGreater(predictions[0].confidence, 0.7)

    def test_recorded_label_influences_similar_future_candidates(self):
        artwork_classifier.record_label(
            self.db,
            ArtworkLabelRequest(
                title_id=self.title.id,
                item=self._backdrop("horizontal.jpg"),
                assigned_role=ArtworkRole.HORIZONTAL_POSTER,
                decision=ArtworkTrainingDecision.CORRECTED,
            ),
        )

        predictions = artwork_classifier.classify_candidates(
            self.db, self.title, [self._backdrop("similar.jpg")], persist=False
        )

        self.assertEqual(predictions[0].predicted_role, ArtworkRole.HORIZONTAL_POSTER)
        self.assertIn("learned", predictions[0].rationale or "")


if __name__ == "__main__":
    unittest.main()
