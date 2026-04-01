"""View for voting on whether to accept long tracks (>6 minutes) into the queue."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord

from ....domain.shared.types import DiscordSnowflake
from ..guards.voice_guards import check_user_in_voice
from .base_view import BaseInteractiveView
from ....utils.reply import format_duration, truncate

if TYPE_CHECKING:
    from ....config.container import Container
    from ....domain.music.entities import Track

logger = logging.getLogger(__name__)


class LongTrackVoteView(BaseInteractiveView):
    """Prompts for a vote to accept/reject a long track."""

    def __init__(
        self,
        *,
        guild_id: DiscordSnowflake,
        track: Track,
        requester_id: DiscordSnowflake,
        requester_name: str,
        container: Container,
    ) -> None:
        super().__init__(timeout=30.0)
        self._guild_id = guild_id
        self._track = track
        self._requester_id = requester_id
        self._requester_name = requester_name
        self._container = container
        self._votes_accept: set[int] = set()
        self._votes_reject: set[int] = set()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await check_user_in_voice(interaction, self._guild_id)

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.green)
    async def accept_button(
        self, interaction: discord.Interaction, _button: discord.ui.Button[LongTrackVoteView]
    ) -> None:
        user_id = interaction.user.id

        # Remove from reject if they voted reject before
        self._votes_reject.discard(user_id)
        self._votes_accept.add(user_id)

        await interaction.response.defer()
        await self._check_vote_result()

    @discord.ui.button(label="Reject", style=discord.ButtonStyle.red)
    async def reject_button(
        self, interaction: discord.Interaction, _button: discord.ui.Button[LongTrackVoteView]
    ) -> None:
        user_id = interaction.user.id

        # Remove from accept if they voted accept before
        self._votes_accept.discard(user_id)
        self._votes_reject.add(user_id)

        await interaction.response.defer()
        await self._check_vote_result()

    async def _check_vote_result(self) -> None:
        """Check if vote threshold is met."""
        # Get listener count from voice channel
        voice_adapter = self._container.voice_adapter
        listeners = await voice_adapter.get_listeners(self._guild_id)
        listener_count = len(listeners)

        # Calculate threshold (50% of listeners, min 1)
        from ....domain.voting.services import VotingDomainService

        threshold = VotingDomainService.calculate_threshold(listener_count)

        # Invalidate votes from users who left the voice channel
        listener_ids = set(listeners)
        active_accepts = self._votes_accept & listener_ids
        active_rejects = self._votes_reject & listener_ids
        accept_count = len(active_accepts)
        reject_count = len(active_rejects)

        # Check if accept threshold met
        if accept_count >= threshold:
            await self._accept_track()
        # Check if majority rejected (simplified - if more reject than could possibly accept)
        elif reject_count > listener_count - threshold:
            await self._reject_track()

    async def _accept_track(self) -> None:
        """Accept the track into the queue."""
        if not self._finish_view():
            return

        # Enqueue the track
        queue_service = self._container.queue_service
        playback_service = self._container.playback_service

        result = await queue_service.enqueue(
            guild_id=self._guild_id,
            track=self._track.model_copy(update={"is_direct_request": True}),
            user_id=self._requester_id,
            user_name=self._requester_name,
        )

        if result.success and result.should_start:
            await playback_service.start_playback(self._guild_id)

        if self._message:
            await self._message.edit(
                content=f"Vote passed! Queued: **{truncate(self._track.title, 60)}** ({format_duration(self._track.duration_seconds)})",
                view=self,
            )

    async def _reject_track(self) -> None:
        """Reject the track."""
        if not self._finish_view():
            return

        if self._message:
            await self._message.edit(
                content=f"Vote failed. Rejected: **{truncate(self._track.title, 60)}**",
                view=self,
            )

    async def on_timeout(self) -> None:
        if not self._finish_view():
            return
        await self._delete_message(delay=10.0)
