"""Deterministic picture-QC rules over stored Rekognition detections. No AWS calls."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from app.services.rekognition.constants import (
    DURATION_MISMATCH_SECONDS,
    FEATURE_LENGTH_MS,
    PROGRAM_TAIL_MS,
    Feature,
)
from app.services.rekognition.rating_policy import implied_rank, rank_label, rating_rank

NONPROGRAM_KINDS = frozenset({"BlackFrames", "ColorBars", "Slate"})
WATCH_LABELS = frozenset({"smoking", "cigarette", "alcohol", "weapon", "blood"})


@dataclass(frozen=True)
class Finding:
    rule_id: str
    severity: str
    message: str
    start_ms: int | None = None
    end_ms: int | None = None
    evidence: dict[str, Any] = field(default_factory=dict)


def _ms(row: dict[str, Any], *keys: str) -> int | None:
    for key in keys:
        value = row.get(key)
        if isinstance(value, (int, float)):
            return int(value)
    return None


def _span(row: dict[str, Any]) -> tuple[int, int] | None:
    start = _ms(row, "start_ms", "timestamp_ms")
    if start is None:
        return None
    end = _ms(row, "end_ms")
    return start, start if end is None else max(start, end)


def _overlaps(a: tuple[int, int], b: tuple[int, int]) -> bool:
    return a[0] < b[1] and b[0] < a[1]


def _cues(detections: Iterable[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
    return [
        row
        for row in detections
        if row.get("feature") == Feature.SEGMENT.value and row.get("kind") == kind
    ]


def _content_span(detections: list[dict[str, Any]]) -> tuple[int, int] | None:
    spans = [_span(row) for row in _cues(detections, "Content")]
    present = [s for s in spans if s is not None]
    if not present:
        return None
    return min(s[0] for s in present), max(s[1] for s in present)


def _text_rows(detections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    texts = [row for row in detections if row.get("feature") == Feature.TEXT.value]
    lines = [row for row in texts if str(row.get("kind") or "").upper() == "LINE"]
    return lines or texts


def evaluate(
    detections: Iterable[dict[str, Any]],
    *,
    media_meta: dict[str, Any] | None = None,
    title_rating: str | None = None,
    asset_duration_seconds: float | None = None,
) -> list[Finding]:
    rows = [
        dict(row)
        for row in detections
        if row.get("feature") != Feature.FINDING.value
    ]
    findings: list[Finding] = []
    content = _content_span(rows)
    findings.extend(_nonprogram_present(rows))

    if content is None:
        findings.append(
            Finding(
                rule_id="REKO_MISSING_CONTENT",
                severity="error",
                message="No Content technical cue on the proxy. Picture QC cannot locate program.",
            )
        )
    else:
        findings.extend(_program_structure(rows, content))
        findings.extend(_burned_in_text(rows, content))
        findings.extend(_watch_labels(rows, content))
        findings.extend(_rating_signal(rows, content, title_rating))

    findings.extend(_duration_mismatch(media_meta, asset_duration_seconds))
    return findings


def _nonprogram_cues(rows: list[dict[str, Any]]) -> list[tuple[str, tuple[int, int]]]:
    found: list[tuple[str, tuple[int, int]]] = []
    for kind in NONPROGRAM_KINDS:
        for cue in _cues(rows, kind):
            span = _span(cue)
            if span:
                found.append((kind, span))
    return found


def _nonprogram_present(rows: list[dict[str, Any]]) -> list[Finding]:
    nonprogram = _nonprogram_cues(rows)
    if not nonprogram:
        return []
    kinds = sorted({kind for kind, _ in nonprogram})
    return [
        Finding(
            rule_id="REKO_NONPROGRAM_PRESENT",
            severity="info",
            message=f"Non-program cues on the proxy: {', '.join(kinds)}.",
            start_ms=min(span[0] for _, span in nonprogram),
            end_ms=max(span[1] for _, span in nonprogram),
            evidence={"kinds": kinds},
        )
    ]


def _program_structure(
    rows: list[dict[str, Any]], content: tuple[int, int]
) -> list[Finding]:
    findings: list[Finding] = []
    nonprogram = _nonprogram_cues(rows)

    overlapping = [(kind, span) for kind, span in nonprogram if _overlaps(span, content)]
    if overlapping:
        kinds = sorted({kind for kind, _ in overlapping})
        findings.append(
            Finding(
                rule_id="REKO_NONPROGRAM_IN_CONTENT",
                severity="warning",
                message=f"Black, bars, or slate overlap the Content span ({', '.join(kinds)}).",
                start_ms=min(span[0] for _, span in overlapping),
                end_ms=max(span[1] for _, span in overlapping),
                evidence={"kinds": kinds},
            )
        )

    content_ms = content[1] - content[0]
    if content_ms >= FEATURE_LENGTH_MS and not _cues(rows, "EndCredits"):
        findings.append(
            Finding(
                rule_id="REKO_MISSING_END_CREDITS",
                severity="warning",
                message="Feature-length Content has no EndCredits cue.",
                start_ms=content[0],
                end_ms=content[1],
                evidence={"content_ms": content_ms},
            )
        )

    tail_start = max(content[0], content[1] - PROGRAM_TAIL_MS)
    mid_black: list[tuple[int, int]] = []
    for cue in _cues(rows, "BlackFrames"):
        span = _span(cue)
        if span is None:
            continue
        if span[0] > content[0] and span[1] < tail_start:
            mid_black.append(span)
    if mid_black:
        findings.append(
            Finding(
                rule_id="REKO_MID_PROGRAM_BLACK",
                severity="warning",
                message="Black frames appear after Content starts and before the program tail.",
                start_ms=min(s[0] for s in mid_black),
                end_ms=max(s[1] for s in mid_black),
                evidence={"count": len(mid_black)},
            )
        )
    return findings


def _program_body(rows: list[dict[str, Any]], content: tuple[int, int]) -> tuple[int, int]:
    opening_ends = [_span(row)[1] for row in _cues(rows, "OpeningCredits") if _span(row)]
    credit_starts = [_span(row)[0] for row in _cues(rows, "EndCredits") if _span(row)]
    start = max(opening_ends) if opening_ends else content[0]
    end = min(credit_starts) if credit_starts else content[1]
    return start, max(start, end)


def _burned_in_text(
    rows: list[dict[str, Any]], content: tuple[int, int]
) -> list[Finding]:
    body = _program_body(rows, content)
    hits: list[tuple[int, str]] = []
    for row in _text_rows(rows):
        ts = _ms(row, "timestamp_ms", "start_ms")
        if ts is None or not (body[0] <= ts < body[1]):
            continue
        text = str(row.get("name") or "").strip()
        if text:
            hits.append((ts, text))
    if not hits:
        return []
    samples = [text for _, text in hits[:8]]
    return [
        Finding(
            rule_id="REKO_BURNED_IN_TEXT",
            severity="info",
            message=f"{len(hits)} on-screen text hit(s) inside program (after opening credits, before end credits).",
            start_ms=hits[0][0],
            end_ms=hits[-1][0],
            evidence={"count": len(hits), "samples": samples},
        )
    ]


def _watch_labels(
    rows: list[dict[str, Any]], content: tuple[int, int]
) -> list[Finding]:
    matched: dict[str, list[int]] = {}
    for row in rows:
        if row.get("feature") != Feature.LABELS.value:
            continue
        name = str(row.get("name") or row.get("kind") or "").strip()
        key = name.lower()
        if key not in WATCH_LABELS:
            continue
        ts = _ms(row, "timestamp_ms", "start_ms")
        if ts is None or not (content[0] <= ts < content[1]):
            continue
        matched.setdefault(name, []).append(ts)
    findings: list[Finding] = []
    for name, times in sorted(matched.items()):
        findings.append(
            Finding(
                rule_id="REKO_WATCH_LABEL",
                severity="info",
                message=f"Watch label “{name}” appears in Content ({len(times)} hit(s)).",
                start_ms=min(times),
                end_ms=max(times),
                evidence={"label": name, "count": len(times)},
            )
        )
    return findings


def _rating_signal(
    rows: list[dict[str, Any]],
    content: tuple[int, int],
    title_rating: str | None,
) -> list[Finding]:
    catalog_rank = rating_rank(title_rating)
    if catalog_rank is None:
        return []
    highest: tuple[int, str, int] | None = None
    for row in rows:
        if row.get("feature") != Feature.MODERATION.value:
            continue
        ts = _ms(row, "timestamp_ms", "start_ms")
        if ts is None or not (content[0] <= ts < content[1]):
            continue
        rank = implied_rank(row.get("kind"), row.get("name"))
        if rank is None:
            continue
        label = str(row.get("kind") or row.get("name") or "moderation")
        if highest is None or rank > highest[0]:
            highest = (rank, label, ts)
    if highest is None or highest[0] <= catalog_rank:
        return []
    rank, label, ts = highest
    return [
        Finding(
            rule_id="REKO_RATING_SIGNAL",
            severity="warning",
            message=(
                f"Visual moderation “{label}” implies {rank_label(rank)}, "
                f"above catalog rating {title_rating}."
            ),
            start_ms=ts,
            evidence={
                "label": label,
                "implied_rating": rank_label(rank),
                "catalog_rating": title_rating,
            },
        )
    ]


def _duration_mismatch(
    media_meta: dict[str, Any] | None,
    asset_duration_seconds: float | None,
) -> list[Finding]:
    if asset_duration_seconds is None:
        return []
    video = (media_meta or {}).get("video") or {}
    duration_ms = video.get("DurationMillis")
    if not isinstance(duration_ms, (int, float)):
        return []
    observed = float(duration_ms) / 1000.0
    if abs(observed - float(asset_duration_seconds)) <= DURATION_MISMATCH_SECONDS:
        return []
    return [
        Finding(
            rule_id="REKO_DURATION_MISMATCH",
            severity="info",
            message=(
                f"Rekognition video duration {observed:.1f}s differs from the asset "
                f"duration {float(asset_duration_seconds):.1f}s."
            ),
            evidence={
                "observed_seconds": observed,
                "asset_seconds": float(asset_duration_seconds),
            },
        )
    ]
