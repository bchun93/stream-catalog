import json
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.ingest_manifest import IngestManifest
from app.models.title import Title, TitleStatus, TitleType
from app.schemas.ingest import IngestJobCreateRequest, IngestManifestValidateRequest
from app.services import ingest_service


class _FakeBody:
    def __init__(self, content: bytes):
        self._content = content

    def read(self):
        return self._content


class _FakeS3Client:
    def __init__(self):
        self._objects = {
            "deliveries/drop/master_1920x1080.mp4": b"",
            "deliveries/drop/master_1920x1080.mp4.mediainfo.json": json.dumps(
                {
                    "media": {
                        "track": [
                            {"@type": "Video", "Format": "AVC", "Duration": "6000", "Width": 1920, "Height": 1080}
                        ]
                    }
                }
            ).encode("utf-8"),
            "deliveries/drop/captions_en.srt": b"",
        }

    def list_objects_v2(self, Bucket, Prefix, MaxKeys, ContinuationToken=None):
        keys = [k for k in self._objects if k.startswith(Prefix)]
        keys = keys[:MaxKeys]
        return {
            "Contents": [{"Key": key, "Size": len(self._objects[key])} for key in keys],
            "IsTruncated": False,
        }

    def get_object(self, Bucket, Key):
        return {"Body": _FakeBody(self._objects[Key])}


class IngestServiceTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=engine)
        self.SessionLocal = sessionmaker(bind=engine)
        self.db = self.SessionLocal()
        self.title = Title(
            slug="test-title",
            name="Test Title",
            title_type=TitleType.MOVIE,
            status=TitleStatus.DRAFT,
        )
        self.db.add(self.title)
        self.db.flush()
        self.manifest = IngestManifest(
            name="test-manifest",
            version=1,
            rules_json=json.dumps(
                [
                    {"pattern": "*master*.mp4", "asset_type": "video_master"},
                    {"pattern": "*.srt", "asset_type": "subtitle"},
                ]
            ),
            enabled=True,
        )
        self.db.add(self.manifest)
        self.db.commit()

    def tearDown(self):
        self.db.close()

    @patch("app.services.ingest_service._s3_client", return_value=_FakeS3Client())
    def test_validate_manifest_matches_files(self, _):
        with patch("app.services.ingest_service.settings.ingest_s3_bucket", "catalog-ingest"), patch(
            "app.services.ingest_service.settings.ingest_s3_prefix", "deliveries"
        ):
            result = ingest_service.validate_manifest(
                self.db,
                IngestManifestValidateRequest(
                    manifest_id=self.manifest.id,
                    source_prefix="drop",
                    max_keys=100,
                ),
            )
        self.assertEqual(result.discovered_count, 2)
        self.assertEqual(result.matched_count, 2)
        self.assertTrue(any(item.inferred_asset_type == "video_master" for item in result.items))

    @patch("app.services.ingest_service._s3_client", return_value=_FakeS3Client())
    def test_create_job_creates_assets(self, _):
        with patch("app.services.ingest_service.settings.ingest_s3_bucket", "catalog-ingest"), patch(
            "app.services.ingest_service.settings.ingest_s3_prefix", "deliveries"
        ):
            job = ingest_service.create_job(
                self.db,
                IngestJobCreateRequest(
                    title_id=self.title.id,
                    manifest_id=self.manifest.id,
                    source_prefix="drop",
                    dry_run=False,
                    max_keys=100,
                ),
            )
        self.assertEqual(job.ingested_count, 2)
        self.assertEqual(job.failed_count, 0)
        self.assertEqual(len(job.items), 2)


if __name__ == "__main__":
    unittest.main()
