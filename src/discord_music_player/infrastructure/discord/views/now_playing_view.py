"""Now-playing view with YouTube, Download, and AI Shuffle buttons."""

from __future__ import annotations

import asyncio
import logging
import urllib.parse
from typing import TYPE_CHECKING, ClassVar

import discord

from discord_music_player.domain.recommendations.entities import RecommendationRequest
from discord_music_player.domain.shared.messages import (
    DiscordUIMessages,
    LogTemplates,
)
from discord_music_player.infrastructure.discord.guards.voice_guards import (
    check_user_in_voice,
)
from discord_music_player.infrastructure.discord.views.base_view import (
    BaseInteractiveView,
)
from discord_music_player.utils.reply import truncate

if TYPE_CHECKING:
    from ....config.container import Container

logger = logging.getLogger(__name__)


class NowPlayingView(BaseInteractiveView):
    """View for now-playing embeds: YouTube link, Download link, and AI Shuffle button."""

    _guild_locks: ClassVar[dict[int, asyncio.Lock]] = {}

    def __init__(
        self,
        *,
        webpage_url: str,
        title: str,
        guild_id: int,
        container: Container,
        timeout: float = 300.0,
    ) -> None:
        super().__init__(timeout=timeout)
        self.webpage_url = webpage_url
        self.title = title
        self.guild_id = guild_id
        self.container = container

        self._add_link_buttons()

    def _add_link_buttons(self) -> None:
        self.add_item(
            discord.ui.Button(
                style=discord.ButtonStyle.link,
                label="\U0001f4fa YouTube",
                url=self.webpage_url,
            )
        )

        cobalt_url = f"https://cobalt.tools/#{urllib.parse.quote(self.webpage_url, safe='')}"
        self.add_item(
            discord.ui.Button(
                style=discord.ButtonStyle.link,
                label="\u2b07\ufe0f Download",
                url=cobalt_url,
            )
        )

    @classmethod
    def _get_lock(cls, guild_id: int) -> asyncio.Lock:
        if guild_id not in cls._guild_locks:
            cls._guild_locks[guild_id] = asyncio.Lock()
        return cls._guild_locks[guild_id]

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await check_user_in_voice(interaction, self.guild_id)

    @discord.ui.button(label="\U0001f500 Shuffle", style=discord.ButtonStyle.primary)
    async def shuffle_button(
        self, interaction: discord.Interaction, button: discord.ui.Button[NowPlayingView]
    ) -> None:
        lock = self._get_lock(self.guild_id)

        if lock.locked():
            await interaction.response.send_message(
                DiscordUIMessages.SHUFFLE_ALREADY_IN_PROGRESS, ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        async with lock:
            edited = False
            try:
                # Disable the shuffle button while processing
                button.disabled = True
                button.label = "\U0001f500 Thinking..."
                await self._try_edit_message()

                # Get current track info for the recommendation
                session = await self.container.session_repository.get(self.guild_id)
                if session is None or session.current_track is None:
                    await interaction.followup.send(
                        DiscordUIMessages.STATE_NOTHING_PLAYING, ephemeral=True
                    )
                    return

                current = session.current_track

                # Get 1 AI recommendation
                request = RecommendationRequest(
                    base_track_title=current.title,
                    base_track_artist=current.artist or current.uploader,
                    count=1,
                )
                recommendations = await self.container.shuffle_ai_client.get_recommendations(
                    request
                )

                if not recommendations:
                    await interaction.followup.send(
                        DiscordUIMessages.SHUFFLE_NO_RECOMMENDATION,
                        ephemeral=True,
                    )
                    return

                rec = recommendations[0]

                # Resolve the recommendation to a playable track
                track = await self.container.audio_resolver.resolve(rec.query)
                if not track:
                    await interaction.followup.send(
                        DiscordUIMessages.SHUFFLE_TRACK_NOT_FOUND.format(
                            display_text=rec.display_text
                        ),
                        ephemeral=True,
                    )
                    return

                # Mark as recommendation
                track = track.model_copy(update={"is_from_recommendation": True})

                # Enqueue as next track
                user = interaction.user
                result = await self.container.queue_service.enqueue_next(
                    guild_id=self.guild_id,
                    track=track,
                    user_id=user.id,
                    user_name=getattr(user, "display_name", user.name),
                )

                if not result.success:
                    await interaction.followup.send(result.message, ephemeral=True)
                    return

                resolved_track = result.track or track

                # Send ephemeral confirmation
                await interaction.followup.send(
                    DiscordUIMessages.SHUFFLE_QUEUED_NEXT.format(
                        track_title=truncate(resolved_track.title, 60)
                    ),
                    ephemeral=True,
                )

                # Re-enable button and update embed with "Next Up" in a single edit
                button.disabled = False
                button.label = "\U0001f500 Shuffle"
                if self._message:
                    from ..services.message_state_manager import MessageStateManager

                    embed = MessageStateManager.build_now_playing_embed(
                        current, next_track=resolved_track
                    )
                    await self._try_edit_message(embed=embed)
                edited = True

            except Exception:
                logger.exception(LogTemplates.SHUFFLE_ERROR)
                await interaction.followup.send(
                    DiscordUIMessages.SHUFFLE_ERROR,
                    ephemeral=True,
                )
            finally:
                # Re-enable the button if the success path didn't already do it
                if not edited:
                    button.disabled = False
                    button.label = "\U0001f500 Shuffle"
                    await self._try_edit_message()

    async def _try_edit_message(self, *, embed: discord.Embed | None = None) -> None:
        """Edit the tracked message, silently ignoring failures."""
        if self._message is None:
            return
        try:
            if embed is not None:
                await self._message.edit(embed=embed, view=self)
            else:
                await self._message.edit(view=self)
        except discord.HTTPException:
            pass
