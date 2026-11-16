"""Pure picture-QC rule tests. No AWS."""

import unittest

from app.services.rekognition.evaluate import evaluate
from app.services.rekognition.rating_policy import implied_rank, rating_rank


def _seg(kind: str, start: int, end: int) -> dict:
    return {
        "feature": "SEGMENT",
        "kind": kind,
        "start_ms": start,
        "end_ms": end,
    }


def _mod(kind: str, parent: str, ts: int) -> dict:
    return {
        "feature": "MODERATION",
        "kind": kind,
        "name": parent,
        "timestamp_ms": ts,
    }


def _label(name: str, ts: int) -> dict:
    return {"feature": "LABELS", "kind": name, "name": name, "timestamp_ms": ts}


def _text(name: str, ts: int, kind: str = "LINE") -> dict:
    return {"feature": "TEXT", "kind": kind, "name": name, "timestamp_ms": ts}


class RatingPolicyTests(unittest.TestCase):
    def test_ranks(self) -> None:
        self.assertEqual(rating_rank("TV-PG"), 1)
        self.assertEqual(implied_rank("Explicit", None), 3)
        self.assertGreater(implied_rank("Explicit", None) or 0, rating_rank("TV-PG") or 0)


class EvaluateTests(unittest.TestCase):
    def _ids(self, findings) -> set[str]:
        return {f.rule_id for f in findings}

    def test_missing_content_is_error(self) -> None:
        findings = evaluate([_seg("BlackFrames", 0, 1000)])
        self.assertIn("REKO_MISSING_CONTENT", self._ids(findings))
        self.assertIn("REKO_NONPROGRAM_PRESENT", self._ids(findings))
        missing = next(f for f in findings if f.rule_id == "REKO_MISSING_CONTENT")
        self.assertEqual(missing.severity, "error")

    def test_program_rules_on_feature_length_content(self) -> None:
        content_end = 25 * 60 * 1000
        rows = [
            _seg("Content", 0, content_end),
            _seg("ColorBars", 1000, 4000),
            _seg("BlackFrames", 60_000, 61_000),
            _text("HELLO", 90_000),
            _label("Smoking", 80_000),
            _mod("Explicit", "Explicit", 70_000),
        ]
        findings = evaluate(rows, title_rating="TV-PG")
        ids = self._ids(findings)
        self.assertNotIn("REKO_MISSING_CONTENT", ids)
        self.assertIn("REKO_NONPROGRAM_IN_CONTENT", ids)
        self.assertIn("REKO_MISSING_END_CREDITS", ids)
        self.assertIn("REKO_MID_PROGRAM_BLACK", ids)
        self.assertIn("REKO_BURNED_IN_TEXT", ids)
        self.assertIn("REKO_WATCH_LABEL", ids)
        self.assertIn("REKO_RATING_SIGNAL", ids)

    def test_text_outside_program_body_ignored(self) -> None:
        rows = [
            _seg("Content", 0, 120_000),
            _seg("OpeningCredits", 0, 10_000),
            _seg("EndCredits", 100_000, 120_000),
            _text("STUDIO", 2_000),
            _text("THE END", 110_000),
        ]
        findings = evaluate(rows)
        self.assertNotIn("REKO_BURNED_IN_TEXT", self._ids(findings))

    def test_watch_label_outside_content_ignored(self) -> None:
        rows = [_seg("Content", 10_000, 20_000), _label("Weapon", 1_000)]
        self.assertNotIn("REKO_WATCH_LABEL", self._ids(evaluate(rows)))

    def test_rating_signal_skipped_without_catalog_rating(self) -> None:
        rows = [_seg("Content", 0, 30_000), _mod("Explicit", "Explicit", 5_000)]
        self.assertNotIn("REKO_RATING_SIGNAL", self._ids(evaluate(rows)))

    def test_duration_mismatch(self) -> None:
        rows = [_seg("Content", 0, 5_000)]
        findings = evaluate(
            rows,
            media_meta={"video": {"DurationMillis": 10_000}},
            asset_duration_seconds=5.0,
        )
        self.assertIn("REKO_DURATION_MISMATCH", self._ids(findings))

    def test_duration_within_tolerance(self) -> None:
        rows = [_seg("Content", 0, 5_000)]
        findings = evaluate(
            rows,
            media_meta={"video": {"DurationMillis": 5_400}},
            asset_duration_seconds=5.0,
        )
        self.assertNotIn("REKO_DURATION_MISMATCH", self._ids(findings))

    def test_end_credits_present_skips_missing_rule(self) -> None:
        content_end = 25 * 60 * 1000
        rows = [
            _seg("Content", 0, content_end),
            _seg("EndCredits", content_end - 30_000, content_end),
        ]
        self.assertNotIn("REKO_MISSING_END_CREDITS", self._ids(evaluate(rows)))

    def test_ignores_existing_finding_rows(self) -> None:
        rows = [
            _seg("BlackFrames", 0, 500),
            {"feature": "FINDING", "kind": "REKO_MISSING_CONTENT", "severity": "error"},
        ]
        findings = evaluate(rows)
        self.assertEqual(
            1, sum(1 for f in findings if f.rule_id == "REKO_MISSING_CONTENT")
        )


if __name__ == "__main__":
    unittest.main()
