"""Centralized message constants for error messages, validation, and user feedback."""

from __future__ import annotations


class ErrorMessages:
    """Shared error messages used across multiple modules."""

    CONTAINER_NOT_FOUND = "Container not found on bot instance"


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
    ERROR_DB_VALIDATE_FAILED = "❌ Failed to validate database."
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

    # Requester Left Messages
    REQUESTER_LEFT_PROMPT = (
        "**{requester_name}** has left the voice channel. "
        "Do you want to continue playing **{track_title}**?"
    )
    REQUESTER_LEFT_RESUMED = "▶️ Playback resumed."
    REQUESTER_LEFT_SKIPPED = "⏭️ Track skipped."
    REQUESTER_LEFT_TIMEOUT = "⏭️ Track skipped (no response)."

    # Resume Playback Messages
    RESUME_PLAYBACK_RESUMED = "▶️ Resumed playback: **{track_title}**"
    RESUME_PLAYBACK_CLEARED = "⏭️ Skipped. Playback cleared."
    RESUME_PLAYBACK_TIMEOUT = "⏭️ Playback cleared (no response)."

    # Radio Messages
    RADIO_ENABLED = "📻 Radio enabled! Queued {count} similar tracks based on **{seed_title}**."
    RADIO_DISABLED = "📻 Radio disabled."
    RADIO_NO_CURRENT_TRACK = "📻 Nothing is playing — play a track first, then use `/radio`."
    RADIO_AI_FAILED = "📻 Couldn't get recommendations right now. Try again later."
    RADIO_SESSION_LIMIT = "📻 Radio session limit reached ({limit} tracks). Use `/radio` to start a new session."

    # Shuffle Messages
    SHUFFLE_ALREADY_IN_PROGRESS = "Someone is already shuffling, please wait."
    SHUFFLE_QUEUED_NEXT = "\U0001f500 Queued next: **{track_title}**"
    SHUFFLE_NO_RECOMMENDATION = "Could not generate a recommendation. Try again later."
    SHUFFLE_TRACK_NOT_FOUND = "Could not find a playable track for: {display_text}"
    SHUFFLE_ERROR = "An error occurred while shuffling. Please try again."

    # Analytics Messages
    ANALYTICS_NO_DATA = "No music has been played yet in this server."
    ANALYTICS_GENRE_UNAVAILABLE = "Genre data unavailable (AI service not configured)."

    # Validation Messages
    ERROR_INVALID_TIMESTAMP = (
        "Invalid timestamp format. Use `1:30`, `1:30:00`, or seconds like `90`."
    )
    ERROR_NO_CHANNEL_CONTEXT = "Cannot start vote: no channel context."

    # Shuffle History
    SHUFFLE_HISTORY_QUEUED = (
        "\U0001f500 Shuffled and queued **{count}** tracks from history."
    )

    # Radio Clear
    RADIO_CLEARED_WITH_COUNT = (
        "\U0001f4fb Radio disabled. Removed **{count}** AI recommendation(s) from the queue."
    )
    RADIO_CLEARED_EMPTY = (
        "\U0001f4fb Radio disabled. No AI recommendations were in the queue."
    )

    # Up Next
    UP_NEXT_NONE = "No Track Queued"

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
    STATE_VOICE_WARMUP_READY = "You can now use commands! Click **Retry** to play."
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
    EMBED_DATABASE_VALIDATION = "🔍 Database Validation"
    EMBED_BOT_STATUS = "🤖 Bot Status"
    EMBED_SERVER_STATS = "📊 Server Music Stats"
    EMBED_TOP_TRACKS = "🏆 Top Tracks"
    EMBED_TOP_USERS = "🏆 Top Listeners"
    EMBED_TOP_SKIPPED = "⏭️ Most Skipped"
    EMBED_USER_STATS = "🎵 Your Music Stats"
    EMBED_ACTIVITY = "📈 Listening Activity"
