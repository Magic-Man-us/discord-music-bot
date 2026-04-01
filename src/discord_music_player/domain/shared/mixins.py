"""Shared mixins for domain entities."""

from __future__ import annotations

from datetime import datetime

from .datetime_utils import utcnow


class ExpirableMixin:
    """Mixin for entities with an optional expiration timestamp."""

    expires_at: datetime | None

    @property
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return utcnow() > self.expires_at
