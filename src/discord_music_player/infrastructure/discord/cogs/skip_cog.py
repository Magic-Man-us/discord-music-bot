"""Slash-command cog for skip (vote and force) functionality."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from discord_music_player.domain.shared.messages import DiscordUIMessages
from discord_music_player.domain.voting.value_objects import VoteResult
from discord_music_player.infrastructure.discord.guards.voice_guards import (
    can_force_skip,
    ensure_user_in_voice_and_warm,
    send_ephemeral,
)

if TYPE_CHECKING:
    from ....application.commands.vote_skip import VoteSkipResult
    from ....config.container import Container

logger = logging.getLogger(__name__)


class SkipCog(commands.Cog):
    def __init__(self, bot: commands.Bot, container: Container) -> None:
        self.bot = bot
        self.container = container

    @app_commands.command(name="skip", description="Vote to skip the current track.")
    @app_commands.describe(force="Force skip (admin only)")
    async def skip(self, interaction: discord.Interaction, force: bool = False) -> None:
        if not await ensure_user_in_voice_and_warm(
            interaction, self.container.voice_warmup_tracker
        ):
            return

        assert interaction.guild is not None

        user = interaction.user
        if not isinstance(user, discord.Member):
            await send_ephemeral(
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
        if not can_force_skip(user, self.container.settings.discord.owner_ids):
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


async def setup(bot: commands.Bot) -> None:
    container = getattr(bot, "container", None)
    if container is None:
        raise RuntimeError("Container not found on bot instance")

    await bot.add_cog(SkipCog(bot, container))
