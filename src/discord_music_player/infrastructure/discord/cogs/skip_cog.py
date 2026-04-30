"""Slash-command cog for skip (vote and force) functionality."""

from __future__ import annotations

import discord
from discord import app_commands

from ..guards.voice_guards import (
    can_force_skip,
    ensure_user_in_voice_and_warm,
    send_ephemeral,
)
from .base_cog import BaseCog


class SkipCog(BaseCog):
    @app_commands.command(
        name="skip", description="Vote to skip the current track, or force-skip if you're an admin."
    )
    @app_commands.guild_only()
    @app_commands.describe(force="Force skip (admin only)")
    async def skip(self, interaction: discord.Interaction, force: bool = False) -> None:
        # Defer immediately so downstream Discord API calls (get_listeners, skip_track)
        # can't blow past the 3s interaction-token deadline (was producing 10062 errors).
        await interaction.response.defer(ephemeral=True)

        if not await ensure_user_in_voice_and_warm(
            interaction, self.container.voice_warmup_tracker
        ):
            return

        # The voice guard already enforces guild + Member + member.voice.channel.
        assert interaction.guild is not None
        assert isinstance(interaction.user, discord.Member)
        user = interaction.user

        if force:
            if not can_force_skip(user, self.container.settings.discord.owner_ids):
                await send_ephemeral(interaction, "Force skip requires administrator permission.")
                return
            await self._handle_force_skip(interaction, user)
        else:
            await self._handle_vote_skip(interaction, user)

    async def _handle_force_skip(
        self, interaction: discord.Interaction, user: discord.Member
    ) -> None:
        assert interaction.guild is not None

        playback_service = self.container.playback_service
        track = await playback_service.skip_track(interaction.guild.id)

        if track:
            await interaction.followup.send(
                f"Force skipped: **{track.title}**",
                ephemeral=True,
            )
        else:
            await interaction.followup.send("Nothing is playing.", ephemeral=True)

    async def _handle_vote_skip(
        self, interaction: discord.Interaction, user: discord.Member
    ) -> None:
        # Guard guarantees guild + member-in-voice; trust the invariant here.
        assert interaction.guild is not None
        assert user.voice is not None and user.voice.channel is not None

        from ....application.commands.vote_skip import VoteSkipCommand

        command = VoteSkipCommand(
            guild_id=interaction.guild.id,
            user_id=user.id,
            user_channel_id=user.voice.channel.id,
        )

        handler = self.container.vote_skip_handler
        result = await handler.handle(command)

        if result.action_executed:
            skipped_track = await self.container.playback_service.skip_track(interaction.guild.id)
            if skipped_track is None:
                # Track ended between the vote check and the skip execution.
                msg = "Nothing is playing."
            else:
                msg = result.format_display(skipped_track.title)
        else:
            msg = result.message

        await interaction.followup.send(msg, ephemeral=True)


setup = SkipCog.setup
