from datetime import date

from app.database import Base, SessionLocal, engine
from app.models.media_asset import AssetStatus, AssetType, MediaAsset
from app.models.title import Title, TitleStatus, TitleType


def seed():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if db.query(Title).count() > 0:
            return
        series = Title(
            slug="neon-drift",
            name="Neon Drift",
            title_type=TitleType.SERIES,
            status=TitleStatus.PUBLISHED,
            synopsis="A cyberpunk crew races through megacity sprawl.",
            genres="Sci-Fi,Action",
            rating="TV-14",
            territories="US,CA,UK",
        )
        db.add(series)
        db.flush()

        season = Title(
            slug="neon-drift-s1",
            name="Neon Drift — Season 1",
            title_type=TitleType.SEASON,
            status=TitleStatus.PUBLISHED,
            parent_id=series.id,
            season_number=1,
        )
        db.add(season)
        db.flush()

        ep1 = Title(
            slug="neon-drift-s1e1",
            name="Gridlock",
            title_type=TitleType.EPISODE,
            status=TitleStatus.PUBLISHED,
            parent_id=season.id,
            season_number=1,
            episode_number=1,
            runtime_minutes=48,
            release_date=date(2025, 3, 1),
        )
        ep2 = Title(
            slug="neon-drift-s1e2",
            name="Ghost Lane",
            title_type=TitleType.EPISODE,
            status=TitleStatus.SCHEDULED,
            parent_id=season.id,
            season_number=1,
            episode_number=2,
            runtime_minutes=50,
            release_date=date(2025, 3, 8),
        )
        movie = Title(
            slug="midnight-express-lane",
            name="Midnight Express Lane",
            title_type=TitleType.MOVIE,
            status=TitleStatus.IN_REVIEW,
            synopsis="One night, one heist, no exits.",
            genres="Thriller",
            rating="R",
            runtime_minutes=112,
            release_date=date(2025, 6, 15),
            availability_start=date(2025, 6, 15),
            availability_end=date(2026, 6, 15),
        )
        db.add_all([ep1, ep2, movie])
        db.flush()

        assets = [
            MediaAsset(
                title_id=ep1.id,
                asset_type=AssetType.VIDEO_MASTER,
                status=AssetStatus.READY,
                filename="gridlock_master.mov",
                mime_type="video/quicktime",
                storage_uri="s3://masters/neon-drift/s1e1/gridlock_master.mov",
                size_bytes=48_000_000_000,
                resolution="3840x2160",
                duration_seconds=2880,
                codec="prores",
                checksum="sha256:abc123",
            ),
            MediaAsset(
                title_id=ep1.id,
                asset_type=AssetType.POSTER,
                status=AssetStatus.READY,
                filename="gridlock_poster.jpg",
                mime_type="image/jpeg",
                storage_uri="s3://artwork/neon-drift/s1e1/poster.jpg",
                size_bytes=2_400_000,
                resolution="2000x3000",
            ),
            MediaAsset(
                title_id=ep1.id,
                asset_type=AssetType.SUBTITLE,
                status=AssetStatus.READY,
                filename="gridlock_en.vtt",
                mime_type="text/vtt",
                storage_uri="s3://subtitles/neon-drift/s1e1/en.vtt",
                language="en",
            ),
            MediaAsset(
                title_id=movie.id,
                asset_type=AssetType.TRAILER,
                status=AssetStatus.PROCESSING,
                filename="mel_trailer.mp4",
                mime_type="video/mp4",
                storage_uri="s3://promo/midnight-express-lane/trailer.mp4",
                size_bytes=450_000_000,
                resolution="1920x1080",
                duration_seconds=120,
            ),
        ]
        db.add_all(assets)
        db.commit()
    finally:
        db.close()
