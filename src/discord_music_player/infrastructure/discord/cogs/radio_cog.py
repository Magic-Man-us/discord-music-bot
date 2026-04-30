"""Slash-command cog for AI radio functionality."""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from ....domain.shared.constants import LimitConstants
from ....domain.shared.enums import AutoDJAction, PlaymineAction, RadioAction
from ....domain.shared.events import RadioPoolExhausted, get_event_bus
from ..guards.voice_guards import (
    ensure_user_in_voice_and_warm,
    ensure_voice,
)
from .base_cog import BaseCog

if TYPE_CHECKING:
    from ....application.services.follow_mode import FollowMode
    from ....application.services.radio_models import RadioToggleResult
    from ....config.container import Container


class RadioCog(BaseCog):
    def __init__(self, bot: commands.Bot, container: Container) -> None:
        super().__init__(bot, container)
        self._bus = get_event_bus()
        self._subscribed = False

    async def cog_load(self) -> None:
        if not self._subscribed:
            self._bus.subscribe(RadioPoolExhausted, self._on_pool_exhausted)
            self._subscribed = True

    async def cog_unload(self) -> None:
        if self._subscribed:
            self._bus.unsubscribe(RadioPoolExhausted, self._on_pool_exhausted)
            self._subscribed = False

    async def _on_pool_exhausted(self, event: RadioPoolExhausted) -> None:
        """Send 'Continue Radio?' prompt to the channel where radio was started."""
        if event.channel_id is None:
            self.logger.warning("RadioPoolExhausted has no channel_id for guild %s", event.guild_id)
            return

        channel = self.bot.get_channel(event.channel_id)
        if channel is None or not isinstance(channel, discord.abc.Messageable):
            return

        from ..views.radio_continue_view import RadioContinueView, build_continue_embed

        state = self.container.radio_service.get_state(event.guild_id)
        tracks_consumed = state.tracks_consumed if state else event.tracks_generated

        embed = build_continue_embed(tracks_consumed)
        view = RadioContinueView(
            guild_id=event.guild_id,
            container=self.container,
        )
        msg = await channel.send(embed=embed, view=view)
        view.set_message(msg)

    @app_commands.command(
        name="radio",
        description="AI radio — auto-queues similar songs based on what's playing.",
    )
    @app_commands.guild_only()
    @app_commands.describe(
        action="Turn radio on or off (default: on)",
        count="How many songs to queue (skips the selection menu)",
        query="Seed with a specific song instead of what's currently playing",
    )
    @app_commands.choices(
        action=[
            app_commands.Choice(name=RadioAction.ON.value, value=RadioAction.ON),
            app_commands.Choice(name=RadioAction.OFF.value, value=RadioAction.OFF),
        ]
    )
    async def radio(
        self,
        interaction: discord.Interaction,
        action: app_commands.Choice[str] | None = None,
        count: app_commands.Range[int, 1, 10] | None = None,
        query: str | None = None,
    ) -> None:
        if not await ensure_user_in_voice_and_warm(
            interaction, self.container.voice_warmup_tracker
        ):
            return

        assert interaction.guild is not None

        radio_action = RadioAction(action.value) if action else RadioAction.ON
        if radio_action is RadioAction.OFF:
            await self._handle_clear(interaction)
            return

        if count is not None:
            await interaction.response.defer()
            await self.start_radio(interaction, count=count, query=query)
        else:
            await self._show_count_select(interaction, query)

    async def _handle_clear(self, interaction: discord.Interaction) -> None:
        """Disable radio and clear AI recommendations from the queue."""
        assert interaction.guild is not None
        await interaction.response.defer(ephemeral=True)

        self.container.radio_service.disable_radio(interaction.guild.id)
        count = await self.container.queue_service.clear_recommendations(interaction.guild.id)

        msg = (
            f"Radio disabled. Removed **{count}** AI recommendation(s) from the queue."
            if count > 0
            else "Radio disabled. No AI recommendations were in the queue."
        )
        await interaction.followup.send(msg, ephemeral=True)

    async def _show_count_select(
        self,
        interaction: discord.Interaction,
        query: str | None,
    ) -> None:
        """Show a select menu asking how many songs to queue."""
        assert interaction.guild is not None
        from ..views.radio_count_view import RadioCountView

        async def _start_radio_cb(
            inter: discord.Interaction, count: int, q: str | None
        ) -> None:
            await self.start_radio(inter, count=count, query=q)

        view = RadioCountView(
            guild_id=interaction.guild.id,
            container=self.container,
            query=query,
            start_radio=_start_radio_cb,
        )
        msg = await interaction.response.send_message(
            "How many songs should radio queue?",
            view=view,
            ephemeral=True,
        )
        if isinstance(msg, discord.InteractionMessage):
            view.set_message(msg)

    async def start_radio(
        self,
        interaction: discord.Interaction,
        *,
        count: int,
        query: str | None = None,
    ) -> None:
        """Start radio with a specific count. Called by both /radio and the count select view."""
        assert interaction.guild is not None
        guild_id = interaction.guild.id
        user = interaction.user

        if query:
            seeded = await self._seed_track(interaction, query)
            if not seeded:
                return

        result = await self.container.radio_service.toggle_radio(
            guild_id=guild_id,
            user_id=user.id,
            user_name=user.display_name,
            channel_id=interaction.channel_id,
            count=count,
        )

        if not result.enabled:
            msg = result.message or "Couldn't enable radio."
            await interaction.followup.send(msg, ephemeral=True)
            return

        await self._send_radio_enabled(interaction, result)

    async def _seed_track(
        self,
        interaction: discord.Interaction,
        query: str,
    ) -> bool:
        """Resolve and enqueue a seed track directly. Returns True on success."""
        assert interaction.guild is not None
        guild_id = interaction.guild.id

        if not await ensure_voice(
            interaction,
            self.container.voice_warmup_tracker,
            self.container.voice_adapter,
        ):
            return False

        track = await self.container.audio_resolver.resolve(query)
        if not track:
            await interaction.followup.send(f"Couldn't find a track for: {query}", ephemeral=True)
            return False

        result = await self.container.queue_service.enqueue(
            guild_id=guild_id,
            track=track.model_copy(update={"is_direct_request": True}),
            user_id=interaction.user.id,
            user_name=interaction.user.display_name,
        )

        if not result.success:
            await interaction.followup.send(result.message, ephemeral=True)
            return False

        if result.should_start:
            await self.container.playback_service.start_playback(guild_id)

        radio_service = self.container.radio_service
        if radio_service.is_enabled(guild_id):
            radio_service.disable_radio(guild_id)

        return True

    @app_commands.command(
        name="dj",
        description="Auto-DJ — when on, AI radio kicks in once the queue empties.",
    )
    @app_commands.guild_only()
    @app_commands.describe(action="Turn Auto-DJ on or off")
    @app_commands.choices(
        action=[
            app_commands.Choice(name=AutoDJAction.ON.value, value=AutoDJAction.ON),
            app_commands.Choice(name=AutoDJAction.OFF.value, value=AutoDJAction.OFF),
        ]
    )
    async def dj(
        self,
        interaction: discord.Interaction,
        action: app_commands.Choice[str],
    ) -> None:
        if not await ensure_user_in_voice_and_warm(
            interaction, self.container.voice_warmup_tracker
        ):
            return

        assert interaction.guild is not None
        auto_dj = self.container.auto_dj
        guild_id = interaction.guild.id

        if AutoDJAction(action.value) is AutoDJAction.OFF:
            auto_dj.disable(guild_id)
            await interaction.response.send_message("Auto-DJ disabled.", ephemeral=True)
            return

        if not await self.container.ai_client.is_available():
            await interaction.response.send_message(
                "Auto-DJ needs AI, but no AI provider is configured.",
                ephemeral=True,
            )
            return
        auto_dj.enable(guild_id)
        await interaction.response.send_message(
            "Auto-DJ enabled. I'll keep the music going once the queue empties.",
            ephemeral=True,
        )

    @app_commands.command(
        name="playmine",
        description="Mirror your live Spotify/Apple Music activity into the queue.",
    )
    @app_commands.guild_only()
    @app_commands.describe(action="Turn live mirror on or off")
    @app_commands.choices(
        action=[
            app_commands.Choice(name=PlaymineAction.ON.value, value=PlaymineAction.ON),
            app_commands.Choice(name=PlaymineAction.OFF.value, value=PlaymineAction.OFF),
        ]
    )
    async def playmine(
        self,
        interaction: discord.Interaction,
        action: app_commands.Choice[str],
    ) -> None:
        if not await ensure_user_in_voice_and_warm(
            interaction, self.container.voice_warmup_tracker
        ):
            return

        assert interaction.guild is not None
        follow_mode = self.container.follow_mode
        guild_id = interaction.guild.id

        if PlaymineAction(action.value) is PlaymineAction.OFF:
            follow_mode.disable(guild_id)
            await interaction.response.send_message(
                "Live mirror disabled.", ephemeral=True
            )
            return

        await self._handle_playmine_on(interaction, follow_mode)

    async def _handle_playmine_on(
        self,
        interaction: discord.Interaction,
        follow_mode: FollowMode,
    ) -> None:
        from ..services.activity import extract_listening_query

        assert interaction.guild is not None
        guild_id = interaction.guild.id
        user = interaction.user

        if not isinstance(user, discord.Member):
            await interaction.response.send_message(
                "Live mirror needs a Member context.", ephemeral=True
            )
            return

        seed_query = extract_listening_query(user)
        if seed_query is None:
            hint = ""
            if not interaction.client.intents.presences:
                hint = (
                    " *(bot's `presences` intent is OFF — check Developer "
                    "Portal + bot.py.)*"
                )
            await interaction.response.send_message(
                "I can't see what you're listening to. Make sure Spotify or "
                "Apple Music is open and **Activity Privacy → Display "
                f"current activity as a status message** is on.{hint}",
                ephemeral=True,
            )
            return

        follow_mode.enable(
            guild_id=guild_id, user_id=user.id, user_name=user.display_name
        )
        await interaction.response.defer(ephemeral=True)

        # Seed with whatever they're listening to right now so the user
        # doesn't have to switch tracks to kick things off.
        enqueued = await follow_mode.on_track_change(
            guild_id=guild_id, user_id=user.id, query=seed_query
        )
        cap = LimitConstants.MAX_FOLLOW_TRACKS
        if enqueued:
            await interaction.followup.send(
                f"Mirroring your listening. Up to **{cap}** tracks will queue, "
                f"then I'll auto-stop.",
                ephemeral=True,
            )
        else:
            await interaction.followup.send(
                f"Mirror started, but I couldn't resolve **{seed_query}** on "
                f"YouTube. The next track you switch to should pick up.",
                ephemeral=True,
            )

    async def _send_radio_enabled(
        self,
        interaction: discord.Interaction,
        result: RadioToggleResult,
    ) -> None:
        """Send the 'Up Next' embed with per-track re-roll buttons."""
        assert interaction.guild is not None
        from ..views.radio_view import RadioView, build_up_next_embed

        queue_info = await self.container.queue_service.get_queue(interaction.guild.id)
        queue_start = max(0, queue_info.total_tracks - len(result.generated_tracks))

        embed = build_up_next_embed(result.generated_tracks, result.seed_title)
        view = RadioView(
            guild_id=interaction.guild.id,
            container=self.container,
            tracks=result.generated_tracks,
            seed_title=result.seed_title,
            queue_start_position=queue_start,
        )
        msg = await interaction.followup.send(embed=embed, view=view, wait=True)
        view.set_message(msg)


setup = RadioCog.setup
