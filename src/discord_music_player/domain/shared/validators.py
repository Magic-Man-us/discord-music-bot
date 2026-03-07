"""Shared Pydantic validators for Discord-specific data types.

NOTE: Most validation is handled declaratively via Annotated type aliases
in ``types.py`` (e.g. ``DiscordSnowflake``, ``NonEmptyStr``).
This module is reserved for validators that cannot be expressed as
simple field constraints.
"""
