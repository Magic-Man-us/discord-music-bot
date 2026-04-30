"""Prefix-style diagnostics — hot-loadable for live inspection.

Use prefix commands (not slash) so they work the moment the cog is loaded
without waiting on a tree.sync(). Read-only, so anyone can run them — useful
for sanity-checking what the bot sees about voice / queue / activities.
"""

from __future__ import annotations

import discord
from discord.ext import commands

from .base_cog import BaseCog


class DiagnosticsCog(BaseCog):
    @commands.group(name="diag", invoke_without_command=True)
    async def diag(self, ctx: commands.Context) -> None:
        await ctx.reply(
            "Subcommands: `!diag activities [@user]`, `!diag state`, `!diag listeners`",
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

        activities = list(target.activities)
        if not activities:
            hint = ""
            if not ctx.bot.intents.presences:
                hint = (
                    " *(bot's `presences` intent is OFF — Discord won't send "
                    "activity data; flip `intents.presences = True` in bot.py "
                    "and restart.)*"
                )
            await ctx.reply(
                f"`{target.display_name}` has no Discord activities visible to the bot.{hint}",
                mention_author=False,
            )
            return

        lines = [f"**{target.display_name}** activities ({len(activities)}):"]
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

        await ctx.reply("\n".join(lines)[:1900], mention_author=False)

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
