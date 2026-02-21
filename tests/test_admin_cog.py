"""
Comprehensive Unit Tests for AdminCog

Tests for all prefix commands and functionality in the admin cog:
- /sync, /slash_status - Slash command synchronization
- /reload, /reload_all - Cog management
- /cache_status, /cache_clear, /cache_prune - Cache operations
- /db_cleanup, /db_stats, /db_validate - Database operations
- /status, /shutdown - System info and lifecycle
- Permission checking (owner/admin only)
- Error handling and validation
- Discord context mocking
- Edge cases (missing guild, invalid args, etc.)

Uses pytest with async/await patterns and proper mocking.
"""

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord.ext import commands

from discord_music_player.domain.shared.messages import DiscordUIMessages, ErrorMessages
from discord_music_player.infrastructure.discord.cogs.admin_cog import (
    AdminCog,
    require_owner,
    require_owner_or_admin,
)
from discord_music_player.infrastructure.persistence.database import (
    ColumnValidation,
    CountValidation,
    DatabaseStats,
    PragmaValidation,
    SchemaValidationResult,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_bot():
    """Create a mock Discord bot."""
    bot = MagicMock(spec=commands.Bot)
    bot.application = MagicMock()
    bot.application.owner = MagicMock()
    bot.application.owner.id = 999999999
    bot.tree = MagicMock()
    bot.tree.sync = AsyncMock(return_value=[MagicMock() for _ in range(3)])
    bot.tree.fetch_commands = AsyncMock(return_value=[])
    bot.tree.get_commands = MagicMock(return_value=[])
    bot.extensions = {}
    bot.reload_extension = AsyncMock()
    bot.guilds = [MagicMock() for _ in range(5)]
    bot.voice_clients = [MagicMock(), MagicMock()]
    bot.cogs = {"PlaybackCog": MagicMock(), "AdminCog": MagicMock()}
    bot.latency = 0.05  # 50ms
    bot.close = AsyncMock()
    return bot


@pytest.fixture
def mock_container():
    """Create a mock DI container."""
    container = MagicMock()

    # Mock settings
    container.settings = MagicMock()
    container.settings.discord.owner_ids = [999999999]
    container.settings.environment = "testing"

    # Mock AI client
    container.ai_client = MagicMock()
    container.ai_client.get_cache_stats = MagicMock(
        return_value={
            "size": 10,
            "hits": 50,
            "misses": 25,
            "hit_rate": 66.67,
            "inflight": 2,
        }
    )
    container.ai_client.clear_cache = MagicMock(return_value=10)
    container.ai_client.prune_cache = MagicMock(return_value=5)

    # Mock database
    container.database = MagicMock()
    container.database.get_stats = AsyncMock(
        return_value=DatabaseStats(
            initialized=True,
            file_size_mb=2.5,
            page_count=1024,
            db_path="/tmp/test.db",
            tables={
                "sessions": 10,
                "history": 100,
                "votes": 5,
            },
        )
    )

    container.database.validate_schema = AsyncMock(
        return_value=SchemaValidationResult(
            tables=CountValidation(expected=7, found=7, missing=[]),
            columns=ColumnValidation(expected=47, found=47, missing={}),
            indexes=CountValidation(expected=9, found=9, missing=[]),
            pragmas=PragmaValidation(journal_mode="wal", foreign_keys=1),
            issues=[],
        )
    )

    # Mock cleanup job
    cleanup_stats = MagicMock()
    cleanup_stats.sessions_cleaned = 5
    cleanup_stats.votes_cleaned = 3
    cleanup_stats.cache_cleaned = 8
    cleanup_stats.history_cleaned = 20
    cleanup_stats.total_cleaned = 36

    container.cleanup_job = MagicMock()
    container.cleanup_job.run_cleanup = AsyncMock(return_value=cleanup_stats)
    container.cleanup_job.shutdown = AsyncMock()

    return container


@pytest.fixture
def admin_cog(mock_bot, mock_container):
    """Create an AdminCog instance with mocked dependencies."""
    mock_bot.container = mock_container
    return AdminCog(mock_bot, mock_container)


@pytest.fixture
def mock_ctx():
    """Create a mock Discord Context for prefix commands."""
    ctx = MagicMock(spec=commands.Context)
    ctx.send = AsyncMock()

    # Guild setup
    ctx.guild = MagicMock(spec=discord.Guild)
    ctx.guild.id = 111111111

    # Author setup (regular member)
    ctx.author = MagicMock(spec=discord.Member)
    ctx.author.id = 333333333
    ctx.author.guild_permissions = MagicMock()
    ctx.author.guild_permissions.administrator = False
    ctx.author.guild_permissions.manage_guild = False

    # Bot setup
    ctx.bot = MagicMock()
    ctx.bot.application = MagicMock()
    ctx.bot.application.owner = MagicMock()
    ctx.bot.application.owner.id = 999999999

    return ctx


@pytest.fixture
def mock_admin_ctx(mock_ctx, mock_container):
    """Create a mock context for an admin user."""
    mock_ctx.author.guild_permissions.administrator = True
    mock_ctx.bot.container = mock_container
    return mock_ctx


@pytest.fixture
def mock_owner_ctx(mock_ctx, mock_container):
    """Create a mock context for a bot owner."""
    mock_ctx.author.id = 999999999  # Owner ID
    mock_ctx.bot.container = mock_container
    return mock_ctx


# =============================================================================
# Permission Decorator Tests
# =============================================================================


class TestRequireOwnerOrAdmin:
    """Tests for require_owner_or_admin decorator."""

    @pytest.mark.asyncio
    async def test_allows_bot_owner(self, mock_owner_ctx):
        """Should allow bot owner."""
        check = require_owner_or_admin()
        result = await check.predicate(mock_owner_ctx)

        assert result is True

    @pytest.mark.asyncio
    async def test_allows_container_owner(self, mock_ctx, mock_container):
        """Should allow owner from container settings."""
        mock_ctx.bot.container = mock_container
        mock_ctx.author.id = 999999999

        check = require_owner_or_admin()
        result = await check.predicate(mock_ctx)

        assert result is True

    @pytest.mark.asyncio
    async def test_allows_administrator(self, mock_admin_ctx):
        """Should allow guild administrator."""
        check = require_owner_or_admin()
        result = await check.predicate(mock_admin_ctx)

        assert result is True

    @pytest.mark.asyncio
    async def test_allows_manage_guild(self, mock_ctx, mock_container):
        """Should allow user with manage_guild permission."""
        mock_ctx.bot.container = mock_container
        mock_ctx.author.guild_permissions.manage_guild = True

        check = require_owner_or_admin()
        result = await check.predicate(mock_ctx)

        assert result is True

    @pytest.mark.asyncio
    async def test_denies_regular_user(self, mock_ctx, mock_container):
        """Should deny regular user."""
        mock_ctx.bot.container = mock_container

        check = require_owner_or_admin()
        result = await check.predicate(mock_ctx)

        assert result is False

    @pytest.mark.asyncio
    async def test_denies_when_no_guild(self, mock_ctx, mock_container):
        """Should deny when not in a guild."""
        mock_ctx.guild = None
        mock_ctx.bot.container = mock_container

        check = require_owner_or_admin()
        result = await check.predicate(mock_ctx)

        assert result is False


class TestRequireOwner:
    """Tests for require_owner decorator (owner-only, no guild admin fallback)."""

    @pytest.mark.asyncio
    async def test_allows_application_owner(self, mock_owner_ctx):
        """Should allow the application owner."""
        check = require_owner()
        result = await check.predicate(mock_owner_ctx)

        assert result is True

    @pytest.mark.asyncio
    async def test_allows_container_owner(self, mock_ctx, mock_container):
        """Should allow owner from container settings."""
        mock_ctx.bot.container = mock_container
        mock_ctx.author.id = 999999999

        check = require_owner()
        result = await check.predicate(mock_ctx)

        assert result is True

    @pytest.mark.asyncio
    async def test_denies_guild_administrator(self, mock_admin_ctx):
        """Should deny guild administrator (owner-only)."""
        check = require_owner()
        result = await check.predicate(mock_admin_ctx)

        assert result is False

    @pytest.mark.asyncio
    async def test_denies_manage_guild(self, mock_ctx, mock_container):
        """Should deny user with manage_guild permission (owner-only)."""
        mock_ctx.bot.container = mock_container
        mock_ctx.author.guild_permissions.manage_guild = True

        check = require_owner()
        result = await check.predicate(mock_ctx)

        assert result is False

    @pytest.mark.asyncio
    async def test_denies_regular_user(self, mock_ctx, mock_container):
        """Should deny regular user."""
        mock_ctx.bot.container = mock_container

        check = require_owner()
        result = await check.predicate(mock_ctx)

        assert result is False

    @pytest.mark.asyncio
    async def test_denies_when_no_guild(self, mock_ctx, mock_container):
        """Should deny when not in a guild."""
        mock_ctx.guild = None
        mock_ctx.bot.container = mock_container

        check = require_owner()
        result = await check.predicate(mock_ctx)

        assert result is False


# =============================================================================
# Cog Initialization Tests
# =============================================================================


class TestAdminCogInitialization:
    """Tests for AdminCog initialization and setup."""

    def test_cog_initializes_with_bot_and_container(self, mock_bot, mock_container):
        """Should initialize with bot and container."""
        cog = AdminCog(mock_bot, mock_container)

        assert cog.bot == mock_bot
        assert cog.container == mock_container

    @pytest.mark.asyncio
    async def test_setup_creates_cog(self, mock_bot, mock_container):
        """Should create and add cog to bot."""
        from discord_music_player.infrastructure.discord.cogs.admin_cog import setup

        mock_bot.container = mock_container
        mock_bot.add_cog = AsyncMock()

        await setup(mock_bot)

        mock_bot.add_cog.assert_called_once()
        args = mock_bot.add_cog.call_args[0]
        assert isinstance(args[0], AdminCog)

    @pytest.mark.asyncio
    async def test_setup_raises_without_container(self, mock_bot):
        """Should raise RuntimeError when container not found."""
        from discord_music_player.infrastructure.discord.cogs.admin_cog import setup

        mock_bot.container = None

        with pytest.raises(RuntimeError, match=ErrorMessages.CONTAINER_NOT_FOUND):
            await setup(mock_bot)


# =============================================================================
# Helper Method Tests
# =============================================================================


class TestHelperMethods:
    """Tests for internal helper methods."""

    @pytest.mark.asyncio
    async def test_reply_sends_content(self, admin_cog, mock_ctx):
        """Should send content message."""
        await admin_cog._reply(mock_ctx, "Test message")

        mock_ctx.send.assert_called_once_with("Test message")

    @pytest.mark.asyncio
    async def test_reply_sends_embed(self, admin_cog, mock_ctx):
        """Should send embed message."""
        embed = discord.Embed(title="Test")

        await admin_cog._reply(mock_ctx, embed=embed)

        mock_ctx.send.assert_called_once_with("", embed=embed)

    @pytest.mark.asyncio
    async def test_reply_sends_content_and_embed(self, admin_cog, mock_ctx):
        """Should send both content and embed."""
        embed = discord.Embed(title="Test")

        await admin_cog._reply(mock_ctx, "Test content", embed=embed)

        mock_ctx.send.assert_called_once_with("Test content", embed=embed)

    @pytest.mark.asyncio
    async def test_reply_defaults_to_success(self, admin_cog, mock_ctx):
        """Should send default success message when no content."""
        await admin_cog._reply(mock_ctx)

        mock_ctx.send.assert_called_once_with(DiscordUIMessages.SUCCESS_GENERIC)


# =============================================================================
# Error Handler Tests
# =============================================================================


class TestErrorHandler:
    """Tests for cog_command_error handler."""

    @pytest.mark.asyncio
    async def test_handles_check_failure(self, admin_cog, mock_ctx):
        """Should handle CheckFailure error."""
        error = commands.CheckFailure()

        await admin_cog.cog_command_error(mock_ctx, error)

        mock_ctx.send.assert_called_once_with(DiscordUIMessages.ERROR_REQUIRES_OWNER_OR_ADMIN)

    @pytest.mark.asyncio
    async def test_handles_missing_required_argument(self, admin_cog, mock_ctx):
        """Should handle MissingRequiredArgument error."""
        param = MagicMock()
        param.name = "test_param"
        error = commands.MissingRequiredArgument(param)

        await admin_cog.cog_command_error(mock_ctx, error)

        call_args = mock_ctx.send.call_args[0][0]
        assert "test_param" in call_args

    @pytest.mark.asyncio
    async def test_handles_bad_argument(self, admin_cog, mock_ctx):
        """Should handle BadArgument error."""
        error = commands.BadArgument()

        await admin_cog.cog_command_error(mock_ctx, error)

        mock_ctx.send.assert_called_once_with(DiscordUIMessages.ERROR_INVALID_ARGUMENT)

    @pytest.mark.asyncio
    async def test_handles_generic_exception(self, admin_cog, mock_ctx):
        """Should handle generic exceptions."""
        error = Exception("Something went wrong")

        await admin_cog.cog_command_error(mock_ctx, error)

        mock_ctx.send.assert_called_once_with(DiscordUIMessages.ERROR_COMMAND_FAILED_SEE_LOGS)

    @pytest.mark.asyncio
    async def test_handles_original_exception(self, admin_cog, mock_ctx):
        """Should extract original exception from command error."""
        original = ValueError("Original error")
        error = MagicMock()
        error.original = original

        await admin_cog.cog_command_error(mock_ctx, error)

        mock_ctx.send.assert_called_once()


# =============================================================================
# /sync Command Tests
# =============================================================================


class TestSyncCommand:
    """Tests for /sync command."""

    @pytest.mark.asyncio
    async def test_sync_guild_success(self, admin_cog, mock_admin_ctx, mock_bot):
        """Should sync commands to guild."""
        mock_admin_ctx.bot.tree = mock_bot.tree

        await admin_cog.sync.callback(admin_cog, mock_admin_ctx, scope="guild")

        mock_bot.tree.sync.assert_called_once_with(guild=mock_admin_ctx.guild)
        call_args = mock_admin_ctx.send.call_args[0][0]
        assert "3" in call_args  # 3 commands synced

    @pytest.mark.asyncio
    async def test_sync_global_success(self, admin_cog, mock_admin_ctx, mock_bot):
        """Should sync commands globally."""
        mock_admin_ctx.bot.tree = mock_bot.tree

        await admin_cog.sync.callback(admin_cog, mock_admin_ctx, scope="global")

        mock_bot.tree.sync.assert_called_once_with()
        call_args = mock_admin_ctx.send.call_args[0][0]
        assert "3" in call_args
        assert "globally" in call_args.lower()

    @pytest.mark.asyncio
    async def test_sync_default_is_guild(self, admin_cog, mock_admin_ctx, mock_bot):
        """Should default to guild scope."""
        mock_admin_ctx.bot.tree = mock_bot.tree

        await admin_cog.sync.callback(admin_cog, mock_admin_ctx)

        mock_bot.tree.sync.assert_called_once_with(guild=mock_admin_ctx.guild)

    @pytest.mark.asyncio
    async def test_sync_case_insensitive(self, admin_cog, mock_admin_ctx, mock_bot):
        """Should handle case insensitive scope."""
        mock_admin_ctx.bot.tree = mock_bot.tree

        await admin_cog.sync.callback(admin_cog, mock_admin_ctx, scope="GLOBAL")

        mock_bot.tree.sync.assert_called_once_with()

    @pytest.mark.asyncio
    async def test_sync_strips_whitespace(self, admin_cog, mock_admin_ctx, mock_bot):
        """Should strip whitespace from scope."""
        mock_admin_ctx.bot.tree = mock_bot.tree

        await admin_cog.sync.callback(admin_cog, mock_admin_ctx, scope="  guild  ")

        mock_bot.tree.sync.assert_called_once_with(guild=mock_admin_ctx.guild)

    @pytest.mark.asyncio
    async def test_sync_guild_requires_guild_context(self, admin_cog, mock_admin_ctx, mock_bot):
        """Should require guild for guild scope."""
        mock_admin_ctx.guild = None
        mock_admin_ctx.bot.tree = mock_bot.tree

        await admin_cog.sync.callback(admin_cog, mock_admin_ctx, scope="guild")

        call_args = mock_admin_ctx.send.call_args[0][0]
        assert "server" in call_args.lower() or "global" in call_args.lower()

    @pytest.mark.asyncio
    async def test_sync_handles_exception(self, admin_cog, mock_admin_ctx, mock_bot):
        """Should handle sync exceptions gracefully."""
        mock_admin_ctx.bot.tree = mock_bot.tree
        mock_bot.tree.sync.side_effect = Exception("API error")

        await admin_cog.sync.callback(admin_cog, mock_admin_ctx, scope="global")

        call_args = mock_admin_ctx.send.call_args[0][0]
        assert "failed" in call_args.lower()


# =============================================================================
# /slash_status Command Tests
# =============================================================================


class TestSlashStatusCommand:
    """Tests for /slash_status command."""

    @pytest.mark.asyncio
    async def test_slash_status_success(self, admin_cog, mock_admin_ctx, mock_bot):
        """Should display slash command status."""
        mock_admin_ctx.bot.tree = mock_bot.tree

        # Mock commands
        global_cmd = MagicMock()
        global_cmd.name = "play"
        guild_cmd = MagicMock()
        guild_cmd.name = "skip"

        mock_bot.tree.fetch_commands = AsyncMock(return_value=[global_cmd])

        await admin_cog.slash_status.callback(admin_cog, mock_admin_ctx)

        # Should send embed
        call_kwargs = mock_admin_ctx.send.call_args.kwargs
        assert "embed" in call_kwargs
        embed = call_kwargs["embed"]
        assert "Slash Command Status" in embed.title

    @pytest.mark.asyncio
    async def test_slash_status_with_guild(self, admin_cog, mock_admin_ctx, mock_bot):
        """Should include guild commands when in guild."""
        mock_admin_ctx.bot.tree = mock_bot.tree

        guild_cmd = MagicMock()
        guild_cmd.name = "admin"

        mock_bot.tree.fetch_commands = AsyncMock(
            side_effect=lambda guild=None: [guild_cmd] if guild else []
        )

        await admin_cog.slash_status.callback(admin_cog, mock_admin_ctx)

        # Should have fetched both global and guild commands
        assert mock_bot.tree.fetch_commands.call_count == 2

    @pytest.mark.asyncio
    async def test_slash_status_truncates_long_names(self, admin_cog, mock_admin_ctx, mock_bot):
        """Should truncate long command name lists."""
        mock_admin_ctx.bot.tree = mock_bot.tree

        # Create many commands
        commands = [MagicMock(name=f"cmd{i}") for i in range(100)]
        mock_bot.tree.fetch_commands = AsyncMock(return_value=commands)

        await admin_cog.slash_status.callback(admin_cog, mock_admin_ctx)

        call_kwargs = mock_admin_ctx.send.call_args.kwargs
        embed = call_kwargs["embed"]

        # Find the Global Names field
        for field in embed.fields:
            if field.name == "Global Names":
                assert len(field.value) <= 501  # 500 + ellipsis

    @pytest.mark.asyncio
    async def test_slash_status_handles_exception(self, admin_cog, mock_admin_ctx, mock_bot):
        """Should handle fetch exceptions."""
        mock_admin_ctx.bot.tree = mock_bot.tree
        mock_bot.tree.fetch_commands = AsyncMock(side_effect=Exception("API error"))

        await admin_cog.slash_status.callback(admin_cog, mock_admin_ctx)

        call_args = mock_admin_ctx.send.call_args[0][0]
        assert "failed" in call_args.lower()


# =============================================================================
# /reload Command Tests
# =============================================================================


class TestReloadCommand:
    """Tests for /reload command."""

    @pytest.mark.asyncio
    async def test_reload_success_new_path(self, admin_cog, mock_admin_ctx, mock_bot):
        """Should reload extension with new path format."""
        mock_admin_ctx.bot = mock_bot

        await admin_cog.reload.callback(admin_cog, mock_admin_ctx, "music_cog")

        mock_bot.reload_extension.assert_called_once_with(
            "discord_music_player.infrastructure.discord.cogs.music_cog"
        )
        call_args = mock_admin_ctx.send.call_args[0][0]
        assert "Reloaded" in call_args

    @pytest.mark.asyncio
    async def test_reload_with_full_path(self, admin_cog, mock_admin_ctx, mock_bot):
        """Should reload with full path provided."""
        mock_admin_ctx.bot = mock_bot

        await admin_cog.reload.callback(
            admin_cog, mock_admin_ctx, "discord_music_player.infrastructure.discord.cogs.music_cog"
        )

        mock_bot.reload_extension.assert_called_once_with(
            "discord_music_player.infrastructure.discord.cogs.music_cog"
        )

    @pytest.mark.asyncio
    async def test_reload_tries_old_path_on_failure(self, admin_cog, mock_admin_ctx, mock_bot):
        """Should try old path format if new path fails."""
        mock_admin_ctx.bot = mock_bot

        # First call fails with ExtensionNotLoaded
        mock_bot.reload_extension = AsyncMock(
            side_effect=[commands.ExtensionNotLoaded("test"), None]
        )

        await admin_cog.reload.callback(admin_cog, mock_admin_ctx, "music_cog")

        # Should have tried both paths
        assert mock_bot.reload_extension.call_count == 2
        calls = mock_bot.reload_extension.call_args_list
        assert calls[0][0][0] == "discord_music_player.infrastructure.discord.cogs.music_cog"
        assert calls[1][0][0] == "cog.music_cog"

    @pytest.mark.asyncio
    async def test_reload_handles_exception(self, admin_cog, mock_admin_ctx, mock_bot):
        """Should handle reload exceptions."""
        mock_admin_ctx.bot = mock_bot
        mock_bot.reload_extension = AsyncMock(side_effect=Exception("Import error"))

        await admin_cog.reload.callback(admin_cog, mock_admin_ctx, "broken_cog")

        call_args = mock_admin_ctx.send.call_args[0][0]
        assert "Failed to reload" in call_args


# =============================================================================
# /reload_all Command Tests
# =============================================================================


class TestReloadAllCommand:
    """Tests for /reload_all command."""

    @pytest.mark.asyncio
    async def test_reload_all_success(self, admin_cog, mock_admin_ctx, mock_bot):
        """Should reload all extensions."""
        mock_admin_ctx.bot = mock_bot
        mock_bot.extensions = {
            "cog.music": MagicMock(),
            "cog.admin": MagicMock(),
        }

        await admin_cog.reload_all.callback(admin_cog, mock_admin_ctx)

        assert mock_bot.reload_extension.call_count == 2
        call_args = mock_admin_ctx.send.call_args[0][0]
        assert "2" in call_args
        assert "0" in call_args  # 0 failed

    @pytest.mark.asyncio
    async def test_reload_all_with_failures(self, admin_cog, mock_admin_ctx, mock_bot):
        """Should handle partial failures."""
        mock_admin_ctx.bot = mock_bot
        mock_bot.extensions = {
            "cog.music": MagicMock(),
            "cog.admin": MagicMock(),
        }

        # First succeeds, second fails
        mock_bot.reload_extension = AsyncMock(side_effect=[None, Exception("Error")])

        await admin_cog.reload_all.callback(admin_cog, mock_admin_ctx)

        call_args = mock_admin_ctx.send.call_args[0][0]
        assert "1" in call_args  # 1 success
        assert "1" in call_args  # 1 failed

    @pytest.mark.asyncio
    async def test_reload_all_no_extensions(self, admin_cog, mock_admin_ctx, mock_bot):
        """Should handle no extensions loaded."""
        mock_admin_ctx.bot = mock_bot
        mock_bot.extensions = {}

        await admin_cog.reload_all.callback(admin_cog, mock_admin_ctx)

        call_args = mock_admin_ctx.send.call_args[0][0]
        assert "No extensions" in call_args


# =============================================================================
# Cache Management Command Tests
# =============================================================================


class TestCacheCommands:
    """Tests for cache management commands."""

    @pytest.mark.asyncio
    async def test_cache_status_success(self, admin_cog, mock_admin_ctx):
        """Should display cache statistics."""
        await admin_cog.cache_status.callback(admin_cog, mock_admin_ctx)

        call_kwargs = mock_admin_ctx.send.call_args.kwargs
        assert "embed" in call_kwargs
        embed = call_kwargs["embed"]
        assert "Cache Statistics" in embed.title

        # Check fields
        field_names = [f.name for f in embed.fields]
        assert "Size" in field_names
        assert "Hits" in field_names
        assert "Misses" in field_names
        assert "Hit Rate" in field_names

    @pytest.mark.asyncio
    async def test_cache_status_handles_exception(self, admin_cog, mock_admin_ctx, mock_container):
        """Should handle cache status exceptions."""
        mock_container.ai_client.get_cache_stats.side_effect = Exception("Cache error")

        await admin_cog.cache_status.callback(admin_cog, mock_admin_ctx)

        call_args = mock_admin_ctx.send.call_args[0][0]
        assert "failed" in call_args.lower()

    @pytest.mark.asyncio
    async def test_cache_clear_success(self, admin_cog, mock_admin_ctx):
        """Should clear cache."""
        await admin_cog.cache_clear.callback(admin_cog, mock_admin_ctx)

        call_args = mock_admin_ctx.send.call_args[0][0]
        assert "10" in call_args  # 10 entries cleared
        assert "Cleared" in call_args

    @pytest.mark.asyncio
    async def test_cache_clear_handles_exception(self, admin_cog, mock_admin_ctx, mock_container):
        """Should handle cache clear exceptions."""
        mock_container.ai_client.clear_cache.side_effect = Exception("Clear error")

        await admin_cog.cache_clear.callback(admin_cog, mock_admin_ctx)

        call_args = mock_admin_ctx.send.call_args[0][0]
        assert "failed" in call_args.lower()

    @pytest.mark.asyncio
    async def test_cache_prune_default_age(self, admin_cog, mock_admin_ctx, mock_container):
        """Should prune cache with default age."""
        await admin_cog.cache_prune.callback(admin_cog, mock_admin_ctx)

        mock_container.ai_client.prune_cache.assert_called_once_with(3600)
        call_args = mock_admin_ctx.send.call_args[0][0]
        assert "5" in call_args  # 5 entries pruned

    @pytest.mark.asyncio
    async def test_cache_prune_custom_age(self, admin_cog, mock_admin_ctx, mock_container):
        """Should prune cache with custom age."""
        await admin_cog.cache_prune.callback(admin_cog, mock_admin_ctx, max_age_seconds=1800)

        mock_container.ai_client.prune_cache.assert_called_once_with(1800)

    @pytest.mark.asyncio
    async def test_cache_prune_handles_exception(self, admin_cog, mock_admin_ctx, mock_container):
        """Should handle cache prune exceptions."""
        mock_container.ai_client.prune_cache.side_effect = Exception("Prune error")

        await admin_cog.cache_prune.callback(admin_cog, mock_admin_ctx)

        call_args = mock_admin_ctx.send.call_args[0][0]
        assert "failed" in call_args.lower()


# =============================================================================
# Database Command Tests
# =============================================================================


class TestDatabaseCommands:
    """Tests for database management commands."""

    @pytest.mark.asyncio
    async def test_db_cleanup_success(self, admin_cog, mock_admin_ctx):
        """Should run database cleanup."""
        await admin_cog.db_cleanup.callback(admin_cog, mock_admin_ctx)

        call_kwargs = mock_admin_ctx.send.call_args.kwargs
        assert "embed" in call_kwargs
        embed = call_kwargs["embed"]
        assert "Cleanup Results" in embed.title

        # Check fields
        field_values = {f.name: f.value for f in embed.fields}
        assert field_values["Sessions"] == "5"
        assert field_values["Votes"] == "3"
        assert field_values["Cache"] == "8"
        assert field_values["History"] == "20"
        assert field_values["Total"] == "36"

    @pytest.mark.asyncio
    async def test_db_cleanup_handles_exception(self, admin_cog, mock_admin_ctx, mock_container):
        """Should handle cleanup exceptions."""
        mock_container.cleanup_job.run_cleanup.side_effect = Exception("Cleanup error")

        await admin_cog.db_cleanup.callback(admin_cog, mock_admin_ctx)

        call_args = mock_admin_ctx.send.call_args[0][0]
        assert "failed" in call_args.lower()

    @pytest.mark.asyncio
    async def test_db_stats_success(self, admin_cog, mock_admin_ctx):
        """Should display database statistics."""
        await admin_cog.db_stats.callback(admin_cog, mock_admin_ctx)

        call_kwargs = mock_admin_ctx.send.call_args.kwargs
        assert "embed" in call_kwargs
        embed = call_kwargs["embed"]
        assert "Database Statistics" in embed.title

        # Check fields
        field_names = [f.name for f in embed.fields]
        assert "Initialized" in field_names
        assert "File Size" in field_names
        assert "Page Count" in field_names
        assert "Tables" in field_names

    @pytest.mark.asyncio
    async def test_db_stats_shows_table_counts(self, admin_cog, mock_admin_ctx):
        """Should show table row counts."""
        await admin_cog.db_stats.callback(admin_cog, mock_admin_ctx)

        call_kwargs = mock_admin_ctx.send.call_args.kwargs
        embed = call_kwargs["embed"]

        # Find tables field
        tables_field = next(f for f in embed.fields if f.name == "Tables")
        assert "sessions: 10" in tables_field.value
        assert "history: 100" in tables_field.value
        assert "votes: 5" in tables_field.value

    @pytest.mark.asyncio
    async def test_db_stats_shows_filename_only(self, admin_cog, mock_admin_ctx, mock_container):
        """Should show only filename, not full filesystem path (security)."""
        mock_container.database.get_stats = AsyncMock(
            return_value=DatabaseStats(
                initialized=True,
                file_size_mb=1.0,
                page_count=100,
                db_path="/home/user/secret/path/data/bot.db",
            )
        )

        await admin_cog.db_stats.callback(admin_cog, mock_admin_ctx)

        call_kwargs = mock_admin_ctx.send.call_args.kwargs
        embed = call_kwargs["embed"]

        db_field = next(f for f in embed.fields if f.name == "Database")
        assert db_field.value == "bot.db"
        assert "/home" not in db_field.value

    @pytest.mark.asyncio
    async def test_db_stats_handles_exception(self, admin_cog, mock_admin_ctx, mock_container):
        """Should handle db stats exceptions."""
        mock_container.database.get_stats.side_effect = Exception("DB error")

        await admin_cog.db_stats.callback(admin_cog, mock_admin_ctx)

        call_args = mock_admin_ctx.send.call_args[0][0]
        assert "failed" in call_args.lower()

    @pytest.mark.asyncio
    async def test_db_validate_success_no_issues(self, admin_cog, mock_admin_ctx):
        """Should display green embed when schema is valid."""
        await admin_cog.db_validate.callback(admin_cog, mock_admin_ctx)

        call_kwargs = mock_admin_ctx.send.call_args.kwargs
        assert "embed" in call_kwargs
        embed = call_kwargs["embed"]
        assert "Database Validation" in embed.title
        assert embed.color == discord.Color.green()

        field_values = {f.name: f.value for f in embed.fields}
        assert field_values["Tables"] == "7/7"
        assert field_values["Columns"] == "47/47"
        assert field_values["Indexes"] == "9/9"
        assert "✅" in field_values["Pragmas"]

        # No Issues field when everything is fine
        assert "Issues" not in field_values

    @pytest.mark.asyncio
    async def test_db_validate_with_issues(self, admin_cog, mock_admin_ctx, mock_container):
        """Should display orange embed when issues are found."""
        mock_container.database.validate_schema = AsyncMock(
            return_value=SchemaValidationResult(
                tables=CountValidation(expected=7, found=6, missing=["track_genres"]),
                columns=ColumnValidation(expected=47, found=44, missing={"track_genres": ["track_id", "genre", "classified_at"]}),
                indexes=CountValidation(expected=9, found=8, missing=["idx_track_genres_genre"]),
                pragmas=PragmaValidation(journal_mode="wal", foreign_keys=1),
                issues=[
                    "Missing tables: track_genres",
                    "Missing columns in track_genres: track_id, genre, classified_at",
                    "Missing indexes: idx_track_genres_genre",
                ],
            )
        )

        await admin_cog.db_validate.callback(admin_cog, mock_admin_ctx)

        call_kwargs = mock_admin_ctx.send.call_args.kwargs
        embed = call_kwargs["embed"]
        assert embed.color == discord.Color.orange()

        field_values = {f.name: f.value for f in embed.fields}
        assert field_values["Tables"] == "6/7"
        assert field_values["Indexes"] == "8/9"
        assert "Issues" in field_values
        assert "track_genres" in field_values["Issues"]

    @pytest.mark.asyncio
    async def test_db_validate_pragma_failures(self, admin_cog, mock_admin_ctx, mock_container):
        """Should show failed pragmas."""
        mock_container.database.validate_schema = AsyncMock(
            return_value=SchemaValidationResult(
                tables=CountValidation(expected=7, found=7, missing=[]),
                columns=ColumnValidation(expected=47, found=47, missing={}),
                indexes=CountValidation(expected=9, found=9, missing=[]),
                pragmas=PragmaValidation(journal_mode="delete", foreign_keys=0),
                issues=[
                    "journal_mode is 'delete', expected 'wal'",
                    "foreign_keys is 0, expected 1",
                ],
            )
        )

        await admin_cog.db_validate.callback(admin_cog, mock_admin_ctx)

        call_kwargs = mock_admin_ctx.send.call_args.kwargs
        embed = call_kwargs["embed"]
        assert embed.color == discord.Color.orange()

        field_values = {f.name: f.value for f in embed.fields}
        assert "❌" in field_values["Pragmas"]

    @pytest.mark.asyncio
    async def test_db_validate_handles_exception(self, admin_cog, mock_admin_ctx, mock_container):
        """Should handle validation exceptions."""
        mock_container.database.validate_schema.side_effect = Exception("DB error")

        await admin_cog.db_validate.callback(admin_cog, mock_admin_ctx)

        call_args = mock_admin_ctx.send.call_args[0][0]
        assert "failed" in call_args.lower()


# =============================================================================
# System Info Command Tests
# =============================================================================


class TestSystemCommands:
    """Tests for system info and lifecycle commands."""

    @pytest.mark.asyncio
    async def test_status_success(self, admin_cog, mock_admin_ctx, mock_bot):
        """Should display bot status."""
        mock_admin_ctx.bot = mock_bot

        await admin_cog.status.callback(admin_cog, mock_admin_ctx)

        call_kwargs = mock_admin_ctx.send.call_args.kwargs
        assert "embed" in call_kwargs
        embed = call_kwargs["embed"]
        assert "Bot Status" in embed.title

        # Check fields
        field_names = [f.name for f in embed.fields]
        assert "Guilds" in field_names
        assert "Latency" in field_names
        assert "Voice Connections" in field_names
        assert "Extensions" in field_names
        assert "Cogs" in field_names
        assert "Environment" in field_names

    @pytest.mark.asyncio
    async def test_status_shows_correct_counts(self, admin_cog, mock_admin_ctx, mock_bot):
        """Should show correct counts."""
        mock_admin_ctx.bot = mock_bot

        await admin_cog.status.callback(admin_cog, mock_admin_ctx)

        call_kwargs = mock_admin_ctx.send.call_args.kwargs
        embed = call_kwargs["embed"]

        field_values = {f.name: f.value for f in embed.fields}
        assert field_values["Guilds"] == "5"
        assert "50" in field_values["Latency"]  # 50ms
        assert field_values["Voice Connections"] == "2"
        assert field_values["Cogs"] == "2"
        assert field_values["Environment"] == "testing"

    @pytest.mark.asyncio
    async def test_shutdown_success(self, admin_cog, mock_admin_ctx, mock_bot, mock_container):
        """Should shutdown bot gracefully."""
        mock_admin_ctx.bot = mock_bot

        await admin_cog.shutdown.callback(admin_cog, mock_admin_ctx)

        # Should send shutdown message
        call_args = mock_admin_ctx.send.call_args[0][0]
        assert "Shutting down" in call_args

        # Should call cleanup
        mock_container.cleanup_job.shutdown.assert_called_once()

        # Should close bot
        mock_bot.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_shutdown_handles_cleanup_exception(
        self, admin_cog, mock_admin_ctx, mock_bot, mock_container
    ):
        """Should continue shutdown even if cleanup fails."""
        mock_admin_ctx.bot = mock_bot
        mock_container.cleanup_job.shutdown.side_effect = Exception("Cleanup error")

        await admin_cog.shutdown.callback(admin_cog, mock_admin_ctx)

        # Should still close bot
        mock_bot.close.assert_called_once()


# =============================================================================
# Edge Cases and Error Handling Tests
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and error conditions."""

    @pytest.mark.asyncio
    async def test_command_without_permission(self, admin_cog, mock_ctx):
        """Should deny command without permission."""
        # The check decorator will raise CheckFailure, which is handled by error handler
        # We're testing that the error handler works correctly
        error = commands.CheckFailure()

        await admin_cog.cog_command_error(mock_ctx, error)

        call_args = mock_ctx.send.call_args[0][0]
        assert "owner or admin" in call_args.lower()

    @pytest.mark.asyncio
    async def test_sync_without_guild_context(self, admin_cog, mock_admin_ctx, mock_bot):
        """Should handle sync without guild for non-global scope."""
        mock_admin_ctx.guild = None
        mock_admin_ctx.bot.tree = mock_bot.tree

        await admin_cog.sync.callback(admin_cog, mock_admin_ctx, scope="guild")

        call_args = mock_admin_ctx.send.call_args[0][0]
        assert "server" in call_args.lower() or "global" in call_args.lower()

    @pytest.mark.asyncio
    async def test_reload_nonexistent_extension(self, admin_cog, mock_admin_ctx, mock_bot):
        """Should handle reload of nonexistent extension."""
        mock_admin_ctx.bot = mock_bot
        mock_bot.reload_extension = AsyncMock(
            side_effect=[commands.ExtensionNotLoaded("test"), commands.ExtensionNotFound("test")]
        )

        await admin_cog.reload.callback(admin_cog, mock_admin_ctx, "nonexistent")

        call_args = mock_admin_ctx.send.call_args[0][0]
        assert "Failed" in call_args

    @pytest.mark.asyncio
    async def test_cache_operations_with_disabled_ai(
        self, admin_cog, mock_admin_ctx, mock_container
    ):
        """Should handle cache operations when AI client unavailable."""
        mock_container.ai_client = None

        # Should raise AttributeError which is caught and handled
        await admin_cog.cache_status.callback(admin_cog, mock_admin_ctx)

        call_args = mock_admin_ctx.send.call_args[0][0]
        assert "failed" in call_args.lower()

    @pytest.mark.asyncio
    async def test_db_stats_with_empty_tables(self, admin_cog, mock_admin_ctx, mock_container):
        """Should handle database with no tables."""
        mock_container.database.get_stats = AsyncMock(
            return_value=DatabaseStats(
                initialized=True,
                file_size_mb=0.1,
                page_count=0,
                db_path="/tmp/empty.db",
            )
        )

        await admin_cog.db_stats.callback(admin_cog, mock_admin_ctx)

        call_kwargs = mock_admin_ctx.send.call_args.kwargs
        embed = call_kwargs["embed"]

        # Should still work with empty tables - field won't be added
        tables_fields = [f for f in embed.fields if f.name == "Tables"]
        assert len(tables_fields) == 0  # No tables field when empty

    @pytest.mark.asyncio
    async def test_db_cleanup_with_zero_results(self, admin_cog, mock_admin_ctx, mock_container):
        """Should handle cleanup with nothing to clean."""
        cleanup_stats = MagicMock()
        cleanup_stats.sessions_cleaned = 0
        cleanup_stats.votes_cleaned = 0
        cleanup_stats.cache_cleaned = 0
        cleanup_stats.history_cleaned = 0
        cleanup_stats.total_cleaned = 0

        mock_container.cleanup_job.run_cleanup = AsyncMock(return_value=cleanup_stats)

        await admin_cog.db_cleanup.callback(admin_cog, mock_admin_ctx)

        call_kwargs = mock_admin_ctx.send.call_args.kwargs
        embed = call_kwargs["embed"]

        # Should still show results
        field_values = {f.name: f.value for f in embed.fields}
        assert field_values["Total"] == "0"

    @pytest.mark.asyncio
    async def test_status_with_no_voice_connections(self, admin_cog, mock_admin_ctx, mock_bot):
        """Should handle status with no voice connections."""
        mock_admin_ctx.bot = mock_bot
        mock_bot.voice_clients = []

        await admin_cog.status.callback(admin_cog, mock_admin_ctx)

        call_kwargs = mock_admin_ctx.send.call_args.kwargs
        embed = call_kwargs["embed"]

        field_values = {f.name: f.value for f in embed.fields}
        assert field_values["Voice Connections"] == "0"

    @pytest.mark.asyncio
    async def test_slash_status_with_no_commands(self, admin_cog, mock_admin_ctx, mock_bot):
        """Should handle slash status with no commands."""
        mock_admin_ctx.bot.tree = mock_bot.tree
        mock_bot.tree.fetch_commands = AsyncMock(return_value=[])
        mock_bot.tree.get_commands = MagicMock(return_value=[])

        await admin_cog.slash_status.callback(admin_cog, mock_admin_ctx)

        call_kwargs = mock_admin_ctx.send.call_args.kwargs
        embed = call_kwargs["embed"]

        # Should show 0 commands
        global_count_field = next(f for f in embed.fields if f.name == "Global (Live)")
        assert global_count_field.value == "0"


# =============================================================================
# Integration Tests
# =============================================================================


class TestIntegration:
    """Integration tests for complex workflows."""

    @pytest.mark.asyncio
    async def test_full_admin_workflow(self, admin_cog, mock_admin_ctx, mock_bot, mock_container):
        """Should handle full admin workflow."""
        mock_admin_ctx.bot = mock_bot
        mock_admin_ctx.bot.tree = mock_bot.tree
        mock_bot.extensions = {"cog.music": MagicMock()}

        # Check status
        await admin_cog.status.callback(admin_cog, mock_admin_ctx)
        assert mock_admin_ctx.send.called

        # Sync commands
        await admin_cog.sync.callback(admin_cog, mock_admin_ctx, scope="guild")
        assert mock_bot.tree.sync.called

        # Check slash status
        await admin_cog.slash_status.callback(admin_cog, mock_admin_ctx)
        assert mock_bot.tree.fetch_commands.called

        # Check cache
        await admin_cog.cache_status.callback(admin_cog, mock_admin_ctx)
        assert mock_container.ai_client.get_cache_stats.called

        # Run cleanup
        await admin_cog.db_cleanup.callback(admin_cog, mock_admin_ctx)
        assert mock_container.cleanup_job.run_cleanup.called

        # Check db stats
        await admin_cog.db_stats.callback(admin_cog, mock_admin_ctx)
        assert mock_container.database.get_stats.called

        # Validate schema
        await admin_cog.db_validate.callback(admin_cog, mock_admin_ctx)
        assert mock_container.database.validate_schema.called

        # All should succeed
        assert mock_admin_ctx.send.call_count >= 7

    @pytest.mark.asyncio
    async def test_cache_management_workflow(self, admin_cog, mock_admin_ctx, mock_container):
        """Should handle cache management workflow."""
        # Check status
        await admin_cog.cache_status.callback(admin_cog, mock_admin_ctx)
        stats1 = mock_container.ai_client.get_cache_stats()
        assert stats1["size"] == 10

        # Prune old entries
        await admin_cog.cache_prune.callback(admin_cog, mock_admin_ctx, max_age_seconds=3600)
        assert mock_container.ai_client.prune_cache.called

        # Clear all
        await admin_cog.cache_clear.callback(admin_cog, mock_admin_ctx)
        assert mock_container.ai_client.clear_cache.called

        # All should succeed
        assert mock_admin_ctx.send.call_count == 3

    @pytest.mark.asyncio
    async def test_cog_reload_workflow(self, admin_cog, mock_admin_ctx, mock_bot):
        """Should handle cog reload workflow."""
        mock_admin_ctx.bot = mock_bot
        mock_bot.extensions = {
            "infrastructure.discord.cogs.music_cog": MagicMock(),
            "infrastructure.discord.cogs.admin_cog": MagicMock(),
        }

        # Reload single cog
        await admin_cog.reload.callback(admin_cog, mock_admin_ctx, "music_cog")
        assert mock_bot.reload_extension.called

        # Reload all cogs
        await admin_cog.reload_all.callback(admin_cog, mock_admin_ctx)
        assert mock_bot.reload_extension.call_count >= 2

        # All should succeed
        assert mock_admin_ctx.send.call_count == 2
