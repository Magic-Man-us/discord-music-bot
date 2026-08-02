"""Tests for the prebuffering AudioSource wrapper."""

from __future__ import annotations

import threading

import discord

from discord_music_player.config.settings import PrebufferSettings
from discord_music_player.domain.shared.constants import AudioConstants
from discord_music_player.infrastructure.discord.adapters.buffered_source import (
    BufferedAudioSource,
)

FRAME_A = b"\x01" * AudioConstants.PCM_FRAME_BYTES
FRAME_B = b"\x02" * AudioConstants.PCM_FRAME_BYTES
SILENCE = b"\x00" * AudioConstants.PCM_FRAME_BYTES


def _config(**overrides: float | bool) -> PrebufferSettings:
    return PrebufferSettings.model_validate(
        {"buffer_seconds": 0.5, "prefill_seconds": 0.0, **overrides}
    )


class FrameListSource(discord.AudioSource):
    """Yields a fixed list of frames, then EOF."""

    def __init__(self, frames: list[bytes], *, opus: bool = False) -> None:
        self._frames = list(frames)
        self._opus = opus
        self.cleaned = False

    def read(self) -> bytes:
        return self._frames.pop(0) if self._frames else b""

    def is_opus(self) -> bool:
        return self._opus

    def cleanup(self) -> None:
        self.cleaned = True


class StallingSource(discord.AudioSource):
    """Yields one frame, then blocks until released — a stalled network stream."""

    def __init__(self) -> None:
        self.release = threading.Event()
        self._sent = False
        self.cleaned = False

    def read(self) -> bytes:
        if not self._sent:
            self._sent = True
            return FRAME_A
        self.release.wait(timeout=5.0)
        return b""

    def is_opus(self) -> bool:
        return False

    def cleanup(self) -> None:
        self.cleaned = True


def test_frames_pass_through_in_order() -> None:
    source = BufferedAudioSource(FrameListSource([FRAME_A, FRAME_B]), _config())
    assert source.read() == FRAME_A
    assert source.read() == FRAME_B
    source.cleanup()


def test_eof_propagates_after_last_frame() -> None:
    source = BufferedAudioSource(FrameListSource([FRAME_A]), _config())
    assert source.read() == FRAME_A
    assert source.read() == b""
    source.cleanup()


def test_empty_source_reports_eof_immediately() -> None:
    source = BufferedAudioSource(FrameListSource([]), _config())
    assert source.read() == b""
    source.cleanup()


def test_is_opus_delegates_to_wrapped_source() -> None:
    inner = FrameListSource([], opus=True)
    source = BufferedAudioSource(inner, _config())
    assert source.is_opus() is True
    source.cleanup()


def test_cleanup_stops_reader_and_cleans_inner() -> None:
    inner = FrameListSource([FRAME_A])
    source = BufferedAudioSource(inner, _config())
    source.cleanup()
    assert inner.cleaned is True
    assert source._reader.is_alive() is False


def test_underrun_emits_silence_rather_than_ending_playback() -> None:
    """A stalled upstream must not look like EOF — that would skip the track."""
    inner = StallingSource()
    source = BufferedAudioSource(inner, _config())
    assert source.read() == FRAME_A
    assert source.read() == SILENCE
    inner.release.set()
    source.cleanup()


def test_frame_counts_derive_from_pcm_rate() -> None:
    config = PrebufferSettings.model_validate({"buffer_seconds": 5.0, "prefill_seconds": 2.0})
    assert config.buffer_frames == 250
    assert config.prefill_frames == 100
