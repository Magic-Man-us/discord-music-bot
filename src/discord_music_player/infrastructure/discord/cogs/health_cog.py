"""
Health Cog

Provides health monitoring and heartbeat functionality using
the DI container
"""

from __future__ import annotations

import json
import logging
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, TypedDict

import discord
from discord.ext import commands, tasks

from discord_music_player.domain.shared.datetime_utils import UtcDateTime
from discord_music_player.domain.shared.messages import (
    DiscordUIMessages,
    ErrorMessages,
    LogTemplates,
)

if TYPE_CHECKING:
    from ....config.container import Container

logger = logging.getLogger(__name__)


# Configuration constants (can be overridden via settings)
DEFAULT_FAST_INTERVAL = 180  # seconds
DEFAULT_DETAILED_INTERVAL = 300  # seconds
LATENCY_OK_MS = 200
LATENCY_WARN_MS = 800
LATENCY_RESET_FACTOR = 0.6
ONE_THOUSAND = 1000.0


class BasicStats(TypedDict):
    """Basic health statistics."""

    ts: str
    uptime_s: int
    uptime_human: str
    latency_ms: float
    latency_human: str
    queue_len: int
    current: str | None
    connected: bool
    status: Literal["online", "offline"]


class DetailedStats(BasicStats, total=False):
    """Extended health statistics."""

    guild_count: int
    voice_connections: int
    rss_mb: float
    vms_mb: float | None
    db_initialized: bool
    db_size_mb: float


class HealthCog(commands.Cog):
    """Health monitoring cog with heartbeat loops.

    Provides:
    - Fast heartbeat loop for basic monitoring
    - Detailed heartbeat loop for extended metrics
    - /ping command for latency check
    - /health command for full status
    """

    def __init__(self, bot: commands.Bot, container: Container) -> None:
        """Initialize the health cog.

        Args:
            bot: The Discord bot instance.
            container: The DI container.
        """
        self.bot = bot
        self.container = container
        self.started_at = time.monotonic()
        self._warned = False

        # Get paths from settings or use defaults
        settings = container.settings
        log_dir = Path(getattr(settings, "log_dir", "logs"))
        log_dir.mkdir(parents=True, exist_ok=True)

        self.heartbeat_file = log_dir / "heartbeat.json"
        self.detailed_file = log_dir / "heartbeat_detailed.json"

        # Get intervals from settings
        health_settings = getattr(settings, "health", None)
        fast_interval = (
            getattr(health_settings, "fast_interval", DEFAULT_FAST_INTERVAL)
            if health_settings
            else DEFAULT_FAST_INTERVAL
        )
        detailed_interval = (
            getattr(health_settings, "detailed_interval", DEFAULT_DETAILED_INTERVAL)
            if health_settings
            else DEFAULT_DETAILED_INTERVAL
        )

        # Configure and start loops
        self.heartbeat_fast.change_interval(seconds=fast_interval)
        self.heartbeat_detailed.change_interval(seconds=detailed_interval)

    async def cog_load(self) -> None:
        """Called when the cog is loaded."""
        self.heartbeat_fast.start()
        self.heartbeat_detailed.start()
        logger.info(LogTemplates.COG_LOADED_HEALTH)

    async def cog_unload(self) -> None:
        """Called when the cog is unloaded."""
        self.heartbeat_fast.cancel()
        self.heartbeat_detailed.cancel()
        logger.info(LogTemplates.COG_UNLOADED_HEALTH)

    # ─────────────────────────────────────────────────────────────────
    # Helper Methods
    # ─────────────────────────────────────────────────────────────────

    def _format_uptime(self, seconds: int) -> str:
        """Format seconds into human-readable uptime duration."""
        hours, rem = divmod(max(seconds, 0), 3600)
        minutes, secs = divmod(rem, 60)
        parts: list[str] = []
        if hours:
            parts.append(f"{hours}h")
        if minutes or hours:
            parts.append(f"{minutes}m")
        parts.append(f"{secs}s")
        return " ".join(parts)

    def _latency_ms(self) -> float:
        """Get current websocket latency in milliseconds."""
        return round((self.bot.latency or 0.0) * ONE_THOUSAND, 1)

    def _latency_emoji(self, ms: float) -> str:
        """Get emoji based on latency level."""
        if ms < LATENCY_OK_MS:
            return "🟢"
        if ms < LATENCY_WARN_MS:
            return "🟠"
        return "🔴"

    def _status_emoji(self, connected: bool) -> str:
        """Get emoji based on connection status."""
        return "🟢" if connected else "🔴"

    def _embed_color_for_latency(self, ms: float) -> discord.Color:
        """Get embed color based on latency level."""
        if ms < LATENCY_OK_MS:
            return discord.Color.green()
        if ms < LATENCY_WARN_MS:
            return discord.Color.gold()
        return discord.Color.red()

    def _audio_snapshot(self) -> tuple[int, str | None]:
        """Get current audio state from playback service."""
        queue_len = 0
        current_title: str | None = None

        try:
            # Try to get from the container's services
            # This depends on the current session state
            pass  # In the new architecture, we'd query the session repository
        except Exception:
            pass

        return queue_len, current_title

    def _atomic_write(
        self, path: Path, payload: BasicStats | DetailedStats | dict[str, Any]
    ) -> None:
        """Atomically write JSON to file."""
        tmp = path.with_suffix(path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(dict(payload), f, ensure_ascii=False, indent=2)
        tmp.replace(path)

    # ─────────────────────────────────────────────────────────────────
    # Stats Collection
    # ─────────────────────────────────────────────────────────────────

    def _collect_basic_stats(self) -> BasicStats:
        """Collect basic health statistics."""
        uptime_s = int(time.monotonic() - self.started_at)
        lat_ms = self._latency_ms()
        queue_len, current_title = self._audio_snapshot()
        connected = not self.bot.is_closed()

        return {
            "ts": UtcDateTime.now().iso,
            "uptime_s": uptime_s,
            "uptime_human": self._format_uptime(uptime_s),
            "latency_ms": lat_ms,
            "latency_human": f"{lat_ms:.1f} ms",
            "queue_len": queue_len,
            "current": current_title,
            "connected": connected,
            "status": "online" if connected else "offline",
        }

    async def _collect_detailed_stats(self) -> DetailedStats:
        """Collect detailed health statistics."""
        payload: DetailedStats = self._collect_basic_stats()  # type: ignore[assignment]

        # Add guild and voice stats
        payload["guild_count"] = len(self.bot.guilds)
        payload["voice_connections"] = len(self.bot.voice_clients)

        # Add memory stats
        try:
            import psutil  # type: ignore

            proc = psutil.Process()
            with proc.oneshot():
                mem = proc.memory_full_info()
                mib = 1024 * 1024
                payload["rss_mb"] = round(mem.rss / mib, 1)
                vms = getattr(mem, "vms", None)
                payload["vms_mb"] = round(vms / mib, 1) if vms else None
        except ImportError:
            pass
        except Exception:
            pass

        # Add database stats
        try:
            db = self.container.database
            db_stats = await db.get_stats()
            payload["db_initialized"] = db_stats.get("initialized", False)
            payload["db_size_mb"] = db_stats.get("file_size_mb", 0)
        except Exception:
            pass

        return payload

    # ─────────────────────────────────────────────────────────────────
    # Heartbeat Loops
    # ─────────────────────────────────────────────────────────────────

    @tasks.loop(seconds=DEFAULT_FAST_INTERVAL, reconnect=True)
    async def heartbeat_fast(self) -> None:
        """Fast heartbeat loop for basic monitoring."""
        try:
            payload = self._collect_basic_stats()
            self._atomic_write(self.heartbeat_file, payload)

            # Latency warning logic
            lat_ms = payload["latency_ms"]
            settings = self.container.settings
            alert_channel_id = getattr(getattr(settings, "health", None), "alert_channel_id", None)

            if alert_channel_id:
                ch = self.bot.get_channel(alert_channel_id)
                if isinstance(ch, (discord.TextChannel, discord.Thread)):
                    if lat_ms >= LATENCY_WARN_MS and not self._warned:
                        try:
                            await ch.send(
                                f"⚠️ Heartbeat warning: latency {lat_ms}ms (>= {LATENCY_WARN_MS}ms)"
                            )
                            self._warned = True
                        except Exception:
                            pass
                    elif self._warned and lat_ms < (LATENCY_WARN_MS * LATENCY_RESET_FACTOR):
                        self._warned = False

            logger.debug(LogTemplates.HEARTBEAT_FAST, lat_ms)
        except Exception:
            logger.exception(LogTemplates.HEARTBEAT_FAST_ERROR)

    @tasks.loop(seconds=DEFAULT_DETAILED_INTERVAL, reconnect=True)
    async def heartbeat_detailed(self) -> None:
        """Detailed heartbeat loop for extended metrics."""
        try:
            payload = await self._collect_detailed_stats()
            self._atomic_write(self.detailed_file, payload)
            logger.debug(LogTemplates.HEARTBEAT_DETAILED)
        except Exception:
            logger.exception(LogTemplates.HEARTBEAT_DETAILED_ERROR)

    @heartbeat_fast.before_loop
    async def _wait_ready_fast(self) -> None:
        """Wait for bot to be ready before starting fast loop."""
        await self.bot.wait_until_ready()

    @heartbeat_detailed.before_loop
    async def _wait_ready_detailed(self) -> None:
        """Wait for bot to be ready before starting detailed loop."""
        await self.bot.wait_until_ready()

    # ─────────────────────────────────────────────────────────────────
    # Commands
    # ─────────────────────────────────────────────────────────────────

    @commands.hybrid_command(name="ping", description="Check bot latency.")
    async def ping(self, ctx: commands.Context) -> None:
        """Show current websocket latency."""
        lat_ms = self._latency_ms()
        emoji = self._latency_emoji(lat_ms)
        await ctx.send(
            DiscordUIMessages.SUCCESS_PONG.format(emoji=emoji, latency_ms=f"{lat_ms:.1f}"),
            ephemeral=True,
        )

    @commands.hybrid_command(name="health", description="Show bot health status.")
    async def health(self, ctx: commands.Context) -> None:
        """Show detailed bot health status."""
        payload = await self._collect_detailed_stats()
        is_admin = self._is_admin(ctx.author)
        embed = self._build_health_embed(payload, is_admin)
        await ctx.send(embed=embed, ephemeral=True)

    def _is_admin(self, author: discord.User | discord.Member) -> bool:
        """Check if author has admin permissions."""
        if isinstance(author, discord.Member):
            return author.guild_permissions.administrator
        return False

    def _build_health_embed(self, payload: DetailedStats, show_admin_info: bool) -> discord.Embed:
        """Build the health status embed.

        Args:
            payload: The collected stats.
            show_admin_info: Whether to show admin-only fields.

        Returns:
            The formatted embed.
        """
        lat_ms = float(payload["latency_ms"])
        color = self._embed_color_for_latency(lat_ms)

        embed = discord.Embed(title=DiscordUIMessages.EMBED_BOT_HEALTH, color=color)
        embed.timestamp = datetime.now(UTC)

        self._add_connection_fields(embed, payload, lat_ms)
        self._add_server_fields(embed, payload)
        self._add_audio_fields(embed, payload)

        if show_admin_info:
            self._add_admin_fields(embed, payload)

        embed.set_footer(text=DiscordUIMessages.EMBED_HEALTH_FOOTER)
        return embed

    def _add_connection_fields(
        self, embed: discord.Embed, payload: DetailedStats, lat_ms: float
    ) -> None:
        """Add connection status fields to embed."""
        connected = bool(payload["connected"])
        status_text = "Connected" if connected else "Disconnected"
        embed.add_field(
            name="Status", value=f"{self._status_emoji(connected)} {status_text}", inline=True
        )
        embed.add_field(name="Uptime", value=str(payload["uptime_human"]), inline=True)
        embed.add_field(
            name="Latency",
            value=f"{self._latency_emoji(lat_ms)} {payload['latency_human']}",
            inline=True,
        )

    def _add_server_fields(self, embed: discord.Embed, payload: DetailedStats) -> None:
        """Add server statistics fields to embed."""
        if "guild_count" in payload:
            embed.add_field(name="Guilds", value=str(payload["guild_count"]), inline=True)
        if "voice_connections" in payload:
            embed.add_field(
                name="Voice Connections", value=str(payload["voice_connections"]), inline=True
            )

    def _add_audio_fields(self, embed: discord.Embed, payload: DetailedStats) -> None:
        """Add audio/queue fields to embed."""
        embed.add_field(name="Queue Length", value=str(payload["queue_len"]), inline=True)
        current = payload.get("current")
        embed.add_field(name="Now Playing", value=current or "Nothing", inline=False)

    def _add_admin_fields(self, embed: discord.Embed, payload: DetailedStats) -> None:
        """Add admin-only fields (memory, database) to embed."""
        # Memory info
        mem_parts = self._format_memory_stats(payload)
        if mem_parts:
            embed.add_field(name="Memory", value=", ".join(mem_parts), inline=True)

        # Database info
        if "db_initialized" in payload:
            db_status = "✅" if payload["db_initialized"] else "❌"
            db_size = payload.get("db_size_mb", 0)
            embed.add_field(name="Database", value=f"{db_status} ({db_size} MB)", inline=True)

    def _format_memory_stats(self, payload: DetailedStats) -> list[str]:
        """Format memory statistics into display strings."""
        mem_parts: list[str] = []
        if "rss_mb" in payload:
            mem_parts.append(f"RSS: {payload['rss_mb']} MB")
        if "vms_mb" in payload and payload["vms_mb"]:
            mem_parts.append(f"VMS: {payload['vms_mb']} MB")
        return mem_parts


async def setup(bot: commands.Bot) -> None:
    """Set up the health cog.

    Args:
        bot: The Discord bot instance.
    """
    container = getattr(bot, "container", None)
    if container is None:
        raise RuntimeError(ErrorMessages.CONTAINER_NOT_FOUND)

    await bot.add_cog(HealthCog(bot, container))
