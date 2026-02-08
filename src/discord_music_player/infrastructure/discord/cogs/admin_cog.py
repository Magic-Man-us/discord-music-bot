"""Prefix-only admin commands for syncing, cog management, cache, and diagnostics."""

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


def _is_bot_owner(ctx: commands.Context) -> bool:
    """Check if the user is a configured bot owner or the application owner."""
    app_info = ctx.bot.application
    if app_info and app_info.owner:
        if ctx.author.id == app_info.owner.id:
            return True

    container = getattr(ctx.bot, "container", None)
    if container:
        owner_ids = container.settings.discord.owner_ids
        if ctx.author.id in owner_ids:
            return True

    return False


def require_owner():
    """Restrict to bot owners only. For sensitive operations like shutdown, db access, reloads."""

    async def predicate(ctx: commands.Context) -> bool:
        if not ctx.guild:
            return False
        return _is_bot_owner(ctx)

    return commands.check(predicate)


def require_owner_or_admin():
    """Allow bot owners and guild admins. For lighter operations like sync, status, cache viewing."""

    async def predicate(ctx: commands.Context) -> bool:
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

    return commands.check(predicate)


class AdminCog(commands.Cog):
    def __init__(self, bot: commands.Bot, container: Container) -> None:
        self.bot = bot
        self.container = container

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
            await ctx.send(content or DiscordUIMessages.SUCCESS_GENERIC)

    async def cog_command_error(self, ctx: commands.Context, error: Exception) -> None:
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

        original = getattr(error, "original", error)
        logger.exception(LogTemplates.ADMIN_COMMAND_FAILED, exc_info=original)
        await self._reply(ctx, DiscordUIMessages.ERROR_COMMAND_FAILED_SEE_LOGS)

    # ─────────────────────────────────────────────────────────────────
    # Slash Command Sync
    # ─────────────────────────────────────────────────────────────────

    @commands.command(name="sync", description="Sync slash commands.")
    @require_owner_or_admin()
    async def sync(self, ctx: commands.Context, scope: str = "guild") -> None:
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
            await self._reply(ctx, DiscordUIMessages.SUCCESS_RELOADED_EXTENSION.format(module=mod))
        except commands.ExtensionNotLoaded:
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
    @require_owner()
    async def reload_all(self, ctx: commands.Context) -> None:
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
    @require_owner()
    async def cache_clear(self, ctx: commands.Context) -> None:
        try:
            ai_client = self.container.ai_client
            cleared = ai_client.clear_cache()
            await self._reply(ctx, DiscordUIMessages.SUCCESS_CACHE_CLEARED.format(cleared=cleared))
        except Exception:
            logger.exception(LogTemplates.ADMIN_CACHE_CLEAR_FAILED)
            await self._reply(ctx, DiscordUIMessages.ERROR_CACHE_CLEAR_FAILED)

    @commands.command(name="cache_prune", description="Prune old cache entries.")
    @require_owner()
    async def cache_prune(self, ctx: commands.Context, max_age_seconds: int = 3600) -> None:
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
    @require_owner()
    async def db_cleanup(self, ctx: commands.Context) -> None:
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
    @require_owner()
    async def db_stats(self, ctx: commands.Context) -> None:
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
            from pathlib import Path

            db_path = stats.get("db_path", "Unknown")
            db_name = Path(db_path).name if db_path != "Unknown" else "Unknown"
            embed.add_field(name="Database", value=db_name, inline=True)

            tables = stats.get("tables", {})
            if tables:
                table_info = "\n".join(f"{name}: {count} rows" for name, count in tables.items())
                embed.add_field(name="Tables", value=table_info or "No tables", inline=False)

            await self._reply(ctx, embed=embed)
        except Exception:
            logger.exception(LogTemplates.ADMIN_DB_STATS_FAILED)
            await self._reply(ctx, DiscordUIMessages.ERROR_DB_STATS_FAILED)

    @commands.command(name="db_validate", description="Validate database schema.")
    @require_owner()
    async def db_validate(self, ctx: commands.Context) -> None:
        try:
            db = self.container.database
            result = await db.validate_schema()

            issues = result.get("issues", [])
            color = discord.Color.green() if not issues else discord.Color.orange()

            embed = discord.Embed(
                title=DiscordUIMessages.EMBED_DATABASE_VALIDATION, color=color
            )

            tables = result["tables"]
            embed.add_field(
                name="Tables",
                value=f"{tables['found']}/{tables['expected']}",
                inline=True,
            )

            columns = result["columns"]
            embed.add_field(
                name="Columns",
                value=f"{columns['found']}/{columns['expected']}",
                inline=True,
            )

            indexes = result["indexes"]
            embed.add_field(
                name="Indexes",
                value=f"{indexes['found']}/{indexes['expected']}",
                inline=True,
            )

            pragmas = result["pragmas"]
            wal_ok = pragmas["journal_mode"] == "wal"
            fk_ok = pragmas["foreign_keys"] == 1
            pragma_text = f"WAL: {'✅' if wal_ok else '❌'}  FK: {'✅' if fk_ok else '❌'}"
            embed.add_field(name="Pragmas", value=pragma_text, inline=True)

            if issues:
                embed.add_field(
                    name="Issues",
                    value="\n".join(f"• {i}" for i in issues)[:1024],
                    inline=False,
                )

            await self._reply(ctx, embed=embed)
        except Exception:
            logger.exception(LogTemplates.ADMIN_DB_VALIDATE_FAILED)
            await self._reply(ctx, DiscordUIMessages.ERROR_DB_VALIDATE_FAILED)

    # ─────────────────────────────────────────────────────────────────
    # System Info
    # ─────────────────────────────────────────────────────────────────

    @commands.command(name="status", description="Show bot status.")
    @require_owner_or_admin()
    async def status(self, ctx: commands.Context) -> None:
        embed = discord.Embed(title=DiscordUIMessages.EMBED_BOT_STATUS, color=discord.Color.green())
        embed.add_field(name="Guilds", value=str(len(self.bot.guilds)), inline=True)
        embed.add_field(name="Latency", value=f"{self.bot.latency * 1000:.0f}ms", inline=True)

        embed.add_field(name="Voice Connections", value=str(len(self.bot.voice_clients)), inline=True)
        embed.add_field(name="Extensions", value=str(len(self.bot.extensions)), inline=True)
        embed.add_field(name="Cogs", value=str(len(self.bot.cogs)), inline=True)

        settings = self.container.settings
        embed.add_field(name="Environment", value=settings.environment, inline=True)

        await self._reply(ctx, embed=embed)

    @commands.command(name="shutdown", description="Gracefully shutdown the bot.")
    @require_owner()
    async def shutdown(self, ctx: commands.Context) -> None:
        await self._reply(ctx, DiscordUIMessages.SUCCESS_SHUTTING_DOWN)

        try:
            cleanup_job = self.container.cleanup_job
            await cleanup_job.shutdown()
        except Exception:
            pass

        await self.bot.close()


async def setup(bot: commands.Bot) -> None:
    container = getattr(bot, "container", None)
    if container is None:
        raise RuntimeError(ErrorMessages.CONTAINER_NOT_FOUND)

    await bot.add_cog(AdminCog(bot, container))
