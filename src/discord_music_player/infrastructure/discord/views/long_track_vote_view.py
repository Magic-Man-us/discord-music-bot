"""View for voting on whether to accept long tracks (>6 minutes) into the queue."""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord

from ....application.services.queue_models import EnqueueOk
from ....domain.shared.constants import LimitConstants, UIConstants
from ....domain.shared.types import DiscordSnowflake
from ....domain.voting.services import VotingDomainService
from ....utils.logging import get_logger
from ....utils.reply import format_duration, truncate
from ..guards.voice_guards import check_user_in_voice
from .base_view import BaseInteractiveView

if TYPE_CHECKING:
    from ....config.container import Container
    from ....domain.music.entities import Track

logger = get_logger(__name__)


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
        super().__init__(timeout=LimitConstants.LONG_TRACK_VOTE_TIMEOUT_SECONDS)
        self._guild_id: DiscordSnowflake = guild_id
        self._track: Track = track
        self._requester_id: DiscordSnowflake = requester_id
        self._requester_name: str = requester_name
        self._container: Container = container
        self._votes_accept: set[int] = set()
        self._votes_reject: set[int] = set()

    def _track_line(self) -> str:
        return f"[{truncate(self._track.title, UIConstants.TITLE_TRUNCATION)}]({self._track.webpage_url})"

    def build_vote_embed(
        self, accept_count: int, reject_count: int, threshold: int, listener_count: int
    ) -> discord.Embed:
        """Build the live vote embed showing the running tally and what's needed to pass."""
        reject_needed = max(1, listener_count - threshold + 1)
        embed = discord.Embed(
            title="Long Track Vote",
            description=(
                f"{self._track_line()}\n"
                f"Requested by: <@{self._requester_id}>"
            ),
            color=discord.Color.blurple(),
        )
        if self._track.thumbnail_url:
            embed.set_thumbnail(url=self._track.thumbnail_url)
        embed.add_field(
            name="Duration", value=format_duration(self._track.duration_seconds), inline=True
        )
        embed.add_field(name="✅ Accept", value=f"**{accept_count}/{threshold}**", inline=True)
        embed.add_field(name="❌ Reject", value=f"**{reject_count}/{reject_needed}**", inline=True)
        embed.set_footer(text=f"{listener_count} listening · majority decides")
        return embed

    def _result_embed(self, title: str, color: discord.Color) -> discord.Embed:
        return discord.Embed(title=title, description=self._track_line(), color=color)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await check_user_in_voice(interaction, self._guild_id)

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.green)
    async def accept_button(
        self, interaction: discord.Interaction, _button: discord.ui.Button[LongTrackVoteView]
    ) -> None:
        user_id = interaction.user.id

        self._votes_reject.discard(user_id)
        self._votes_accept.add(user_id)

        await interaction.response.send_message("✅ Counted your vote to **accept**.", ephemeral=True)
        await self._check_vote_result()

    @discord.ui.button(label="Reject", style=discord.ButtonStyle.red)
    async def reject_button(
        self, interaction: discord.Interaction, _button: discord.ui.Button[LongTrackVoteView]
    ) -> None:
        user_id = interaction.user.id

        self._votes_accept.discard(user_id)
        self._votes_reject.add(user_id)

        await interaction.response.send_message("❌ Counted your vote to **reject**.", ephemeral=True)
        await self._check_vote_result()

    async def _check_vote_result(self) -> None:
        """Tally live votes, refresh the embed, and resolve if a threshold is crossed."""
        voice_adapter = self._container.voice_adapter
        listeners = await voice_adapter.get_listeners(self._guild_id)
        listener_count = len(listeners)

        threshold = VotingDomainService.calculate_threshold(listener_count)

        listener_ids = set(listeners)
        accept_count = len(self._votes_accept & listener_ids)
        reject_count = len(self._votes_reject & listener_ids)

        if accept_count >= threshold:
            await self._accept_track()
            return
        if reject_count > listener_count - threshold:
            await self._reject_track()
            return

        if self._message:
            await self._message.edit(
                embed=self.build_vote_embed(
                    accept_count, reject_count, threshold, listener_count
                ),
                view=self,
            )

    async def _accept_track(self) -> None:
        """Accept the track into the queue."""
        if not self._finish_view():
            return

        queue_service = self._container.queue_service
        playback_service = self._container.playback_service

        result = await queue_service.enqueue(
            guild_id=self._guild_id,
            track=self._track.model_copy(update={"is_direct_request": True}),
            user_id=self._requester_id,
            user_name=self._requester_name,
        )

        if isinstance(result, EnqueueOk) and result.should_start:
            await playback_service.start_playback(self._guild_id)

        # Vote passed: drop the vote message. Now Playing posts itself when the
        # track starts; if it only queued, the prompt simply clears.
        await self._delete_message()

    async def _reject_track(self) -> None:
        """Reject the track."""
        if not self._finish_view():
            return

        if self._message:
            await self._message.edit(
                embed=self._result_embed("Vote failed — rejected", discord.Color.red()),
                view=self,
            )

    async def on_timeout(self) -> None:
        if not self._finish_view():
            return
        if self._message:
            await self._message.edit(
                embed=self._result_embed(
                    "Vote expired — not enough votes", discord.Color.greyple()
                ),
                view=self,
            )
        await self._delete_message(delay=10.0)
