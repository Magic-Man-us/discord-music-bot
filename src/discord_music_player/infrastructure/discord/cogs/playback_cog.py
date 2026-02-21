"""Slash-command cog for core playback: play, pause, resume, stop, leave."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from discord_music_player.domain.music.entities import Track
from discord_music_player.domain.shared.constants import UIConstants
from discord_music_player.domain.shared.messages import DiscordUIMessages, ErrorMessages
from discord_music_player.domain.shared.types import DiscordSnowflake
from discord_music_player.infrastructure.discord.guards.voice_guards import (
    ensure_user_in_voice_and_warm,
    get_member,
    send_ephemeral,
)
from discord_music_player.utils.reply import (
    extract_youtube_timestamp,
    format_duration,
    parse_timestamp,
    truncate,
)

if TYPE_CHECKING:
    from ....config.container import Container
    from ....domain.music.value_objects import StartSeconds

logger = logging.getLogger(__name__)


class PlaybackCog(commands.Cog):
    def __init__(self, bot: commands.Bot, container: Container) -> None:
        self.bot = bot
        self.container = container

    async def cog_load(self) -> None:
        self.container.playback_service.set_track_finished_callback(self._on_track_finished)
        self.container.auto_skip_on_requester_leave.set_on_requester_left_callback(
            self._on_requester_left
        )

    async def cog_unload(self) -> None:
        self.container.message_state_manager.clear_all()

    # ─────────────────────────────────────────────────────────────────
    # Play
    # ─────────────────────────────────────────────────────────────────

    @app_commands.command(name="play", description="Play a song by URL or search query.")
    @app_commands.describe(
        query="YouTube URL or search query",
        timestamp='Start position (e.g. "1:30" or "90")',
    )
    async def play(
        self,
        interaction: discord.Interaction,
        query: str,
        timestamp: str | None = None,
    ) -> None:
        from ....domain.music.value_objects import StartSeconds

        raw_seconds: int | None = None
        if timestamp is not None:
            raw_seconds = parse_timestamp(timestamp)
            if raw_seconds is None:
                await interaction.response.send_message(
                    DiscordUIMessages.ERROR_INVALID_TIMESTAMP,
                    ephemeral=True,
                )
                return
        else:
            raw_seconds = extract_youtube_timestamp(query)

        seek = StartSeconds.from_optional(raw_seconds)

        await interaction.response.defer()
        await self._execute_play(interaction, query, start_seconds=seek)

    async def _execute_play(
        self,
        interaction: discord.Interaction,
        query: str,
        *,
        start_seconds: StartSeconds | None = None,
    ) -> None:
        """Full play flow: voice checks, warmup with retry view, connect, play.

        Expects the interaction to already be deferred.
        """
        member = await get_member(interaction)
        if member is None:
            return

        if not member.voice or not member.voice.channel:
            await send_ephemeral(interaction, DiscordUIMessages.STATE_NEED_TO_BE_IN_VOICE)
            return

        if not interaction.guild:
            return

        remaining = self.container.voice_warmup_tracker.remaining_seconds(
            guild_id=interaction.guild.id,
            user_id=member.id,
        )
        if remaining > 0:
            from ..views.warmup_retry_view import WarmupRetryView

            view = WarmupRetryView(
                remaining_seconds=remaining,
                query=query,
                execute_play=self._execute_play,
            )
            msg = await interaction.followup.send(
                DiscordUIMessages.STATE_VOICE_WARMUP_REQUIRED.format(remaining=remaining),
                view=view,
                ephemeral=True,
                wait=True,
            )
            view.set_message(msg)
            return

        voice_adapter = self.container.voice_adapter
        channel_id = member.voice.channel.id

        if not voice_adapter.is_connected(interaction.guild.id):
            success = await voice_adapter.ensure_connected(interaction.guild.id, channel_id)
            if not success:
                await send_ephemeral(
                    interaction, DiscordUIMessages.ERROR_COULD_NOT_JOIN_VOICE
                )
                return

        await self._play_track(interaction, query, start_seconds=start_seconds)

    async def _play_track(
        self,
        interaction: discord.Interaction,
        query: str,
        *,
        start_seconds: StartSeconds | None = None,
    ) -> None:
        """Resolve track, enqueue, start playback, and send response."""
        if not interaction.guild:
            return

        try:
            queue_service = self.container.queue_service
            playback_service = self.container.playback_service
            msm = self.container.message_state_manager
            resolver = self.container.audio_resolver

            track = await resolver.resolve(query)
            if not track:
                await interaction.followup.send(
                    DiscordUIMessages.ERROR_TRACK_NOT_FOUND.format(query=query), ephemeral=True
                )
                return

            user = interaction.user

            # Check if track is longer than 6 minutes - trigger vote
            from ....domain.shared.constants import LimitConstants

            if (
                track.duration_seconds
                and track.duration_seconds > LimitConstants.LONG_TRACK_THRESHOLD_SECONDS
            ):
                listeners = await self.container.voice_adapter.get_listeners(
                    interaction.guild.id
                )
                if len(listeners) > LimitConstants.LONG_TRACK_VOTE_BYPASS_LISTENERS:
                    if not interaction.channel_id:
                        await interaction.followup.send(
                            DiscordUIMessages.ERROR_NO_CHANNEL_CONTEXT, ephemeral=True
                        )
                        return

                    from ..views.long_track_vote_view import LongTrackVoteView

                    view = LongTrackVoteView(
                        guild_id=interaction.guild.id,
                        track=track,
                        requester_id=user.id,
                        requester_name=getattr(user, "display_name", user.name),
                        container=self.container,
                    )

                    channel = self.bot.get_channel(interaction.channel_id)
                    if channel and hasattr(channel, "send"):
                        vote_msg = await channel.send(
                            f"\u23f1\ufe0f **{getattr(user, 'display_name', user.name)}** wants to queue a long track ({format_duration(track.duration_seconds)}): **{truncate(track.title, 60)}**\nVote to accept or reject:",
                            view=view,
                        )
                        view.set_message(vote_msg)

                        await interaction.followup.send(
                            f"\u23f1\ufe0f Started vote for long track: **{truncate(track.title, 60)}**",
                            ephemeral=True,
                        )
                    return

            # Normal enqueue flow
            result = await queue_service.enqueue(
                guild_id=interaction.guild.id,
                track=track,
                user_id=user.id,
                user_name=getattr(user, "display_name", user.name),
            )

            if not result.success:
                await interaction.followup.send(result.message, ephemeral=True)
                return

            logger.info(
                "Enqueue result: position=%s, should_start=%s",
                result.position,
                result.should_start,
            )
            if result.should_start:
                logger.info("Calling start_playback for guild %s", interaction.guild.id)
                await playback_service.start_playback(
                    interaction.guild.id, start_seconds=start_seconds
                )

            resolved_track = result.track or track

            if result.should_start:
                # Check if there's a next track in the queue
                session = await self.container.session_repository.get(interaction.guild.id)
                upcoming = session.peek() if session else None

                embed = msm.build_now_playing_embed(resolved_track, next_track=upcoming)

                from ..views.now_playing_view import NowPlayingView

                view = NowPlayingView(
                    webpage_url=resolved_track.webpage_url,
                    title=resolved_track.title,
                    guild_id=interaction.guild.id,
                    container=self.container,
                )

                sent = await interaction.followup.send(
                    embed=embed,
                    view=view,
                    wait=True,
                )
                view.set_message(sent)
                if interaction.channel_id is not None:
                    msm.track_now_playing(
                        guild_id=interaction.guild.id,
                        track=resolved_track,
                        channel_id=interaction.channel_id,
                        message_id=sent.id,
                    )
            else:
                content = msm.format_queued_line(resolved_track)
                sent = await interaction.followup.send(
                    content=content,
                    wait=True,
                )
                if interaction.channel_id is not None:
                    msm.track_queued(
                        guild_id=interaction.guild.id,
                        track=resolved_track,
                        channel_id=interaction.channel_id,
                        message_id=sent.id,
                    )

        except Exception as e:
            logger.exception("Error in play command")
            await interaction.followup.send(
                DiscordUIMessages.ERROR_OCCURRED.format(error=e), ephemeral=True
            )

    # ─────────────────────────────────────────────────────────────────
    # Callbacks
    # ─────────────────────────────────────────────────────────────────

    async def _on_requester_left(self, guild_id: DiscordSnowflake, user_id: DiscordSnowflake, track: Track) -> None:
        from ....domain.shared.messages import LogTemplates
        from ..views.requester_left_view import RequesterLeftView

        msm = self.container.message_state_manager

        channel: discord.abc.Messageable | None = None
        state = msm.get_state(guild_id)
        if state.now_playing is not None:
            candidate = self.bot.get_channel(state.now_playing.channel_id)
            if isinstance(candidate, discord.abc.Messageable):
                channel = candidate

        if channel is None:
            guild = self.bot.get_guild(guild_id)
            if guild is not None and isinstance(guild.system_channel, discord.abc.Messageable):
                channel = guild.system_channel

        if channel is None:
            logger.warning(LogTemplates.REQUESTER_LEFT_CALLBACK_CHANNEL_FAILED, guild_id)
            await self.container.playback_service.skip_track(guild_id)
            return

        requester_name = f"<@{user_id}>"
        view = RequesterLeftView(
            guild_id=guild_id,
            playback_service=self.container.playback_service,
            track_title=track.title,
            requester_name=requester_name,
        )
        content = DiscordUIMessages.REQUESTER_LEFT_PROMPT.format(
            requester_name=requester_name,
            track_title=truncate(track.title, UIConstants.TITLE_TRUNCATION),
        )
        message = await channel.send(content, view=view)
        view.set_message(message)

    async def _on_track_finished(self, guild_id: DiscordSnowflake, track: Track) -> None:
        msm = self.container.message_state_manager
        await msm.on_track_finished(guild_id, track)

        session = await self.container.session_repository.get(guild_id)
        next_track = session.current_track if session is not None else None
        if next_track is not None:
            upcoming = session.peek() if session else None
            await msm.promote_next_track(
                guild_id,
                next_track,
                container=self.container,
                upcoming_track=upcoming,
            )

    # ─────────────────────────────────────────────────────────────────
    # Playback Controls
    # ─────────────────────────────────────────────────────────────────

    @app_commands.command(name="stop", description="Stop playback and clear the queue.")
    async def stop(self, interaction: discord.Interaction) -> None:
        if not await ensure_user_in_voice_and_warm(
            interaction, self.container.voice_warmup_tracker
        ):
            return

        assert interaction.guild is not None

        playback_service = self.container.playback_service
        queue_service = self.container.queue_service

        self.container.radio_service.disable_radio(interaction.guild.id)
        stopped = await playback_service.stop_playback(interaction.guild.id)
        cleared = await queue_service.clear(interaction.guild.id)

        if stopped or cleared > 0:
            self.container.message_state_manager.reset(interaction.guild.id)
            await interaction.response.send_message(
                DiscordUIMessages.ACTION_STOPPED, ephemeral=True
            )
        else:
            await interaction.response.send_message(
                DiscordUIMessages.STATE_NOTHING_PLAYING, ephemeral=True
            )

    @app_commands.command(name="pause", description="Pause the current track.")
    async def pause(self, interaction: discord.Interaction) -> None:
        if not await ensure_user_in_voice_and_warm(
            interaction, self.container.voice_warmup_tracker
        ):
            return

        assert interaction.guild is not None

        playback_service = self.container.playback_service
        paused = await playback_service.pause_playback(interaction.guild.id)

        if paused:
            await interaction.response.send_message(DiscordUIMessages.ACTION_PAUSED, ephemeral=True)
        else:
            await interaction.response.send_message(
                DiscordUIMessages.STATE_NOTHING_PLAYING_OR_PAUSED, ephemeral=True
            )

    @app_commands.command(name="resume", description="Resume paused playback.")
    async def resume(self, interaction: discord.Interaction) -> None:
        if not await ensure_user_in_voice_and_warm(
            interaction, self.container.voice_warmup_tracker
        ):
            return

        assert interaction.guild is not None

        playback_service = self.container.playback_service
        resumed = await playback_service.resume_playback(interaction.guild.id)

        if resumed:
            await interaction.response.send_message(
                DiscordUIMessages.ACTION_RESUMED, ephemeral=True
            )
        else:
            await interaction.response.send_message(
                DiscordUIMessages.STATE_NOTHING_PAUSED, ephemeral=True
            )

    # ─────────────────────────────────────────────────────────────────
    # Leave
    # ─────────────────────────────────────────────────────────────────

    @app_commands.command(name="leave", description="Disconnect from voice channel.")
    async def leave(self, interaction: discord.Interaction) -> None:
        if not await ensure_user_in_voice_and_warm(
            interaction, self.container.voice_warmup_tracker
        ):
            return

        assert interaction.guild is not None

        voice_adapter = self.container.voice_adapter
        playback_service = self.container.playback_service

        self.container.radio_service.disable_radio(interaction.guild.id)
        await playback_service.cleanup_guild(interaction.guild.id)
        self.container.message_state_manager.reset(interaction.guild.id)
        disconnected = await voice_adapter.disconnect(interaction.guild.id)

        if disconnected:
            await interaction.response.send_message(
                DiscordUIMessages.ACTION_DISCONNECTED, ephemeral=True
            )
        else:
            await interaction.response.send_message(
                DiscordUIMessages.STATE_NOT_CONNECTED_TO_VOICE, ephemeral=True
            )


async def setup(bot: commands.Bot) -> None:
    container = getattr(bot, "container", None)
    if container is None:
        raise RuntimeError(ErrorMessages.CONTAINER_NOT_FOUND)

    await bot.add_cog(PlaybackCog(bot, container))
