#!/usr/bin/env python3
"""Download titles from a deployed stream-catalog API and restore into local SQLite."""
from __future__ import annotations

import argparse
import json
import sys
from collections import deque
from datetime import date, datetime
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.database import SessionLocal  # noqa: E402
from app.models.media_asset import MediaAsset  # noqa: E402
from app.models.title import Title, TitleStatus, TitleType  # noqa: E402


def fetch_titles(cloud_url: str) -> list[dict]:
    url = f"{cloud_url.rstrip('/')}/api/v1/titles"
    with httpx.Client(timeout=120.0) as client:
        resp = client.get(url, params={"limit": 500})
        resp.raise_for_status()
        data = resp.json()
    if not isinstance(data, list):
        raise RuntimeError(f"Unexpected response from {url}: {type(data)}")
    return data


def sort_parents_first(titles: list[dict]) -> list[dict]:
    by_id = {t["id"]: t for t in titles}
    children: dict[int | None, list[dict]] = {}
    for t in titles:
        children.setdefault(t.get("parent_id"), []).append(t)

    ordered: list[dict] = []
    queue: deque[int | None] = deque([None])
    seen: set[int] = set()
    while queue:
        parent_id = queue.popleft()
        for t in children.get(parent_id, []):
            tid = t["id"]
            if tid in seen:
                continue
            seen.add(tid)
            ordered.append(t)
            queue.append(tid)

    # Append any orphans not reachable from roots
    for t in titles:
        if t["id"] not in seen:
            ordered.append(t)
    return ordered


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def import_titles(titles: list[dict]) -> int:
    db = SessionLocal()
    try:
        db.query(MediaAsset).delete()
        db.query(Title).delete()
        db.commit()

        id_map: dict[int, int] = {}
        for raw in sort_parents_first(titles):
            cloud_id = raw["id"]
            cloud_parent = raw.get("parent_id")
            parent_id = id_map.get(cloud_parent) if cloud_parent else None

            title = Title(
                slug=raw["slug"],
                name=raw["name"],
                title_type=TitleType(raw["title_type"]),
                status=TitleStatus(raw["status"]),
                synopsis=raw.get("synopsis"),
                short_description=raw.get("short_description"),
                release_date=parse_date(raw.get("release_date")),
                rating=raw.get("rating"),
                genres=raw.get("genres"),
                territories=raw.get("territories"),
                availability_start=parse_date(raw.get("availability_start")),
                availability_end=parse_date(raw.get("availability_end")),
                parent_id=parent_id,
                season_number=raw.get("season_number"),
                episode_number=raw.get("episode_number"),
                runtime_minutes=raw.get("runtime_minutes"),
                release_year=raw.get("release_year"),
                licensor=raw.get("licensor"),
                studio=raw.get("studio"),
                cast=raw.get("cast"),
                crew=raw.get("crew"),
                eidr=raw.get("eidr"),
                external_id=raw.get("external_id"),
                metadata_source=raw.get("metadata_source"),
                poster_url=raw.get("poster_url"),
                metadata_json=raw.get("metadata_json"),
                internal_id=raw.get("internal_id"),
            )
            created = parse_datetime(raw.get("created_at"))
            updated = parse_datetime(raw.get("updated_at"))
            if created:
                title.created_at = created.replace(tzinfo=None)
            if updated:
                title.updated_at = updated.replace(tzinfo=None)

            db.add(title)
            db.flush()
            id_map[cloud_id] = title.id

        db.commit()
        return len(id_map)
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cloud-url",
        default="https://stream-catalog.onrender.com",
        help="Deployed API base URL",
    )
    parser.add_argument(
        "--backup",
        type=Path,
        default=ROOT / "data" / "cloud-titles-backup.json",
        help="Where to write a JSON backup of cloud titles",
    )
    args = parser.parse_args()

    print(f"Fetching titles from {args.cloud_url} ...")
    titles = fetch_titles(args.cloud_url)
    print(f"Downloaded {len(titles)} titles")

    args.backup.parent.mkdir(parents=True, exist_ok=True)
    args.backup.write_text(json.dumps(titles, indent=2), encoding="utf-8")
    print(f"Backup written to {args.backup}")

    count = import_titles(titles)
    print(f"Imported {count} titles into local database")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
