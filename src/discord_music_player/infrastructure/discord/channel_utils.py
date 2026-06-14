"""Helpers for resolving Discord channels to a usable form."""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord

from ...domain.shared.types import DiscordSnowflake

if TYPE_CHECKING:
    from discord.ext import commands


def resolve_messageable(
    bot: commands.Bot, channel_id: DiscordSnowflake
) -> discord.abc.Messageable | None:
    """Return the cached channel for ``channel_id`` if it can receive messages, else ``None``."""
    channel = bot.get_channel(channel_id)
    if channel is None or not isinstance(channel, discord.abc.Messageable):
        return None
    return channel
