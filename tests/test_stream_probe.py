"""Tests for the SSRF guard on HttpStreamProbe and the FFmpeg User-Agent allowlist."""

from __future__ import annotations

import pytest

from discord_music_player.infrastructure.audio.stream_probe import _host_is_public
from discord_music_player.infrastructure.discord.adapters.voice_adapter import _SAFE_USER_AGENT_RE


class TestHostIsPublic:
    def test_allows_public_ip(self):
        # Literal public IP — no DNS, deterministic offline.
        assert _host_is_public("http://8.8.8.8/videoplayback?x=1") is True

    @pytest.mark.parametrize(
        "url",
        [
            "http://127.0.0.1:4416/",  # loopback (bgutil provider, redis, etc.)
            "http://169.254.169.254/latest/meta-data/",  # cloud metadata
            "http://10.0.0.5/",  # private
            "http://192.168.1.1/",  # private
            "http://172.16.0.1/",  # private
            "http://[::1]/",  # ipv6 loopback
            "http://0.0.0.0/",  # unspecified
            "http://localhost/",  # resolves to loopback via /etc/hosts
            "http://user:pass@8.8.8.8/",  # embedded credentials
            "not a url",  # no host
        ],
    )
    def test_blocks_non_public_or_malformed(self, url):
        assert _host_is_public(url) is False


class TestUserAgentAllowlist:
    @pytest.mark.parametrize(
        "user_agent",
        [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36",
            "com.google.android.youtube/19.44.38 (Linux; U; Android 14) gzip",
        ],
    )
    def test_accepts_real_user_agents(self, user_agent):
        assert _SAFE_USER_AGENT_RE.match(user_agent)

    @pytest.mark.parametrize(
        "user_agent",
        [
            'x" -af "loudnorm',  # quote breakout into ffmpeg args
            "agent\r\nX-Injected: 1",  # CRLF header injection
            'has"quote',  # embedded double quote
        ],
    )
    def test_rejects_injection_payloads(self, user_agent):
        assert not _SAFE_USER_AGENT_RE.match(user_agent)
