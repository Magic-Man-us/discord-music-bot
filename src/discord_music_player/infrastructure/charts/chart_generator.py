"""Discord-dark-themed matplotlib chart generator for analytics."""

from __future__ import annotations

import asyncio
import io

import matplotlib

matplotlib.use("Agg")

import discord  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

# Discord dark theme colors
BG_COLOR = "#2C2F33"
TEXT_COLOR = "#FFFFFF"
ACCENT_COLOR = "#5865F2"
GRID_COLOR = "#40444B"


class ChartGenerator:
    """Stateless chart renderer. All methods are sync and should be called via asyncio.to_thread."""

    def _apply_theme(self, fig: plt.Figure, ax: plt.Axes) -> None:
        fig.patch.set_facecolor(BG_COLOR)
        ax.set_facecolor(BG_COLOR)
        ax.tick_params(colors=TEXT_COLOR)
        ax.xaxis.label.set_color(TEXT_COLOR)
        ax.yaxis.label.set_color(TEXT_COLOR)
        ax.title.set_color(TEXT_COLOR)
        for spine in ax.spines.values():
            spine.set_color(GRID_COLOR)

    def _fig_to_bytes(self, fig: plt.Figure) -> bytes:
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=100, bbox_inches="tight", facecolor=fig.get_facecolor())
        plt.close(fig)
        buf.seek(0)
        return buf.read()

    def horizontal_bar_chart(
        self,
        labels: list[str],
        values: list[int | float],
        title: str,
        color: str = ACCENT_COLOR,
    ) -> bytes:
        fig, ax = plt.subplots(figsize=(8, max(3, len(labels) * 0.5 + 1)))
        self._apply_theme(fig, ax)

        y_pos = range(len(labels))
        ax.barh(y_pos, values, color=color, height=0.6)
        ax.set_yticks(y_pos)
        ax.set_yticklabels(labels, fontsize=9)
        ax.invert_yaxis()
        ax.set_title(title, fontsize=14, fontweight="bold", pad=12)
        ax.set_xlabel("Plays", fontsize=10)
        ax.grid(axis="x", color=GRID_COLOR, alpha=0.3)

        for i, v in enumerate(values):
            ax.text(v + max(values) * 0.01, i, str(int(v)), va="center", color=TEXT_COLOR, fontsize=9)

        return self._fig_to_bytes(fig)

    def line_chart(
        self,
        x_labels: list[str],
        values: list[int | float],
        title: str,
    ) -> bytes:
        fig, ax = plt.subplots(figsize=(10, 4))
        self._apply_theme(fig, ax)

        ax.plot(range(len(x_labels)), values, color=ACCENT_COLOR, linewidth=2, marker="o", markersize=4)
        ax.fill_between(range(len(x_labels)), values, alpha=0.15, color=ACCENT_COLOR)
        ax.set_xticks(range(len(x_labels)))
        ax.set_xticklabels(x_labels, rotation=45, ha="right", fontsize=7)
        ax.set_title(title, fontsize=14, fontweight="bold", pad=12)
        ax.set_ylabel("Plays", fontsize=10)
        ax.grid(color=GRID_COLOR, alpha=0.3)

        return self._fig_to_bytes(fig)

    def bar_chart(
        self,
        labels: list[str],
        values: list[int | float],
        title: str,
        color: str = ACCENT_COLOR,
    ) -> bytes:
        fig, ax = plt.subplots(figsize=(10, 4))
        self._apply_theme(fig, ax)

        ax.bar(range(len(labels)), values, color=color, width=0.6)
        ax.set_xticks(range(len(labels)))
        ax.set_xticklabels(labels, fontsize=9)
        ax.set_title(title, fontsize=14, fontweight="bold", pad=12)
        ax.set_ylabel("Plays", fontsize=10)
        ax.grid(axis="y", color=GRID_COLOR, alpha=0.3)

        return self._fig_to_bytes(fig)

    def pie_chart(
        self,
        labels: list[str],
        values: list[int | float],
        title: str,
    ) -> bytes:
        fig, ax = plt.subplots(figsize=(7, 7))
        fig.patch.set_facecolor(BG_COLOR)
        ax.set_facecolor(BG_COLOR)

        colors = plt.cm.Set3.colors[: len(labels)]
        wedges, texts, autotexts = ax.pie(
            values,
            labels=labels,
            autopct="%1.0f%%",
            colors=colors,
            textprops={"color": TEXT_COLOR, "fontsize": 9},
            pctdistance=0.8,
            startangle=90,
        )
        for autotext in autotexts:
            autotext.set_fontsize(8)
            autotext.set_color(TEXT_COLOR)

        ax.set_title(title, fontsize=14, fontweight="bold", color=TEXT_COLOR, pad=12)

        return self._fig_to_bytes(fig)

    @staticmethod
    def to_discord_file(png_bytes: bytes, filename: str = "chart.png") -> discord.File:
        return discord.File(io.BytesIO(png_bytes), filename=filename)

    async def async_horizontal_bar_chart(self, *args, **kwargs) -> bytes:
        return await asyncio.to_thread(self.horizontal_bar_chart, *args, **kwargs)

    async def async_line_chart(self, *args, **kwargs) -> bytes:
        return await asyncio.to_thread(self.line_chart, *args, **kwargs)

    async def async_bar_chart(self, *args, **kwargs) -> bytes:
        return await asyncio.to_thread(self.bar_chart, *args, **kwargs)

    async def async_pie_chart(self, *args, **kwargs) -> bytes:
        return await asyncio.to_thread(self.pie_chart, *args, **kwargs)
