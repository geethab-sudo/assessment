"""Unit tests for timed assessment attempt helpers."""

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
    def test_untimed(self) -> None:
        self.assertEqual(validate_timed_config(False, None, None), (None, None))

    def test_timed_defaults_grace(self) -> None:
        dur, grace = validate_timed_config(True, 45, None)
        self.assertEqual(dur, 45)
        self.assertEqual(grace, DEFAULT_NOTEBOOK_GRACE_MINUTES)

    def test_duration_minimum(self) -> None:
        dur, grace = validate_timed_config(True, 2, 5)
        self.assertEqual(dur, 2)
        self.assertEqual(grace, 5)
        with self.assertRaises(ValueError):
            validate_timed_config(True, 0, 5)
        with self.assertRaises(ValueError):
            validate_timed_config(True, -1, 5)


class TestNormalizeEmployeeId(unittest.TestCase):
    def test_casefold(self) -> None:
        self.assertEqual(normalize_employee_id("E1001"), "e1001")


class TestAssertMainSubmit(unittest.TestCase):
    @patch("services.attempt_service._get_attempt_row")
    @patch("services.attempt_service._utc_now")
    def test_allows_within_slack(self, mock_now, mock_row) -> None:
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
