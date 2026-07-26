import json
import unittest
from datetime import date
from unittest.mock import patch

from app.models.title import Title, TitleStatus, TitleType
from app.services.mec_service import (
    MecValidationError,
    build_mec_xml,
    generate_and_store,
    mec_filename,
)


def _movie(**kwargs) -> Title:
    defaults = dict(
        id=42,
        slug="cucamonga-2019",
        name="Cucamonga",
        title_type=TitleType.MOVIE,
        status=TitleStatus.PUBLISHED,
        synopsis="A long synopsis about the desert and the sky above it.",
        short_description="Desert skies.",
        release_date=date(2019, 6, 1),
        release_year=2019,
        rating="PG-13",
        genres="Adventure, Drama",
        runtime_minutes=98,
        studio="Relay Pictures",
        cast="Alice Actor, Bob Actor",
        eidr="10.5240/ABCD-EFGH-IJKL-MNOP-QRST-U",
        internal_id="MOV-42",
        metadata_json=json.dumps(
            {
                "copyright_line": "Copyright 2019 Relay Pictures",
                "language": "en",
                "origin": "US",
                "directors": "Carol Director",
                "writers": "Dan Writer",
            }
        ),
        poster_url="https://example.com/poster.jpg",
    )
    defaults.update(kwargs)
    return Title(**defaults)


class MecServiceTests(unittest.TestCase):
    def test_build_mec_xml_contains_core_fields(self):
        xml = build_mec_xml(_movie()).decode("utf-8")
        self.assertIn("mdmec:CoreMetadata", xml)
        self.assertIn("Cucamonga", xml)
        self.assertIn("md:cid:org:relay:MOV-42", xml)
        self.assertIn("2019", xml)
        self.assertIn("10.5240/ABCD-EFGH-IJKL-MNOP-QRST-U", xml)
        self.assertIn("Carol Director", xml)
        self.assertIn("Alice Actor", xml)
        self.assertIn("Adventure", xml)
        self.assertIn("Copyright 2019 Relay Pictures", xml)
        self.assertIn("WorkType", xml)
        self.assertIn("Movie", xml)
        self.assertIn("PT1H38M", xml)
        # Pretty-printed: elements on their own indented lines
        self.assertIn("\n  <mdmec:Basic", xml)
        self.assertIn("\n    <md:LocalizedInfo", xml)
        self.assertGreater(xml.count("\n"), 10)

    def test_rejects_non_movie(self):
        title = _movie(title_type=TitleType.SERIES, name="A Series")
        with self.assertRaises(MecValidationError) as ctx:
            build_mec_xml(title)
        self.assertIn("movie", str(ctx.exception).lower())

    def test_rejects_empty_name(self):
        title = _movie(name="  ")
        with self.assertRaises(MecValidationError) as ctx:
            build_mec_xml(title)
        self.assertIn("title", str(ctx.exception).lower())

    def test_rejects_missing_poster(self):
        title = _movie(poster_url=None)
        with self.assertRaises(MecValidationError) as ctx:
            build_mec_xml(title)
        self.assertIn("artreference", str(ctx.exception).lower())

    def test_rejects_missing_release_year(self):
        title = _movie(release_year=None, release_date=None, metadata_json="{}")
        with self.assertRaises(MecValidationError) as ctx:
            build_mec_xml(title)
        self.assertIn("releaseyear", str(ctx.exception).lower().replace(" ", ""))

    def test_rejects_unmappable_genre(self):
        title = _movie(genres="Western, Crime")
        with self.assertRaises(MecValidationError) as ctx:
            build_mec_xml(title)
        self.assertIn("genre", str(ctx.exception).lower())

    def test_maps_sci_fi_alias(self):
        xml = build_mec_xml(_movie(genres="Sci-Fi")).decode("utf-8")
        self.assertIn(">Science Fiction</md:Genre>", xml)
        self.assertIn("mec_primary_genre.html", xml)
        self.assertIn('default="true"', xml)

    def test_mec_filename(self):
        self.assertEqual(mec_filename(_movie()), "cucamonga-2019-42-mec.xml")

    def test_generate_and_store_puts_to_s3(self):
        title = _movie()
        with patch("app.services.mec_service.s3_service.put_bytes") as put:
            put.return_value = (
                "deliveries/inbound/mec/cucamonga-2019-42-mec.xml",
                "s3://stream-catalog-ingest/deliveries/inbound/mec/cucamonga-2019-42-mec.xml",
            )
            result = generate_and_store(title)
        put.assert_called_once()
        kwargs = put.call_args.kwargs
        self.assertEqual(kwargs["relative_prefix"], "mec")
        self.assertEqual(kwargs["filename"], "cucamonga-2019-42-mec.xml")
        self.assertEqual(kwargs["content_type"], "application/xml")
        self.assertTrue(kwargs["body"].startswith(b"<?xml"))
        self.assertEqual(result.title_id, 42)
        self.assertIn("Cucamonga", result.xml)
        self.assertTrue(result.storage_uri.startswith("s3://"))


if __name__ == "__main__":
    unittest.main()
