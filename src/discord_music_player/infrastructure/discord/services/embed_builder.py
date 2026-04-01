"""Stateless helpers for building Discord embeds and one-liner messages."""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord

from discord_music_player.domain.shared.constants import UIConstants
from discord_music_player.utils.reply import format_duration, truncate

if TYPE_CHECKING:
    from ....domain.music.entities import Track


def format_requester(track: Track) -> str:
    if track.requested_by_id:
        return f"<@{track.requested_by_id}>"
    if track.requested_by_name:
        return track.requested_by_name
    return "Unknown"


def format_queued_line(track: Track) -> str:
    requester = format_requester(track)
    title = truncate(track.title, 80)
    return f"Queued for play: **{title}** — {requester}"


def format_finished_line(track: Track) -> str:
    title = truncate(track.title, 80)
    return f"Finished playing: **{title}**"


def build_now_playing_embed(track: Track, *, next_track: Track | None = None) -> discord.Embed:
    requester_display = format_requester(track)
    artist_or_uploader = track.artist or track.uploader
    likes_display = f"{track.like_count:,}" if track.like_count is not None else None

    description_lines = [f"[{track.title}]({track.webpage_url})"]
    description_lines.append(f"Requested by: {requester_display}")

    embed = discord.Embed(
        title="Now Playing",
        description="\n".join(description_lines),
        color=discord.Color.green(),
    )

    if track.thumbnail_url:
        embed.set_thumbnail(url=track.thumbnail_url)

    embed.add_field(
        name="Duration",
        value=format_duration(track.duration_seconds),
        inline=True,
    )

    if artist_or_uploader:
        embed.add_field(
            name="Artist",
            value=truncate(artist_or_uploader, 64),
            inline=True,
        )

    if likes_display:
        embed.add_field(
            name="Likes",
            value=likes_display,
            inline=True,
        )

    if next_track:
        embed.add_field(
            name="Next Up",
            value=truncate(next_track.title, 60),
            inline=False,
        )
    else:
        embed.add_field(
            name="Next Up",
            value=UIConstants.NEXT_UP_NONE,
            inline=False,
        )

    return embed
