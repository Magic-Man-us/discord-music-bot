"""Tests for SQLiteFavoritesRepository.

Covers add/remove/get_all/is_favorited/count with the cap enforcement
and duplicate-insertion behavior.
"""

from __future__ import annotations

import pytest

from discord_music_player.domain.music.entities import Track
from discord_music_player.domain.music.wrappers import TrackId


def _make_track(track_id: str, title: str = "Some Song") -> Track:
    return Track(
        id=TrackId(value=track_id),
        title=title,
        webpage_url=f"https://youtube.com/watch?v={track_id}",
        stream_url="https://stream.url/x",
        duration_seconds=200,
        thumbnail_url="https://thumb.url/x.jpg",
        artist="An Artist",
        uploader="An Uploader",
    )


class TestFavoritesRepository:
    @pytest.mark.asyncio
    async def test_add_new_favorite_returns_true(self, favorites_repository):
        track = _make_track("t1")
        result = await favorites_repository.add(user_id=1, track=track)
        assert result is True

    @pytest.mark.asyncio
    async def test_add_is_idempotent_for_same_track(self, favorites_repository):
        track = _make_track("t1")
        assert await favorites_repository.add(user_id=1, track=track) is True
        # Duplicate insert: INSERT OR IGNORE means no exception, still reports success,
        # but count stays at 1.
        assert await favorites_repository.add(user_id=1, track=track) is True
        assert await favorites_repository.count(user_id=1) == 1

    @pytest.mark.asyncio
    async def test_add_rejects_when_cap_reached(self, favorites_repository):
        # Cap is 100 per user; add 100 tracks then attempt one more.
        for i in range(100):
            await favorites_repository.add(user_id=42, track=_make_track(f"t{i}"))
        overflow = await favorites_repository.add(user_id=42, track=_make_track("t_over"))
        assert overflow is False
        assert await favorites_repository.count(user_id=42) == 100

    @pytest.mark.asyncio
    async def test_remove_returns_true_when_track_exists(self, favorites_repository):
        await favorites_repository.add(user_id=1, track=_make_track("t1"))
        assert await favorites_repository.remove(user_id=1, track_id="t1") is True
        assert await favorites_repository.count(user_id=1) == 0

    @pytest.mark.asyncio
    async def test_remove_returns_false_when_track_missing(self, favorites_repository):
        result = await favorites_repository.remove(user_id=1, track_id="nope")
        assert result is False

    @pytest.mark.asyncio
    async def test_remove_scoped_to_user(self, favorites_repository):
        await favorites_repository.add(user_id=1, track=_make_track("t1"))
        await favorites_repository.add(user_id=2, track=_make_track("t1"))
        # Removing for user 1 leaves user 2's copy intact.
        assert await favorites_repository.remove(user_id=1, track_id="t1") is True
        assert await favorites_repository.is_favorited(user_id=2, track_id="t1") is True

    @pytest.mark.asyncio
    async def test_is_favorited(self, favorites_repository):
        await favorites_repository.add(user_id=1, track=_make_track("t1"))
        assert await favorites_repository.is_favorited(user_id=1, track_id="t1") is True
        assert await favorites_repository.is_favorited(user_id=1, track_id="other") is False

    @pytest.mark.asyncio
    async def test_count_zero_for_new_user(self, favorites_repository):
        assert await favorites_repository.count(user_id=99999) == 0

    @pytest.mark.asyncio
    async def test_get_all_returns_tracks(self, favorites_repository):
        await favorites_repository.add(user_id=1, track=_make_track("t1", title="First"))
        await favorites_repository.add(user_id=1, track=_make_track("t2", title="Second"))
        tracks = await favorites_repository.get_all(user_id=1)
        titles = {t.title for t in tracks}
        assert titles == {"First", "Second"}

    @pytest.mark.asyncio
    async def test_get_all_respects_limit(self, favorites_repository):
        for i in range(5):
            await favorites_repository.add(user_id=1, track=_make_track(f"t{i}"))
        tracks = await favorites_repository.get_all(user_id=1, limit=2)
        assert len(tracks) == 2

    @pytest.mark.asyncio
    async def test_get_all_returns_empty_for_unknown_user(self, favorites_repository):
        tracks = await favorites_repository.get_all(user_id=123456)
        assert tracks == []
