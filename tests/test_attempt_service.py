"""Timed assessment attempt helpers (``services.attempt_service``).

Validates duration/grace configuration, employee ID normalization for attempt
rows, and the small post-deadline slack window allowed for main-form submit.
See TEST_GUIDE.md § Assessment generation and delivery.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from services.attempt_service import (
    DEFAULT_NOTEBOOK_GRACE_MINUTES,
    MAIN_SUBMIT_SLACK_SECONDS,
    TimedAssessmentError,
    normalize_employee_id,
    validate_timed_config,
)


class TestValidateTimedConfig(unittest.TestCase):
    """``validate_timed_config`` — timed vs untimed and duration bounds."""

    def test_untimed(self) -> None:
        """Untimed assessments return (None, None) for duration and grace."""
        self.assertEqual(validate_timed_config(False, None, None), (None, None))

    def test_timed_defaults_grace(self) -> None:
        """When grace is omitted, notebook grace defaults to the platform constant."""
        dur, grace = validate_timed_config(True, 45, None)
        self.assertEqual(dur, 45)
        self.assertEqual(grace, DEFAULT_NOTEBOOK_GRACE_MINUTES)

    def test_duration_minimum(self) -> None:
        """Duration must be at least 1 minute; zero or negative raises ValueError."""
        dur, grace = validate_timed_config(True, 2, 5)
        self.assertEqual(dur, 2)
        self.assertEqual(grace, 5)
        with self.assertRaises(ValueError):
            validate_timed_config(True, 0, 5)
        with self.assertRaises(ValueError):
            validate_timed_config(True, -1, 5)


class TestNormalizeEmployeeId(unittest.TestCase):
    """Employee IDs are stored and compared case-insensitively."""

    def test_casefold(self) -> None:
        """``E1001`` and ``e1001`` normalize to the same lookup key."""
        self.assertEqual(normalize_employee_id("E1001"), "e1001")


class TestAssertMainSubmit(unittest.TestCase):
    """``assert_main_submit_allowed`` — deadline enforcement with slack."""

    @patch("services.attempt_service._get_attempt_row")
    @patch("services.attempt_service._utc_now")
    def test_allows_within_slack(self, mock_now, mock_row) -> None:
        """Submit exactly at expires_at + MAIN_SUBMIT_SLACK_SECONDS is still allowed."""
        from services.attempt_service import assert_main_submit_allowed

        expires = datetime(2026, 5, 29, 12, 45, tzinfo=timezone.utc)
        mock_row.return_value = MagicMock(
            expires_at=expires.isoformat(),
            notebook_expires_at=(expires + timedelta(minutes=5)).isoformat(),
        )
        mock_now.return_value = expires + timedelta(seconds=MAIN_SUBMIT_SLACK_SECONDS)
        assert_main_submit_allowed("aid", "E1", is_timed=True)

    @patch("services.attempt_service._get_attempt_row")
    @patch("services.attempt_service._utc_now")
    def test_rejects_after_slack(self, mock_now, mock_row) -> None:
        """One second past the slack window raises TimedAssessmentError."""
        from services.attempt_service import assert_main_submit_allowed

        expires = datetime(2026, 5, 29, 12, 45, tzinfo=timezone.utc)
        mock_row.return_value = MagicMock(
            expires_at=expires.isoformat(),
            notebook_expires_at=(expires + timedelta(minutes=5)).isoformat(),
        )
        mock_now.return_value = expires + timedelta(seconds=MAIN_SUBMIT_SLACK_SECONDS + 1)
        with self.assertRaises(TimedAssessmentError):
            assert_main_submit_allowed("aid", "E1", is_timed=True)


if __name__ == "__main__":
    unittest.main()
