"""Tests for auto per-topic config and notebook expectation planning."""

from unittest.mock import patch

from services.notebook_plan_service import (
    derive_per_topic_config,
    expected_notebook_coding_from_config,
    notebook_plan_from_rows,
    validate_notebook_plan_after_generation,
)


def test_derive_per_topic_config_even_split():
    topics = ["A", "B", "C", "D"]
    cfg = derive_per_topic_config(
        topics,
        ["mcq", "coding"],
        {"mcq": 4, "coding": 4},
    )
    assert cfg == {
        "A": {"mcq": 1, "coding": 1},
        "B": {"mcq": 1, "coding": 1},
        "C": {"mcq": 1, "coding": 1},
        "D": {"mcq": 1, "coding": 1},
    }


def test_derive_per_topic_config_remainder():
    cfg = derive_per_topic_config(
        ["T1", "T2", "T3"],
        ["mcq"],
        {"mcq": 5},
    )
    assert cfg["T1"]["mcq"] == 2
    assert cfg["T2"]["mcq"] == 2
    assert cfg["T3"]["mcq"] == 1


def test_expected_notebook_coding_from_config():
    per_topic = {
        "Pyodide Topic": {"mcq": 1, "coding": 1},
        "Jupyter Topic": {"mcq": 1, "coding": 1},
    }
    assert (
        expected_notebook_coding_from_config(per_topic, ["Jupyter Topic"]) == 1
    )


@patch("services.notebook_plan_service.db_service.get_topic_modality_by_names")
def test_notebook_plan_no_jupyter_coding_expected(mock_modality):
    mock_modality.return_value = {
        "Jupyter Tier": "jupyter",
        "Pyodide": "pyodide",
    }
    rows = [
        {"type": "mcq", "topic_name": "Jupyter Tier", "question_id": "1"},
        {"type": "coding", "topic_name": "Pyodide", "question_id": "2"},
    ]
    plan = notebook_plan_from_rows(
        rows,
        topic_names=["Jupyter Tier", "Pyodide"],
        per_topic_config={
            "Jupyter Tier": {"mcq": 1},
            "Pyodide": {"coding": 1},
        },
        routing_flag="mixed",
    )
    assert plan["expected_notebook_coding_count"] == 0
    assert plan["notebook_expected"] is False
    assert plan["actual_notebook_coding_count"] == 0


@patch("services.notebook_plan_service.db_service.get_topic_modality_by_names")
def test_notebook_plan_jupyter_coding_tagged(mock_modality):
    mock_modality.return_value = {
        "Async IO": "jupyter",
        "Basics": "pyodide",
    }
    rows = [
        {"type": "coding", "topic_name": "Async IO", "question_id": "1"},
        {"type": "coding", "topic_name": "Basics", "question_id": "2"},
    ]
    plan = notebook_plan_from_rows(
        rows,
        topic_names=["Async IO", "Basics"],
        per_topic_config={
            "Async IO": {"coding": 1},
            "Basics": {"coding": 1},
        },
        routing_flag="mixed",
    )
    assert plan["expected_notebook_coding_count"] == 1
    assert plan["notebook_expected"] is True
    assert plan["actual_notebook_coding_count"] == 1
    assert plan["notebook_ready"] is True


def test_validate_fails_when_expected_but_no_actual():
    plan = {
        "expected_notebook_coding_count": 2,
        "actual_notebook_coding_count": 0,
    }
    try:
        validate_notebook_plan_after_generation(plan)
        raised = False
    except ValueError:
        raised = True
    assert raised


def test_validate_ok_when_no_notebook_expected():
    validate_notebook_plan_after_generation(
        {"expected_notebook_coding_count": 0, "actual_notebook_coding_count": 0}
    )
