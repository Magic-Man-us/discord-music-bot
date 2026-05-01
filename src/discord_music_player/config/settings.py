"""Pydantic-based settings loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache
from typing import ClassVar

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    computed_field,
    field_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

from ..domain.shared.enums import EnvironmentType, LogLevel, YtDlpPlayerClient
from ..domain.shared.types import (
    BusyTimeoutMs,
    CommandPrefixStr,
    ConnectionTimeoutS,
    DiscordSnowflake,
    HttpUrlStr,
    MaxQueueSize,
    MaxTokens,
    NonEmptyStr,
    NonNegativeInt,
    PoolSize,
    PositiveInt,
    RadioBatchSize,
    RadioCount,
    RadioMaxTracks,
    TemperatureFloat,
    UnitInterval,
    VolumeFloat,
)


class DatabaseSettings(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, populate_by_name=True)

    url: str = Field(
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
    model_config = ConfigDict(frozen=True, strict=True, populate_by_name=True)

    token: SecretStr = Field(
        default=SecretStr(""), validation_alias=AliasChoices("token", "bot_token", "discord_token")
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
    owner_ids: tuple[DiscordSnowflake, ...] = Field(
        default_factory=tuple, validation_alias=AliasChoices("owner_ids", "owners")
    )
    guild_ids: tuple[DiscordSnowflake, ...] = Field(
        default_factory=tuple, validation_alias=AliasChoices("guild_ids", "guilds")
    )
    test_guild_ids: tuple[DiscordSnowflake, ...] = Field(
        default_factory=tuple, validation_alias=AliasChoices("test_guild_ids", "test_guilds")
    )
    sync_on_startup: bool = True
    dj_role_id: DiscordSnowflake | None = Field(
        default=None,
        validation_alias=AliasChoices("dj_role_id", "dj_role"),
        description="Optional role ID that gates destructive commands (skip, stop, clear, etc.)",
    )

    @field_validator("owner_ids", "guild_ids", "test_guild_ids", mode="before")
    @classmethod
    def _coerce_to_tuple(cls, v: tuple[int, ...] | list[int] | str) -> tuple[int, ...]:
        if isinstance(v, str):
            import json

            try:
                parsed = json.loads(v)
            except json.JSONDecodeError:
                parsed = [int(s.strip()) for s in v.split(",") if s.strip()]
            if isinstance(parsed, list):
                return tuple(parsed)
            return (parsed,)
        if isinstance(v, list):
            return tuple(v)
        return v


class AudioSettings(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, populate_by_name=True)

    default_volume: VolumeFloat = 0.5
    max_queue_size: MaxQueueSize = 50
    ffmpeg_options: dict[str, str] = Field(
        default_factory=lambda: {
            "before_options": (
                "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 3"
                " -analyzeduration 0 -probesize 32768 -thread_queue_size 8192"
            ),
            "options": "-vn -bufsize 256k",
        }
    )
    ytdlp_format: NonEmptyStr = "bestaudio/best"
    # android last is the no-JS-runtime fallback (legacy fmt 18, no PO token).
    player_client: list[YtDlpPlayerClient] = Field(
        default_factory=lambda: [
            YtDlpPlayerClient.WEB,
            YtDlpPlayerClient.MWEB,
            YtDlpPlayerClient.ANDROID,
        ],
    )
    pot_server_url: HttpUrlStr = Field(
        default="http://127.0.0.1:4416",
        validation_alias=AliasChoices("pot_server_url", "bgutil_pot_server_url"),
    )
    normalize_audio: bool = Field(
        default=False,
        description="Apply EBU R128 loudnorm filter to normalize audio volume across tracks.",
    )


class AISettings(BaseModel):
    """AI configuration. Features auto-disable when the provider API key is missing."""

    model_config = ConfigDict(frozen=True, strict=True, populate_by_name=True)

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
                "(e.g. 'openai:gpt-5-mini', 'anthropic:claude-sonnet-4-5-20250929', 'google-gla:gemini-2.0-flash')"
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
    model_config = ConfigDict(frozen=True, strict=True)

    skip_threshold_percentage: UnitInterval = 0.5
    min_voters: PositiveInt = 1
    auto_skip_listener_count: PositiveInt = 2


class RadioSettings(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True)

    batch_size: RadioBatchSize = 10
    visible_count: RadioCount = 3
    max_tracks_per_session: RadioMaxTracks = 50


class CleanupSettings(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True)

    stale_session_hours: PositiveInt = 24
    cleanup_interval_minutes: PositiveInt = 30
    history_retention_days: PositiveInt = 30


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

    @field_validator("log_level", mode="before")
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


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def clear_settings_cache() -> None:
    get_settings.cache_clear()
