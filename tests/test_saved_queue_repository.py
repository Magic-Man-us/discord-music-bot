"""Tests for SQLiteSavedQueueRepository.

Covers save/get/list_all/delete/count plus the 25-per-guild cap and
the ON CONFLICT(guild_id, name) upsert path.
"""

from __future__ import annotations

import pytest

from discord_music_player.domain.music.entities import Track
from discord_music_player.domain.music.wrappers import TrackId


def _make_track(track_id: str, title: str = "Song") -> Track:
    return Track(
        id=TrackId(value=track_id),
        title=title,
        webpage_url=f"https://youtube.com/watch?v={track_id}",
        stream_url="https://stream.url/x",
        duration_seconds=200,
        thumbnail_url="https://thumb.url/x.jpg",
        artist="Artist",
        uploader="Uploader",
    )


class TestSavedQueueRepository:
    @pytest.mark.asyncio
    async def test_save_new_queue_returns_true(self, saved_queue_repository):
        tracks = [_make_track("a"), _make_track("b")]
        result = await saved_queue_repository.save(
            guild_id=1,
            name="roadtrip",
            tracks=tracks,
            user_id=42,
            user_name="alice",
        )
        assert result is True
        assert await saved_queue_repository.count(guild_id=1) == 1

    @pytest.mark.asyncio
    async def test_save_upserts_existing_name_without_counting_twice(
        self, saved_queue_repository
    ):
        await saved_queue_repository.save(
            guild_id=1, name="mix", tracks=[_make_track("a")], user_id=1, user_name="x"
        )
        # Same name in same guild -> upsert, count still 1.
        await saved_queue_repository.save(
            guild_id=1,
            name="mix",
            tracks=[_make_track("a"), _make_track("b")],
            user_id=1,
            user_name="x",
        )
        assert await saved_queue_repository.count(guild_id=1) == 1

        row = await saved_queue_repository.get(guild_id=1, name="mix")
        assert row is not None
        assert row.track_count == 2

    @pytest.mark.asyncio
    async def test_save_rejects_new_name_when_cap_reached(self, saved_queue_repository):
        # Per-guild cap is 25; fill it then attempt a 26th distinct name.
        for i in range(25):
            ok = await saved_queue_repository.save(
                guild_id=1, name=f"q{i}", tracks=[_make_track("a")], user_id=1, user_name="x"
            )
            assert ok is True

        overflow = await saved_queue_repository.save(
            guild_id=1, name="q_over", tracks=[_make_track("a")], user_id=1, user_name="x"
        )
        assert overflow is False

    @pytest.mark.asyncio
    async def test_save_allows_upsert_even_at_cap(self, saved_queue_repository):
        for i in range(25):
            await saved_queue_repository.save(
                guild_id=1, name=f"q{i}", tracks=[_make_track("a")], user_id=1, user_name="x"
            )
        # Updating an existing name is allowed even at cap.
        result = await saved_queue_repository.save(
            guild_id=1, name="q0", tracks=[_make_track("b")], user_id=1, user_name="x"
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_get_returns_none_for_missing_queue(self, saved_queue_repository):
        result = await saved_queue_repository.get(guild_id=1, name="missing")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_roundtrips_tracks_via_json(self, saved_queue_repository):
        original = [_make_track("a", "A"), _make_track("b", "B")]
        await saved_queue_repository.save(
            guild_id=1, name="mix", tracks=original, user_id=1, user_name="x"
        )

        row = await saved_queue_repository.get(guild_id=1, name="mix")
        assert row is not None
        tracks = row.to_tracks()
        assert [t.title for t in tracks] == ["A", "B"]

    @pytest.mark.asyncio
    async def test_list_all_returns_summaries_scoped_to_guild(self, saved_queue_repository):
        await saved_queue_repository.save(
            guild_id=1, name="one", tracks=[_make_track("a")], user_id=1, user_name="x"
        )
        await saved_queue_repository.save(
            guild_id=1, name="two", tracks=[_make_track("b")], user_id=1, user_name="x"
        )
        await saved_queue_repository.save(
            guild_id=2, name="other", tracks=[_make_track("c")], user_id=1, user_name="x"
        )

        infos = await saved_queue_repository.list_all(guild_id=1)
        names = {i.name for i in infos}
        assert names == {"one", "two"}

    @pytest.mark.asyncio
    async def test_delete_returns_true_when_present(self, saved_queue_repository):
        await saved_queue_repository.save(
            guild_id=1, name="mix", tracks=[_make_track("a")], user_id=1, user_name="x"
        )
        assert await saved_queue_repository.delete(guild_id=1, name="mix") is True
        assert await saved_queue_repository.get(guild_id=1, name="mix") is None

    @pytest.mark.asyncio
    async def test_delete_returns_false_when_absent(self, saved_queue_repository):
        result = await saved_queue_repository.delete(guild_id=1, name="missing")
        assert result is False

    @pytest.mark.asyncio
    async def test_count_zero_for_new_guild(self, saved_queue_repository):
        assert await saved_queue_repository.count(guild_id=99999) == 0
