#!/usr/bin/env python3
"""Stream Netflix Open Content into Relay's ingest prefix, then exit.

Source reads are anonymous (Netflix's documented --no-sign-request method).
Destination writes use the instance role. Objects are streamed in 64 MiB
parts so large IMF essence never lands on disk.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any

import boto3
from botocore import UNSIGNED
from botocore.config import Config
from botocore.exceptions import ClientError

LICENSE_NOTE = (
    "Netflix Open Content, licensed under Creative Commons Attribution 4.0 "
    "International (CC BY 4.0). https://opencontent.netflix.com/"
)
PART_SIZE = 64 * 1024 * 1024
log = logging.getLogger("relay.netflix-transfer")


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def unsigned_client(region: str):
    return boto3.client(
        "s3",
        region_name=region,
        config=Config(
            signature_version=UNSIGNED,
            s3={"addressing_style": "path"},
            retries={"max_attempts": 10, "mode": "adaptive"},
            max_pool_connections=8,
        ),
    )


def signed_client(region: str):
    return boto3.client(
        "s3",
        region_name=region,
        config=Config(
            retries={"max_attempts": 10, "mode": "adaptive"},
            max_pool_connections=8,
        ),
    )


def write_status(dest, bucket: str, key: str, payload: dict[str, Any]) -> None:
    dest.put_object(
        Bucket=bucket,
        Key=key,
        Body=json.dumps(payload, indent=2).encode("utf-8"),
        ContentType="application/json",
    )


def already_copied(dest, bucket: str, key: str, size: int) -> bool:
    try:
        head = dest.head_object(Bucket=bucket, Key=key)
        return int(head["ContentLength"]) == size
    except ClientError as exc:
        code = str(exc.response.get("Error", {}).get("Code", ""))
        if code in {"404", "NoSuchKey", "NotFound"}:
            return False
        raise


def abort_multipart(dest, bucket: str, key: str, upload_id: str) -> None:
    try:
        dest.abort_multipart_upload(Bucket=bucket, Key=key, UploadId=upload_id)
    except Exception:
        log.exception("Failed to abort multipart upload %s", key)


def stream_copy(
    source,
    dest,
    *,
    src_bucket: str,
    dest_bucket: str,
    source_key: str,
    dest_key: str,
    expected_size: int,
) -> str:
    if already_copied(dest, dest_bucket, dest_key, expected_size):
        return "skipped"

    src_obj = source.get_object(Bucket=src_bucket, Key=source_key)
    body = src_obj["Body"]
    extra: dict[str, Any] = {"StorageClass": "INTELLIGENT_TIERING"}
    content_type = src_obj.get("ContentType")
    if content_type:
        extra["ContentType"] = content_type

    if expected_size <= PART_SIZE:
        payload = body.read()
        if len(payload) != expected_size:
            raise RuntimeError(
                f"{source_key}: got {len(payload)} bytes, expected {expected_size}"
            )
        dest.put_object(Bucket=dest_bucket, Key=dest_key, Body=payload, **extra)
        return "copied"

    upload = dest.create_multipart_upload(Bucket=dest_bucket, Key=dest_key, **extra)
    upload_id = upload["UploadId"]
    parts: list[dict[str, Any]] = []
    digest = hashlib.sha256()
    copied = 0
    part_number = 1
    try:
        while True:
            chunk = body.read(PART_SIZE)
            if not chunk:
                break
            digest.update(chunk)
            copied += len(chunk)
            response = dest.upload_part(
                Bucket=dest_bucket,
                Key=dest_key,
                UploadId=upload_id,
                PartNumber=part_number,
                Body=chunk,
            )
            parts.append({"ETag": response["ETag"], "PartNumber": part_number})
            part_number += 1
        if copied != expected_size:
            raise RuntimeError(
                f"{source_key}: streamed {copied} bytes, expected {expected_size}"
            )
        dest.complete_multipart_upload(
            Bucket=dest_bucket,
            Key=dest_key,
            UploadId=upload_id,
            MultipartUpload={"Parts": parts},
        )
        return "copied"
    except Exception:
        abort_multipart(dest, dest_bucket, dest_key, upload_id)
        raise
    finally:
        body.close()


def emit_manifest(plan: dict[str, Any], dest_bucket: str, dest_prefix: str) -> dict[str, Any]:
    titles: dict[str, dict[str, Any]] = {}
    for item in plan["objects"]:
        title = titles.setdefault(
            item["title"],
            {"title_slug": item["title"], "license": LICENSE_NOTE, "packages": {}},
        )
        pkg_key = f"{item['group']}:{os.path.dirname(item['key'])}"
        pkg = title["packages"].setdefault(
            pkg_key,
            {
                "package_type": item["group"],
                "source_prefix": os.path.dirname(item["key"]),
                "assets": [],
            },
        )
        pkg["assets"].append(
            {
                "s3_uri": f"s3://{dest_bucket}/{dest_prefix}/{item['key']}",
                "filename": os.path.basename(item["key"]),
                "size_bytes": item["size"],
            }
        )
    return {
        "generated_at": utc_now(),
        "source": f"s3://{plan['source_bucket']}",
        "license": LICENSE_NOTE,
        "titles": [{**title, "packages": list(title["packages"].values())} for title in titles.values()],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--status-key", default="")
    parser.add_argument("--ingest-manifest-key", default="")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )

    plan = json.loads(open(args.manifest, encoding="utf-8").read())
    objects = plan["objects"]
    total = sum(int(item["size"]) for item in objects)
    ceiling = int(plan["hard_ceiling_bytes"])
    if total > ceiling:
        log.error("Pinned manifest is %.2f GiB, ceiling is %.2f GiB", total / 1024**3, ceiling / 1024**3)
        return 2

    dest_bucket = plan["dest_bucket"]
    dest_prefix = plan["dest_prefix"].rstrip("/")
    status_key = args.status_key or f"{dest_prefix}/_relay-bootstrap/status.json"
    ingest_key = args.ingest_manifest_key or f"{dest_prefix}/_relay-bootstrap/ingest.json"

    source = unsigned_client("us-east-1")
    dest = signed_client("ap-northeast-1")
    tally = {"copied": 0, "skipped": 0, "error": 0}
    errors: list[str] = []
    started = time.time()

    write_status(
        dest,
        dest_bucket,
        status_key,
        {
            "state": "running",
            "started_at": utc_now(),
            "total_objects": len(objects),
            "total_bytes": total,
            **tally,
            "errors": errors,
        },
    )

    for index, item in enumerate(objects, start=1):
        dest_key = f"{dest_prefix}/{item['key']}"
        try:
            status = stream_copy(
                source,
                dest,
                src_bucket=plan["source_bucket"],
                dest_bucket=dest_bucket,
                source_key=item["key"],
                dest_key=dest_key,
                expected_size=int(item["size"]),
            )
            tally[status] += 1
            log.info("%s %s (%s/%s)", status, item["key"], index, len(objects))
        except Exception as exc:
            tally["error"] += 1
            errors.append(f"{item['key']}: {exc}")
            log.exception("Failed %s", item["key"])
        if index % 5 == 0 or index == len(objects):
            write_status(
                dest,
                dest_bucket,
                status_key,
                {
                    "state": "running",
                    "started_at": utc_now(),
                    "completed": index,
                    "total_objects": len(objects),
                    "elapsed_seconds": round(time.time() - started, 1),
                    **tally,
                    "errors": errors,
                },
            )

    ingest = emit_manifest(plan, dest_bucket, dest_prefix)
    dest.put_object(
        Bucket=dest_bucket,
        Key=ingest_key,
        Body=json.dumps(ingest, indent=2).encode("utf-8"),
        ContentType="application/json",
    )
    final_state = "failed" if tally["error"] else "succeeded"
    write_status(
        dest,
        dest_bucket,
        status_key,
        {
            "state": final_state,
            "finished_at": utc_now(),
            "elapsed_seconds": round(time.time() - started, 1),
            "total_objects": len(objects),
            "total_bytes": total,
            "ingest_manifest": f"s3://{dest_bucket}/{ingest_key}",
            **tally,
            "errors": errors,
        },
    )
    log.info("Done state=%s copied=%s skipped=%s error=%s", final_state, tally["copied"], tally["skipped"], tally["error"])
    return 1 if tally["error"] else 0


if __name__ == "__main__":
    sys.exit(main())
