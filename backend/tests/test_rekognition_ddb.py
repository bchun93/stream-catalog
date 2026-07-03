"""Access-layer tests for the Rekognition DynamoDB module.

Uses moto to emulate DynamoDB. Skipped automatically when moto isn't installed, so the
stdlib ``python -m unittest`` run stays dependency-light for environments without it.
"""

import importlib
import os
import unittest

try:
    import moto  # noqa: F401

    _HAS_MOTO = True
except Exception:  # pragma: no cover - environment without moto
    _HAS_MOTO = False


@unittest.skipUnless(_HAS_MOTO, "moto is required for DynamoDB access-layer tests")
class RekognitionDdbTests(unittest.TestCase):
    def setUp(self) -> None:
        from moto import mock_aws

        self._mock = mock_aws()
        self._mock.start()

        # Point config at test tables + dummy creds, then reload modules that bind settings.
        os.environ["AWS_REGION"] = "us-east-1"
        os.environ["AWS_ACCESS_KEY_ID"] = "testing"
        os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
        os.environ["DDB_JOBS_TABLE"] = "test_jobs"
        os.environ["DDB_DETECTIONS_TABLE"] = "test_detections"
        os.environ.pop("AWS_PROFILE", None)
        os.environ.pop("AWS_ENDPOINT_URL", None)

        import app.config as config

        importlib.reload(config)
        import app.services.aws_clients as aws_clients

        importlib.reload(aws_clients)
        import app.services.rekognition.ddb as ddb

        importlib.reload(ddb)
        self.ddb = ddb
        from app.services.rekognition.constants import Feature, JobStatus

        self.Feature = Feature
        self.JobStatus = JobStatus

        self._create_tables(aws_clients)

    def tearDown(self) -> None:
        self._mock.stop()

    def _create_tables(self, aws_clients) -> None:
        client = aws_clients.dynamodb_resource().meta.client
        client.create_table(
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
        client.create_table(
            TableName="test_detections",
            BillingMode="PAY_PER_REQUEST",
            AttributeDefinitions=[
                {"AttributeName": "asset_id", "AttributeType": "S"},
                {"AttributeName": "sk", "AttributeType": "S"},
            ],
            KeySchema=[
                {"AttributeName": "asset_id", "KeyType": "HASH"},
                {"AttributeName": "sk", "KeyType": "RANGE"},
            ],
        )

    def test_put_job_is_idempotent_and_conflicts(self) -> None:
        ddb, Feature = self.ddb, self.Feature
        ddb.put_job(
            asset_id="1",
            feature=Feature.LABELS,
            aws_job_id="job-abc",
            client_request_token="1:LABELS",
        )
        # Second create for same (asset, feature) while IN_PROGRESS must conflict.
        with self.assertRaises(ddb.JobConflictError) as ctx:
            ddb.put_job(
                asset_id="1",
                feature=Feature.LABELS,
                aws_job_id="job-def",
                client_request_token="1:LABELS",
            )
        self.assertIsNotNone(ctx.exception.existing)
        self.assertEqual(ctx.exception.existing["aws_job_id"], "job-abc")

    def test_failed_job_can_be_recreated(self) -> None:
        ddb, Feature, JobStatus = self.ddb, self.Feature, self.JobStatus
        ddb.put_job(
            asset_id="2",
            feature=Feature.SEGMENT,
            aws_job_id="job-1",
            client_request_token="2:SEGMENT",
        )
        ddb.update_job_status(
            asset_id="2", feature=Feature.SEGMENT, status=JobStatus.FAILED, error="boom"
        )
        # Re-running a FAILED feature is allowed.
        recreated = ddb.put_job(
            asset_id="2",
            feature=Feature.SEGMENT,
            aws_job_id="job-2",
            client_request_token="2:SEGMENT",
        )
        self.assertEqual(recreated["aws_job_id"], "job-2")
        self.assertEqual(recreated["status"], JobStatus.IN_PROGRESS.value)

    def test_get_job_by_aws_job_id_via_gsi(self) -> None:
        ddb, Feature = self.ddb, self.Feature
        ddb.put_job(
            asset_id="9",
            feature=Feature.MODERATION,
            aws_job_id="lookup-me",
            client_request_token="9:MODERATION",
        )
        found = ddb.get_job_by_aws_job_id("lookup-me")
        self.assertIsNotNone(found)
        self.assertEqual(found["asset_id"], "9")
        self.assertEqual(found["feature"], Feature.MODERATION.value)
        self.assertIsNone(ddb.get_job_by_aws_job_id("nonexistent"))

    def test_batch_put_and_query_time_ordered(self) -> None:
        ddb, Feature = self.ddb, self.Feature
        # Insert out of order; expect chronological read-back by sk.
        rows = []
        for ms in (5000, 1000, 3000):
            rows.append(
                {
                    "asset_id": "7",
                    "sk": ddb.build_detection_sk(Feature.LABELS, ms, f"Car|{ms}"),
                    "feature": Feature.LABELS.value,
                    "kind": "Car",
                    "name": "Car",
                    "confidence": 0.9,
                    "timestamp_ms": ms,
                    "job_id": "j",
                    "created_at": "now",
                }
            )
        # A moderation row should not appear in a LABELS query.
        rows.append(
            {
                "asset_id": "7",
                "sk": ddb.build_detection_sk(Feature.MODERATION, 2000, "Nudity|2000"),
                "feature": Feature.MODERATION.value,
                "kind": "Nudity",
                "confidence": 0.8,
                "timestamp_ms": 2000,
                "job_id": "j",
                "created_at": "now",
            }
        )
        written = ddb.batch_put_detections(rows)
        self.assertEqual(written, 4)

        labels = ddb.query_detections(asset_id="7", feature=Feature.LABELS)
        self.assertEqual([d["timestamp_ms"] for d in labels], [1000, 3000, 5000])
        self.assertTrue(all(d["feature"] == "LABELS" for d in labels))
        self.assertIsInstance(labels[0]["confidence"], float)

        all_rows = ddb.query_detections(asset_id="7")
        self.assertEqual(len(all_rows), 4)

    def test_batch_put_idempotent_on_deterministic_sk(self) -> None:
        ddb, Feature = self.ddb, self.Feature
        row = {
            "asset_id": "8",
            "sk": ddb.build_detection_sk(Feature.SEGMENT, 1500, "BlackFrames|1500|3000"),
            "feature": Feature.SEGMENT.value,
            "kind": "BlackFrames",
            "confidence": 0.99,
            "start_ms": 1500,
            "end_ms": 3000,
            "job_id": "j",
            "created_at": "now",
        }
        ddb.batch_put_detections([row])
        ddb.batch_put_detections([dict(row)])  # reprocess redelivered message
        self.assertEqual(len(ddb.query_detections(asset_id="8")), 1)


if __name__ == "__main__":
    unittest.main()
