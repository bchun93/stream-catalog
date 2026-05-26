import json
import re
from dataclasses import dataclass


@dataclass
class MediaInfoSummary:
    codec: str | None = None
    duration_seconds: int | None = None
    resolution: str | None = None
    raw_json: str | None = None


_RESOLUTION_RE = re.compile(r"(?P<w>\d{3,5})[xX](?P<h>\d{3,5})")


def infer_resolution_from_name(name: str) -> str | None:
    match = _RESOLUTION_RE.search(name)
    if not match:
        return None
    return f"{match.group('w')}×{match.group('h')}"


def summarize_media_info(payload: dict | None) -> MediaInfoSummary:
    if not payload:
        return MediaInfoSummary()
    tracks = payload.get("media", {}).get("track")
    if not isinstance(tracks, list):
        return MediaInfoSummary(raw_json=json.dumps(payload, separators=(",", ":")))

    codec: str | None = None
    duration_seconds: int | None = None
    width: int | None = None
    height: int | None = None

    for track in tracks:
        if not isinstance(track, dict):
            continue
        track_type = str(track.get("@type", "")).lower()
        if track_type == "video":
            codec = codec or _as_str(track.get("Format"))
            width = width or _as_int(track.get("Width"))
            height = height or _as_int(track.get("Height"))
            duration_seconds = duration_seconds or _duration_to_seconds(track.get("Duration"))
        elif track_type in {"audio", "text"}:
            duration_seconds = duration_seconds or _duration_to_seconds(track.get("Duration"))

    resolution = f"{width}×{height}" if width and height else None
    return MediaInfoSummary(
        codec=codec,
        duration_seconds=duration_seconds,
        resolution=resolution,
        raw_json=json.dumps(payload, separators=(",", ":")),
    )


def _duration_to_seconds(value: object) -> int | None:
    if value is None:
        return None
    as_float = _as_float(value)
    if as_float is None:
        return None
    if as_float > 10_000:
        return int(as_float / 1000)
    return int(as_float)


def _as_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    text = str(value)
    digits = "".join(ch for ch in text if ch.isdigit())
    if not digits:
        return None
    try:
        return int(digits)
    except Exception:
        return None


def _as_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).replace(",", ".")
    match = re.search(r"\d+(\.\d+)?", text)
    if not match:
        return None
    try:
        return float(match.group(0))
    except Exception:
        return None


def _as_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
