"""User, server, and message information commands and context menus."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from discord_music_player.domain.shared.constants import DiscordEmbedLimits, UIConstants
from discord_music_player.domain.shared.messages import (
    DiscordUIMessages,
    ErrorMessages,
    LogTemplates,
)

if TYPE_CHECKING:
    from ....config.container import Container

logger = logging.getLogger(__name__)


def _format_abs_rel(dt: datetime | None) -> str:
    if dt is None:
        return "-"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    abs_ts = discord.utils.format_dt(dt, style="F")
    rel_ts = discord.utils.format_dt(dt, style="R")
    return f"{abs_ts} ({rel_ts})"


class InfoCog(commands.Cog):
    def __init__(self, bot: commands.Bot, container: Container) -> None:
        self.bot = bot
        self.container = container

        self._user_info_ctx = app_commands.ContextMenu(
            name="User Info",
            callback=self._user_info_context_menu,
        )
        self._message_info_ctx = app_commands.ContextMenu(
            name="Message Info",
            callback=self._message_info_context_menu,
        )

    async def cog_load(self) -> None:
        self.bot.tree.add_command(self._user_info_ctx)
        self.bot.tree.add_command(self._message_info_ctx)
        logger.info(LogTemplates.COG_LOADED_INFO)

    async def cog_unload(self) -> None:
        self.bot.tree.remove_command(self._user_info_ctx.name, type=self._user_info_ctx.type)
        self.bot.tree.remove_command(self._message_info_ctx.name, type=self._message_info_ctx.type)
        logger.info(LogTemplates.COG_UNLOADED_INFO)

    # ─────────────────────────────────────────────────────────────────
    # Context Menus
    # ─────────────────────────────────────────────────────────────────

    async def _user_info_context_menu(
        self,
        interaction: discord.Interaction,
        user: discord.User | discord.Member,
    ) -> None:
        embed = self._build_user_info_embed(user, include_roles=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    def _build_user_info_embed(
        self, user: discord.User | discord.Member, include_roles: bool = False
    ) -> discord.Embed:
        member = user if isinstance(user, discord.Member) else None

        embed = discord.Embed(
            title=DiscordUIMessages.EMBED_USER_INFO.format(
                display_name=getattr(user, "display_name", user.name)
            ),
            color=discord.Color.blurple(),
        )
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.timestamp = datetime.now(UTC)

        self._add_user_basic_info(embed, user)

        if member is not None:
            self._add_member_guild_info(embed, member, include_roles)

        return embed

    def _add_user_basic_info(
        self, embed: discord.Embed, user: discord.User | discord.Member
    ) -> None:
        embed.add_field(name="ID", value=str(user.id), inline=True)
        embed.add_field(name="Mention", value=user.mention, inline=True)
        embed.add_field(name="Type", value="Bot" if user.bot else "Human", inline=True)
        embed.add_field(name="Created", value=_format_abs_rel(user.created_at), inline=False)

    def _add_member_guild_info(
        self, embed: discord.Embed, member: discord.Member, include_roles: bool
    ) -> None:
        embed.add_field(name="Joined", value=_format_abs_rel(member.joined_at), inline=False)
        embed.add_field(name="Nick", value=member.nick or "-", inline=True)

        if include_roles:
            self._add_member_roles_field(embed, member)
        else:
            self._add_member_role_summary(embed, member)

        self._add_member_optional_fields(embed, member)

    def _add_member_roles_field(self, embed: discord.Embed, member: discord.Member) -> None:
        roles = [r for r in member.roles if r.name != UIConstants.EVERYONE_ROLE]
        roles_sorted = sorted(roles, key=lambda r: r.position, reverse=True)
        top_roles = roles_sorted[:10]
        roles_value = ", ".join(r.mention for r in top_roles) or "-"
        embed.add_field(name=f"Roles ({len(roles)})", value=roles_value, inline=False)

    def _add_member_role_summary(self, embed: discord.Embed, member: discord.Member) -> None:
        if member.top_role.name != UIConstants.EVERYONE_ROLE:
            embed.add_field(name="Top Role", value=member.top_role.mention, inline=True)
        role_count = len([r for r in member.roles if r.name != UIConstants.EVERYONE_ROLE])
        embed.add_field(name="Role Count", value=str(role_count), inline=True)

    def _add_member_optional_fields(self, embed: discord.Embed, member: discord.Member) -> None:
        if member.voice and member.voice.channel:
            embed.add_field(name="Voice", value=member.voice.channel.mention, inline=True)

        if getattr(member, "timed_out_until", None):
            embed.add_field(
                name="Timeout Until", value=_format_abs_rel(member.timed_out_until), inline=True
            )

        if getattr(member, "premium_since", None):
            embed.add_field(
                name="Boosting Since", value=_format_abs_rel(member.premium_since), inline=True
            )

    async def _message_info_context_menu(
        self,
        interaction: discord.Interaction,
        message: discord.Message,
    ) -> None:
        embed = discord.Embed(
            title=DiscordUIMessages.EMBED_MESSAGE_INFO, color=discord.Color.teal()
        )
        embed.timestamp = datetime.now(UTC)

        embed.add_field(name="ID", value=str(message.id), inline=True)
        embed.add_field(name="Author", value=message.author.mention, inline=True)

        ch = message.channel
        ch_value = getattr(ch, "mention", None) or (
            f"#{getattr(ch, 'name', 'DM')}" if hasattr(ch, "name") else "DM"
        )
        embed.add_field(name="Channel", value=ch_value, inline=True)

        embed.add_field(
            name="Created",
            value=_format_abs_rel(message.created_at),
            inline=False,
        )

        content = (message.content or "").strip()
        snippet = (content[:DiscordEmbedLimits.MESSAGE_CONTENT_SNIPPET] + "…") if len(content) > DiscordEmbedLimits.MESSAGE_CONTENT_SNIPPET else content or "-"
        embed.add_field(name="Content", value=snippet, inline=False)

        embed.add_field(name="Attachments", value=str(len(message.attachments)), inline=True)
        embed.add_field(name="Jump", value=f"[Link]({message.jump_url})", inline=True)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ─────────────────────────────────────────────────────────────────
    # Commands
    # ─────────────────────────────────────────────────────────────────

    @commands.hybrid_command(name="serverinfo", description="Show server information.")
    @commands.guild_only()
    async def serverinfo(self, ctx: commands.Context) -> None:
        if ctx.guild is None:
            await ctx.send(DiscordUIMessages.STATE_SERVER_ONLY, ephemeral=True)
            return

        embed = self._build_serverinfo_embed(ctx.guild)
        await ctx.send(embed=embed, ephemeral=True)

    def _build_serverinfo_embed(self, guild: discord.Guild) -> discord.Embed:
        embed = discord.Embed(
            title=DiscordUIMessages.EMBED_SERVER_INFO.format(guild_name=guild.name),
            color=discord.Color.green(),
        )
        embed.timestamp = datetime.now(UTC)

        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)

        self._add_basic_info(embed, guild)
        self._add_member_counts(embed, guild)
        self._add_channel_counts(embed, guild)
        self._add_extras(embed, guild)

        return embed

    def _add_basic_info(self, embed: discord.Embed, guild: discord.Guild) -> None:
        embed.add_field(name="ID", value=str(guild.id), inline=True)
        if guild.owner:
            embed.add_field(name="Owner", value=guild.owner.mention, inline=True)
        embed.add_field(name="Created", value=_format_abs_rel(guild.created_at), inline=False)

    def _add_member_counts(self, embed: discord.Embed, guild: discord.Guild) -> None:
        humans = sum(1 for m in guild.members if not m.bot)
        bots = sum(1 for m in guild.members if m.bot)
        embed.add_field(name="Members", value=str(guild.member_count), inline=True)
        embed.add_field(name="Humans", value=str(humans), inline=True)
        embed.add_field(name="Bots", value=str(bots), inline=True)

    def _add_channel_counts(self, embed: discord.Embed, guild: discord.Guild) -> None:
        text_ch = sum(1 for c in guild.channels if isinstance(c, discord.TextChannel))
        voice_ch = sum(1 for c in guild.channels if isinstance(c, discord.VoiceChannel))
        stage_ch = sum(1 for c in guild.channels if isinstance(c, discord.StageChannel))

        embed.add_field(name="Text Channels", value=str(text_ch), inline=True)
        embed.add_field(name="Voice Channels", value=str(voice_ch), inline=True)
        embed.add_field(name="Stage Channels", value=str(stage_ch), inline=True)

    def _add_extras(self, embed: discord.Embed, guild: discord.Guild) -> None:
        embed.add_field(name="Roles", value=str(len(guild.roles)), inline=True)
        embed.add_field(name="Emojis", value=str(len(guild.emojis)), inline=True)
        embed.add_field(name="Stickers", value=str(len(guild.stickers)), inline=True)

        embed.add_field(
            name="Boosts", value=str(guild.premium_subscription_count or 0), inline=True
        )
        embed.add_field(name="Boost Tier", value=str(guild.premium_tier or 0), inline=True)
        embed.add_field(name="Verification", value=str(guild.verification_level), inline=True)

        if guild.features:
            features = ", ".join(sorted(guild.features)[:10])
            if len(guild.features) > 10:
                features += f" (+{len(guild.features) - 10} more)"
            embed.add_field(name="Features", value=features or "-", inline=False)

    @commands.hybrid_command(name="userinfo", description="Show user information.")
    @app_commands.describe(user="The user to get info about (defaults to you)")
    async def userinfo(
        self, ctx: commands.Context, user: discord.User | discord.Member | None = None
    ) -> None:
        target = user or ctx.author
        embed = self._build_user_info_embed(target, include_roles=False)
        await ctx.send(embed=embed, ephemeral=True)

    @commands.hybrid_command(name="avatar", description="Show user's avatar.")
    @app_commands.describe(user="The user to get avatar of (defaults to you)")
    async def avatar(
        self, ctx: commands.Context, user: discord.User | discord.Member | None = None
    ) -> None:
        target = user or ctx.author

        embed = discord.Embed(
            title=DiscordUIMessages.EMBED_AVATAR.format(
                display_name=getattr(target, "display_name", target.name)
            ),
            color=discord.Color.blurple(),
        )
        embed.set_image(url=target.display_avatar.url)

        avatar = target.display_avatar
        links = []
        for fmt in ["png", "jpg", "webp"]:
            links.append(f"[{fmt.upper()}]({avatar.with_format(fmt).url})")  # type: ignore
        if avatar.is_animated():
            links.append(f"[GIF]({avatar.with_format('gif').url})")  # type: ignore

        embed.description = " • ".join(links)

        await ctx.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    container = getattr(bot, "container", None)
    if container is None:
        raise RuntimeError(ErrorMessages.CONTAINER_NOT_FOUND)

    await bot.add_cog(InfoCog(bot, container))
