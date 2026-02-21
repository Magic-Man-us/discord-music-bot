"""
Comprehensive Unit Tests for HealthCog

75 tests covering health monitoring functionality in the health cog:

Test Coverage:

1. TestHealthCogInitialization (7 tests):
   - Cog initialization with bot and container
   - Heartbeat file path creation
   - Log directory creation
   - Heartbeat loop interval configuration
   - Missing health settings handling
   - Cog load/unload lifecycle

2. TestHelperMethods (16 tests):
   - Uptime formatting (various durations)
   - Latency conversion to milliseconds
   - Latency emoji selection based on thresholds
   - Connection status emoji
   - Embed color selection for latency
   - Audio snapshot retrieval
   - Atomic file writing

3. TestBasicStatsCollection (7 tests):
   - Basic stats structure validation
   - Timestamp formatting
   - Uptime calculation
   - Latency metrics
   - Connection status (online/offline)
   - Queue defaults

4. TestDetailedStatsCollection (6 tests):
   - Basic stats inclusion in detailed stats
   - Guild count
   - Voice connection count
   - Memory stats (with/without psutil)
   - Database statistics
   - Error handling for database failures

5. TestHeartbeatLoops (8 tests):
   - Fast heartbeat collection and file writing
   - Fast heartbeat error handling
   - Latency warning system (threshold detection, one-time warning, reset)
   - Detailed heartbeat collection and file writing
   - Detailed heartbeat error handling
   - Bot ready wait hooks

6. TestPingCommand (4 tests):
   - Latency display
   - Emoji inclusion based on latency
   - Ephemeral response
   - High latency emoji handling

7. TestHealthCommand (10 tests):
   - Embed response structure
   - Ephemeral response
   - Connection status, uptime, and latency fields
   - Admin vs regular user permission checks
   - Admin-only fields (memory, database)
   - Embed color based on latency
   - Timestamp and footer inclusion

8. TestEmbedBuilding (7 tests):
   - Basic embed structure
   - Admin field inclusion
   - Admin permission checking (Member vs User)
   - Memory stats formatting (RSS, VMS, both, none)

9. TestSetupFunction (2 tests):
   - Container requirement validation
   - Cog registration with bot

Uses pytest with async/await patterns and proper mocking.
All tests run quickly (~1 second) by mocking system dependencies.
"""

import json
import time
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, mock_open, patch

import discord
import pytest
from discord.ext import tasks

from discord_music_player.infrastructure.discord.cogs.health_cog import (
    LATENCY_OK_MS,
    LATENCY_WARN_MS,
    DetailedStats,
    HealthCog,
)
from discord_music_player.infrastructure.persistence.database import DatabaseStats

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_bot():
    """Create a mock Discord bot."""
    bot = MagicMock()
    bot.latency = 0.05  # 50ms
    bot.is_closed = MagicMock(return_value=False)
    bot.guilds = [MagicMock(id=111111), MagicMock(id=222222)]
    bot.voice_clients = []
    bot.wait_until_ready = AsyncMock()
    bot.get_channel = MagicMock(return_value=None)
    return bot


@pytest.fixture
def mock_container():
    """Create a mock DI container."""
    container = MagicMock()

    # Mock settings
    settings = MagicMock()
    settings.log_dir = "logs"
    health_settings = MagicMock()
    health_settings.fast_interval = 180
    health_settings.detailed_interval = 300
    health_settings.alert_channel_id = None
    settings.health = health_settings
    container.settings = settings

    # Mock database
    database = MagicMock()
    database.get_stats = AsyncMock(return_value=DatabaseStats(db_path=":memory:", initialized=True, file_size_mb=2.5))
    container.database = database

    return container


@pytest.fixture
def mock_context():
    """Create a mock Discord Context."""
    ctx = MagicMock()
    ctx.send = AsyncMock()

    # Mock author (regular user)
    author = MagicMock(spec=discord.Member)
    author.id = 123456789
    author.guild_permissions = MagicMock()
    author.guild_permissions.administrator = False
    ctx.author = author

    return ctx


@pytest.fixture
def mock_admin_context(mock_context):
    """Create a mock Discord Context with admin user."""
    mock_context.author.guild_permissions.administrator = True
    return mock_context


@pytest.fixture
def health_cog(mock_bot, mock_container, tmp_path):
    """Create a HealthCog instance with mocked dependencies."""
    # Override log directory to use temp path
    mock_container.settings.log_dir = str(tmp_path)

    with patch.object(tasks.Loop, "change_interval"):
        cog = HealthCog(mock_bot, mock_container)

    return cog


# =============================================================================
# Initialization Tests
# =============================================================================


class TestHealthCogInitialization:
    """Tests for HealthCog initialization and lifecycle."""

    def test_cog_initializes_with_bot_and_container(self, mock_bot, mock_container):
        """Should initialize with bot and container."""
        with patch.object(tasks.Loop, "change_interval"):
            cog = HealthCog(mock_bot, mock_container)

        assert cog.bot == mock_bot
        assert cog.container == mock_container
        assert cog._warned is False

    def test_cog_creates_heartbeat_files_paths(self, mock_bot, mock_container, tmp_path):
        """Should create heartbeat file paths."""
        mock_container.settings.log_dir = str(tmp_path)

        with patch.object(tasks.Loop, "change_interval"):
            cog = HealthCog(mock_bot, mock_container)

        assert cog.heartbeat_file == tmp_path / "heartbeat.json"
        assert cog.detailed_file == tmp_path / "heartbeat_detailed.json"

    def test_cog_creates_log_directory(self, mock_bot, mock_container, tmp_path):
        """Should create log directory if it doesn't exist."""
        log_dir = tmp_path / "custom_logs"
        mock_container.settings.log_dir = str(log_dir)

        with patch.object(tasks.Loop, "change_interval"):
            HealthCog(mock_bot, mock_container)

        assert log_dir.exists()
        assert log_dir.is_dir()

    def test_cog_sets_heartbeat_intervals(self, mock_bot, mock_container):
        """Should configure heartbeat loop intervals from settings."""
        mock_container.settings.health.fast_interval = 60
        mock_container.settings.health.detailed_interval = 120

        with patch.object(tasks.Loop, "change_interval") as mock_change:
            HealthCog(mock_bot, mock_container)

        # Should be called (multiple times as tasks.loop creates multiple Loop instances)
        assert mock_change.call_count >= 2

    def test_cog_handles_missing_health_settings(self, mock_bot, mock_container):
        """Should use default intervals when health settings missing."""
        mock_container.settings.health = None

        with patch.object(tasks.Loop, "change_interval"):
            cog = HealthCog(mock_bot, mock_container)

        # Should not raise, uses defaults
        assert cog is not None

    @pytest.mark.asyncio
    async def test_cog_load_starts_heartbeat_loops(self, health_cog):
        """Should start heartbeat loops on cog load."""
        with patch.object(health_cog.heartbeat_fast, "start") as mock_fast:
            with patch.object(health_cog.heartbeat_detailed, "start") as mock_detailed:
                await health_cog.cog_load()

        mock_fast.assert_called_once()
        mock_detailed.assert_called_once()

    @pytest.mark.asyncio
    async def test_cog_unload_stops_heartbeat_loops(self, health_cog):
        """Should cancel heartbeat loops on cog unload."""
        with patch.object(health_cog.heartbeat_fast, "cancel") as mock_fast:
            with patch.object(health_cog.heartbeat_detailed, "cancel") as mock_detailed:
                await health_cog.cog_unload()

        mock_fast.assert_called_once()
        mock_detailed.assert_called_once()


# =============================================================================
# Helper Method Tests
# =============================================================================


class TestHelperMethods:
    """Tests for internal helper methods."""

    def test_format_uptime_seconds_only(self, health_cog):
        """Should format uptime with seconds only."""
        result = health_cog._format_uptime(45)
        assert result == "45s"

    def test_format_uptime_minutes_and_seconds(self, health_cog):
        """Should format uptime with minutes and seconds."""
        result = health_cog._format_uptime(125)
        assert result == "2m 5s"

    def test_format_uptime_hours_minutes_seconds(self, health_cog):
        """Should format uptime with hours, minutes, and seconds."""
        result = health_cog._format_uptime(7325)
        assert result == "2h 2m 5s"

    def test_format_uptime_zero(self, health_cog):
        """Should handle zero uptime."""
        result = health_cog._format_uptime(0)
        assert result == "0s"

    def test_format_uptime_negative_handled(self, health_cog):
        """Should handle negative uptime gracefully."""
        result = health_cog._format_uptime(-100)
        assert result == "0s"

    def test_latency_ms_conversion(self, health_cog, mock_bot):
        """Should convert bot latency to milliseconds."""
        mock_bot.latency = 0.123
        result = health_cog._latency_ms()
        assert result == 123.0

    def test_latency_ms_rounds_properly(self, health_cog, mock_bot):
        """Should round latency to one decimal."""
        mock_bot.latency = 0.1234
        result = health_cog._latency_ms()
        assert result == 123.4

    def test_latency_ms_handles_none(self, health_cog, mock_bot):
        """Should handle None latency."""
        mock_bot.latency = None
        result = health_cog._latency_ms()
        assert result == 0.0

    def test_latency_emoji_green_for_low(self, health_cog):
        """Should return green emoji for low latency."""
        result = health_cog._latency_emoji(50)
        assert result == "🟢"

    def test_latency_emoji_orange_for_medium(self, health_cog):
        """Should return orange emoji for medium latency."""
        result = health_cog._latency_emoji(500)
        assert result == "🟠"

    def test_latency_emoji_red_for_high(self, health_cog):
        """Should return red emoji for high latency."""
        result = health_cog._latency_emoji(1000)
        assert result == "🔴"

    def test_latency_emoji_boundary_ok(self, health_cog):
        """Should use green at OK threshold boundary."""
        result = health_cog._latency_emoji(LATENCY_OK_MS - 1)
        assert result == "🟢"

    def test_latency_emoji_boundary_warn(self, health_cog):
        """Should use orange at warn threshold boundary."""
        result = health_cog._latency_emoji(LATENCY_WARN_MS - 1)
        assert result == "🟠"

    def test_status_emoji_connected(self, health_cog):
        """Should return green emoji when connected."""
        result = health_cog._status_emoji(True)
        assert result == "🟢"

    def test_status_emoji_disconnected(self, health_cog):
        """Should return red emoji when disconnected."""
        result = health_cog._status_emoji(False)
        assert result == "🔴"

    def test_embed_color_green_for_low_latency(self, health_cog):
        """Should return green color for low latency."""
        result = health_cog._embed_color_for_latency(50)
        assert result == discord.Color.green()

    def test_embed_color_gold_for_medium_latency(self, health_cog):
        """Should return gold color for medium latency."""
        result = health_cog._embed_color_for_latency(500)
        assert result == discord.Color.gold()

    def test_embed_color_red_for_high_latency(self, health_cog):
        """Should return red color for high latency."""
        result = health_cog._embed_color_for_latency(1000)
        assert result == discord.Color.red()

    def test_audio_snapshot_returns_defaults(self, health_cog):
        """Should return default audio snapshot."""
        queue_len, current_title = health_cog._audio_snapshot()

        assert queue_len == 0
        assert current_title is None

    def test_atomic_write_creates_file(self, health_cog, tmp_path):
        """Should atomically write JSON to file."""
        test_file = tmp_path / "test.json"
        payload = {"test": "data", "number": 123}

        health_cog._atomic_write(test_file, payload)

        assert test_file.exists()
        with open(test_file) as f:
            data = json.load(f)
        assert data == payload

    def test_atomic_write_uses_temp_file(self, health_cog, tmp_path):
        """Should write to temp file then rename."""
        test_file = tmp_path / "test.json"
        payload = {"test": "data"}

        with patch("pathlib.Path.open", mock_open()) as mock_file:
            with patch("pathlib.Path.replace") as mock_replace:
                health_cog._atomic_write(test_file, payload)

        # Should have called replace
        mock_replace.assert_called_once()


# =============================================================================
# Basic Stats Collection Tests
# =============================================================================


class TestBasicStatsCollection:
    """Tests for basic health statistics collection."""

    def test_collect_basic_stats_structure(self, health_cog, mock_bot):
        """Should collect all required basic stats fields."""
        stats = health_cog._collect_basic_stats()

        assert "ts" in stats
        assert "uptime_s" in stats
        assert "uptime_human" in stats
        assert "latency_ms" in stats
        assert "latency_human" in stats
        assert "queue_len" in stats
        assert "current" in stats
        assert "connected" in stats
        assert "status" in stats

    def test_collect_basic_stats_timestamp_format(self, health_cog):
        """Should include ISO timestamp."""
        stats = health_cog._collect_basic_stats()

        # Should be ISO format
        assert "T" in stats["ts"]
        # Should be parseable
        datetime.fromisoformat(stats["ts"])

    def test_collect_basic_stats_uptime(self, health_cog):
        """Should calculate uptime correctly."""
        # Simulate 5 seconds of uptime
        health_cog.started_at = time.monotonic() - 5

        stats = health_cog._collect_basic_stats()

        assert stats["uptime_s"] >= 4
        assert stats["uptime_s"] <= 6

    def test_collect_basic_stats_latency(self, health_cog, mock_bot):
        """Should include latency in milliseconds."""
        mock_bot.latency = 0.075  # 75ms

        stats = health_cog._collect_basic_stats()

        assert stats["latency_ms"] == 75.0
        assert "75.0 ms" in stats["latency_human"]

    def test_collect_basic_stats_connection_online(self, health_cog, mock_bot):
        """Should report online status when connected."""
        mock_bot.is_closed = MagicMock(return_value=False)

        stats = health_cog._collect_basic_stats()

        assert stats["connected"] is True
        assert stats["status"] == "online"

    def test_collect_basic_stats_connection_offline(self, health_cog, mock_bot):
        """Should report offline status when disconnected."""
        mock_bot.is_closed = MagicMock(return_value=True)

        stats = health_cog._collect_basic_stats()

        assert stats["connected"] is False
        assert stats["status"] == "offline"

    def test_collect_basic_stats_queue_defaults(self, health_cog):
        """Should have default queue values."""
        stats = health_cog._collect_basic_stats()

        assert stats["queue_len"] == 0
        assert stats["current"] is None


# =============================================================================
# Detailed Stats Collection Tests
# =============================================================================


class TestDetailedStatsCollection:
    """Tests for detailed health statistics collection."""

    @pytest.mark.asyncio
    async def test_collect_detailed_stats_includes_basic(self, health_cog):
        """Should include all basic stats in detailed stats."""
        stats = await health_cog._collect_detailed_stats()

        # All basic fields should be present
        assert "ts" in stats
        assert "uptime_s" in stats
        assert "latency_ms" in stats
        assert "connected" in stats

    @pytest.mark.asyncio
    async def test_collect_detailed_stats_guild_count(self, health_cog, mock_bot):
        """Should include guild count."""
        mock_bot.guilds = [MagicMock(), MagicMock(), MagicMock()]

        stats = await health_cog._collect_detailed_stats()

        assert stats["guild_count"] == 3

    @pytest.mark.asyncio
    async def test_collect_detailed_stats_voice_connections(self, health_cog, mock_bot):
        """Should include voice connection count."""
        mock_bot.voice_clients = [MagicMock(), MagicMock()]

        stats = await health_cog._collect_detailed_stats()

        assert stats["voice_connections"] == 2

    @pytest.mark.asyncio
    async def test_collect_detailed_stats_memory_with_psutil(self, health_cog):
        """Should include memory stats when psutil available."""
        mock_process = MagicMock()
        mock_memory = MagicMock()
        mock_memory.rss = 100 * 1024 * 1024  # 100 MB
        mock_memory.vms = 200 * 1024 * 1024  # 200 MB
        mock_process.memory_full_info.return_value = mock_memory
        mock_process.oneshot.return_value.__enter__ = lambda self: None
        mock_process.oneshot.return_value.__exit__ = lambda self, *args: None

        with patch("psutil.Process", return_value=mock_process):
            stats = await health_cog._collect_detailed_stats()

        assert "rss_mb" in stats
        assert stats["rss_mb"] == 100.0
        assert "vms_mb" in stats
        assert stats["vms_mb"] == 200.0

    @pytest.mark.asyncio
    async def test_collect_detailed_stats_memory_without_psutil(self, health_cog):
        """Should handle missing psutil gracefully."""
        with patch("psutil.Process", side_effect=ImportError):
            stats = await health_cog._collect_detailed_stats()

        # Should not have memory fields
        assert "rss_mb" not in stats
        assert "vms_mb" not in stats

    @pytest.mark.asyncio
    async def test_collect_detailed_stats_database(self, health_cog, mock_container):
        """Should include database statistics."""
        mock_container.database.get_stats = AsyncMock(
            return_value=DatabaseStats(db_path=":memory:", initialized=True, file_size_mb=5.2)
        )

        stats = await health_cog._collect_detailed_stats()

        assert stats["db_initialized"] is True
        assert stats["db_size_mb"] == 5.2

    @pytest.mark.asyncio
    async def test_collect_detailed_stats_database_error(self, health_cog, mock_container):
        """Should handle database stats errors gracefully."""
        mock_container.database.get_stats = AsyncMock(side_effect=Exception("Database error"))

        stats = await health_cog._collect_detailed_stats()

        # Should not have db fields
        assert "db_initialized" not in stats
        assert "db_size_mb" not in stats


# =============================================================================
# Heartbeat Loop Tests
# =============================================================================


class TestHeartbeatLoops:
    """Tests for heartbeat monitoring loops."""

    @pytest.mark.asyncio
    async def test_heartbeat_fast_collects_and_writes(self, health_cog, tmp_path):
        """Should collect basic stats and write to file."""
        health_cog.heartbeat_file = tmp_path / "heartbeat.json"

        await health_cog.heartbeat_fast()

        assert health_cog.heartbeat_file.exists()
        with open(health_cog.heartbeat_file) as f:
            data = json.load(f)
        assert "ts" in data
        assert "latency_ms" in data

    @pytest.mark.asyncio
    async def test_heartbeat_fast_error_handling(self, health_cog):
        """Should handle errors in fast heartbeat gracefully."""
        with patch.object(health_cog, "_collect_basic_stats", side_effect=Exception("Test error")):
            # Should not raise
            await health_cog.heartbeat_fast()

    @pytest.mark.asyncio
    async def test_heartbeat_fast_latency_warning(self, health_cog, mock_bot, mock_container):
        """Should send warning when latency exceeds threshold."""
        mock_bot.latency = 1.0  # 1000ms - high latency
        mock_container.settings.health.alert_channel_id = 999999

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.send = AsyncMock()
        mock_bot.get_channel.return_value = mock_channel

        await health_cog.heartbeat_fast()

        # Should have sent warning
        mock_channel.send.assert_called_once()
        call_args = mock_channel.send.call_args[0][0]
        assert "warning" in call_args.lower()

    @pytest.mark.asyncio
    async def test_heartbeat_fast_warning_only_once(self, health_cog, mock_bot, mock_container):
        """Should only send latency warning once."""
        mock_bot.latency = 1.0  # High latency
        mock_container.settings.health.alert_channel_id = 999999

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.send = AsyncMock()
        mock_bot.get_channel.return_value = mock_channel

        # First call - should warn
        await health_cog.heartbeat_fast()
        assert mock_channel.send.call_count == 1

        # Second call - should not warn again
        await health_cog.heartbeat_fast()
        assert mock_channel.send.call_count == 1

    @pytest.mark.asyncio
    async def test_heartbeat_fast_warning_reset(self, health_cog, mock_bot, mock_container):
        """Should reset warning flag when latency improves."""
        mock_container.settings.health.alert_channel_id = 999999
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.send = AsyncMock()
        mock_bot.get_channel.return_value = mock_channel

        # High latency
        mock_bot.latency = 1.0
        await health_cog.heartbeat_fast()
        assert health_cog._warned is True

        # Latency improves significantly
        mock_bot.latency = 0.1  # 100ms - good latency
        await health_cog.heartbeat_fast()
        assert health_cog._warned is False

    @pytest.mark.asyncio
    async def test_heartbeat_detailed_collects_and_writes(self, health_cog, tmp_path):
        """Should collect detailed stats and write to file."""
        health_cog.detailed_file = tmp_path / "detailed.json"

        await health_cog.heartbeat_detailed()

        assert health_cog.detailed_file.exists()
        with open(health_cog.detailed_file) as f:
            data = json.load(f)
        assert "ts" in data
        assert "guild_count" in data

    @pytest.mark.asyncio
    async def test_heartbeat_detailed_error_handling(self, health_cog):
        """Should handle errors in detailed heartbeat gracefully."""
        with patch.object(
            health_cog,
            "_collect_detailed_stats",
            side_effect=Exception("Test error"),
        ):
            # Should not raise
            await health_cog.heartbeat_detailed()

    @pytest.mark.asyncio
    async def test_heartbeat_fast_waits_for_ready(self, health_cog, mock_bot):
        """Should wait for bot ready before starting fast loop."""
        await health_cog._wait_ready_fast()

        mock_bot.wait_until_ready.assert_called_once()

    @pytest.mark.asyncio
    async def test_heartbeat_detailed_waits_for_ready(self, health_cog, mock_bot):
        """Should wait for bot ready before starting detailed loop."""
        await health_cog._wait_ready_detailed()

        mock_bot.wait_until_ready.assert_called_once()


# =============================================================================
# /ping Command Tests
# =============================================================================


class TestPingCommand:
    """Tests for /ping command."""

    @pytest.mark.asyncio
    async def test_ping_shows_latency(self, health_cog, mock_context, mock_bot):
        """Should display current latency."""
        mock_bot.latency = 0.05  # 50ms

        await health_cog.ping.callback(health_cog, mock_context)

        mock_context.send.assert_called_once()
        call_args = mock_context.send.call_args[0][0]
        assert "50.0" in call_args

    @pytest.mark.asyncio
    async def test_ping_includes_emoji(self, health_cog, mock_context, mock_bot):
        """Should include status emoji based on latency."""
        mock_bot.latency = 0.05  # 50ms - low

        await health_cog.ping.callback(health_cog, mock_context)

        call_args = mock_context.send.call_args[0][0]
        assert "🟢" in call_args

    @pytest.mark.asyncio
    async def test_ping_ephemeral_response(self, health_cog, mock_context):
        """Should send ephemeral response."""
        await health_cog.ping.callback(health_cog, mock_context)

        call_kwargs = mock_context.send.call_args[1]
        assert call_kwargs.get("ephemeral") is True

    @pytest.mark.asyncio
    async def test_ping_high_latency_emoji(self, health_cog, mock_context, mock_bot):
        """Should show red emoji for high latency."""
        mock_bot.latency = 1.0  # 1000ms - high

        await health_cog.ping.callback(health_cog, mock_context)

        call_args = mock_context.send.call_args[0][0]
        assert "🔴" in call_args


# =============================================================================
# /health Command Tests
# =============================================================================


class TestHealthCommand:
    """Tests for /health command."""

    @pytest.mark.asyncio
    async def test_health_returns_embed(self, health_cog, mock_context):
        """Should return embed with health information."""
        await health_cog.health.callback(health_cog, mock_context)

        mock_context.send.assert_called_once()
        call_kwargs = mock_context.send.call_args[1]
        assert "embed" in call_kwargs
        assert isinstance(call_kwargs["embed"], discord.Embed)

    @pytest.mark.asyncio
    async def test_health_ephemeral_response(self, health_cog, mock_context):
        """Should send ephemeral response."""
        await health_cog.health.callback(health_cog, mock_context)

        call_kwargs = mock_context.send.call_args[1]
        assert call_kwargs.get("ephemeral") is True

    @pytest.mark.asyncio
    async def test_health_includes_connection_status(self, health_cog, mock_context):
        """Should include connection status in embed."""
        await health_cog.health.callback(health_cog, mock_context)

        embed = mock_context.send.call_args[1]["embed"]
        field_names = [field.name for field in embed.fields]
        assert "Status" in field_names

    @pytest.mark.asyncio
    async def test_health_includes_uptime(self, health_cog, mock_context):
        """Should include uptime in embed."""
        await health_cog.health.callback(health_cog, mock_context)

        embed = mock_context.send.call_args[1]["embed"]
        field_names = [field.name for field in embed.fields]
        assert "Uptime" in field_names

    @pytest.mark.asyncio
    async def test_health_includes_latency(self, health_cog, mock_context):
        """Should include latency in embed."""
        await health_cog.health.callback(health_cog, mock_context)

        embed = mock_context.send.call_args[1]["embed"]
        field_names = [field.name for field in embed.fields]
        assert "Latency" in field_names

    @pytest.mark.asyncio
    async def test_health_regular_user_no_admin_info(self, health_cog, mock_context):
        """Should not show admin info to regular users."""
        mock_context.author.guild_permissions.administrator = False

        await health_cog.health.callback(health_cog, mock_context)

        embed = mock_context.send.call_args[1]["embed"]
        field_names = [field.name for field in embed.fields]

        # Should not have admin fields
        assert "Memory" not in field_names
        assert "Database" not in field_names

    @pytest.mark.asyncio
    async def test_health_admin_sees_admin_info(
        self, health_cog, mock_admin_context, mock_container
    ):
        """Should show admin info to administrators."""
        # Mock memory info
        mock_process = MagicMock()
        mock_memory = MagicMock()
        mock_memory.rss = 100 * 1024 * 1024
        mock_memory.vms = 200 * 1024 * 1024
        mock_process.memory_full_info.return_value = mock_memory
        mock_process.oneshot.return_value.__enter__ = lambda self: None
        mock_process.oneshot.return_value.__exit__ = lambda self, *args: None

        with patch("psutil.Process", return_value=mock_process):
            await health_cog.health.callback(health_cog, mock_admin_context)

        embed = mock_admin_context.send.call_args[1]["embed"]
        field_names = [field.name for field in embed.fields]

        # Should have admin fields
        assert "Memory" in field_names
        assert "Database" in field_names

    @pytest.mark.asyncio
    async def test_health_embed_color_based_on_latency(self, health_cog, mock_context, mock_bot):
        """Should set embed color based on latency."""
        mock_bot.latency = 1.0  # High latency

        await health_cog.health.callback(health_cog, mock_context)

        embed = mock_context.send.call_args[1]["embed"]
        assert embed.color == discord.Color.red()

    @pytest.mark.asyncio
    async def test_health_includes_timestamp(self, health_cog, mock_context):
        """Should include timestamp in embed."""
        await health_cog.health.callback(health_cog, mock_context)

        embed = mock_context.send.call_args[1]["embed"]
        assert embed.timestamp is not None

    @pytest.mark.asyncio
    async def test_health_includes_footer(self, health_cog, mock_context):
        """Should include footer text."""
        await health_cog.health.callback(health_cog, mock_context)

        embed = mock_context.send.call_args[1]["embed"]
        assert embed.footer is not None
        assert embed.footer.text is not None


# =============================================================================
# Embed Building Tests
# =============================================================================


class TestEmbedBuilding:
    """Tests for health embed construction."""

    def test_build_health_embed_basic_structure(self, health_cog):
        """Should build embed with basic structure."""
        payload: DetailedStats = {
            "ts": "2024-01-01T00:00:00Z",
            "uptime_s": 3600,
            "uptime_human": "1h 0m 0s",
            "latency_ms": 50.0,
            "latency_human": "50.0 ms",
            "queue_len": 0,
            "current": None,
            "connected": True,
            "status": "online",
        }

        embed = health_cog._build_health_embed(payload, False)

        assert isinstance(embed, discord.Embed)
        assert embed.title is not None
        assert len(embed.fields) > 0

    def test_build_health_embed_with_admin_info(self, health_cog):
        """Should include admin fields when requested."""
        payload: DetailedStats = {
            "ts": "2024-01-01T00:00:00Z",
            "uptime_s": 3600,
            "uptime_human": "1h 0m 0s",
            "latency_ms": 50.0,
            "latency_human": "50.0 ms",
            "queue_len": 0,
            "current": None,
            "connected": True,
            "status": "online",
            "guild_count": 5,
            "voice_connections": 2,
            "rss_mb": 100.0,
            "vms_mb": 200.0,
            "db_initialized": True,
            "db_size_mb": 5.5,
        }

        embed = health_cog._build_health_embed(payload, True)

        field_names = [field.name for field in embed.fields]
        assert "Memory" in field_names
        assert "Database" in field_names

    def test_is_admin_with_administrator(self, health_cog):
        """Should recognize administrator permission."""
        member = MagicMock(spec=discord.Member)
        member.guild_permissions.administrator = True

        result = health_cog._is_admin(member)

        assert result is True

    def test_is_admin_without_administrator(self, health_cog):
        """Should reject non-administrator."""
        member = MagicMock(spec=discord.Member)
        member.guild_permissions.administrator = False

        result = health_cog._is_admin(member)

        assert result is False

    def test_is_admin_with_user_not_member(self, health_cog):
        """Should return False for non-Member user."""
        user = MagicMock(spec=discord.User)

        result = health_cog._is_admin(user)

        assert result is False

    def test_format_memory_stats_with_both(self, health_cog):
        """Should format both RSS and VMS memory stats."""
        payload: DetailedStats = {
            "ts": "2024-01-01T00:00:00Z",
            "uptime_s": 0,
            "uptime_human": "0s",
            "latency_ms": 0.0,
            "latency_human": "0.0 ms",
            "queue_len": 0,
            "current": None,
            "connected": True,
            "status": "online",
            "rss_mb": 100.5,
            "vms_mb": 250.3,
        }

        result = health_cog._format_memory_stats(payload)

        assert len(result) == 2
        assert "RSS: 100.5 MB" in result
        assert "VMS: 250.3 MB" in result

    def test_format_memory_stats_rss_only(self, health_cog):
        """Should format RSS only when VMS not available."""
        payload: DetailedStats = {
            "ts": "2024-01-01T00:00:00Z",
            "uptime_s": 0,
            "uptime_human": "0s",
            "latency_ms": 0.0,
            "latency_human": "0.0 ms",
            "queue_len": 0,
            "current": None,
            "connected": True,
            "status": "online",
            "rss_mb": 100.5,
        }

        result = health_cog._format_memory_stats(payload)

        assert len(result) == 1
        assert "RSS: 100.5 MB" in result

    def test_format_memory_stats_empty_when_none(self, health_cog):
        """Should return empty list when no memory stats."""
        payload: DetailedStats = {
            "ts": "2024-01-01T00:00:00Z",
            "uptime_s": 0,
            "uptime_human": "0s",
            "latency_ms": 0.0,
            "latency_human": "0.0 ms",
            "queue_len": 0,
            "current": None,
            "connected": True,
            "status": "online",
        }

        result = health_cog._format_memory_stats(payload)

        assert len(result) == 0


# =============================================================================
# Setup Function Tests
# =============================================================================


class TestSetupFunction:
    """Tests for the setup function."""

    @pytest.mark.asyncio
    async def test_setup_requires_container(self, mock_bot):
        """Should raise error when container not found."""
        from discord_music_player.infrastructure.discord.cogs.health_cog import setup

        mock_bot.container = None

        with pytest.raises(RuntimeError, match="Container not found"):
            await setup(mock_bot)

    @pytest.mark.asyncio
    async def test_setup_adds_cog(self, mock_bot, mock_container):
        """Should add HealthCog to bot."""
        from discord_music_player.infrastructure.discord.cogs.health_cog import setup

        mock_bot.container = mock_container
        mock_bot.add_cog = AsyncMock()

        with patch.object(tasks.Loop, "change_interval"):
            await setup(mock_bot)

        mock_bot.add_cog.assert_called_once()
        cog = mock_bot.add_cog.call_args[0][0]
        assert isinstance(cog, HealthCog)
