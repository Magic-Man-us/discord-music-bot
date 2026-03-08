"""Discord-dark-themed matplotlib chart generator for analytics."""

from __future__ import annotations

import asyncio
import io
import threading
from collections.abc import Sequence
from typing import Any, cast

import matplotlib
import matplotlib.axes
import matplotlib.figure
import matplotlib.pyplot as plt
import matplotlib.text

matplotlib.use("Agg")

import discord  # noqa: E402

from discord_music_player.domain.shared.constants import AnalyticsConstants  # noqa: E402
from discord_music_player.domain.shared.types import NonEmptyStr  # noqa: E402

_BG = AnalyticsConstants.CHART_BG_COLOR
_TEXT = AnalyticsConstants.CHART_TEXT_COLOR
_ACCENT = AnalyticsConstants.CHART_ACCENT_COLOR
_GRID = AnalyticsConstants.CHART_GRID_COLOR
_DPI = AnalyticsConstants.CHART_DPI
_LABEL_FS = AnalyticsConstants.CHART_LABEL_FONTSIZE
_TITLE_FS = AnalyticsConstants.CHART_TITLE_FONTSIZE
_VALUE_OFFSET = AnalyticsConstants.CHART_VALUE_LABEL_OFFSET

# matplotlib's pyplot state machine is NOT thread-safe.
# A single lock serialises all chart rendering across asyncio.to_thread calls.
_render_lock = threading.Lock()


class ChartGenerator:
    """Thread-safe, stateless chart renderer for Discord embeds."""

    # ── Theme ────────────────────────────────────────────────────────

    @staticmethod
    def _apply_theme(fig: matplotlib.figure.Figure, ax: matplotlib.axes.Axes) -> None:
        fig.patch.set_facecolor(_BG)
        ax.set_facecolor(_BG)
        ax.tick_params(colors=_TEXT)
        ax.xaxis.label.set_color(_TEXT)
        ax.yaxis.label.set_color(_TEXT)
        ax.title.set_color(_TEXT)
        for spine in ax.spines.values():
            spine.set_color(_GRID)

    @staticmethod
    def _fig_to_bytes(fig: matplotlib.figure.Figure) -> bytes:
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=_DPI, bbox_inches="tight", facecolor=fig.get_facecolor())
        plt.close(fig)
        buf.seek(0)
        return buf.read()

    # ── Sync chart methods (called inside _render_lock) ──────────────

    def horizontal_bar_chart(
        self,
        labels: Sequence[str],
        values: Sequence[int | float],
        title: NonEmptyStr,
        color: str = _ACCENT,
    ) -> bytes:
        with _render_lock:
            fig, ax = plt.subplots(figsize=(8, max(3, len(labels) * 0.5 + 1)))
            self._apply_theme(fig, ax)

            y_pos = range(len(labels))
            ax.barh(y_pos, values, color=color, height=0.6)
            ax.set_yticks(y_pos)
            ax.set_yticklabels(labels, fontsize=_LABEL_FS)
            ax.invert_yaxis()
            ax.set_title(title, fontsize=_TITLE_FS, fontweight="bold", pad=12)
            ax.set_xlabel("Plays", fontsize=10)
            ax.grid(axis="x", color=_GRID, alpha=0.3)

            peak = max(values) if values else 1
            for i, v in enumerate(values):
                ax.text(
                    v + peak * _VALUE_OFFSET, i, str(int(v)),
                    va="center", color=_TEXT, fontsize=_LABEL_FS,
                )

            return self._fig_to_bytes(fig)

    def line_chart(
        self,
        x_labels: Sequence[str],
        values: Sequence[int | float],
        title: NonEmptyStr,
    ) -> bytes:
        with _render_lock:
            fig, ax = plt.subplots(figsize=(10, 4))
            self._apply_theme(fig, ax)

            x_range = range(len(x_labels))
            ax.plot(x_range, values, color=_ACCENT, linewidth=2, marker="o", markersize=4)
            ax.fill_between(x_range, values, alpha=0.15, color=_ACCENT)
            ax.set_xticks(x_range)
            ax.set_xticklabels(x_labels, rotation=45, ha="right", fontsize=7)
            ax.set_title(title, fontsize=_TITLE_FS, fontweight="bold", pad=12)
            ax.set_ylabel("Plays", fontsize=10)
            ax.grid(color=_GRID, alpha=0.3)

            return self._fig_to_bytes(fig)

    def bar_chart(
        self,
        labels: Sequence[str],
        values: Sequence[int | float],
        title: NonEmptyStr,
        color: str = _ACCENT,
    ) -> bytes:
        with _render_lock:
            fig, ax = plt.subplots(figsize=(10, 4))
            self._apply_theme(fig, ax)

            ax.bar(range(len(labels)), values, color=color, width=0.6)
            ax.set_xticks(range(len(labels)))
            ax.set_xticklabels(labels, fontsize=_LABEL_FS)
            ax.set_title(title, fontsize=_TITLE_FS, fontweight="bold", pad=12)
            ax.set_ylabel("Plays", fontsize=10)
            ax.grid(axis="y", color=_GRID, alpha=0.3)

            return self._fig_to_bytes(fig)

    def pie_chart(
        self,
        labels: Sequence[str],
        values: Sequence[int | float],
        title: NonEmptyStr,
    ) -> bytes:
        with _render_lock:
            fig, ax = plt.subplots(figsize=(7, 7))
            self._apply_theme(fig, ax)

            palette = plt.cm.Set3.colors  # type: ignore[attr-defined]
            n = len(labels)
            colors = (palette * ((n // len(palette)) + 1))[:n] if n > 0 else palette

            # autopct is set → pie() always returns (wedges, texts, autotexts)
            pie_result: Any = ax.pie(
                values,
                labels=labels,
                autopct="%1.0f%%",
                colors=colors,
                textprops={"color": _TEXT, "fontsize": _LABEL_FS},
                pctdistance=0.8,
                startangle=90,
            )
            autotexts = cast(list[matplotlib.text.Text], pie_result[2])
            for autotext in autotexts:
                autotext.set_fontsize(8)
                autotext.set_color(_TEXT)

            ax.set_title(title, fontsize=_TITLE_FS, fontweight="bold", color=_TEXT, pad=12)

            return self._fig_to_bytes(fig)

    # ── Discord file helper ──────────────────────────────────────────

    @staticmethod
    def to_discord_file(png_bytes: bytes, filename: str = "chart.png") -> discord.File:
        return discord.File(io.BytesIO(png_bytes), filename=filename)

    # ── Typed async wrappers ─────────────────────────────────────────

    async def async_horizontal_bar_chart(
        self,
        labels: Sequence[str],
        values: Sequence[int | float],
        title: NonEmptyStr,
        color: str = _ACCENT,
    ) -> bytes:
        return await asyncio.to_thread(self.horizontal_bar_chart, labels, values, title, color)

    async def async_line_chart(
        self,
        x_labels: Sequence[str],
        values: Sequence[int | float],
        title: NonEmptyStr,
    ) -> bytes:
        return await asyncio.to_thread(self.line_chart, x_labels, values, title)

    async def async_bar_chart(
        self,
        labels: Sequence[str],
        values: Sequence[int | float],
        title: NonEmptyStr,
        color: str = _ACCENT,
    ) -> bytes:
        return await asyncio.to_thread(self.bar_chart, labels, values, title, color)

    async def async_pie_chart(
        self,
        labels: Sequence[str],
        values: Sequence[int | float],
        title: NonEmptyStr,
    ) -> bytes:
        return await asyncio.to_thread(self.pie_chart, labels, values, title)
