"""Now-playing view with YouTube, Download, and AI buttons (+1 Similar / Radio)."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, ClassVar

import discord

from ....domain.recommendations.entities import RecommendationRequest
from ....domain.shared.types import DiscordSnowflake, HttpUrlStr, NonEmptyStr
from ....utils.logging import get_logger
from ....utils.reply import truncate
from ..guards.voice_guards import (
    check_user_in_voice,
)
from .base_view import (
    BaseInteractiveView,
)
from .download_view import (
    add_track_link_buttons,
)

if TYPE_CHECKING:
    from ....config.container import Container
    from ....domain.music.entities import Track

logger = get_logger(__name__)


class NowPlayingView(BaseInteractiveView):
    """YouTube/Download links plus AI-powered '+1 Similar' and 'Radio' buttons."""

    _MAX_GUILD_LOCKS: ClassVar[int] = 256
    _guild_locks: ClassVar[dict[DiscordSnowflake, asyncio.Lock]] = {}

    def __init__(
        self,
        *,
        webpage_url: HttpUrlStr,
        title: NonEmptyStr,
        guild_id: DiscordSnowflake,
        container: Container,
        timeout: float = 300.0,
    ) -> None:
        super().__init__(timeout=timeout)
        self.webpage_url = webpage_url
        self.title = title
        self.guild_id = guild_id
        self._container = container

        add_track_link_buttons(self, webpage_url)

        if not container.ai_enabled:
            self.remove_item(self.similar_button)
            self.remove_item(self.radio_button)

    @classmethod
    def _get_lock(cls, guild_id: DiscordSnowflake) -> asyncio.Lock:
        if guild_id not in cls._guild_locks:
            if len(cls._guild_locks) >= cls._MAX_GUILD_LOCKS:
                unlocked = [gid for gid, lk in cls._guild_locks.items() if not lk.locked()]
                for gid in unlocked:
                    del cls._guild_locks[gid]
            cls._guild_locks[guild_id] = asyncio.Lock()
        return cls._guild_locks[guild_id]

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await check_user_in_voice(interaction, self.guild_id)

    # ── +1 Similar: quick-add one track ────────────────────────────────

    @discord.ui.button(label="+1 Similar", style=discord.ButtonStyle.primary)
    async def similar_button(
        self, interaction: discord.Interaction, button: discord.ui.Button[NowPlayingView]
    ) -> None:
        lock = self._get_lock(self.guild_id)

        if lock.locked():
            await interaction.response.send_message(
                "A similar track search is already in progress, please wait.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        async with lock:
            edited = False
            try:
                button.disabled = True
                button.label = "Finding..."
                await self._try_edit_message()

                current = await self._get_current_track(interaction)
                if current is None:
                    return

                request = RecommendationRequest(
                    base_track_title=current.title,
                    base_track_artist=current.artist or current.uploader,
                    count=1,
                )
                recommendations = await self._container.shuffle_ai_client.get_recommendations(
                    request
                )

                if not recommendations:
                    await interaction.followup.send(
                        "Could not generate a recommendation. Try again later.",
                        ephemeral=True,
                    )
                    return

                rec = recommendations[0]

                track = await self._container.audio_resolver.resolve(rec.query)
                if not track:
                    await interaction.followup.send(
                        f"Could not find a playable track for: {rec.display_text}",
                        ephemeral=True,
                    )
                    return

                track = track.model_copy(
                    update={"is_from_recommendation": True, "is_direct_request": True}
                )

                user = interaction.user
                result = await self._container.queue_service.enqueue_next(
                    guild_id=self.guild_id,
                    track=track,
                    user_id=user.id,
                    user_name=user.display_name,
                )

                if not result.success:
                    await interaction.followup.send(result.message, ephemeral=True)
                    return

                resolved_track = result.track or track

                await interaction.followup.send(
                    f"Queued next: **{truncate(resolved_track.title, 60)}**",
                    ephemeral=True,
                )

                button.disabled = False
                button.label = "+1 Similar"
                if self._message:
                    from ..services.embed_builder import build_now_playing_embed

                    embed = build_now_playing_embed(current, next_track=resolved_track)
                    await self._try_edit_message(embed=embed)
                edited = True

            except Exception:
                logger.exception("Error in similar button handler")
                await interaction.followup.send(
                    "An error occurred while finding similar tracks. Please try again.",
                    ephemeral=True,
                )
            finally:
                if not edited:
                    button.disabled = False
                    button.label = "+1 Similar"
                    await self._try_edit_message()

    # ── Radio: seed from current track, show RadioView with rerolls ───

    @discord.ui.button(label="Radio", style=discord.ButtonStyle.secondary)
    async def radio_button(
        self, interaction: discord.Interaction, _button: discord.ui.Button[NowPlayingView]
    ) -> None:
        radio_service = self._container.radio_service

        if radio_service.is_enabled(self.guild_id):
            await interaction.response.send_message(
                "Radio is already active. Use `/radio off` to disable it.",
                ephemeral=True,
            )
            return

        from ..views.radio_count_view import RadioCountView

        view = RadioCountView(
            guild_id=self.guild_id,
            container=self._container,
        )
        await interaction.response.send_message(
            "How many songs should radio queue?",
            view=view,
            ephemeral=True,
        )

    # ── Shared helpers ─────────────────────────────────────────────────

    async def _get_current_track(self, interaction: discord.Interaction) -> Track | None:
        """Get the current track, or send an ephemeral error and return None."""
        session = await self._container.session_repository.get(self.guild_id)
        if session is None or session.current_track is None:
            await interaction.followup.send("Nothing is playing.", ephemeral=True)
            return None
        return session.current_track

    async def on_timeout(self) -> None:
        self._disable_buttons()
        if self._message is not None:
            try:
                await self._message.edit(view=self)
            except discord.HTTPException:
                pass

    async def _try_edit_message(self, *, embed: discord.Embed | None = None) -> None:
        if self._message is None:
            return
        try:
            if embed is not None:
                await self._message.edit(embed=embed, view=self)
            else:
                await self._message.edit(view=self)
        except discord.HTTPException:
            pass
