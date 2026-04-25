from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
import pytest_asyncio


# ============================================================================
# Discord stub helpers — Protocol-shaped fakes for cog/guard tests.
# Centralized here so cog tests don't reinvent MagicMock(spec=...) every time.
# ============================================================================


def make_role(role_id):
    """Build a stub `discord.Role` that satisfies isinstance checks."""
    role = MagicMock(spec=discord.Role)
    role.id = role_id
    return role


def make_voice_channel(channel_id, members=None):
    """Build a stub `discord.VoiceChannel` with controllable membership."""
    channel = MagicMock(spec=discord.VoiceChannel)
    channel.id = channel_id
    channel.members = list(members or [])
    return channel


def make_voice_state(channel=None):
    """Build a `discord.VoiceState`-shaped stub. Pass `channel=None` for not-in-voice."""
    state = MagicMock()
    state.channel = channel
    return state


def make_member(
    *,
    member_id=1,
    voice=None,
    is_bot=False,
    roles=None,
    administrator=False,
):
    """Build a `discord.Member` stub. `voice=None` means user is not in voice."""
    member = MagicMock(spec=discord.Member)
    member.id = member_id
    member.voice = voice
    member.bot = is_bot
    member.roles = list(roles or [])
    member.guild_permissions = MagicMock()
    member.guild_permissions.administrator = administrator
    return member


def make_user_only(user_id=1):
    """Build a `discord.User` (non-Member) stub for guild-only failures."""
    user = MagicMock(spec=discord.User)
    user.id = user_id
    return user


def make_interaction(
    *,
    user=None,
    guild_id=1,
    has_guild=True,
    response_done=False,
    bot_voice_channel_id=None,
):
    """Build a `discord.Interaction` stub.

    - `user`: pass a stub from `make_member`/`make_user_only`. Defaults to a fresh member.
    - `has_guild=False` makes `interaction.guild` None for "this command needs a server" paths.
    - `response_done` toggles `interaction.response.is_done()` so `send_ephemeral` exercises followup.
    - `bot_voice_channel_id` populates `client.get_guild(...).voice_client.channel.id`
      for `check_user_in_voice` tests. None means the bot isn't connected.
    """
    interaction = MagicMock(spec=discord.Interaction)
    interaction.user = user if user is not None else make_member()

    if has_guild:
        guild = MagicMock(spec=discord.Guild)
        guild.id = guild_id
        interaction.guild = guild
    else:
        interaction.guild = None

    interaction.response = MagicMock()
    interaction.response.is_done = MagicMock(return_value=response_done)
    interaction.response.send_message = AsyncMock()
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()

    client_guild = MagicMock()
    if bot_voice_channel_id is not None:
        client_guild.voice_client = MagicMock()
        client_guild.voice_client.channel = MagicMock(spec=discord.VoiceChannel)
        client_guild.voice_client.channel.id = bot_voice_channel_id
    else:
        client_guild.voice_client = None

    interaction.client = MagicMock()
    interaction.client.get_guild = MagicMock(return_value=client_guild)

    return interaction


class FakeVoiceAdapter:
    """Stub for the application VoiceAdapter Protocol used by ensure_voice."""

    def __init__(self, *, connected=False, connect_succeeds=True):
        self._connected = connected
        self._connect_succeeds = connect_succeeds
        self.ensure_connected_calls = []

    def is_connected(self, guild_id):
        return self._connected

    async def ensure_connected(self, guild_id, channel_id):
        self.ensure_connected_calls.append((guild_id, channel_id))
        return self._connect_succeeds


class FakeVoiceWarmupTracker:
    """Stub for VoiceWarmupTracker — controls remaining_seconds."""

    def __init__(self, *, remaining=0):
        self._remaining = remaining
        self.calls = []

    def remaining_seconds(self, *, guild_id, user_id):
        self.calls.append((guild_id, user_id))
        return self._remaining

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


@pytest_asyncio.fixture
async def favorites_repository(in_memory_database):
    """Create a favorites repository with in-memory database."""
    from discord_music_player.infrastructure.persistence.repositories.favorites_repository import (
        SQLiteFavoritesRepository,
    )

    return SQLiteFavoritesRepository(in_memory_database)


@pytest_asyncio.fixture
async def saved_queue_repository(in_memory_database):
    """Create a saved queue repository with in-memory database."""
    from discord_music_player.infrastructure.persistence.repositories.saved_queue_repository import (
        SQLiteSavedQueueRepository,
    )

    return SQLiteSavedQueueRepository(in_memory_database)


# ============================================================================
# Domain Entity Fixtures
# ============================================================================


@pytest.fixture
def sample_track():
    """Create a sample track for testing."""
    from discord_music_player.domain.music.entities import Track
    from discord_music_player.domain.music.wrappers import TrackId

    return Track(
        id=TrackId(value="test-track-123"),
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
