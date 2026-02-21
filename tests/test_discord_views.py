"""
Unit Tests for Discord Views and UI Components

Tests for:
- DownloadView: Download button view with YouTube and Cobalt links

Uses pytest with async/await patterns and Discord UI mocking.
Ensures proper button creation, initialization, and timeout handling.
"""

import asyncio
import urllib.parse
from unittest.mock import MagicMock, patch

import discord
import pytest

from discord_music_player.infrastructure.discord.views.download_view import (
    DownloadView,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def mock_discord_event_loop():
    """Mock the event loop for Discord UI views (auto-applied to all tests)."""
    loop = MagicMock(spec=asyncio.AbstractEventLoop)
    future = MagicMock()
    loop.create_future.return_value = future

    with patch("asyncio.get_running_loop", return_value=loop):
        yield loop


# =============================================================================
# DownloadView Tests
# =============================================================================


class TestDownloadView:
    """Tests for DownloadView - download buttons for tracks."""

    @pytest.fixture
    def sample_url(self):
        """Sample YouTube URL for testing."""
        return "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

    @pytest.fixture
    def sample_title(self):
        """Sample track title for testing."""
        return "Never Gonna Give You Up"

    # Initialization Tests

    def test_initialization_with_defaults(self, sample_url, sample_title):
        """Should initialize view with default timeout."""
        view = DownloadView(
            webpage_url=sample_url,
            title=sample_title,
        )

        assert view.webpage_url == sample_url
        assert view.title == sample_title
        assert view.timeout == 300.0

    def test_initialization_with_custom_timeout(self, sample_url, sample_title):
        """Should initialize view with custom timeout."""
        view = DownloadView(
            webpage_url=sample_url,
            title=sample_title,
            timeout=600.0,
        )

        assert view.timeout == 600.0

    def test_initialization_creates_buttons(self, sample_url, sample_title):
        """Should create YouTube and Download buttons on initialization."""
        view = DownloadView(
            webpage_url=sample_url,
            title=sample_title,
        )

        # Should have 2 buttons
        assert len(view.children) == 2

    # Button Creation Tests

    def test_youtube_button_created(self, sample_url, sample_title):
        """Should create YouTube link button with correct properties."""
        view = DownloadView(
            webpage_url=sample_url,
            title=sample_title,
        )

        # Find YouTube button
        youtube_button = None
        for child in view.children:
            if isinstance(child, discord.ui.Button) and child.label and "YouTube" in child.label:
                youtube_button = child
                break

        assert youtube_button is not None
        assert youtube_button.style == discord.ButtonStyle.link
        assert youtube_button.url == sample_url
        assert youtube_button.label is not None
        assert "📺" in youtube_button.label

    def test_download_button_created(self, sample_url, sample_title):
        """Should create Download button with Cobalt URL."""
        view = DownloadView(
            webpage_url=sample_url,
            title=sample_title,
        )

        # Find Download button
        download_button = None
        for child in view.children:
            if isinstance(child, discord.ui.Button) and child.label and "Download" in child.label:
                download_button = child
                break

        assert download_button is not None
        assert download_button.style == discord.ButtonStyle.link
        assert "cobalt.tools" in download_button.url
        assert download_button.label is not None
        assert "⬇️" in download_button.label

    def test_cobalt_url_encoding(self, sample_url, sample_title):
        """Should properly encode URL for Cobalt service."""
        view = DownloadView(
            webpage_url=sample_url,
            title=sample_title,
        )

        # Get download button URL
        download_button = None
        for child in view.children:
            if isinstance(child, discord.ui.Button) and child.label and "Download" in child.label:
                download_button = child
                break

        assert download_button is not None
        expected_encoded = urllib.parse.quote(sample_url, safe="")
        assert expected_encoded in download_button.url
        assert download_button.url.startswith("https://cobalt.tools/#")

    # URL Encoding Tests

    def test_encode_url_basic(self, sample_title):
        """Test URL encoding with basic URL."""
        view = DownloadView(
            webpage_url="https://example.com/test",
            title=sample_title,
        )

        encoded = view._encode_url("https://example.com/test")
        assert encoded == urllib.parse.quote("https://example.com/test", safe="")

    def test_encode_url_with_special_characters(self, sample_title):
        """Test URL encoding with special characters."""
        url_with_special = "https://example.com/test?param=value&other=123"
        view = DownloadView(
            webpage_url=url_with_special,
            title=sample_title,
        )

        encoded = view._encode_url(url_with_special)
        # Should encode all special characters
        assert "?" not in encoded
        assert "&" not in encoded
        assert "=" not in encoded

    def test_encode_url_with_unicode(self, sample_title):
        """Test URL encoding with Unicode characters."""
        url_with_unicode = "https://example.com/音楽"
        view = DownloadView(
            webpage_url=url_with_unicode,
            title=sample_title,
        )

        encoded = view._encode_url(url_with_unicode)
        # Should be properly encoded
        assert isinstance(encoded, str)
        # Unicode should be percent-encoded
        assert "音楽" not in encoded

    # Button Properties Tests

    def test_all_buttons_are_links(self, sample_url, sample_title):
        """All buttons should be link-style buttons."""
        view = DownloadView(
            webpage_url=sample_url,
            title=sample_title,
        )

        for child in view.children:
            if isinstance(child, discord.ui.Button):
                assert child.style == discord.ButtonStyle.link

    def test_buttons_have_urls(self, sample_url, sample_title):
        """All buttons should have URLs set."""
        view = DownloadView(
            webpage_url=sample_url,
            title=sample_title,
        )

        for child in view.children:
            if isinstance(child, discord.ui.Button):
                assert child.url is not None
                assert child.url.startswith("https://")

    def test_buttons_have_labels(self, sample_url, sample_title):
        """All buttons should have non-empty labels."""
        view = DownloadView(
            webpage_url=sample_url,
            title=sample_title,
        )

        for child in view.children:
            if isinstance(child, discord.ui.Button):
                assert child.label is not None
                assert len(child.label) > 0


