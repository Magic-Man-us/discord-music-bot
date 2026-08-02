"""Pydantic-based settings loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache
from typing import ClassVar, Final

from pydantic import (
    AliasChoices,
    BaseModel,
    Field,
    SecretStr,
    TypeAdapter,
    ValidationError,
    computed_field,
    field_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

from ..domain.shared.constants import AudioConstants, HealthConstants
from ..domain.shared.enums import EnvironmentType, LogLevel, YtDlpPlayerClient
from ..domain.shared.model_config import FrozenStrictModelConfig, SettingsSubModelConfig
from ..domain.shared.types import (
    BusyTimeoutMs,
    CommandPrefixStr,
    ConnectionTimeoutS,
    DatabaseUrlStr,
    DiscordSnowflake,
    DiscordSnowflakeTuple,
    FfmpegOptions,
    FrameCount,
    HttpUrlStr,
    MaxQueueSize,
    MaxTokens,
    NonEmptyStr,
    NonNegativeInt,
    PlayerClientList,
    PoolSize,
    PositiveInt,
    PrebufferSeconds,
    PrefillSeconds,
    PrefillTimeoutSeconds,
    RadioBatchSize,
    RadioCount,
    RadioMaxTracks,
    TemperatureFloat,
    UnitInterval,
    VolumeFloat,
)

_VALIDATOR_MODE_BEFORE: Final[str] = "before"
_TRUTHY_ENV_VALUES: Final[frozenset[str]] = frozenset("1 true t yes y on".split())
_FALSY_ENV_VALUES: Final[frozenset[str]] = frozenset("0 false f no n off release".split())
_SNOWFLAKE_TUPLE_ADAPTER: Final = TypeAdapter(tuple[int, ...])


class DatabaseSettings(BaseModel):
    model_config = SettingsSubModelConfig

    url: DatabaseUrlStr = Field(
        default="sqlite:///data/bot.db",
        validation_alias=AliasChoices("url", "database_url", "db_url"),
    )
    pool_size: PoolSize = 5
    echo: bool = False
    busy_timeout_ms: BusyTimeoutMs = Field(
        default=5000,
        validation_alias=AliasChoices("busy_timeout_ms", "busy_timeout"),
    )
    connection_timeout_s: ConnectionTimeoutS = Field(
        default=10,
        validation_alias=AliasChoices("connection_timeout_s", "connection_timeout"),
    )

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        if not v.startswith(("sqlite://", "postgresql://", "mysql://")):
            raise ValueError("Database URL must start with sqlite://, postgresql://, or mysql://")
        return v


class DiscordSettings(BaseModel):
    model_config = SettingsSubModelConfig

    token: SecretStr = Field(
        default=SecretStr(""),
        validation_alias=AliasChoices("token", "bot_token", "discord_token"),
    )

    @field_validator("token")
    @classmethod
    def _token_not_empty(cls, v: SecretStr) -> SecretStr:
        if not v.get_secret_value().strip():
            raise ValueError("Discord token must not be empty — set DISCORD_TOKEN")
        return v

    command_prefix: CommandPrefixStr = Field(
        default="!",
        validation_alias=AliasChoices("command_prefix", "prefix"),
    )
    owner_ids: DiscordSnowflakeTuple = Field(
        default_factory=tuple, validation_alias=AliasChoices("owner_ids", "owners")
    )
    guild_ids: DiscordSnowflakeTuple = Field(
        default_factory=tuple, validation_alias=AliasChoices("guild_ids", "guilds")
    )
    test_guild_ids: DiscordSnowflakeTuple = Field(
        default_factory=tuple,
        validation_alias=AliasChoices("test_guild_ids", "test_guilds"),
    )
    sync_on_startup: bool = True
    dj_role_id: DiscordSnowflake | None = Field(
        default=None,
        validation_alias=AliasChoices("dj_role_id", "dj_role"),
        description="Optional role ID that gates destructive commands (skip, stop, clear, etc.)",
    )

    @field_validator("owner_ids", "guild_ids", "test_guild_ids", mode=_VALIDATOR_MODE_BEFORE)
    @classmethod
    def _coerce_to_tuple(cls, v: tuple[int, ...] | list[int] | str) -> tuple[int, ...]:
        if isinstance(v, str):
            try:
                return _SNOWFLAKE_TUPLE_ADAPTER.validate_json(v)
            except ValidationError:
                return tuple(int(s.strip()) for s in v.split(",") if s.strip())
        if isinstance(v, list):
            return tuple(v)
        return v


class PrebufferSettings(BaseModel):
    """Decoupling buffer between FFmpeg's pipe and discord.py's 20 ms send loop.

    Without it the only slack is the 64 KB OS pipe plus an 8 KB BufferedReader — about
    384 ms of PCM — and any upstream stall longer than that is an audible gap.
    """

    model_config = SettingsSubModelConfig

    enabled: bool = True
    buffer_seconds: PrebufferSeconds = 5.0
    prefill_seconds: PrefillSeconds = 2.0

    @staticmethod
    def _to_frames(seconds: float) -> FrameCount:
        frames_per_second = AudioConstants.PCM_BYTES_PER_SECOND / AudioConstants.PCM_FRAME_BYTES
        return max(1, round(seconds * frames_per_second))

    @computed_field
    @property
    def buffer_frames(self) -> FrameCount:
        return self._to_frames(self.buffer_seconds)

    @computed_field
    @property
    def prefill_frames(self) -> FrameCount:
        return self._to_frames(self.prefill_seconds)

    @computed_field
    @property
    def prefill_timeout(self) -> PrefillTimeoutSeconds:
        """Upper bound on the first read()'s wait, so a dead stream can't hang playback."""
        return self.prefill_seconds + AudioConstants.PREFILL_GRACE_SECONDS


class AudioSettings(BaseModel):
    model_config = SettingsSubModelConfig

    default_volume: VolumeFloat = 0.5
    max_queue_size: MaxQueueSize = 50
    prebuffer: PrebufferSettings = Field(default_factory=PrebufferSettings)
    ffmpeg_options: FfmpegOptions = Field(
        default_factory=lambda: {
            # A reconnect stalls the pipe for its full delay, so keep the ceiling tight.
            "before_options": (
                "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 1"
                " -analyzeduration 0 -probesize 32768 -thread_queue_size 8192"
            ),
            # -bufsize is encoder rate control; this output is raw PCM with no encoder.
            "options": "-vn",
        }
    )
    ytdlp_format: NonEmptyStr = "bestaudio/best"
    # tv_simply serves Opus 251 on URLs that authorize here; web/mweb 251 URLs 403. android (itag 18) is the fallback.
    player_client: PlayerClientList = Field(
        default_factory=lambda: [
            YtDlpPlayerClient.TV_SIMPLY,
            YtDlpPlayerClient.ANDROID,
        ],
    )
    pot_server_url: HttpUrlStr = Field(
        default="http://127.0.0.1:4416",
        validation_alias=AliasChoices("pot_server_url", "bgutil_pot_server_url"),
    )
    js_runtime_path: NonEmptyStr | None = Field(
        default=None,
        validation_alias=AliasChoices("js_runtime_path", "node_path"),
        description="Path to the Node/Deno binary yt-dlp uses to solve YouTube's nsig challenge.",
    )
    normalize_audio: bool = Field(
        default=True,
        description="Apply the dynaudnorm filter to even out volume across tracks.",
    )


class AISettings(BaseModel):
    """AI configuration. Features auto-disable when the provider API key is missing."""

    model_config = SettingsSubModelConfig

    # Provider prefix → environment variable holding the API key.
    _PROVIDER_API_KEY_ENV: ClassVar[dict[str, str]] = {
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "google-gla": "GOOGLE_API_KEY",
        "google-vertex": "GOOGLE_API_KEY",
    }

    model: NonEmptyStr = Field(
        default="openai:gpt-5-mini", validation_alias=AliasChoices("model", "ai_model")
    )
    max_tokens: MaxTokens = 500
    temperature: TemperatureFloat = 0.7
    cache_ttl_seconds: NonNegativeInt = Field(
        default=3600, validation_alias=AliasChoices("cache_ttl_seconds", "cache_ttl")
    )
    shuffle_model: NonEmptyStr = Field(
        default="anthropic:claude-haiku-4-5-20251001",
        validation_alias=AliasChoices("shuffle_model", "ai_shuffle_model"),
    )

    @field_validator("model", "shuffle_model")
    @classmethod
    def validate_model_format(cls, v: str) -> str:
        if ":" not in v:
            msg = (
                "AI model must be in 'provider:model' format "
                "(e.g. 'openai:gpt-5-mini', "
                "'anthropic:claude-sonnet-4-5-20250929', "
                "'google-gla:gemini-2.0-flash')"
            )
            raise ValueError(msg)
        return v

    @computed_field  # type: ignore[prop-decorator]
    @property
    def enabled(self) -> bool:
        """True only when the primary model's provider has a non-empty API key."""
        return self._has_api_key(self.model)

    def _has_api_key(self, model_str: str) -> bool:
        import os

        provider = model_str.split(":", 1)[0]
        env_var = self._PROVIDER_API_KEY_ENV.get(provider)
        if env_var is None:
            return False
        return bool(os.environ.get(env_var, "").strip())


class VotingSettings(BaseModel):
    model_config = FrozenStrictModelConfig

    skip_threshold_percentage: UnitInterval = 0.5
    min_voters: PositiveInt = 1
    auto_skip_listener_count: PositiveInt = 2


class RadioSettings(BaseModel):
    model_config = FrozenStrictModelConfig

    batch_size: RadioBatchSize = 10
    visible_count: RadioCount = 3
    max_tracks_per_session: RadioMaxTracks = 50


class CleanupSettings(BaseModel):
    model_config = FrozenStrictModelConfig

    stale_session_hours: PositiveInt = 24
    cleanup_interval_minutes: PositiveInt = 30
    history_retention_days: PositiveInt = 30


class HealthSettings(BaseModel):
    model_config = SettingsSubModelConfig

    fast_interval: PositiveInt = HealthConstants.DEFAULT_FAST_INTERVAL
    detailed_interval: PositiveInt = HealthConstants.DEFAULT_DETAILED_INTERVAL
    alert_channel_id: DiscordSnowflake | None = Field(
        default=None,
        validation_alias=AliasChoices("alert_channel_id", "alert_channel"),
    )


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_nested_delimiter="__",
        extra="ignore",
        strict=True,
    )

    environment: EnvironmentType = EnvironmentType.DEVELOPMENT
    debug: bool = False
    log_level: LogLevel = LogLevel.INFO

    database: DatabaseSettings = Field(default_factory=DatabaseSettings)

    @field_validator("debug", mode=_VALIDATOR_MODE_BEFORE)
    @classmethod
    def _normalize_debug(cls, v: bool | str) -> bool | str:
        """Coerce common boolean env strings and tolerate shell ``DEBUG=release``."""
        if isinstance(v, str):
            normalized = v.strip().casefold()
            if normalized in _TRUTHY_ENV_VALUES:
                return True
            if not normalized or normalized in _FALSY_ENV_VALUES:
                return False
        return v

    @field_validator("log_level", mode=_VALIDATOR_MODE_BEFORE)
    @classmethod
    def _normalize_log_level(cls, v: str | LogLevel) -> LogLevel:
        if isinstance(v, str) and not isinstance(v, LogLevel):
            return LogLevel(v.upper())
        return v

    discord: DiscordSettings = Field(default_factory=DiscordSettings)
    audio: AudioSettings = Field(default_factory=AudioSettings)
    ai: AISettings = Field(default_factory=AISettings)
    voting: VotingSettings = Field(default_factory=VotingSettings)
    cleanup: CleanupSettings = Field(default_factory=CleanupSettings)
    radio: RadioSettings = Field(default_factory=RadioSettings)
    health: HealthSettings = Field(default_factory=HealthSettings)
    log_dir: NonEmptyStr = "logs"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def clear_settings_cache() -> None:
    get_settings.cache_clear()
