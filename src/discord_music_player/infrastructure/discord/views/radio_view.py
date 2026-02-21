"""View with per-track re-roll buttons and Accept for radio recommendations."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord

from discord_music_player.infrastructure.discord.guards.voice_guards import check_user_in_voice
from discord_music_player.utils.reply import truncate

if TYPE_CHECKING:
    from ....config.container import Container
    from ....domain.music.entities import Track

logger = logging.getLogger(__name__)

# Max tracks shown as re-roll buttons (Discord allows 5 buttons per row)
_MAX_REROLL_BUTTONS = 5

# View timeout in seconds (5 minutes)
_VIEW_TIMEOUT = 300.0


def build_up_next_embed(
    tracks: list[Track],
    seed_title: str | None,
) -> discord.Embed:
    """Build the radio embed showing the Up Next track list."""
    embed = discord.Embed(
        title="\U0001f4fb Radio Enabled",
        description=f"Playing similar tracks based on **{seed_title}**" if seed_title else "Radio active",
        color=discord.Color.purple(),
    )

    if tracks:
        lines = [f"{idx}. {truncate(t.title, 60)}" for idx, t in enumerate(tracks, start=1)]
        embed.add_field(
            name="\U0001f3b5 Up Next",
            value="\n".join(lines),
            inline=False,
        )
    else:
        embed.add_field(name="\U0001f3b5 Up Next", value="No tracks queued", inline=False)

    return embed


class RerollButton(discord.ui.Button["RadioView"]):
    """A numbered button that re-rolls a single radio track."""

    def __init__(self, index: int, queue_position: int) -> None:
        super().__init__(
            label=str(index + 1),
            style=discord.ButtonStyle.secondary,
            row=0,
        )
        self.index = index
        self.queue_position = queue_position

    async def callback(self, interaction: discord.Interaction) -> None:
        assert self.view is not None
        view: RadioView = self.view

        if view._reroll_in_progress:
            await interaction.response.send_message(
                "A re-roll is already in progress, please wait.",
                ephemeral=True,
            )
            return

        view._reroll_in_progress = True

        # Disable all reroll buttons to prevent concurrent clicks
        view._set_reroll_buttons_disabled(True)
        await interaction.response.edit_message(view=view)

        try:
            user = interaction.user
            new_track = await view._container.radio_service.reroll_track(
                guild_id=view._guild_id,
                queue_position=self.queue_position,
                user_id=user.id,
                user_name=getattr(user, "display_name", user.name),
            )

            if new_track is None:
                await interaction.followup.send(
                    "\u274c Couldn't generate a replacement track.",
                    ephemeral=True,
                )
                # Re-enable buttons even on failure
                view._set_reroll_buttons_disabled(False)
                await interaction.edit_original_response(view=view)
                return

            # Update internal track list
            view._tracks[self.index] = new_track

            # Rebuild embed and edit original message
            view._set_reroll_buttons_disabled(False)
            embed = build_up_next_embed(view._tracks, view._seed_title)
            await interaction.edit_original_response(embed=embed, view=view)
        finally:
            view._reroll_in_progress = False


class AcceptButton(discord.ui.Button["RadioView"]):
    """Locks in the current selection and disables all buttons."""

    def __init__(self) -> None:
        super().__init__(
            label="\u2705 Accept",
            style=discord.ButtonStyle.success,
            row=1,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        assert self.view is not None
        view: RadioView = self.view

        # Disable all buttons
        for item in view.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True

        view.stop()

        embed = build_up_next_embed(view._tracks, view._seed_title)
        embed.set_footer(text="Selection accepted")
        await interaction.response.edit_message(embed=embed, view=view)


class RadioView(discord.ui.View):
    """Shows numbered re-roll buttons for each radio track, plus an Accept button."""

    def __init__(
        self,
        *,
        guild_id: int,
        container: Container,
        tracks: list[Track],
        seed_title: str | None = None,
        queue_start_position: int = 0,
    ) -> None:
        super().__init__(timeout=_VIEW_TIMEOUT)
        self._guild_id = guild_id
        self._container = container
        self._tracks: list[Track] = list(tracks)
        self._seed_title = seed_title
        self._reroll_in_progress = False
        self._message: discord.Message | None = None

        for i, _track in enumerate(tracks[:_MAX_REROLL_BUTTONS]):
            self.add_item(RerollButton(index=i, queue_position=queue_start_position + i))

        self.add_item(AcceptButton())

    def _set_reroll_buttons_disabled(self, disabled: bool) -> None:
        for item in self.children:
            if isinstance(item, RerollButton):
                item.disabled = disabled

    async def on_timeout(self) -> None:
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True

        if self._message is not None:
            try:
                embed = build_up_next_embed(self._tracks, self._seed_title)
                embed.set_footer(text="Re-roll timed out")
                await self._message.edit(embed=embed, view=self)
            except discord.HTTPException:
                pass

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await check_user_in_voice(interaction, self._guild_id)
