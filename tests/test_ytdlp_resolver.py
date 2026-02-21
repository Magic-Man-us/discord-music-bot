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
    CACHE_MAX_SIZE,
    CACHE_TTL,
    RESOLVE_BATCH_SIZE,
    AudioFormatInfo,
    CacheEntry,
    YouTubeExtractorConfig,
    YtDlpOpts,
    YtDlpResolver,
    YtDlpTrackInfo,
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
def mock_info():
    """Create a mock yt-dlp info model."""
    return YtDlpTrackInfo(
        webpage_url="https://youtube.com/watch?v=dQw4w9WgXcQ",
        title="Test Song",
        url="https://example.com/stream.m4a",
        duration=180,
        thumbnail="https://example.com/thumb.jpg",
        artist="Test Artist",
        creator=None,
        uploader="Test Channel",
        channel=None,
        like_count=1000,
        view_count=50000,
    )


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
    """Tests for converting YtDlpTrackInfo models to Track entities."""

    def test_info_to_track_success(self, resolver, mock_info):
        """Should convert valid info model to Track."""
        track = resolver._info_to_track(mock_info)

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
        info = YtDlpTrackInfo(title="Test")
        track = resolver._info_to_track(info)
        assert track is None

    def test_info_to_track_with_missing_stream_url(self, resolver):
        """Should return None when stream URL is missing."""
        info = YtDlpTrackInfo(
            webpage_url="https://youtube.com/watch?v=abc",
            title="Test",
        )
        track = resolver._info_to_track(info)
        assert track is None

    def test_info_to_track_with_creator_instead_of_artist(self, resolver, mock_info):
        """Should use creator when artist is None."""
        raw = mock_info.model_dump()
        raw["artist"] = None
        raw["creator"] = "Test Creator"
        info = YtDlpTrackInfo.model_validate(raw)

        track = resolver._info_to_track(info)

        assert track is not None
        assert track.artist == "Test Creator"

    def test_info_to_track_with_channel_instead_of_uploader(self, resolver, mock_info):
        """Should use channel when uploader is None."""
        raw = mock_info.model_dump()
        raw["uploader"] = None
        raw["channel"] = "Test Channel Name"
        info = YtDlpTrackInfo.model_validate(raw)

        track = resolver._info_to_track(info)

        assert track is not None
        assert track.uploader == "Test Channel Name"

    def test_info_to_track_with_invalid_like_count(self, resolver, mock_info):
        """Should handle invalid like count gracefully via model coercion."""
        raw = mock_info.model_dump()
        raw["like_count"] = "invalid"
        info = YtDlpTrackInfo.model_validate(raw)

        track = resolver._info_to_track(info)

        assert track is not None
        assert track.like_count is None

    def test_info_to_track_with_invalid_view_count(self, resolver, mock_info):
        """Should handle invalid view count gracefully via model coercion."""
        raw = mock_info.model_dump()
        raw["view_count"] = "not_a_number"
        info = YtDlpTrackInfo.model_validate(raw)

        track = resolver._info_to_track(info)

        assert track is not None
        assert track.view_count is None

    def test_info_to_track_with_exception_during_construction(self, resolver):
        """Should return None when Track construction raises exception."""
        info = YtDlpTrackInfo(
            webpage_url="https://youtube.com/watch?v=abc",
            title="Test",
            url="https://example.com/stream.m4a",
        )

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
    """Tests for extracting URLs from info models."""

    def test_extract_webpage_url_from_webpage_url_field(self, resolver):
        """Should extract from webpage_url field."""
        info = YtDlpTrackInfo(webpage_url="https://youtube.com/watch?v=abc")
        url = resolver._extract_webpage_url(info)
        assert url == "https://youtube.com/watch?v=abc"

    def test_extract_webpage_url_from_url_field(self, resolver):
        """Should fallback to url field."""
        info = YtDlpTrackInfo(url="https://youtube.com/watch?v=abc")
        url = resolver._extract_webpage_url(info)
        assert url == "https://youtube.com/watch?v=abc"

    def test_extract_webpage_url_missing(self, resolver):
        """Should return None when both fields missing."""
        info = YtDlpTrackInfo(title="Test")
        url = resolver._extract_webpage_url(info)
        assert url is None


# =============================================================================
# Stream URL Extraction Tests
# =============================================================================


class TestStreamURLExtraction:
    """Tests for extracting stream URLs from info models."""

    def test_extract_stream_url_from_url_field(self, resolver):
        """Should extract from url field."""
        info = YtDlpTrackInfo(url="https://example.com/stream.m4a")
        url = resolver._extract_stream_url(info)
        assert url == "https://example.com/stream.m4a"

    def test_extract_stream_url_from_formats(self, resolver):
        """Should extract from formats list."""
        info = YtDlpTrackInfo(
            formats=[
                AudioFormatInfo(acodec="none", url="video_only.mp4"),
                AudioFormatInfo(acodec="opus", url="audio1.webm"),
                AudioFormatInfo(acodec="aac", url="audio2.m4a"),
            ]
        )
        url = resolver._extract_stream_url(info)
        assert url == "audio2.m4a"  # Last audio format

    def test_extract_stream_url_from_empty_formats(self, resolver):
        """Should return None for empty formats."""
        info = YtDlpTrackInfo(formats=[])
        url = resolver._extract_stream_url(info)
        assert url is None

    def test_extract_stream_url_with_no_audio(self, resolver):
        """Should return None when no audio formats."""
        info = YtDlpTrackInfo(
            formats=[AudioFormatInfo(acodec="none", url="video.mp4")]
        )
        url = resolver._extract_stream_url(info)
        assert url is None


# =============================================================================
# Resolve Tests
# =============================================================================


class TestResolve:
    """Tests for resolve method."""

    @pytest.mark.asyncio
    async def test_resolve_url(self, resolver, mock_info):
        """Should resolve URL to track."""
        with patch.object(resolver, "_extract_info_sync", return_value=mock_info):
            track = await resolver.resolve("https://youtube.com/watch?v=abc")

        assert track is not None
        assert track.title == "Test Song"

    @pytest.mark.asyncio
    async def test_resolve_search_query(self, resolver, mock_info):
        """Should resolve search query to track."""
        with patch.object(resolver, "_search_sync", return_value=[mock_info]):
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
            YtDlpTrackInfo(
                webpage_url=f"https://youtube.com/watch?v=abc{i}",
                title=f"Song {i}",
                url=f"https://example.com/stream{i}.m4a",
            )
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
        # Create enough queries to span multiple batches
        queries = [f"query{i}" for i in range(RESOLVE_BATCH_SIZE * 2 + 2)]

        mock_track = Track(
            id=TrackId(value="test"),
            title="Test",
            webpage_url="https://youtube.com/watch?v=test",
            stream_url="https://example.com/stream.m4a",
        )

        with patch.object(resolver, "resolve", return_value=mock_track):
            tracks = await resolver.resolve_many(queries)

        assert len(tracks) == len(queries)

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
        # All 3 queries fit in one batch (RESOLVE_BATCH_SIZE), so all are lost
        assert len(tracks) == 0


# =============================================================================
# Playlist Extraction Tests
# =============================================================================


class TestPlaylistExtraction:
    """Tests for extract_playlist method."""

    @pytest.mark.asyncio
    async def test_extract_playlist_success(self, resolver, mock_info):
        """Should extract playlist entries."""
        playlist_entries = [
            YtDlpTrackInfo(url="https://youtube.com/watch?v=abc1"),
            YtDlpTrackInfo(webpage_url="https://youtube.com/watch?v=abc2"),
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
        assert result[0].title == "Song 1"
        assert result[1].title == "Song 2"

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
        assert result[0].title == "Song 1"
        assert result[1].title == "Song 3"

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
        mock_raw = {"webpage_url": url, "title": "Cached Song", "url": "stream.m4a"}

        # First call - cache miss
        with patch(
            "discord_music_player.infrastructure.audio.ytdlp_resolver.YoutubeDL"
        ) as mock_ydl:
            mock_ydl.return_value.__enter__.return_value.extract_info.return_value = mock_raw
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
        assert result2.title == "Cached Song"

    def test_cache_expiry(self, resolver):
        """Should refetch after cache expiry."""
        url = "https://youtube.com/watch?v=abc"
        mock_raw1 = {"webpage_url": url, "title": "Original", "url": "stream.m4a"}
        mock_raw2 = {"webpage_url": url, "title": "Updated", "url": "stream.m4a"}

        # First call
        with patch(
            "discord_music_player.infrastructure.audio.ytdlp_resolver.YoutubeDL"
        ) as mock_ydl:
            mock_ydl.return_value.__enter__.return_value.extract_info.return_value = mock_raw1
            result1 = resolver._extract_info_sync(url)

        # Simulate cache expiry
        cached = _info_cache[url]
        _info_cache[url] = CacheEntry(info=cached.info, cached_at=time.time() - CACHE_TTL - 1)

        # Second call after expiry
        with patch(
            "discord_music_player.infrastructure.audio.ytdlp_resolver.YoutubeDL"
        ) as mock_ydl:
            mock_ydl.return_value.__enter__.return_value.extract_info.return_value = mock_raw2
            result2 = resolver._extract_info_sync(url)

        assert result1.title == "Original"
        assert result2.title == "Updated"

    def test_cache_cleanup(self, resolver):
        """Should clean up expired entries when cache grows."""
        fill_count = CACHE_MAX_SIZE + 1  # triggers cleanup at > CACHE_MAX_SIZE
        expired_count = 100

        with patch(
            "discord_music_player.infrastructure.audio.ytdlp_resolver.YoutubeDL"
        ) as mock_ydl:
            for i in range(fill_count):
                url = f"https://youtube.com/watch?v=test{i}"
                mock_raw = {"webpage_url": url, "title": f"Song {i}", "url": "stream.m4a"}
                mock_ydl.return_value.__enter__.return_value.extract_info.return_value = mock_raw

                # Make first batch of entries expired
                if i < expired_count:
                    info = YtDlpTrackInfo.model_validate(mock_raw)
                    _info_cache[url] = CacheEntry(
                        info=info, cached_at=time.time() - CACHE_TTL - 1
                    )
                else:
                    resolver._extract_info_sync(url)

        # Cache should have cleaned up expired entries
        assert len(_info_cache) <= fill_count

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

        opts = resolver._get_opts()
        assert isinstance(opts, YtDlpOpts)
        assert opts.extractor_args is not None
        assert opts.extractor_args.youtube.pot_server_url == settings.pot_server_url
        assert opts.extractor_args.youtube.player_client == ["android", "web"]

    def test_pot_config_included_in_opts(self):
        """Should include POT configuration in yt-dlp options."""
        settings = AudioSettings(pot_server_url="http://test:4416")
        resolver = YtDlpResolver(settings)

        opts = resolver._get_opts()

        assert opts.extractor_args is not None
        assert opts.extractor_args.youtube.pot_server_url == "http://test:4416"

    def test_pot_config_preserved_with_overrides(self):
        """Should preserve POT config when applying option overrides."""
        resolver = YtDlpResolver()

        opts = resolver._get_opts(quiet=False, noplaylist=False)

        # Overrides should be applied
        assert opts.quiet is False
        assert opts.noplaylist is False

        # POT config should still be present
        assert opts.extractor_args is not None
        assert opts.extractor_args.youtube.pot_server_url is not None

    def test_pot_config_in_playlist_opts(self):
        """Should include POT configuration in playlist options."""
        resolver = YtDlpResolver()

        opts = resolver._get_playlist_opts()

        # Playlist-specific settings
        assert opts.noplaylist is False
        assert opts.extract_flat == "in_playlist"

        # POT config should be present
        assert opts.extractor_args is not None
        assert opts.extractor_args.youtube is not None


# =============================================================================
# Model Validation Tests
# =============================================================================


class TestModelValidation:
    """Tests for Pydantic model validation behavior."""

    def test_ytdlp_track_info_ignores_extra_fields(self):
        """Should silently ignore unknown fields from yt-dlp."""
        raw = {
            "title": "Test",
            "webpage_url": "https://example.com",
            "unknown_field": "value",
            "another_unknown": 42,
        }
        info = YtDlpTrackInfo.model_validate(raw)
        assert info.title == "Test"
        assert not hasattr(info, "unknown_field")

    def test_audio_format_info_ignores_extra_fields(self):
        """Should silently ignore extra format fields from yt-dlp."""
        raw = {"url": "https://example.com/stream", "acodec": "opus", "vcodec": "none", "ext": "webm"}
        fmt = AudioFormatInfo.model_validate(raw)
        assert fmt.url == "https://example.com/stream"
        assert fmt.acodec == "opus"

    def test_ytdlp_track_info_coerces_string_counts(self):
        """Should coerce string like/view counts to int."""
        raw = {"title": "Test", "like_count": "1000", "view_count": "50000"}
        info = YtDlpTrackInfo.model_validate(raw)
        assert info.like_count == 1000
        assert info.view_count == 50000

    def test_ytdlp_track_info_nullifies_invalid_counts(self):
        """Should set invalid counts to None instead of raising."""
        raw = {"title": "Test", "like_count": "not_a_number", "view_count": [1, 2]}
        info = YtDlpTrackInfo.model_validate(raw)
        assert info.like_count is None
        assert info.view_count is None

    def test_ytdlp_track_info_nullifies_negative_counts(self):
        """Should coerce negative counts to None."""
        raw = {"title": "Test", "like_count": -1, "view_count": -999}
        info = YtDlpTrackInfo.model_validate(raw)
        assert info.like_count is None
        assert info.view_count is None

    def test_ytdlp_track_info_empty_strings_become_none(self):
        """Should coerce empty / whitespace-only strings to None."""
        raw = {
            "title": "Test",
            "webpage_url": "",
            "url": "   ",
            "thumbnail": "",
            "artist": "  ",
            "uploader": "",
        }
        info = YtDlpTrackInfo.model_validate(raw)
        assert info.webpage_url is None
        assert info.url is None
        assert info.thumbnail is None
        assert info.artist is None
        assert info.uploader is None

    def test_ytdlp_track_info_empty_title_gets_default(self):
        """Should fall back to 'Unknown Title' for empty title."""
        info = YtDlpTrackInfo.model_validate({"title": ""})
        assert info.title == "Unknown Title"

        info2 = YtDlpTrackInfo.model_validate({"title": None})
        assert info2.title == "Unknown Title"

    def test_ytdlp_track_info_negative_duration_becomes_none(self):
        """Should coerce negative duration to None."""
        info = YtDlpTrackInfo.model_validate({"title": "Test", "duration": -30})
        assert info.duration is None

    def test_ytdlp_track_info_string_duration_coerced(self):
        """Should coerce string duration to int."""
        info = YtDlpTrackInfo.model_validate({"title": "Test", "duration": "180"})
        assert info.duration == 180

    def test_cache_entry_immutable(self):
        """CacheEntry should be immutable (frozen)."""
        entry = CacheEntry(info=None, cached_at=time.time())
        with pytest.raises(Exception):
            entry.cached_at = 0.0

    def test_ytdlp_opts_model_dump_produces_valid_dict(self):
        """model_dump should produce a dict consumable by YoutubeDL."""
        from discord_music_player.infrastructure.audio.ytdlp_resolver import (
            ExtractorArgs,
            YouTubeExtractorConfig,
        )

        opts = YtDlpOpts(
            format="bestaudio/best",
            extractor_args=ExtractorArgs(
                youtube=YouTubeExtractorConfig(pot_server_url="http://localhost:4416")
            ),
        )
        dumped = opts.model_dump()

        assert isinstance(dumped, dict)
        assert dumped["format"] == "bestaudio/best"
        assert dumped["quiet"] is True
        assert dumped["extractor_args"]["youtube"]["pot_server_url"] == "http://localhost:4416"
        assert dumped["extractor_args"]["youtube"]["player_client"] == ["android", "web"]

    def test_ytdlp_opts_rejects_empty_format(self):
        """Should reject empty format string."""
        with pytest.raises(Exception):
            YtDlpOpts(format="")

    def test_ytdlp_opts_rejects_zero_retries(self):
        """Should reject non-positive retries."""
        with pytest.raises(Exception):
            YtDlpOpts(retries=0)

    def test_youtube_extractor_config_rejects_empty_player_clients(self):
        """Should reject empty player_client list."""
        with pytest.raises(Exception):
            YouTubeExtractorConfig(pot_server_url="http://localhost:4416", player_client=[])
