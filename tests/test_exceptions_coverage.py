"""
Additional Exceptions Tests for Coverage

Tests edge cases and uncovered code paths in domain exceptions.
"""

import pytest

from discord_music_player.domain.shared.exceptions import (
    BusinessRuleViolationError,
    ConcurrencyError,
    DomainError,
    EntityNotFoundError,
    InvalidOperationError,
    ValidationError,
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

    def test_validation_error_with_message(self):
        """Should create ValidationError with message."""
        error = ValidationError("Invalid input")

        assert str(error) == "Invalid input"
        assert error.code == "VALIDATION_ERROR"
        assert error.field is None

    def test_validation_error_with_field(self):
        """Should include field name in ValidationError."""
        error = ValidationError("Email is required", field="email")

        assert error.message == "Email is required"
        assert error.field == "email"
        assert error.code == "VALIDATION_ERROR"

    def test_entity_not_found_error_default_message(self):
        """Should generate default message for EntityNotFoundError."""
        error = EntityNotFoundError("Track", "abc123")

        assert "Track" in str(error)
        assert "abc123" in str(error)
        assert "not found" in str(error)
        assert error.entity_type == "Track"
        assert error.identifier == "abc123"
        assert error.code == "ENTITY_NOT_FOUND"

    def test_entity_not_found_error_custom_message(self):
        """Should use custom message when provided."""
        error = EntityNotFoundError("User", 12345, message="User does not exist")

        assert str(error) == "User does not exist"
        assert error.entity_type == "User"
        assert error.identifier == 12345

    def test_entity_not_found_error_with_string_id(self):
        """Should handle string identifiers."""
        error = EntityNotFoundError("Guild", "test-guild-id")

        assert error.identifier == "test-guild-id"
        assert "test-guild-id" in str(error)

    def test_entity_not_found_error_with_int_id(self):
        """Should handle integer identifiers."""
        error = EntityNotFoundError("Session", 999)

        assert error.identifier == 999
        assert "999" in str(error)

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

    def test_concurrency_error_default_message(self):
        """Should generate default message for ConcurrencyError."""
        error = ConcurrencyError("PlaybackSession")

        assert "Concurrent modification" in str(error)
        assert "PlaybackSession" in str(error)
        assert error.entity_type == "PlaybackSession"
        assert error.code == "CONCURRENCY_ERROR"

    def test_concurrency_error_custom_message(self):
        """Should use custom message when provided."""
        error = ConcurrencyError(
            "VoteSession", message="Vote session was modified by another request"
        )

        assert str(error) == "Vote session was modified by another request"
        assert error.entity_type == "VoteSession"

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

    def test_exceptions_can_be_raised_and_caught(self):
        """Should be able to raise and catch exceptions."""
        with pytest.raises(ValidationError) as exc_info:
            raise ValidationError("Test error", field="test_field")

        assert exc_info.value.field == "test_field"

    def test_exception_inheritance(self):
        """All domain exceptions should inherit from DomainError."""
        assert issubclass(ValidationError, DomainError)
        assert issubclass(EntityNotFoundError, DomainError)
        assert issubclass(BusinessRuleViolationError, DomainError)
        assert issubclass(ConcurrencyError, DomainError)
        assert issubclass(InvalidOperationError, DomainError)

    def test_exceptions_are_exceptions(self):
        """All domain exceptions should inherit from Exception."""
        assert issubclass(DomainError, Exception)
        assert issubclass(ValidationError, Exception)
