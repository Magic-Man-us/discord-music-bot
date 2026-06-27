"""A single voter's private Accept/Reject panel for a long-track vote.

Each voter gets their own ephemeral instance. Buttons mutate the parent's
shared tally; per-user button state (grey out the chosen option, relabel the
other to "Change my vote") works here because the message is ephemeral to one
voter — it cannot be done on the shared public message.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord

from ....domain.shared.constants import LimitConstants
from ..guards.voice_guards import check_user_in_voice
from .long_track_vote_view import VoteChoice

if TYPE_CHECKING:
    from .long_track_vote_view import LongTrackVoteView


class PersonalVotePanel(discord.ui.View):
    def __init__(self, *, parent: LongTrackVoteView, user_id: int) -> None:
        super().__init__(timeout=LimitConstants.LONG_TRACK_VOTE_TIMEOUT_SECONDS)
        self._parent = parent
        self._user_id = user_id
        self._sync()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await check_user_in_voice(interaction, self._parent._guild_id)

    def panel_text(self) -> str:
        match self._parent.vote_of(self._user_id):
            case VoteChoice.ACCEPT:
                return "You voted: ✅ Accept"
            case VoteChoice.REJECT:
                return "You voted: ❌ Reject"
            case None:
                return "Cast your vote on the long track:"

    def _sync(self) -> None:
        """Grey out the voter's current pick and relabel the other to 'Change my vote'."""
        match self._parent.vote_of(self._user_id):
            case VoteChoice.ACCEPT:
                self.accept_action.label = "✅ Accepted"
                self.accept_action.disabled = True
                self.accept_action.style = discord.ButtonStyle.green
                self.reject_action.label = "Change my vote"
                self.reject_action.disabled = False
                self.reject_action.style = discord.ButtonStyle.secondary
            case VoteChoice.REJECT:
                self.reject_action.label = "❌ Rejected"
                self.reject_action.disabled = True
                self.reject_action.style = discord.ButtonStyle.red
                self.accept_action.label = "Change my vote"
                self.accept_action.disabled = False
                self.accept_action.style = discord.ButtonStyle.secondary
            case None:
                self.accept_action.label = "Accept"
                self.accept_action.disabled = False
                self.accept_action.style = discord.ButtonStyle.green
                self.reject_action.label = "Reject"
                self.reject_action.disabled = False
                self.reject_action.style = discord.ButtonStyle.red

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.green)
    async def accept_action(
        self, interaction: discord.Interaction, _button: discord.ui.Button[PersonalVotePanel]
    ) -> None:
        self._parent.record_accept(self._user_id)
        self._sync()
        await interaction.response.edit_message(content=self.panel_text(), view=self)
        await self._parent.refresh_tally()

    @discord.ui.button(label="Reject", style=discord.ButtonStyle.red)
    async def reject_action(
        self, interaction: discord.Interaction, _button: discord.ui.Button[PersonalVotePanel]
    ) -> None:
        self._parent.record_reject(self._user_id)
        self._sync()
        await interaction.response.edit_message(content=self.panel_text(), view=self)
        await self._parent.refresh_tally()
