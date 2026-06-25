import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.media_asset import AssetStatus, AssetType, MediaAsset
from app.models.title import Title, TitleStatus, TitleType
from app.services.artwork_service import (
    clear_all_artwork_assets,
    delete_artwork_asset,
    list_artwork_assets,
    save_artwork_selection,
)
from app.schemas.artwork import ArtworkItem


class ArtworkServiceTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=engine)
        SessionLocal = sessionmaker(bind=engine)
        self.db = SessionLocal()
        self.title = Title(
            slug="gladiator",
            name="Gladiator",
            title_type=TitleType.MOVIE,
            status=TitleStatus.DRAFT,
            poster_url="https://image.tmdb.org/t/p/w500/poster.jpg",
        )
        self.db.add(self.title)
        self.db.commit()
        self.db.refresh(self.title)

    def tearDown(self):
        self.db.close()

    def _add_poster(self, uri: str) -> MediaAsset:
        asset = MediaAsset(
            title_id=self.title.id,
            asset_type=AssetType.POSTER,
            status=AssetStatus.READY,
            filename="poster.jpg",
            mime_type="image/jpeg",
            storage_uri=uri,
        )
        self.db.add(asset)
        self.db.commit()
        self.db.refresh(asset)
        return asset

    def test_delete_artwork_asset_removes_row(self):
        asset = self._add_poster("https://image.tmdb.org/t/p/w500/cast.jpg")
        delete_artwork_asset(self.db, self.title.id, asset.id)
        self.assertEqual(list_artwork_assets(self.db, self.title.id), [])

    def test_delete_artwork_asset_updates_title_poster_when_removed(self):
        poster = self._add_poster("https://image.tmdb.org/t/p/w500/poster.jpg")
        cast = self._add_poster("https://image.tmdb.org/t/p/w185/cast.jpg")
        self.title.poster_url = cast.storage_uri
        self.db.commit()

        delete_artwork_asset(self.db, self.title.id, cast.id)

        self.db.refresh(self.title)
        self.assertEqual(self.title.poster_url, poster.storage_uri)
        remaining = list_artwork_assets(self.db, self.title.id)
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0].id, poster.id)

    def test_clear_all_artwork_assets_removes_everything(self):
        self._add_poster("https://image.tmdb.org/t/p/w500/poster.jpg")
        self._add_poster("https://image.tmdb.org/t/p/w185/cast.jpg")
        self.title.poster_url = "https://image.tmdb.org/t/p/w185/cast.jpg"
        self.db.commit()

        removed = clear_all_artwork_assets(self.db, self.title.id)

        self.assertEqual(removed, 2)
        self.assertEqual(list_artwork_assets(self.db, self.title.id), [])
        self.db.refresh(self.title)
        self.assertIsNone(self.title.poster_url)

    def test_save_artwork_selection_skips_existing_uri(self):
        item = ArtworkItem(
            asset_type=AssetType.POSTER,
            storage_uri="https://image.tmdb.org/t/p/w500/new.jpg",
            filename="new.jpg",
            mime_type="image/jpeg",
        )
        saved = save_artwork_selection(self.db, self.title.id, [item])
        self.assertEqual(len(saved), 1)
        again = save_artwork_selection(self.db, self.title.id, [item])
        self.assertEqual(len(again), 1)


if __name__ == "__main__":
    unittest.main()
