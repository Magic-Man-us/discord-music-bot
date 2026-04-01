"""View with per-track re-roll buttons and Accept for radio recommendations."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord

from discord_music_player.domain.shared.types import DiscordSnowflake, TrackTitleStr
from discord_music_player.infrastructure.discord.guards.voice_guards import check_user_in_voice
from discord_music_player.infrastructure.discord.views.base_view import BaseInteractiveView
from discord_music_player.utils.reply import truncate

if TYPE_CHECKING:
    from ....config.container import Container
    from ....domain.music.entities import Track

logger = logging.getLogger(__name__)

_MAX_REROLL_BUTTONS = 5
_VIEW_TIMEOUT = 300.0


def build_up_next_embed(
    tracks: list[Track],
    seed_title: TrackTitleStr | None,
) -> discord.Embed:
    embed = discord.Embed(
        title="Radio Enabled",
        description=f"Playing similar tracks based on **{seed_title}**"
        if seed_title
        else "Radio active",
        color=discord.Color.purple(),
    )

    if tracks:
        lines = [f"{idx}. {truncate(t.title, 60)}" for idx, t in enumerate(tracks, start=1)]
        embed.add_field(name="Up Next", value="\n".join(lines), inline=False)
    else:
        embed.add_field(name="Up Next", value="No tracks queued", inline=False)

    return embed


class RadioView(BaseInteractiveView):
    """Interactive radio panel allowing per-track re-rolls before locking in the selection."""

    def __init__(
        self,
        *,
        guild_id: DiscordSnowflake,
        container: Container,
        tracks: list[Track],
        seed_title: TrackTitleStr | None = None,
        queue_start_position: int = 0,
    ) -> None:
        super().__init__(timeout=_VIEW_TIMEOUT)
        self._guild_id = guild_id
        self._container = container
        self._tracks: list[Track] = list(tracks)
        self._seed_title = seed_title
        self._reroll_in_progress = False

        for i, _track in enumerate(tracks[:_MAX_REROLL_BUTTONS]):
            self._add_reroll_button(index=i, queue_position=queue_start_position + i)

    def _add_reroll_button(self, *, index: int, queue_position: int) -> None:
        button = discord.ui.Button[RadioView](
            label=str(index + 1),
            style=discord.ButtonStyle.secondary,
            row=0,
        )

        async def on_reroll(interaction: discord.Interaction) -> None:
            await self._handle_reroll(interaction, index=index, queue_position=queue_position)

        button.callback = on_reroll
        self.add_item(button)

    async def _handle_reroll(
        self, interaction: discord.Interaction, *, index: int, queue_position: int
    ) -> None:
        if self._reroll_in_progress:
            await interaction.response.send_message(
                "A re-roll is already in progress, please wait.",
                ephemeral=True,
            )
            return

        self._reroll_in_progress = True
        self._set_reroll_buttons_disabled(True)
        await interaction.response.edit_message(view=self)

        try:
            user = interaction.user
            new_track = await self._container.radio_service.reroll_track(
                guild_id=self._guild_id,
                queue_position=queue_position,
                user_id=user.id,
                user_name=user.display_name,
            )

            if new_track is None:
                await interaction.followup.send(
                    "Couldn't generate a replacement track.",
                    ephemeral=True,
                )
                self._set_reroll_buttons_disabled(False)
                await interaction.edit_original_response(view=self)
                return

            self._tracks[index] = new_track

            self._set_reroll_buttons_disabled(False)
            embed = build_up_next_embed(self._tracks, self._seed_title)
            await interaction.edit_original_response(embed=embed, view=self)
        except Exception:
            logger.exception("Error in reroll button handler")
            await interaction.followup.send(
                "An error occurred while re-rolling. Please try again.",
                ephemeral=True,
            )
            self._set_reroll_buttons_disabled(False)
            try:
                await interaction.edit_original_response(view=self)
            except discord.HTTPException:
                pass
        finally:
            self._reroll_in_progress = False

    def _set_reroll_buttons_disabled(self, disabled: bool) -> None:
        for item in self.children:
            if isinstance(item, discord.ui.Button) and item.row == 0:
                item.disabled = disabled

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.success, row=1)
    async def accept_button(
        self, interaction: discord.Interaction, _button: discord.ui.Button[RadioView]
    ) -> None:
        if self._reroll_in_progress:
            await interaction.response.send_message(
                "A re-roll is in progress, please wait before accepting.",
                ephemeral=True,
            )
            return

        self._disable_buttons()
        self.stop()

        embed = build_up_next_embed(self._tracks, self._seed_title)
        embed.set_footer(text="Selection accepted")
        await interaction.response.edit_message(embed=embed, view=self)

    async def on_timeout(self) -> None:
        self._finish_view()
        await self._delete_message(delay=10.0)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await check_user_in_voice(interaction, self._guild_id)
