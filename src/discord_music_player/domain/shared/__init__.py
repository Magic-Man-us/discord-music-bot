"""
Shared Domain Kernel

Contains value objects and exceptions shared across all bounded contexts.
"""

from .exceptions import (
    BusinessRuleViolationError,
    DomainError,
    InvalidOperationError,
)

__all__ = [
    "DomainError",
    "BusinessRuleViolationError",
    "InvalidOperationError",
]
