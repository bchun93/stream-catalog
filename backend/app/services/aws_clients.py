"""Centralized, typed AWS client factory for the Rekognition Video integration.

All Rekognition/SQS/S3/DynamoDB access goes through here so region and credential
configuration lives in exactly one place. Credentials follow the same resolution order as
the existing ``s3_service`` (explicit keys → named profile → default chain), and honor
``AWS_ENDPOINT_URL`` for local LocalStack/MinIO testing.

Typing uses ``boto3-stubs`` (``mypy_boto3_*``) so every response is statically typed.
"""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING, Any

import boto3

from app.config import settings

if TYPE_CHECKING:  # stubs are dev-only; never required at runtime
    from mypy_boto3_dynamodb.service_resource import DynamoDBServiceResource, Table
    from mypy_boto3_rekognition.client import RekognitionClient
    from mypy_boto3_s3.client import S3Client
    from mypy_boto3_sqs.client import SQSClient


def _session() -> boto3.session.Session:
    kwargs: dict[str, Any] = {"region_name": settings.aws_region}
    if settings.aws_profile:
        kwargs["profile_name"] = settings.aws_profile
    if settings.aws_access_key_id and settings.aws_secret_access_key:
        kwargs["aws_access_key_id"] = settings.aws_access_key_id
        kwargs["aws_secret_access_key"] = settings.aws_secret_access_key
    return boto3.Session(**kwargs)


def _client_kwargs() -> dict[str, Any]:
    kwargs: dict[str, Any] = {}
    if settings.aws_endpoint_url:
        kwargs["endpoint_url"] = settings.aws_endpoint_url
    return kwargs


@lru_cache(maxsize=1)
def rekognition_client() -> "RekognitionClient":
    return _session().client("rekognition", **_client_kwargs())


@lru_cache(maxsize=1)
def sqs_client() -> "SQSClient":
    return _session().client("sqs", **_client_kwargs())


@lru_cache(maxsize=1)
def s3_client() -> "S3Client":
    return _session().client("s3", **_client_kwargs())


def dynamodb_resource() -> "DynamoDBServiceResource":
    """High-level resource — auto-marshals Python types (Python's DocumentClient).

    NOT cached: boto3 *resources* are not thread-safe (unlike botocore clients), and the
    consumer/reads run on FastAPI's thread pool. A fresh resource per call avoids races;
    the cost is negligible at this app's scale.
    """
    return _session().resource("dynamodb", **_client_kwargs())


def jobs_table() -> "Table":
    return dynamodb_resource().Table(settings.ddb_jobs_table)


def detections_table() -> "Table":
    return dynamodb_resource().Table(settings.ddb_detections_table)


def reset_clients() -> None:
    """Clear cached clients. Note: ``_session()`` reads the module-level ``settings``
    singleton, so tests that change env must also re-instantiate/patch ``settings`` for a
    cleared client to pick up new values. (``dynamodb_resource`` is uncached already.)"""
    rekognition_client.cache_clear()
    sqs_client.cache_clear()
    s3_client.cache_clear()
