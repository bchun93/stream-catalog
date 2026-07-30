"""Delivery profile library + package validation against profile specs."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session, joinedload

from app.models.delivery_package import DeliveryPackage, MonetizationModel
from app.models.delivery_package_title import DeliveryPackageTitle
from app.models.delivery_profile import DeliveryProfile
from app.models.media_asset import AssetType, MediaAsset
from app.schemas.delivery_profile import (
    DeliveryProfileRead,
    DeliveryProfileSummary,
    PackageValidationResponse,
    ValidationFinding,
)

logger = logging.getLogger(__name__)

PROFILES_DIR = Path(__file__).resolve().parent.parent / "data" / "delivery_profiles"

_VIDEO_TYPES = {AssetType.VIDEO_MASTER, AssetType.TRAILER}
_CODEC_ALIASES = {
    "prores422hq": "ProRes422HQ",
    "prores 422 hq": "ProRes422HQ",
    "apple prores 422 hq": "ProRes422HQ",
    "prores444xq": "ProRes444XQ",
    "prores 4444 xq": "ProRes444XQ",
    "h264": "H264",
    "avc": "H264",
    "avc1": "H264",
    "hevc": "HEVC",
    "h265": "HEVC",
    "dnxhr_hqx": "DNxHR_HQX",
    "dnxhr hqx": "DNxHR_HQX",
    "aac": "AAC",
    "ac3": "AC3",
    "ac-3": "AC3",
    "eac3": "EAC3",
    "e-ac-3": "EAC3",
    "prores": "ProRes",
}


def _load_yaml(path: Path) -> dict[str, Any]:
    import yaml

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"Invalid delivery profile YAML: {path.name}")
    return raw


def load_profile_documents() -> list[dict[str, Any]]:
    if not PROFILES_DIR.is_dir():
        return []
    docs: list[dict[str, Any]] = []
    for path in sorted(PROFILES_DIR.glob("*.yaml")):
        try:
            docs.append(_load_yaml(path))
        except Exception:
            logger.exception("Failed to load delivery profile %s", path)
    return docs


def profile_to_summary(profile: DeliveryProfile) -> DeliveryProfileSummary:
    return DeliveryProfileSummary.model_validate(profile)


def profile_to_read(profile: DeliveryProfile) -> DeliveryProfileRead:
    return DeliveryProfileRead(
        id=profile.id,
        slug=profile.slug,
        name=profile.name,
        platform=profile.platform,
        channel=profile.channel,
        version=profile.version,
        description=profile.description,
        enabled=profile.enabled,
        spec=profile.spec,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


def list_profiles(
    db: Session,
    *,
    enabled_only: bool = True,
) -> list[DeliveryProfileSummary]:
    q = db.query(DeliveryProfile).order_by(DeliveryProfile.name.asc())
    if enabled_only:
        q = q.filter(DeliveryProfile.enabled.is_(True))
    return [profile_to_summary(row) for row in q.all()]


def get_profile(db: Session, profile_id: int) -> DeliveryProfileRead | None:
    profile = db.query(DeliveryProfile).filter(DeliveryProfile.id == profile_id).first()
    if not profile:
        return None
    return profile_to_read(profile)


def get_profile_model(db: Session, profile_id: int) -> DeliveryProfile | None:
    return db.query(DeliveryProfile).filter(DeliveryProfile.id == profile_id).first()


def channel_to_monetization(channel: str) -> MonetizationModel:
    try:
        return MonetizationModel(channel.strip().lower())
    except ValueError:
        return MonetizationModel.SVOD


def _parse_resolution(raw: str | None) -> tuple[int, int] | None:
    if not raw:
        return None
    m = re.search(r"(\d{2,5})\s*[x×X]\s*(\d{2,5})", raw)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def _normalize_codec(raw: str | None) -> str | None:
    if not raw:
        return None
    key = re.sub(r"\s+", " ", raw.strip().lower())
    if key in _CODEC_ALIASES:
        return _CODEC_ALIASES[key]
    compact = key.replace(" ", "").replace("-", "").replace("_", "")
    for alias, canon in _CODEC_ALIASES.items():
        if alias.replace(" ", "").replace("-", "").replace("_", "") == compact:
            return canon
    # Keep original casing-stripped token for enum compare
    return raw.strip()


def _asset_media_info(asset: MediaAsset) -> dict[str, Any]:
    raw = (asset.metadata_json or "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    media = parsed.get("media_info")
    return media if isinstance(media, dict) else {}


def _media_tracks(media_info: dict[str, Any], track_type: str) -> list[dict[str, Any]]:
    media = media_info.get("media") if isinstance(media_info.get("media"), dict) else media_info
    if not isinstance(media, dict):
        return []
    tracks = media.get("track")
    if isinstance(tracks, dict):
        tracks = [tracks]
    if not isinstance(tracks, list):
        return []
    out: list[dict[str, Any]] = []
    for track in tracks:
        if isinstance(track, dict) and str(track.get("@type", "")).lower() == track_type.lower():
            out.append(track)
    return out


def _track_duration_seconds(track: dict[str, Any]) -> float | None:
    raw = track.get("Duration")
    if raw is None:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    # MediaInfo often reports ms when large
    if value > 10_000:
        return value / 1000.0
    return value


def _pick_video_asset(assets: list[MediaAsset]) -> MediaAsset | None:
    masters = [a for a in assets if a.asset_type == AssetType.VIDEO_MASTER]
    if masters:
        return sorted(masters, key=lambda a: a.id)[0]
    trailers = [a for a in assets if a.asset_type == AssetType.TRAILER]
    if trailers:
        return sorted(trailers, key=lambda a: a.id)[0]
    videos = [a for a in assets if a.asset_type in _VIDEO_TYPES]
    return sorted(videos, key=lambda a: a.id)[0] if videos else None


def _finding(
    *,
    rule_id: str,
    section: str,
    status: str,
    message: str,
    title_id: int | None = None,
    title_name: str | None = None,
    asset_id: int | None = None,
    observed: str | None = None,
    expected: str | None = None,
) -> ValidationFinding:
    return ValidationFinding(
        rule_id=rule_id,
        section=section,
        status=status,  # type: ignore[arg-type]
        message=message,
        title_id=title_id,
        title_name=title_name,
        asset_id=asset_id,
        observed=observed,
        expected=expected,
    )


def _eval_rule_expr(rule: str, width: int, height: int) -> bool:
    """Evaluate simple width/height comparison rules from the profile YAML."""
    expr = rule.strip()
    # Tokenize: WIDTH/HEIGHT comparisons joined by AND/OR
    tokens = re.split(r"\s+(AND|OR)\s+", expr, flags=re.IGNORECASE)
    if not tokens:
        raise ValueError(f"Unsupported rule expression: {rule}")

    def _compare(piece: str) -> bool:
        m = re.fullmatch(
            r"\s*(width|height)\s*(>=|<=|>|<|==|=)\s*(\d+)\s*",
            piece,
            flags=re.IGNORECASE,
        )
        if not m:
            raise ValueError(f"Unsupported rule expression: {rule}")
        left = width if m.group(1).lower() == "width" else height
        op = m.group(2)
        right = int(m.group(3))
        if op in (">=",):
            return left >= right
        if op in ("<=",):
            return left <= right
        if op == ">":
            return left > right
        if op == "<":
            return left < right
        return left == right

    result = _compare(tokens[0])
    i = 1
    while i < len(tokens):
        op = tokens[i].upper()
        rhs = _compare(tokens[i + 1])
        if op == "AND":
            result = result and rhs
        else:
            result = result or rhs
        i += 2
    return result


def validate_asset_against_spec(
    *,
    asset: MediaAsset,
    spec: dict[str, Any],
    title_id: int | None = None,
    title_name: str | None = None,
) -> list[ValidationFinding]:
    findings: list[ValidationFinding] = []
    video = spec.get("video") if isinstance(spec.get("video"), dict) else {}
    audio = spec.get("audio") if isinstance(spec.get("audio"), dict) else {}
    loudness = spec.get("loudness") if isinstance(spec.get("loudness"), dict) else {}
    integrity = spec.get("integrity") if isinstance(spec.get("integrity"), dict) else {}
    manifest = spec.get("manifest") if isinstance(spec.get("manifest"), dict) else {}

    media_info = _asset_media_info(asset)
    video_tracks = _media_tracks(media_info, "Video")
    audio_tracks = _media_tracks(media_info, "Audio")
    vtrack = video_tracks[0] if video_tracks else {}

    codec_raw = asset.codec or (str(vtrack.get("Format")) if vtrack.get("Format") else None)
    codec = _normalize_codec(codec_raw)
    filename = (asset.filename or "").lower()
    ext = filename.rsplit(".", 1)[-1] if "." in filename else ""

    # --- video.codec ---
    codec_rule = video.get("codec") if isinstance(video.get("codec"), dict) else {}
    allowed = [str(v) for v in codec_rule.get("values") or []]
    if allowed:
        if not codec:
            findings.append(
                _finding(
                    rule_id="video.codec",
                    section="video",
                    status="skip",
                    message="Codec not available on asset or MediaInfo",
                    title_id=title_id,
                    title_name=title_name,
                    asset_id=asset.id,
                    expected=", ".join(allowed),
                )
            )
        else:
            ok = any(
                codec.casefold() == a.casefold()
                or a.casefold() in codec.casefold()
                or codec.casefold() in a.casefold()
                for a in allowed
            )
            findings.append(
                _finding(
                    rule_id="video.codec",
                    section="video",
                    status="pass" if ok else "fail",
                    message="Codec allowed" if ok else "Codec not in allowed list",
                    title_id=title_id,
                    title_name=title_name,
                    asset_id=asset.id,
                    observed=codec,
                    expected=", ".join(allowed),
                )
            )

    # --- disallowed codecs ---
    disallowed = [str(v) for v in video.get("disallowed_codecs") or []]
    if disallowed:
        if not codec:
            findings.append(
                _finding(
                    rule_id="video.disallowed_codecs",
                    section="video",
                    status="skip",
                    message="Codec not available to check disallowed list",
                    title_id=title_id,
                    title_name=title_name,
                    asset_id=asset.id,
                )
            )
        else:
            hit = next(
                (
                    d
                    for d in disallowed
                    if d.casefold() in codec.casefold() or codec.casefold() in d.casefold()
                ),
                None,
            )
            findings.append(
                _finding(
                    rule_id="video.disallowed_codecs",
                    section="video",
                    status="fail" if hit else "pass",
                    message=f"Disallowed codec {hit}" if hit else "No disallowed codec",
                    title_id=title_id,
                    title_name=title_name,
                    asset_id=asset.id,
                    observed=codec,
                    expected=f"not in {', '.join(disallowed)}",
                )
            )

    # --- mov + ProRes constraint ---
    mov_rule = video.get("mov_codec_constraint") if isinstance(video.get("mov_codec_constraint"), dict) else {}
    if mov_rule.get("if_ext") and ext == str(mov_rule.get("if_ext")).lower():
        require = str(mov_rule.get("require_codec") or "")
        if not codec:
            findings.append(
                _finding(
                    rule_id="video.mov_codec_constraint",
                    section="video",
                    status="skip",
                    message="MOV detected but codec unknown",
                    title_id=title_id,
                    title_name=title_name,
                    asset_id=asset.id,
                    expected=require,
                )
            )
        else:
            ok = require.casefold() in codec.casefold()
            findings.append(
                _finding(
                    rule_id="video.mov_codec_constraint",
                    section="video",
                    status="pass" if ok else "fail",
                    message="MOV codec constraint satisfied" if ok else "MOV requires ProRes family codec",
                    title_id=title_id,
                    title_name=title_name,
                    asset_id=asset.id,
                    observed=codec,
                    expected=require,
                )
            )

    # --- resolution enum + hd/sd mins ---
    res_raw = asset.resolution
    if not res_raw and vtrack.get("Width") and vtrack.get("Height"):
        res_raw = f"{vtrack.get('Width')}x{vtrack.get('Height')}"
    dims = _parse_resolution(res_raw)

    res_rule = video.get("resolution") if isinstance(video.get("resolution"), dict) else {}
    res_values = [str(v) for v in res_rule.get("values") or []]
    if res_values:
        if not dims:
            findings.append(
                _finding(
                    rule_id="video.resolution",
                    section="video",
                    status="skip",
                    message="Resolution not available",
                    title_id=title_id,
                    title_name=title_name,
                    asset_id=asset.id,
                    expected=", ".join(res_values),
                )
            )
        else:
            observed = f"{dims[0]}x{dims[1]}"
            ok = any(_parse_resolution(v) == dims for v in res_values)
            findings.append(
                _finding(
                    rule_id="video.resolution",
                    section="video",
                    status="pass" if ok else "fail",
                    message="Resolution allowed" if ok else "Resolution not in allowed list",
                    title_id=title_id,
                    title_name=title_name,
                    asset_id=asset.id,
                    observed=observed,
                    expected=", ".join(res_values),
                )
            )

    for rule_key in ("hd_min", "sd_min"):
        rule_obj = video.get(rule_key) if isinstance(video.get(rule_key), dict) else {}
        rule_expr = rule_obj.get("rule")
        if not rule_expr:
            continue
        if not dims:
            findings.append(
                _finding(
                    rule_id=f"video.{rule_key}",
                    section="video",
                    status="skip",
                    message=f"Cannot evaluate {rule_key} without resolution",
                    title_id=title_id,
                    title_name=title_name,
                    asset_id=asset.id,
                    expected=str(rule_expr),
                )
            )
            continue
        try:
            ok = _eval_rule_expr(str(rule_expr), dims[0], dims[1])
            findings.append(
                _finding(
                    rule_id=f"video.{rule_key}",
                    section="video",
                    status="pass" if ok else "fail",
                    message=f"{rule_key} satisfied" if ok else f"{rule_key} not satisfied",
                    title_id=title_id,
                    title_name=title_name,
                    asset_id=asset.id,
                    observed=f"{dims[0]}x{dims[1]}",
                    expected=str(rule_expr),
                )
            )
        except ValueError as exc:
            findings.append(
                _finding(
                    rule_id=f"video.{rule_key}",
                    section="video",
                    status="skip",
                    message=str(exc),
                    title_id=title_id,
                    title_name=title_name,
                    asset_id=asset.id,
                )
            )

    # --- scan / frame rate / color — MediaInfo only ---
    scan_rule = video.get("scan_type") if isinstance(video.get("scan_type"), dict) else {}
    scan_values = [str(v).casefold() for v in scan_rule.get("values") or []]
    if scan_values:
        scan_obs = str(vtrack.get("ScanType") or vtrack.get("Scan type") or "").strip()
        if not scan_obs:
            findings.append(
                _finding(
                    rule_id="video.scan_type",
                    section="video",
                    status="skip",
                    message="Scan type not in MediaInfo",
                    title_id=title_id,
                    title_name=title_name,
                    asset_id=asset.id,
                    expected=", ".join(scan_rule.get("values") or []),
                )
            )
        else:
            ok = scan_obs.casefold() in scan_values or "progressive" in scan_obs.casefold()
            findings.append(
                _finding(
                    rule_id="video.scan_type",
                    section="video",
                    status="pass" if ok else "fail",
                    message="Scan type ok" if ok else "Scan type not allowed",
                    title_id=title_id,
                    title_name=title_name,
                    asset_id=asset.id,
                    observed=scan_obs,
                    expected=", ".join(str(v) for v in scan_rule.get("values") or []),
                )
            )

    fr_rule = video.get("frame_rate") if isinstance(video.get("frame_rate"), dict) else {}
    fr_values = [float(v) for v in fr_rule.get("values") or []]
    if fr_values:
        fr_raw = vtrack.get("FrameRate") or vtrack.get("Frame rate")
        if fr_raw is None:
            findings.append(
                _finding(
                    rule_id="video.frame_rate",
                    section="video",
                    status="skip",
                    message="Frame rate not in MediaInfo",
                    title_id=title_id,
                    title_name=title_name,
                    asset_id=asset.id,
                    expected=", ".join(str(v) for v in fr_values),
                )
            )
        else:
            try:
                fr = float(fr_raw)
                ok = any(abs(fr - allowed) < 0.02 for allowed in fr_values)
                findings.append(
                    _finding(
                        rule_id="video.frame_rate",
                        section="video",
                        status="pass" if ok else "fail",
                        message="Frame rate allowed" if ok else "Frame rate not allowed",
                        title_id=title_id,
                        title_name=title_name,
                        asset_id=asset.id,
                        observed=str(fr),
                        expected=", ".join(str(v) for v in fr_values),
                    )
                )
            except (TypeError, ValueError):
                findings.append(
                    _finding(
                        rule_id="video.frame_rate",
                        section="video",
                        status="skip",
                        message=f"Unparseable frame rate: {fr_raw}",
                        title_id=title_id,
                        title_name=title_name,
                        asset_id=asset.id,
                    )
                )

    frm_rule = video.get("frame_rate_mode") if isinstance(video.get("frame_rate_mode"), dict) else {}
    frm_values = [str(v).casefold() for v in frm_rule.get("values") or []]
    if frm_values:
        frm_obs = str(vtrack.get("FrameRate_Mode") or vtrack.get("Frame rate mode") or "").strip()
        if not frm_obs:
            findings.append(
                _finding(
                    rule_id="video.frame_rate_mode",
                    section="video",
                    status="skip",
                    message="Frame rate mode not in MediaInfo",
                    title_id=title_id,
                    title_name=title_name,
                    asset_id=asset.id,
                    expected=", ".join(str(v) for v in frm_rule.get("values") or []),
                )
            )
        else:
            ok = frm_obs.casefold() in frm_values or frm_obs.casefold() == "cfr"
            findings.append(
                _finding(
                    rule_id="video.frame_rate_mode",
                    section="video",
                    status="pass" if ok else "fail",
                    message="Frame rate mode ok" if ok else "Frame rate mode must be CFR",
                    title_id=title_id,
                    title_name=title_name,
                    asset_id=asset.id,
                    observed=frm_obs,
                    expected=", ".join(str(v) for v in frm_rule.get("values") or []),
                )
            )

    # upscaled — only if Original dimensions present
    up_rule = video.get("upscaled") if isinstance(video.get("upscaled"), dict) else {}
    if up_rule.get("require") is False:
        orig_w = vtrack.get("Width_Original") or vtrack.get("Original source width")
        orig_h = vtrack.get("Height_Original") or vtrack.get("Original source height")
        if not dims or orig_w is None or orig_h is None:
            findings.append(
                _finding(
                    rule_id="video.upscaled",
                    section="video",
                    status="skip",
                    message="Original dimensions not available to detect upscale",
                    title_id=title_id,
                    title_name=title_name,
                    asset_id=asset.id,
                    expected="not upscaled",
                )
            )
        else:
            try:
                ow, oh = int(orig_w), int(orig_h)
                upscaled = dims[0] > ow or dims[1] > oh
                findings.append(
                    _finding(
                        rule_id="video.upscaled",
                        section="video",
                        status="fail" if upscaled else "pass",
                        message="Upscaled video not allowed" if upscaled else "Not upscaled",
                        title_id=title_id,
                        title_name=title_name,
                        asset_id=asset.id,
                        observed=f"{dims[0]}x{dims[1]} from {ow}x{oh}",
                        expected="not upscaled",
                    )
                )
            except (TypeError, ValueError):
                findings.append(
                    _finding(
                        rule_id="video.upscaled",
                        section="video",
                        status="skip",
                        message="Could not parse original dimensions",
                        title_id=title_id,
                        title_name=title_name,
                        asset_id=asset.id,
                    )
                )

    # color / HDR — skip unless MediaInfo color tags present
    sdr = video.get("sdr_color_space") if isinstance(video.get("sdr_color_space"), dict) else {}
    hdr = video.get("hdr_format") if isinstance(video.get("hdr_format"), dict) else {}
    color_space = str(
        vtrack.get("colour_primaries")
        or vtrack.get("ColorSpace")
        or vtrack.get("color_primaries")
        or ""
    ).strip()
    hdr_format = str(vtrack.get("HDR_Format") or vtrack.get("hdr_format") or "").strip()
    if sdr.get("value") or hdr.get("value"):
        if not color_space and not hdr_format:
            findings.append(
                _finding(
                    rule_id="video.color",
                    section="video",
                    status="skip",
                    message="Color/HDR metadata not in MediaInfo",
                    title_id=title_id,
                    title_name=title_name,
                    asset_id=asset.id,
                    expected=f"SDR {sdr.get('value')} or HDR {hdr.get('value')}",
                )
            )
        elif hdr_format:
            expected_hdr = str(hdr.get("value") or "")
            ok = expected_hdr.casefold() in hdr_format.casefold() if expected_hdr else True
            findings.append(
                _finding(
                    rule_id="video.hdr_format",
                    section="video",
                    status="pass" if ok else "fail",
                    message="HDR format ok" if ok else "HDR format mismatch",
                    title_id=title_id,
                    title_name=title_name,
                    asset_id=asset.id,
                    observed=hdr_format,
                    expected=expected_hdr or None,
                )
            )
        else:
            expected_sdr = str(sdr.get("value") or "Rec709")
            ok = "709" in color_space or expected_sdr.casefold() in color_space.casefold()
            findings.append(
                _finding(
                    rule_id="video.sdr_color_space",
                    section="video",
                    status="pass" if ok else "fail",
                    message="SDR color space ok" if ok else "SDR color space mismatch",
                    title_id=title_id,
                    title_name=title_name,
                    asset_id=asset.id,
                    observed=color_space,
                    expected=expected_sdr,
                )
            )

    # --- audio ---
    audio_codec_rule = audio.get("codec") if isinstance(audio.get("codec"), dict) else {}
    audio_allowed = [str(v) for v in audio_codec_rule.get("values") or []]
    if audio_allowed:
        if not audio_tracks:
            findings.append(
                _finding(
                    rule_id="audio.codec",
                    section="audio",
                    status="skip",
                    message="No audio track / MediaInfo audio missing",
                    title_id=title_id,
                    title_name=title_name,
                    asset_id=asset.id,
                    expected=", ".join(audio_allowed),
                )
            )
        else:
            atrack = audio_tracks[0]
            acodec = _normalize_codec(str(atrack.get("Format") or ""))
            ok = bool(
                acodec
                and any(
                    acodec.casefold() == a.casefold() or a.casefold() in acodec.casefold()
                    for a in audio_allowed
                )
            )
            findings.append(
                _finding(
                    rule_id="audio.codec",
                    section="audio",
                    status="pass" if ok else "fail",
                    message="Audio codec allowed" if ok else "Audio codec not allowed",
                    title_id=title_id,
                    title_name=title_name,
                    asset_id=asset.id,
                    observed=acodec,
                    expected=", ".join(audio_allowed),
                )
            )

            sr_rule = audio.get("sample_rate_hz") if isinstance(audio.get("sample_rate_hz"), dict) else {}
            expected_sr = sr_rule.get("value")
            if expected_sr is not None:
                sr_raw = atrack.get("SamplingRate") or atrack.get("Sampling rate")
                if sr_raw is None:
                    findings.append(
                        _finding(
                            rule_id="audio.sample_rate_hz",
                            section="audio",
                            status="skip",
                            message="Sample rate not in MediaInfo",
                            title_id=title_id,
                            title_name=title_name,
                            asset_id=asset.id,
                            expected=str(expected_sr),
                        )
                    )
                else:
                    try:
                        sr = int(float(sr_raw))
                        ok = sr == int(expected_sr)
                        findings.append(
                            _finding(
                                rule_id="audio.sample_rate_hz",
                                section="audio",
                                status="pass" if ok else "fail",
                                message="Sample rate ok" if ok else "Sample rate mismatch",
                                title_id=title_id,
                                title_name=title_name,
                                asset_id=asset.id,
                                observed=str(sr),
                                expected=str(expected_sr),
                            )
                        )
                    except (TypeError, ValueError):
                        findings.append(
                            _finding(
                                rule_id="audio.sample_rate_hz",
                                section="audio",
                                status="skip",
                                message=f"Unparseable sample rate: {sr_raw}",
                                title_id=title_id,
                                title_name=title_name,
                                asset_id=asset.id,
                            )
                        )

    for track_rule_id in ("disabled_tracks", "me_mos_tracks"):
        rule_obj = audio.get(track_rule_id) if isinstance(audio.get(track_rule_id), dict) else {}
        if rule_obj.get("require") == "absent":
            findings.append(
                _finding(
                    rule_id=f"audio.{track_rule_id}",
                    section="audio",
                    status="skip",
                    message=f"{track_rule_id} not measurable from available MediaInfo",
                    title_id=title_id,
                    title_name=title_name,
                    asset_id=asset.id,
                    expected="absent",
                )
            )

    # bitrate mins / atmos — skip without bitrate metadata
    if isinstance(audio.get("bitrate_min_kbps"), dict):
        findings.append(
            _finding(
                rule_id="audio.bitrate_min_kbps",
                section="audio",
                status="skip",
                message="Audio bitrate / layout not fully available for min checks",
                title_id=title_id,
                title_name=title_name,
                asset_id=asset.id,
            )
        )

    # --- loudness ---
    lkfs_rule = loudness.get("integrated_lkfs") if isinstance(loudness.get("integrated_lkfs"), dict) else {}
    if lkfs_rule:
        # Look for common loudness keys in MediaInfo
        lkfs_raw = None
        for track in audio_tracks:
            for key in ("Loudness_Integrated", "IntegratedLoudness", "loudness_integrated"):
                if track.get(key) is not None:
                    lkfs_raw = track.get(key)
                    break
            if lkfs_raw is not None:
                break
        if lkfs_raw is None:
            findings.append(
                _finding(
                    rule_id="loudness.integrated_lkfs",
                    section="loudness",
                    status="skip",
                    message="Integrated loudness not measured",
                    title_id=title_id,
                    title_name=title_name,
                    asset_id=asset.id,
                    expected=f"{lkfs_rule.get('min')}..{lkfs_rule.get('max')} LKFS",
                )
            )
        else:
            try:
                lkfs = float(str(lkfs_raw).replace("LUFS", "").replace("LKFS", "").strip())
                lo = float(lkfs_rule.get("min"))
                hi = float(lkfs_rule.get("max"))
                ok = lo <= lkfs <= hi
                findings.append(
                    _finding(
                        rule_id="loudness.integrated_lkfs",
                        section="loudness",
                        status="pass" if ok else "fail",
                        message="Loudness in range" if ok else "Loudness out of range",
                        title_id=title_id,
                        title_name=title_name,
                        asset_id=asset.id,
                        observed=str(lkfs),
                        expected=f"{lo}..{hi}",
                    )
                )
            except (TypeError, ValueError):
                findings.append(
                    _finding(
                        rule_id="loudness.integrated_lkfs",
                        section="loudness",
                        status="skip",
                        message=f"Unparseable loudness: {lkfs_raw}",
                        title_id=title_id,
                        title_name=title_name,
                        asset_id=asset.id,
                    )
                )

    # --- integrity ---
    checksum_rule = integrity.get("checksum") if isinstance(integrity.get("checksum"), dict) else {}
    if checksum_rule.get("required"):
        has_checksum = bool((asset.checksum or "").strip())
        findings.append(
            _finding(
                rule_id="integrity.checksum",
                section="integrity",
                status="pass" if has_checksum else "fail",
                message="Checksum present" if has_checksum else "Checksum required but missing",
                title_id=title_id,
                title_name=title_name,
                asset_id=asset.id,
                observed=asset.checksum or None,
                expected="non-empty checksum",
            )
        )

    av_rule = integrity.get("av_duration_match") if isinstance(integrity.get("av_duration_match"), dict) else {}
    if av_rule:
        if not video_tracks or not audio_tracks:
            findings.append(
                _finding(
                    rule_id="integrity.av_duration_match",
                    section="integrity",
                    status="skip",
                    message="Need video and audio MediaInfo durations to compare",
                    title_id=title_id,
                    title_name=title_name,
                    asset_id=asset.id,
                )
            )
        else:
            vd = _track_duration_seconds(video_tracks[0])
            ad = _track_duration_seconds(audio_tracks[0])
            if vd is None or ad is None:
                findings.append(
                    _finding(
                        rule_id="integrity.av_duration_match",
                        section="integrity",
                        status="skip",
                        message="Video or audio duration missing",
                        title_id=title_id,
                        title_name=title_name,
                        asset_id=asset.id,
                    )
                )
            else:
                # Approximate 1-frame tolerance at 24fps ≈ 0.042s; use 0.05s floor
                tol_frames = int(av_rule.get("tolerance_frames") or 1)
                fr_raw = video_tracks[0].get("FrameRate") or 24
                try:
                    fr = float(fr_raw)
                except (TypeError, ValueError):
                    fr = 24.0
                tol = max(0.05, tol_frames / fr)
                ok = abs(vd - ad) <= tol
                findings.append(
                    _finding(
                        rule_id="integrity.av_duration_match",
                        section="integrity",
                        status="pass" if ok else "fail",
                        message="A/V durations match" if ok else "A/V durations differ beyond tolerance",
                        title_id=title_id,
                        title_name=title_name,
                        asset_id=asset.id,
                        observed=f"video={vd:.3f}s audio={ad:.3f}s",
                        expected=f"tolerance {tol_frames} frame(s)",
                    )
                )

    if isinstance(integrity.get("non_program_content"), dict):
        findings.append(
            _finding(
                rule_id="integrity.non_program_content",
                section="integrity",
                status="skip",
                message="Non-program content not measurable in v1",
                title_id=title_id,
                title_name=title_name,
                asset_id=asset.id,
                expected="absent",
            )
        )

    # --- manifest (package-level rules still recorded per asset run as skip) ---
    if manifest:
        findings.append(
            _finding(
                rule_id="manifest.inventory",
                section="manifest",
                status="skip",
                message="Inventory/manifest checks not measurable in v1",
                title_id=title_id,
                title_name=title_name,
                asset_id=asset.id,
                expected="every_file_in_inventory / no dangling refs / ratings_per_territory",
            )
        )

    return findings


def validate_package(db: Session, package_id: int) -> PackageValidationResponse:
    package = (
        db.query(DeliveryPackage)
        .options(
            joinedload(DeliveryPackage.profile),
            joinedload(DeliveryPackage.package_titles).joinedload(
                DeliveryPackageTitle.title
            ),
        )
        .filter(DeliveryPackage.id == package_id)
        .first()
    )
    if not package:
        raise ValueError("Package not found")
    if not package.profile_id or not package.profile:
        raise ValueError("Package has no delivery profile — assign a profile before validating")

    profile = package.profile
    spec = profile.spec
    findings: list[ValidationFinding] = []

    title_ids = [link.title_id for link in package.package_titles if link.title_id]
    assets_by_title: dict[int, list[MediaAsset]] = {tid: [] for tid in title_ids}
    if title_ids:
        assets = (
            db.query(MediaAsset)
            .filter(MediaAsset.title_id.in_(title_ids))
            .order_by(MediaAsset.id.asc())
            .all()
        )
        for asset in assets:
            assets_by_title.setdefault(asset.title_id, []).append(asset)

    if not title_ids:
        findings.append(
            _finding(
                rule_id="package.titles",
                section="package",
                status="skip",
                message="Package has no titles to validate",
            )
        )

    for link in package.package_titles:
        title = link.title
        if not title:
            continue
        asset = _pick_video_asset(assets_by_title.get(title.id, []))
        if not asset:
            findings.append(
                _finding(
                    rule_id="package.video_asset",
                    section="package",
                    status="skip",
                    message="No video_master/trailer asset found for title",
                    title_id=title.id,
                    title_name=title.name,
                )
            )
            continue
        findings.extend(
            validate_asset_against_spec(
                asset=asset,
                spec=spec,
                title_id=title.id,
                title_name=title.name,
            )
        )

    pass_count = sum(1 for f in findings if f.status == "pass")
    fail_count = sum(1 for f in findings if f.status == "fail")
    skip_count = sum(1 for f in findings if f.status == "skip")
    if fail_count:
        summary = "fail"
    elif pass_count == 0:
        summary = "incomplete"
    else:
        summary = "pass"

    return PackageValidationResponse(
        package_id=package.id,
        profile_id=profile.id,
        profile_slug=profile.slug,
        summary=summary,
        pass_count=pass_count,
        fail_count=fail_count,
        skip_count=skip_count,
        findings=findings,
    )
