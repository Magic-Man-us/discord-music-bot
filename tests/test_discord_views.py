"""
Unit Tests for Discord Views and UI Components

Tests for:
- DownloadView: Download button view with YouTube and Cobalt links
- NowPlayingView: Now playing controls with download buttons

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
    NowPlayingView,
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

    # Edge Cases

    def test_view_with_very_long_url(self, sample_title):
        """Should handle very long URLs."""
        long_url = "https://youtube.com/watch?v=" + "x" * 500
        view = DownloadView(
            webpage_url=long_url,
            title=sample_title,
        )

        assert view.webpage_url == long_url
        assert len(view.children) == 2

    def test_view_with_minimal_url(self, sample_title):
        """Should handle minimal URL."""
        minimal_url = "https://y.be/abc"
        view = DownloadView(
            webpage_url=minimal_url,
            title=sample_title,
        )

        assert view.webpage_url == minimal_url
        assert len(view.children) == 2

    def test_view_with_zero_timeout(self, sample_url, sample_title):
        """Should allow zero timeout (immediate expiry)."""
        view = DownloadView(
            webpage_url=sample_url,
            title=sample_title,
            timeout=0.0,
        )

        assert view.timeout == 0.0

    def test_view_with_none_timeout(self, sample_url, sample_title):
        """Should allow None timeout (never expires)."""
        view = DownloadView(
            webpage_url=sample_url,
            title=sample_title,
            timeout=None,
        )

        assert view.timeout is None

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


# =============================================================================
# NowPlayingView Tests
# =============================================================================


class TestNowPlayingView:
    """Tests for NowPlayingView - now playing controls with download."""

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
        view = NowPlayingView(
            webpage_url=sample_url,
            title=sample_title,
        )

        assert view.webpage_url == sample_url
        assert view.title == sample_title
        assert view.timeout == 300.0

    def test_initialization_with_custom_timeout(self, sample_url, sample_title):
        """Should initialize view with custom timeout."""
        view = NowPlayingView(
            webpage_url=sample_url,
            title=sample_title,
            timeout=600.0,
        )

        assert view.timeout == 600.0

    def test_initialization_creates_buttons(self, sample_url, sample_title):
        """Should create buttons on initialization."""
        view = NowPlayingView(
            webpage_url=sample_url,
            title=sample_title,
        )

        # Should have 2 buttons (YouTube + Download)
        assert len(view.children) == 2

    # Button Creation Tests

    def test_youtube_button_created(self, sample_url, sample_title):
        """Should create YouTube link button."""
        view = NowPlayingView(
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

    def test_download_button_created(self, sample_url, sample_title):
        """Should create Download button with Cobalt URL."""
        view = NowPlayingView(
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

    def test_cobalt_url_matches_download_view(self, sample_url, sample_title):
        """Should use same Cobalt URL format as DownloadView."""
        now_playing_view = NowPlayingView(
            webpage_url=sample_url,
            title=sample_title,
        )

        download_view = DownloadView(
            webpage_url=sample_url,
            title=sample_title,
        )

        # Get download buttons from both views
        np_download_button = None
        for child in now_playing_view.children:
            if isinstance(child, discord.ui.Button) and child.label and "Download" in child.label:
                np_download_button = child
                break

        dv_download_button = None
        for child in download_view.children:
            if isinstance(child, discord.ui.Button) and child.label and "Download" in child.label:
                dv_download_button = child
                break

        # Both should have same URL structure
        assert np_download_button.url == dv_download_button.url

    # Button Properties Tests

    def test_all_buttons_are_links(self, sample_url, sample_title):
        """All buttons should be link-style buttons."""
        view = NowPlayingView(
            webpage_url=sample_url,
            title=sample_title,
        )

        for child in view.children:
            if isinstance(child, discord.ui.Button):
                assert child.style == discord.ButtonStyle.link

    def test_buttons_have_urls(self, sample_url, sample_title):
        """All buttons should have URLs set."""
        view = NowPlayingView(
            webpage_url=sample_url,
            title=sample_title,
        )

        for child in view.children:
            if isinstance(child, discord.ui.Button):
                assert child.url is not None
                assert child.url.startswith("https://")

    def test_buttons_have_labels(self, sample_url, sample_title):
        """All buttons should have non-empty labels."""
        view = NowPlayingView(
            webpage_url=sample_url,
            title=sample_title,
        )

        for child in view.children:
            if isinstance(child, discord.ui.Button):
                assert child.label is not None
                assert len(child.label) > 0

    # Edge Cases

    def test_view_with_special_characters_in_url(self, sample_title):
        """Should handle URLs with special characters."""
        special_url = "https://youtube.com/watch?v=abc&t=123&list=PLtest"
        view = NowPlayingView(
            webpage_url=special_url,
            title=sample_title,
        )

        assert view.webpage_url == special_url
        # YouTube button should have exact URL
        youtube_button = None
        for child in view.children:
            if isinstance(child, discord.ui.Button) and child.label and "YouTube" in child.label:
                youtube_button = child
                break
        assert youtube_button.url == special_url

    def test_view_with_none_timeout(self, sample_url, sample_title):
        """Should allow None timeout (never expires)."""
        view = NowPlayingView(
            webpage_url=sample_url,
            title=sample_title,
            timeout=None,
        )

        assert view.timeout is None

    def test_view_maintains_url_integrity(self, sample_title):
        """Should not modify the original URL for YouTube button."""
        original_url = "https://youtube.com/watch?v=test&feature=share"
        view = NowPlayingView(
            webpage_url=original_url,
            title=sample_title,
        )

        # YouTube button should have unmodified URL
        youtube_button = None
        for child in view.children:
            if isinstance(child, discord.ui.Button) and child.label and "YouTube" in child.label:
                youtube_button = child
                break

        assert youtube_button.url == original_url


# =============================================================================
# Integration Tests
# =============================================================================


class TestViewIntegration:
    """Integration tests for view usage patterns."""

    def test_both_views_have_same_button_count(self):
        """Both views should have same number of buttons."""
        url = "https://youtube.com/watch?v=test"
        title = "Test Song"

        download_view = DownloadView(webpage_url=url, title=title)
        now_playing_view = NowPlayingView(webpage_url=url, title=title)

        assert len(download_view.children) == len(now_playing_view.children)

    def test_both_views_create_youtube_buttons(self):
        """Both views should create YouTube buttons."""
        url = "https://youtube.com/watch?v=test"
        title = "Test Song"

        download_view = DownloadView(webpage_url=url, title=title)
        now_playing_view = NowPlayingView(webpage_url=url, title=title)

        # Check download view
        has_youtube_download = False
        for child in download_view.children:
            if isinstance(child, discord.ui.Button) and child.label and "YouTube" in child.label:
                has_youtube_download = True
                break

        # Check now playing view
        has_youtube_now_playing = False
        for child in now_playing_view.children:
            if isinstance(child, discord.ui.Button) and child.label and "YouTube" in child.label:
                has_youtube_now_playing = True
                break

        assert has_youtube_download
        assert has_youtube_now_playing

    def test_both_views_create_download_buttons(self):
        """Both views should create Download buttons."""
        url = "https://youtube.com/watch?v=test"
        title = "Test Song"

        download_view = DownloadView(webpage_url=url, title=title)
        now_playing_view = NowPlayingView(webpage_url=url, title=title)

        # Check download view
        has_download_download = False
        for child in download_view.children:
            if isinstance(child, discord.ui.Button) and child.label and "Download" in child.label:
                has_download_download = True
                break

        # Check now playing view
        has_download_now_playing = False
        for child in now_playing_view.children:
            if isinstance(child, discord.ui.Button) and child.label and "Download" in child.label:
                has_download_now_playing = True
                break

        assert has_download_download
        assert has_download_now_playing

    def test_view_can_be_used_multiple_times(self):
        """Should be able to create multiple views with same parameters."""
        url = "https://youtube.com/watch?v=test"
        title = "Test Song"

        view1 = DownloadView(webpage_url=url, title=title)
        view2 = DownloadView(webpage_url=url, title=title)
        view3 = DownloadView(webpage_url=url, title=title)

        # All should be independent instances
        assert view1 is not view2
        assert view2 is not view3
        assert view1 is not view3

        # All should have same properties
        assert view1.webpage_url == view2.webpage_url == view3.webpage_url
        assert view1.title == view2.title == view3.title
        assert len(view1.children) == len(view2.children) == len(view3.children)


# =============================================================================
# Error Handling Tests
# =============================================================================


class TestViewErrorHandling:
    """Tests for error handling in views."""

    def test_download_view_with_empty_url(self):
        """Should handle empty URL."""
        view = DownloadView(
            webpage_url="",
            title="Test Song",
        )

        assert view.webpage_url == ""
        # Should still create buttons (even if URL is empty)
        assert len(view.children) == 2

    def test_download_view_with_empty_title(self):
        """Should handle empty title."""
        view = DownloadView(
            webpage_url="https://youtube.com/watch?v=test",
            title="",
        )

        assert view.title == ""
        assert len(view.children) == 2

    def test_now_playing_view_with_empty_url(self):
        """Should handle empty URL."""
        view = NowPlayingView(
            webpage_url="",
            title="Test Song",
        )

        assert view.webpage_url == ""
        assert len(view.children) == 2

    def test_now_playing_view_with_empty_title(self):
        """Should handle empty title."""
        view = NowPlayingView(
            webpage_url="https://youtube.com/watch?v=test",
            title="",
        )

        assert view.title == ""
        assert len(view.children) == 2

    def test_url_encoding_with_empty_string(self):
        """Test URL encoding with empty string."""
        view = DownloadView(
            webpage_url="https://youtube.com/watch?v=test",
            title="Test",
        )

        # Should handle encoding empty string
        encoded = view._encode_url("")
        assert encoded == ""
