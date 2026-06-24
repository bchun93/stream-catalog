"""String-backed SQLAlchemy enums — avoids PG native enum / VARCHAR mismatches."""

import enum
from typing import TypeVar

from sqlalchemy import Enum

E = TypeVar("E", bound=enum.Enum)


def str_enum(enum_cls: type[E]) -> Enum:
    """Store Python str enums as lowercase VARCHAR values (not PG native enums)."""
    return Enum(
        enum_cls,
        values_callable=lambda members: [member.value for member in members],
        native_enum=False,
    )
