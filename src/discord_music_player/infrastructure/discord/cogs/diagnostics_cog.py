"""Prefix-style diagnostics — hot-loadable for live inspection.

Use prefix commands (not slash) so they work the moment the cog is loaded
without waiting on a tree.sync(). Read-only, so anyone can run them — useful
for sanity-checking what the bot sees about voice / queue / activities.
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from ..services.activity import extract_listening_query, resolve_activity_member
from .base_cog import BaseCog


def _format_activities_message(
    target: discord.Member,
    *,
    presences_enabled: bool,
    label: str | None = None,
) -> str:
    """Return a compact dump of the activities visible for a member."""
    activities = list(target.activities)
    resolved_query = extract_listening_query(target)
    header_prefix = f"**{label}**\n" if label else ""
    status_line = (
        f"status=`{getattr(target, 'status', '?')}` "
        f"desktop=`{getattr(target, 'desktop_status', '?')}` "
        f"mobile=`{getattr(target, 'mobile_status', '?')}` "
        f"web=`{getattr(target, 'web_status', '?')}`"
    )

    if not activities:
        hint = ""
        if not presences_enabled:
            hint = (
                " *(bot's `presences` intent is OFF — Discord won't send "
                "activity data; flip `intents.presences = True` in bot.py "
                "and restart.)*"
            )
        return (
            f"{header_prefix}`{target.display_name}` has no Discord activities visible "
            f"to the bot.{hint}\n"
            f"{status_line}\n"
            f"parser query=`{resolved_query or 'None'}`"
        )[:1900]

    lines = [
        *([f"**{label}**"] if label else []),
        f"**{target.display_name}** activities ({len(activities)}):",
        status_line,
        f"parser query=`{resolved_query or 'None'}`",
    ]
    for idx, act in enumerate(activities, start=1):
        kind = type(act).__name__
        type_name = getattr(act.type, "name", "?") if hasattr(act, "type") else "?"
        line = f"`{idx}` **{kind}** (type=`{type_name}`)"

        if isinstance(act, discord.Spotify):
            line += (
                f"\n    title=`{act.title}` artist=`{act.artist}` "
                f"album=`{act.album}` track_id=`{act.track_id}`"
            )
        elif isinstance(act, discord.CustomActivity):
            line += f"\n    name=`{act.name}` emoji=`{act.emoji}`"
        elif isinstance(act, discord.Streaming):
            line += f"\n    name=`{act.name}` url=`{act.url}` platform=`{act.platform}`"
        elif isinstance(act, discord.Activity):
            line += (
                f"\n    name=`{act.name}` details=`{act.details}` state=`{act.state}` "
                f"app_id=`{act.application_id}`"
            )
        else:
            line += f"\n    repr=`{act!r}`"

        lines.append(line)

    return "\n".join(lines)[:1900]


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
            await ctx.reply(
                "Need a Member to inspect activities.", mention_author=False
            )
            return
        target = target_candidate

        message = _format_activities_message(
            target,
            presences_enabled=ctx.bot.intents.presences,
        )
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

        cached = resolve_activity_member(interaction.guild, user)
        if cached is user:
            message = _format_activities_message(
                user,
                presences_enabled=interaction.client.intents.presences,
            )
        else:
            message = "\n\n".join(
                [
                    _format_activities_message(
                        user,
                        presences_enabled=interaction.client.intents.presences,
                        label="interaction.user",
                    ),
                    _format_activities_message(
                        cached,
                        presences_enabled=interaction.client.intents.presences,
                        label="guild cache",
                    ),
                ]
            )[:1900]
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
        await ctx.reply("\n".join(lines)[:1900], mention_author=False)


setup = DiagnosticsCog.setup
