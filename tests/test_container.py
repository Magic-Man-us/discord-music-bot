"""
Unit Tests for Dependency Injection Container

Tests for:
- Container initialization with settings
- Lazy initialization (properties create instances on first access)
- Caching (subsequent property access returns same instance)
- Bot instance management (set_bot, bot property, error when not set)
- All repository properties (session, history, vote, cache)
- All service properties (queue, playback, domain services)
- All handler properties (command and query handlers)
- Infrastructure adapters (audio_resolver, voice_adapter, ai_client)
- Lifecycle methods (initialize, shutdown)
- Cleanup job creation
- Voice warmup tracker
- Auto-skip subscriber

Uses mocking to isolate from actual implementations.
"""

from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from discord_music_player.config.container import Container, create_container
from discord_music_player.config.settings import Settings


@pytest.fixture
def mock_settings():
    """Mock Settings object."""
    settings = Mock(spec=Settings)
    settings.database = Mock()
    settings.database.url = "sqlite:///:memory:"
    settings.audio = Mock()
    settings.audio.default_volume = 0.5
    settings.ai = Mock()
    settings.ai.api_key = Mock()
    settings.ai.model = "gpt-4o-mini"
    settings.cleanup = Mock()
    settings.cleanup.stale_session_hours = 24
    settings.radio = Mock()
    settings.radio.default_count = 5
    settings.radio.max_tracks_per_session = 50
    return settings


@pytest.fixture
def container(mock_settings):
    """Create container with mock settings."""
    return Container(settings=mock_settings)


@pytest.fixture
def mock_bot():
    """Mock Discord bot instance."""
    bot = MagicMock()
    bot.user = MagicMock()
    bot.user.id = 123456789
    return bot


# =============================================================================
# Container Initialization Tests
# =============================================================================


class TestContainerInitialization:
    """Unit tests for Container initialization."""

    def test_create_container_with_settings(self, mock_settings):
        """Should create container with settings."""
        container = Container(settings=mock_settings)
        assert container.settings == mock_settings

    def test_create_container_factory(self, mock_settings):
        """Should create container using factory function."""
        container = create_container(mock_settings)
        assert isinstance(container, Container)
        assert container.settings == mock_settings

    def test_initial_state_all_none(self, container):
        """Should initialize with all private attributes as None."""
        assert container._bot is None
        assert container._database is None
        assert container._session_repo is None
        assert container._history_repository is None
        assert container._vote_repository is None
        assert container._cache_repository is None
        assert container._audio_resolver is None
        assert container._voice_adapter is None
        assert container._ai_client is None
        assert container._queue_domain_service is None
        assert container._playback_domain_service is None
        assert container._voting_domain_service is None
        assert container._playback_service is None
        assert container._queue_service is None
        assert container._voice_warmup_tracker is None
        assert container._auto_skip_on_requester_leave is None

    def test_instances_dict_initialized_empty(self, container):
        """Should initialize with empty instances dict."""
        assert container._instances == {}


# =============================================================================
# Bot Instance Management Tests
# =============================================================================


class TestBotManagement:
    """Unit tests for bot instance management."""

    def test_set_bot(self, container, mock_bot):
        """Should set bot instance."""
        container.set_bot(mock_bot)
        assert container._bot == mock_bot

    def test_get_bot_when_set(self, container, mock_bot):
        """Should return bot instance when set."""
        container.set_bot(mock_bot)
        assert container.bot == mock_bot

    def test_get_bot_when_not_set_raises_error(self, container):
        """Should raise RuntimeError when bot not set."""
        with pytest.raises(RuntimeError, match="Bot not initialized"):
            _ = container.bot


# =============================================================================
# Database Tests
# =============================================================================


class TestDatabase:
    """Unit tests for database property."""

    def test_database_lazy_initialization(self, container):
        """Should create database on first access."""
        with patch(
            "discord_music_player.infrastructure.persistence.database.Database"
        ) as MockDatabase:
            db = container.database
            MockDatabase.assert_called_once_with(
                container.settings.database.url, settings=container.settings.database
            )
            assert db == MockDatabase.return_value

    def test_database_caching(self, container):
        """Should return same instance on subsequent calls."""
        with patch(
            "discord_music_player.infrastructure.persistence.database.Database"
        ) as MockDatabase:
            db1 = container.database
            db2 = container.database
            assert db1 is db2
            MockDatabase.assert_called_once()


# =============================================================================
# Repository Tests
# =============================================================================


class TestSessionRepository:
    """Unit tests for session_repository property."""

    def test_lazy_initialization(self, container):
        """Should create repository on first access."""
        with patch(
            "discord_music_player.infrastructure.persistence.repositories.session_repository.SQLiteSessionRepository"
        ) as MockRepo:
            repo = container.session_repository
            MockRepo.assert_called_once_with(container.database)
            assert repo == MockRepo.return_value

    def test_caching(self, container):
        """Should return same instance on subsequent calls."""
        with patch(
            "discord_music_player.infrastructure.persistence.repositories.session_repository.SQLiteSessionRepository"
        ) as MockRepo:
            repo1 = container.session_repository
            repo2 = container.session_repository
            assert repo1 is repo2
            MockRepo.assert_called_once()


class TestHistoryRepository:
    """Unit tests for history_repository property."""

    def test_lazy_initialization(self, container):
        """Should create repository on first access."""
        with patch(
            "discord_music_player.infrastructure.persistence.repositories.history_repository.SQLiteHistoryRepository"
        ) as MockRepo:
            repo = container.history_repository
            MockRepo.assert_called_once_with(container.database)
            assert repo == MockRepo.return_value

    def test_caching(self, container):
        """Should return same instance on subsequent calls."""
        with patch(
            "discord_music_player.infrastructure.persistence.repositories.history_repository.SQLiteHistoryRepository"
        ) as MockRepo:
            repo1 = container.history_repository
            repo2 = container.history_repository
            assert repo1 is repo2
            MockRepo.assert_called_once()


class TestVoteRepository:
    """Unit tests for vote_repository property."""

    def test_lazy_initialization(self, container):
        """Should create repository on first access."""
        with patch(
            "discord_music_player.infrastructure.persistence.repositories.vote_repository.SQLiteVoteSessionRepository"
        ) as MockRepo:
            repo = container.vote_repository
            MockRepo.assert_called_once_with(container.database)
            assert repo == MockRepo.return_value

    def test_caching(self, container):
        """Should return same instance on subsequent calls."""
        with patch(
            "discord_music_player.infrastructure.persistence.repositories.vote_repository.SQLiteVoteSessionRepository"
        ) as MockRepo:
            repo1 = container.vote_repository
            repo2 = container.vote_repository
            assert repo1 is repo2
            MockRepo.assert_called_once()


class TestCacheRepository:
    """Unit tests for cache_repository property."""

    def test_lazy_initialization(self, container):
        """Should create repository on first access."""
        with patch(
            "discord_music_player.infrastructure.persistence.repositories.cache_repository.SQLiteCacheRepository"
        ) as MockRepo:
            repo = container.cache_repository
            MockRepo.assert_called_once_with(container.database)
            assert repo == MockRepo.return_value

    def test_caching(self, container):
        """Should return same instance on subsequent calls."""
        with patch(
            "discord_music_player.infrastructure.persistence.repositories.cache_repository.SQLiteCacheRepository"
        ) as MockRepo:
            repo1 = container.cache_repository
            repo2 = container.cache_repository
            assert repo1 is repo2
            MockRepo.assert_called_once()


# =============================================================================
# Infrastructure Adapter Tests
# =============================================================================


class TestAudioResolver:
    """Unit tests for audio_resolver property."""

    def test_lazy_initialization(self, container):
        """Should create resolver on first access."""
        with patch(
            "discord_music_player.infrastructure.audio.ytdlp_resolver.YtDlpResolver"
        ) as MockResolver:
            resolver = container.audio_resolver
            MockResolver.assert_called_once_with(container.settings.audio)
            assert resolver == MockResolver.return_value

    def test_caching(self, container):
        """Should return same instance on subsequent calls."""
        with patch(
            "discord_music_player.infrastructure.audio.ytdlp_resolver.YtDlpResolver"
        ) as MockResolver:
            resolver1 = container.audio_resolver
            resolver2 = container.audio_resolver
            assert resolver1 is resolver2
            MockResolver.assert_called_once()


class TestVoiceAdapter:
    """Unit tests for voice_adapter property."""

    def test_lazy_initialization(self, container, mock_bot):
        """Should create adapter on first access."""
        container.set_bot(mock_bot)
        with patch(
            "discord_music_player.infrastructure.discord.adapters.voice_adapter.DiscordVoiceAdapter"
        ) as MockAdapter:
            adapter = container.voice_adapter
            MockAdapter.assert_called_once_with(mock_bot, container.settings.audio)
            assert adapter == MockAdapter.return_value

    def test_caching(self, container, mock_bot):
        """Should return same instance on subsequent calls."""
        container.set_bot(mock_bot)
        with patch(
            "discord_music_player.infrastructure.discord.adapters.voice_adapter.DiscordVoiceAdapter"
        ) as MockAdapter:
            adapter1 = container.voice_adapter
            adapter2 = container.voice_adapter
            assert adapter1 is adapter2
            MockAdapter.assert_called_once()

    def test_requires_bot_to_be_set(self, container):
        """Should raise error when bot not set."""
        with pytest.raises(RuntimeError, match="Bot not initialized"):
            _ = container.voice_adapter


class TestAIClient:
    """Unit tests for ai_client property."""

    def test_lazy_initialization(self, container):
        """Should create client on first access."""
        with patch(
            "discord_music_player.infrastructure.ai.openai_client.OpenAIRecommendationClient"
        ) as MockClient:
            client = container.ai_client
            MockClient.assert_called_once_with(container.settings.ai)
            assert client == MockClient.return_value

    def test_caching(self, container):
        """Should return same instance on subsequent calls."""
        with patch(
            "discord_music_player.infrastructure.ai.openai_client.OpenAIRecommendationClient"
        ) as MockClient:
            client1 = container.ai_client
            client2 = container.ai_client
            assert client1 is client2
            MockClient.assert_called_once()


# =============================================================================
# Domain Service Tests
# =============================================================================


class TestQueueDomainService:
    """Unit tests for queue_domain_service property."""

    def test_lazy_initialization(self, container):
        """Should create service on first access."""
        with patch("discord_music_player.domain.music.services.QueueDomainService") as MockService:
            service = container.queue_domain_service
            MockService.assert_called_once_with()
            assert service == MockService.return_value

    def test_caching(self, container):
        """Should return same instance on subsequent calls."""
        with patch("discord_music_player.domain.music.services.QueueDomainService") as MockService:
            service1 = container.queue_domain_service
            service2 = container.queue_domain_service
            assert service1 is service2
            MockService.assert_called_once()


class TestPlaybackDomainService:
    """Unit tests for playback_domain_service property."""

    def test_lazy_initialization(self, container):
        """Should create service on first access."""
        with patch(
            "discord_music_player.domain.music.services.PlaybackDomainService"
        ) as MockService:
            service = container.playback_domain_service
            MockService.assert_called_once_with()
            assert service == MockService.return_value

    def test_caching(self, container):
        """Should return same instance on subsequent calls."""
        with patch(
            "discord_music_player.domain.music.services.PlaybackDomainService"
        ) as MockService:
            service1 = container.playback_domain_service
            service2 = container.playback_domain_service
            assert service1 is service2
            MockService.assert_called_once()


class TestVotingDomainService:
    """Unit tests for voting_domain_service property."""

    def test_lazy_initialization(self, container):
        """Should create service on first access."""
        with patch(
            "discord_music_player.domain.voting.services.VotingDomainService"
        ) as MockService:
            service = container.voting_domain_service
            MockService.assert_called_once_with()
            assert service == MockService.return_value

    def test_caching(self, container):
        """Should return same instance on subsequent calls."""
        with patch(
            "discord_music_player.domain.voting.services.VotingDomainService"
        ) as MockService:
            service1 = container.voting_domain_service
            service2 = container.voting_domain_service
            assert service1 is service2
            MockService.assert_called_once()


# =============================================================================
# Application Service Tests
# =============================================================================


class TestPlaybackService:
    """Unit tests for playback_service property."""

    def test_lazy_initialization(self, container, mock_bot):
        """Should create service with correct dependencies."""
        container.set_bot(mock_bot)
        with patch(
            "discord_music_player.application.services.playback_service.PlaybackApplicationService"
        ) as MockService:
            service = container.playback_service
            MockService.assert_called_once_with(
                session_repository=container.session_repository,
                history_repository=container.history_repository,
                voice_adapter=container.voice_adapter,
                audio_resolver=container.audio_resolver,
                playback_domain_service=container.playback_domain_service,
            )
            assert service == MockService.return_value

    def test_caching(self, container, mock_bot):
        """Should return same instance on subsequent calls."""
        container.set_bot(mock_bot)
        with patch(
            "discord_music_player.application.services.playback_service.PlaybackApplicationService"
        ) as MockService:
            service1 = container.playback_service
            service2 = container.playback_service
            assert service1 is service2
            MockService.assert_called_once()


class TestQueueService:
    """Unit tests for queue_service property."""

    def test_lazy_initialization(self, container):
        """Should create service with correct dependencies."""
        with patch(
            "discord_music_player.application.services.queue_service.QueueApplicationService"
        ) as MockService:
            service = container.queue_service
            MockService.assert_called_once_with(
                session_repository=container.session_repository,
                queue_domain_service=container.queue_domain_service,
            )
            assert service == MockService.return_value

    def test_caching(self, container):
        """Should return same instance on subsequent calls."""
        with patch(
            "discord_music_player.application.services.queue_service.QueueApplicationService"
        ) as MockService:
            service1 = container.queue_service
            service2 = container.queue_service
            assert service1 is service2
            MockService.assert_called_once()


# =============================================================================
# Command Handler Tests
# =============================================================================


class TestPlayTrackHandler:
    """Unit tests for play_track_handler property."""

    def test_lazy_initialization(self, container, mock_bot):
        """Should create handler with correct dependencies."""
        container.set_bot(mock_bot)
        with patch(
            "discord_music_player.application.commands.play_track.PlayTrackHandler"
        ) as MockHandler:
            handler = container.play_track_handler
            MockHandler.assert_called_once_with(
                session_repository=container.session_repository,
                audio_resolver=container.audio_resolver,
                voice_adapter=container.voice_adapter,
            )
            assert handler == MockHandler.return_value

    def test_caching(self, container, mock_bot):
        """Should return same instance on subsequent calls."""
        container.set_bot(mock_bot)
        with patch(
            "discord_music_player.application.commands.play_track.PlayTrackHandler"
        ) as MockHandler:
            handler1 = container.play_track_handler
            handler2 = container.play_track_handler
            assert handler1 is handler2
            MockHandler.assert_called_once()


class TestSkipTrackHandler:
    """Unit tests for skip_track_handler property."""

    def test_lazy_initialization(self, container, mock_bot):
        """Should create handler with correct dependencies."""
        container.set_bot(mock_bot)
        with patch(
            "discord_music_player.application.commands.skip_track.SkipTrackHandler"
        ) as MockHandler:
            handler = container.skip_track_handler
            MockHandler.assert_called_once_with(
                session_repository=container.session_repository,
                voice_adapter=container.voice_adapter,
            )
            assert handler == MockHandler.return_value

    def test_caching(self, container, mock_bot):
        """Should return same instance on subsequent calls."""
        container.set_bot(mock_bot)
        with patch(
            "discord_music_player.application.commands.skip_track.SkipTrackHandler"
        ) as MockHandler:
            handler1 = container.skip_track_handler
            handler2 = container.skip_track_handler
            assert handler1 is handler2
            MockHandler.assert_called_once()


class TestStopPlaybackHandler:
    """Unit tests for stop_playback_handler property."""

    def test_lazy_initialization(self, container, mock_bot):
        """Should create handler with correct dependencies."""
        container.set_bot(mock_bot)
        with patch(
            "discord_music_player.application.commands.stop_playback.StopPlaybackHandler"
        ) as MockHandler:
            handler = container.stop_playback_handler
            MockHandler.assert_called_once_with(
                session_repository=container.session_repository,
                voice_adapter=container.voice_adapter,
            )
            assert handler == MockHandler.return_value

    def test_caching(self, container, mock_bot):
        """Should return same instance on subsequent calls."""
        container.set_bot(mock_bot)
        with patch(
            "discord_music_player.application.commands.stop_playback.StopPlaybackHandler"
        ) as MockHandler:
            handler1 = container.stop_playback_handler
            handler2 = container.stop_playback_handler
            assert handler1 is handler2
            MockHandler.assert_called_once()


class TestClearQueueHandler:
    """Unit tests for clear_queue_handler property."""

    def test_lazy_initialization(self, container):
        """Should create handler with correct dependencies."""
        with patch(
            "discord_music_player.application.commands.clear_queue.ClearQueueHandler"
        ) as MockHandler:
            handler = container.clear_queue_handler
            MockHandler.assert_called_once_with(
                session_repository=container.session_repository,
            )
            assert handler == MockHandler.return_value

    def test_caching(self, container):
        """Should return same instance on subsequent calls."""
        with patch(
            "discord_music_player.application.commands.clear_queue.ClearQueueHandler"
        ) as MockHandler:
            handler1 = container.clear_queue_handler
            handler2 = container.clear_queue_handler
            assert handler1 is handler2
            MockHandler.assert_called_once()


class TestVoteSkipHandler:
    """Unit tests for vote_skip_handler property."""

    def test_lazy_initialization(self, container, mock_bot):
        """Should create handler with correct dependencies."""
        container.set_bot(mock_bot)
        with patch(
            "discord_music_player.application.commands.vote_skip.VoteSkipHandler"
        ) as MockHandler:
            handler = container.vote_skip_handler
            MockHandler.assert_called_once_with(
                session_repository=container.session_repository,
                vote_repository=container.vote_repository,
                voice_adapter=container.voice_adapter,
            )
            assert handler == MockHandler.return_value

    def test_caching(self, container, mock_bot):
        """Should return same instance on subsequent calls."""
        container.set_bot(mock_bot)
        with patch(
            "discord_music_player.application.commands.vote_skip.VoteSkipHandler"
        ) as MockHandler:
            handler1 = container.vote_skip_handler
            handler2 = container.vote_skip_handler
            assert handler1 is handler2
            MockHandler.assert_called_once()


# =============================================================================
# Query Handler Tests
# =============================================================================


class TestGetQueueHandler:
    """Unit tests for get_queue_handler property."""

    def test_lazy_initialization(self, container):
        """Should create handler with correct dependencies."""
        with patch(
            "discord_music_player.application.queries.get_queue.GetQueueHandler"
        ) as MockHandler:
            handler = container.get_queue_handler
            MockHandler.assert_called_once_with(
                session_repository=container.session_repository,
            )
            assert handler == MockHandler.return_value

    def test_caching(self, container):
        """Should return same instance on subsequent calls."""
        with patch(
            "discord_music_player.application.queries.get_queue.GetQueueHandler"
        ) as MockHandler:
            handler1 = container.get_queue_handler
            handler2 = container.get_queue_handler
            assert handler1 is handler2
            MockHandler.assert_called_once()


class TestGetCurrentHandler:
    """Unit tests for get_current_handler property."""

    def test_lazy_initialization(self, container):
        """Should create handler with correct dependencies."""
        with patch(
            "discord_music_player.application.queries.get_current.GetCurrentTrackHandler"
        ) as MockHandler:
            handler = container.get_current_handler
            MockHandler.assert_called_once_with(
                session_repository=container.session_repository,
            )
            assert handler == MockHandler.return_value

    def test_caching(self, container):
        """Should return same instance on subsequent calls."""
        with patch(
            "discord_music_player.application.queries.get_current.GetCurrentTrackHandler"
        ) as MockHandler:
            handler1 = container.get_current_handler
            handler2 = container.get_current_handler
            assert handler1 is handler2
            MockHandler.assert_called_once()


# =============================================================================
# Voice Warmup Tracker Tests
# =============================================================================


class TestVoiceWarmupTracker:
    """Unit tests for voice_warmup_tracker property."""

    def test_lazy_initialization(self, container):
        """Should create tracker with warmup_seconds=60."""
        with patch(
            "discord_music_player.infrastructure.discord.services.voice_warmup.VoiceWarmupTracker"
        ) as MockTracker:
            tracker = container.voice_warmup_tracker
            MockTracker.assert_called_once_with(warmup_seconds=60)
            assert tracker == MockTracker.return_value

    def test_caching(self, container):
        """Should return same instance on subsequent calls."""
        with patch(
            "discord_music_player.infrastructure.discord.services.voice_warmup.VoiceWarmupTracker"
        ) as MockTracker:
            tracker1 = container.voice_warmup_tracker
            tracker2 = container.voice_warmup_tracker
            assert tracker1 is tracker2
            MockTracker.assert_called_once()


# =============================================================================
# Auto-Skip Subscriber Tests
# =============================================================================


class TestAutoSkipOnRequesterLeave:
    """Unit tests for auto_skip_on_requester_leave property."""

    def test_lazy_initialization(self, container, mock_bot):
        """Should create subscriber with correct dependencies."""
        container.set_bot(mock_bot)
        with patch(
            "discord_music_player.application.services.requester_leave_autoskip.AutoSkipOnRequesterLeave"
        ) as MockSubscriber:
            subscriber = container.auto_skip_on_requester_leave
            MockSubscriber.assert_called_once_with(
                session_repository=container.session_repository,
                playback_service=container.playback_service,
                voice_adapter=container.voice_adapter,
            )
            assert subscriber == MockSubscriber.return_value

    def test_caching(self, container, mock_bot):
        """Should return same instance on subsequent calls."""
        container.set_bot(mock_bot)
        with patch(
            "discord_music_player.application.services.requester_leave_autoskip.AutoSkipOnRequesterLeave"
        ) as MockSubscriber:
            subscriber1 = container.auto_skip_on_requester_leave
            subscriber2 = container.auto_skip_on_requester_leave
            assert subscriber1 is subscriber2
            MockSubscriber.assert_called_once()


# =============================================================================
# Cleanup Job Tests
# =============================================================================


class TestCleanupJob:
    """Unit tests for cleanup_job property."""

    def test_lazy_initialization(self, container):
        """Should create job with correct dependencies."""
        with patch("discord_music_player.infrastructure.persistence.cleanup.CleanupJob") as MockJob:
            job = container.cleanup_job
            MockJob.assert_called_once_with(
                session_repository=container.session_repository,
                history_repository=container.history_repository,
                cache_repository=container.cache_repository,
                vote_repository=container.vote_repository,
                settings=container.settings.cleanup,
            )
            assert job == MockJob.return_value

    def test_caching(self, container):
        """Should return same instance on subsequent calls."""
        with patch("discord_music_player.infrastructure.persistence.cleanup.CleanupJob") as MockJob:
            job1 = container.cleanup_job
            job2 = container.cleanup_job
            assert job1 is job2
            MockJob.assert_called_once()


# =============================================================================
# Lifecycle Tests
# =============================================================================


class TestLifecycleInitialize:
    """Unit tests for container.initialize method."""

    @pytest.mark.asyncio
    async def test_initialize_database(self, container, mock_bot):
        """Should initialize database."""
        container.set_bot(mock_bot)
        mock_db = AsyncMock()
        mock_subscriber = MagicMock()
        container._database = mock_db
        container._auto_skip_on_requester_leave = mock_subscriber

        await container.initialize()

        mock_db.initialize.assert_called_once()

    @pytest.mark.asyncio
    async def test_initialize_starts_auto_skip_subscriber(self, container, mock_bot):
        """Should start auto-skip subscriber."""
        container.set_bot(mock_bot)
        mock_db = AsyncMock()
        mock_subscriber = MagicMock()
        container._database = mock_db
        container._auto_skip_on_requester_leave = mock_subscriber

        await container.initialize()

        mock_subscriber.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_initialize_creates_auto_skip_if_not_exists(self, container, mock_bot):
        """Should create auto-skip subscriber if not already created."""
        container.set_bot(mock_bot)
        mock_db = AsyncMock()
        container._database = mock_db

        with patch(
            "discord_music_player.application.services.requester_leave_autoskip.AutoSkipOnRequesterLeave"
        ) as MockSubscriber:
            mock_instance = MagicMock()
            MockSubscriber.return_value = mock_instance

            await container.initialize()

            mock_instance.start.assert_called_once()


class TestLifecycleShutdown:
    """Unit tests for container.shutdown method."""

    @pytest.mark.asyncio
    async def test_shutdown_stops_auto_skip_subscriber(self, container):
        """Should stop auto-skip subscriber if exists."""
        mock_subscriber = MagicMock()
        container._auto_skip_on_requester_leave = mock_subscriber

        await container.shutdown()

        mock_subscriber.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_shutdown_handles_subscriber_error(self, container):
        """Should handle errors when stopping subscriber."""
        mock_subscriber = MagicMock()
        mock_subscriber.stop.side_effect = Exception("Stop failed")
        container._auto_skip_on_requester_leave = mock_subscriber

        # Should not raise
        await container.shutdown()

    @pytest.mark.asyncio
    async def test_shutdown_closes_database(self, container):
        """Should close database if exists."""
        mock_db = AsyncMock()
        container._database = mock_db

        await container.shutdown()

        mock_db.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_shutdown_clears_instances(self, container):
        """Should clear instances dict."""
        container._instances = {"test": "value"}

        await container.shutdown()

        assert container._instances == {}

    @pytest.mark.asyncio
    async def test_shutdown_without_database(self, container):
        """Should not fail when database not initialized."""
        # Database is None
        assert container._database is None

        # Should not raise
        await container.shutdown()

    @pytest.mark.asyncio
    async def test_shutdown_full_lifecycle(self, container):
        """Should handle complete shutdown sequence."""
        mock_subscriber = MagicMock()
        mock_db = AsyncMock()
        container._auto_skip_on_requester_leave = mock_subscriber
        container._database = mock_db
        container._instances = {"key": "value"}

        await container.shutdown()

        mock_subscriber.stop.assert_called_once()
        mock_db.close.assert_called_once()
        assert container._instances == {}


# =============================================================================
# Integration Tests
# =============================================================================


class TestContainerIntegration:
    """Integration tests verifying multiple components work together."""

    def test_dependencies_cascade_correctly(self, container, mock_bot):
        """Should create all dependencies when accessing a high-level service."""
        container.set_bot(mock_bot)

        # Access playback_service which depends on many components
        with patch(
            "discord_music_player.application.services.playback_service.PlaybackApplicationService"
        ):
            service = container.playback_service

            # All dependencies should be created
            assert container._session_repo is not None
            assert container._history_repository is not None
            assert container._voice_adapter is not None
            assert container._audio_resolver is not None
            assert container._playback_domain_service is not None

    def test_multiple_handlers_share_repositories(self, container, mock_bot):
        """Should share repository instances across handlers."""
        container.set_bot(mock_bot)

        with (
            patch("discord_music_player.application.commands.play_track.PlayTrackHandler"),
            patch("discord_music_player.application.commands.skip_track.SkipTrackHandler"),
            patch("discord_music_player.application.commands.vote_skip.VoteSkipHandler"),
        ):
            # Access multiple handlers
            _ = container.play_track_handler
            _ = container.skip_track_handler
            _ = container.vote_skip_handler

            # All should share the same session_repository instance
            assert container._session_repo is not None
            # The repository should only be created once
            # (Verified by caching tests above)
