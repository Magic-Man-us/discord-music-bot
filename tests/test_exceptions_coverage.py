"""
Additional Exceptions Tests for Coverage

Tests edge cases and uncovered code paths in domain exceptions.
"""

import pytest

from discord_music_player.domain.shared.exceptions import (
    BusinessRuleViolationError,
    DomainError,
    InvalidOperationError,
)


class TestDomainExceptionEdgeCases:
    """Tests for domain exception edge cases and uncovered paths."""

    def test_domain_error_with_message(self):
        """Should create DomainError with message."""
        error = DomainError("Something went wrong")

        assert str(error) == "Something went wrong"
        assert error.message == "Something went wrong"
        assert error.code == "DomainError"

    def test_domain_error_with_custom_code(self):
        """Should use custom error code when provided."""
        error = DomainError("Custom error", code="CUSTOM_CODE")

        assert error.code == "CUSTOM_CODE"

    def test_business_rule_violation_default_message(self):
        """Should generate default message for BusinessRuleViolationError."""
        error = BusinessRuleViolationError("MaxQueueSize")

        assert "Business rule violated" in str(error)
        assert "MaxQueueSize" in str(error)
        assert error.rule == "MaxQueueSize"
        assert error.code == "BUSINESS_RULE_VIOLATION"

    def test_business_rule_violation_custom_message(self):
        """Should use custom message when provided."""
        error = BusinessRuleViolationError("MaxQueueSize", message="Queue cannot exceed 100 tracks")

        assert str(error) == "Queue cannot exceed 100 tracks"
        assert error.rule == "MaxQueueSize"

    def test_invalid_operation_error_default_message(self):
        """Should generate default message for InvalidOperationError."""
        error = InvalidOperationError("play", "stopped")

        assert "Cannot perform" in str(error)
        assert "play" in str(error)
        assert "stopped" in str(error)
        assert error.operation == "play"
        assert error.current_state == "stopped"
        assert error.code == "INVALID_OPERATION"

    def test_invalid_operation_error_custom_message(self):
        """Should use custom message when provided."""
        error = InvalidOperationError(
            "resume",
            "not_paused",
            message="Cannot resume playback that is not paused",
        )

        assert str(error) == "Cannot resume playback that is not paused"
        assert error.operation == "resume"
        assert error.current_state == "not_paused"

    def test_exception_inheritance(self):
        """All domain exceptions should inherit from DomainError."""
        assert issubclass(BusinessRuleViolationError, DomainError)
        assert issubclass(InvalidOperationError, DomainError)

    def test_exceptions_are_exceptions(self):
        """All domain exceptions should inherit from Exception."""
        assert issubclass(DomainError, Exception)
        assert issubclass(BusinessRuleViolationError, Exception)
