"""Shared Pydantic validators for Discord-specific data types.

NOTE: All validation is handled declaratively via Annotated type aliases
in ``types.py`` (e.g. ``DiscordSnowflake``, ``NonEmptyStr``).
This module is intentionally empty — add validators here only when they
cannot be expressed as simple field constraints.
"""
