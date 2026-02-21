"""Pydantic-based settings loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, BaseModel, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

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
    RadioCount,
    RadioMaxTracks,
    TemperatureFloat,
    UnitInterval,
    VolumeFloat,
)


class DatabaseSettings(BaseModel):

    model_config = SettingsConfigDict(frozen=True, strict=True, populate_by_name=True)

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

    model_config = SettingsConfigDict(frozen=True, strict=True, populate_by_name=True)

    token: SecretStr = Field(
        default=SecretStr(""), validation_alias=AliasChoices("token", "bot_token", "discord_token")
    )
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

    @field_validator("owner_ids", "guild_ids", "test_guild_ids", mode="before")
    @classmethod
    def _coerce_list_to_tuple(cls, v: tuple[int, ...] | list[int]) -> tuple[int, ...]:
        if isinstance(v, list):
            return tuple(v)
        return v


class AudioSettings(BaseModel):

    model_config = SettingsConfigDict(frozen=True, strict=True, populate_by_name=True)

    default_volume: VolumeFloat = 0.5
    max_queue_size: MaxQueueSize = 50
    ffmpeg_options: dict[str, str] = Field(
        default_factory=lambda: {
            "before_options": (
                "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
                " -analyzeduration 0 -probesize 32768 -thread_queue_size 4096"
            ),
            "options": "-vn -bufsize 64k",
        }
    )
    ytdlp_format: NonEmptyStr = "bestaudio/best"
    pot_server_url: HttpUrlStr = Field(
        default="http://127.0.0.1:4416",
        validation_alias=AliasChoices("pot_server_url", "bgutil_pot_server_url"),
    )


class AISettings(BaseModel):

    model_config = SettingsConfigDict(frozen=True, strict=True, populate_by_name=True)

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


class VotingSettings(BaseModel):

    model_config = SettingsConfigDict(frozen=True, strict=True)

    skip_threshold_percentage: UnitInterval = 0.5
    min_voters: PositiveInt = 1
    auto_skip_listener_count: PositiveInt = 2


class RadioSettings(BaseModel):

    model_config = SettingsConfigDict(frozen=True, strict=True)

    default_count: RadioCount = 5
    max_tracks_per_session: RadioMaxTracks = 50


class CleanupSettings(BaseModel):

    model_config = SettingsConfigDict(frozen=True, strict=True)

    stale_session_hours: PositiveInt = 24
    cleanup_interval_minutes: PositiveInt = 30


class Settings(BaseSettings):

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        case_sensitive=False,
        extra="ignore",
        strict=True,
    )

    environment: Literal["development", "production", "test"] = "development"
    debug: bool = False
    log_level: str = "INFO"

    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    discord: DiscordSettings = Field(default_factory=DiscordSettings)
    audio: AudioSettings = Field(default_factory=AudioSettings)
    ai: AISettings = Field(default_factory=AISettings)
    voting: VotingSettings = Field(default_factory=VotingSettings)
    cleanup: CleanupSettings = Field(default_factory=CleanupSettings)
    radio: RadioSettings = Field(default_factory=RadioSettings)

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        v_upper = v.upper()
        if v_upper not in valid_levels:
            raise ValueError(f"Invalid log level: {v}. Must be one of {valid_levels}")
        return v_upper

    @classmethod
    def from_env(cls) -> Settings:
        return cls()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def clear_settings_cache() -> None:
    get_settings.cache_clear()
