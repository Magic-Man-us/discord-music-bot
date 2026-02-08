"""Base exception classes for domain-level errors."""

from __future__ import annotations


class DomainError(Exception):
    """Base exception for all domain-level errors."""

    def __init__(self, message: str, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.code = code or self.__class__.__name__


class ValidationError(DomainError):
    """Raised when domain validation fails."""

    def __init__(self, message: str, field: str | None = None) -> None:
        super().__init__(message, code="VALIDATION_ERROR")
        self.field = field


class EntityNotFoundError(DomainError):
    """Raised when a requested entity does not exist."""

    def __init__(self, entity_type: str, identifier: str | int, message: str | None = None) -> None:
        msg = message or f"{entity_type} with id '{identifier}' not found"
        super().__init__(msg, code="ENTITY_NOT_FOUND")
        self.entity_type = entity_type
        self.identifier = identifier


class BusinessRuleViolationError(DomainError):
    """Raised when a business rule is violated."""

    def __init__(self, rule: str, message: str | None = None) -> None:
        msg = message or f"Business rule violated: {rule}"
        super().__init__(msg, code="BUSINESS_RULE_VIOLATION")
        self.rule = rule


class ConcurrencyError(DomainError):
    """Raised when a concurrent modification conflict occurs."""

    def __init__(self, entity_type: str, message: str | None = None) -> None:
        msg = message or f"Concurrent modification detected for {entity_type}"
        super().__init__(msg, code="CONCURRENCY_ERROR")
        self.entity_type = entity_type


class InvalidOperationError(DomainError):
    """Raised when an operation is invalid in the current state."""

    def __init__(self, operation: str, current_state: str, message: str | None = None) -> None:
        msg = message or f"Cannot perform '{operation}' in state '{current_state}'"
        super().__init__(msg, code="INVALID_OPERATION")
        self.operation = operation
        self.current_state = current_state
