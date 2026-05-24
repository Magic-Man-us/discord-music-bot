"""Helpers for Discord music activity and live mirror setup."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

import discord

from ....domain.shared.constants import LimitConstants
from ....domain.shared.types import FollowTrackCount, NonEmptyStr

if TYPE_CHECKING:
    from ....application.services.follow_mode import FollowMode

APPLE_MUSIC_APP_ID: Final[int] = 1066220978406953012
SPOTIFY_APP_ID: Final[int] = 463097721130188830


def _format_query(artist: str | None, title: str | None) -> NonEmptyStr | None:
    """Return a normalised ``"<artist> - <title>"`` query when both parts exist."""
    if not artist or not title:
        return None
    return f"{artist} - {title}"


def _extract_listening_payload(
    member: discord.Member | discord.User,
) -> tuple[str, NonEmptyStr] | None:
    """Return ``(source_label, query)`` for the first supported listening activity."""
    if not isinstance(member, discord.Member):
        return None

    for act in member.activities:
        if isinstance(act, discord.Spotify):
            query = _format_query(act.artist, act.title)
            if query is not None:
                return ("Spotify", query)
            continue

        if (
            isinstance(act, discord.Activity)
            and act.type == discord.ActivityType.listening
        ):
            payload = _extract_generic_music_payload(act)
            if payload is not None:
                return payload

    return None


def resolve_activity_member(
    guild: discord.Guild | None,
    user: discord.Member | discord.User,
) -> discord.Member | discord.User:
    """Prefer the cached guild member because slash interaction payloads omit presences."""
    if guild is None:
        return user

    cached = guild.get_member(user.id)
    if cached is not None:
        return cached
    return user


def extract_listening_query(
    member: discord.Member | discord.User,
) -> NonEmptyStr | None:
    """Return ``"<artist> - <track>"`` from the member's current music activity.

    Recognises Spotify (typed activity) and Apple Music (generic
    ``Activity`` with ``type=listening`` and matching ``application_id``).
    Returns ``None`` if the member isn't broadcasting a music activity or
    isn't a Member (e.g. a User in a DM context).
    """
    payload = _extract_listening_payload(member)
    return payload[1] if payload is not None else None


def _extract_generic_music_payload(
    act: discord.Activity,
) -> tuple[str, NonEmptyStr] | None:
    """Extract ``(source_label, query)`` from generic music integrations."""
    if not act.details or not act.state:
        return None

    app_name = (act.name or "").casefold()
    app_id = act.application_id
    if app_id == SPOTIFY_APP_ID or app_name == "spotify":
        source_label = "Spotify"
    elif app_id == APPLE_MUSIC_APP_ID or app_name == "apple music":
        source_label = "Apple Music"
    else:
        return None

    query = _format_query(act.state, act.details)
    if query is None:
        return None
    return (source_label, query)


async def enable_live_mirror(
    interaction: discord.Interaction,
    *,
    follow_mode: FollowMode,
    max_tracks: FollowTrackCount = LimitConstants.MAX_FOLLOW_TRACKS,
    notice: str | None = None,
) -> None:
    """Enable follow mode for the invoking member and seed it from current activity."""
    assert interaction.guild is not None

    user = interaction.user
    if not isinstance(user, discord.Member):
        await interaction.response.send_message(
            "Live mirror needs a Member context.", ephemeral=True
        )
        return

    activity_member = resolve_activity_member(interaction.guild, user)
    seed_query = extract_listening_query(activity_member)
    if seed_query is None:
        presences_enabled = interaction.client.intents.presences
        hint = ""
        if not presences_enabled:
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
        guild_id=interaction.guild.id,
        user_id=user.id,
        user_name=user.display_name,
        max_tracks=max_tracks,
    )
    await interaction.response.defer(ephemeral=True)

    enqueued = await follow_mode.on_track_change(
        guild_id=interaction.guild.id,
        user_id=user.id,
        query=seed_query,
    )
    if enqueued:
        message = (
            f"Mirroring your listening — I'll follow up to **{max_tracks}** "
            "track(s), then auto-stop."
        )
    else:
        message = (
            f"Mirror started, but I couldn't resolve **{seed_query}** on "
            "YouTube. The next track you switch to should pick up."
        )

    if notice:
        message = f"{notice} {message}"

    await interaction.followup.send(message, ephemeral=True)
