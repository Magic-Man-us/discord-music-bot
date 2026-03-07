"""Generic base for single-field frozen value objects."""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class ValueWrapper(BaseModel, Generic[T]):
    """Generic base for single-field frozen value objects.

    Provides positional construction (``TrackId("abc")``), hashing, equality,
    and str/int conversions.
    """

    model_config = ConfigDict(frozen=True)

    value: T  # type: ignore[misc]

    def __init__(self, value: T | None = None, /, **kwargs: object) -> None:
        if value is not None and "value" not in kwargs:
            kwargs["value"] = value
        super().__init__(**kwargs)

    def __str__(self) -> str:
        return str(self.value)

    def __int__(self) -> int:
        return int(self.value)  # type: ignore[arg-type]

    def __hash__(self) -> int:
        return hash(self.value)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, type(self)):
            return self.value == other.value
        return NotImplemented
