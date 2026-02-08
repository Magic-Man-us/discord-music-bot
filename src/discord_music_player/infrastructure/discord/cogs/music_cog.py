"""Slash-command music cog delegating to application services."""

from __future__ import annotations

import logging
import math
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from discord_music_player.domain.music.entities import Track
from discord_music_player.domain.music.value_objects import LoopMode
from discord_music_player.domain.shared.messages import DiscordUIMessages
from discord_music_player.domain.voting.value_objects import VoteResult
from discord_music_player.utils.reply import format_duration, truncate

if TYPE_CHECKING:
    from ....application.commands.vote_skip import VoteSkipResult
    from ....config.container import Container

logger = logging.getLogger(__name__)

QUEUE_PER_PAGE = 10


@dataclass(slots=True, frozen=True)
class _TrackKey:
    track_id: str
    requested_by_id: int | None
    requested_at: datetime | None

    @classmethod
    def from_track(cls, track: Track) -> _TrackKey:
        return cls(
            track_id=track.id.value,
            requested_by_id=track.requested_by_id,
            requested_at=track.requested_at,
        )


@dataclass(slots=True)
class _TrackedMessage:
    channel_id: int
    message_id: int
    track_key: _TrackKey

    @classmethod
    def from_track(cls, track: Track, *, channel_id: int, message_id: int) -> _TrackedMessage:
        return cls(
            channel_id=channel_id,
            message_id=message_id,
            track_key=_TrackKey.from_track(track),
        )


@dataclass(slots=True)
class _GuildMessageState:
    now_playing: _TrackedMessage | None = None
    queued: deque[_TrackedMessage] = field(default_factory=deque)

    def pop_matching_queued(self, track: Track) -> _TrackedMessage | None:
        target = _TrackKey.from_track(track)
        if not self.queued:
            return None

        found: _TrackedMessage | None = None
        for tracked in self.queued:
            if tracked.track_key == target:
                found = tracked
                break

        if found is None:
            return None

        self.queued = deque(t for t in self.queued if t.track_key != target)
        return found


class MusicCog(commands.Cog):
    def __init__(self, bot: commands.Bot, container: Container) -> None:
        self.bot = bot
        self.container = container

        self._message_state_by_guild: dict[int, _GuildMessageState] = {}

    async def cog_load(self) -> None:
        self.container.playback_service.set_track_finished_callback(self._on_track_finished)
        self.container.auto_skip_on_requester_leave.set_on_requester_left_callback(
            self._on_requester_left
        )

    async def cog_unload(self) -> None:
        self._message_state_by_guild.clear()

    async def _send_ephemeral(self, interaction: discord.Interaction, message: str) -> None:
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)

    async def _get_member(self, interaction: discord.Interaction) -> discord.Member | None:
        if not interaction.guild:
            await self._send_ephemeral(
                interaction,
                DiscordUIMessages.STATE_SERVER_ONLY,
            )
            return None

        user = interaction.user
        if not isinstance(user, discord.Member):
            await self._send_ephemeral(interaction, DiscordUIMessages.STATE_VERIFY_VOICE_FAILED)
            return None

        return user

    async def _ensure_voice_warmup(
        self, interaction: discord.Interaction, member: discord.Member
    ) -> bool:
        if not interaction.guild:
            return False

        remaining = self.container.voice_warmup_tracker.remaining_seconds(
            guild_id=interaction.guild.id,
            user_id=member.id,
        )
        if remaining <= 0:
            return True

        await self._send_ephemeral(
            interaction,
            DiscordUIMessages.STATE_VOICE_WARMUP_REQUIRED.format(remaining=remaining),
        )
        return False

    async def _ensure_user_in_voice_and_warm(self, interaction: discord.Interaction) -> bool:
        member = await self._get_member(interaction)
        if member is None:
            return False

        if not member.voice or not member.voice.channel:
            await self._send_ephemeral(interaction, DiscordUIMessages.STATE_NEED_TO_BE_IN_VOICE)
            return False

        return await self._ensure_voice_warmup(interaction, member)

    async def _ensure_voice(self, interaction: discord.Interaction) -> bool:
        member = await self._get_member(interaction)
        if member is None:
            return False

        assert interaction.guild is not None

        if not member.voice or not member.voice.channel:
            await self._send_ephemeral(interaction, DiscordUIMessages.STATE_NEED_TO_BE_IN_VOICE)
            return False

        if not await self._ensure_voice_warmup(interaction, member):
            return False

        voice_adapter = self.container.voice_adapter
        channel_id = member.voice.channel.id

        if not voice_adapter.is_connected(interaction.guild.id):
            success = await voice_adapter.ensure_connected(interaction.guild.id, channel_id)
            if not success:
                await self._send_ephemeral(
                    interaction, DiscordUIMessages.ERROR_COULD_NOT_JOIN_VOICE
                )
                return False

        return True

    @app_commands.command(name="play", description="Play a song by URL or search query.")
    @app_commands.describe(query="YouTube URL or search query")
    async def play(
        self,
        interaction: discord.Interaction,
        query: str,
    ) -> None:
        # Defer early because voice connection can exceed the 3-second interaction deadline
        await interaction.response.defer()

        if not await self._ensure_voice(interaction):
            return

        if not interaction.guild:
            return

        try:
            queue_service = self.container.queue_service
            playback_service = self.container.playback_service
            resolver = self.container.audio_resolver

            track = await resolver.resolve(query)
            if not track:
                await interaction.followup.send(
                    DiscordUIMessages.ERROR_TRACK_NOT_FOUND.format(query=query), ephemeral=True
                )
                return

            user = interaction.user
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
                logger.info(
                    "Calling start_playback for guild %s",
                    interaction.guild.id,
                )
                await playback_service.start_playback(interaction.guild.id)

            resolved_track = result.track or track

            if result.should_start:
                embed = self._build_now_playing_embed(resolved_track)

                from ..views.download_view import DownloadView

                view = DownloadView(
                    webpage_url=resolved_track.webpage_url,
                    title=resolved_track.title,
                )

                sent = await interaction.followup.send(
                    embed=embed,
                    view=view,
                    wait=True,
                )
                if interaction.channel_id is not None:
                    self._track_now_playing_message(
                        guild_id=interaction.guild.id,
                        track=resolved_track,
                        channel_id=interaction.channel_id,
                        message_id=sent.id,
                    )
            else:
                content = self._format_queued_line(resolved_track)
                sent = await interaction.followup.send(
                    content=content,
                    wait=True,
                )
                if interaction.channel_id is not None:
                    self._track_queued_message(
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

    async def _on_requester_left(self, guild_id: int, user_id: int, track: Track) -> None:
        from ....domain.shared.messages import LogTemplates
        from ..views.requester_left_view import RequesterLeftView

        # Determine text channel from now-playing message state
        channel: discord.abc.Messageable | None = None
        state = self._message_state_by_guild.get(guild_id)
        if state is not None and state.now_playing is not None:
            candidate = self.bot.get_channel(state.now_playing.channel_id)
            if isinstance(candidate, discord.abc.Messageable):
                channel = candidate

        # Fall back to guild system channel
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
            track_title=truncate(track.title, 80),
        )
        message = await channel.send(content, view=view)
        view.set_message(message)

    async def _on_track_finished(self, guild_id: int, track: Track) -> None:
        state = self._message_state_by_guild.get(guild_id)
        if state is None:
            return

        if state.now_playing is not None:
            await self._edit_message_to_one_liner(
                state.now_playing,
                content=self._format_finished_line(track),
            )
            state.now_playing = None

        session = await self.container.session_repository.get(guild_id)
        next_track = session.current_track if session is not None else None
        if next_track is None:
            return

        queued_msg = state.pop_matching_queued(next_track)
        if queued_msg is None:
            return

        embed = self._build_now_playing_embed(next_track)

        from ..views.download_view import DownloadView

        view = DownloadView(webpage_url=next_track.webpage_url, title=next_track.title)

        await self._edit_message_to_embed(queued_msg, embed=embed, view=view)
        state.now_playing = queued_msg

    def _get_state(self, guild_id: int) -> _GuildMessageState:
        state = self._message_state_by_guild.get(guild_id)
        if state is None:
            state = _GuildMessageState()
            self._message_state_by_guild[guild_id] = state
        return state

    def _track_now_playing_message(
        self,
        *,
        guild_id: int,
        track: Track,
        channel_id: int,
        message_id: int,
    ) -> None:
        state = self._get_state(guild_id)
        state.now_playing = _TrackedMessage.from_track(
            track,
            channel_id=channel_id,
            message_id=message_id,
        )

    def _track_queued_message(
        self,
        *,
        guild_id: int,
        track: Track,
        channel_id: int,
        message_id: int,
    ) -> None:
        state = self._get_state(guild_id)
        state.queued.append(
            _TrackedMessage.from_track(
                track,
                channel_id=channel_id,
                message_id=message_id,
            )
        )

    def _format_requester(self, track: Track) -> str:
        if track.requested_by_id:
            return f"<@{track.requested_by_id}>"
        if track.requested_by_name:
            return track.requested_by_name
        return "Unknown"

    def _format_queued_line(self, track: Track) -> str:
        requester = self._format_requester(track)
        title = truncate(track.title, 80)
        return f"⏭️ Queued for play: [{title}]({track.webpage_url}) — {requester}"

    def _format_finished_line(self, track: Track) -> str:
        requester = self._format_requester(track)
        title = truncate(track.title, 80)
        return f"✅ Finished playing: [{title}]({track.webpage_url}) — {requester}"

    def _build_now_playing_embed(self, track: Track) -> discord.Embed:
        requester_display = self._format_requester(track)
        artist_or_uploader = track.artist or track.uploader
        likes_display = f"{track.like_count:,}" if track.like_count is not None else None

        description_lines = [f"[{track.title}]({track.webpage_url})"]
        description_lines.append(f"Requested by: {requester_display}")

        embed = discord.Embed(
            title=DiscordUIMessages.EMBED_NOW_PLAYING,
            description="\n".join(description_lines),
            color=discord.Color.green(),
        )

        if track.thumbnail_url:
            embed.set_thumbnail(url=track.thumbnail_url)

        embed.add_field(
            name="⏱️ Duration",
            value=format_duration(track.duration_seconds),
            inline=True,
        )

        if artist_or_uploader:
            embed.add_field(
                name="👤 Artist",
                value=truncate(artist_or_uploader, 64),
                inline=True,
            )

        if likes_display:
            embed.add_field(
                name="👍 Likes",
                value=likes_display,
                inline=True,
            )

        return embed

    async def _edit_message_to_one_liner(self, tracked: _TrackedMessage, *, content: str) -> None:
        message = await self._fetch_message(tracked)
        if message is None:
            return

        try:
            await message.edit(content=content, embed=None, view=None)
        except discord.HTTPException:
            logger.debug(
                "Failed editing message %s in channel %s",
                tracked.message_id,
                tracked.channel_id,
            )

    async def _edit_message_to_embed(
        self,
        tracked: _TrackedMessage,
        *,
        embed: discord.Embed,
        view: discord.ui.View | None,
    ) -> None:
        message = await self._fetch_message(tracked)
        if message is None:
            return

        try:
            await message.edit(content=None, embed=embed, view=view)
        except discord.HTTPException:
            logger.debug(
                "Failed promoting message %s in channel %s",
                tracked.message_id,
                tracked.channel_id,
            )

    async def _fetch_message(self, tracked: _TrackedMessage) -> discord.Message | None:
        channel = self.bot.get_channel(tracked.channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(tracked.channel_id)
            except discord.HTTPException:
                return None

        fetch_message = getattr(channel, "fetch_message", None)
        if fetch_message is None:
            return None

        try:
            return await fetch_message(tracked.message_id)
        except discord.HTTPException:
            return None

    def _reset_message_state(self, guild_id: int) -> None:
        self._message_state_by_guild.pop(guild_id, None)

    def cleanup_guild_message_state(self, guild_id: int) -> None:
        self._reset_message_state(guild_id)
        logger.debug("Cleaned up message state for guild %s", guild_id)

    @app_commands.command(
        name="played",
        description="Show recently played tracks for this server.",
    )
    async def played(self, interaction: discord.Interaction) -> None:
        if not await self._ensure_user_in_voice_and_warm(interaction):
            return

        if not interaction.guild:
            return

        history_repo = self.container.history_repository
        tracks = await history_repo.get_recent(interaction.guild.id, limit=10)
        if not tracks:
            await self._send_ephemeral(interaction, DiscordUIMessages.STATE_NO_TRACKS_PLAYED_YET)
            return

        lines: list[str] = []
        for index, history_track in enumerate(tracks, start=1):
            parts: list[str] = []

            title = truncate(history_track.title, 80)
            parts.append(f"**{index}.** [{title}]({history_track.webpage_url})")

            artist_or_uploader = history_track.artist or history_track.uploader
            if artist_or_uploader:
                parts.append(truncate(artist_or_uploader, 48))

            duration = format_duration(history_track.duration_seconds)
            if duration:
                parts.append(duration)

            if history_track.like_count is not None:
                parts.append(f"👍 {history_track.like_count:,}")

            if history_track.requested_by_id:
                parts.append(f"req <@{history_track.requested_by_id}>")
            elif history_track.requested_by_name:
                parts.append(f"req {truncate(history_track.requested_by_name, 24)}")

            lines.append(" — ".join(parts))

        embed = discord.Embed(
            title=DiscordUIMessages.EMBED_RECENTLY_PLAYED,
            description="\n".join(lines),
            color=discord.Color.blurple(),
        )

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="skip", description="Vote to skip the current track.")
    @app_commands.describe(force="Force skip (admin only)")
    async def skip(self, interaction: discord.Interaction, force: bool = False) -> None:
        if not await self._ensure_user_in_voice_and_warm(interaction):
            return

        assert interaction.guild is not None

        user = interaction.user
        if not isinstance(user, discord.Member):
            await self._send_ephemeral(
                interaction, DiscordUIMessages.STATE_VERIFY_PERMISSIONS_FAILED
            )
            return

        if force:
            await self._handle_force_skip(interaction, user)
        else:
            await self._handle_vote_skip(interaction, user)

    async def _handle_force_skip(
        self, interaction: discord.Interaction, user: discord.Member
    ) -> None:
        if not self._can_force_skip(user):
            await interaction.response.send_message(
                DiscordUIMessages.ERROR_FORCE_SKIP_REQUIRES_ADMIN, ephemeral=True
            )
            return

        playback_service = self.container.playback_service
        track = await playback_service.skip_track(interaction.guild.id)  # type: ignore

        if track:
            await interaction.response.send_message(
                DiscordUIMessages.ACTION_SKIP_FORCE.format(track_title=track.title), ephemeral=True
            )
        else:
            await interaction.response.send_message(
                DiscordUIMessages.STATE_NOTHING_PLAYING, ephemeral=True
            )

    def _can_force_skip(self, user: discord.Member) -> bool:
        is_admin = user.guild_permissions.administrator
        is_owner = user.id in self.container.settings.discord.owner_ids
        return is_admin or is_owner

    async def _handle_vote_skip(
        self, interaction: discord.Interaction, user: discord.Member
    ) -> None:
        user_channel_id = None
        if user.voice and user.voice.channel:
            user_channel_id = user.voice.channel.id

        from ....application.commands.vote_skip import VoteSkipCommand

        command = VoteSkipCommand(
            guild_id=interaction.guild.id,  # type: ignore
            user_id=user.id,
            user_channel_id=user_channel_id,
        )

        handler = self.container.vote_skip_handler
        result = await handler.handle(command)

        if result.action_executed:
            await self._send_skip_success(interaction, result)
        else:
            await self._send_skip_failure(interaction, result)

    async def _send_skip_success(
        self, interaction: discord.Interaction, result: VoteSkipResult
    ) -> None:
        playback_service = self.container.playback_service
        skipped_track = await playback_service.skip_track(interaction.guild.id)  # type: ignore
        track_title = skipped_track.title if skipped_track else "track"

        match result.result:
            case VoteResult.THRESHOLD_MET:
                msg = DiscordUIMessages.ACTION_SKIP_THRESHOLD_MET.format(
                    votes_current=result.votes_current,
                    votes_needed=result.votes_needed,
                    track_title=track_title,
                )
            case VoteResult.REQUESTER_SKIP:
                msg = DiscordUIMessages.ACTION_SKIP_REQUESTER.format(track_title=track_title)
            case VoteResult.AUTO_SKIP:
                msg = DiscordUIMessages.ACTION_SKIP_AUTO.format(track_title=track_title)
            case _:
                msg = DiscordUIMessages.ACTION_SKIP_GENERIC.format(track_title=track_title)

        await interaction.response.send_message(msg, ephemeral=True)

    async def _send_skip_failure(
        self, interaction: discord.Interaction, result: VoteSkipResult
    ) -> None:
        match result.result:
            case VoteResult.NO_PLAYING:
                msg = DiscordUIMessages.STATE_NOTHING_PLAYING
            case VoteResult.NOT_IN_CHANNEL:
                msg = DiscordUIMessages.VOTE_NOT_IN_CHANNEL
            case VoteResult.ALREADY_VOTED:
                msg = DiscordUIMessages.VOTE_ALREADY_VOTED.format(
                    votes_current=result.votes_current, votes_needed=result.votes_needed
                )
            case VoteResult.VOTE_RECORDED:
                msg = DiscordUIMessages.VOTE_RECORDED.format(
                    votes_current=result.votes_current, votes_needed=result.votes_needed
                )
            case _:
                msg = DiscordUIMessages.VOTE_SKIP_PROCESSED

        await interaction.response.send_message(msg, ephemeral=True)

    @app_commands.command(name="stop", description="Stop playback and clear the queue.")
    async def stop(self, interaction: discord.Interaction) -> None:
        if not await self._ensure_user_in_voice_and_warm(interaction):
            return

        assert interaction.guild is not None

        playback_service = self.container.playback_service
        queue_service = self.container.queue_service

        self.container.radio_service.disable_radio(interaction.guild.id)
        stopped = await playback_service.stop_playback(interaction.guild.id)
        cleared = await queue_service.clear(interaction.guild.id)

        if stopped or cleared > 0:
            self._reset_message_state(interaction.guild.id)
            await interaction.response.send_message(
                DiscordUIMessages.ACTION_STOPPED, ephemeral=True
            )
        else:
            await interaction.response.send_message(
                DiscordUIMessages.STATE_NOTHING_PLAYING, ephemeral=True
            )

    @app_commands.command(name="pause", description="Pause the current track.")
    async def pause(self, interaction: discord.Interaction) -> None:
        if not await self._ensure_user_in_voice_and_warm(interaction):
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
        if not await self._ensure_user_in_voice_and_warm(interaction):
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

    @app_commands.command(name="queue", description="Show the current queue.")
    @app_commands.describe(page="Page number")
    async def queue(self, interaction: discord.Interaction, page: int = 1) -> None:
        if not await self._ensure_user_in_voice_and_warm(interaction):
            return

        assert interaction.guild is not None

        queue_service = self.container.queue_service
        queue_info = await queue_service.get_queue(interaction.guild.id)

        if queue_info.total_tracks == 0:
            await interaction.response.send_message(
                DiscordUIMessages.STATE_QUEUE_EMPTY, ephemeral=True
            )
            return

        per_page = QUEUE_PER_PAGE
        total_pages = max(1, math.ceil(queue_info.total_tracks / per_page))
        page = max(1, min(page, total_pages))
        start_idx = (page - 1) * per_page

        embed = discord.Embed(
            title=DiscordUIMessages.EMBED_QUEUE.format(
                total_tracks=queue_info.total_tracks, page=page, total_pages=total_pages
            ),
            color=discord.Color.blurple(),
        )

        if queue_info.current_track:
            embed.add_field(
                name="🎵 Now Playing",
                value=f"**{truncate(queue_info.current_track.title)}**\n"
                f"Duration: {format_duration(queue_info.current_track.duration_seconds)}",
                inline=False,
            )

        tracks = queue_info.tracks[start_idx : start_idx + per_page]
        for idx, track in enumerate(tracks, start=start_idx + 1):
            embed.add_field(
                name=f"{idx}. {truncate(track.title)}",
                value=f"Requested by: {track.requested_by_name or 'Unknown'}",
                inline=False,
            )

        if queue_info.total_duration:
            embed.set_footer(text=f"Total duration: {format_duration(queue_info.total_duration)}")

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="current", description="Show the current track.")
    async def current(self, interaction: discord.Interaction) -> None:
        if not await self._ensure_user_in_voice_and_warm(interaction):
            return

        assert interaction.guild is not None

        queue_service = self.container.queue_service
        queue_info = await queue_service.get_queue(interaction.guild.id)

        if not queue_info.current_track:
            await interaction.response.send_message(
                DiscordUIMessages.STATE_NOTHING_PLAYING, ephemeral=True
            )
            return

        track = queue_info.current_track

        embed = discord.Embed(
            title=DiscordUIMessages.EMBED_NOW_PLAYING,
            description=f"**{track.title}**",
            color=discord.Color.green(),
        )

        if track.thumbnail_url:
            embed.set_thumbnail(url=track.thumbnail_url)

        embed.add_field(
            name="⏱️ Duration", value=format_duration(track.duration_seconds), inline=True
        )

        embed.add_field(
            name="👤 Requested by", value=track.requested_by_name or "Unknown", inline=True
        )

        from ..views.download_view import DownloadView

        view = DownloadView(
            webpage_url=track.webpage_url,
            title=track.title,
        )

        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @app_commands.command(name="shuffle", description="Shuffle the queue.")
    async def shuffle(self, interaction: discord.Interaction) -> None:
        if not await self._ensure_user_in_voice_and_warm(interaction):
            return

        assert interaction.guild is not None

        queue_service = self.container.queue_service
        shuffled = await queue_service.shuffle(interaction.guild.id)

        if shuffled:
            await interaction.response.send_message(
                DiscordUIMessages.ACTION_SHUFFLED, ephemeral=True
            )
        else:
            await interaction.response.send_message(
                DiscordUIMessages.STATE_NOT_ENOUGH_TRACKS_TO_SHUFFLE, ephemeral=True
            )

    @app_commands.command(name="loop", description="Toggle loop mode.")
    async def loop(self, interaction: discord.Interaction) -> None:
        if not await self._ensure_user_in_voice_and_warm(interaction):
            return

        assert interaction.guild is not None

        queue_service = self.container.queue_service
        mode = await queue_service.toggle_loop(interaction.guild.id)

        match mode:
            case LoopMode.OFF:
                emoji = "➡️"
            case LoopMode.TRACK:
                emoji = "🔂"
            case LoopMode.QUEUE:
                emoji = "🔁"
            case _:
                emoji = "➡️"

        await interaction.response.send_message(
            DiscordUIMessages.ACTION_LOOP_MODE_CHANGED.format(emoji=emoji, mode=mode.value),
            ephemeral=True,
        )

    @app_commands.command(name="remove", description="Remove a track from the queue.")
    @app_commands.describe(position="Position in queue (1-based)")
    async def remove(self, interaction: discord.Interaction, position: int) -> None:
        if not await self._ensure_user_in_voice_and_warm(interaction):
            return

        assert interaction.guild is not None

        if position < 1:
            await interaction.response.send_message(
                DiscordUIMessages.ERROR_POSITION_MUST_BE_POSITIVE, ephemeral=True
            )
            return

        queue_service = self.container.queue_service
        track = await queue_service.remove(interaction.guild.id, position - 1)

        if track:
            await interaction.response.send_message(
                DiscordUIMessages.ACTION_TRACK_REMOVED.format(track_title=track.title),
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                DiscordUIMessages.ERROR_NO_TRACK_AT_POSITION.format(position=position),
                ephemeral=True,
            )

    @app_commands.command(name="clear", description="Clear the queue.")
    async def clear(self, interaction: discord.Interaction) -> None:
        if not await self._ensure_user_in_voice_and_warm(interaction):
            return

        assert interaction.guild is not None

        queue_service = self.container.queue_service
        count = await queue_service.clear(interaction.guild.id)

        if count > 0:
            self._reset_message_state(interaction.guild.id)
            await interaction.response.send_message(
                DiscordUIMessages.ACTION_QUEUE_CLEARED.format(count=count), ephemeral=True
            )
        else:
            await interaction.response.send_message(
                DiscordUIMessages.STATE_QUEUE_ALREADY_EMPTY, ephemeral=True
            )

    @app_commands.command(
        name="radio",
        description="Toggle AI radio — auto-queue similar songs.",
    )
    async def radio(self, interaction: discord.Interaction) -> None:
        if not await self._ensure_user_in_voice_and_warm(interaction):
            return

        assert interaction.guild is not None

        await interaction.response.defer(ephemeral=True)

        user = interaction.user
        radio_service = self.container.radio_service

        result = await radio_service.toggle_radio(
            guild_id=interaction.guild.id,
            user_id=user.id,
            user_name=getattr(user, "display_name", user.name),
        )

        if result.enabled:
            msg = DiscordUIMessages.RADIO_ENABLED.format(
                count=result.tracks_added,
                seed_title=result.seed_title,
            )
        elif result.message:
            msg = f"{DiscordUIMessages.RADIO_DISABLED} {result.message}"
        else:
            msg = DiscordUIMessages.RADIO_DISABLED

        await interaction.followup.send(msg, ephemeral=True)

    @app_commands.command(name="leave", description="Disconnect from voice channel.")
    async def leave(self, interaction: discord.Interaction) -> None:
        if not await self._ensure_user_in_voice_and_warm(interaction):
            return

        assert interaction.guild is not None

        voice_adapter = self.container.voice_adapter
        playback_service = self.container.playback_service

        self.container.radio_service.disable_radio(interaction.guild.id)
        await playback_service.cleanup_guild(interaction.guild.id)
        self._reset_message_state(interaction.guild.id)
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
        raise RuntimeError("Container not found on bot instance")

    await bot.add_cog(MusicCog(bot, container))
