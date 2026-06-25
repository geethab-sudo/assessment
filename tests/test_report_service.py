"""Participant feedback report (``services.report_service``).

Pure unit tests for topic aggregation. Mongo-backed ``build_report`` tests live
in ``test_mongodb_integration.py``.
"""

from __future__ import annotations

from services.report_service import aggregate_topic_summary


def test_aggregate_topic_summary_groups_and_averages():
    """Topics are grouped; empty topic_name becomes General; averages are computed."""
    questions = [
        {"topic_name": "OOP", "score": 90, "correct": True},
        {"topic_name": "OOP", "score": 80, "correct": True},
        {"topic_name": "Error Handling", "score": 50, "correct": False},
        {"topic_name": "", "score": 100, "correct": True},
    ]
    summary = aggregate_topic_summary(questions)
    assert len(summary) == 3
    by_name = {s["topic_name"]: s for s in summary}
    assert by_name["OOP"]["questions_count"] == 2
    assert by_name["OOP"]["correct_count"] == 2
    assert by_name["OOP"]["total_score"] == 2
    assert by_name["OOP"]["max_score"] == 2
    assert by_name["OOP"]["average_score"] == 85
    assert by_name["Error Handling"]["percent"] == 50
    assert by_name["General"]["questions_count"] == 1
