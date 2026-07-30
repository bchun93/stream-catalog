"""Unit tests for delivery profile validation against Amazon SVOD-style specs."""

from __future__ import annotations

import json
import unittest

from app.models.media_asset import AssetStatus, AssetType, MediaAsset
from app.services.delivery_profile_service import (
    PROFILES_DIR,
    load_profile_documents,
    validate_asset_against_spec,
)


def _amazon_spec() -> dict:
    docs = load_profile_documents()
    for doc in docs:
        if doc.get("slug") == "amazon-prime-video-svod":
            return doc
    raise AssertionError("amazon-prime-video-svod YAML not found")


def _asset(**kwargs) -> MediaAsset:
    defaults = dict(
        id=1,
        title_id=10,
        asset_type=AssetType.VIDEO_MASTER,
        status=AssetStatus.READY,
        filename="feature.mov",
        storage_uri="s3://bucket/feature.mov",
        codec="ProRes422HQ",
        resolution="1920x1080",
        checksum="sha256:abc",
        metadata_json=None,
    )
    defaults.update(kwargs)
    return MediaAsset(**defaults)


class DeliveryProfileLoaderTests(unittest.TestCase):
    def test_yaml_seed_present(self):
        path = PROFILES_DIR / "amazon_prime_video_svod.v1.yaml"
        self.assertTrue(path.is_file(), f"missing {path}")
        docs = load_profile_documents()
        slugs = {d.get("slug") for d in docs}
        self.assertIn("amazon-prime-video-svod", slugs)


class DeliveryProfileValidatorTests(unittest.TestCase):
    def setUp(self):
        self.spec = _amazon_spec()

    def test_prores_hd_with_checksum_passes_core_rules(self):
        findings = validate_asset_against_spec(asset=_asset(), spec=self.spec)
        by_id = {f.rule_id: f for f in findings}
        self.assertEqual(by_id["video.codec"].status, "pass")
        self.assertEqual(by_id["video.resolution"].status, "pass")
        self.assertEqual(by_id["integrity.checksum"].status, "pass")
        self.assertEqual(by_id["video.disallowed_codecs"].status, "pass")

    def test_disallowed_prores444xq_fails(self):
        findings = validate_asset_against_spec(
            asset=_asset(codec="ProRes444XQ"),
            spec=self.spec,
        )
        by_id = {f.rule_id: f for f in findings}
        self.assertEqual(by_id["video.disallowed_codecs"].status, "fail")

    def test_missing_resolution_skips_resolution_rules(self):
        findings = validate_asset_against_spec(
            asset=_asset(resolution=None),
            spec=self.spec,
        )
        by_id = {f.rule_id: f for f in findings}
        self.assertEqual(by_id["video.resolution"].status, "skip")
        self.assertEqual(by_id["video.hd_min"].status, "skip")

    def test_missing_checksum_fails(self):
        findings = validate_asset_against_spec(
            asset=_asset(checksum=None),
            spec=self.spec,
        )
        by_id = {f.rule_id: f for f in findings}
        self.assertEqual(by_id["integrity.checksum"].status, "fail")

    def test_mov_requires_prores(self):
        findings = validate_asset_against_spec(
            asset=_asset(filename="feature.mov", codec="H264"),
            spec=self.spec,
        )
        by_id = {f.rule_id: f for f in findings}
        self.assertEqual(by_id["video.mov_codec_constraint"].status, "fail")

    def test_mediainfo_audio_and_frame_rate(self):
        media_info = {
            "media": {
                "track": [
                    {
                        "@type": "Video",
                        "Format": "AVC",
                        "Width": "1920",
                        "Height": "1080",
                        "FrameRate": "23.976",
                        "FrameRate_Mode": "CFR",
                        "ScanType": "Progressive",
                        "Duration": "3600",
                    },
                    {
                        "@type": "Audio",
                        "Format": "AAC",
                        "SamplingRate": "48000",
                        "Duration": "3600",
                    },
                ]
            }
        }
        asset = _asset(
            codec=None,
            resolution=None,
            filename="feature.mp4",
            metadata_json=json.dumps({"media_info": media_info}),
        )
        findings = validate_asset_against_spec(asset=asset, spec=self.spec)
        by_id = {f.rule_id: f for f in findings}
        self.assertEqual(by_id["video.codec"].status, "pass")
        self.assertEqual(by_id["video.resolution"].status, "pass")
        self.assertEqual(by_id["video.frame_rate"].status, "pass")
        self.assertEqual(by_id["audio.codec"].status, "pass")
        self.assertEqual(by_id["audio.sample_rate_hz"].status, "pass")
        self.assertEqual(by_id["integrity.av_duration_match"].status, "pass")


if __name__ == "__main__":
    unittest.main()
