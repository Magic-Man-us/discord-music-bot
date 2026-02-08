import pytest
import pytest_asyncio

# ============================================================================
# Database Fixtures
# ============================================================================


@pytest_asyncio.fixture
async def in_memory_database():
    """Create an in-memory SQLite database for testing."""
    from discord_music_player.infrastructure.persistence.database import Database

    db = Database(":memory:")
    await db.initialize()
    yield db
    await db.close()


@pytest_asyncio.fixture
async def test_db(in_memory_database):
    """Alias for in_memory_database for compatibility."""
    return in_memory_database


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


# ============================================================================
# Domain Entity Fixtures
# ============================================================================


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
        artist="Test Artist",
        uploader="Test Uploader",
    )


@pytest.fixture
def sample_session(sample_track):
    """Create a sample guild playback session for testing."""
    from discord_music_player.domain.music.entities import GuildPlaybackSession

    session = GuildPlaybackSession(guild_id=987654321)
    session.set_current_track(sample_track)
    return session
