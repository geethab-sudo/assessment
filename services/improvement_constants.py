"""Shared limits and thresholds for client improvement flows (Stage 12)."""

from __future__ import annotations

import os

DEFAULT_QUESTIONS_REQUESTED = 15
MIN_QUESTIONS_REQUESTED = 1
MAX_QUESTIONS_REQUESTED = 15
MAX_QUESTIONS_PER_TOPIC = 5
MAX_TOPICS_PER_SESSION = 5
DEFAULT_QUICK_PRACTICE_QUESTIONS = 10

PROFICIENCY_THRESHOLD_PERCENT = float(
    os.environ.get("FOCUS_TOPIC_PERCENT_THRESHOLD", "75")
)
