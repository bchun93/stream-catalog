"""Map Rekognition moderation labels and catalog ratings onto a shared rank."""

from __future__ import annotations

# Higher rank = more restricted. Unknown strings return None (skip comparison).
_RATING_RANK: dict[str, int] = {
    "g": 0,
    "tv-g": 0,
    "tv-y": 0,
    "pg": 1,
    "tv-pg": 1,
    "tv-y7": 1,
    "pg-13": 2,
    "tv-14": 2,
    "r": 3,
    "tv-ma": 3,
    "nc-17": 3,
    "ma": 3,
}

# Rekognition moderation v7 L1/L2 names (lowercased) -> implied minimum rank.
_LABEL_RANK: dict[str, int] = {
    "explicit": 3,
    "explicit nudity": 3,
    "violence": 2,
    "graphic violence": 3,
    "hate symbols": 3,
    "drugs & tobacco": 2,
    "drugs": 2,
    "tobacco": 2,
    "alcohol": 1,
    "gambling": 1,
}

_RANK_LABEL = {
    0: "G / TV-G",
    1: "PG / TV-PG",
    2: "PG-13 / TV-14",
    3: "R / TV-MA",
}


def rating_rank(rating: str | None) -> int | None:
    if not rating:
        return None
    return _RATING_RANK.get(rating.strip().lower())


def implied_rank(label_name: str | None, parent_name: str | None = None) -> int | None:
    for raw in (label_name, parent_name):
        if not raw:
            continue
        rank = _LABEL_RANK.get(raw.strip().lower())
        if rank is not None:
            return rank
    return None


def rank_label(rank: int) -> str:
    return _RANK_LABEL.get(rank, f"rank {rank}")
