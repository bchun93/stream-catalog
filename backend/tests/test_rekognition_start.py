"""Tests for start_analysis: H.264/MP4 guards, idempotent skip, and job rows landing."""

import importlib
import os
import unittest
from unittest.mock import patch

try:
    import moto  # noqa: F401

    _HAS_MOTO = True
except Exception:  # pragma: no cover
    _HAS_MOTO = False


class _FakeRekognition:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        self._n = 0

    def _job(self, op: str, **kwargs) -> dict:
        self.calls.append((op, kwargs))
        self._n += 1
        return {"JobId": f"job-{self._n}"}

    def start_segment_detection(self, **kwargs):
        return self._job("segment", **kwargs)

    def start_content_moderation(self, **kwargs):
        return self._job("moderation", **kwargs)

    def start_label_detection(self, **kwargs):
        return self._job("labels", **kwargs)


@unittest.skipUnless(_HAS_MOTO, "moto required")
class StartAnalysisTests(unittest.TestCase):
    def setUp(self) -> None:
        from moto import mock_aws

        self._mock = mock_aws()
        self._mock.start()

        os.environ.update(
            {
                "AWS_REGION": "us-east-1",
                "AWS_ACCESS_KEY_ID": "testing",
                "AWS_SECRET_ACCESS_KEY": "testing",
                "DDB_JOBS_TABLE": "test_jobs",
                "DDB_DETECTIONS_TABLE": "test_detections",
                "S3_ANALYSIS_BUCKET": "relay-analysis",
                "REKOGNITION_ROLE_ARN": "arn:aws:iam::123456789012:role/RelayRekognitionServiceRole",
                "REKOGNITION_SNS_TOPIC_ARN": "arn:aws:sns:us-east-1:123456789012:AmazonRekognition-relay-completion",
            }
        )
        os.environ.pop("AWS_PROFILE", None)
        os.environ.pop("AWS_ENDPOINT_URL", None)

        import app.config as config

        importlib.reload(config)
        import app.services.aws_clients as aws_clients

        importlib.reload(aws_clients)
        import app.services.rekognition.ddb as ddb

        importlib.reload(ddb)
        import app.services.rekognition.start as start

        importlib.reload(start)
        self.ddb = ddb
        self.start = start

        from app.models.media_asset import MediaAsset

        self.MediaAsset = MediaAsset
        self._create_jobs_table(aws_clients)

    def tearDown(self) -> None:
        self._mock.stop()

    def _create_jobs_table(self, aws_clients) -> None:
        aws_clients.dynamodb_resource().meta.client.create_table(
            TableName="test_jobs",
            BillingMode="PAY_PER_REQUEST",
            AttributeDefinitions=[
                {"AttributeName": "asset_id", "AttributeType": "S"},
                {"AttributeName": "feature", "AttributeType": "S"},
                {"AttributeName": "aws_job_id", "AttributeType": "S"},
            ],
            KeySchema=[
                {"AttributeName": "asset_id", "KeyType": "HASH"},
                {"AttributeName": "feature", "KeyType": "RANGE"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "gsi_job_id",
                    "KeySchema": [{"AttributeName": "aws_job_id", "KeyType": "HASH"}],
                    "Projection": {
                        "ProjectionType": "INCLUDE",
                        "NonKeyAttributes": ["asset_id", "feature", "status"],
                    },
                }
            ],
        )

    def _asset(self, **over):
        defaults = dict(id=1, storage_uri="s3://relay-analysis/proxies/clip.mp4", codec="h264")
        defaults.update(over)
        return self.MediaAsset(**defaults)

    def test_starts_three_jobs_and_writes_rows(self) -> None:
        fake = _FakeRekognition()
        with patch.object(self.start, "rekognition_client", return_value=fake):
            result = self.start.start_analysis(self._asset())
        self.assertEqual(len(result.results), 3)
        self.assertTrue(all(r.started for r in result.results))
        self.assertEqual(len(fake.calls), 3)
        # Every Start* carried NotificationChannel + idempotency token + JobTag.
        for _, kwargs in fake.calls:
            self.assertIn("SNSTopicArn", kwargs["NotificationChannel"])
            self.assertIn("RoleArn", kwargs["NotificationChannel"])
            self.assertRegex(kwargs["ClientRequestToken"], r"^1_(SEGMENT|MODERATION|LABELS)$")
            self.assertRegex(kwargs["JobTag"], r"^1:(SEGMENT|MODERATION|LABELS)$")
        # 3 rows persisted IN_PROGRESS.
        jobs = self.ddb.list_jobs_for_asset("1")
        self.assertEqual(len(jobs), 3)
        self.assertTrue(all(j["status"] == "IN_PROGRESS" for j in jobs))

    def test_reclick_does_not_restart(self) -> None:
        fake = _FakeRekognition()
        with patch.object(self.start, "rekognition_client", return_value=fake):
            self.start.start_analysis(self._asset())
            self.assertEqual(len(fake.calls), 3)
            again = self.start.start_analysis(self._asset())
        # No new Start* calls; all reported as skipped.
        self.assertEqual(len(fake.calls), 3)
        self.assertTrue(all(not r.started for r in again.results))

    def test_rejects_non_h264_codec(self) -> None:
        fake = _FakeRekognition()
        with patch.object(self.start, "rekognition_client", return_value=fake):
            with self.assertRaises(self.start.AnalysisInputError):
                self.start.start_analysis(self._asset(codec="prores"))
        self.assertEqual(len(fake.calls), 0)

    def test_rejects_non_video_extension(self) -> None:
        with self.assertRaises(self.start.AnalysisInputError):
            self.start.start_analysis(
                self._asset(storage_uri="s3://relay-analysis/x.mkv", codec="h264")
            )

    def test_rejects_non_s3_uri(self) -> None:
        with self.assertRaises(self.start.AnalysisInputError):
            self.start.start_analysis(
                self._asset(storage_uri="https://cdn.example.com/x.mp4")
            )

    def test_failed_feature_retry_uses_fresh_token(self) -> None:
        fake = _FakeRekognition()
        with patch.object(self.start, "rekognition_client", return_value=fake):
            self.start.start_analysis(self._asset())
            first_tokens = {c[1]["ClientRequestToken"] for c in fake.calls}
            # Mark one feature FAILED, then re-run.
            self.ddb.update_job_status(
                asset_id="1",
                feature=self.start.Feature.LABELS,
                status=self.start.JobStatus.FAILED,
                error="boom",
            )
            again = self.start.start_analysis(self._asset())
        labels = next(r for r in again.results if r.feature.value == "LABELS")
        self.assertTrue(labels.started)
        # The retry used a distinct token (attempt-bumped), not the original.
        retry_tokens = {c[1]["ClientRequestToken"] for c in fake.calls}
        self.assertIn("1_LABELS_2", retry_tokens)
        self.assertIn("1_LABELS", first_tokens)

    def test_default_path_rejects_foreign_bucket(self) -> None:
        with self.assertRaises(self.start.AnalysisInputError):
            self.start.start_analysis(
                self._asset(storage_uri="s3://some-other-bucket/clip.mp4", codec="h264")
            )

    def test_unknown_codec_warns_but_proceeds(self) -> None:
        fake = _FakeRekognition()
        with patch.object(self.start, "rekognition_client", return_value=fake):
            result = self.start.start_analysis(self._asset(codec=None))
        self.assertEqual(len(fake.calls), 3)
        self.assertTrue(any("unknown" in w.lower() for w in result.warnings))


if __name__ == "__main__":
    unittest.main()
