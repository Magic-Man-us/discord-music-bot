"""Centralized message constants for error messages, validation, and user feedback."""

from __future__ import annotations


class ErrorMessages:
    """Error messages for exceptions and validation failures."""

    # Discord ID Validation Errors
    INVALID_GUILD_ID = "Guild ID must be positive"
    INVALID_USER_ID = "User ID must be positive"
    INVALID_CHANNEL_ID = "Channel ID must be positive"
    INVALID_SNOWFLAKE = "Discord snowflake ID must be positive"
    SNOWFLAKE_TOO_LARGE = "Discord snowflake ID exceeds maximum value (2^64)"

    # Track Validation Errors
    EMPTY_TRACK_ID = "Track ID cannot be empty"
    EMPTY_TRACK_TITLE = "Track title cannot be empty"
    EMPTY_TRACK_URL = "Track webpage URL cannot be empty"
    NO_STREAM_URL = "Track '{title}' has no stream URL"

    # Voting Validation Errors
    INVALID_THRESHOLD = "Threshold must be at least 1"

    # Recommendation Validation Errors
    EMPTY_BASE_TRACK_TITLE = "Base track title is required"
    INVALID_RECOMMENDATION_COUNT_MIN = "Count must be at least 1"
    INVALID_RECOMMENDATION_COUNT_MAX = "Count cannot exceed 10"
    EMPTY_RECOMMENDATION_TITLE = "Recommendation title is required"
    INVALID_CONFIDENCE = "Confidence must be between 0 and 1"

    # Queue Validation Errors
    INVALID_QUEUE_POSITION = "Queue position cannot be negative"

    # Time/Date Validation Errors
    INVALID_WARMUP_SECONDS = "warmup_seconds must be non-negative"
    TIMEZONE_REQUIRED_JOINED_AT = "joined_at must be timezone-aware"
    TIMEZONE_REQUIRED_NOW = "now must be timezone-aware"
    TIMEZONE_REQUIRED_UTC_DATETIME = "UtcDateTime requires a timezone-aware datetime"

    # Field Validation Errors (templates)
    FIELD_MUST_BE_POSITIVE = "{field_name} must be positive"
    FIELD_CANNOT_BE_EMPTY = "{field_name} cannot be empty"

    # Database Validation Errors
    INVALID_DATABASE_URL = "Database URL must start with sqlite://, postgresql://, or mysql://"
    INVALID_LOG_LEVEL = "Invalid log level: {level}. Must be one of {valid_levels}"

    # Audio/Stream Errors
    NO_URL_IN_INFO_DICT = "No URL found in info dict"
    NO_STREAM_URL_FOR_TRACK = "No stream URL found for {title}"
    EMPTY_API_RESPONSE = "Empty response from API"
    RESOLVER_RETURNED_NONE = "Resolver returned None"

    # Radio Errors
    RADIO_NO_CURRENT_TRACK = "No track is currently playing to base radio on"
    RADIO_AI_UNAVAILABLE = "AI recommendation service is unavailable"

    # Authentication/Security Errors
    OPENAI_API_KEY_NOT_SET = "OPENAI_API_KEY is not set; AI recommender is disabled."
    DISCORD_TOKEN_REQUIRED = "DISCORD_TOKEN environment variable is required"
    BOT_NOT_INITIALIZED = "Bot not initialized. Call set_bot() first."
    CONTAINER_NOT_FOUND = "Container not found on bot instance"


class LogTemplates:
    """Log message templates for structured logging.

    Use these with logger.info(), logger.error(), etc. and pass values as parameters
    for proper log formatting and structured logging support.
    """

    # Database Lifecycle
    DATABASE_INITIALIZED = "Database initialized at %s"
    DATABASE_CLOSED = "Database manager closed"
    TABLE_MIGRATED = "Migrated table %s: added column %s"

    # Cleanup Operations
    CLEANUP_STARTED = "Cleanup job started"
    CLEANUP_STOPPED = "Cleanup job stopped"
    CLEANUP_ALREADY_RUNNING = "Cleanup job is already running"
    CLEANUP_CYCLE_RUNNING = "Running cleanup cycle"
    CLEANUP_COMPLETED = (
        "Cleanup completed: %s sessions, %s history entries, %s cache entries, %s vote sessions"
    )
    CLEANUP_SESSIONS_FAILED = "Failed to cleanup sessions: %r"
    CLEANUP_HISTORY_FAILED = "Failed to cleanup history: %r"
    CLEANUP_CACHE_FAILED = "Failed to cleanup cache: %r"
    CLEANUP_VOTE_SESSIONS_FAILED = "Failed to cleanup vote sessions: %r"

    # Cache Operations
    CACHE_HIT = "Cache hit for '%s'"
    CACHE_HIT_URL = "Cache hit for URL: %s"
    CACHE_EXPIRED_CLEANED = "Cleaned %d expired cache entries"
    CACHE_EXPIRED_PRUNED = "Pruned %d expired cache entries"
    CACHE_CLEARED = "Cleared %d cache entries"
    CACHE_JOIN_INFLIGHT = "Joining in-flight request for '%s'"

    # Voice/Audio Operations
    VOICE_CONNECTED = "Connected to voice channel %s in %s"
    VOICE_DISCONNECTED = "Disconnected from voice in guild %s"
    VOICE_MOVED = "Moved to voice channel %s"
    VOICE_CONNECTION_TIMEOUT = "Timeout connecting to channel %s"
    VOICE_MOVE_TIMEOUT = "Timeout moving to channel %s"
    VOICE_NO_PERMISSION = "No permission to connect to channel %s"
    VOICE_CLIENT_ERROR = "Client error connecting: %r"
    VOICE_STALE_CLEANUP = "Found stale voice client in guild %s, cleaning up"
    VOICE_NOT_CONNECTED = "Not connected to voice in guild %s"
    VOICE_CONNECTION_CLEANED_UP = "Cleaned up voice connection for guild %s"
    VOICE_CLEANUP_ERROR = "Error during voice cleanup"
    VOICE_CONNECTION_CONTEXT_ERROR = "Error in voice connection context: %s"
    VOICE_ADAPTER_FAILED = "Voice adapter failed to play in guild %s"
    VOICE_SELF_DEAFEN_FAILED = "Failed to self-deafen in guild %s: %r"

    # Playback Operations
    PLAYBACK_STARTED = "Started playing '%s' in guild %s"
    PLAYBACK_STOPPED = "Stopped playback in guild %s"
    PLAYBACK_PAUSED = "Paused playback in guild %s"
    PLAYBACK_RESUMED = "Resumed playback in guild %s"
    PLAYBACK_ERROR = "Playback error in guild %s: %s"
    PLAYBACK_FAILED_START = "Failed to start playback: %s"
    PLAYBACK_FAILED_STOP = "Failed to stop playback: %s"
    PLAYBACK_FAILED_PAUSE = "Failed to pause: %s"
    PLAYBACK_FAILED_RESUME = "Failed to resume: %s"
    PLAYBACK_FAILED_VOLUME = "Failed to set volume: %s"
    PLAYBACK_NO_CALLBACK = "No track end callback set for guild %s"
    PLAYBACK_CALLING_CALLBACK = "Calling track end callback for guild %s"
    PLAYBACK_CALLBACK_ERROR = "Error in track end callback for guild %s: %s"
    PLAYBACK_ALREADY_PLAYING = "Already playing in guild %s, returning True"
    PLAYBACK_START_CALLED = "start_playback called for guild %s"
    PLAYBACK_IGNORING_CALLBACK = "Ignoring voice track-end callback for guild %s"

    # Track Operations
    TRACK_STARTED = "Started playing: %s in guild %s"
    TRACK_SKIPPED = "Skipped track: %s in guild %s"
    TRACK_FINISHED = "Track finished: %s in guild %s"
    TRACK_ENDED = "Track ended in guild %s (error: %s)"
    TRACK_GOT_TO_PLAY = "Got track to play: %s"

    # Queue Operations
    QUEUE_EMPTY = "Queue empty in guild %s"
    QUEUE_NO_TRACKS = "No tracks in queue for guild %s"
    QUEUE_ENQUEUED = "Enqueued track '%s' at position %s in guild %s"
    QUEUE_ENQUEUED_NEXT = "Enqueued track '%s' to play next in guild %s"
    QUEUE_REMOVED = "Removed track '%s' from queue in guild %s"
    QUEUE_CLEARED = "Cleared %s tracks from queue in guild %s"
    QUEUE_SHUFFLED = "Shuffled queue in guild %s"
    QUEUE_MOVED = "Moved track from %s to %s in guild %s"

    # Loop Mode
    LOOP_MODE_CHANGED = "Loop mode changed to %s in guild %s"

    # Session/Guild Operations
    SESSION_NOT_FOUND = "No session found for guild %s"
    SESSION_CLEANED_UP = "Cleaned up guild %s"
    SESSION_STALE_CLEANED = "Cleaned up %s stale sessions"
    GUILD_NOT_FOUND = "Guild %s not found"
    CHANNEL_NOT_VOICE = "Channel %s is not a voice channel"

    # Repository Operations
    SESSION_SAVED = "Saved session for guild %s"
    SESSION_DELETED = "Deleted session for guild %s"
    VOTE_SESSION_SAVED = "Saved vote session for guild %s"
    VOTE_SESSION_DELETED = "Deleted vote session for guild %s"
    VOTE_SESSIONS_DELETED = "Deleted %s vote sessions for guild %s"
    VOTE_SESSION_COMPLETED = "Completed vote session for guild %s, result=%s"
    VOTE_SESSIONS_EXPIRED_CLEANED = "Cleaned up %s expired vote sessions"
    HISTORY_RECORDED = "Recorded play for track %s in guild %s"
    HISTORY_OLD_CLEANED = "Cleaned up %s old history entries"
    HISTORY_CLEARED = "Cleared %s history entries for guild %s"

    # Cog Lifecycle
    COG_LOADED_INFO = "Info cog loaded with context menus"
    COG_UNLOADED_INFO = "Info cog unloaded, context menus removed"
    COG_LOADED_HEALTH = "Health cog loaded, heartbeat loops started"
    COG_UNLOADED_HEALTH = "Health cog unloaded, heartbeat loops stopped"

    # Health/Heartbeat (continued)
    HEARTBEAT_FAST_ERROR = "Fast heartbeat error"
    HEARTBEAT_DETAILED_ERROR = "Detailed heartbeat error"

    # Admin/Command Operations
    ADMIN_COMMAND_FAILED = "Admin command failed"
    ADMIN_RELOAD_FAILED = "Failed to reload %s"
    ADMIN_SYNC_COMMANDS_FAILED = "Failed to sync commands"
    ADMIN_FETCH_SLASH_STATUS_FAILED = "Failed to fetch slash status"
    ADMIN_CACHE_STATUS_FAILED = "Failed to get cache status"
    ADMIN_CACHE_CLEAR_FAILED = "Failed to clear cache"
    ADMIN_CACHE_PRUNE_FAILED = "Failed to prune cache"
    ADMIN_CLEANUP_FAILED = "Failed to run cleanup"
    ADMIN_DB_STATS_FAILED = "Failed to get db stats"
    MESSAGE_STATE_CLEANED = "Cleaned up message state for guild %s"
    MESSAGE_DELETED = "Message deleted %s by %s"

    # FFmpeg/Audio Resource Management
    FFMPEG_RESOURCES_CLEANED = "Cleaned up FFmpeg resources for %s guilds"
    FFMPEG_SOURCE_CLEANUP_ERROR = "Error cleaning up source: %s"
    FFMPEG_PROCESS_CLEANUP_ERROR = "Error cleaning up process: %s"
    FFMPEG_DISCORD_CLIENT_ERROR = "Discord client error: %s"

    # Resolution/Search
    RESOLUTION_FAILED = "Resolution failed: {error}"
    SEARCH_FAILED = "Search failed for '{query}': {error}"
    PLAYLIST_FAILED = "Playlist extraction failed for {url}: {error}"
    YTDLP_NO_URL_IN_INFO_DICT = "No URL found in info dict"
    YTDLP_NO_STREAM_URL = "No stream URL found for %s"
    YTDLP_FAILED_INFO_TO_TRACK = "Failed to convert info to track"
    YTDLP_FAILED_EXTRACT_INFO = "Failed to extract info from %s"
    YTDLP_FAILED_SEARCH = "Failed to search for %r"
    YTDLP_FAILED_EXTRACT_PLAYLIST = "Failed to extract playlist from %s"
    YTDLP_FAILED_RESOLVE = "Failed to resolve %r"
    YTDLP_POT_CONFIGURED = "bgutil-ytdlp-pot-provider configured (server=%s)"

    # Health/Heartbeat
    HEARTBEAT_FAST = "Fast heartbeat: latency=%.1fms"
    HEARTBEAT_DETAILED = "Detailed heartbeat collected"

    # Application Lifecycle
    BOT_STARTING = "Starting Discord Music Bot in {environment} mode"
    BOT_SETUP = "Setting up bot..."
    BOT_CONTAINER_INITIALIZED = "Container initialized successfully"
    BOT_CONTAINER_INIT_FAILED = "Failed to initialize container: %s"
    BOT_SETUP_COMPLETE = "Bot setup complete"
    BOT_STARTING_RUN = "Starting bot..."
    BOT_STOPPED = "Bot stopped successfully"
    BOT_KEYBOARD_INTERRUPT = "Received keyboard interrupt, shutting down..."
    BOT_FATAL_ERROR = "Fatal error: %s"
    BOT_SHUTTING_DOWN = "Shutting down bot..."
    BOT_CONTAINER_SHUTDOWN = "Container shutdown complete"
    BOT_CONTAINER_SHUTDOWN_ERROR = "Error during container shutdown: %s"
    BOT_SHUTDOWN_COMPLETE = "Bot shutdown complete"
    BOT_READY = "Bot ready as %s (%s)"
    BOT_CONNECTED_GUILDS = "Connected to %s guilds"

    # Bot Cog Management
    BOT_COG_LOADED = "Loaded cog: %s"
    BOT_COG_LOAD_FAILED = "Failed to load cog %s: %s"
    BOT_COGS_LOADED_SUMMARY = "Cogs loaded: %s success, %s failed"

    # Bot Command Sync
    BOT_SYNCED_GUILD = "Synced %s commands to guild %s"
    BOT_SYNC_GUILD_FAILED = "Failed to sync to guild %s: %s"
    BOT_SYNCED_GLOBAL = "Synced %s commands globally"
    BOT_SYNC_GLOBAL_FAILED = "Failed to sync commands globally: %s"
    BOT_SYNC_ON_STARTUP_FAILED = "Failed to sync commands on startup: %s"

    # Bot Session Management
    BOT_STALE_SESSIONS_RESET = "Reset %s stale sessions on startup"
    BOT_NO_STALE_SESSIONS = "No stale sessions found on startup"
    BOT_STALE_SESSIONS_RESET_FAILED = "Failed to reset stale sessions: %s"

    # Bot Error Handling
    BOT_SLASH_COMMAND_ERROR = "Slash command error in '%s': %s"
    BOT_ERROR_MESSAGE_SEND_FAILED = "Failed to send error message to user"
    BOT_CLEANUP_START_FAILED = "Failed to start cleanup job: %s"
    BOT_CLEANUP_STOP_ERROR = "Error stopping cleanup job: %s"

    # AI/Recommendations
    AI_CLIENT_INITIALIZED = "AI client initialized (model=%s, timeout=%ss)"
    AI_RESPONSE_PARSE_ERROR = "AI response parse error: %s"
    AI_REQUEST_FAILED = "Failed to get recommendations: %s"
    AI_CACHE_PARSE_FAILED = "Failed to parse cached recommendations: %s"
    AI_GENERATED_RECOMMENDATIONS = "Generated %d recommendations for '%s'"
    AI_CACHE_SAVED = "Cached recommendations for '%s' (expires in %d seconds)"
    AI_FETCHING_RECOMMENDATIONS = "Fetching recommendations for '%s' (count=%d)"
    AI_API_ERROR_RETRY = "AI API error attempt=%d/%d: %s"

    # Database Statistics
    DATABASE_STATS_FAILED = "Failed to get database stats: %s"

    # Auto-skip
    AUTOSKIP_ON_REQUESTER_LEAVE = "Requester left voice channel in guild %s, auto-skipping..."

    # Radio
    RADIO_ENABLED = "Radio enabled in guild %s (seed='%s')"
    RADIO_DISABLED = "Radio disabled in guild %s"
    RADIO_REFILL_TRIGGERED = "Radio refill triggered in guild %s"
    RADIO_REFILL_COMPLETED = "Radio refill completed in guild %s: %d tracks added"
    RADIO_REFILL_FAILED = "Radio refill failed in guild %s: %s"
    RADIO_TRACK_RESOLVE_FAILED = "Radio: failed to resolve recommendation '%s': %s"
    RADIO_SESSION_LIMIT = "Radio session limit reached in guild %s (%d/%d tracks)"


class DiscordUIMessages:
    """User-facing Discord messages and responses.

    These strings are shown directly to users in Discord interactions.
    Keep them concise, friendly, and include appropriate emoji.
    """

    # Success Messages
    SUCCESS_COMMANDS_SYNCED = "✅ Commands synced successfully"
    SUCCESS_SKIP_VOTE_RECORDED = "✅ Your skip vote was recorded"
    SUCCESS_TRACK_REMOVED = "✅ Removed track from position {position}"
    SUCCESS_QUEUE_CLEARED = "✅ Cleared the queue."
    SUCCESS_GENERIC = "Done."
    SUCCESS_SYNCED_GLOBAL = "✅ Synced {count} slash commands globally."
    SUCCESS_SYNCED_GUILD = "✅ Synced {count} slash commands to this server."
    SUCCESS_RELOADED_EXTENSION = "✅ Reloaded `{module}`"
    SUCCESS_RELOADED_EXTENSIONS = "✅ Reloaded {ok} extensions, {failed} failed."
    SUCCESS_CACHE_CLEARED = "✅ Cleared {cleared} cache entries."
    SUCCESS_CACHE_PRUNED = "✅ Pruned {pruned} expired cache entries."
    SUCCESS_SHUTTING_DOWN = "👋 Shutting down..."
    SUCCESS_PONG = "{emoji} Pong: {latency_ms} ms"
    SUCCESS_GUILD_WELCOME = "Thanks for inviting me! Use `/help` for commands."
    SUCCESS_MEMBER_WELCOME = "Welcome {member_mention}!"

    # Vote Messages
    VOTE_ALREADY_VOTED = "You already voted. Votes: {votes_current}/{votes_needed}"
    VOTE_RECORDED = "Vote recorded ({votes_current}/{votes_needed})."
    VOTE_SKIP_PROCESSED = "Skip request processed."
    VOTE_NOT_IN_CHANNEL = "Join my voice channel to vote skip."

    # Error Messages
    ERROR_COMMANDS_SYNC_FAILED = "⚠️ Failed to sync commands"
    ERROR_OCCURRED = "An error occurred: {error}"
    ERROR_SKIP_FAILED = "❌ Could not complete the skip"
    ERROR_INVALID_POSITION = "❌ Invalid position: {position}"
    ERROR_POSITION_REQUIRED = "❌ You must provide a position number."
    ERROR_POSITION_MUST_BE_POSITIVE = "Position must be 1 or greater."
    ERROR_NO_TRACK_AT_POSITION = "No track at position {position}."
    ERROR_TRACK_NOT_FOUND = "Couldn't find a track for: {query}"
    ERROR_FORCE_SKIP_REQUIRES_ADMIN = "Force skip requires administrator permission."
    ERROR_COULD_NOT_JOIN_VOICE = "I couldn't join your voice channel."
    ERROR_REQUIRES_OWNER_OR_ADMIN = "❌ Requires owner or admin permissions."
    ERROR_MISSING_ARGUMENT = "❌ Missing argument: {param_name}"
    ERROR_INVALID_ARGUMENT = "❌ Invalid argument."
    ERROR_COMMAND_FAILED_SEE_LOGS = "❌ Command failed. See logs."
    ERROR_RUN_IN_SERVER_OR_SYNC_GLOBAL = "❌ Run in a server or use `!sync global`."
    ERROR_SYNC_FAILED_SEE_LOGS = "❌ Failed to sync. See logs."
    ERROR_FETCH_STATUS_FAILED = "❌ Failed to fetch status. See logs."
    ERROR_RELOAD_FAILED = "❌ Failed to reload `{extension}`"
    ERROR_NO_EXTENSIONS_LOADED = "❌ No extensions loaded."
    ERROR_CACHE_STATUS_FAILED = "❌ Failed to get cache status."
    ERROR_CACHE_CLEAR_FAILED = "❌ Failed to clear cache."
    ERROR_CACHE_PRUNE_FAILED = "❌ Failed to prune cache."
    ERROR_CLEANUP_FAILED = "❌ Failed to run cleanup."
    ERROR_DB_STATS_FAILED = "❌ Failed to get database stats."
    ERROR_COMMAND_COOLDOWN = "⏳ Command on cooldown. Try again in {time_str}."
    ERROR_MISSING_PERMISSIONS = "❌ You don't have permission to use this command."
    ERROR_BOT_MISSING_PERMISSIONS = "❌ I need these permissions: {missing}"

    # Action Messages
    ACTION_SKIP_PASSED = "⏭️ Vote skip passed! Moving to next track..."
    ACTION_SKIP_THRESHOLD_MET = (
        "⏭️ Skip threshold met ({votes_current}/{votes_needed}). Skipped: **{track_title}**"
    )
    ACTION_SKIP_REQUESTER = "⏭️ Requester skipped: **{track_title}**"
    ACTION_SKIP_AUTO = "⏭️ Auto-skipped (small audience): **{track_title}**"
    ACTION_SKIP_FORCE = "⏭️ Force skipped: **{track_title}**"
    ACTION_SKIP_GENERIC = "⏭️ Skipped: **{track_title}**"
    ACTION_STOPPED = "⏹️ Stopped playback and cleared the queue."
    ACTION_PAUSED = "⏸️ Paused playback."
    ACTION_RESUMED = "▶️ Resumed playback."
    ACTION_SHUFFLED = "🔀 Shuffled the queue."
    ACTION_LOOP_MODE_SET = "🔁 Loop mode set to: {mode}"
    ACTION_LOOP_MODE_CHANGED = "{emoji} Loop mode: **{mode}**"
    ACTION_DISCONNECTED = "👋 Disconnected from voice channel."
    ACTION_TRACK_REMOVED = "🗑️ Removed: **{track_title}**"
    ACTION_QUEUE_CLEARED = "🗑️ Cleared {count} tracks from the queue."

    # Radio Messages
    RADIO_ENABLED = "📻 Radio enabled! Queued {count} similar tracks based on **{seed_title}**."
    RADIO_DISABLED = "📻 Radio disabled."
    RADIO_NO_CURRENT_TRACK = "📻 Nothing is playing — play a track first, then use `/radio`."
    RADIO_AI_FAILED = "📻 Couldn't get recommendations right now. Try again later."
    RADIO_SESSION_LIMIT = "📻 Radio session limit reached ({limit} tracks). Use `/radio` to start a new session."

    # State Messages
    STATE_NOTHING_PLAYING = "Nothing is playing."
    STATE_NOTHING_PLAYING_OR_PAUSED = "Nothing is playing or already paused."
    STATE_NOTHING_PAUSED = "Nothing is paused."
    STATE_QUEUE_EMPTY = "Queue is empty."
    STATE_QUEUE_ALREADY_EMPTY = "Queue is already empty."
    STATE_NOT_ENOUGH_TRACKS_TO_SHUFFLE = "Not enough tracks to shuffle."
    STATE_NOT_CONNECTED_TO_VOICE = "Not connected to a voice channel."
    STATE_NO_TRACKS_PLAYED_YET = "No tracks have been played yet in this server."
    STATE_MUST_BE_IN_VOICE = "You must be in a voice channel to use this command!"
    STATE_NEED_TO_BE_IN_VOICE = "You need to be in a voice channel first."
    STATE_VOICE_WARMUP_REQUIRED = (
        "You must be in the voice channel for {remaining}s before you can use commands."
    )
    STATE_SERVER_ONLY = "This command can only be used in a server."
    STATE_VERIFY_VOICE_FAILED = "Could not verify your voice state."
    STATE_VERIFY_PERMISSIONS_FAILED = "Could not verify your permissions."

    # Embed Titles
    EMBED_NOW_PLAYING = "🎵 Now Playing"
    EMBED_RECENTLY_PLAYED = "Recently Played"
    EMBED_QUEUE = "📋 Queue ({total_tracks} tracks) — Page {page}/{total_pages}"
    EMBED_BOT_HEALTH = "🏥 Bot Health"
    EMBED_USER_INFO = "User Info: {display_name}"
    EMBED_MESSAGE_INFO = "Message Info"
    EMBED_SERVER_INFO = "Server Info: {guild_name}"
    EMBED_AVATAR = "Avatar: {display_name}"
    EMBED_SLASH_COMMAND_STATUS = "📋 Slash Command Status"
    EMBED_SLASH_STATUS_FOOTER = "Global sync can take up to 1 hour. Guild sync is immediate."
    EMBED_HEALTH_FOOTER = "Use /ping for quick latency check"
    EMBED_CACHE_STATISTICS = "📊 Cache Statistics"
    EMBED_CLEANUP_RESULTS = "🧹 Cleanup Results"
    EMBED_DATABASE_STATISTICS = "🗄️ Database Statistics"
    EMBED_BOT_STATUS = "🤖 Bot Status"


class EmojiConstants:
    """Emoji constants for consistent visual feedback."""

    # Status Indicators
    SUCCESS = "✅"
    ERROR = "❌"
    WARNING = "⚠️"
    INFO = "ℹ️"

    # Media Controls
    PLAY = "▶️"
    PAUSE = "⏸️"
    STOP = "⏹️"
    SKIP = "⏭️"
    PREVIOUS = "⏮️"
    FAST_FORWARD = "⏩"
    REWIND = "⏪"

    # Queue Operations
    SHUFFLE = "🔀"
    LOOP = "🔁"
    QUEUE = "📋"

    # Music/Audio
    MUSIC_NOTE = "🎵"
    MUSIC_NOTES = "🎶"
    SPEAKER = "🔊"
    MUTE = "🔇"
    MICROPHONE = "🎤"

    # Actions
    WAVE = "👋"  # Leave/goodbye
    MAGNIFYING_GLASS = "🔍"  # Search
    LINK = "🔗"  # External link
    DOWNLOAD = "📥"  # Download

    # Status/Info
    HEALTH = "🏥"
    ROBOT = "🤖"
    CHART = "📊"
    DATABASE = "🗄️"
    CLEANUP = "🧹"
    TOOLS = "🔧"
    SETTINGS = "⚙️"

    # Server/User
    CROWN = "👑"  # Owner/admin
    SHIELD = "🛡️"  # Moderator
    PERSON = "👤"  # User
    PEOPLE = "👥"  # Members

    # Time
    CLOCK = "🕐"
    CALENDAR = "📅"
    HOURGLASS = "⏳"

    # Radio
    RADIO = "📻"
