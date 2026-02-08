"""
Unit Tests for Application Settings Configuration

Tests for:
- Loading settings from environment variables
- Required field validation
- Default values for optional fields
- Type coercion (strings to ints, bools, floats)
- Nested settings objects (DatabaseSettings, AudioSettings, AISettings, CleanupSettings)
- Invalid values (wrong types, out of range values)
- Custom validators (database URL, log level, snowflake IDs)
- Settings caching and clearing
"""

import pytest
from pydantic import SecretStr, ValidationError

from discord_music_player.config.settings import (
    AISettings,
    AudioSettings,
    CleanupSettings,
    DatabaseSettings,
    DiscordSettings,
    Settings,
    VotingSettings,
    clear_settings_cache,
    get_settings,
)

# =============================================================================
# DatabaseSettings Tests
# =============================================================================


class TestDatabaseSettings:
    """Unit tests for DatabaseSettings configuration."""

    def test_create_with_defaults(self):
        """Should create DatabaseSettings with default values."""
        db = DatabaseSettings()

        assert db.url == "sqlite:///data/bot.db"
        assert db.pool_size == 5
        assert db.echo is False
        assert db.busy_timeout_ms == 5000
        assert db.connection_timeout_s == 10

    def test_create_with_custom_sqlite_url(self):
        """Should accept custom SQLite URL."""
        db = DatabaseSettings(url="sqlite:///custom/path.db")

        assert db.url == "sqlite:///custom/path.db"

    def test_create_with_postgresql_url(self):
        """Should accept PostgreSQL URL."""
        db = DatabaseSettings(url="postgresql://user:pass@localhost/db")

        assert db.url == "postgresql://user:pass@localhost/db"

    def test_create_with_mysql_url(self):
        """Should accept MySQL URL."""
        db = DatabaseSettings(url="mysql://user:pass@localhost/db")

        assert db.url == "mysql://user:pass@localhost/db"

    def test_invalid_url_scheme_raises_error(self):
        """Should raise ValidationError for invalid database URL scheme."""
        with pytest.raises(ValidationError, match="Database URL must start with"):
            DatabaseSettings(url="invalid://localhost/db")

    def test_pool_size_validation_minimum(self):
        """Should raise ValidationError for pool_size below minimum."""
        with pytest.raises(ValidationError, match="greater than or equal to 1"):
            DatabaseSettings(pool_size=0)

    def test_pool_size_validation_maximum(self):
        """Should raise ValidationError for pool_size above maximum."""
        with pytest.raises(ValidationError, match="less than or equal to 100"):
            DatabaseSettings(pool_size=101)

    def test_busy_timeout_validation_minimum(self):
        """Should raise ValidationError for busy_timeout_ms below minimum."""
        with pytest.raises(ValidationError, match="greater than or equal to 1000"):
            DatabaseSettings(busy_timeout_ms=999)

    def test_busy_timeout_validation_maximum(self):
        """Should raise ValidationError for busy_timeout_ms above maximum."""
        with pytest.raises(ValidationError, match="less than or equal to 30000"):
            DatabaseSettings(busy_timeout_ms=30001)

    def test_connection_timeout_validation_minimum(self):
        """Should raise ValidationError for connection_timeout_s below minimum."""
        with pytest.raises(ValidationError, match="greater than or equal to 1"):
            DatabaseSettings(connection_timeout_s=0)

    def test_connection_timeout_validation_maximum(self):
        """Should raise ValidationError for connection_timeout_s above maximum."""
        with pytest.raises(ValidationError, match="less than or equal to 60"):
            DatabaseSettings(connection_timeout_s=61)

    def test_url_alias_database_url(self):
        """Should accept 'database_url' alias for url field."""
        db = DatabaseSettings(database_url="sqlite:///aliased.db")

        assert db.url == "sqlite:///aliased.db"

    def test_url_alias_db_url(self):
        """Should accept 'db_url' alias for url field."""
        db = DatabaseSettings(db_url="sqlite:///aliased2.db")

        assert db.url == "sqlite:///aliased2.db"

    def test_immutability(self):
        """Should be immutable (frozen)."""
        db = DatabaseSettings()

        with pytest.raises(ValidationError):
            db.url = "sqlite:///new.db"


# =============================================================================
# DiscordSettings Tests
# =============================================================================


class TestDiscordSettings:
    """Unit tests for DiscordSettings configuration."""

    def test_create_with_defaults(self):
        """Should create DiscordSettings with default values."""
        discord = DiscordSettings()

        assert discord.token.get_secret_value() == ""
        assert discord.command_prefix == "!"
        assert discord.owner_ids == ()
        assert discord.guild_ids == ()
        assert discord.test_guild_ids == ()
        assert discord.sync_on_startup is False

    def test_create_with_custom_token(self):
        """Should accept custom bot token."""
        discord = DiscordSettings(token=SecretStr("my-secret-token"))

        assert discord.token.get_secret_value() == "my-secret-token"

    def test_create_with_custom_prefix(self):
        """Should accept custom command prefix."""
        discord = DiscordSettings(command_prefix="?")

        assert discord.command_prefix == "?"

    def test_prefix_minimum_length(self):
        """Should raise ValidationError for empty prefix."""
        with pytest.raises(ValidationError, match="at least 1 character"):
            DiscordSettings(command_prefix="")

    def test_prefix_maximum_length(self):
        """Should raise ValidationError for prefix too long."""
        with pytest.raises(ValidationError, match="at most 5 characters"):
            DiscordSettings(command_prefix="!@#$%^")

    def test_valid_owner_ids(self):
        """Should accept valid Discord snowflake IDs for owners."""
        discord = DiscordSettings(owner_ids=(123456789012345678, 987654321098765432))

        assert len(discord.owner_ids) == 2
        assert 123456789012345678 in discord.owner_ids

    def test_invalid_owner_id_negative(self):
        """Should raise ValidationError for negative owner ID."""
        with pytest.raises(ValidationError, match="snowflake ID must be positive"):
            DiscordSettings(owner_ids=(-1,))

    def test_invalid_owner_id_zero(self):
        """Should raise ValidationError for zero owner ID."""
        with pytest.raises(ValidationError, match="snowflake ID must be positive"):
            DiscordSettings(owner_ids=(0,))

    def test_invalid_owner_id_too_large(self):
        """Should raise ValidationError for owner ID exceeding 64-bit limit."""
        with pytest.raises(ValidationError, match="exceeds maximum value"):
            DiscordSettings(owner_ids=(2**64,))

    def test_valid_guild_ids(self):
        """Should accept valid Discord snowflake IDs for guilds."""
        discord = DiscordSettings(guild_ids=(111111111111111111, 222222222222222222))

        assert len(discord.guild_ids) == 2

    def test_token_alias_bot_token(self):
        """Should accept 'bot_token' alias for token field."""
        discord = DiscordSettings(bot_token=SecretStr("aliased-token"))

        assert discord.token.get_secret_value() == "aliased-token"

    def test_token_alias_discord_token(self):
        """Should accept 'discord_token' alias for token field."""
        discord = DiscordSettings(discord_token=SecretStr("discord-token"))

        assert discord.token.get_secret_value() == "discord-token"

    def test_prefix_alias(self):
        """Should accept 'prefix' alias for command_prefix field."""
        discord = DiscordSettings(prefix="$")

        assert discord.command_prefix == "$"


# =============================================================================
# AudioSettings Tests
# =============================================================================


class TestAudioSettings:
    """Unit tests for AudioSettings configuration."""

    def test_create_with_defaults(self):
        """Should create AudioSettings with default values."""
        audio = AudioSettings()

        assert audio.default_volume == 0.5
        assert audio.max_queue_size == 50
        assert audio.ytdlp_format == "bestaudio/best"
        assert "before_options" in audio.ffmpeg_options
        assert "options" in audio.ffmpeg_options

    def test_create_with_custom_volume(self):
        """Should accept custom default volume."""
        audio = AudioSettings(default_volume=0.8)

        assert audio.default_volume == 0.8

    def test_volume_validation_minimum(self):
        """Should raise ValidationError for volume below 0.0."""
        with pytest.raises(ValidationError, match="greater than or equal to 0"):
            AudioSettings(default_volume=-0.1)

    def test_volume_validation_maximum(self):
        """Should raise ValidationError for volume above 2.0."""
        with pytest.raises(ValidationError, match="less than or equal to 2"):
            AudioSettings(default_volume=2.1)

    def test_queue_size_validation_minimum(self):
        """Should raise ValidationError for queue size below minimum."""
        with pytest.raises(ValidationError, match="greater than or equal to 1"):
            AudioSettings(max_queue_size=0)

    def test_queue_size_validation_maximum(self):
        """Should raise ValidationError for queue size above maximum."""
        with pytest.raises(ValidationError, match="less than or equal to 1000"):
            AudioSettings(max_queue_size=1001)

    def test_custom_ffmpeg_options(self):
        """Should accept custom FFmpeg options."""
        custom_opts = {"before_options": "-custom", "options": "-vn -ar 48000"}
        audio = AudioSettings(ffmpeg_options=custom_opts)

        assert audio.ffmpeg_options == custom_opts

    def test_custom_ytdlp_format(self):
        """Should accept custom yt-dlp format string."""
        audio = AudioSettings(ytdlp_format="bestaudio[ext=m4a]")

        assert audio.ytdlp_format == "bestaudio[ext=m4a]"


# =============================================================================
# AISettings Tests
# =============================================================================


class TestAISettings:
    """Unit tests for AISettings configuration."""

    def test_create_with_defaults(self):
        """Should create AISettings with default values."""
        ai = AISettings()

        assert ai.api_key.get_secret_value() == ""
        assert ai.model == "gpt-4o-mini"
        assert ai.max_tokens == 500
        assert ai.temperature == 0.7
        assert ai.cache_ttl_seconds == 3600

    def test_create_with_custom_api_key(self):
        """Should accept custom API key."""
        ai = AISettings(api_key=SecretStr("sk-test-key"))

        assert ai.api_key.get_secret_value() == "sk-test-key"

    def test_create_with_custom_model(self):
        """Should accept custom model name."""
        ai = AISettings(model="gpt-4o")

        assert ai.model == "gpt-4o"

    def test_max_tokens_validation_minimum(self):
        """Should raise ValidationError for max_tokens below minimum."""
        with pytest.raises(ValidationError, match="greater than or equal to 1"):
            AISettings(max_tokens=0)

    def test_max_tokens_validation_maximum(self):
        """Should raise ValidationError for max_tokens above maximum."""
        with pytest.raises(ValidationError, match="less than or equal to 4096"):
            AISettings(max_tokens=4097)

    def test_temperature_validation_minimum(self):
        """Should raise ValidationError for temperature below 0.0."""
        with pytest.raises(ValidationError, match="greater than or equal to 0"):
            AISettings(temperature=-0.1)

    def test_temperature_validation_maximum(self):
        """Should raise ValidationError for temperature above 2.0."""
        with pytest.raises(ValidationError, match="less than or equal to 2"):
            AISettings(temperature=2.1)

    def test_cache_ttl_validation_minimum(self):
        """Should accept cache_ttl_seconds of 0 (no caching)."""
        ai = AISettings(cache_ttl_seconds=0)

        assert ai.cache_ttl_seconds == 0

    def test_api_key_alias_openai_api_key(self):
        """Should accept 'openai_api_key' alias for api_key field."""
        ai = AISettings(openai_api_key=SecretStr("sk-openai-key"))

        assert ai.api_key.get_secret_value() == "sk-openai-key"

    def test_model_alias_ai_model(self):
        """Should accept 'ai_model' alias for model field."""
        ai = AISettings(ai_model="gpt-3.5-turbo")

        assert ai.model == "gpt-3.5-turbo"


# =============================================================================
# VotingSettings Tests
# =============================================================================


class TestVotingSettings:
    """Unit tests for VotingSettings configuration."""

    def test_create_with_defaults(self):
        """Should create VotingSettings with default values."""
        voting = VotingSettings()

        assert voting.skip_threshold_percentage == 0.5
        assert voting.min_voters == 1
        assert voting.auto_skip_listener_count == 2

    def test_threshold_validation_minimum(self):
        """Should raise ValidationError for threshold below 0.0."""
        with pytest.raises(ValidationError, match="greater than or equal to 0"):
            VotingSettings(skip_threshold_percentage=-0.1)

    def test_threshold_validation_maximum(self):
        """Should raise ValidationError for threshold above 1.0."""
        with pytest.raises(ValidationError, match="less than or equal to 1"):
            VotingSettings(skip_threshold_percentage=1.1)

    def test_min_voters_validation(self):
        """Should raise ValidationError for min_voters below 1."""
        with pytest.raises(ValidationError, match="greater than or equal to 1"):
            VotingSettings(min_voters=0)


# =============================================================================
# CleanupSettings Tests
# =============================================================================


class TestCleanupSettings:
    """Unit tests for CleanupSettings configuration."""

    def test_create_with_defaults(self):
        """Should create CleanupSettings with default values."""
        cleanup = CleanupSettings()

        assert cleanup.stale_session_hours == 24
        assert cleanup.cleanup_interval_minutes == 30

    def test_stale_session_hours_validation(self):
        """Should raise ValidationError for stale_session_hours below 1."""
        with pytest.raises(ValidationError, match="greater than or equal to 1"):
            CleanupSettings(stale_session_hours=0)

    def test_cleanup_interval_validation(self):
        """Should raise ValidationError for cleanup_interval_minutes below 1."""
        with pytest.raises(ValidationError, match="greater than or equal to 1"):
            CleanupSettings(cleanup_interval_minutes=0)

    def test_custom_retention_periods(self):
        """Should accept custom retention periods."""
        cleanup = CleanupSettings(stale_session_hours=48, cleanup_interval_minutes=60)

        assert cleanup.stale_session_hours == 48
        assert cleanup.cleanup_interval_minutes == 60


# =============================================================================
# Settings (Main Container) Tests
# =============================================================================


class TestSettings:
    """Unit tests for main Settings configuration container."""

    def test_create_with_all_defaults(self, monkeypatch):
        """Should create Settings with all default values."""
        # Clear any environment variables that might interfere
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        monkeypatch.delenv("DEBUG", raising=False)
        monkeypatch.delenv("LOG_LEVEL", raising=False)

        # Create settings with _env_file=None to skip .env file loading
        settings = Settings(_env_file=None)

        assert settings.environment == "development"
        assert settings.debug is False
        assert settings.log_level == "INFO"
        assert isinstance(settings.database, DatabaseSettings)
        assert isinstance(settings.discord, DiscordSettings)
        assert isinstance(settings.audio, AudioSettings)
        assert isinstance(settings.ai, AISettings)
        assert isinstance(settings.voting, VotingSettings)
        assert isinstance(settings.cleanup, CleanupSettings)

    def test_load_from_environment_variables(self, monkeypatch):
        """Should load top-level settings from environment variables."""
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("DEBUG", "true")
        monkeypatch.setenv("LOG_LEVEL", "WARNING")

        settings = Settings()

        assert settings.environment == "production"
        assert settings.debug is True
        assert settings.log_level == "WARNING"

    def test_load_nested_settings_from_env(self, monkeypatch):
        """Should load nested settings using env_nested_delimiter."""
        monkeypatch.setenv("DATABASE__URL", "postgresql://localhost/testdb")
        monkeypatch.setenv("DATABASE__POOL_SIZE", "10")
        monkeypatch.setenv("DISCORD__COMMAND_PREFIX", "?")
        monkeypatch.setenv("AUDIO__DEFAULT_VOLUME", "0.8")

        settings = Settings()

        assert settings.database.url == "postgresql://localhost/testdb"
        assert settings.database.pool_size == 10
        assert settings.discord.command_prefix == "?"
        assert settings.audio.default_volume == 0.8

    def test_type_coercion_from_strings(self, monkeypatch):
        """Should coerce string environment variables to correct types."""
        monkeypatch.setenv("DEBUG", "1")  # String "1" to bool True
        monkeypatch.setenv("DATABASE__POOL_SIZE", "15")  # String to int
        monkeypatch.setenv("AUDIO__DEFAULT_VOLUME", "0.75")  # String to float
        monkeypatch.setenv("DISCORD__SYNC_ON_STARTUP", "yes")  # String to bool

        settings = Settings()

        assert settings.debug is True
        assert settings.database.pool_size == 15
        assert settings.audio.default_volume == 0.75
        assert settings.discord.sync_on_startup is True

    def test_environment_validation(self, monkeypatch):
        """Should validate environment is one of allowed literal values."""
        monkeypatch.setenv("ENVIRONMENT", "invalid")

        with pytest.raises(ValidationError, match="Input should be"):
            Settings()

    def test_log_level_validation_case_insensitive(self, monkeypatch):
        """Should accept case-insensitive log levels and normalize to uppercase."""
        monkeypatch.setenv("LOG_LEVEL", "debug")

        settings = Settings()

        assert settings.log_level == "DEBUG"

    def test_log_level_validation_invalid(self, monkeypatch):
        """Should raise ValidationError for invalid log level."""
        monkeypatch.setenv("LOG_LEVEL", "INVALID")

        with pytest.raises(ValidationError, match="Invalid log level"):
            Settings()

    def test_nested_validation_propagates(self, monkeypatch):
        """Should propagate validation errors from nested settings."""
        monkeypatch.setenv("DATABASE__URL", "invalid://url")

        with pytest.raises(ValidationError, match="Database URL must start with"):
            Settings()

    def test_from_env_class_method(self, monkeypatch):
        """Should create settings using from_env() class method."""
        monkeypatch.setenv("ENVIRONMENT", "test")

        settings = Settings.from_env()

        assert settings.environment == "test"
        assert isinstance(settings, Settings)

    def test_case_insensitive_env_vars(self, monkeypatch):
        """Should accept environment variables in any case."""
        monkeypatch.setenv("environment", "production")  # lowercase
        monkeypatch.setenv("Debug", "true")  # mixed case
        monkeypatch.setenv("LOG_LEVEL", "ERROR")  # uppercase

        settings = Settings()

        assert settings.environment == "production"
        assert settings.debug is True
        assert settings.log_level == "ERROR"


# =============================================================================
# Settings Caching Tests
# =============================================================================


class TestSettingsCaching:
    """Unit tests for settings caching mechanism."""

    def test_get_settings_returns_cached_instance(self, monkeypatch):
        """Should return same instance on multiple calls to get_settings()."""
        clear_settings_cache()
        monkeypatch.setenv("ENVIRONMENT", "test")

        settings1 = get_settings()
        settings2 = get_settings()

        assert settings1 is settings2

    def test_clear_settings_cache(self, monkeypatch):
        """Should clear cache and return new instance after clear_settings_cache()."""
        clear_settings_cache()
        monkeypatch.setenv("ENVIRONMENT", "test")

        settings1 = get_settings()
        clear_settings_cache()
        monkeypatch.setenv("ENVIRONMENT", "production")
        settings2 = get_settings()

        assert settings1 is not settings2
        assert settings1.environment == "test"
        assert settings2.environment == "production"


# =============================================================================
# Integration Tests
# =============================================================================


class TestSettingsIntegration:
    """Integration tests for full settings configuration scenarios."""

    def test_production_configuration(self, monkeypatch):
        """Should create valid production configuration."""
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("DEBUG", "false")
        monkeypatch.setenv("LOG_LEVEL", "WARNING")
        monkeypatch.setenv("DATABASE__URL", "postgresql://prod-host/prod-db")
        monkeypatch.setenv("DISCORD__TOKEN", "prod-bot-token")
        monkeypatch.setenv("DISCORD__COMMAND_PREFIX", "!")
        monkeypatch.setenv("AI__API_KEY", "sk-prod-key")

        settings = Settings()

        assert settings.environment == "production"
        assert settings.debug is False
        assert settings.log_level == "WARNING"
        assert settings.database.url == "postgresql://prod-host/prod-db"
        assert settings.discord.token.get_secret_value() == "prod-bot-token"

    def test_development_configuration_minimal(self, monkeypatch):
        """Should create valid development configuration with minimal settings."""
        monkeypatch.setenv("ENVIRONMENT", "development")

        settings = Settings()

        assert settings.environment == "development"
        assert settings.database.url == "sqlite:///data/bot.db"
        assert settings.discord.command_prefix == "!"
        assert settings.audio.default_volume == 0.5

    def test_test_environment_configuration(self, monkeypatch):
        """Should create valid test environment configuration."""
        monkeypatch.setenv("ENVIRONMENT", "test")
        monkeypatch.setenv("DEBUG", "true")
        monkeypatch.setenv("DATABASE__URL", "sqlite:///:memory:")

        settings = Settings()

        assert settings.environment == "test"
        assert settings.debug is True
        assert settings.database.url == "sqlite:///:memory:"
