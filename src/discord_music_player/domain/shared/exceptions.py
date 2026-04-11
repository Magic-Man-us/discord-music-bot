"""Base exception classes for domain-level errors."""

from __future__ import annotations


class DomainError(Exception):

    def __init__(self, message: str, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.code = code or self.__class__.__name__


class BusinessRuleViolationError(DomainError):

    def __init__(self, rule: str, message: str | None = None) -> None:
        msg = message or f"Business rule violated: {rule}"
        super().__init__(msg, code="BUSINESS_RULE_VIOLATION")
        self.rule = rule


class InvalidOperationError(DomainError):

    def __init__(self, operation: str, current_state: str, message: str | None = None) -> None:
        msg = message or f"Cannot perform '{operation}' in state '{current_state}'"
        super().__init__(msg, code="INVALID_OPERATION")
        self.operation = operation
        self.current_state = current_state
