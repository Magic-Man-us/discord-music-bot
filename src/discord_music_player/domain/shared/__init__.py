"""
Shared Domain Kernel

Contains value objects and exceptions shared across all bounded contexts.
"""

from .exceptions import (
    BusinessRuleViolationError,
    ConcurrencyError,
    DomainError,
    EntityNotFoundError,
    InvalidOperationError,
    ValidationError,
)

__all__ = [
    "DomainError",
    "ValidationError",
    "EntityNotFoundError",
    "BusinessRuleViolationError",
    "ConcurrencyError",
    "InvalidOperationError",
]
