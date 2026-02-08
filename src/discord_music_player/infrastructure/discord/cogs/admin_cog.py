"""
Admin Cog

Prefix-only admin commands for bot management.
These commands are restricted to bot owners and admins.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

from discord_music_player.domain.shared.messages import (
    DiscordUIMessages,
    ErrorMessages,
    LogTemplates,
)

if TYPE_CHECKING:
    from ....config.container import Container

logger = logging.getLogger(__name__)


def require_owner_or_admin():
    """Check decorator that requires owner or admin permissions."""

    async def predicate(ctx: commands.Context) -> bool:
        if not ctx.guild:
            return False

        # Check if bot owner
        app_info = ctx.bot.application
        if app_info and app_info.owner:
            if ctx.author.id == app_info.owner.id:
                return True

        # Check container settings for owner IDs
        container = getattr(ctx.bot, "container", None)
        if container:
            owner_ids = container.settings.discord.owner_ids
            if ctx.author.id in owner_ids:
                return True

        # Check server admin
        if isinstance(ctx.author, discord.Member):
            if ctx.author.guild_permissions.administrator:
                return True
            if ctx.author.guild_permissions.manage_guild:
                return True

        return False

    return commands.check(predicate)


class AdminCog(commands.Cog):
    """Prefix-only admin commands for bot management.

    These commands handle slash command syncing, cog reloading,
    cache management, and system diagnostics.
    """

    def __init__(self, bot: commands.Bot, container: Container) -> None:
        """Initialize the admin cog.

        Args:
            bot: The Discord bot instance.
            container: The DI container.
        """
        self.bot = bot
        self.container = container

    async def _reply(
        self,
        ctx: commands.Context,
        content: str | None = None,
        *,
        embed: discord.Embed | None = None,
    ) -> None:
        """Reply in the invoking channel."""
        if embed:
            await ctx.send(content or "", embed=embed)
        else:
            await ctx.send(content or DiscordUIMessages.SUCCESS_GENERIC)

    async def cog_command_error(self, ctx: commands.Context, error: Exception) -> None:
        """Handle errors from admin commands."""
        if isinstance(error, commands.CheckFailure):
            await self._reply(ctx, DiscordUIMessages.ERROR_REQUIRES_OWNER_OR_ADMIN)
            return

        if isinstance(error, commands.MissingRequiredArgument):
            await self._reply(
                ctx, DiscordUIMessages.ERROR_MISSING_ARGUMENT.format(param_name=error.param.name)
            )
            return

        if isinstance(error, commands.BadArgument):
            await self._reply(ctx, DiscordUIMessages.ERROR_INVALID_ARGUMENT)
            return

        # Log and report
        original = getattr(error, "original", error)
        logger.exception(LogTemplates.ADMIN_COMMAND_FAILED, exc_info=original)
        await self._reply(ctx, DiscordUIMessages.ERROR_COMMAND_FAILED_SEE_LOGS)

    # ─────────────────────────────────────────────────────────────────
    # Slash Command Sync
    # ─────────────────────────────────────────────────────────────────

    @commands.command(name="sync", description="Sync slash commands.")
    @require_owner_or_admin()
    async def sync(self, ctx: commands.Context, scope: str = "guild") -> None:
        """Sync slash commands to Discord.

        Args:
            ctx: Command context.
            scope: "guild" for current server, "global" for all servers.
        """
        try:
            scope_lower = scope.strip().lower()

            if scope_lower == "global":
                synced = await self.bot.tree.sync()
                await self._reply(
                    ctx, DiscordUIMessages.SUCCESS_SYNCED_GLOBAL.format(count=len(synced))
                )
            else:
                if not ctx.guild:
                    await self._reply(ctx, DiscordUIMessages.ERROR_RUN_IN_SERVER_OR_SYNC_GLOBAL)
                    return

                synced = await self.bot.tree.sync(guild=ctx.guild)
                await self._reply(
                    ctx, DiscordUIMessages.SUCCESS_SYNCED_GUILD.format(count=len(synced))
                )
        except Exception:
            logger.exception(LogTemplates.ADMIN_SYNC_COMMANDS_FAILED)
            await self._reply(ctx, DiscordUIMessages.ERROR_SYNC_FAILED_SEE_LOGS)

    @commands.command(name="slash_status", description="Show slash command status.")
    @require_owner_or_admin()
    async def slash_status(self, ctx: commands.Context) -> None:
        """Display registered slash commands."""
        try:
            global_cmds = await self.bot.tree.fetch_commands()
            guild_cmds = []

            if ctx.guild:
                guild_cmds = await self.bot.tree.fetch_commands(guild=ctx.guild)

            local_cmds = self.bot.tree.get_commands()

            def format_names(cmds: list) -> str:
                names = [f"/{c.name}" for c in cmds]
                result = ", ".join(names) or "-"
                return result[:500] + "…" if len(result) > 500 else result

            embed = discord.Embed(
                title=DiscordUIMessages.EMBED_SLASH_COMMAND_STATUS, color=discord.Color.blurple()
            )
            embed.add_field(name="Global (Live)", value=str(len(global_cmds)), inline=True)
            if ctx.guild:
                embed.add_field(name="Guild (Live)", value=str(len(guild_cmds)), inline=True)
            embed.add_field(name="Local (Tree)", value=str(len(local_cmds)), inline=True)
            embed.add_field(name="Global Names", value=format_names(global_cmds), inline=False)
            if ctx.guild:
                embed.add_field(name="Guild Names", value=format_names(guild_cmds), inline=False)

            embed.set_footer(text=DiscordUIMessages.EMBED_SLASH_STATUS_FOOTER)

            await self._reply(ctx, embed=embed)
        except Exception:
            logger.exception(LogTemplates.ADMIN_FETCH_SLASH_STATUS_FAILED)
            await self._reply(ctx, DiscordUIMessages.ERROR_FETCH_STATUS_FAILED)

    # ─────────────────────────────────────────────────────────────────
    # Cog Management
    # ─────────────────────────────────────────────────────────────────

    @commands.command(name="reload", description="Reload a cog.")
    @require_owner_or_admin()
    async def reload(self, ctx: commands.Context, extension: str) -> None:
        """Reload a single extension/cog.

        Args:
            ctx: Command context.
            extension: Cog name (e.g., "music_cog" or "cog.music_cog").
        """
        # Handle both new and old module paths
        if extension.startswith("discord_music_player."):
            # Full path provided
            mod = extension
        elif extension.startswith("cog."):
            # Legacy path format
            mod = extension
        else:
            # Short name - construct full path
            mod = f"discord_music_player.infrastructure.discord.cogs.{extension}"

        try:
            await self.bot.reload_extension(mod)
            await self._reply(ctx, DiscordUIMessages.SUCCESS_RELOADED_EXTENSION.format(module=mod))
        except commands.ExtensionNotLoaded:
            # Try old path
            old_mod = f"cog.{extension}"
            try:
                await self.bot.reload_extension(old_mod)
                await self._reply(
                    ctx, DiscordUIMessages.SUCCESS_RELOADED_EXTENSION.format(module=old_mod)
                )
            except Exception:
                logger.exception(LogTemplates.ADMIN_RELOAD_FAILED, extension)
                await self._reply(
                    ctx, DiscordUIMessages.ERROR_RELOAD_FAILED.format(extension=extension)
                )
        except Exception:
            logger.exception(LogTemplates.ADMIN_RELOAD_FAILED, mod)
            await self._reply(ctx, DiscordUIMessages.ERROR_RELOAD_FAILED.format(extension=mod))

    @commands.command(name="reload_all", description="Reload all cogs.")
    @require_owner_or_admin()
    async def reload_all(self, ctx: commands.Context) -> None:
        """Reload all loaded extensions."""
        extensions = list(self.bot.extensions.keys())

        if not extensions:
            await self._reply(ctx, DiscordUIMessages.ERROR_NO_EXTENSIONS_LOADED)
            return

        ok, failed = 0, 0
        for mod in extensions:
            try:
                await self.bot.reload_extension(mod)
                ok += 1
            except Exception:
                failed += 1
                logger.exception(LogTemplates.ADMIN_RELOAD_FAILED, mod)

        await self._reply(
            ctx, DiscordUIMessages.SUCCESS_RELOADED_EXTENSIONS.format(ok=ok, failed=failed)
        )

    # ─────────────────────────────────────────────────────────────────
    # Cache Management
    # ─────────────────────────────────────────────────────────────────

    @commands.command(name="cache_status", description="Show cache statistics.")
    @require_owner_or_admin()
    async def cache_status(self, ctx: commands.Context) -> None:
        """Show AI recommendation cache statistics."""
        try:
            ai_client = self.container.ai_client
            stats = ai_client.get_cache_stats()

            embed = discord.Embed(
                title=DiscordUIMessages.EMBED_CACHE_STATISTICS, color=discord.Color.blue()
            )
            embed.add_field(name="Size", value=str(stats.get("size", 0)), inline=True)
            embed.add_field(name="Hits", value=str(stats.get("hits", 0)), inline=True)
            embed.add_field(name="Misses", value=str(stats.get("misses", 0)), inline=True)
            embed.add_field(name="Hit Rate", value=f"{stats.get('hit_rate', 0)}%", inline=True)
            embed.add_field(name="In-Flight", value=str(stats.get("inflight", 0)), inline=True)

            await self._reply(ctx, embed=embed)
        except Exception:
            logger.exception(LogTemplates.ADMIN_CACHE_STATUS_FAILED)
            await self._reply(ctx, DiscordUIMessages.ERROR_CACHE_STATUS_FAILED)

    @commands.command(name="cache_clear", description="Clear the AI cache.")
    @require_owner_or_admin()
    async def cache_clear(self, ctx: commands.Context) -> None:
        """Clear the AI recommendation cache."""
        try:
            ai_client = self.container.ai_client
            cleared = ai_client.clear_cache()
            await self._reply(ctx, DiscordUIMessages.SUCCESS_CACHE_CLEARED.format(cleared=cleared))
        except Exception:
            logger.exception(LogTemplates.ADMIN_CACHE_CLEAR_FAILED)
            await self._reply(ctx, DiscordUIMessages.ERROR_CACHE_CLEAR_FAILED)

    @commands.command(name="cache_prune", description="Prune old cache entries.")
    @require_owner_or_admin()
    async def cache_prune(self, ctx: commands.Context, max_age_seconds: int = 3600) -> None:
        """Prune old cache entries.

        Args:
            ctx: Command context.
            max_age_seconds: Maximum age of entries to keep.
        """
        try:
            ai_client = self.container.ai_client
            pruned = ai_client.prune_cache(max_age_seconds)
            await self._reply(ctx, DiscordUIMessages.SUCCESS_CACHE_PRUNED.format(pruned=pruned))
        except Exception:
            logger.exception(LogTemplates.ADMIN_CACHE_PRUNE_FAILED)
            await self._reply(ctx, DiscordUIMessages.ERROR_CACHE_PRUNE_FAILED)

    # ─────────────────────────────────────────────────────────────────
    # Database & Cleanup
    # ─────────────────────────────────────────────────────────────────

    @commands.command(name="db_cleanup", description="Run database cleanup.")
    @require_owner_or_admin()
    async def db_cleanup(self, ctx: commands.Context) -> None:
        """Manually trigger database cleanup job."""
        try:
            cleanup_job = self.container.cleanup_job
            stats = await cleanup_job.run_cleanup()

            embed = discord.Embed(
                title=DiscordUIMessages.EMBED_CLEANUP_RESULTS, color=discord.Color.green()
            )
            embed.add_field(name="Sessions", value=str(stats.sessions_cleaned), inline=True)
            embed.add_field(name="Votes", value=str(stats.votes_cleaned), inline=True)
            embed.add_field(name="Cache", value=str(stats.cache_cleaned), inline=True)
            embed.add_field(name="History", value=str(stats.history_cleaned), inline=True)
            embed.add_field(name="Total", value=str(stats.total_cleaned), inline=True)

            await self._reply(ctx, embed=embed)
        except Exception:
            logger.exception(LogTemplates.ADMIN_CLEANUP_FAILED)
            await self._reply(ctx, DiscordUIMessages.ERROR_CLEANUP_FAILED)

    @commands.command(name="db_stats", description="Show database statistics.")
    @require_owner_or_admin()
    async def db_stats(self, ctx: commands.Context) -> None:
        """Show database connection statistics."""
        try:
            db = self.container.database
            stats = await db.get_stats()

            embed = discord.Embed(
                title=DiscordUIMessages.EMBED_DATABASE_STATISTICS, color=discord.Color.gold()
            )
            embed.add_field(
                name="Initialized", value="✅" if stats.get("initialized") else "❌", inline=True
            )
            embed.add_field(
                name="File Size", value=f"{stats.get('file_size_mb', 0)} MB", inline=True
            )
            embed.add_field(name="Page Count", value=str(stats.get("page_count", 0)), inline=True)
            embed.add_field(
                name="Database Path", value=str(stats.get("db_path", "Unknown")), inline=False
            )

            # Table stats
            tables = stats.get("tables", {})
            if tables:
                table_info = "\n".join(f"{name}: {count} rows" for name, count in tables.items())
                embed.add_field(name="Tables", value=table_info or "No tables", inline=False)

            await self._reply(ctx, embed=embed)
        except Exception:
            logger.exception(LogTemplates.ADMIN_DB_STATS_FAILED)
            await self._reply(ctx, DiscordUIMessages.ERROR_DB_STATS_FAILED)

    # ─────────────────────────────────────────────────────────────────
    # System Info
    # ─────────────────────────────────────────────────────────────────

    @commands.command(name="status", description="Show bot status.")
    @require_owner_or_admin()
    async def status(self, ctx: commands.Context) -> None:
        """Show overall bot status and statistics."""
        embed = discord.Embed(title=DiscordUIMessages.EMBED_BOT_STATUS, color=discord.Color.green())

        # Basic stats
        embed.add_field(name="Guilds", value=str(len(self.bot.guilds)), inline=True)
        embed.add_field(name="Latency", value=f"{self.bot.latency * 1000:.0f}ms", inline=True)

        # Voice connections
        voice_connections = len(self.bot.voice_clients)
        embed.add_field(name="Voice Connections", value=str(voice_connections), inline=True)

        # Extensions
        embed.add_field(name="Extensions", value=str(len(self.bot.extensions)), inline=True)

        # Cogs
        embed.add_field(name="Cogs", value=str(len(self.bot.cogs)), inline=True)

        # Settings info
        settings = self.container.settings
        embed.add_field(name="Environment", value=settings.environment, inline=True)

        await self._reply(ctx, embed=embed)

    @commands.command(name="shutdown", description="Gracefully shutdown the bot.")
    @require_owner_or_admin()
    async def shutdown(self, ctx: commands.Context) -> None:
        """Gracefully shutdown the bot."""
        await self._reply(ctx, DiscordUIMessages.SUCCESS_SHUTTING_DOWN)

        # Cleanup
        try:
            cleanup_job = self.container.cleanup_job
            await cleanup_job.shutdown()
        except Exception:
            pass

        await self.bot.close()


async def setup(bot: commands.Bot) -> None:
    """Set up the admin cog.

    Args:
        bot: The Discord bot instance.
    """
    container = getattr(bot, "container", None)
    if container is None:
        raise RuntimeError(ErrorMessages.CONTAINER_NOT_FOUND)

    await bot.add_cog(AdminCog(bot, container))
