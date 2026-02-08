"""
Comprehensive Unit Tests for InfoCog

Tests for all info commands and context menus:
- User Info context menu
- Message Info context menu
- /serverinfo command
- /userinfo command
- /avatar command
- Embed formatting and field handling
- Error handling and edge cases
- Discord interaction mocking

Uses pytest with async/await patterns and proper mocking.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from discord_music_player.infrastructure.discord.cogs.info_cog import InfoCog, _format_abs_rel

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_bot():
    """Create a mock Discord bot."""
    bot = MagicMock()
    bot.tree = MagicMock()
    bot.tree.add_command = MagicMock()
    bot.tree.remove_command = MagicMock()
    return bot


@pytest.fixture
def mock_container():
    """Create a mock DI container."""
    container = MagicMock()
    return container


@pytest.fixture
def info_cog(mock_bot, mock_container):
    """Create an InfoCog instance with mocked dependencies."""
    return InfoCog(mock_bot, mock_container)


@pytest.fixture
def mock_interaction():
    """Create a mock Discord Interaction."""
    interaction = MagicMock(spec=discord.Interaction)
    interaction.response = MagicMock()
    interaction.response.send_message = AsyncMock()
    interaction.send = AsyncMock()

    # Guild setup
    interaction.guild = MagicMock()
    interaction.guild.id = 111111111
    interaction.guild.name = "Test Server"

    return interaction


@pytest.fixture
def mock_user():
    """Create a mock Discord User."""
    user = MagicMock(spec=discord.User)
    user.id = 123456789
    user.name = "testuser"
    user.display_name = "TestUser"
    user.mention = "<@123456789>"
    user.bot = False
    user.created_at = datetime(2020, 1, 1, 12, 0, 0, tzinfo=UTC)

    # Avatar
    user.display_avatar = MagicMock()
    user.display_avatar.url = "https://cdn.discordapp.com/avatars/123/abc.png"
    user.display_avatar.is_animated = MagicMock(return_value=False)
    user.display_avatar.with_format = MagicMock(return_value=user.display_avatar)

    return user


@pytest.fixture
def mock_member():
    """Create a mock Discord Member."""
    member = MagicMock(spec=discord.Member)
    member.id = 123456789
    member.name = "testuser"
    member.display_name = "TestUser"
    member.mention = "<@123456789>"
    member.bot = False
    member.nick = "TestNick"
    member.created_at = datetime(2020, 1, 1, 12, 0, 0, tzinfo=UTC)
    member.joined_at = datetime(2021, 6, 15, 10, 30, 0, tzinfo=UTC)

    # Avatar
    member.display_avatar = MagicMock()
    member.display_avatar.url = "https://cdn.discordapp.com/avatars/123/abc.png"
    member.display_avatar.is_animated = MagicMock(return_value=False)
    member.display_avatar.with_format = MagicMock(return_value=member.display_avatar)

    # Roles
    role1 = MagicMock()
    role1.name = "Member"
    role1.position = 1
    role1.mention = "<@&111>"

    role2 = MagicMock()
    role2.name = "Moderator"
    role2.position = 2
    role2.mention = "<@&222>"

    everyone_role = MagicMock()
    everyone_role.name = "@everyone"
    everyone_role.position = 0

    member.roles = [everyone_role, role1, role2]
    member.top_role = role2

    # Voice state
    member.voice = None

    # Guild permissions
    member.guild_permissions = MagicMock()
    member.guild_permissions.administrator = False

    # Optional attributes
    member.timed_out_until = None
    member.premium_since = None

    return member


@pytest.fixture
def mock_guild():
    """Create a mock Discord Guild."""
    guild = MagicMock(spec=discord.Guild)
    guild.id = 999888777
    guild.name = "Test Server"
    guild.created_at = datetime(2019, 5, 10, 8, 0, 0, tzinfo=UTC)
    guild.member_count = 150

    # Icon
    guild.icon = MagicMock()
    guild.icon.url = "https://cdn.discordapp.com/icons/999/icon.png"

    # Owner
    guild.owner = MagicMock()
    guild.owner.mention = "<@999999999>"

    # Members
    member1 = MagicMock()
    member1.bot = False
    member2 = MagicMock()
    member2.bot = False
    member3 = MagicMock()
    member3.bot = True
    guild.members = [member1, member2, member3]

    # Channels
    text_channel = MagicMock(spec=discord.TextChannel)
    voice_channel = MagicMock(spec=discord.VoiceChannel)
    stage_channel = MagicMock(spec=discord.StageChannel)
    guild.channels = [text_channel, voice_channel, stage_channel]

    # Roles
    role1 = MagicMock()
    role2 = MagicMock()
    guild.roles = [role1, role2]

    # Emojis and stickers
    guild.emojis = [MagicMock(), MagicMock()]
    guild.stickers = [MagicMock()]

    # Boost info
    guild.premium_subscription_count = 5
    guild.premium_tier = 1

    # Verification
    guild.verification_level = discord.VerificationLevel.medium

    # Features
    guild.features = ["COMMUNITY", "DISCOVERABLE"]

    return guild


@pytest.fixture
def mock_message():
    """Create a mock Discord Message."""
    message = MagicMock(spec=discord.Message)
    message.id = 555666777
    message.content = "Hello, this is a test message!"
    message.created_at = datetime(2024, 1, 15, 14, 30, 0, tzinfo=UTC)
    message.jump_url = "https://discord.com/channels/999/888/777"

    # Author
    message.author = MagicMock()
    message.author.mention = "<@123456789>"

    # Channel
    message.channel = MagicMock()
    message.channel.mention = "<#888888888>"

    # Attachments
    message.attachments = []

    return message


# =============================================================================
# Helper Function Tests
# =============================================================================


class TestFormatAbsRel:
    """Tests for _format_abs_rel helper function."""

    def test_format_abs_rel_with_datetime(self):
        """Should format datetime with absolute and relative timestamps."""
        dt = datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)
        result = _format_abs_rel(dt)

        assert "<t:" in result
        assert ":F>" in result
        assert "(<t:" in result
        assert ":R>)" in result

    def test_format_abs_rel_with_none(self):
        """Should return dash for None."""
        result = _format_abs_rel(None)
        assert result == "-"

    def test_format_abs_rel_adds_utc_timezone(self):
        """Should add UTC timezone if datetime is naive."""
        dt = datetime(2024, 1, 15, 12, 0, 0)  # No timezone
        result = _format_abs_rel(dt)

        # Should not crash and should produce valid format
        assert "<t:" in result


# =============================================================================
# Cog Initialization Tests
# =============================================================================


class TestInfoCogInitialization:
    """Tests for InfoCog initialization and lifecycle."""

    def test_cog_initializes_with_bot_and_container(self, mock_bot, mock_container):
        """Should initialize with bot and container."""
        cog = InfoCog(mock_bot, mock_container)

        assert cog.bot == mock_bot
        assert cog.container == mock_container
        assert cog._user_info_ctx is not None
        assert cog._message_info_ctx is not None

    def test_context_menus_created(self, info_cog):
        """Should create context menu commands."""
        assert info_cog._user_info_ctx.name == "User Info"
        assert info_cog._message_info_ctx.name == "Message Info"

    @pytest.mark.asyncio
    async def test_cog_load_registers_context_menus(self, info_cog, mock_bot):
        """Should register context menus on load."""
        await info_cog.cog_load()

        assert mock_bot.tree.add_command.call_count == 2

    @pytest.mark.asyncio
    async def test_cog_unload_removes_context_menus(self, info_cog, mock_bot):
        """Should remove context menus on unload."""
        await info_cog.cog_unload()

        assert mock_bot.tree.remove_command.call_count == 2


# =============================================================================
# User Info Context Menu Tests
# =============================================================================


class TestUserInfoContextMenu:
    """Tests for User Info context menu."""

    @pytest.mark.asyncio
    async def test_user_info_context_menu_sends_embed(self, info_cog, mock_interaction, mock_user):
        """Should send embed with user info."""
        await info_cog._user_info_context_menu(mock_interaction, mock_user)

        mock_interaction.response.send_message.assert_called_once()
        call_kwargs = mock_interaction.response.send_message.call_args.kwargs
        assert "embed" in call_kwargs
        assert call_kwargs["ephemeral"] is True

    @pytest.mark.asyncio
    async def test_user_info_context_menu_with_member(
        self, info_cog, mock_interaction, mock_member
    ):
        """Should send embed with member info including roles."""
        await info_cog._user_info_context_menu(mock_interaction, mock_member)

        mock_interaction.response.send_message.assert_called_once()
        call_kwargs = mock_interaction.response.send_message.call_args.kwargs
        embed = call_kwargs["embed"]

        assert isinstance(embed, discord.Embed)
        assert "TestUser" in embed.title


# =============================================================================
# User Info Embed Building Tests
# =============================================================================


class TestBuildUserInfoEmbed:
    """Tests for _build_user_info_embed method."""

    def test_build_user_info_embed_basic_user(self, info_cog, mock_user):
        """Should build embed for basic user."""
        embed = info_cog._build_user_info_embed(mock_user, include_roles=False)

        assert isinstance(embed, discord.Embed)
        assert "TestUser" in embed.title
        assert embed.color == discord.Color.blurple()
        assert embed.thumbnail.url == mock_user.display_avatar.url

    def test_build_user_info_embed_includes_basic_fields(self, info_cog, mock_user):
        """Should include ID, mention, type, and created fields."""
        embed = info_cog._build_user_info_embed(mock_user, include_roles=False)

        field_names = [field.name for field in embed.fields]
        assert "ID" in field_names
        assert "Mention" in field_names
        assert "Type" in field_names
        assert "Created" in field_names

    def test_build_user_info_embed_bot_type(self, info_cog, mock_user):
        """Should show Bot type for bot users."""
        mock_user.bot = True
        embed = info_cog._build_user_info_embed(mock_user, include_roles=False)

        type_field = next(field for field in embed.fields if field.name == "Type")
        assert type_field.value == "Bot"

    def test_build_user_info_embed_human_type(self, info_cog, mock_user):
        """Should show Human type for regular users."""
        mock_user.bot = False
        embed = info_cog._build_user_info_embed(mock_user, include_roles=False)

        type_field = next(field for field in embed.fields if field.name == "Type")
        assert type_field.value == "Human"

    def test_build_user_info_embed_member_with_roles(self, info_cog, mock_member):
        """Should include member-specific fields with roles."""
        embed = info_cog._build_user_info_embed(mock_member, include_roles=True)

        field_names = [field.name for field in embed.fields]
        assert "Joined" in field_names
        assert "Nick" in field_names
        assert any("Roles" in name for name in field_names)

    def test_build_user_info_embed_member_without_roles(self, info_cog, mock_member):
        """Should include role summary instead of full list when include_roles=False."""
        embed = info_cog._build_user_info_embed(mock_member, include_roles=False)

        field_names = [field.name for field in embed.fields]
        assert "Top Role" in field_names or "Role Count" in field_names

    def test_build_user_info_embed_member_no_nick(self, info_cog, mock_member):
        """Should show dash when member has no nickname."""
        mock_member.nick = None
        embed = info_cog._build_user_info_embed(mock_member, include_roles=False)

        nick_field = next(field for field in embed.fields if field.name == "Nick")
        assert nick_field.value == "-"

    def test_build_user_info_embed_member_in_voice(self, info_cog, mock_member):
        """Should include voice channel when member is in voice."""
        mock_member.voice = MagicMock()
        mock_member.voice.channel = MagicMock()
        mock_member.voice.channel.mention = "<#999999999>"

        embed = info_cog._build_user_info_embed(mock_member, include_roles=False)

        field_names = [field.name for field in embed.fields]
        assert "Voice" in field_names

    def test_build_user_info_embed_member_timed_out(self, info_cog, mock_member):
        """Should include timeout info when member is timed out."""
        mock_member.timed_out_until = datetime(2024, 12, 31, 23, 59, 59, tzinfo=UTC)

        embed = info_cog._build_user_info_embed(mock_member, include_roles=False)

        field_names = [field.name for field in embed.fields]
        assert "Timeout Until" in field_names

    def test_build_user_info_embed_member_boosting(self, info_cog, mock_member):
        """Should include boost info when member is boosting."""
        mock_member.premium_since = datetime(2023, 6, 1, 0, 0, 0, tzinfo=UTC)

        embed = info_cog._build_user_info_embed(mock_member, include_roles=False)

        field_names = [field.name for field in embed.fields]
        assert "Boosting Since" in field_names


# =============================================================================
# Message Info Context Menu Tests
# =============================================================================


class TestMessageInfoContextMenu:
    """Tests for Message Info context menu."""

    @pytest.mark.asyncio
    async def test_message_info_context_menu_sends_embed(
        self, info_cog, mock_interaction, mock_message
    ):
        """Should send embed with message info."""
        await info_cog._message_info_context_menu(mock_interaction, mock_message)

        mock_interaction.response.send_message.assert_called_once()
        call_kwargs = mock_interaction.response.send_message.call_args.kwargs
        assert "embed" in call_kwargs
        assert call_kwargs["ephemeral"] is True

    @pytest.mark.asyncio
    async def test_message_info_includes_basic_fields(
        self, info_cog, mock_interaction, mock_message
    ):
        """Should include ID, author, channel, and content fields."""
        await info_cog._message_info_context_menu(mock_interaction, mock_message)

        call_kwargs = mock_interaction.response.send_message.call_args.kwargs
        embed = call_kwargs["embed"]

        field_names = [field.name for field in embed.fields]
        assert "ID" in field_names
        assert "Author" in field_names
        assert "Channel" in field_names
        assert "Created" in field_names
        assert "Content" in field_names
        assert "Attachments" in field_names
        assert "Jump" in field_names

    @pytest.mark.asyncio
    async def test_message_info_truncates_long_content(
        self, info_cog, mock_interaction, mock_message
    ):
        """Should truncate content longer than 256 characters."""
        mock_message.content = "a" * 300

        await info_cog._message_info_context_menu(mock_interaction, mock_message)

        call_kwargs = mock_interaction.response.send_message.call_args.kwargs
        embed = call_kwargs["embed"]
        content_field = next(field for field in embed.fields if field.name == "Content")

        assert len(content_field.value) <= 257  # 256 + ellipsis
        assert "…" in content_field.value

    @pytest.mark.asyncio
    async def test_message_info_empty_content(self, info_cog, mock_interaction, mock_message):
        """Should show dash for empty content."""
        mock_message.content = ""

        await info_cog._message_info_context_menu(mock_interaction, mock_message)

        call_kwargs = mock_interaction.response.send_message.call_args.kwargs
        embed = call_kwargs["embed"]
        content_field = next(field for field in embed.fields if field.name == "Content")

        assert content_field.value == "-"

    @pytest.mark.asyncio
    async def test_message_info_shows_attachment_count(
        self, info_cog, mock_interaction, mock_message
    ):
        """Should show attachment count."""
        mock_message.attachments = [MagicMock(), MagicMock(), MagicMock()]

        await info_cog._message_info_context_menu(mock_interaction, mock_message)

        call_kwargs = mock_interaction.response.send_message.call_args.kwargs
        embed = call_kwargs["embed"]
        attachments_field = next(field for field in embed.fields if field.name == "Attachments")

        assert attachments_field.value == "3"


# =============================================================================
# /serverinfo Command Tests
# =============================================================================


class TestServerinfoCommand:
    """Tests for /serverinfo command."""

    @pytest.mark.asyncio
    async def test_serverinfo_sends_embed(self, info_cog, mock_interaction, mock_guild):
        """Should send embed with server info."""
        mock_ctx = MagicMock()
        mock_ctx.guild = mock_guild
        mock_ctx.send = AsyncMock()

        await info_cog.serverinfo.callback(info_cog, mock_ctx)

        mock_ctx.send.assert_called_once()
        call_kwargs = mock_ctx.send.call_args.kwargs
        assert "embed" in call_kwargs
        assert call_kwargs["ephemeral"] is True

    @pytest.mark.asyncio
    async def test_serverinfo_no_guild_returns_error(self, info_cog):
        """Should return error when not in a guild."""
        mock_ctx = MagicMock()
        mock_ctx.guild = None
        mock_ctx.send = AsyncMock()

        await info_cog.serverinfo.callback(info_cog, mock_ctx)

        mock_ctx.send.assert_called_once()
        args = mock_ctx.send.call_args[0]
        assert "server" in args[0].lower()

    def test_build_serverinfo_embed_basic_info(self, info_cog, mock_guild):
        """Should include basic server info."""
        embed = info_cog._build_serverinfo_embed(mock_guild)

        assert isinstance(embed, discord.Embed)
        assert "Test Server" in embed.title
        assert embed.color == discord.Color.green()
        assert embed.thumbnail.url == mock_guild.icon.url

    def test_build_serverinfo_embed_fields(self, info_cog, mock_guild):
        """Should include all expected fields."""
        embed = info_cog._build_serverinfo_embed(mock_guild)

        field_names = [field.name for field in embed.fields]

        # Basic info
        assert "ID" in field_names
        assert "Owner" in field_names
        assert "Created" in field_names

        # Member counts
        assert "Members" in field_names
        assert "Humans" in field_names
        assert "Bots" in field_names

        # Channel counts
        assert "Text Channels" in field_names
        assert "Voice Channels" in field_names
        assert "Stage Channels" in field_names

        # Extras
        assert "Roles" in field_names
        assert "Emojis" in field_names
        assert "Stickers" in field_names
        assert "Boosts" in field_names
        assert "Boost Tier" in field_names
        assert "Verification" in field_names

    def test_build_serverinfo_embed_member_counts(self, info_cog, mock_guild):
        """Should correctly count humans and bots."""
        embed = info_cog._build_serverinfo_embed(mock_guild)

        humans_field = next(field for field in embed.fields if field.name == "Humans")
        bots_field = next(field for field in embed.fields if field.name == "Bots")

        assert humans_field.value == "2"  # 2 humans in mock_guild
        assert bots_field.value == "1"  # 1 bot in mock_guild

    def test_build_serverinfo_embed_channel_counts(self, info_cog, mock_guild):
        """Should correctly count different channel types."""
        embed = info_cog._build_serverinfo_embed(mock_guild)

        text_field = next(field for field in embed.fields if field.name == "Text Channels")
        voice_field = next(field for field in embed.fields if field.name == "Voice Channels")
        stage_field = next(field for field in embed.fields if field.name == "Stage Channels")

        assert text_field.value == "1"
        assert voice_field.value == "1"
        assert stage_field.value == "1"

    def test_build_serverinfo_embed_features(self, info_cog, mock_guild):
        """Should include server features."""
        embed = info_cog._build_serverinfo_embed(mock_guild)

        field_names = [field.name for field in embed.fields]
        assert "Features" in field_names

        features_field = next(field for field in embed.fields if field.name == "Features")
        assert "COMMUNITY" in features_field.value
        assert "DISCOVERABLE" in features_field.value

    def test_build_serverinfo_embed_many_features_truncated(self, info_cog, mock_guild):
        """Should truncate features list when more than 10."""
        mock_guild.features = [f"FEATURE_{i}" for i in range(15)]

        embed = info_cog._build_serverinfo_embed(mock_guild)

        features_field = next(field for field in embed.fields if field.name == "Features")
        assert "+5 more" in features_field.value

    def test_build_serverinfo_embed_no_icon(self, info_cog, mock_guild):
        """Should handle guilds without icons."""
        mock_guild.icon = None

        embed = info_cog._build_serverinfo_embed(mock_guild)

        assert embed.thumbnail is None or embed.thumbnail.url is None


# =============================================================================
# /userinfo Command Tests
# =============================================================================


class TestUserinfoCommand:
    """Tests for /userinfo command."""

    @pytest.mark.asyncio
    async def test_userinfo_sends_embed(self, info_cog, mock_user):
        """Should send embed with user info."""
        mock_ctx = MagicMock()
        mock_ctx.author = mock_user
        mock_ctx.send = AsyncMock()

        await info_cog.userinfo.callback(info_cog, mock_ctx, user=None)

        mock_ctx.send.assert_called_once()
        call_kwargs = mock_ctx.send.call_args.kwargs
        assert "embed" in call_kwargs
        assert call_kwargs["ephemeral"] is True

    @pytest.mark.asyncio
    async def test_userinfo_defaults_to_author(self, info_cog, mock_user):
        """Should default to command author when no user specified."""
        mock_ctx = MagicMock()
        mock_ctx.author = mock_user
        mock_ctx.send = AsyncMock()

        await info_cog.userinfo.callback(info_cog, mock_ctx, user=None)

        # Should use author
        call_kwargs = mock_ctx.send.call_args.kwargs
        embed = call_kwargs["embed"]
        assert "TestUser" in embed.title

    @pytest.mark.asyncio
    async def test_userinfo_specific_user(self, info_cog, mock_user):
        """Should show info for specified user."""
        mock_ctx = MagicMock()
        mock_ctx.author = MagicMock()
        mock_ctx.send = AsyncMock()

        other_user = MagicMock(spec=discord.User)
        other_user.display_name = "OtherUser"
        other_user.name = "otheruser"
        other_user.display_avatar = MagicMock()
        other_user.display_avatar.url = "https://example.com/avatar.png"

        await info_cog.userinfo.callback(info_cog, mock_ctx, user=other_user)

        call_kwargs = mock_ctx.send.call_args.kwargs
        embed = call_kwargs["embed"]
        assert "OtherUser" in embed.title


# =============================================================================
# /avatar Command Tests
# =============================================================================


class TestAvatarCommand:
    """Tests for /avatar command."""

    @pytest.mark.asyncio
    async def test_avatar_sends_embed(self, info_cog, mock_user):
        """Should send embed with avatar."""
        mock_ctx = MagicMock()
        mock_ctx.author = mock_user
        mock_ctx.send = AsyncMock()

        await info_cog.avatar.callback(info_cog, mock_ctx, user=None)

        mock_ctx.send.assert_called_once()
        call_kwargs = mock_ctx.send.call_args.kwargs
        assert "embed" in call_kwargs
        assert call_kwargs["ephemeral"] is True

    @pytest.mark.asyncio
    async def test_avatar_defaults_to_author(self, info_cog, mock_user):
        """Should default to command author when no user specified."""
        mock_ctx = MagicMock()
        mock_ctx.author = mock_user
        mock_ctx.send = AsyncMock()

        await info_cog.avatar.callback(info_cog, mock_ctx, user=None)

        call_kwargs = mock_ctx.send.call_args.kwargs
        embed = call_kwargs["embed"]
        assert "TestUser" in embed.title

    @pytest.mark.asyncio
    async def test_avatar_shows_image(self, info_cog, mock_user):
        """Should set image to user's avatar."""
        mock_ctx = MagicMock()
        mock_ctx.author = mock_user
        mock_ctx.send = AsyncMock()

        await info_cog.avatar.callback(info_cog, mock_ctx, user=None)

        call_kwargs = mock_ctx.send.call_args.kwargs
        embed = call_kwargs["embed"]
        assert embed.image.url == mock_user.display_avatar.url

    @pytest.mark.asyncio
    async def test_avatar_includes_format_links(self, info_cog, mock_user):
        """Should include links to different avatar formats."""
        mock_ctx = MagicMock()
        mock_ctx.author = mock_user
        mock_ctx.send = AsyncMock()

        await info_cog.avatar.callback(info_cog, mock_ctx, user=None)

        call_kwargs = mock_ctx.send.call_args.kwargs
        embed = call_kwargs["embed"]

        # Should have links for PNG, JPG, WEBP
        assert "PNG" in embed.description
        assert "JPG" in embed.description
        assert "WEBP" in embed.description

    @pytest.mark.asyncio
    async def test_avatar_includes_gif_for_animated(self, info_cog, mock_user):
        """Should include GIF link for animated avatars."""
        mock_ctx = MagicMock()
        mock_ctx.author = mock_user
        mock_ctx.send = AsyncMock()

        # Make avatar animated
        mock_user.display_avatar.is_animated = MagicMock(return_value=True)

        await info_cog.avatar.callback(info_cog, mock_ctx, user=None)

        call_kwargs = mock_ctx.send.call_args.kwargs
        embed = call_kwargs["embed"]

        assert "GIF" in embed.description

    @pytest.mark.asyncio
    async def test_avatar_no_gif_for_static(self, info_cog, mock_user):
        """Should not include GIF link for static avatars."""
        mock_ctx = MagicMock()
        mock_ctx.author = mock_user
        mock_ctx.send = AsyncMock()

        # Make avatar not animated
        mock_user.display_avatar.is_animated = MagicMock(return_value=False)

        await info_cog.avatar.callback(info_cog, mock_ctx, user=None)

        call_kwargs = mock_ctx.send.call_args.kwargs
        embed = call_kwargs["embed"]

        assert "GIF" not in embed.description


# =============================================================================
# Edge Cases and Error Handling Tests
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and error conditions."""

    def test_build_user_info_embed_no_display_name(self, info_cog, mock_user):
        """Should handle users without display_name attribute."""
        delattr(mock_user, "display_name")

        embed = info_cog._build_user_info_embed(mock_user, include_roles=False)

        # Should use name as fallback
        assert isinstance(embed, discord.Embed)
        assert "testuser" in embed.title.lower()

    def test_build_user_info_embed_member_no_top_role(self, info_cog, mock_member):
        """Should handle members where top role is @everyone."""
        everyone_role = MagicMock()
        everyone_role.name = "@everyone"
        mock_member.top_role = everyone_role
        mock_member.roles = [everyone_role]

        embed = info_cog._build_user_info_embed(mock_member, include_roles=False)

        # Should not crash
        assert isinstance(embed, discord.Embed)

    def test_build_user_info_embed_many_roles(self, info_cog, mock_member):
        """Should limit roles display to top 10."""
        # Create 15 roles
        everyone_role = MagicMock()
        everyone_role.name = "@everyone"
        everyone_role.position = 0

        roles = [everyone_role]
        for i in range(15):
            role = MagicMock()
            role.name = f"Role{i}"
            role.position = i + 1
            role.mention = f"<@&{i}>"
            roles.append(role)

        mock_member.roles = roles

        embed = info_cog._build_user_info_embed(mock_member, include_roles=True)

        # Should limit to 10 roles (excluding @everyone)
        roles_field = next(field for field in embed.fields if "Roles" in field.name)
        role_mentions = roles_field.value.count("<@&")
        assert role_mentions == 10

    def test_build_serverinfo_embed_no_owner(self, info_cog, mock_guild):
        """Should handle guilds where owner is not cached."""
        mock_guild.owner = None

        embed = info_cog._build_serverinfo_embed(mock_guild)

        # Should not crash and should not have Owner field
        field_names = [field.name for field in embed.fields]
        assert "Owner" not in field_names

    def test_build_serverinfo_embed_no_features(self, info_cog, mock_guild):
        """Should handle guilds with no features."""
        mock_guild.features = []

        embed = info_cog._build_serverinfo_embed(mock_guild)

        # Should not crash
        assert isinstance(embed, discord.Embed)

    @pytest.mark.asyncio
    async def test_message_info_dm_channel(self, info_cog, mock_interaction, mock_message):
        """Should handle messages in DM channels."""
        # Make channel a DM (no mention attribute)
        mock_message.channel = MagicMock()
        delattr(mock_message.channel, "mention")
        mock_message.channel.name = "DM"

        await info_cog._message_info_context_menu(mock_interaction, mock_message)

        call_kwargs = mock_interaction.response.send_message.call_args.kwargs
        embed = call_kwargs["embed"]
        channel_field = next(field for field in embed.fields if field.name == "Channel")

        assert "DM" in channel_field.value
