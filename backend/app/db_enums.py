"""String-backed SQLAlchemy enums — avoids PG native enum / VARCHAR mismatches."""

import enum
from typing import TypeVar

from sqlalchemy import String
from sqlalchemy.types import TypeDecorator

E = TypeVar("E", bound=enum.Enum)


def _coerce_enum(enum_cls: type[E], value: object) -> E:
    if isinstance(value, enum_cls):
        return value
    text = str(value)
    if text in enum_cls.__members__:
        return enum_cls[text]
    return enum_cls(text.lower())


def _enum_bind_value(enum_cls: type[E], value: object) -> str:
    if value is None:
        raise TypeError("enum bind value cannot be None")
    if isinstance(value, enum_cls):
        return value.value
    text = str(value)
    if text in enum_cls.__members__:
        return enum_cls[text].value
    return text.lower()


def str_enum(enum_cls: type[E], *, length: int = 32) -> TypeDecorator:
    """Store Python str enums as lowercase VARCHAR; read legacy uppercase safely."""

    class CaseInsensitiveStrEnum(TypeDecorator):
        impl = String(length)
        cache_ok = True

        def process_bind_param(self, value: object | None, dialect) -> str | None:
            if value is None:
                return None
            return _enum_bind_value(enum_cls, value)

        def process_result_value(self, value: object | None, dialect) -> E | None:
            if value is None:
                return None
            return _coerce_enum(enum_cls, value)

    return CaseInsensitiveStrEnum()
