"""Application Settings and Configuration

Pydantic-based settings management using environment variables.
Settings are loaded from environment variables with support for .env files,
type validation, and sensible defaults. All settings are frozen and immutable
after initialization.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, BaseModel, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from ..domain.shared.validators import validate_discord_snowflake


class DatabaseSettings(BaseModel):
    """Database configuration."""

    model_config = SettingsConfigDict(frozen=True, strict=True, populate_by_name=True)

    url: str = Field(
        default="sqlite:///data/bot.db",
        validation_alias=AliasChoices("url", "database_url", "db_url"),
    )
    pool_size: int = Field(default=5, ge=1, le=100)  # Reserved for future use
    echo: bool = False
    busy_timeout_ms: int = Field(
        default=5000,
        ge=1000,
        le=30000,
        validation_alias=AliasChoices("busy_timeout_ms", "busy_timeout"),
    )
    connection_timeout_s: int = Field(
        default=10,
        ge=1,
        le=60,
        validation_alias=AliasChoices("connection_timeout_s", "connection_timeout"),
    )

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        """Validate database URL format."""
        if not v.startswith(("sqlite://", "postgresql://", "mysql://")):
            raise ValueError("Database URL must start with sqlite://, postgresql://, or mysql://")
        return v


class DiscordSettings(BaseModel):
    """Discord bot configuration."""

    model_config = SettingsConfigDict(frozen=True, strict=True, populate_by_name=True)

    token: SecretStr = Field(
        default=SecretStr(""), validation_alias=AliasChoices("token", "bot_token", "discord_token")
    )
    command_prefix: str = Field(
        default="!",
        min_length=1,
        max_length=5,
        validation_alias=AliasChoices("command_prefix", "prefix"),
    )
    owner_ids: tuple[int, ...] = Field(
        default_factory=tuple, validation_alias=AliasChoices("owner_ids", "owners")
    )
    guild_ids: tuple[int, ...] = Field(
        default_factory=tuple, validation_alias=AliasChoices("guild_ids", "guilds")
    )
    test_guild_ids: tuple[int, ...] = Field(
        default_factory=tuple, validation_alias=AliasChoices("test_guild_ids", "test_guilds")
    )
    sync_on_startup: bool = False

    @field_validator("owner_ids", "guild_ids", "test_guild_ids", mode="before")
    @classmethod
    def validate_snowflake_ids(cls, v: tuple[int, ...] | list[int]) -> tuple[int, ...]:
        """Validate Discord snowflake IDs and convert lists to tuples."""
        # Convert list to tuple if needed (from JSON array in env vars)
        if isinstance(v, list):
            v = tuple(v)
        for snowflake in v:
            validate_discord_snowflake(snowflake)
        return v


class AudioSettings(BaseModel):
    """Audio playback configuration."""

    model_config = SettingsConfigDict(frozen=True, strict=True, populate_by_name=True)

    default_volume: float = Field(default=0.5, ge=0.0, le=2.0)
    max_queue_size: int = Field(default=50, ge=1, le=1000)
    ffmpeg_options: dict[str, str] = Field(
        default_factory=lambda: {
            "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
            "options": "-vn",
        }
    )
    ytdlp_format: str = "bestaudio/best"
    pot_server_url: str = Field(
        default="http://127.0.0.1:4416",
        validation_alias=AliasChoices("pot_server_url", "bgutil_pot_server_url"),
    )


class AISettings(BaseModel):
    """AI/OpenAI configuration."""

    model_config = SettingsConfigDict(frozen=True, strict=True, populate_by_name=True)

    api_key: SecretStr = Field(
        default=SecretStr(""),
        validation_alias=AliasChoices("api_key", "openai_api_key", "openai_key"),
    )
    model: str = Field(
        default="gpt-4o-mini", validation_alias=AliasChoices("model", "ai_model", "openai_model")
    )
    max_tokens: int = Field(default=500, ge=1, le=4096)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    cache_ttl_seconds: int = Field(
        default=3600, ge=0, validation_alias=AliasChoices("cache_ttl_seconds", "cache_ttl")
    )


class VotingSettings(BaseModel):
    """Voting configuration."""

    model_config = SettingsConfigDict(frozen=True, strict=True)

    skip_threshold_percentage: float = Field(default=0.5, ge=0.0, le=1.0)
    min_voters: int = Field(default=1, ge=1)
    auto_skip_listener_count: int = Field(default=2, ge=1)


class RadioSettings(BaseModel):
    """Radio feature configuration."""

    model_config = SettingsConfigDict(frozen=True, strict=True)

    default_count: int = Field(default=5, ge=1, le=10)
    max_tracks_per_session: int = Field(default=50, ge=1, le=200)


class CleanupSettings(BaseModel):
    """Session cleanup configuration."""

    model_config = SettingsConfigDict(frozen=True, strict=True)

    stale_session_hours: int = Field(default=24, ge=1)
    cleanup_interval_minutes: int = Field(default=30, ge=1)


class Settings(BaseSettings):
    """Application settings container.

    Automatically loads configuration from environment variables.

    Environment variable naming:
    - ENVIRONMENT, DEBUG, LOG_LEVEL (top-level)
    - DISCORD_TOKEN, DISCORD_COMMAND_PREFIX, etc. (nested with prefix)
    - OWNER_IDS, GUILD_IDS (comma-separated integers)
    - DATABASE_PATH (converted to sqlite:/// URL)
    - OPENAI_API_KEY, AI_MODEL, etc. (nested with prefix)
    """

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
        """Validate log level."""
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        v_upper = v.upper()
        if v_upper not in valid_levels:
            raise ValueError(f"Invalid log level: {v}. Must be one of {valid_levels}")
        return v_upper

    @classmethod
    def from_env(cls) -> Settings:
        """Create settings from environment variables.

        This method is provided for backward compatibility.
        Pydantic BaseSettings automatically loads from environment.
        """
        return cls()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Get cached application settings.

    Settings are automatically loaded from:
    1. .env file (if present)
    2. Environment variables
    3. Default values
    """
    return Settings()


def clear_settings_cache() -> None:
    """Clear the settings cache (useful for testing)."""
    get_settings.cache_clear()
