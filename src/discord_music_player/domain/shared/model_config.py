"""Centralized Pydantic ``model_config`` presets — the single source for model configs.

Models reference a preset (``model_config = FrozenModelConfig``) instead of inlining
``ConfigDict(...)``, so configuration intent lives in one place.
"""

from __future__ import annotations

from pydantic import ConfigDict

# Immutable value objects and entities — the common case.
FrozenModelConfig = ConfigDict(frozen=True)

# Immutable DTOs that must reject silent coercion.
FrozenStrictModelConfig = ConfigDict(frozen=True, strict=True)

# Immutable models parsing external payloads (DB rows, yt-dlp / AI responses) — drop unknown keys.
FrozenBoundaryModelConfig = ConfigDict(frozen=True, extra="ignore")

# Boundary models that also accept field names alongside aliases (Apple Music JSON).
FrozenBoundaryAliasedModelConfig = ConfigDict(frozen=True, extra="ignore", populate_by_name=True)

# Nested settings sub-models loaded by the top-level BaseSettings.
SettingsSubModelConfig = ConfigDict(frozen=True, strict=True, populate_by_name=True)

# Domain events — immutable and reject unknown keys.
EventModelConfig = ConfigDict(frozen=True, extra="forbid")

# Mutable aggregates and per-run state.
MutableModelConfig = ConfigDict()

# Mutable aggregate that must reject silent coercion (playback session).
MutableStrictModelConfig = ConfigDict(strict=True)

# Immutable model holding non-Pydantic objects (callables, deque).
FrozenArbitraryModelConfig = ConfigDict(frozen=True, arbitrary_types_allowed=True)

# Mutable model holding non-Pydantic objects (Discord message state).
MutableArbitraryModelConfig = ConfigDict(arbitrary_types_allowed=True)

# Strict JSON schema serialized to disk — reject unknown keys (heartbeat payload).
StrictSchemaModelConfig = ConfigDict(extra="forbid")

# Schema that tolerates extra runtime fields (detailed heartbeat metrics).
ExtraAllowedModelConfig = ConfigDict(extra="allow")
