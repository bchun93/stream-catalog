"""Shared enums and tunable config constants for the Rekognition integration.

Confidence thresholds live here (not as magic numbers scattered through the code) per the
cost/correctness guardrails. They can be promoted to env-backed settings later if needed.
"""

from __future__ import annotations

import enum


class Feature(str, enum.Enum):
    """The three v1 analysis features. Value doubles as the DynamoDB sort-key prefix."""

    SEGMENT = "SEGMENT"
    MODERATION = "MODERATION"
    LABELS = "LABELS"


class JobStatus(str, enum.Enum):
    IN_PROGRESS = "IN_PROGRESS"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


# --- Confidence thresholds (configurable constants, not magic numbers) ---
MODERATION_MIN_CONFIDENCE: float = 60.0
LABEL_MIN_CONFIDENCE: float = 70.0
SEGMENT_TECHNICAL_CUE_MIN_CONFIDENCE: float = 80.0
SEGMENT_SHOT_MIN_CONFIDENCE: float = 80.0

# Zero-pad width for time in the detections sort key so lexicographic == chronological.
# 12 digits covers up to ~31 years in milliseconds — far beyond the 6h Rekognition cap.
SK_TIME_PAD_WIDTH: int = 12

# Allowed input containers for the H.264 proxy guard (Rekognition: MP4/MOV, H.264).
ALLOWED_VIDEO_EXTENSIONS: tuple[str, ...] = (".mp4", ".mov")
# Codec strings (lowercased) we treat as H.264.
H264_CODEC_HINTS: tuple[str, ...] = ("h264", "h.264", "avc", "avc1", "x264")
