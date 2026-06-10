"""Tests for participant feedback report building."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from services.report_service import aggregate_topic_summary, build_report


def test_aggregate_topic_summary_groups_and_averages():
    questions = [
        {"topic_name": "OOP", "score": 90},
        {"topic_name": "OOP", "score": 80},
        {"topic_name": "Error Handling", "score": 50},
        {"topic_name": "", "score": 100},
    ]
    summary = aggregate_topic_summary(questions)
    assert len(summary) == 3
    by_name = {s["topic_name"]: s for s in summary}
    assert by_name["OOP"]["questions_count"] == 2
    assert by_name["OOP"]["total_score"] == 170
    assert by_name["OOP"]["max_score"] == 200
    assert by_name["OOP"]["average_score"] == 85
    assert by_name["Error Handling"]["percent"] == 50
    assert by_name["General"]["questions_count"] == 1


@patch("services.report_service.db_service.get_topic_modality_by_names")
@patch("services.report_service.db_service.get_participant_in_browser_submissions")
@patch("services.report_service.db_service.read_questions_by_assessment")
@patch("services.report_service.db_service.get_assessment_metadata")
def test_build_report_joins_submissions_and_skips_jupyter_coding(
    mock_meta,
    mock_read_questions,
    mock_submissions,
    mock_modality,
):
    mock_meta.return_value = {"jupyter_topic_names": ["Live API"]}
    mock_modality.return_value = {"Live API": "jupyter", "OOP": "pyodide"}
    mock_read_questions.return_value = [
        {
            "question_id": "1",
            "question": "What is a class?",
            "type": "mcq",
            "options": '["A","B"]',
            "correct_answer": "A",
            "topic_name": "OOP",
            "code_snippet": "",
        },
        {
            "question_id": "2",
            "question": "Write a function",
            "type": "coding",
            "options": "",
            "correct_answer": "",
            "topic_name": "Live API",
            "code_snippet": "",
        },
        {
            "question_id": "3",
            "question": "Print hello",
            "type": "coding",
            "options": "",
            "correct_answer": "",
            "topic_name": "OOP",
            "code_snippet": "",
        },
    ]
    mock_submissions.return_value = [
        {
            "user_id": "E1001 | Jane Doe",
            "question_id": "1",
            "user_answer": "A",
            "score": "100",
            "feedback": "Correct.",
            "timestamp": "2026-06-08T10:00:00+00:00",
            "routing_flag": "pyodide",
        },
        {
            "user_id": "E1001 | Jane Doe",
            "question_id": "2",
            "user_answer": "import requests",
            "score": "40",
            "feedback": "Partial.",
            "timestamp": "2026-06-08T10:00:01+00:00",
            "routing_flag": "pyodide",
        },
        {
            "user_id": "E1001 | Jane Doe",
            "question_id": "3",
            "user_answer": "print('hi')",
            "score": "80",
            "feedback": "Good.",
            "timestamp": "2026-06-08T10:00:02+00:00",
            "routing_flag": "pyodide",
        },
    ]

    report = build_report("aid-1", "E1001")

    assert report["participant"]["employee_id"] == "E1001"
    assert report["participant"]["name"] == "Jane Doe"
    assert report["overall_score"] == 90.0
    assert report["questions_graded"] == 2
    assert [q["question_id"] for q in report["questions"]] == ["1", "3"]
    assert report["topic_summary"][0]["topic_name"] == "OOP"
    assert report["report_scope"] == "in_browser"


@patch("services.report_service.db_service.get_participant_in_browser_submissions")
@patch("services.report_service.db_service.read_questions_by_assessment")
@patch("services.report_service.db_service.get_assessment_metadata")
def test_build_report_raises_when_no_submission(
    mock_meta,
    mock_read_questions,
    mock_submissions,
):
    mock_meta.return_value = {"jupyter_topic_names": []}
    mock_read_questions.return_value = [{"question_id": "1", "type": "mcq", "question": "Q"}]
    mock_submissions.return_value = []

    with pytest.raises(ValueError, match="No submission found"):
        build_report("aid-1", "E999")
