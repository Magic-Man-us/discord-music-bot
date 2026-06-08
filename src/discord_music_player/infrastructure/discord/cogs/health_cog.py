"""Health monitoring with heartbeat loops, latency tracking, and status commands."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import discord
from discord.ext import commands, tasks
from pydantic import BaseModel

from ....domain.music.enums import PlaybackState
from ....domain.shared.constants import HealthConstants, UIConstants
from ....domain.shared.datetime_utils import UtcDateTime
from ....domain.shared.enums import BotStatus
from ....domain.shared.model_config import ExtraAllowedModelConfig, StrictSchemaModelConfig
from ....domain.shared.types import (
    BYTES_PER_MB,
    FileSizeMB,
    NonEmptyStr,
    NonNegativeFloat,
    NonNegativeInt,
)
from .base_cog import BaseCog

if TYPE_CHECKING:
    from ....config.container import Container


class BasicStats(BaseModel):
    """Core heartbeat stats written to JSON file."""

    model_config = StrictSchemaModelConfig

    ts: NonEmptyStr
    uptime_s: NonNegativeInt
    uptime_human: NonEmptyStr
    latency_ms: NonNegativeFloat
    latency_human: NonEmptyStr
    queue_len: NonNegativeInt
    guilds_playing: NonNegativeInt
    connected: bool
    status: BotStatus


class DetailedStats(BasicStats):
    """Extended heartbeat stats with optional system info."""

    model_config = ExtraAllowedModelConfig

    guild_count: NonNegativeInt | None = None
    voice_connections: NonNegativeInt | None = None
    rss_mb: FileSizeMB | None = None
    vms_mb: FileSizeMB | None = None
    db_initialized: bool | None = None
    db_size_mb: FileSizeMB | None = None


class HealthCog(BaseCog):
    def __init__(self, bot: commands.Bot, container: Container) -> None:
        super().__init__(bot, container)

        self.started_at = time.monotonic()
        self._warned = False

        settings = container.settings
        log_dir = Path(settings.log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)

        self.heartbeat_file = log_dir / "heartbeat.json"
        self.detailed_file = log_dir / "heartbeat_detailed.json"

        self.heartbeat_fast.change_interval(seconds=settings.health.fast_interval)
        self.heartbeat_detailed.change_interval(seconds=settings.health.detailed_interval)

    async def cog_load(self) -> None:
        self.heartbeat_fast.start()
        self.heartbeat_detailed.start()
        self.logger.info("Health cog loaded, heartbeat loops started")

    async def cog_unload(self) -> None:
        self.heartbeat_fast.cancel()
        self.heartbeat_detailed.cancel()
        self.logger.info("Health cog unloaded, heartbeat loops stopped")

    # ─────────────────────────────────────────────────────────────────
    # Helper Methods
    # ─────────────────────────────────────────────────────────────────

    def _format_uptime(self, seconds: int) -> str:
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
        return round((self.bot.latency or 0.0) * UIConstants.MS_PER_SECOND, 1)

    def _latency_label(self, ms: float) -> str:
        if ms < HealthConstants.LATENCY_OK_MS:
            return "OK"
        if ms < HealthConstants.LATENCY_WARN_MS:
            return "Slow"
        return "Critical"

    def _status_label(self, connected: bool) -> str:
        return "Online" if connected else "Offline"

    def _embed_color_for_latency(self, ms: float) -> discord.Color:
        if ms < HealthConstants.LATENCY_OK_MS:
            return discord.Color.green()
        if ms < HealthConstants.LATENCY_WARN_MS:
            return discord.Color.gold()
        return discord.Color.red()

    async def _audio_snapshot(self) -> tuple[int, int]:
        """Aggregate (total queued tracks, guilds currently playing) over active sessions."""
        try:
            sessions = await self.container.session_repository.get_all_active()
        except Exception:
            # Best-effort metric: a transient DB read failure must not abort the heartbeat.
            self.logger.debug("Failed to read sessions for health snapshot")
            return 0, 0

        total_queued = sum(session.queue_length for session in sessions)
        guilds_playing = sum(1 for session in sessions if session.state == PlaybackState.PLAYING)
        return total_queued, guilds_playing

    def _atomic_write(self, path: Path, payload: BasicStats | DetailedStats) -> None:
        tmp = path.with_suffix(path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            f.write(payload.model_dump_json(exclude_none=True, indent=2))
        tmp.replace(path)

    # ─────────────────────────────────────────────────────────────────
    # Stats Collection
    # ─────────────────────────────────────────────────────────────────

    async def _collect_basic_stats(self) -> BasicStats:
        uptime_s = int(time.monotonic() - self.started_at)
        lat_ms = self._latency_ms()
        queue_len, guilds_playing = await self._audio_snapshot()
        connected = not self.bot.is_closed()

        return BasicStats(
            ts=UtcDateTime.now().iso,
            uptime_s=uptime_s,
            uptime_human=self._format_uptime(uptime_s),
            latency_ms=lat_ms,
            latency_human=f"{lat_ms:.1f} ms",
            queue_len=queue_len,
            guilds_playing=guilds_playing,
            connected=connected,
            status=BotStatus.ONLINE if connected else BotStatus.OFFLINE,
        )

    async def _collect_detailed_stats(self) -> DetailedStats:
        basic = await self._collect_basic_stats()
        payload = DetailedStats(
            **basic.model_dump(),
            guild_count=len(self.bot.guilds),
            voice_connections=len(self.bot.voice_clients),
        )

        try:
            import psutil  # type: ignore

            proc = psutil.Process()
            with proc.oneshot():
                mem = proc.memory_full_info()
                payload.rss_mb = round(mem.rss / BYTES_PER_MB, 1)
                # psutil's memory tuple is platform-dependent; the broad except below covers gaps.
                payload.vms_mb = round(mem.vms / BYTES_PER_MB, 1)
        except ImportError:
            pass
        except Exception:
            pass

        try:
            db = self.container.database
            db_stats = await db.get_stats()
            payload.db_initialized = db_stats.initialized
            payload.db_size_mb = db_stats.file_size_mb if db_stats.file_size_mb is not None else 0.0
        except Exception:
            pass

        return payload

    # ─────────────────────────────────────────────────────────────────
    # Heartbeat Loops
    # ─────────────────────────────────────────────────────────────────

    @tasks.loop(seconds=HealthConstants.DEFAULT_FAST_INTERVAL, reconnect=True)
    async def heartbeat_fast(self) -> None:
        try:
            payload = await self._collect_basic_stats()
            self._atomic_write(self.heartbeat_file, payload)

            # Latency warning logic
            lat_ms = payload.latency_ms
            alert_channel_id = self.container.settings.health.alert_channel_id

            if alert_channel_id:
                ch = self.bot.get_channel(alert_channel_id)
                if isinstance(ch, (discord.TextChannel, discord.Thread)):
                    if lat_ms >= HealthConstants.LATENCY_WARN_MS and not self._warned:
                        try:
                            await ch.send(
                                f"Heartbeat warning: latency {lat_ms}ms (>= {HealthConstants.LATENCY_WARN_MS}ms)"
                            )
                            self._warned = True
                        except Exception:
                            pass
                    elif self._warned and lat_ms < (
                        HealthConstants.LATENCY_WARN_MS * HealthConstants.LATENCY_RESET_FACTOR
                    ):
                        self._warned = False

            self.logger.debug("Fast heartbeat: latency=%.1fms", lat_ms)
        except Exception:
            self.logger.exception("Fast heartbeat error")

    @tasks.loop(seconds=HealthConstants.DEFAULT_DETAILED_INTERVAL, reconnect=True)
    async def heartbeat_detailed(self) -> None:
        try:
            payload = await self._collect_detailed_stats()
            self._atomic_write(self.detailed_file, payload)
            self.logger.debug("Detailed heartbeat collected")
        except Exception:
            self.logger.exception("Detailed heartbeat error")

    @heartbeat_fast.before_loop
    async def _wait_ready_fast(self) -> None:
        await self.bot.wait_until_ready()

    @heartbeat_detailed.before_loop
    async def _wait_ready_detailed(self) -> None:
        await self.bot.wait_until_ready()

    # ─────────────────────────────────────────────────────────────────
    # Commands
    # ─────────────────────────────────────────────────────────────────

    @commands.hybrid_command(name="ping", description="Check bot latency.")
    async def ping(self, ctx: commands.Context) -> None:
        lat_ms = self._latency_ms()
        label = self._latency_label(lat_ms)
        await ctx.send(
            f"Pong: {lat_ms:.1f} ms ({label})",
            ephemeral=True,
        )

    @commands.hybrid_command(name="health", description="Show bot health status.")
    async def health(self, ctx: commands.Context) -> None:
        payload = await self._collect_detailed_stats()
        is_admin = self._is_admin(ctx.author)
        embed = self._build_health_embed(payload, is_admin)
        await ctx.send(embed=embed, ephemeral=True)

    def _is_admin(self, author: discord.User | discord.Member) -> bool:
        if isinstance(author, discord.Member):
            return author.guild_permissions.administrator
        return False

    def _build_health_embed(self, payload: DetailedStats, show_admin_info: bool) -> discord.Embed:
        lat_ms = payload.latency_ms
        color = self._embed_color_for_latency(lat_ms)

        embed = discord.Embed(title="Bot Health", color=color)
        embed.timestamp = datetime.now(UTC)

        self._add_connection_fields(embed, payload, lat_ms)
        self._add_server_fields(embed, payload)
        self._add_audio_fields(embed, payload)

        if show_admin_info:
            self._add_admin_fields(embed, payload)

        embed.set_footer(text="Use /ping for quick latency check")
        return embed

    def _add_connection_fields(
        self, embed: discord.Embed, payload: DetailedStats, lat_ms: float
    ) -> None:
        status_text = self._status_label(payload.connected)
        embed.add_field(name="Status", value=status_text, inline=True)
        embed.add_field(name="Uptime", value=payload.uptime_human, inline=True)
        embed.add_field(
            name="Latency",
            value=f"{payload.latency_human} ({self._latency_label(lat_ms)})",
            inline=True,
        )

    def _add_server_fields(self, embed: discord.Embed, payload: DetailedStats) -> None:
        if payload.guild_count is not None:
            embed.add_field(name="Guilds", value=str(payload.guild_count), inline=True)
        if payload.voice_connections is not None:
            embed.add_field(
                name="Voice Connections", value=str(payload.voice_connections), inline=True
            )

    def _add_audio_fields(self, embed: discord.Embed, payload: DetailedStats) -> None:
        embed.add_field(name="Tracks Queued", value=str(payload.queue_len), inline=True)
        embed.add_field(name="Guilds Playing", value=str(payload.guilds_playing), inline=True)

    def _add_admin_fields(self, embed: discord.Embed, payload: DetailedStats) -> None:
        mem_parts = self._format_memory_stats(payload)
        if mem_parts:
            embed.add_field(name="Memory", value=", ".join(mem_parts), inline=True)

        if payload.db_initialized is not None:
            db_status = "Yes" if payload.db_initialized else "No"
            db_size = payload.db_size_mb or 0
            embed.add_field(name="Database", value=f"{db_status} ({db_size} MB)", inline=True)

    def _format_memory_stats(self, payload: DetailedStats) -> list[str]:
        mem_parts: list[str] = []
        if payload.rss_mb is not None:
            mem_parts.append(f"RSS: {payload.rss_mb} MB")
        if payload.vms_mb is not None:
            mem_parts.append(f"VMS: {payload.vms_mb} MB")
        return mem_parts


setup = HealthCog.setup
