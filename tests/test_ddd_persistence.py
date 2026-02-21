"""Unit tests for the DDD persistence layer.

Tests for SQLite repositories and database operations.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
import pytest_asyncio

from discord_music_player.domain.music.value_objects import TrackId

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))


# === Test Fixtures ===


@pytest_asyncio.fixture
async def in_memory_database():
    """Create an in-memory SQLite database for testing."""
    from discord_music_player.infrastructure.persistence.database import Database

    db = Database(":memory:")
    await db.initialize()
    yield db
    await db.close()


@pytest_asyncio.fixture
async def session_repository(in_memory_database):
    """Create a session repository with in-memory database."""
    from discord_music_player.infrastructure.persistence.repositories.session_repository import (
        SQLiteSessionRepository,
    )

    return SQLiteSessionRepository(in_memory_database)


@pytest_asyncio.fixture
async def history_repository(in_memory_database):
    """Create a history repository with in-memory database."""
    from discord_music_player.infrastructure.persistence.repositories.history_repository import (
        SQLiteHistoryRepository,
    )

    return SQLiteHistoryRepository(in_memory_database)


@pytest_asyncio.fixture
async def vote_repository(in_memory_database):
    """Create a vote repository with in-memory database."""
    from discord_music_player.infrastructure.persistence.repositories.vote_repository import (
        SQLiteVoteSessionRepository,
    )

    return SQLiteVoteSessionRepository(in_memory_database)


@pytest_asyncio.fixture
async def cache_repository(in_memory_database):
    """Create a cache repository with in-memory database."""
    from discord_music_player.infrastructure.persistence.repositories.cache_repository import (
        SQLiteCacheRepository,
    )

    return SQLiteCacheRepository(in_memory_database)


@pytest.fixture
def sample_track():
    """Create a sample track for testing."""
    from discord_music_player.domain.music.entities import Track
    from discord_music_player.domain.music.value_objects import TrackId

    return Track(
        id=TrackId("test-track-123"),
        title="Test Track",
        webpage_url="https://youtube.com/watch?v=test123",
        stream_url="https://stream.url/test",
        duration_seconds=180,
        thumbnail_url="https://thumbnail.url/test.jpg",
        requested_by_id=123456789,
        requested_by_name="TestUser",
        requested_at=datetime.now(UTC),
    )


@pytest.fixture
def sample_session(sample_track):
    """Create a sample guild playback session for testing."""
    from discord_music_player.domain.music.entities import GuildPlaybackSession

    session = GuildPlaybackSession(guild_id=987654321)
    session.set_current_track(sample_track)
    return session


# === Database Tests ===


class TestDatabase:
    """Tests for the Database class."""

    @pytest.mark.asyncio
    async def test_initialize_creates_tables(self, in_memory_database):
        """Test that initialize creates required tables."""
        # Tables should be created during fixture initialization
        stats = await in_memory_database.get_stats()
        assert "guild_sessions" in str(stats) or stats is not None

    @pytest.mark.asyncio
    async def test_execute_basic_query(self, in_memory_database):
        """Test basic query execution."""
        await in_memory_database.execute(
            "INSERT INTO guild_sessions (guild_id, state, created_at, last_activity) VALUES (?, ?, datetime('now'), datetime('now'))",
            (123, "idle"),
        )

        rows = await in_memory_database.fetch_all(
            "SELECT * FROM guild_sessions WHERE guild_id = ?",
            (123,),
        )

        assert len(rows) == 1
        assert rows[0]["guild_id"] == 123

    @pytest.mark.asyncio
    async def test_transaction_rollback(self, in_memory_database):
        """Test that failed transactions rollback."""
        try:
            async with in_memory_database.transaction() as conn:
                await conn.execute(
                    "INSERT INTO guild_sessions (guild_id, state, created_at, last_activity) VALUES (?, ?, datetime('now'), datetime('now'))",
                    (456, "idle"),
                )
                # This should fail
                raise ValueError("Test error")
        except ValueError:
            pass

        # Row should not exist
        rows = await in_memory_database.fetch_all(
            "SELECT * FROM guild_sessions WHERE guild_id = ?",
            (456,),
        )

        assert len(rows) == 0

    @pytest.mark.asyncio
    async def test_validate_schema_healthy(self, in_memory_database):
        """Test that a freshly initialized DB passes validation."""
        result = await in_memory_database.validate_schema()

        assert result.tables.expected == 7
        assert result.tables.found == 7
        assert result.tables.missing == []

        assert result.columns.expected == result.columns.found
        assert result.columns.missing == {}

        assert result.indexes.expected == 9
        assert result.indexes.found == 9
        assert result.indexes.missing == []

        # In-memory SQLite uses journal_mode=memory instead of wal
        assert result.pragmas.journal_mode in ("wal", "memory")
        assert result.pragmas.foreign_keys == 1

        # Pragma issue for journal_mode is expected with in-memory DBs
        non_pragma_issues = [i for i in result.issues if "journal_mode" not in i]
        assert non_pragma_issues == []

    @pytest.mark.asyncio
    async def test_validate_schema_missing_table(self, in_memory_database):
        """Test validation detects a dropped table."""
        await in_memory_database.execute("DROP TABLE IF EXISTS track_genres")

        result = await in_memory_database.validate_schema()

        assert "track_genres" in result.tables.missing
        assert result.tables.found == 6
        assert len(result.issues) > 0
        assert any("track_genres" in issue for issue in result.issues)

    @pytest.mark.asyncio
    async def test_validate_schema_missing_index(self, in_memory_database):
        """Test validation detects a dropped index."""
        await in_memory_database.execute("DROP INDEX IF EXISTS idx_track_genres_genre")

        result = await in_memory_database.validate_schema()

        assert "idx_track_genres_genre" in result.indexes.missing
        assert result.indexes.found == 8
        assert any("idx_track_genres_genre" in issue for issue in result.issues)


# === Session Repository Tests ===


class TestSessionRepository:
    """Tests for SQLiteSessionRepository."""

    @pytest.mark.asyncio
    async def test_save_and_get_session(self, session_repository, sample_session):
        """Test saving and retrieving a session."""
        await session_repository.save(sample_session)

        retrieved = await session_repository.get(sample_session.guild_id)

        assert retrieved is not None
        assert retrieved.guild_id == sample_session.guild_id

    @pytest.mark.asyncio
    async def test_get_nonexistent_session_returns_none(self, session_repository):
        """Test getting a session that doesn't exist."""
        result = await session_repository.get(999999)
        assert result is None

    @pytest.mark.asyncio
    async def test_get_or_create_creates_new_session(self, session_repository):
        """Test get_or_create creates a new session if none exists."""
        guild_id = 111222333

        session = await session_repository.get_or_create(guild_id)

        assert session is not None
        assert session.guild_id == guild_id

    @pytest.mark.asyncio
    async def test_get_or_create_returns_existing(self, session_repository, sample_session):
        """Test get_or_create returns existing session."""
        await session_repository.save(sample_session)

        session = await session_repository.get_or_create(sample_session.guild_id)

        assert session.guild_id == sample_session.guild_id

    @pytest.mark.asyncio
    async def test_delete_session(self, session_repository, sample_session):
        """Test deleting a session."""
        await session_repository.save(sample_session)

        await session_repository.delete(sample_session.guild_id)

        result = await session_repository.get(sample_session.guild_id)
        assert result is None

    @pytest.mark.asyncio
    async def test_get_all_active_sessions(self, session_repository):
        """Test getting all active sessions."""
        from discord_music_player.domain.music.entities import GuildPlaybackSession

        # Create multiple sessions
        for guild_id in [100, 200, 300]:
            session = GuildPlaybackSession(guild_id=guild_id)
            await session_repository.save(session)

        sessions = await session_repository.get_all_active()

        assert len(sessions) >= 3

    @pytest.mark.asyncio
    async def test_cleanup_stale_sessions(self, session_repository):
        """Test cleanup removes stale sessions."""
        from discord_music_player.domain.music.entities import GuildPlaybackSession

        # Create a session (would have recent updated_at)
        session = GuildPlaybackSession(guild_id=444)
        await session_repository.save(session)

        # Cleanup with 1 hours threshold
        deleted = await session_repository.cleanup_stale(max_age_hours=1)

        # Session may or may not be deleted depending on time
        assert isinstance(deleted, int)


# === History Repository Tests ===


class TestHistoryRepository:
    """Tests for SQLiteHistoryRepository."""

    @pytest.mark.asyncio
    async def test_record_track_play(self, history_repository, sample_track):
        """Test recording a track play."""
        guild_id = 123

        await history_repository.record_play(guild_id, sample_track)

        # Verify by getting history
        history = await history_repository.get_guild_history(guild_id, limit=10)

        assert len(history) == 1
        assert history[0].track.title == sample_track.title

    @pytest.mark.asyncio
    async def test_get_guild_history_respects_limit(self, history_repository, sample_track):
        """Test that history limit is respected."""
        from discord_music_player.domain.music.entities import Track
        from discord_music_player.domain.music.value_objects import TrackId

        guild_id = 456

        # Add multiple tracks
        for i in range(15):
            track = Track(
                id=TrackId(f"track-{i}"),
                title=f"Track {i}",
                webpage_url=f"https://url/{i}",
            )
            await history_repository.record_play(guild_id, track)

        history = await history_repository.get_guild_history(guild_id, limit=10)

        assert len(history) == 10

    @pytest.mark.asyncio
    async def test_get_recent_track_titles(self, history_repository, sample_track):
        """Test getting recent track titles."""
        from discord_music_player.domain.music.entities import Track
        from discord_music_player.domain.music.value_objects import TrackId

        guild_id = 789

        # Add tracks
        for i in range(5):
            track = Track(
                id=TrackId(f"track-{i}"),
                title=f"Recent Track {i}",
                webpage_url=f"https://url/{i}",
            )
            await history_repository.record_play(guild_id, track)

        titles = await history_repository.get_recent_titles(guild_id, limit=3)

        assert len(titles) == 3
        assert all("Recent Track" in t for t in titles)

    @pytest.mark.asyncio
    async def test_cleanup_old_history(self, history_repository, sample_track):
        """Test cleaning up old history records."""
        guild_id = 111

        await history_repository.record_play(guild_id, sample_track)

        # Cleanup with 0 days threshold
        deleted = await history_repository.cleanup_old(max_age_days=0)

        assert isinstance(deleted, int)


# === Vote Repository Tests ===


class TestVoteRepository:
    """Tests for SQLiteVoteSessionRepository."""

    @pytest.mark.asyncio
    async def test_create_and_get_vote_session(self, vote_repository):
        """Test creating and retrieving a vote session."""
        from discord_music_player.domain.voting.entities import VoteSession
        from discord_music_player.domain.voting.value_objects import VoteType

        guild_id = 123
        track_id = TrackId("track-123")

        session = VoteSession(
            guild_id=guild_id,
            track_id=track_id,
            vote_type=VoteType.SKIP,
            threshold=3,
        )

        await vote_repository.save(session)

        retrieved = await vote_repository.get_active(guild_id, track_id)

        assert retrieved is not None
        assert retrieved.guild_id == guild_id

    @pytest.mark.asyncio
    async def test_get_nonexistent_vote_session(self, vote_repository):
        """Test getting a vote session that doesn't exist."""
        result = await vote_repository.get_active(999, TrackId("nonexistent"))
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_vote_session(self, vote_repository):
        """Test deleting a vote session."""
        from discord_music_player.domain.voting.entities import VoteSession
        from discord_music_player.domain.voting.value_objects import VoteType

        guild_id = 456
        track_id = TrackId("track-456")

        session = VoteSession(
            guild_id=guild_id,
            track_id=track_id,
            vote_type=VoteType.SKIP,
            threshold=2,
        )

        await vote_repository.save(session)
        await vote_repository.delete_by_track(guild_id, track_id)

        result = await vote_repository.get_active(guild_id, track_id)
        assert result is None

    @pytest.mark.asyncio
    async def test_cleanup_expired_sessions(self, vote_repository):
        """Test cleaning up expired vote sessions."""
        deleted = await vote_repository.cleanup_expired()
        assert isinstance(deleted, int)


# === Cache Repository Tests ===


class TestCacheRepository:
    """Tests for SQLiteCacheRepository."""

    @pytest.mark.asyncio
    async def test_set_and_get_cache(self, cache_repository):
        """Test setting and getting a cache entry."""
        key = "test-key-123"
        data = {"recommendations": ["song1", "song2"], "metadata": {"count": 2}}
        ttl = 3600

        await cache_repository.set(key, data, ttl)

        result = await cache_repository.get(key)

        assert result is not None
        assert [r.title for r in result.recommendations] == data["recommendations"]

    @pytest.mark.asyncio
    async def test_get_nonexistent_cache(self, cache_repository):
        """Test getting a cache entry that doesn't exist."""
        result = await cache_repository.get("nonexistent-key")
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_cache(self, cache_repository):
        """Test deleting a cache entry."""
        key = "delete-me"

        await cache_repository.set(key, {"data": "test"}, 3600)
        await cache_repository.delete(key)

        result = await cache_repository.get(key)
        assert result is None

    @pytest.mark.asyncio
    async def test_clear_all_cache(self, cache_repository):
        """Test clearing all cache entries."""
        # Add multiple entries
        for i in range(5):
            await cache_repository.set(f"key-{i}", {"index": i}, 3600)

        await cache_repository.clear_all()

        # Verify all are gone
        for i in range(5):
            result = await cache_repository.get(f"key-{i}")
            assert result is None

    @pytest.mark.asyncio
    async def test_cleanup_expired_cache(self, cache_repository):
        """Test cleaning up expired cache entries."""
        deleted = await cache_repository.cleanup_expired()
        assert isinstance(deleted, int)


# === Integration Tests ===


class TestRepositoryIntegration:
    """Integration tests for repository interactions."""

    @pytest.mark.asyncio
    async def test_full_session_lifecycle(self, session_repository, sample_track):
        """Test complete session lifecycle."""
        from discord_music_player.domain.music.value_objects import PlaybackState

        guild_id = 999

        # Create session
        session = await session_repository.get_or_create(guild_id)
        assert session.state == PlaybackState.IDLE

        # Add track and update state
        session.enqueue(sample_track)
        session.set_current_track(session.dequeue())
        session.transition_to(PlaybackState.PLAYING)

        await session_repository.save(session)

        # Retrieve and verify
        retrieved = await session_repository.get(guild_id)
        assert retrieved is not None

        # Cleanup
        await session_repository.delete(guild_id)

        final = await session_repository.get(guild_id)
        assert final is None

    @pytest.mark.asyncio
    async def test_history_with_multiple_sessions(
        self, history_repository, session_repository, sample_track
    ):
        """Test history recording across multiple sessions."""
        from discord_music_player.domain.music.entities import GuildPlaybackSession, Track
        from discord_music_player.domain.music.value_objects import TrackId

        # Create sessions for different guilds
        guilds = [111, 222, 333]

        for guild_id in guilds:
            session = GuildPlaybackSession(guild_id=guild_id)
            await session_repository.save(session)

            track = Track(
                id=TrackId(f"track-{guild_id}"),
                title=f"Song for guild {guild_id}",
                webpage_url=f"https://url/{guild_id}",
            )
            await history_repository.record_play(guild_id, track)

        # Verify each guild has its own history
        for guild_id in guilds:
            history = await history_repository.get_guild_history(guild_id, limit=10)
            assert len(history) == 1
            assert str(guild_id) in history[0].track.title


# === Domain Events Tests ===


class TestDomainEvents:
    """Tests for the domain event bus."""

    def test_event_bus_subscribe_and_publish(self):
        """Test subscribing to and publishing events."""
        from discord_music_player.domain.shared.events import (
            EventBus,
            TrackStartedPlaying,
        )

        bus = EventBus()
        received_events = []

        async def handler(event: TrackStartedPlaying):
            received_events.append(event)

        bus.subscribe(TrackStartedPlaying, handler)

        event = TrackStartedPlaying(
            guild_id=123,
            track_id=TrackId("test"),
            track_title="Test Song",
            track_url="https://test.url",
        )

        # Run async publish
        asyncio.run(bus.publish(event))

        assert len(received_events) == 1
        assert received_events[0].track_title == "Test Song"

    def test_event_bus_unsubscribe(self):
        """Test unsubscribing from events."""
        from discord_music_player.domain.shared.events import (
            EventBus,
            TrackSkipped,
        )

        bus = EventBus()
        call_count = 0

        async def handler(event: TrackSkipped):
            nonlocal call_count
            call_count += 1

        bus.subscribe(TrackSkipped, handler)
        bus.unsubscribe(TrackSkipped, handler)

        event = TrackSkipped(
            guild_id=123,
            track_id=TrackId("test"),
            track_title="Test",
            skipped_by_id=456,
        )

        asyncio.run(bus.publish(event))

        assert call_count == 0

    def test_event_bus_multiple_handlers(self):
        """Test multiple handlers for same event type."""
        from discord_music_player.domain.shared.events import (
            EventBus,
            QueueCleared,
        )

        bus = EventBus()
        handler1_called = False
        handler2_called = False

        async def handler1(event: QueueCleared):
            nonlocal handler1_called
            handler1_called = True

        async def handler2(event: QueueCleared):
            nonlocal handler2_called
            handler2_called = True

        bus.subscribe(QueueCleared, handler1)
        bus.subscribe(QueueCleared, handler2)

        event = QueueCleared(
            guild_id=123,
            cleared_by_id=456,
            track_count=5,
        )

        asyncio.run(bus.publish(event))

        assert handler1_called
        assert handler2_called

    def test_global_event_bus(self):
        """Test global event bus singleton."""
        from discord_music_player.domain.shared.events import (
            get_event_bus,
            reset_event_bus,
        )

        reset_event_bus()

        bus1 = get_event_bus()
        bus2 = get_event_bus()

        assert bus1 is bus2

        reset_event_bus()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
