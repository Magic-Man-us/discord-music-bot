"""Extract a YouTube search query from a member's Discord music activity.

Used by ``/play mine`` and ``/dj follow`` to resolve whatever the user is
currently listening to (Spotify, Apple Music) into a string we can hand to
the audio resolver.
"""

from __future__ import annotations

from typing import Final

import discord

from ....domain.shared.types import NonEmptyStr

APPLE_MUSIC_APP_ID: Final[int] = 1066220978406953012


def extract_listening_query(member: discord.Member | discord.User) -> NonEmptyStr | None:
    """Return ``"<artist> - <track>"`` from the member's current music activity.

    Recognises Spotify (typed activity) and Apple Music (generic
    ``Activity`` with ``type=listening`` and matching ``application_id``).
    Returns ``None`` if the member isn't broadcasting a music activity or
    isn't a Member (e.g. a User in a DM context).
    """
    if not isinstance(member, discord.Member):
        return None

    for act in member.activities:
        if isinstance(act, discord.Spotify):
            if act.title and act.artist:
                return f"{act.artist} - {act.title}"
            continue

        if isinstance(act, discord.Activity) and act.type == discord.ActivityType.listening:
            is_apple = act.application_id == APPLE_MUSIC_APP_ID or act.name == "Apple Music"
            if is_apple and act.details and act.state:
                return f"{act.state} - {act.details}"

    return None
