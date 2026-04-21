"""Slash-command cog for core playback: play, pause, resume, stop, leave."""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from ....domain.music.entities import Track
from ....domain.shared.constants import PlaylistConstants, UIConstants
from ....domain.shared.types import DiscordSnowflake, HttpUrlStr
from .base_cog import BaseCog
from ..guards.voice_guards import (
    ensure_dj_role,
    ensure_user_in_voice_and_warm,
    get_member,
    is_solo_in_channel,
    send_ephemeral,
)
from ..services.embed_builder import (
    build_now_playing_embed,
    format_queued_line,
)
from ....utils.reply import (
    extract_youtube_timestamp,
    format_duration,
    parse_timestamp,
    truncate,
)

if TYPE_CHECKING:
    from ....config.container import Container
    from ....domain.music.wrappers import StartSeconds
    from ....domain.shared.events import TrackStartedPlaying
    from ..views.requester_left_view import RequesterLeftView


class PlaybackCog(BaseCog):
    def __init__(self, bot: commands.Bot, container: Container) -> None:
        super().__init__(bot, container)
        self._requester_left_views: dict[DiscordSnowflake, RequesterLeftView] = {}

    async def cog_load(self) -> None:
        self.container.playback_service.set_track_finished_callback(self._on_track_finished)
        auto_skip = self.container.auto_skip_on_requester_leave
        auto_skip.set_on_requester_left_callback(self._on_requester_left)
        auto_skip.set_on_requester_rejoined_callback(self._on_requester_rejoined)
        from ....domain.shared.events import TrackStartedPlaying, get_event_bus

        self._event_bus = get_event_bus()
        self._event_bus.subscribe(TrackStartedPlaying, self._on_track_started_auto_post)

    async def cog_unload(self) -> None:
        self.container.playback_service.set_track_finished_callback(None)
        auto_skip = self.container.auto_skip_on_requester_leave
        auto_skip.set_on_requester_left_callback(None)
        auto_skip.set_on_requester_rejoined_callback(None)
        self.container.message_state_manager.clear_all()
        if hasattr(self, "_event_bus"):
            from ....domain.shared.events import TrackStartedPlaying

            self._event_bus.unsubscribe(TrackStartedPlaying, self._on_track_started_auto_post)

    # ─────────────────────────────────────────────────────────────────
    # Play
    # ─────────────────────────────────────────────────────────────────

    @app_commands.command(
        name="play", description="Play a song — paste a YouTube link or just type a song name."
    )
    @app_commands.guild_only()
    @app_commands.describe(
        query="YouTube URL or search query",
        timestamp='Start position (e.g. "1:30" or "90")',
        count="How many tracks to import from an Apple Music playlist/album (default 5, max 50)",
    )
    async def play(
        self,
        interaction: discord.Interaction,
        query: str,
        timestamp: str | None = None,
        count: app_commands.Range[int, 1, PlaylistConstants.MAX_PLAYLIST_TRACKS] | None = None,
    ) -> None:
        from ....domain.music.wrappers import StartSeconds

        raw_seconds: int | None = None
        if timestamp is not None:
            raw_seconds = parse_timestamp(timestamp)
            if raw_seconds is None:
                await interaction.response.send_message(
                    "Invalid timestamp format. Use `1:30`, `1:30:00`, or seconds like `90`.",
                    ephemeral=True,
                )
                return
        else:
            raw_seconds = extract_youtube_timestamp(query)

        seek = StartSeconds.from_optional(raw_seconds)

        await interaction.response.defer()
        await self._execute_play(interaction, query, start_seconds=seek, count=count)

    async def _ensure_voice_ready(
        self,
        interaction: discord.Interaction,
    ) -> discord.Member | None:
        """Validate voice state, warmup, and connection. Returns member or None on failure."""
        member = await get_member(interaction)
        if member is None:
            return None

        if not member.voice or not member.voice.channel:
            await send_ephemeral(interaction, "You need to be in a voice channel first.")
            return None

        if not interaction.guild:
            return None

        if not is_solo_in_channel(member):
            remaining = self.container.voice_warmup_tracker.remaining_seconds(
                guild_id=interaction.guild.id,
                user_id=member.id,
            )
            if remaining > 0:
                await send_ephemeral(
                    interaction,
                    f"You must be in the voice channel for {remaining}s before you can use commands.",
                )
                return None

        voice_adapter = self.container.voice_adapter
        if not voice_adapter.is_connected(interaction.guild.id):
            success = await voice_adapter.ensure_connected(
                interaction.guild.id, member.voice.channel.id
            )
            if not success:
                await send_ephemeral(interaction, "I couldn't join your voice channel.")
                return None

        return member

    async def _execute_play(
        self,
        interaction: discord.Interaction,
        query: str,
        *,
        start_seconds: StartSeconds | None = None,
        count: int | None = None,
    ) -> None:
        """Full play flow: voice checks, warmup with retry view, connect, play.

        Expects the interaction to already be deferred.
        """
        member = await get_member(interaction)
        if member is None:
            return

        if not member.voice or not member.voice.channel:
            await send_ephemeral(interaction, "You need to be in a voice channel first.")
            return

        if not interaction.guild:
            return

        if not is_solo_in_channel(member):
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
                    f"You must be in the voice channel for {remaining}s before you can use commands.",
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
                await send_ephemeral(interaction, "I couldn't join your voice channel.")
                return

        # Apple Music playlist / album → expand to N YouTube searches and
        # batch-enqueue. Spotify playlists stay unsupported for now.
        from ....utils.url_extractor import (
            is_apple_music_url,
            is_external_music_url,
            is_spotify_playlist_url,
        )

        if is_spotify_playlist_url(query):
            await send_ephemeral(
                interaction,
                "Spotify playlists aren't supported (no public scraping API). "
                "Paste individual track URLs or use a YouTube playlist link.",
            )
            return

        if is_apple_music_url(query):
            handled = await self._handle_apple_music_url(
                interaction, query, count_override=count
            )
            if handled:
                return
            # Not handled (e.g. song URL) → fall through to single-track search.

        if is_external_music_url(query):
            from ....utils.url_extractor import extract_search_query_from_url

            search_query = await extract_search_query_from_url(query)
            if search_query:
                self.logger.info("Resolved external URL to search query: %s", search_query)
                query = search_query
            else:
                await send_ephemeral(
                    interaction,
                    "Couldn't extract track info from that URL. Try pasting the song name instead.",
                )
                return

        # Detect playlist URLs and show selection UI
        resolver = self.container.audio_resolver
        if resolver.is_url(query) and resolver.is_playlist(query):
            await self._handle_playlist(interaction, query)
            return

        await self._play_track(interaction, query, start_seconds=start_seconds)

    async def _handle_apple_music_url(
        self,
        interaction: discord.Interaction,
        url: str,
        *,
        count_override: int | None,
    ) -> bool:
        """Expand an Apple Music playlist/album URL, enqueue up to
        ``count_override`` tracks (default: EXTERNAL_PLAYLIST_DEFAULT_COUNT,
        max: MAX_PLAYLIST_TRACKS). Returns True when handled as a multi-track
        resource; False when the caller should keep processing the URL as a
        single track (song or album?i=track)."""
        from ....infrastructure.audio.apple_music import (
            AppleMusicError,
            AppleResourceType,
            parse_apple_music_url,
        )

        assert interaction.guild is not None

        resource = parse_apple_music_url(url)
        if resource is None or resource.resource_type is AppleResourceType.SONG:
            return False

        try:
            all_queries = await self.container.apple_music_client.get_track_queries(url)
        except AppleMusicError as exc:
            self.logger.warning("Apple Music lookup failed for %s: %s", url, exc)
            await send_ephemeral(
                interaction,
                "Couldn't fetch that Apple Music playlist. "
                "Try again in a moment or paste individual song URLs.",
            )
            return True

        if not all_queries:
            await send_ephemeral(interaction, "That Apple Music playlist is empty.")
            return True

        requested = count_override or PlaylistConstants.EXTERNAL_PLAYLIST_DEFAULT_COUNT
        cap = min(requested, PlaylistConstants.MAX_PLAYLIST_TRACKS, len(all_queries))
        queries = all_queries[:cap]
        truncated = len(all_queries) - len(queries)

        source_label = f"Apple Music {resource.resource_type.value[:-1]}"
        self.logger.info(
            "Apple Music %s: enqueuing %d/%d tracks for guild %s",
            resource.resource_type.value,
            len(queries),
            len(all_queries),
            interaction.guild.id,
        )

        header = f"Queueing **{len(queries)}** of **{len(all_queries)}** tracks"
        if truncated > 0 and count_override is None:
            header += f" (default — pass `count:` to queue up to {PlaylistConstants.MAX_PLAYLIST_TRACKS})"
        await interaction.followup.send(
            f"{header} from {source_label}. Resolving on YouTube…",
            ephemeral=True,
        )

        tracks = await self.container.audio_resolver.resolve_many(queries)
        if not tracks:
            await interaction.followup.send(
                "Couldn't find any of those tracks on YouTube.",
                ephemeral=True,
            )
            return True

        result = await self.enqueue_and_start(interaction, tracks)
        await interaction.followup.send(
            f"Queued **{result.enqueued}/{len(queries)}** tracks from {source_label}.",
            ephemeral=True,
        )
        return True

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
            track = await self.container.audio_resolver.resolve(query)
            if not track:
                await interaction.followup.send(
                    f"Couldn't find a track for: {query}", ephemeral=True
                )
                return

            # Long track → community vote instead of direct enqueue
            if await self._start_long_track_vote(interaction, track):
                return

            result = await self.container.queue_service.enqueue(
                guild_id=interaction.guild.id,
                track=track.model_copy(update={"is_direct_request": True}),
                user_id=interaction.user.id,
                user_name=interaction.user.display_name,
            )

            if not result.success:
                await interaction.followup.send(result.message, ephemeral=True)
                return

            self.logger.info(
                "Enqueue result: position=%s, should_start=%s",
                result.position,
                result.should_start,
            )
            if result.should_start:
                self.logger.info("Calling start_playback for guild %s", interaction.guild.id)
                self.container.message_state_manager.reserve_now_playing(interaction.guild.id)
                await self.container.playback_service.start_playback(
                    interaction.guild.id, start_seconds=start_seconds
                )

            resolved_track = result.track or track

            if result.should_start:
                await self._send_now_playing(interaction, resolved_track)
            else:
                await self._send_queued(interaction, resolved_track)

        except Exception:
            self.logger.exception("Error in play command")
            await interaction.followup.send("Command failed. See logs.", ephemeral=True)

    async def _start_long_track_vote(
        self,
        interaction: discord.Interaction,
        track: Track,
    ) -> bool:
        """If the track exceeds the duration threshold and there are enough listeners,
        start a community vote. Returns True if a vote was initiated (caller should return)."""
        from ....domain.shared.constants import LimitConstants

        assert interaction.guild is not None

        if (
            not track.duration_seconds
            or track.duration_seconds <= LimitConstants.LONG_TRACK_THRESHOLD_SECONDS
        ):
            return False

        listeners = await self.container.voice_adapter.get_listeners(interaction.guild.id)
        if len(listeners) <= LimitConstants.LONG_TRACK_VOTE_BYPASS_LISTENERS:
            return False

        if not interaction.channel_id:
            await interaction.followup.send(
                "Cannot start vote: no channel context.", ephemeral=True
            )
            return True

        from ..views.long_track_vote_view import LongTrackVoteView

        user = interaction.user
        view = LongTrackVoteView(
            guild_id=interaction.guild.id,
            track=track,
            requester_id=user.id,
            requester_name=user.display_name,
            container=self.container,
        )

        channel = self.bot.get_channel(interaction.channel_id)
        if isinstance(channel, discord.abc.Messageable):
            vote_msg = await channel.send(
                f"**{user.display_name}** wants to queue a long track ({format_duration(track.duration_seconds)}): **{truncate(track.title, UIConstants.TITLE_TRUNCATION)}**\nVote to accept or reject:",
                view=view,
            )
            view.set_message(vote_msg)
            await interaction.followup.send(
                f"Started vote for long track: **{truncate(track.title, UIConstants.TITLE_TRUNCATION)}**",
                ephemeral=True,
            )
        else:
            await interaction.followup.send(
                "Could not find a channel to post the vote. Please try again.",
                ephemeral=True,
            )
        return True

    async def _send_now_playing(
        self,
        interaction: discord.Interaction,
        track: Track,
    ) -> None:
        """Send the Now Playing embed with interactive view."""
        assert interaction.guild is not None
        msm = self.container.message_state_manager
        guild_id = interaction.guild.id

        session = await self.container.session_repository.get(guild_id)
        upcoming = session.peek() if session else None

        embed = build_now_playing_embed(track, next_track=upcoming)

        from ..views.now_playing_view import NowPlayingView

        view = NowPlayingView(
            webpage_url=track.webpage_url,
            title=track.title,
            guild_id=guild_id,
            container=self.container,
        )
        sent = await interaction.followup.send(embed=embed, view=view, wait=True)
        view.set_message(sent)

        if interaction.channel_id is not None:
            msm.track_now_playing(
                guild_id=guild_id,
                track=track,
                channel_id=interaction.channel_id,
                message_id=sent.id,
            )

    async def _send_queued(
        self,
        interaction: discord.Interaction,
        track: Track,
    ) -> None:
        """Send the 'added to queue' message and update the Now Playing embed."""
        assert interaction.guild is not None
        msm = self.container.message_state_manager
        guild_id = interaction.guild.id

        content = format_queued_line(track)
        sent = await interaction.followup.send(
            content=content,
            wait=True,
        )
        if sent is not None:
            await sent.delete(delay=UIConstants.QUEUED_DELETE_AFTER)

            if interaction.channel_id is not None:
                msm.track_queued(
                    guild_id=guild_id,
                    track=track,
                    channel_id=interaction.channel_id,
                    message_id=sent.id,
                )

        session = await self.container.session_repository.get(guild_id)
        upcoming = session.peek() if session else None
        await msm.update_next_up(guild_id, upcoming)

    # ─────────────────────────────────────────────────────────────────
    # Seek
    # ─────────────────────────────────────────────────────────────────

    @app_commands.command(
        name="seek", description="Jump to a specific time in the current track (e.g. 1:30)."
    )
    @app_commands.guild_only()
    @app_commands.describe(timestamp='Position (e.g. "1:30", "1:30:00", or seconds like "90")')
    async def seek(self, interaction: discord.Interaction, timestamp: str) -> None:
        if not await ensure_user_in_voice_and_warm(
            interaction, self.container.voice_warmup_tracker
        ):
            return

        assert interaction.guild is not None

        raw_seconds = parse_timestamp(timestamp)
        if raw_seconds is None:
            await interaction.response.send_message(
                "Invalid timestamp format. Use `1:30`, `1:30:00`, or seconds like `90`.",
                ephemeral=True,
            )
            return

        from ....domain.music.wrappers import StartSeconds

        seek = StartSeconds.from_optional(raw_seconds)
        if seek is None:
            await interaction.response.send_message(
                "Timestamp must be greater than 0.", ephemeral=True
            )
            return

        playback_service = self.container.playback_service
        success = await playback_service.seek_playback(interaction.guild.id, start_seconds=seek)

        if success:
            await interaction.response.send_message(
                f"Seeked to **{format_duration(raw_seconds)}**.", ephemeral=True
            )
        else:
            await interaction.response.send_message("Nothing is playing to seek.", ephemeral=True)

    # ─────────────────────────────────────────────────────────────────
    # Play Next
    # ─────────────────────────────────────────────────────────────────

    @app_commands.command(
        name="playnext", description="Add a song that plays right after the current one."
    )
    @app_commands.guild_only()
    @app_commands.describe(query="YouTube URL or search query")
    async def playnext(self, interaction: discord.Interaction, query: str) -> None:
        await interaction.response.defer()
        await self._execute_playnext(interaction, query)

    async def _execute_playnext(self, interaction: discord.Interaction, query: str) -> None:
        member = await self._ensure_voice_ready(interaction)
        if member is None or interaction.guild is None:
            return

        try:
            track = await self.container.audio_resolver.resolve(query)
            if not track:
                await interaction.followup.send(
                    f"Couldn't find a track for: {query}", ephemeral=True
                )
                return

            result = await self.container.queue_service.enqueue_next(
                guild_id=interaction.guild.id,
                track=track.model_copy(update={"is_direct_request": True}),
                user_id=interaction.user.id,
                user_name=interaction.user.display_name,
            )

            if not result.success:
                await interaction.followup.send(result.message, ephemeral=True)
                return

            resolved_track = result.track or track
            title = truncate(resolved_track.title, UIConstants.TITLE_TRUNCATION)
            sent = await interaction.followup.send(f"Up next: **{title}**", wait=True)
            if sent is not None:
                await sent.delete(delay=UIConstants.QUEUED_DELETE_AFTER)

        except Exception:
            self.logger.exception("Error in playnext command")
            await interaction.followup.send("Command failed. See logs.", ephemeral=True)

    # ─────────────────────────────────────────────────────────────────
    # Playlist
    # ─────────────────────────────────────────────────────────────────

    async def _handle_playlist(self, interaction: discord.Interaction, url: HttpUrlStr) -> None:
        """Extract playlist entries and show selection UI."""
        resolver = self.container.audio_resolver
        entries = await resolver.preview_playlist(url)

        if not entries:
            await interaction.followup.send("That playlist appears to be empty.", ephemeral=True)
            return

        from ..views.playlist_view import PlaylistView, build_playlist_embed

        embed = build_playlist_embed(entries)
        view = PlaylistView(
            entries=entries,
            interaction=interaction,
            container=self.container,
        )
        msg = await interaction.followup.send(embed=embed, view=view, wait=True)
        view.set_message(msg)

    # ─────────────────────────────────────────────────────────────────
    # Callbacks
    # ─────────────────────────────────────────────────────────────────

    async def _on_track_started_auto_post(self, event: TrackStartedPlaying) -> None:
        """Auto-post a now-playing embed when no existing message is being tracked."""
        guild_id = event.guild_id
        msm = self.container.message_state_manager
        state = msm.get_state(guild_id)

        # If there's already a tracked now-playing message (or one is about to be sent
        # by the /play command), skip to avoid duplicate embeds
        if state.now_playing is not None or state.now_playing_reserved:
            return

        # Use event payload directly to avoid stale DB reads under rapid track changes
        if event.track_title is None or event.track_url is None:
            return

        session = await self.container.session_repository.get(guild_id)
        if session is None or session.current_track is None:
            return

        track = session.current_track
        upcoming = session.peek() if session else None

        # Verify the session's current track matches the event to avoid posting
        # an embed for the wrong track under rapid skips
        if track.title != event.track_title:
            return

        # Find the best text channel to post in
        channel = self._find_auto_post_channel(guild_id)
        if channel is None:
            return

        embed = build_now_playing_embed(track, next_track=upcoming)

        from ..views.now_playing_view import NowPlayingView

        view = NowPlayingView(
            webpage_url=track.webpage_url,
            title=track.title,
            guild_id=guild_id,
            container=self.container,
        )

        try:
            sent = await channel.send(embed=embed, view=view)
            view.set_message(sent)
            msm.track_now_playing(
                guild_id=guild_id,
                track=track,
                channel_id=channel.id,
                message_id=sent.id,
            )
        except Exception:
            self.logger.debug("Failed to auto-post now-playing for guild %s", guild_id)

    def _find_auto_post_channel(self, guild_id: DiscordSnowflake) -> discord.TextChannel | None:
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            return None

        for candidate in self._auto_post_candidates(guild):
            if candidate.permissions_for(guild.me).send_messages:
                return candidate
        return None

    @staticmethod
    def _auto_post_candidates(guild: discord.Guild) -> list[discord.TextChannel]:
        """Yield candidate text channels in priority order: same category as voice > system > any."""
        candidates: list[discord.TextChannel] = []

        if guild.voice_client and guild.voice_client.channel:
            category = getattr(guild.voice_client.channel, "category", None)
            if category is not None:
                candidates.extend(category.text_channels)

        if guild.system_channel:
            candidates.append(guild.system_channel)

        candidates.extend(guild.text_channels)
        return candidates

    async def _on_requester_left(
        self, guild_id: DiscordSnowflake, user_id: DiscordSnowflake, track: Track
    ) -> None:
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
            self.logger.warning(
                "Could not find text channel for requester-left prompt in guild %s, auto-skipping",
                guild_id,
            )
            await self.container.playback_service.skip_track(guild_id)
            return

        requester_name = f"<@{user_id}>"
        view = RequesterLeftView(
            guild_id=guild_id,
            playback_service=self.container.playback_service,
            auto_skip_service=self.container.auto_skip_on_requester_leave,
            track_title=track.title,
            requester_name=requester_name,
        )
        content = f"**{requester_name}** has left the voice channel. Do you want to continue playing **{truncate(track.title, UIConstants.TITLE_TRUNCATION)}**?"
        message = await channel.send(content, view=view)
        view.set_message(message)
        self._requester_left_views[guild_id] = view

    async def _on_requester_rejoined(
        self, guild_id: DiscordSnowflake, user_id: DiscordSnowflake
    ) -> None:
        view = self._requester_left_views.pop(guild_id, None)
        if view is not None:
            await view.dismiss()

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

    @app_commands.command(name="stop", description="Stop the music and clear the entire queue.")
    @app_commands.guild_only()
    async def stop(self, interaction: discord.Interaction) -> None:
        if not await ensure_user_in_voice_and_warm(
            interaction, self.container.voice_warmup_tracker
        ):
            return

        if not await ensure_dj_role(interaction, self.container.settings.discord.dj_role_id):
            return

        assert interaction.guild is not None

        playback_service = self.container.playback_service
        queue_service = self.container.queue_service

        self.container.radio_service.disable_radio(interaction.guild.id)
        stopped = await playback_service.stop_playback(interaction.guild.id)
        cleared = await queue_service.clear(interaction.guild.id)

        if stopped or cleared > 0:
            await self.container.message_state_manager.reset(interaction.guild.id)
            await interaction.response.send_message(
                "Stopped playback and cleared the queue.", ephemeral=True
            )
        else:
            await interaction.response.send_message("Nothing is playing.", ephemeral=True)

    @app_commands.command(name="pause", description="Pause the current track.")
    @app_commands.guild_only()
    async def pause(self, interaction: discord.Interaction) -> None:
        if not await ensure_user_in_voice_and_warm(
            interaction, self.container.voice_warmup_tracker
        ):
            return

        assert interaction.guild is not None

        playback_service = self.container.playback_service
        paused = await playback_service.pause_playback(interaction.guild.id)

        if paused:
            await interaction.response.send_message("Paused playback.", ephemeral=True)
        else:
            await interaction.response.send_message(
                "Nothing is playing or already paused.", ephemeral=True
            )

    @app_commands.command(name="resume", description="Resume paused playback.")
    @app_commands.guild_only()
    async def resume(self, interaction: discord.Interaction) -> None:
        if not await ensure_user_in_voice_and_warm(
            interaction, self.container.voice_warmup_tracker
        ):
            return

        assert interaction.guild is not None

        playback_service = self.container.playback_service
        resumed = await playback_service.resume_playback(interaction.guild.id)

        if resumed:
            await interaction.response.send_message("Resumed playback.", ephemeral=True)
        else:
            await interaction.response.send_message("Nothing is paused.", ephemeral=True)

    # ─────────────────────────────────────────────────────────────────
    # Leave
    # ─────────────────────────────────────────────────────────────────

    @app_commands.command(name="leave", description="Disconnect the bot from the voice channel.")
    @app_commands.guild_only()
    async def leave(self, interaction: discord.Interaction) -> None:
        if not await ensure_user_in_voice_and_warm(
            interaction, self.container.voice_warmup_tracker
        ):
            return

        assert interaction.guild is not None

        voice_adapter = self.container.voice_adapter
        playback_service = self.container.playback_service

        self.container.radio_service.disable_radio(interaction.guild.id)
        was_connected = voice_adapter.is_connected(interaction.guild.id)
        await playback_service.cleanup_guild(interaction.guild.id)
        await self.container.message_state_manager.reset(interaction.guild.id)

        if was_connected:
            await interaction.response.send_message(
                "Disconnected from voice channel.", ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "Not connected to a voice channel.", ephemeral=True
            )


setup = PlaybackCog.setup
