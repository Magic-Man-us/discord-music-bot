"""Reusable voice-channel guard functions for Discord slash commands.

These are free functions that accept explicit dependencies rather than relying
on a specific cog instance, making them usable from any cog.
"""

from __future__ import annotations

from collections.abc import Collection
from typing import TYPE_CHECKING

import discord

from discord_music_player.domain.shared.constants import UIConstants
from discord_music_player.domain.shared.types import DiscordSnowflake

if TYPE_CHECKING:
    from ....application.interfaces.voice_adapter import VoiceAdapter
    from ....infrastructure.discord.services.voice_warmup import VoiceWarmupTracker


async def send_ephemeral(interaction: discord.Interaction, message: str) -> None:
    """Send an ephemeral message, handling both fresh and already-responded interactions."""
    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=True)
    else:
        await interaction.response.send_message(message, ephemeral=True)


async def get_member(interaction: discord.Interaction) -> discord.Member | None:
    """Validate that the interaction comes from a guild member. Returns None with error on failure."""
    if not interaction.guild:
        await send_ephemeral(interaction, "This command can only be used in a server.")
        return None

    user = interaction.user
    if not isinstance(user, discord.Member):
        await send_ephemeral(interaction, "Could not verify your voice state.")
        return None

    return user


async def ensure_voice_warmup(
    interaction: discord.Interaction,
    member: discord.Member,
    voice_warmup_tracker: VoiceWarmupTracker,
) -> bool:
    """Check if the member has passed the voice warmup period. Returns False with error on failure."""
    if not interaction.guild:
        return False

    remaining = voice_warmup_tracker.remaining_seconds(
        guild_id=interaction.guild.id,
        user_id=member.id,
    )
    if remaining <= 0:
        return True

    await send_ephemeral(
        interaction,
        f"You must be in the voice channel for {remaining}s before you can use commands.",
    )
    return False


async def ensure_user_in_voice_and_warm(
    interaction: discord.Interaction,
    voice_warmup_tracker: VoiceWarmupTracker,
) -> bool:
    """Check that the user is in a voice channel and has passed warmup. No bot connection."""
    member = await get_member(interaction)
    if member is None:
        return False

    if not member.voice or not member.voice.channel:
        await send_ephemeral(interaction, UIConstants.NOT_IN_VOICE)
        return False

    return await ensure_voice_warmup(interaction, member, voice_warmup_tracker)


async def ensure_voice(
    interaction: discord.Interaction,
    voice_warmup_tracker: VoiceWarmupTracker,
    voice_adapter: VoiceAdapter,
) -> bool:
    """Check user is in voice, passed warmup, and connect the bot if needed."""
    member = await get_member(interaction)
    if member is None:
        return False

    assert interaction.guild is not None

    if not member.voice or not member.voice.channel:
        await send_ephemeral(interaction, UIConstants.NOT_IN_VOICE)
        return False

    if not await ensure_voice_warmup(interaction, member, voice_warmup_tracker):
        return False

    channel_id = member.voice.channel.id

    if not voice_adapter.is_connected(interaction.guild.id):
        success = await voice_adapter.ensure_connected(interaction.guild.id, channel_id)
        if not success:
            await send_ephemeral(interaction, "I couldn't join your voice channel.")
            return False

    return True


async def check_user_in_voice(
    interaction: discord.Interaction, guild_id: DiscordSnowflake
) -> bool:
    """Return True if the interacting user is in the bot's voice channel.

    Sends an ephemeral rejection and returns False otherwise.
    Used as an ``interaction_check`` in views that require voice presence.
    """
    user = interaction.user
    if not isinstance(user, discord.Member):
        await interaction.response.send_message(
            "Could not verify your voice state.", ephemeral=True
        )
        return False

    if not user.voice or not user.voice.channel:
        await interaction.response.send_message(
            UIConstants.NOT_IN_VOICE, ephemeral=True
        )
        return False

    guild = interaction.client.get_guild(guild_id)
    if guild and guild.voice_client and guild.voice_client.channel:
        bot_channel = guild.voice_client.channel
        # voice_client.channel is typed as Connectable in discord.py stubs,
        # but at runtime it's always VoiceChannel/StageChannel which have .id
        if isinstance(bot_channel, discord.abc.GuildChannel) and user.voice.channel.id != bot_channel.id:
            await interaction.response.send_message(
                "You must be in a voice channel to use this command!", ephemeral=True
            )
            return False

    return True


def can_force_skip(user: discord.Member, owner_ids: Collection[int]) -> bool:
    """Check if the user is an admin or bot owner."""
    is_admin = user.guild_permissions.administrator
    is_owner = user.id in owner_ids
    return is_admin or is_owner
