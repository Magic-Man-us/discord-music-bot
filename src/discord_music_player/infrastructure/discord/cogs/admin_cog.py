"""Prefix-only admin commands for syncing, cog management, cache, and diagnostics."""

from __future__ import annotations

from pathlib import Path

import discord
from discord.ext import commands

from ....domain.shared.constants import DiscordEmbedLimits, SQLPragmas, UIConstants
from ....domain.shared.enums import SyncScope
from .base_cog import BaseCog

_FAILED_RELOAD_LOG = "Failed to reload %s"


def _is_bot_owner(ctx: commands.Context) -> bool:
    """Check if the user is a configured bot owner or the application owner."""
    bot = ctx.bot
    app_info = bot.application
    if app_info and app_info.owner:
        if ctx.author.id == app_info.owner.id:
            return True

    container = bot.container
    if container:
        owner_ids = container.settings.discord.owner_ids
        if ctx.author.id in owner_ids:
            return True

    return False


def require_owner() -> commands.Check[commands.Context]:
    """Restrict to bot owners only. For sensitive operations like shutdown, db access, reloads."""

    async def _owner_predicate(ctx: commands.Context) -> bool:
        if not ctx.guild:
            return False
        return _is_bot_owner(ctx)

    return commands.check(_owner_predicate)


def require_owner_or_admin() -> commands.Check[commands.Context]:
    """Allow bot owners and guild admins. For lighter operations like sync, status, cache viewing."""

    async def _owner_or_admin_predicate(ctx: commands.Context) -> bool:
        if not ctx.guild:
            return False

        if _is_bot_owner(ctx):
            return True

        if isinstance(ctx.author, discord.Member):
            if ctx.author.guild_permissions.administrator:
                return True
            if ctx.author.guild_permissions.manage_guild:
                return True

        return False

    return commands.check(_owner_or_admin_predicate)


class AdminCog(BaseCog):
    async def _require_ai(self, ctx: commands.Context) -> bool:
        """Return True if AI is enabled, otherwise reply and return False."""
        if not self.container.ai_enabled:
            await self._reply(ctx, "AI features are disabled.")
            return False
        return True

    async def _reply(
        self,
        ctx: commands.Context,
        content: str | None = None,
        *,
        embed: discord.Embed | None = None,
    ) -> None:
        if embed:
            await ctx.send(content or "", embed=embed)
        else:
            await ctx.send(content or "Done.")

    async def cog_command_error(self, ctx: commands.Context, error: Exception) -> None:
        if isinstance(error, commands.CheckFailure):
            await self._reply(ctx, "Requires owner or admin permissions.")
            return

        if isinstance(error, commands.MissingRequiredArgument):
            await self._reply(ctx, f"Missing argument: {error.param.name}")
            return

        if isinstance(error, commands.BadArgument):
            await self._reply(ctx, "Invalid argument.")
            return

        original = error.original if isinstance(error, commands.CommandInvokeError) else error
        self.logger.exception("Admin command failed", exc_info=original)
        await self._reply(ctx, "Command failed. See logs.")

    # ─────────────────────────────────────────────────────────────────
    # Slash Command Sync
    # ─────────────────────────────────────────────────────────────────

    @commands.command(name="sync", description="Sync slash commands.")
    @require_owner_or_admin()
    async def sync(self, ctx: commands.Context, scope: str = "guild") -> None:
        try:
            scope_lower = scope.strip().lower()

            if scope_lower == SyncScope.GLOBAL:
                synced = await self.bot.tree.sync()
                await self._reply(ctx, f"Synced {len(synced)} slash commands globally.")
            else:
                if not ctx.guild:
                    await self._reply(ctx, "Run in a server or use `!sync global`.")
                    return

                synced = await self.bot.tree.sync(guild=ctx.guild)
                await self._reply(ctx, f"Synced {len(synced)} slash commands to this server.")
        except Exception:
            self.logger.exception("Failed to sync commands")
            await self._reply(ctx, "Failed to sync. See logs.")

    @commands.command(name="slash_status", description="Show slash command status.")
    @require_owner_or_admin()
    async def slash_status(self, ctx: commands.Context) -> None:
        try:
            global_cmds = await self.bot.tree.fetch_commands()
            guild_cmds = []

            if ctx.guild:
                guild_cmds = await self.bot.tree.fetch_commands(guild=ctx.guild)

            local_cmds = self.bot.tree.get_commands()

            def format_names(cmds: list[discord.app_commands.AppCommand]) -> str:
                names = [f"/{c.name}" for c in cmds]
                result = ", ".join(names) or "-"
                limit = DiscordEmbedLimits.SLASH_STATUS_TRUNCATION
                return result[:limit] + "..." if len(result) > limit else result

            embed = discord.Embed(title="Slash Command Status", color=discord.Color.blurple())
            embed.add_field(name="Global (Live)", value=str(len(global_cmds)), inline=True)
            if ctx.guild:
                embed.add_field(name="Guild (Live)", value=str(len(guild_cmds)), inline=True)
            embed.add_field(name="Local (Tree)", value=str(len(local_cmds)), inline=True)
            embed.add_field(name="Global Names", value=format_names(global_cmds), inline=False)
            if ctx.guild:
                embed.add_field(name="Guild Names", value=format_names(guild_cmds), inline=False)

            embed.set_footer(text="Global sync can take up to 1 hour. Guild sync is immediate.")

            await self._reply(ctx, embed=embed)
        except Exception:
            self.logger.exception("Failed to fetch slash status")
            await self._reply(ctx, "Failed to fetch status. See logs.")

    # ─────────────────────────────────────────────────────────────────
    # Cog Management
    # ─────────────────────────────────────────────────────────────────

    @commands.command(name="reload", description="Reload a cog.")
    @require_owner()
    async def reload(self, ctx: commands.Context, extension: str) -> None:
        if extension.startswith("discord_music_player."):
            mod = extension
        elif extension.startswith("cog."):
            mod = extension
        else:
            mod = f"discord_music_player.infrastructure.discord.cogs.{extension}"

        try:
            await self.bot.reload_extension(mod)
            await self._reply(ctx, f"Reloaded `{mod}`")
        except commands.ExtensionNotLoaded:
            old_mod = f"cog.{extension}"
            try:
                await self.bot.reload_extension(old_mod)
                await self._reply(ctx, f"Reloaded `{old_mod}`")
            except Exception:
                self.logger.exception(_FAILED_RELOAD_LOG, extension)
                await self._reply(ctx, f"Failed to reload `{extension}`")
        except Exception:
            self.logger.exception(_FAILED_RELOAD_LOG, mod)
            await self._reply(ctx, f"Failed to reload `{mod}`")

    @commands.command(name="load", description="Load a cog (extension) at runtime.")
    @require_owner()
    async def load(self, ctx: commands.Context, extension: str) -> None:
        if extension.startswith("discord_music_player."):
            mod = extension
        else:
            mod = f"discord_music_player.infrastructure.discord.cogs.{extension}"

        try:
            await self.bot.load_extension(mod)
            await self._reply(ctx, f"Loaded `{mod}`")
        except commands.ExtensionAlreadyLoaded:
            await self._reply(ctx, f"`{mod}` is already loaded — use `!reload` instead.")
        except Exception:
            self.logger.exception("Failed to load %s", mod)
            await self._reply(ctx, f"Failed to load `{mod}` (see logs).")

    @commands.command(name="unload", description="Unload a cog (extension) at runtime.")
    @require_owner()
    async def unload(self, ctx: commands.Context, extension: str) -> None:
        if extension.startswith("discord_music_player."):
            mod = extension
        else:
            mod = f"discord_music_player.infrastructure.discord.cogs.{extension}"

        try:
            await self.bot.unload_extension(mod)
            await self._reply(ctx, f"Unloaded `{mod}`")
        except commands.ExtensionNotLoaded:
            await self._reply(ctx, f"`{mod}` is not loaded.")
        except Exception:
            self.logger.exception("Failed to unload %s", mod)
            await self._reply(ctx, f"Failed to unload `{mod}` (see logs).")

    @commands.command(name="reload_all", description="Reload all cogs.")
    @require_owner()
    async def reload_all(self, ctx: commands.Context) -> None:
        extensions = list(self.bot.extensions.keys())

        if not extensions:
            await self._reply(ctx, "No extensions loaded.")
            return

        ok, failed = 0, 0
        for mod in extensions:
            try:
                await self.bot.reload_extension(mod)
                ok += 1
            except Exception:
                failed += 1
                self.logger.exception(_FAILED_RELOAD_LOG, mod)

        await self._reply(ctx, f"Reloaded {ok} extensions, {failed} failed.")

    # ─────────────────────────────────────────────────────────────────
    # Cache Management
    # ─────────────────────────────────────────────────────────────────

    @commands.command(name="cache_status", description="Show cache statistics.")
    @require_owner_or_admin()
    async def cache_status(self, ctx: commands.Context) -> None:
        if not await self._require_ai(ctx):
            return

        try:
            ai_client = self.container.ai_client
            stats = ai_client.get_cache_stats()

            embed = discord.Embed(title="Cache Statistics", color=discord.Color.blue())
            embed.add_field(name="Size", value=str(stats.size), inline=True)
            embed.add_field(name="Hits", value=str(stats.hits), inline=True)
            embed.add_field(name="Misses", value=str(stats.misses), inline=True)
            embed.add_field(name="Hit Rate", value=f"{stats.hit_rate}%", inline=True)
            embed.add_field(name="In-Flight", value=str(stats.inflight), inline=True)

            await self._reply(ctx, embed=embed)
        except Exception:
            self.logger.exception("Failed to get cache status")
            await self._reply(ctx, "Failed to get cache status.")

    @commands.command(name="ai_usage", description="Show AI token usage statistics.")
    @require_owner_or_admin()
    async def ai_usage(self, ctx: commands.Context) -> None:
        if not await self._require_ai(ctx):
            return

        try:
            stats = self.container.ai_client.get_cache_stats()
            usage = stats.usage

            embed = discord.Embed(title="AI Token Usage", color=discord.Color.purple())
            embed.add_field(name="Input Tokens", value=f"{usage.total_input_tokens:,}", inline=True)
            embed.add_field(
                name="Output Tokens", value=f"{usage.total_output_tokens:,}", inline=True
            )
            embed.add_field(name="Total Tokens", value=f"{usage.total_tokens:,}", inline=True)
            embed.add_field(name="API Calls", value=str(usage.total_calls), inline=True)
            embed.add_field(name="API Requests", value=str(usage.total_requests), inline=True)
            embed.add_field(name="Cache Hit Rate", value=f"{stats.hit_rate}%", inline=True)

            await self._reply(ctx, embed=embed)
        except Exception:
            self.logger.exception("Failed to get AI usage stats")
            await self._reply(ctx, "Failed to get AI usage stats.")

    @commands.command(name="cache_clear", description="Clear the AI cache.")
    @require_owner()
    async def cache_clear(self, ctx: commands.Context) -> None:
        if not await self._require_ai(ctx):
            return

        try:
            ai_client = self.container.ai_client
            cleared = ai_client.clear_cache()
            await self._reply(ctx, f"Cleared {cleared} cache entries.")
        except Exception:
            self.logger.exception("Failed to clear cache")
            await self._reply(ctx, "Failed to clear cache.")

    @commands.command(name="cache_prune", description="Prune old cache entries.")
    @require_owner()
    async def cache_prune(self, ctx: commands.Context, max_age_seconds: int = 3600) -> None:
        if not await self._require_ai(ctx):
            return

        try:
            ai_client = self.container.ai_client
            pruned = ai_client.prune_cache(max_age_seconds)
            await self._reply(ctx, f"Pruned {pruned} expired cache entries.")
        except Exception:
            self.logger.exception("Failed to prune cache")
            await self._reply(ctx, "Failed to prune cache.")

    # ─────────────────────────────────────────────────────────────────
    # Database & Cleanup
    # ─────────────────────────────────────────────────────────────────

    @commands.command(name="db_cleanup", description="Run database cleanup.")
    @require_owner()
    async def db_cleanup(self, ctx: commands.Context) -> None:
        try:
            cleanup_job = self.container.cleanup_job
            stats = await cleanup_job.run_cleanup()

            embed = discord.Embed(title="Cleanup Results", color=discord.Color.green())
            embed.add_field(name="Sessions", value=str(stats.sessions_cleaned), inline=True)
            embed.add_field(name="Votes", value=str(stats.votes_cleaned), inline=True)
            embed.add_field(name="Cache", value=str(stats.cache_cleaned), inline=True)
            embed.add_field(name="History", value=str(stats.history_cleaned), inline=True)
            embed.add_field(name="Total", value=str(stats.total_cleaned), inline=True)

            await self._reply(ctx, embed=embed)
        except Exception:
            self.logger.exception("Failed to run cleanup")
            await self._reply(ctx, "Failed to run cleanup.")

    @commands.command(name="db_stats", description="Show database statistics.")
    @require_owner()
    async def db_stats(self, ctx: commands.Context) -> None:
        try:
            db = self.container.database
            stats = await db.get_stats()

            embed = discord.Embed(title="Database Statistics", color=discord.Color.gold())
            embed.add_field(
                name="Initialized", value="Yes" if stats.initialized else "No", inline=True
            )
            embed.add_field(name="File Size", value=f"{stats.file_size_mb or 0} MB", inline=True)
            embed.add_field(name="Page Count", value=str(stats.page_count or 0), inline=True)

            db_name = Path(stats.db_path).name if stats.db_path else "Unknown"
            embed.add_field(name="Database", value=db_name, inline=True)

            if stats.tables:
                table_info = "\n".join(
                    f"{name}: {count} rows" for name, count in stats.tables.items()
                )
                embed.add_field(name="Tables", value=table_info or "No tables", inline=False)

            await self._reply(ctx, embed=embed)
        except Exception:
            self.logger.exception("Failed to get db stats")
            await self._reply(ctx, "Failed to get database stats.")

    @commands.command(name="db_validate", description="Validate database schema.")
    @require_owner()
    async def db_validate(self, ctx: commands.Context) -> None:
        try:
            db = self.container.database
            result = await db.validate_schema()

            issues = result.issues
            color = discord.Color.green() if not issues else discord.Color.orange()

            embed = discord.Embed(title="Database Validation", color=color)

            embed.add_field(
                name="Tables",
                value=f"{result.tables.found}/{result.tables.expected}",
                inline=True,
            )

            embed.add_field(
                name="Columns",
                value=f"{result.columns.found}/{result.columns.expected}",
                inline=True,
            )

            embed.add_field(
                name="Indexes",
                value=f"{result.indexes.found}/{result.indexes.expected}",
                inline=True,
            )

            wal_ok = result.pragmas.journal_mode == SQLPragmas.EXPECTED_JOURNAL_MODE
            fk_ok = result.pragmas.foreign_keys == 1
            pragma_text = f"WAL: {'Yes' if wal_ok else 'No'}  FK: {'Yes' if fk_ok else 'No'}"
            embed.add_field(name="Pragmas", value=pragma_text, inline=True)

            if issues:
                embed.add_field(
                    name="Issues",
                    value="\n".join(f"- {i}" for i in issues)[
                        : DiscordEmbedLimits.EMBED_FIELD_VALUE_MAX
                    ],
                    inline=False,
                )

            await self._reply(ctx, embed=embed)
        except Exception:
            self.logger.exception("Failed to validate database schema")
            await self._reply(ctx, "Failed to validate database.")

    # ─────────────────────────────────────────────────────────────────
    # System Info
    # ─────────────────────────────────────────────────────────────────

    @commands.command(name="status", description="Show bot status.")
    @require_owner_or_admin()
    async def status(self, ctx: commands.Context) -> None:
        embed = discord.Embed(title="Bot Status", color=discord.Color.green())
        embed.add_field(name="Guilds", value=str(len(self.bot.guilds)), inline=True)
        embed.add_field(
            name="Latency",
            value=f"{self.bot.latency * UIConstants.MS_PER_SECOND:.0f}ms",
            inline=True,
        )

        embed.add_field(
            name="Voice Connections", value=str(len(self.bot.voice_clients)), inline=True
        )
        embed.add_field(name="Extensions", value=str(len(self.bot.extensions)), inline=True)
        embed.add_field(name="Cogs", value=str(len(self.bot.cogs)), inline=True)

        settings = self.container.settings
        embed.add_field(name="Environment", value=settings.environment, inline=True)

        await self._reply(ctx, embed=embed)

    @commands.command(name="shutdown", description="Gracefully shutdown the bot.")
    @require_owner()
    async def shutdown(self, ctx: commands.Context) -> None:
        await self._reply(ctx, "Shutting down...")

        try:
            cleanup_job = self.container.cleanup_job
            await cleanup_job.stop()
        except Exception:
            pass

        await self.bot.close()


setup = AdminCog.setup
