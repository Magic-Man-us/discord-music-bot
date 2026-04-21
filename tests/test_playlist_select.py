"""Tests for the shared playlist slicer used by /play imports."""

from __future__ import annotations

import random

import pytest

from discord_music_player.domain.shared.constants import PlaylistConstants
from discord_music_player.utils.playlist_select import (
    PlaylistSlice,
    select_playlist_items,
)


@pytest.fixture
def sample() -> list[str]:
    return [f"track-{i}" for i in range(1, 26)]


class TestDefaults:
    def test_no_args_yields_default_count(self, sample: list[str]) -> None:
        items, info = select_playlist_items(sample)
        assert len(items) == PlaylistConstants.EXTERNAL_PLAYLIST_DEFAULT_COUNT
        assert items == sample[: PlaylistConstants.EXTERNAL_PLAYLIST_DEFAULT_COUNT]
        assert info.kept == PlaylistConstants.EXTERNAL_PLAYLIST_DEFAULT_COUNT
        assert info.start == 1
        assert info.total == 25
        assert info.shuffled is False

    def test_truncated_reports_the_skipped_count(self, sample: list[str]) -> None:
        _, info = select_playlist_items(sample, count=5)
        assert info.truncated == 20


class TestCount:
    def test_caps_at_count(self, sample: list[str]) -> None:
        items, info = select_playlist_items(sample, count=3)
        assert items == sample[:3]
        assert info.kept == 3

    def test_count_above_max_is_capped_to_max(self) -> None:
        big = [f"t{i}" for i in range(200)]
        items, info = select_playlist_items(big, count=PlaylistConstants.MAX_PLAYLIST_TRACKS)
        assert len(items) == PlaylistConstants.MAX_PLAYLIST_TRACKS
        assert info.requested_count == PlaylistConstants.MAX_PLAYLIST_TRACKS

    def test_count_above_playlist_size_returns_all_items(self, sample: list[str]) -> None:
        items, info = select_playlist_items(sample, count=PlaylistConstants.MAX_PLAYLIST_TRACKS)
        assert items == sample
        assert info.truncated == 0


class TestStart:
    def test_start_shifts_window(self, sample: list[str]) -> None:
        items, info = select_playlist_items(sample, start=10, count=5)
        assert items == sample[9:14]
        assert info.start == 10
        assert info.kept == 5

    def test_start_past_end_returns_empty(self, sample: list[str]) -> None:
        items, info = select_playlist_items(sample, start=999, count=5)
        assert items == []
        assert info.kept == 0

    def test_start_combined_with_default_count(self, sample: list[str]) -> None:
        items, _ = select_playlist_items(sample, start=20)
        assert items == sample[19:25]  # default 10, but only 6 left

    def test_start_1_is_identity(self, sample: list[str]) -> None:
        items_default, _ = select_playlist_items(sample, count=5)
        items_explicit, _ = select_playlist_items(sample, start=1, count=5)
        assert items_default == items_explicit


class TestShuffle:
    def test_shuffle_produces_same_multiset(self, sample: list[str]) -> None:
        random.seed(0)
        items, info = select_playlist_items(sample, count=10, shuffle=True)
        assert info.shuffled is True
        assert sorted(items) == sorted(sample[:10])

    def test_shuffle_touches_order(self, sample: list[str]) -> None:
        random.seed(42)
        items, _ = select_playlist_items(sample, count=25, shuffle=True)
        assert items != sample  # seeded shuffle reorders

    def test_shuffle_does_not_mutate_input(self, sample: list[str]) -> None:
        before = list(sample)
        select_playlist_items(sample, count=10, shuffle=True)
        assert sample == before

    def test_shuffle_respects_start_window(self, sample: list[str]) -> None:
        random.seed(0)
        items, _ = select_playlist_items(sample, start=15, count=5, shuffle=True)
        # Only tracks 15-19 should be candidates regardless of shuffle.
        assert sorted(items) == sorted(sample[14:19])


class TestSliceSummary:
    def test_is_pydantic_frozen(self) -> None:
        _, info = select_playlist_items(["a", "b"], count=1)
        assert isinstance(info, PlaylistSlice)
        with pytest.raises(Exception):  # frozen model
            info.total = 9999  # type: ignore[misc]

    def test_indices_match_selected_items(self) -> None:
        items = ["a", "b", "c", "d", "e"]
        selected, info = select_playlist_items(items, start=2, count=3)
        assert [items[i] for i in info.items_indices] == selected
