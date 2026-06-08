"""Prefix-style diagnostics — hot-loadable for live inspection.

Use prefix commands (not slash) so they work the moment the cog is loaded
without waiting on a tree.sync(). Read-only, so anyone can run them — useful
for sanity-checking what the bot sees about voice / queue / activities.
"""

from __future__ import annotations

from typing import Annotated, Final, Literal

import discord
from discord import app_commands
from discord.ext import commands
from pydantic import BaseModel, Field

from ....domain.shared.model_config import FrozenModelConfig
from ....domain.shared.types import DiscordSnowflake, NonEmptyStr, OptionalNonEmptyStr
from ..services.activity import extract_listening_query, resolve_activity_member
from .base_cog import BaseCog

# Discord caps messages at 2000 chars; truncate diag dumps with headroom.
_MAX_DIAG_CHARS: Final[int] = 1900
_PRESENCES_OFF_HINT: Final[str] = (
    " *(bot's `presences` intent is OFF — Discord won't send activity data; "
    "flip `intents.presences = True` in bot.py and restart.)*"
)


class _SpotifyDetail(BaseModel):
    model_config = FrozenModelConfig

    kind: Literal["spotify"] = "spotify"
    title: OptionalNonEmptyStr = None
    artist: OptionalNonEmptyStr = None
    album: OptionalNonEmptyStr = None
    track_id: OptionalNonEmptyStr = None


class _CustomDetail(BaseModel):
    model_config = FrozenModelConfig

    kind: Literal["custom"] = "custom"
    name: OptionalNonEmptyStr = None
    emoji: OptionalNonEmptyStr = None


class _StreamingDetail(BaseModel):
    model_config = FrozenModelConfig

    kind: Literal["streaming"] = "streaming"
    name: OptionalNonEmptyStr = None
    url: OptionalNonEmptyStr = None
    platform: OptionalNonEmptyStr = None


class _GenericDetail(BaseModel):
    model_config = FrozenModelConfig

    kind: Literal["generic"] = "generic"
    name: OptionalNonEmptyStr = None
    details: OptionalNonEmptyStr = None
    state: OptionalNonEmptyStr = None
    app_id: DiscordSnowflake | None = None


class _UnknownDetail(BaseModel):
    model_config = FrozenModelConfig

    kind: Literal["unknown"] = "unknown"
    repr: NonEmptyStr


_ActivityDetail = Annotated[
    _SpotifyDetail | _CustomDetail | _StreamingDetail | _GenericDetail | _UnknownDetail,
    Field(discriminator="kind"),
]


def _format_detail(detail: _ActivityDetail) -> str:
    match detail:
        case _SpotifyDetail():
            return (
                f"title=`{detail.title}` artist=`{detail.artist}` "
                f"album=`{detail.album}` track_id=`{detail.track_id}`"
            )
        case _CustomDetail():
            return f"name=`{detail.name}` emoji=`{detail.emoji}`"
        case _StreamingDetail():
            return f"name=`{detail.name}` url=`{detail.url}` platform=`{detail.platform}`"
        case _GenericDetail():
            return (
                f"name=`{detail.name}` details=`{detail.details}` "
                f"state=`{detail.state}` app_id=`{detail.app_id}`"
            )
        case _UnknownDetail():
            return f"repr=`{detail.repr}`"


class _ActivityInfo(BaseModel):
    model_config = FrozenModelConfig

    class_name: NonEmptyStr
    type_name: NonEmptyStr
    detail: _ActivityDetail

    @classmethod
    def from_activity(cls, act: discord.BaseActivity | discord.Spotify) -> _ActivityInfo:
        # discord.py owns these classes; this boundary match is the only place we
        # dispatch on them — past here every activity is a tagged _ActivityDetail.
        detail: _ActivityDetail
        match act:
            case discord.Spotify():
                detail = _SpotifyDetail(
                    title=act.title, artist=act.artist, album=act.album, track_id=act.track_id
                )
            case discord.CustomActivity():
                detail = _CustomDetail(name=act.name, emoji=str(act.emoji) if act.emoji else None)
            case discord.Streaming():
                detail = _StreamingDetail(name=act.name, url=act.url, platform=act.platform)
            case discord.Activity():
                detail = _GenericDetail(
                    name=act.name,
                    details=act.details,
                    state=act.state,
                    app_id=act.application_id,
                )
            case _:
                detail = _UnknownDetail(repr=repr(act))
        return cls(class_name=type(act).__name__, type_name=act.type.name, detail=detail)


def _format_activity(info: _ActivityInfo) -> str:
    return f"**{info.class_name}** (type=`{info.type_name}`)\n    {_format_detail(info.detail)}"


class _PresenceStatus(BaseModel):
    model_config = FrozenModelConfig

    overall: NonEmptyStr
    desktop: NonEmptyStr
    mobile: NonEmptyStr
    web: NonEmptyStr


class _MemberPresence(BaseModel):
    model_config = FrozenModelConfig

    display_name: NonEmptyStr
    status: _PresenceStatus
    presences_enabled: bool
    parser_query: OptionalNonEmptyStr = None
    activities: tuple[_ActivityInfo, ...] = ()

    @classmethod
    def from_member(cls, member: discord.Member, *, presences_enabled: bool) -> _MemberPresence:
        return cls(
            display_name=member.display_name,
            status=_PresenceStatus(
                overall=str(member.status),
                desktop=str(member.desktop_status),
                mobile=str(member.mobile_status),
                web=str(member.web_status),
            ),
            presences_enabled=presences_enabled,
            parser_query=extract_listening_query(member),
            activities=tuple(_ActivityInfo.from_activity(a) for a in member.activities),
        )

    def render(self, *, label: str | None = None) -> str:
        header = [f"**{label}**"] if label else []
        status_line = (
            f"status=`{self.status.overall}` desktop=`{self.status.desktop}` "
            f"mobile=`{self.status.mobile}` web=`{self.status.web}`"
        )
        query_line = f"parser query=`{self.parser_query or 'None'}`"

        if not self.activities:
            hint = "" if self.presences_enabled else _PRESENCES_OFF_HINT
            body = [
                f"`{self.display_name}` has no Discord activities visible to the bot.{hint}",
                status_line,
                query_line,
            ]
            return "\n".join(header + body)[:_MAX_DIAG_CHARS]

        body = [
            f"**{self.display_name}** activities ({len(self.activities)}):",
            status_line,
            query_line,
            *(f"`{idx}` {_format_activity(info)}" for idx, info in enumerate(self.activities, 1)),
        ]
        return "\n".join(header + body)[:_MAX_DIAG_CHARS]


class DiagnosticsCog(BaseCog):
    @commands.group(name="diag", invoke_without_command=True)
    async def diag(self, ctx: commands.Context) -> None:
        await ctx.reply(
            "Subcommands: `!diag activities [@user]`, `!diag state`, "
            "`!diag listeners`, `/diag_activities`",
            mention_author=False,
        )

    @diag.command(name="activities")
    async def activities(
        self,
        ctx: commands.Context,
        *,
        query: str | None = None,
    ) -> None:
        """Inspect a member's Discord activity integrations (Spotify etc.).

        ``query`` is keyword-rest so multi-word nicknames like "butta b" work.
        Pass nothing to inspect yourself.
        """
        if query is None:
            target_candidate: discord.Member | discord.User = ctx.author
        else:
            try:
                target_candidate = await commands.MemberConverter().convert(ctx, query)
            except commands.MemberNotFound:
                await ctx.reply(
                    f"No member matched `{query}`. Try an @mention or numeric ID.",
                    mention_author=False,
                )
                return

        if not isinstance(target_candidate, discord.Member):
            await ctx.reply("Need a Member to inspect activities.", mention_author=False)
            return
        target = target_candidate

        message = _MemberPresence.from_member(
            target,
            presences_enabled=ctx.bot.intents.presences,
        ).render()
        await ctx.reply(message, mention_author=False)

    @app_commands.command(
        name="diag_activities",
        description="Show the Discord activities the bot sees for you.",
    )
    @app_commands.guild_only()
    async def diag_activities(self, interaction: discord.Interaction) -> None:
        """Show an ephemeral dump of the caller's Discord activities."""
        user = interaction.user
        if not isinstance(user, discord.Member):
            await interaction.response.send_message(
                "Need a Member context to inspect activities.",
                ephemeral=True,
            )
            return

        presences_enabled = interaction.client.intents.presences
        cached = resolve_activity_member(interaction.guild, user)
        if isinstance(cached, discord.Member) and cached is not user:
            message = "\n\n".join(
                [
                    _MemberPresence.from_member(user, presences_enabled=presences_enabled).render(
                        label="interaction.user"
                    ),
                    _MemberPresence.from_member(cached, presences_enabled=presences_enabled).render(
                        label="guild cache"
                    ),
                ]
            )[:_MAX_DIAG_CHARS]
        else:
            message = _MemberPresence.from_member(
                user, presences_enabled=presences_enabled
            ).render()
        await interaction.response.send_message(message, ephemeral=True)

    @diag.command(name="state")
    async def state(self, ctx: commands.Context) -> None:
        if ctx.guild is None:
            await ctx.reply("Guild only.", mention_author=False)
            return

        guild_id = ctx.guild.id
        container = self.container

        session = await container.session_repository.get(guild_id)
        radio_enabled = container.radio_service.is_enabled(guild_id)
        autodj_enabled = container.auto_dj.is_enabled(guild_id)
        voice_connected = container.voice_adapter.is_connected(guild_id)
        ai_available = await container.ai_client.is_available()

        if session is None:
            session_line = "session: none"
        else:
            current = session.current_track.title if session.current_track else "—"
            session_line = (
                f"session: state=`{session.state}` queue_len=`{len(session.queue)}` "
                f"current=`{current}`"
            )

        await ctx.reply(
            "\n".join(
                [
                    f"**Diag — guild {guild_id}**",
                    session_line,
                    f"voice connected: `{voice_connected}`",
                    f"radio enabled: `{radio_enabled}`",
                    f"auto-DJ enabled: `{autodj_enabled}`",
                    f"AI available: `{ai_available}`",
                ]
            ),
            mention_author=False,
        )

    @diag.command(name="listeners")
    async def listeners(self, ctx: commands.Context) -> None:
        if ctx.guild is None:
            await ctx.reply("Guild only.", mention_author=False)
            return

        listeners = await self.container.voice_adapter.get_listeners(ctx.guild.id)
        if not listeners:
            await ctx.reply("No listeners (or not connected).", mention_author=False)
            return

        lines = [f"**Listeners in guild {ctx.guild.id}** ({len(listeners)}):"]
        for user_id in listeners:
            member = ctx.guild.get_member(user_id)
            label = member.display_name if member else f"<unknown {user_id}>"
            lines.append(f"  - `{user_id}` {label}")
        await ctx.reply("\n".join(lines)[:_MAX_DIAG_CHARS], mention_author=False)


setup = DiagnosticsCog.setup
