"""Uniform slicing + shuffle for playlist imports.

Applied to Apple Music query strings and YouTube ``PlaylistEntry`` lists so
both paths honour ``start``, ``count``, and ``shuffle`` identically.
"""

from __future__ import annotations

import random
from typing import TypeVar

from pydantic import BaseModel, ConfigDict

from ..domain.shared.constants import PlaylistConstants
from ..domain.shared.types import (
    NonNegativeInt,
    PlaylistImportCount,
    PlaylistStartIndex,
)

T = TypeVar("T")


class PlaylistSlice(BaseModel):
    """Summary of which playlist positions were selected.

    ``truncated`` reports how many items past the kept slice were dropped,
    so callers can render "queuing 10 of 42 tracks" honestly.
    """

    model_config = ConfigDict(frozen=True)

    items_indices: tuple[int, ...]
    total: NonNegativeInt
    start: PlaylistStartIndex
    requested_count: PlaylistImportCount
    shuffled: bool

    @property
    def kept(self) -> int:
        return len(self.items_indices)

    @property
    def truncated(self) -> int:
        remaining_after_start = max(0, self.total - self.start + 1)
        return max(0, remaining_after_start - self.kept)


def select_playlist_items(
    items: list[T],
    *,
    start: PlaylistStartIndex | None = None,
    count: PlaylistImportCount | None = None,
    shuffle: bool = False,
    default_count: PlaylistImportCount = PlaylistConstants.EXTERNAL_PLAYLIST_DEFAULT_COUNT,
    max_count: PlaylistImportCount = PlaylistConstants.MAX_PLAYLIST_TRACKS,
) -> tuple[list[T], PlaylistSlice]:
    """Return a new list of selected items plus a slice summary.

    Semantics:
      1. ``start`` (1-based) drops items before that position.
      2. ``count`` (or ``default_count``) caps the remainder, never above
         ``max_count``.
      3. ``shuffle`` randomises the final selection.

    Out-of-range ``start`` yields an empty selection (no error raised).
    """
    total = len(items)
    resolved_start = start if start is not None else 1
    resolved_count = count if count is not None else default_count
    effective_count = min(resolved_count, max_count)

    if resolved_start > total:
        selection_indices: list[int] = []
    else:
        offset = resolved_start - 1
        selection_indices = list(range(offset, min(offset + effective_count, total)))

    selected = [items[i] for i in selection_indices]
    if shuffle:
        paired = list(zip(selection_indices, selected, strict=True))
        random.shuffle(paired)
        selection_indices = [i for i, _ in paired]
        selected = [item for _, item in paired]

    summary = PlaylistSlice(
        items_indices=tuple(selection_indices),
        total=total,
        start=resolved_start,
        requested_count=resolved_count,
        shuffled=shuffle,
    )
    return selected, summary
