"""Build MovieLabs Media Entertainment Core (MEC) v2.25 XML from a Relay Title.

Maps title columns + metadata_json core keys into a minimal mdmec:CoreMetadata
document suitable for retailer handoff. Series/TV and MMC are out of scope for v1.

Schema: https://www.movielabs.com/schema/mdmec/v2.25/mdmec-v2.25.xsd
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import date, datetime
from xml.etree.ElementTree import Element, SubElement, indent, tostring

from app.config import settings
from app.models.title import Title, TitleType
from app.services import s3_service

logger = logging.getLogger(__name__)

MDMEC_NS = "http://www.movielabs.com/schema/mdmec/v2.25"
MD_NS = "http://www.movielabs.com/schema/md/v2.25/md"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
SCHEMA_LOCATION = (
    f"{MDMEC_NS} https://www.movielabs.com/schema/mdmec/v2.25/mdmec-v2.25.xsd"
)
MEC_GENRE_SOURCE = "http://www.movielabs.com/md/mec/mec_primary_genre.html"

# Official MEC primary genres (case-insensitive match; emit canonical spelling).
MEC_PRIMARY_GENRES: dict[str, str] = {
    name.casefold(): name
    for name in (
        "Action",
        "Adventure",
        "Anime",
        "Children's",
        "Comedy",
        "Documentary",
        "Drama",
        "Erotic",
        "Faith and Spirituality",
        "Family",
        "Fantasy",
        "Horror",
        "Instructional",
        "Live Performance",
        "Musical",
        "Mystery",
        "Reality",
        "Romance",
        "Science Fiction",
        "Sports",
        "Thriller",
        "Variety/Talk Show",
        "Miscellaneous",
    )
}

# Common catalog / TMDB labels → MEC primary genre.
_GENRE_ALIASES: dict[str, str] = {
    "sci-fi": "Science Fiction",
    "scifi": "Science Fiction",
    "science-fiction": "Science Fiction",
    "kids": "Children's",
    "children": "Children's",
    "childrens": "Children's",
    "children's": "Children's",
    "sport": "Sports",
    "talk show": "Variety/Talk Show",
    "variety": "Variety/Talk Show",
    "faith": "Faith and Spirituality",
    "spirituality": "Faith and Spirituality",
    "religious": "Faith and Spirituality",
    "concert": "Live Performance",
    "live": "Live Performance",
    "educational": "Instructional",
    "howto": "Instructional",
    "how-to": "Instructional",
    "music": "Musical",
}

# Register prefixes so tostring emits md: / mdmec: instead of ns0:
for prefix, uri in (("mdmec", MDMEC_NS), ("md", MD_NS), ("xsi", XSI_NS)):
    # ElementTree.register_namespace is process-global; safe for our fixed prefixes.
    from xml.etree.ElementTree import register_namespace

    register_namespace(prefix, uri)


class MecValidationError(ValueError):
    """Missing required title data for MEC generation."""


@dataclass
class MecGenerateResult:
    title_id: int
    filename: str
    storage_uri: str | None
    content_type: str
    xml: str
    stored: bool = True
    warning: str | None = None


def _core(title: Title) -> dict[str, str]:
    raw = (title.metadata_json or "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    out: dict[str, str] = {}
    for key, value in parsed.items():
        if isinstance(value, str) and value.strip():
            out[str(key)] = value.strip()
    return out


def _first(*values: str | None) -> str | None:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _split_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    parts = re.split(r"[,;\n]+", raw)
    return [p.strip() for p in parts if p.strip()]


def _content_id(title: Title) -> str:
    token = _first(title.internal_id, title.slug, str(title.id) if title.id else None)
    if not token:
        raise MecValidationError("Missing ContentID (need internal_id, slug, or id).")
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", token).strip("-._") or f"title-{title.id}"
    return f"md:cid:org:relay:{safe}"


def _run_length(minutes: int | None) -> str | None:
    if minutes is None or minutes < 0:
        return None
    hours, mins = divmod(int(minutes), 60)
    if hours and mins:
        return f"PT{hours}H{mins}M"
    if hours:
        return f"PT{hours}H"
    return f"PT{mins}M"


def _release_date_text(title: Title, core: dict[str, str]) -> str | None:
    if title.release_date:
        return title.release_date.isoformat()
    raw = core.get("release_date")
    if not raw:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _map_mec_genre(raw: str) -> str | None:
    key = raw.strip().casefold()
    if not key:
        return None
    if key in MEC_PRIMARY_GENRES:
        return MEC_PRIMARY_GENRES[key]
    aliased = _GENRE_ALIASES.get(key)
    if aliased:
        return aliased
    return None


def _resolve_primary_genre(genres: list[str]) -> str:
    """Return a MEC-vocab primary genre or raise with a clear missing-fields message."""
    for candidate in genres:
        mapped = _map_mec_genre(candidate)
        if mapped:
            return mapped
    if not genres:
        raise MecValidationError(
            "Missing primary genre (need a MovieLabs MEC genre such as Drama, Action, or Comedy)."
        )
    raise MecValidationError(
        "No mappable MEC primary genre from "
        f"{', '.join(genres)}. Use a MovieLabs genre "
        "(e.g. Drama, Action, Adventure, Comedy, Science Fiction)."
    )


def _release_year(title: Title, core: dict[str, str], release_date: str | None) -> int | None:
    if title.release_year:
        return int(title.release_year)
    raw = core.get("initial_release_year") or core.get("latest_release_year")
    if raw and raw.isdigit():
        return int(raw)
    if release_date and len(release_date) >= 4 and release_date[:4].isdigit():
        return int(release_date[:4])
    return None


def _runtime_minutes(title: Title, core: dict[str, str]) -> int | None:
    if title.runtime_minutes is not None:
        return int(title.runtime_minutes)
    raw = core.get("runtime")
    if raw and raw.isdigit():
        return int(raw)
    return None


def _sub(parent: Element, ns: str, tag: str, text: str | None = None) -> Element:
    el = SubElement(parent, f"{{{ns}}}{tag}")
    if text is not None:
        el.text = text
    return el


def _add_people(basic: Element, job_function: str, names: list[str]) -> None:
    for name in names:
        people = _sub(basic, MD_NS, "People")
        job = _sub(people, MD_NS, "Job")
        _sub(job, MD_NS, "JobFunction", job_function)
        name_el = _sub(people, MD_NS, "Name")
        _sub(name_el, MD_NS, "DisplayName", name)


def build_mec_xml(title: Title) -> bytes:
    """Return UTF-8 MEC XML bytes for a movie title."""
    if title.title_type != TitleType.MOVIE:
        raise MecValidationError("MEC generation is only supported for movie titles.")

    display_title = _first(title.name)
    if not display_title:
        raise MecValidationError("Missing display title (name).")

    art_uri = _first(title.poster_url)
    if not art_uri:
        raise MecValidationError(
            "Missing ArtReference (need poster_url / artwork on the title)."
        )

    content_id = _content_id(title)
    core = _core(title)

    synopsis = _first(title.synopsis, core.get("synopsis"))
    short = _first(title.short_description, core.get("short_synopsis"))
    release_date = _release_date_text(title, core)
    year = _release_year(title, core, release_date)
    if year is None:
        raise MecValidationError(
            "Missing ReleaseYear (need release_year or initial_release_year)."
        )
    runtime = _runtime_minutes(title, core)
    rating = _first(title.rating, core.get("rating"))
    genre_candidates = _split_list(_first(title.genres, core.get("genre")))
    primary_genre = _resolve_primary_genre(genre_candidates)
    studio = _first(title.studio, core.get("studio"))
    copyright_line = _first(
        core.get("copyright_line"),
        f"Copyright {year} {studio}".strip() if studio else f"Copyright {year}",
        f"Copyright {display_title}",
    )
    language = _first(core.get("language"), "en")
    # LocalizedInfo @language expects BCP-47-ish; keep short codes as-is.
    loc_lang = language if "-" in language or len(language) > 2 else f"{language}-US"
    origin = _first(core.get("origin"), "US")
    origin_token = origin.split(",")[0].strip()
    if re.fullmatch(r"[A-Za-z]{2}", origin_token):
        origin_country = origin_token.upper()
    else:
        origin_country = "US"

    actors = _split_list(_first(title.cast, core.get("actors")))
    directors = _split_list(core.get("directors"))
    writers = _split_list(core.get("writers"))
    # Lightweight crew parse: "Director: Name" lines if present
    if title.crew and not directors:
        for part in _split_list(title.crew):
            lower = part.lower()
            if lower.startswith("director"):
                name = re.split(r"[:\-–]", part, maxsplit=1)
                if len(name) > 1 and name[1].strip():
                    directors.append(name[1].strip())

    root = Element(
        f"{{{MDMEC_NS}}}CoreMetadata",
        {
            f"{{{XSI_NS}}}schemaLocation": SCHEMA_LOCATION,
        },
    )
    basic = _sub(root, MDMEC_NS, "Basic")
    basic.set("ContentID", content_id)

    localized = _sub(basic, MD_NS, "LocalizedInfo")
    localized.set("language", loc_lang)
    localized.set("default", "true")
    _sub(localized, MD_NS, "TitleDisplayUnlimited", display_title)
    _sub(localized, MD_NS, "TitleSort", display_title)
    art = _sub(localized, MD_NS, "ArtReference", art_uri)
    art.set("purpose", "cover")
    if short:
        summary190 = short[:190]
        _sub(localized, MD_NS, "Summary190", summary190)
    if synopsis:
        _sub(localized, MD_NS, "Summary400", synopsis[:400])
        if len(synopsis) > 400:
            _sub(localized, MD_NS, "Summary4000", synopsis[:4000])
    elif short:
        _sub(localized, MD_NS, "Summary400", short[:400])

    genre_el = _sub(localized, MD_NS, "Genre", primary_genre)
    genre_el.set("source", MEC_GENRE_SOURCE)
    genre_el.set("level", "0")
    seen_genres = {primary_genre}
    for extra in genre_candidates:
        mapped = _map_mec_genre(extra)
        if mapped and mapped not in seen_genres:
            seen_genres.add(mapped)
            g = _sub(localized, MD_NS, "Genre", mapped)
            g.set("source", MEC_GENRE_SOURCE)
            g.set("level", "1")

    _sub(localized, MD_NS, "OriginalTitle", display_title)
    _sub(localized, MD_NS, "CopyrightLine", copyright_line or f"Copyright {display_title}")

    run = _run_length(runtime)
    if run:
        _sub(basic, MD_NS, "RunLength", run)
    _sub(basic, MD_NS, "ReleaseYear", str(year))
    if release_date:
        _sub(basic, MD_NS, "ReleaseDate", release_date)
    _sub(basic, MD_NS, "WorkType", "Movie")

    if title.eidr:
        alt = _sub(basic, MD_NS, "AltIdentifier")
        _sub(alt, MD_NS, "Namespace", "EIDR")
        _sub(alt, MD_NS, "Identifier", title.eidr.strip())

    if rating:
        rating_set = _sub(basic, MD_NS, "RatingSet")
        rating_el = _sub(rating_set, MD_NS, "Rating")
        region = _sub(rating_el, MD_NS, "Region")
        _sub(region, MD_NS, "country", "US")
        _sub(rating_el, MD_NS, "System", "MPAA")
        _sub(rating_el, MD_NS, "Value", rating)

    _add_people(basic, "Director", directors)
    _add_people(basic, "Writer", writers)
    _add_people(basic, "Actor", actors)

    country = _sub(basic, MD_NS, "CountryOfOrigin")
    _sub(country, MD_NS, "country", origin_country)
    _sub(basic, MD_NS, "PrimarySpokenLanguage", language[:8])

    if studio:
        org = _sub(basic, MD_NS, "AssociatedOrg")
        org.set("role", "licensor")
        _sub(org, MD_NS, "DisplayName", studio)

    # Pretty-print for human-readable retailer handoff (compact XML is still valid MEC).
    indent(root, space="  ")
    xml_bytes = tostring(root, encoding="utf-8", xml_declaration=True)
    return xml_bytes


def mec_filename(title: Title) -> str:
    slug = _first(title.slug, title.internal_id, f"title-{title.id}") or f"title-{title.id}"
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", slug).strip("-._") or f"title-{title.id}"
    return f"{safe}-{title.id}-mec.xml"


def generate_and_store(title: Title) -> MecGenerateResult:
    """Build MEC XML, store in ingest S3 when configured, always return XML for download."""
    xml_bytes = build_mec_xml(title)
    filename = mec_filename(title)
    xml_text = xml_bytes.decode("utf-8")

    bucket = (settings.ingest_s3_bucket or "").strip()
    if not bucket:
        logger.warning(
            "MEC generate for title %s: INGEST_S3_BUCKET unset — returning download-only XML",
            title.id,
        )
        return MecGenerateResult(
            title_id=title.id,
            filename=filename,
            storage_uri=None,
            content_type="application/xml",
            xml=xml_text,
            stored=False,
            warning=(
                "INGEST_S3_BUCKET is not configured on the API — XML was generated for "
                "download only. Set INGEST_S3_BUCKET on Render (or local .env) to also "
                "store under the ingest bucket."
            ),
        )

    try:
        _key, uri = s3_service.put_bytes(
            relative_prefix="mec",
            filename=filename,
            body=xml_bytes,
            content_type="application/xml",
        )
    except Exception:
        logger.exception("MEC S3 put failed for title %s — returning download-only XML", title.id)
        return MecGenerateResult(
            title_id=title.id,
            filename=filename,
            storage_uri=None,
            content_type="application/xml",
            xml=xml_text,
            stored=False,
            warning=(
                "Could not write MEC to S3 — XML was generated for download only. "
                "Check AWS credentials and INGEST_S3_BUCKET."
            ),
        )

    return MecGenerateResult(
        title_id=title.id,
        filename=filename,
        storage_uri=uri,
        content_type="application/xml",
        xml=xml_text,
        stored=True,
        warning=None,
    )
