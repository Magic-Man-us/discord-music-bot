"""Lazy-initializing dependency injection container for all application components."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from discord.ext.commands import Bot

    from ..application.commands.vote_skip import VoteSkipHandler
    from ..application.interfaces.ai_client import AIClient
    from ..application.interfaces.audio_resolver import AudioResolver
    from ..application.interfaces.voice_adapter import VoiceAdapter
    from ..application.services.playback_service import PlaybackApplicationService
    from ..application.services.queue_service import QueueApplicationService
    from ..application.services.radio_auto_refill import RadioAutoRefill
    from ..application.services.radio_service import RadioApplicationService
    from ..application.services.auto_dj import AutoDJ
    from ..application.services.requester_leave_autoskip import (
        AutoSkipOnRequesterLeave,
    )
    from ..domain.music.repository import SessionRepository, TrackHistoryRepository
    from ..domain.recommendations.repository import RecommendationCacheRepository
    from ..domain.voting.repository import VoteSessionRepository
    from ..infrastructure.ai.genre_classifier import AIGenreClassifier
    from ..infrastructure.charts.chart_generator import ChartGenerator
    from ..infrastructure.discord.services.message_state_manager import MessageStateManager
    from ..infrastructure.discord.services.voice_warmup import VoiceWarmupTracker
    from ..infrastructure.persistence.cleanup import CleanupJob
    from ..infrastructure.persistence.database import Database
    from ..infrastructure.persistence.repositories.favorites_repository import (
        SQLiteFavoritesRepository,
    )
    from ..infrastructure.persistence.repositories.saved_queue_repository import (
        SQLiteSavedQueueRepository,
    )
    from ..infrastructure.persistence.repositories.genre_repository import (
        SQLiteGenreCacheRepository,
    )
    from .settings import Settings


@dataclass  # noqa: not-a-boundary
class Container:
    """Lazy-initializing service locator for all application components.

    Uses stdlib ``dataclass`` intentionally — this is not a data boundary.
    All type annotations live under ``TYPE_CHECKING`` to avoid eagerly
    importing the entire application graph.  Pydantic dataclasses cannot
    work here because ``rebuild_dataclass`` requires every annotated type
    to be resolvable at rebuild time, defeating the lazy-import pattern.
    """

    settings: Settings
    _bot: Bot | None = None

    # Persistence layer
    _database: Database | None = None
    _session_repository: SessionRepository | None = None
    _history_repository: TrackHistoryRepository | None = None
    _vote_repository: VoteSessionRepository | None = None
    _cache_repository: RecommendationCacheRepository | None = None
    _favorites_repository: SQLiteFavoritesRepository | None = None
    _saved_queue_repository: SQLiteSavedQueueRepository | None = None

    # Analytics
    _genre_repository: SQLiteGenreCacheRepository | None = None
    _genre_classifier: AIGenreClassifier | None = None
    _chart_generator: ChartGenerator | None = None

    # Infrastructure adapters
    _audio_resolver: AudioResolver | None = None
    _voice_adapter: VoiceAdapter | None = None
    _ai_client: AIClient | None = None
    _shuffle_ai_client: AIClient | None = None

    # Application services
    _playback_service: PlaybackApplicationService | None = None
    _queue_service: QueueApplicationService | None = None

    # Discord interaction helpers
    _voice_warmup_tracker: VoiceWarmupTracker | None = None
    _message_state_manager: MessageStateManager | None = None

    # Cross-cutting event subscribers
    _auto_skip_on_requester_leave: AutoSkipOnRequesterLeave | None = None
    _radio_service: RadioApplicationService | None = None
    _radio_auto_refill: RadioAutoRefill | None = None
    _auto_dj: AutoDJ | None = None

    # Command handlers
    _vote_skip_handler: VoteSkipHandler | None = None

    # Background jobs
    _cleanup_job: CleanupJob | None = None

    def set_bot(self, bot: Bot) -> None:
        self._bot = bot

    @property
    def bot(self) -> Bot:
        if self._bot is None:
            raise RuntimeError("Bot not initialized. Call set_bot() first.")
        return self._bot

    # === Database ===

    @property
    def database(self) -> Database:
        if self._database is None:
            from ..infrastructure.persistence.database import Database

            self._database = Database(self.settings.database.url, settings=self.settings.database)
        return self._database

    # === Repositories ===

    @property
    def session_repository(self) -> SessionRepository:
        if self._session_repository is None:
            from ..infrastructure.persistence.repositories.session_repository import (
                SQLiteSessionRepository,
            )

            self._session_repository = SQLiteSessionRepository(self.database)
        return self._session_repository

    @property
    def history_repository(self) -> TrackHistoryRepository:
        if self._history_repository is None:
            from ..infrastructure.persistence.repositories.history_repository import (
                SQLiteHistoryRepository,
            )

            self._history_repository = SQLiteHistoryRepository(self.database)
        return self._history_repository

    @property
    def vote_repository(self) -> VoteSessionRepository:
        if self._vote_repository is None:
            from ..infrastructure.persistence.repositories.vote_repository import (
                SQLiteVoteSessionRepository,
            )

            self._vote_repository = SQLiteVoteSessionRepository(self.database)
        return self._vote_repository

    @property
    def cache_repository(self) -> RecommendationCacheRepository:
        if self._cache_repository is None:
            from ..infrastructure.persistence.repositories.cache_repository import (
                SQLiteCacheRepository,
            )

            self._cache_repository = SQLiteCacheRepository(self.database)
        return self._cache_repository


    @property
    def favorites_repository(self) -> SQLiteFavoritesRepository:
        if self._favorites_repository is None:
            from ..infrastructure.persistence.repositories.favorites_repository import (
                SQLiteFavoritesRepository,
            )

            self._favorites_repository = SQLiteFavoritesRepository(self.database)
        return self._favorites_repository


    @property
    def saved_queue_repository(self) -> SQLiteSavedQueueRepository:
        if self._saved_queue_repository is None:
            from ..infrastructure.persistence.repositories.saved_queue_repository import (
                SQLiteSavedQueueRepository,
            )

            self._saved_queue_repository = SQLiteSavedQueueRepository(self.database)
        return self._saved_queue_repository

    # === Analytics ===

    @property
    def genre_repository(self) -> SQLiteGenreCacheRepository:
        if self._genre_repository is None:
            from ..infrastructure.persistence.repositories.genre_repository import (
                SQLiteGenreCacheRepository,
            )

            self._genre_repository = SQLiteGenreCacheRepository(self.database)
        return self._genre_repository

    @property
    def genre_classifier(self) -> AIGenreClassifier:
        if self._genre_classifier is None:
            from ..infrastructure.ai.genre_classifier import AIGenreClassifier

            self._genre_classifier = AIGenreClassifier(self.settings.ai)
        return self._genre_classifier

    @property
    def chart_generator(self) -> ChartGenerator:
        if self._chart_generator is None:
            from ..infrastructure.charts.chart_generator import ChartGenerator

            self._chart_generator = ChartGenerator()
        return self._chart_generator

    # === Infrastructure Adapters ===

    @property
    def audio_resolver(self) -> AudioResolver:
        if self._audio_resolver is None:
            from ..infrastructure.audio.ytdlp_resolver import YtDlpResolver

            self._audio_resolver = YtDlpResolver(self.settings.audio)
        return self._audio_resolver

    @property
    def voice_adapter(self) -> VoiceAdapter:
        if self._voice_adapter is None:
            from ..infrastructure.discord.adapters.voice_adapter import (
                DiscordVoiceAdapter,
            )

            self._voice_adapter = DiscordVoiceAdapter(self.bot, self.settings.audio)
        return self._voice_adapter

    @property
    def ai_enabled(self) -> bool:
        return self.settings.ai.enabled

    @property
    def ai_client(self) -> AIClient:
        if self._ai_client is None:
            if not self.ai_enabled:
                from ..infrastructure.ai.noop_client import NoOpAIClient

                self._ai_client = NoOpAIClient()
            else:
                from ..infrastructure.ai.recommendation_client import AIRecommendationClient

                self._ai_client = AIRecommendationClient(self.settings.ai)
        return self._ai_client

    @property
    def shuffle_ai_client(self) -> AIClient:
        if self._shuffle_ai_client is None:
            if not self.ai_enabled:
                from ..infrastructure.ai.noop_client import NoOpAIClient

                self._shuffle_ai_client = NoOpAIClient()
            else:
                from ..infrastructure.ai.recommendation_client import AIRecommendationClient

                shuffle_settings = self.settings.ai.model_copy(
                    update={"model": self.settings.ai.shuffle_model}
                )
                self._shuffle_ai_client = AIRecommendationClient(shuffle_settings)
        return self._shuffle_ai_client

    @property
    def playback_service(self) -> PlaybackApplicationService:
        if self._playback_service is None:
            from ..application.services.playback_service import (
                PlaybackApplicationService,
            )

            self._playback_service = PlaybackApplicationService(
                session_repository=self.session_repository,
                history_repository=self.history_repository,
                voice_adapter=self.voice_adapter,
                audio_resolver=self.audio_resolver,
            )
        return self._playback_service

    @property
    def queue_service(self) -> QueueApplicationService:
        if self._queue_service is None:
            from ..application.services.queue_service import QueueApplicationService

            self._queue_service = QueueApplicationService(
                session_repository=self.session_repository,
            )
        return self._queue_service

    # === Command Handlers ===

    @property
    def vote_skip_handler(self) -> VoteSkipHandler:
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
        if self._voice_warmup_tracker is None:
            from ..infrastructure.discord.services.voice_warmup import (
                VoiceWarmupTracker,
            )

            self._voice_warmup_tracker = VoiceWarmupTracker(warmup_seconds=60)
        return self._voice_warmup_tracker

    @property
    def message_state_manager(self) -> MessageStateManager:
        if self._message_state_manager is None:
            from ..infrastructure.discord.services.message_state_manager import (
                MessageStateManager,
            )

            self._message_state_manager = MessageStateManager(self.bot)
        return self._message_state_manager

    # === Event Subscribers ===

    @property
    def auto_skip_on_requester_leave(self) -> AutoSkipOnRequesterLeave:
        if self._auto_skip_on_requester_leave is None:
            from ..application.services.requester_leave_autoskip import (
                AutoSkipOnRequesterLeave,
            )

            self._auto_skip_on_requester_leave = AutoSkipOnRequesterLeave(
                session_repository=self.session_repository,
                playback_service=self.playback_service,
                voice_adapter=self.voice_adapter,
            )
        return self._auto_skip_on_requester_leave

    @property
    def radio_service(self) -> RadioApplicationService:
        if self._radio_service is None:
            from ..application.services.radio_service import RadioApplicationService

            self._radio_service = RadioApplicationService(
                ai_client=self.ai_client,
                audio_resolver=self.audio_resolver,
                queue_service=self.queue_service,
                session_repository=self.session_repository,
                history_repository=self.history_repository,
                settings=self.settings.radio,
            )
        return self._radio_service

    @property
    def radio_auto_refill(self) -> RadioAutoRefill:
        if self._radio_auto_refill is None:
            from ..application.services.radio_auto_refill import RadioAutoRefill

            self._radio_auto_refill = RadioAutoRefill(
                radio_service=self.radio_service,
                playback_service=self.playback_service,
            )
        return self._radio_auto_refill


    @property
    def auto_dj(self) -> AutoDJ:
        if self._auto_dj is None:
            from ..application.services.auto_dj import AutoDJ

            self._auto_dj = AutoDJ(
                radio_service=self.radio_service,
                playback_service=self.playback_service,
                session_repository=self.session_repository,
                history_repository=self.history_repository,
                ai_client=self.ai_client,
            )
        return self._auto_dj

    # === Background Jobs ===

    @property
    def cleanup_job(self) -> CleanupJob:
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
        await self.database.initialize()
        self.auto_skip_on_requester_leave.start()
        if self.ai_enabled:
            self.radio_auto_refill.start()
            self.auto_dj.start()

    async def shutdown(self) -> None:
        for subscriber in (self._auto_skip_on_requester_leave, self._radio_auto_refill, self._auto_dj):
            if subscriber is not None:
                try:
                    subscriber.stop()
                except Exception:
                    pass

        if self._database is not None:
            await self._database.close()


def create_container(settings: Settings) -> Container:
    return Container(settings=settings)
