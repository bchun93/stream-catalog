"""Tests for the SNS->SQS completion consumer: mapping, status flips, idempotency, delete."""

import importlib
import json
import os
import unittest
from unittest.mock import patch

try:
    import moto  # noqa: F401

    _HAS_MOTO = True
except Exception:  # pragma: no cover
    _HAS_MOTO = False


def _sns_envelope(notification: dict) -> str:
    return json.dumps({"Type": "Notification", "Message": json.dumps(notification)})


class _FakeRekognitionGet:
    """Returns canned Get* payloads (single page)."""

    def get_segment_detection(self, **_):
        return {
            "Segments": [
                {
                    "Type": "TECHNICAL_CUE",
                    "StartTimestampMillis": 0,
                    "EndTimestampMillis": 1200,
                    "TechnicalCueSegment": {"Type": "BlackFrames", "Confidence": 99.1},
                },
                {
                    "Type": "SHOT",
                    "StartTimestampMillis": 1200,
                    "EndTimestampMillis": 5000,
                    "ShotSegment": {"Index": 0, "Confidence": 98.0},
                },
            ]
        }

    def get_content_moderation(self, **_):
        return {
            "ModerationLabels": [
                {
                    "Timestamp": 3000,
                    "ModerationLabel": {
                        "Name": "Violence",
                        "ParentName": "",
                        "Confidence": 81.5,
                    },
                }
            ]
        }

    def get_label_detection(self, **_):
        return {
            "Labels": [
                {
                    "Timestamp": 2000,
                    "Label": {
                        "Name": "Car",
                        "Confidence": 95.0,
                        "Instances": [{"BoundingBox": {"Width": 0.5}, "Confidence": 95.0}],
                    },
                }
            ]
        }


@unittest.skipUnless(_HAS_MOTO, "moto required")
class ConsumerTests(unittest.TestCase):
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
        import app.services.rekognition.consumer as consumer

        importlib.reload(consumer)
        self.config = config
        self.ddb = ddb
        self.consumer = consumer
        from app.services.rekognition.constants import Feature

        self.Feature = Feature
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

    def _seed_job(self, feature, job_id="job-1"):
        self.ddb.put_job(
            asset_id="5",
            feature=feature,
            aws_job_id=job_id,
            client_request_token=f"5_{feature.value}",
        )

    def test_segment_success_maps_and_flips_status(self) -> None:
        self._seed_job(self.Feature.SEGMENT, "seg-1")
        msg = _sns_envelope(
            {"JobId": "seg-1", "Status": "SUCCEEDED", "JobTag": "5:SEGMENT"}
        )
        with patch.object(self.consumer, "rekognition_client", return_value=_FakeRekognitionGet()):
            outcome = self.consumer.process_completion(msg)
        self.assertTrue(outcome.ok)
        rows = self.ddb.query_detections(asset_id="5", feature=self.Feature.SEGMENT)
        self.assertEqual(len(rows), 2)
        kinds = {r["kind"] for r in rows}
        self.assertEqual(kinds, {"BlackFrames", "Shot"})
        # Time-ordered by sk: BlackFrames (0) before Shot (1200).
        self.assertEqual(rows[0]["start_ms"], 0)
        self.assertEqual(rows[1]["start_ms"], 1200)
        job = self.ddb.get_job(asset_id="5", feature=self.Feature.SEGMENT)
        self.assertEqual(job["status"], "SUCCEEDED")

    def test_labels_success_with_bounding_box(self) -> None:
        self._seed_job(self.Feature.LABELS, "lab-1")
        msg = _sns_envelope({"JobId": "lab-1", "Status": "SUCCEEDED", "JobTag": "5:LABELS"})
        with patch.object(self.consumer, "rekognition_client", return_value=_FakeRekognitionGet()):
            self.consumer.process_completion(msg)
        rows = self.ddb.query_detections(asset_id="5", feature=self.Feature.LABELS)
        self.assertEqual(rows[0]["name"], "Car")
        self.assertEqual(rows[0]["timestamp_ms"], 2000)
        self.assertEqual(rows[0]["bounding_box"]["Width"], 0.5)

    def test_failed_status_marks_job_failed(self) -> None:
        self._seed_job(self.Feature.MODERATION, "mod-1")
        msg = _sns_envelope(
            {
                "JobId": "mod-1",
                "Status": "FAILED",
                "JobTag": "5:MODERATION",
                "StatusMessage": "bad input",
            }
        )
        outcome = self.consumer.process_completion(msg)
        self.assertTrue(outcome.ok)
        job = self.ddb.get_job(asset_id="5", feature=self.Feature.MODERATION)
        self.assertEqual(job["status"], "FAILED")
        self.assertEqual(job["error"], "bad input")

    def test_reprocessing_is_idempotent(self) -> None:
        self._seed_job(self.Feature.SEGMENT, "seg-2")
        msg = _sns_envelope({"JobId": "seg-2", "Status": "SUCCEEDED", "JobTag": "5:SEGMENT"})
        with patch.object(self.consumer, "rekognition_client", return_value=_FakeRekognitionGet()):
            self.consumer.process_completion(msg)
            self.consumer.process_completion(msg)  # redelivery
        rows = self.ddb.query_detections(asset_id="5", feature=self.Feature.SEGMENT)
        self.assertEqual(len(rows), 2)  # not 4

    def test_unidentifiable_message_left_for_retry(self) -> None:
        msg = _sns_envelope({"JobId": "ghost", "Status": "SUCCEEDED"})
        outcome = self.consumer.process_completion(msg)
        self.assertFalse(outcome.ok)

    def test_drain_deletes_after_write(self) -> None:
        import app.services.aws_clients as aws_clients

        sqs = aws_clients.sqs_client()
        queue_url = sqs.create_queue(QueueName="test-q")["QueueUrl"]
        os.environ["REKOGNITION_SQS_QUEUE_URL"] = queue_url
        importlib.reload(self.config)
        importlib.reload(aws_clients)
        importlib.reload(self.consumer)

        self._seed_job(self.Feature.LABELS, "lab-9")
        sqs.send_message(
            QueueUrl=queue_url,
            MessageBody=_sns_envelope(
                {"JobId": "lab-9", "Status": "SUCCEEDED", "JobTag": "5:LABELS"}
            ),
        )
        with patch.object(self.consumer, "rekognition_client", return_value=_FakeRekognitionGet()):
            result = self.consumer.drain_queue(max_batches=1, wait_time_seconds=0)
        self.assertEqual(result.received, 1)
        self.assertEqual(result.deleted, 1)
        # Queue is now empty.
        attrs = sqs.get_queue_attributes(
            QueueUrl=queue_url, AttributeNames=["ApproximateNumberOfMessages"]
        )
        self.assertEqual(attrs["Attributes"]["ApproximateNumberOfMessages"], "0")


if __name__ == "__main__":
    unittest.main()
