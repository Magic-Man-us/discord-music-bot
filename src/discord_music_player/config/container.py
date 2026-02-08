"""Dependency Injection Container

Manages the application's dependency graph, providing lazy initialization
and lifecycle management for all services, repositories, adapters, and handlers.
Components are created on-demand and cached for reuse throughout the application.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from discord.ext.commands import Bot

    from ..application.commands.clear_queue import ClearQueueHandler
    from ..application.commands.play_track import PlayTrackHandler
    from ..application.commands.skip_track import SkipTrackHandler
    from ..application.commands.stop_playback import StopPlaybackHandler
    from ..application.commands.vote_skip import VoteSkipHandler
    from ..application.interfaces.ai_client import AIClient
    from ..application.interfaces.audio_resolver import AudioResolver
    from ..application.interfaces.voice_adapter import VoiceAdapter
    from ..application.queries.get_current import GetCurrentTrackHandler
    from ..application.queries.get_queue import GetQueueHandler
    from ..application.services.playback_service import PlaybackApplicationService
    from ..application.services.queue_service import QueueApplicationService
    from ..application.services.radio_auto_refill import RadioAutoRefill
    from ..application.services.radio_service import RadioApplicationService
    from ..application.services.requester_leave_autoskip import (
        AutoSkipOnRequesterLeave,
    )
    from ..domain.music.repository import SessionRepository, TrackHistoryRepository
    from ..domain.music.services import PlaybackDomainService, QueueDomainService
    from ..domain.recommendations.repository import RecommendationCacheRepository
    from ..domain.voting.repository import VoteSessionRepository
    from ..domain.voting.services import VotingDomainService
    from ..infrastructure.discord.services.voice_warmup import VoiceWarmupTracker
    from ..infrastructure.persistence.database import Database
    from .settings import Settings


@dataclass
class Container:
    """Dependency injection container.

    This container manages all application dependencies and their lifecycle.
    Components are lazily initialized when first accessed.
    """

    settings: Settings
    _bot: Bot | None = None
    _instances: dict[str, Any] = field(default_factory=dict)

    # Persistence layer
    _database: Database | None = None
    _session_repository: SessionRepository | None = None
    _history_repository: TrackHistoryRepository | None = None
    _vote_repository: VoteSessionRepository | None = None
    _cache_repository: RecommendationCacheRepository | None = None

    # Infrastructure adapters
    _audio_resolver: AudioResolver | None = None
    _voice_adapter: VoiceAdapter | None = None
    _ai_client: AIClient | None = None

    # Domain services
    _queue_domain_service: QueueDomainService | None = None
    _playback_domain_service: PlaybackDomainService | None = None
    _voting_domain_service: VotingDomainService | None = None

    # Application services
    _playback_service: PlaybackApplicationService | None = None
    _queue_service: QueueApplicationService | None = None

    # Discord interaction helpers
    _voice_warmup_tracker: VoiceWarmupTracker | None = None

    # Cross-cutting event subscribers
    _auto_skip_on_requester_leave: AutoSkipOnRequesterLeave | None = None
    _radio_service: RadioApplicationService | None = None
    _radio_auto_refill: RadioAutoRefill | None = None

    # Command handlers
    _play_track_handler: PlayTrackHandler | None = None
    _skip_track_handler: SkipTrackHandler | None = None
    _stop_playback_handler: StopPlaybackHandler | None = None
    _clear_queue_handler: ClearQueueHandler | None = None
    _vote_skip_handler: VoteSkipHandler | None = None

    # Query handlers
    _get_queue_handler: GetQueueHandler | None = None
    _get_current_handler: GetCurrentTrackHandler | None = None

    # Background jobs
    _cleanup_job: Any = None  # CleanupJob

    def set_bot(self, bot: Bot) -> None:
        """Set the Discord bot instance."""
        self._bot = bot

    @property
    def bot(self) -> Bot:
        """Get the Discord bot instance."""
        if self._bot is None:
            raise RuntimeError("Bot not initialized. Call set_bot() first.")
        return self._bot

    # === Database ===

    @property
    def database(self) -> Database:
        """Get the database connection manager."""
        if self._database is None:
            from ..infrastructure.persistence.database import Database

            self._database = Database(self.settings.database.url, settings=self.settings.database)
        return self._database

    # === Repositories ===

    @property
    def session_repository(self) -> SessionRepository:
        """Get the session repository."""
        if self._session_repository is None:
            from ..infrastructure.persistence.repositories.session_repository import (
                SQLiteSessionRepository,
            )

            self._session_repository = SQLiteSessionRepository(self.database)
        return self._session_repository

    @property
    def history_repository(self) -> TrackHistoryRepository:
        """Get the track history repository."""
        if self._history_repository is None:
            from ..infrastructure.persistence.repositories.history_repository import (
                SQLiteHistoryRepository,
            )

            self._history_repository = SQLiteHistoryRepository(self.database)
        return self._history_repository

    @property
    def vote_repository(self) -> VoteSessionRepository:
        """Get the vote session repository."""
        if self._vote_repository is None:
            from ..infrastructure.persistence.repositories.vote_repository import (
                SQLiteVoteSessionRepository,
            )

            self._vote_repository = SQLiteVoteSessionRepository(self.database)
        return self._vote_repository

    @property
    def cache_repository(self) -> RecommendationCacheRepository:
        """Get the recommendation cache repository."""
        if self._cache_repository is None:
            from ..infrastructure.persistence.repositories.cache_repository import (
                SQLiteCacheRepository,
            )

            self._cache_repository = SQLiteCacheRepository(self.database)
        return self._cache_repository

    # === Infrastructure Adapters ===

    @property
    def audio_resolver(self) -> AudioResolver:
        """Get the audio resolver."""
        if self._audio_resolver is None:
            from ..infrastructure.audio.ytdlp_resolver import YtDlpResolver

            self._audio_resolver = YtDlpResolver(self.settings.audio)
        return self._audio_resolver

    @property
    def voice_adapter(self) -> VoiceAdapter:
        """Get the voice adapter."""
        if self._voice_adapter is None:
            from ..infrastructure.discord.adapters.voice_adapter import (
                DiscordVoiceAdapter,
            )

            self._voice_adapter = DiscordVoiceAdapter(self.bot, self.settings.audio)
        return self._voice_adapter

    @property
    def ai_client(self) -> AIClient:
        """Get the AI client."""
        if self._ai_client is None:
            from ..infrastructure.ai.openai_client import OpenAIRecommendationClient

            self._ai_client = OpenAIRecommendationClient(self.settings.ai)
        return self._ai_client

    # === Domain Services ===

    @property
    def queue_domain_service(self) -> QueueDomainService:
        """Get the queue domain service."""
        if self._queue_domain_service is None:
            from ..domain.music.services import QueueDomainService

            self._queue_domain_service = QueueDomainService()
        return self._queue_domain_service

    @property
    def playback_domain_service(self) -> PlaybackDomainService:
        """Get the playback domain service."""
        if self._playback_domain_service is None:
            from ..domain.music.services import PlaybackDomainService

            self._playback_domain_service = PlaybackDomainService()
        return self._playback_domain_service

    @property
    def voting_domain_service(self) -> VotingDomainService:
        """Get the voting domain service."""
        if self._voting_domain_service is None:
            from ..domain.voting.services import VotingDomainService

            self._voting_domain_service = VotingDomainService()
        return self._voting_domain_service

    # === Application Services ===

    @property
    def playback_service(self) -> PlaybackApplicationService:
        """Get the playback application service."""
        if self._playback_service is None:
            from ..application.services.playback_service import (
                PlaybackApplicationService,
            )

            self._playback_service = PlaybackApplicationService(
                session_repository=self.session_repository,
                history_repository=self.history_repository,
                voice_adapter=self.voice_adapter,
                audio_resolver=self.audio_resolver,
                playback_domain_service=self.playback_domain_service,
            )
        return self._playback_service

    @property
    def queue_service(self) -> QueueApplicationService:
        """Get the queue application service."""
        if self._queue_service is None:
            from ..application.services.queue_service import QueueApplicationService

            self._queue_service = QueueApplicationService(
                session_repository=self.session_repository,
                queue_domain_service=self.queue_domain_service,
            )
        return self._queue_service

    # === Command Handlers ===

    @property
    def play_track_handler(self) -> PlayTrackHandler:
        """Get the play track command handler."""
        if self._play_track_handler is None:
            from ..application.commands.play_track import PlayTrackHandler

            self._play_track_handler = PlayTrackHandler(
                session_repository=self.session_repository,
                audio_resolver=self.audio_resolver,
                voice_adapter=self.voice_adapter,
            )
        return self._play_track_handler

    @property
    def skip_track_handler(self) -> SkipTrackHandler:
        """Get the skip track command handler."""
        if self._skip_track_handler is None:
            from ..application.commands.skip_track import SkipTrackHandler

            self._skip_track_handler = SkipTrackHandler(
                session_repository=self.session_repository,
                voice_adapter=self.voice_adapter,
            )
        return self._skip_track_handler

    @property
    def stop_playback_handler(self) -> StopPlaybackHandler:
        """Get the stop playback command handler."""
        if self._stop_playback_handler is None:
            from ..application.commands.stop_playback import StopPlaybackHandler

            self._stop_playback_handler = StopPlaybackHandler(
                session_repository=self.session_repository,
                voice_adapter=self.voice_adapter,
            )
        return self._stop_playback_handler

    @property
    def clear_queue_handler(self) -> ClearQueueHandler:
        """Get the clear queue command handler."""
        if self._clear_queue_handler is None:
            from ..application.commands.clear_queue import ClearQueueHandler

            self._clear_queue_handler = ClearQueueHandler(
                session_repository=self.session_repository,
            )
        return self._clear_queue_handler

    @property
    def vote_skip_handler(self) -> VoteSkipHandler:
        """Get the vote skip command handler."""
        if self._vote_skip_handler is None:
            from ..application.commands.vote_skip import VoteSkipHandler

            self._vote_skip_handler = VoteSkipHandler(
                session_repository=self.session_repository,
                vote_repository=self.vote_repository,
                voice_adapter=self.voice_adapter,
            )
        return self._vote_skip_handler

    # === Discord Helpers ===

    @property
    def voice_warmup_tracker(self) -> VoiceWarmupTracker:
        """Get the in-memory voice warmup tracker."""
        if self._voice_warmup_tracker is None:
            from ..infrastructure.discord.services.voice_warmup import (
                VoiceWarmupTracker,
            )

            self._voice_warmup_tracker = VoiceWarmupTracker(warmup_seconds=60)
        return self._voice_warmup_tracker

    # === Event Subscribers ===

    @property
    def auto_skip_on_requester_leave(self) -> AutoSkipOnRequesterLeave:
        """Get the requester-leave auto-skip subscriber."""
        if self._auto_skip_on_requester_leave is None:
            from ..application.services.requester_leave_autoskip import (
                AutoSkipOnRequesterLeave,
            )

            self._auto_skip_on_requester_leave = AutoSkipOnRequesterLeave(
                session_repository=self.session_repository,
                playback_service=self.playback_service,
            )
        return self._auto_skip_on_requester_leave

    @property
    def radio_service(self) -> RadioApplicationService:
        """Get the radio application service."""
        if self._radio_service is None:
            from ..application.services.radio_service import RadioApplicationService

            self._radio_service = RadioApplicationService(
                ai_client=self.ai_client,
                audio_resolver=self.audio_resolver,
                queue_service=self.queue_service,
                session_repository=self.session_repository,
                settings=self.settings.radio,
            )
        return self._radio_service

    @property
    def radio_auto_refill(self) -> RadioAutoRefill:
        """Get the radio auto-refill subscriber."""
        if self._radio_auto_refill is None:
            from ..application.services.radio_auto_refill import RadioAutoRefill

            self._radio_auto_refill = RadioAutoRefill(
                radio_service=self.radio_service,
                playback_service=self.playback_service,
            )
        return self._radio_auto_refill

    # === Query Handlers ===

    @property
    def get_queue_handler(self) -> GetQueueHandler:
        """Get the get queue query handler."""
        if self._get_queue_handler is None:
            from ..application.queries.get_queue import GetQueueHandler

            self._get_queue_handler = GetQueueHandler(
                session_repository=self.session_repository,
            )
        return self._get_queue_handler

    @property
    def get_current_handler(self) -> GetCurrentTrackHandler:
        """Get the get current track query handler."""
        if self._get_current_handler is None:
            from ..application.queries.get_current import GetCurrentTrackHandler

            self._get_current_handler = GetCurrentTrackHandler(
                session_repository=self.session_repository,
            )
        return self._get_current_handler

    # === Background Jobs ===

    @property
    def cleanup_job(self) -> Any:
        """Get the cleanup job."""
        if self._cleanup_job is None:
            from ..infrastructure.persistence.cleanup import CleanupJob

            self._cleanup_job = CleanupJob(
                session_repository=self.session_repository,
                history_repository=self.history_repository,
                cache_repository=self.cache_repository,
                vote_repository=self.vote_repository,
                settings=self.settings.cleanup,
            )
        return self._cleanup_job

    # === Lifecycle ===

    async def initialize(self) -> None:
        """Initialize all async resources."""
        await self.database.initialize()

        # Start cross-cutting subscribers.
        self.auto_skip_on_requester_leave.start()
        self.radio_auto_refill.start()

    async def shutdown(self) -> None:
        """Shutdown and cleanup all resources."""
        try:
            if self._auto_skip_on_requester_leave is not None:
                self._auto_skip_on_requester_leave.stop()
        except Exception as exc:
            logger.warning("Failed stopping auto-skip subscriber: %r", exc)

        try:
            if self._radio_auto_refill is not None:
                self._radio_auto_refill.stop()
        except Exception as exc:
            logger.warning("Failed stopping radio auto-refill subscriber: %r", exc)

        if self._database is not None:
            await self._database.close()

        # Clear all cached instances
        self._instances.clear()


def create_container(settings: Settings) -> Container:
    """Create a new dependency injection container."""
    return Container(settings)
