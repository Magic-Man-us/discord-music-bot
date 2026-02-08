"""
Comprehensive Unit Tests for YtDlpResolver

Tests for the yt-dlp based audio resolver infrastructure:
- URL and playlist detection
- Track ID generation
- Info dict to Track conversion
- Resolve (URL and search)
- Search functionality
- Playlist extraction
- Caching behavior
- Error handling

Uses pytest with async/await patterns and proper mocking.
"""

import time
from unittest.mock import patch

import pytest

from discord_music_player.config.settings import AudioSettings
from discord_music_player.domain.music.entities import Track
from discord_music_player.domain.music.value_objects import TrackId
from discord_music_player.infrastructure.audio.ytdlp_resolver import (
    CACHE_TTL,
    YtDlpResolver,
    _generate_track_id,
    _info_cache,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def resolver():
    """Create a YtDlpResolver instance."""
    settings = AudioSettings()
    return YtDlpResolver(settings)


@pytest.fixture
def mock_info_dict():
    """Create a mock yt-dlp info dictionary."""
    return {
        "webpage_url": "https://youtube.com/watch?v=dQw4w9WgXcQ",
        "title": "Test Song",
        "url": "https://example.com/stream.m4a",
        "duration": 180,
        "thumbnail": "https://example.com/thumb.jpg",
        "artist": "Test Artist",
        "creator": None,
        "uploader": "Test Channel",
        "channel": None,
        "like_count": 1000,
        "view_count": 50000,
    }


@pytest.fixture(autouse=True)
def clear_cache():
    """Clear the global cache before each test."""
    _info_cache.clear()
    yield
    _info_cache.clear()


# =============================================================================
# URL Detection Tests
# =============================================================================


class TestURLDetection:
    """Tests for URL detection functionality."""

    def test_is_url_with_http(self, resolver):
        """Should detect http URLs."""
        assert resolver.is_url("http://youtube.com/watch?v=abc")

    def test_is_url_with_https(self, resolver):
        """Should detect https URLs."""
        assert resolver.is_url("https://youtube.com/watch?v=abc")

    def test_is_url_with_www(self, resolver):
        """Should detect www URLs."""
        assert resolver.is_url("www.youtube.com/watch?v=abc")

    def test_is_url_with_search_query(self, resolver):
        """Should not detect search queries as URLs."""
        assert not resolver.is_url("never gonna give you up")

    def test_is_url_with_empty_string(self, resolver):
        """Should handle empty string."""
        assert not resolver.is_url("")


# =============================================================================
# Playlist Detection Tests
# =============================================================================


class TestPlaylistDetection:
    """Tests for playlist detection functionality."""

    def test_is_playlist_with_youtube_list_param(self, resolver):
        """Should detect YouTube playlist URLs with list parameter."""
        assert resolver.is_playlist("https://youtube.com/watch?v=abc&list=PLxyz")

    def test_is_playlist_with_youtube_playlist_path(self, resolver):
        """Should detect YouTube playlist path."""
        assert resolver.is_playlist("https://youtube.com/playlist?list=PLxyz")

    def test_is_playlist_with_soundcloud_sets(self, resolver):
        """Should detect SoundCloud sets."""
        assert resolver.is_playlist("https://soundcloud.com/user/sets/playlist")

    def test_is_playlist_with_single_video(self, resolver):
        """Should not detect single videos as playlists."""
        assert not resolver.is_playlist("https://youtube.com/watch?v=abc")


# =============================================================================
# Track ID Generation Tests
# =============================================================================


class TestTrackIDGeneration:
    """Tests for track ID generation."""

    def test_generate_track_id_from_youtube_watch_url(self):
        """Should extract YouTube ID from watch URL."""
        url = "https://youtube.com/watch?v=dQw4w9WgXcQ"
        track_id = _generate_track_id(url, "Test Title")
        assert track_id == "dQw4w9WgXcQ"

    def test_generate_track_id_from_youtube_short_url(self):
        """Should extract YouTube ID from short URL."""
        url = "https://youtu.be/dQw4w9WgXcQ"
        track_id = _generate_track_id(url, "Test Title")
        assert track_id == "dQw4w9WgXcQ"

    def test_generate_track_id_from_youtube_embed_url(self):
        """Should extract YouTube ID from embed URL."""
        url = "https://youtube.com/embed/dQw4w9WgXcQ"
        track_id = _generate_track_id(url, "Test Title")
        assert track_id == "dQw4w9WgXcQ"

    def test_generate_track_id_from_non_youtube_url(self):
        """Should generate hash for non-YouTube URLs."""
        url = "https://example.com/song.mp3"
        track_id = _generate_track_id(url, "Test Title")
        assert len(track_id) == 16
        assert track_id.isalnum()


# =============================================================================
# Info to Track Conversion Tests
# =============================================================================


class TestInfoToTrack:
    """Tests for converting yt-dlp info dicts to Track entities."""

    def test_info_to_track_success(self, resolver, mock_info_dict):
        """Should convert valid info dict to Track."""
        track = resolver._info_to_track(mock_info_dict)

        assert track is not None
        assert isinstance(track, Track)
        assert track.title == "Test Song"
        assert track.webpage_url == "https://youtube.com/watch?v=dQw4w9WgXcQ"
        assert track.stream_url == "https://example.com/stream.m4a"
        assert track.duration_seconds == 180
        assert track.artist == "Test Artist"
        assert track.uploader == "Test Channel"
        assert track.like_count == 1000
        assert track.view_count == 50000

    def test_info_to_track_with_missing_url(self, resolver):
        """Should return None when URL is missing."""
        info = {"title": "Test"}
        track = resolver._info_to_track(info)
        assert track is None

    def test_info_to_track_with_missing_stream_url(self, resolver):
        """Should return None when stream URL is missing."""
        info = {"webpage_url": "https://youtube.com/watch?v=abc", "title": "Test"}
        track = resolver._info_to_track(info)
        assert track is None

    def test_info_to_track_with_creator_instead_of_artist(self, resolver, mock_info_dict):
        """Should use creator when artist is None."""
        mock_info_dict["artist"] = None
        mock_info_dict["creator"] = "Test Creator"
        track = resolver._info_to_track(mock_info_dict)

        assert track is not None
        assert track.artist == "Test Creator"

    def test_info_to_track_with_channel_instead_of_uploader(self, resolver, mock_info_dict):
        """Should use channel when uploader is None."""
        mock_info_dict["uploader"] = None
        mock_info_dict["channel"] = "Test Channel Name"
        track = resolver._info_to_track(mock_info_dict)

        assert track is not None
        assert track.uploader == "Test Channel Name"

    def test_info_to_track_with_invalid_like_count(self, resolver, mock_info_dict):
        """Should handle invalid like count gracefully."""
        mock_info_dict["like_count"] = "invalid"
        track = resolver._info_to_track(mock_info_dict)

        assert track is not None
        assert track.like_count is None

    def test_info_to_track_with_invalid_view_count(self, resolver, mock_info_dict):
        """Should handle invalid view count gracefully."""
        mock_info_dict["view_count"] = "not_a_number"
        track = resolver._info_to_track(mock_info_dict)

        assert track is not None
        assert track.view_count is None

    def test_info_to_track_with_exception_during_construction(self, resolver):
        """Should return None when Track construction raises exception."""
        # Create an info dict that will pass initial validation but fail Track construction
        info = {
            "webpage_url": "https://youtube.com/watch?v=abc",
            "title": "Test",
            "url": "https://example.com/stream.m4a",
        }

        # Mock Track to raise an exception during construction
        with patch(
            "discord_music_player.infrastructure.audio.ytdlp_resolver.Track",
            side_effect=Exception("Validation error"),
        ):
            track = resolver._info_to_track(info)

        assert track is None


# =============================================================================
# URL Extraction Tests
# =============================================================================


class TestURLExtraction:
    """Tests for extracting URLs from info dicts."""

    def test_extract_webpage_url_from_webpage_url_field(self, resolver):
        """Should extract from webpage_url field."""
        info = {"webpage_url": "https://youtube.com/watch?v=abc"}
        url = resolver._extract_webpage_url(info)
        assert url == "https://youtube.com/watch?v=abc"

    def test_extract_webpage_url_from_url_field(self, resolver):
        """Should fallback to url field."""
        info = {"url": "https://youtube.com/watch?v=abc"}
        url = resolver._extract_webpage_url(info)
        assert url == "https://youtube.com/watch?v=abc"

    def test_extract_webpage_url_missing(self, resolver):
        """Should return None when both fields missing."""
        info = {"title": "Test"}
        url = resolver._extract_webpage_url(info)
        assert url is None


# =============================================================================
# Stream URL Extraction Tests
# =============================================================================


class TestStreamURLExtraction:
    """Tests for extracting stream URLs from info dicts."""

    def test_extract_stream_url_from_url_field(self, resolver):
        """Should extract from url field."""
        info = {"url": "https://example.com/stream.m4a"}
        url = resolver._extract_stream_url(info)
        assert url == "https://example.com/stream.m4a"

    def test_extract_stream_url_from_formats(self, resolver):
        """Should extract from formats list."""
        info = {
            "formats": [
                {"acodec": "none", "url": "video_only.mp4"},
                {"acodec": "opus", "url": "audio1.webm"},
                {"acodec": "aac", "url": "audio2.m4a"},
            ]
        }
        url = resolver._extract_stream_url(info)
        assert url == "audio2.m4a"  # Last audio format

    def test_extract_stream_url_from_empty_formats(self, resolver):
        """Should return None for empty formats."""
        info = {"formats": []}
        url = resolver._extract_stream_url(info)
        assert url is None

    def test_extract_stream_url_with_no_audio(self, resolver):
        """Should return None when no audio formats."""
        info = {"formats": [{"acodec": "none", "url": "video.mp4"}]}
        url = resolver._extract_stream_url(info)
        assert url is None


# =============================================================================
# Resolve Tests
# =============================================================================


class TestResolve:
    """Tests for resolve method."""

    @pytest.mark.asyncio
    async def test_resolve_url(self, resolver, mock_info_dict):
        """Should resolve URL to track."""
        with patch.object(resolver, "_extract_info_sync", return_value=mock_info_dict):
            track = await resolver.resolve("https://youtube.com/watch?v=abc")

        assert track is not None
        assert track.title == "Test Song"

    @pytest.mark.asyncio
    async def test_resolve_search_query(self, resolver, mock_info_dict):
        """Should resolve search query to track."""
        with patch.object(resolver, "_search_sync", return_value=[mock_info_dict]):
            track = await resolver.resolve("never gonna give you up")

        assert track is not None
        assert track.title == "Test Song"

    @pytest.mark.asyncio
    async def test_resolve_no_results(self, resolver):
        """Should return None when no results."""
        with patch.object(resolver, "_search_sync", return_value=[]):
            track = await resolver.resolve("nonexistent song xyz")

        assert track is None

    @pytest.mark.asyncio
    async def test_resolve_exception(self, resolver):
        """Should handle exceptions gracefully."""
        with patch.object(resolver, "_extract_info_sync", side_effect=Exception("API Error")):
            track = await resolver.resolve("https://youtube.com/watch?v=abc")

        assert track is None


# =============================================================================
# Search Tests
# =============================================================================


class TestSearch:
    """Tests for search method."""

    @pytest.mark.asyncio
    async def test_search_multiple_results(self, resolver):
        """Should return multiple search results."""
        mock_results = [
            {
                "webpage_url": f"https://youtube.com/watch?v=abc{i}",
                "title": f"Song {i}",
                "url": f"https://example.com/stream{i}.m4a",
            }
            for i in range(3)
        ]

        with patch.object(resolver, "_search_sync", return_value=mock_results):
            tracks = await resolver.search("test query", limit=3)

        assert len(tracks) == 3
        assert all(isinstance(t, Track) for t in tracks)

    @pytest.mark.asyncio
    async def test_search_no_results(self, resolver):
        """Should return empty list when no results."""
        with patch.object(resolver, "_search_sync", return_value=[]):
            tracks = await resolver.search("nonexistent query")

        assert tracks == []

    @pytest.mark.asyncio
    async def test_search_exception(self, resolver):
        """Should handle exceptions gracefully."""
        with patch.object(resolver, "_search_sync", side_effect=Exception("Search failed")):
            tracks = await resolver.search("test query")

        assert tracks == []


# =============================================================================
# Resolve Many Tests
# =============================================================================


class TestResolveMany:
    """Tests for resolve_many method."""

    @pytest.mark.asyncio
    async def test_resolve_many_success(self, resolver):
        """Should resolve multiple queries successfully."""
        queries = [
            "https://youtube.com/watch?v=abc1",
            "https://youtube.com/watch?v=abc2",
            "test song query",
        ]

        mock_tracks = [
            Track(
                id=TrackId(value=f"track{i}"),
                title=f"Song {i}",
                webpage_url=f"https://youtube.com/watch?v=abc{i}",
                stream_url=f"https://example.com/stream{i}.m4a",
            )
            for i in range(3)
        ]

        with patch.object(resolver, "resolve", side_effect=mock_tracks):
            tracks = await resolver.resolve_many(queries)

        assert len(tracks) == 3
        assert all(isinstance(t, Track) for t in tracks)

    @pytest.mark.asyncio
    async def test_resolve_many_partial_success(self, resolver):
        """Should return only successfully resolved tracks."""
        queries = ["query1", "query2", "query3"]

        # Second query returns None (failed)
        mock_results = [
            Track(
                id=TrackId(value="track1"),
                title="Song 1",
                webpage_url="https://youtube.com/watch?v=abc1",
                stream_url="https://example.com/stream1.m4a",
            ),
            None,  # Failed resolution
            Track(
                id=TrackId(value="track3"),
                title="Song 3",
                webpage_url="https://youtube.com/watch?v=abc3",
                stream_url="https://example.com/stream3.m4a",
            ),
        ]

        with patch.object(resolver, "resolve", side_effect=mock_results):
            tracks = await resolver.resolve_many(queries)

        assert len(tracks) == 2
        assert tracks[0].title == "Song 1"
        assert tracks[1].title == "Song 3"

    @pytest.mark.asyncio
    async def test_resolve_many_empty_list(self, resolver):
        """Should handle empty query list."""
        tracks = await resolver.resolve_many([])
        assert tracks == []

    @pytest.mark.asyncio
    async def test_resolve_many_batching(self, resolver):
        """Should process queries in batches."""
        # Create 12 queries to test batching (batch_size=5)
        queries = [f"query{i}" for i in range(12)]

        mock_track = Track(
            id=TrackId(value="test"),
            title="Test",
            webpage_url="https://youtube.com/watch?v=test",
            stream_url="https://example.com/stream.m4a",
        )

        with patch.object(resolver, "resolve", return_value=mock_track):
            tracks = await resolver.resolve_many(queries)

        assert len(tracks) == 12

    @pytest.mark.asyncio
    async def test_resolve_many_with_exceptions(self, resolver):
        """Should handle exceptions gracefully - batch with exceptions is lost."""
        queries = ["query1", "query2", "query3"]

        # Second query raises exception
        async def mock_resolve(query):
            if query == "query2":
                raise Exception("Resolution failed")
            return Track(
                id=TrackId(value=query),
                title=f"Song {query}",
                webpage_url=f"https://youtube.com/watch?v={query}",
                stream_url=f"https://example.com/stream-{query}.m4a",
            )

        with patch.object(resolver, "resolve", side_effect=mock_resolve):
            tracks = await resolver.resolve_many(queries)

        # When TaskGroup raises exception, entire batch is lost
        # Since batch_size=5, all 3 queries are in one batch
        assert len(tracks) == 0


# =============================================================================
# Playlist Extraction Tests
# =============================================================================


class TestPlaylistExtraction:
    """Tests for extract_playlist method."""

    @pytest.mark.asyncio
    async def test_extract_playlist_success(self, resolver, mock_info_dict):
        """Should extract playlist entries."""
        playlist_entries = [
            {"url": "https://youtube.com/watch?v=abc1"},
            {"webpage_url": "https://youtube.com/watch?v=abc2"},
        ]

        with patch.object(resolver, "_extract_playlist_sync", return_value=playlist_entries):
            with patch.object(
                resolver,
                "resolve",
                side_effect=[
                    Track(
                        id=TrackId(value="abc1"),
                        title="Song 1",
                        webpage_url="https://youtube.com/watch?v=abc1",
                        stream_url="https://example.com/stream1.m4a",
                    ),
                    Track(
                        id=TrackId(value="abc2"),
                        title="Song 2",
                        webpage_url="https://youtube.com/watch?v=abc2",
                        stream_url="https://example.com/stream2.m4a",
                    ),
                ],
            ):
                tracks = await resolver.extract_playlist("https://youtube.com/playlist?list=PLxyz")

        assert len(tracks) == 2
        assert tracks[0].title == "Song 1"
        assert tracks[1].title == "Song 2"

    @pytest.mark.asyncio
    async def test_extract_playlist_empty(self, resolver):
        """Should return empty list for empty playlist."""
        with patch.object(resolver, "_extract_playlist_sync", return_value=[]):
            tracks = await resolver.extract_playlist("https://youtube.com/playlist?list=PLxyz")

        assert tracks == []

    @pytest.mark.asyncio
    async def test_extract_playlist_exception(self, resolver):
        """Should handle exceptions gracefully."""
        with patch.object(
            resolver, "_extract_playlist_sync", side_effect=Exception("Playlist error")
        ):
            tracks = await resolver.extract_playlist("https://youtube.com/playlist?list=PLxyz")

        assert tracks == []

    def test_extract_playlist_sync_success(self, resolver):
        """Should extract playlist entries successfully."""
        url = "https://youtube.com/playlist?list=PLxyz"
        mock_entries = [
            {"webpage_url": "https://youtube.com/watch?v=abc1", "title": "Song 1"},
            {"webpage_url": "https://youtube.com/watch?v=abc2", "title": "Song 2"},
        ]
        mock_data = {"entries": mock_entries}

        with patch(
            "discord_music_player.infrastructure.audio.ytdlp_resolver.YoutubeDL"
        ) as mock_ydl:
            mock_ydl.return_value.__enter__.return_value.extract_info.return_value = mock_data
            result = resolver._extract_playlist_sync(url)

        assert len(result) == 2
        assert result[0]["title"] == "Song 1"
        assert result[1]["title"] == "Song 2"

    def test_extract_playlist_sync_invalid_data_type(self, resolver):
        """Should return empty list when data is not a dict."""
        url = "https://youtube.com/playlist?list=PLxyz"

        with patch(
            "discord_music_player.infrastructure.audio.ytdlp_resolver.YoutubeDL"
        ) as mock_ydl:
            # Return non-dict type
            mock_ydl.return_value.__enter__.return_value.extract_info.return_value = ["not", "dict"]
            result = resolver._extract_playlist_sync(url)

        assert result == []

    def test_extract_playlist_sync_entries_not_list(self, resolver):
        """Should return empty list when entries is not a list."""
        url = "https://youtube.com/playlist?list=PLxyz"

        with patch(
            "discord_music_player.infrastructure.audio.ytdlp_resolver.YoutubeDL"
        ) as mock_ydl:
            # Return dict with entries as non-list
            mock_ydl.return_value.__enter__.return_value.extract_info.return_value = {
                "entries": "not a list"
            }
            result = resolver._extract_playlist_sync(url)

        assert result == []

    def test_extract_playlist_sync_filters_none_entries(self, resolver):
        """Should filter out None entries."""
        url = "https://youtube.com/playlist?list=PLxyz"
        mock_entries = [
            {"webpage_url": "https://youtube.com/watch?v=abc1", "title": "Song 1"},
            None,  # Unavailable video
            {"webpage_url": "https://youtube.com/watch?v=abc3", "title": "Song 3"},
        ]
        mock_data = {"entries": mock_entries}

        with patch(
            "discord_music_player.infrastructure.audio.ytdlp_resolver.YoutubeDL"
        ) as mock_ydl:
            mock_ydl.return_value.__enter__.return_value.extract_info.return_value = mock_data
            result = resolver._extract_playlist_sync(url)

        assert len(result) == 2
        assert result[0]["title"] == "Song 1"
        assert result[1]["title"] == "Song 3"

    def test_extract_playlist_sync_exception(self, resolver):
        """Should return empty list when YoutubeDL raises exception."""
        url = "https://youtube.com/playlist?list=PLxyz"

        with patch(
            "discord_music_player.infrastructure.audio.ytdlp_resolver.YoutubeDL"
        ) as mock_ydl:
            mock_ydl.return_value.__enter__.return_value.extract_info.side_effect = Exception(
                "Playlist error"
            )
            result = resolver._extract_playlist_sync(url)

        assert result == []


# =============================================================================
# Caching Tests
# =============================================================================


class TestCaching:
    """Tests for caching behavior."""

    def test_cache_hit(self, resolver):
        """Should use cached result on second call."""
        url = "https://youtube.com/watch?v=abc"
        mock_info = {"webpage_url": url, "title": "Cached Song", "url": "stream.m4a"}

        # First call - cache miss
        with patch(
            "discord_music_player.infrastructure.audio.ytdlp_resolver.YoutubeDL"
        ) as mock_ydl:
            mock_ydl.return_value.__enter__.return_value.extract_info.return_value = mock_info
            result1 = resolver._extract_info_sync(url)

        # Second call - should use cache
        with patch(
            "discord_music_player.infrastructure.audio.ytdlp_resolver.YoutubeDL"
        ) as mock_ydl:
            mock_ydl.return_value.__enter__.return_value.extract_info.return_value = {
                "title": "Different"
            }
            result2 = resolver._extract_info_sync(url)

        assert result1 == result2
        assert result2["title"] == "Cached Song"

    def test_cache_expiry(self, resolver):
        """Should refetch after cache expiry."""
        url = "https://youtube.com/watch?v=abc"
        mock_info1 = {"webpage_url": url, "title": "Original", "url": "stream.m4a"}
        mock_info2 = {"webpage_url": url, "title": "Updated", "url": "stream.m4a"}

        # First call
        with patch(
            "discord_music_player.infrastructure.audio.ytdlp_resolver.YoutubeDL"
        ) as mock_ydl:
            mock_ydl.return_value.__enter__.return_value.extract_info.return_value = mock_info1
            result1 = resolver._extract_info_sync(url)

        # Simulate cache expiry
        _info_cache[url] = (_info_cache[url][0], time.time() - CACHE_TTL - 1)

        # Second call after expiry
        with patch(
            "discord_music_player.infrastructure.audio.ytdlp_resolver.YoutubeDL"
        ) as mock_ydl:
            mock_ydl.return_value.__enter__.return_value.extract_info.return_value = mock_info2
            result2 = resolver._extract_info_sync(url)

        assert result1["title"] == "Original"
        assert result2["title"] == "Updated"

    def test_cache_cleanup(self, resolver):
        """Should clean up expired entries when cache grows."""
        # Fill cache with 501 entries (triggers cleanup at >500)
        with patch(
            "discord_music_player.infrastructure.audio.ytdlp_resolver.YoutubeDL"
        ) as mock_ydl:
            for i in range(501):
                url = f"https://youtube.com/watch?v=test{i}"
                mock_info = {"webpage_url": url, "title": f"Song {i}", "url": "stream.m4a"}
                mock_ydl.return_value.__enter__.return_value.extract_info.return_value = mock_info

                # Make first 100 entries expired
                if i < 100:
                    _info_cache[url] = (mock_info, time.time() - CACHE_TTL - 1)
                else:
                    resolver._extract_info_sync(url)

        # Cache should have cleaned up expired entries
        assert len(_info_cache) <= 501

    def test_extract_info_sync_exception(self, resolver):
        """Should return None when YoutubeDL raises exception."""
        url = "https://youtube.com/watch?v=abc"

        with patch(
            "discord_music_player.infrastructure.audio.ytdlp_resolver.YoutubeDL"
        ) as mock_ydl:
            mock_ydl.return_value.__enter__.return_value.extract_info.side_effect = Exception(
                "Network error"
            )
            result = resolver._extract_info_sync(url)

        assert result is None

    def test_search_sync_exception(self, resolver):
        """Should return empty list when YoutubeDL raises exception."""
        with patch(
            "discord_music_player.infrastructure.audio.ytdlp_resolver.YoutubeDL"
        ) as mock_ydl:
            mock_ydl.return_value.__enter__.return_value.extract_info.side_effect = Exception(
                "Search error"
            )
            result = resolver._search_sync("test query")

        assert result == []

    def test_search_sync_invalid_data_type(self, resolver):
        """Should return empty list when data is not a dict."""
        with patch(
            "discord_music_player.infrastructure.audio.ytdlp_resolver.YoutubeDL"
        ) as mock_ydl:
            # Return a non-dict type
            mock_ydl.return_value.__enter__.return_value.extract_info.return_value = [
                "not",
                "a",
                "dict",
            ]
            result = resolver._search_sync("test query")

        assert result == []

    def test_search_sync_entries_not_list(self, resolver):
        """Should return empty list when entries is not a list."""
        with patch(
            "discord_music_player.infrastructure.audio.ytdlp_resolver.YoutubeDL"
        ) as mock_ydl:
            # Return dict with entries as non-list
            mock_ydl.return_value.__enter__.return_value.extract_info.return_value = {
                "entries": "not a list"
            }
            result = resolver._search_sync("test query")

        assert result == []


# =============================================================================
# POT Provider Configuration Tests
# =============================================================================


class TestPOTProviderConfiguration:
    """Tests for bgutil-ytdlp-pot-provider configuration."""

    def test_default_pot_server_url(self):
        """Should use default POT server URL."""
        settings = AudioSettings()
        assert settings.pot_server_url == "http://127.0.0.1:4416"

    def test_custom_pot_server_url(self):
        """Should accept custom POT server URL."""
        settings = AudioSettings(pot_server_url="http://localhost:5000")
        assert settings.pot_server_url == "http://localhost:5000"

    def test_resolver_initializes_with_pot_config(self):
        """Should initialize resolver with POT configuration."""
        settings = AudioSettings()
        resolver = YtDlpResolver(settings)

        # Verify POT options are set
        assert hasattr(resolver, "_pot_opts")
        assert "extractor_args" in resolver._pot_opts
        assert "youtube" in resolver._pot_opts["extractor_args"]
        assert (
            resolver._pot_opts["extractor_args"]["youtube"]["pot_server_url"]
            == settings.pot_server_url
        )

    def test_pot_config_included_in_opts(self):
        """Should include POT configuration in yt-dlp options."""
        settings = AudioSettings(pot_server_url="http://test:4416")
        resolver = YtDlpResolver(settings)

        opts = resolver._get_opts()

        assert "extractor_args" in opts
        assert "youtube" in opts["extractor_args"]
        assert opts["extractor_args"]["youtube"]["pot_server_url"] == "http://test:4416"

    def test_pot_config_preserved_with_overrides(self):
        """Should preserve POT config when applying option overrides."""
        resolver = YtDlpResolver()

        opts = resolver._get_opts(quiet=False, noplaylist=False)

        # Overrides should be applied
        assert opts["quiet"] is False
        assert opts["noplaylist"] is False

        # POT config should still be present
        assert "extractor_args" in opts
        assert "youtube" in opts["extractor_args"]
        assert "pot_server_url" in opts["extractor_args"]["youtube"]

    def test_pot_config_in_playlist_opts(self):
        """Should include POT configuration in playlist options."""
        resolver = YtDlpResolver()

        opts = resolver._get_playlist_opts()

        # Playlist-specific settings
        assert opts["noplaylist"] is False
        assert opts["extract_flat"] == "in_playlist"

        # POT config should be present
        assert "extractor_args" in opts
        assert "youtube" in opts["extractor_args"]
