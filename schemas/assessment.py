"""Public assessment API request and response schemas."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AnswerItem(BaseModel):
    """A single answer keyed by question identifier."""

    question_id: str | int = Field(
        ...,
        description="Question identifier as returned in the assessment payload.",
        examples=["1"],
    )
    answer: str = Field(
        ...,
        description="Participant's answer text (MCQ option, code, or free text).",
        examples=["Option B"],
    )


class SubmitAssessmentBody(BaseModel):
    """Submit in-browser answers for grading."""

    assessment_id: str = Field(
        ...,
        description="Assessment id (ASM-XXXXXXXX for new assessments; legacy UUIDs still accepted).",
        examples=["ASM-A8DK2PQX"],
    )
    employee_id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Participant employee identifier (used for timed attempts and deduplication).",
        examples=["EMP-10042"],
    )
    participant_name: str = Field(
        ...,
        min_length=1,
        max_length=256,
        description="Display name of the participant.",
        examples=["Jane Doe"],
    )
    answers: list[AnswerItem] = Field(
        ...,
        min_length=1,
        description="One entry per answered question.",
    )

    @field_validator("assessment_id", "employee_id", "participant_name", mode="before")
    @classmethod
    def strip_participant_fields(cls, v: str) -> str:
        if isinstance(v, str):
            return v.strip()
        return v

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "assessment_id": "550e8400-e29b-41d4-a716-446655440000",
                    "employee_id": "EMP-10042",
                    "participant_name": "Jane Doe",
                    "answers": [
                        {"question_id": "1", "answer": "def add(a, b): return a + b"},
                        {"question_id": "2", "answer": "Option B"},
                    ],
                }
            ]
        }
    )


class SampleTestCaseOut(BaseModel):
    """Read-only sample input → output for self-validation (coding questions)."""

    input: str = ""
    expected_output: str = ""
    label: str | None = None


class QuestionOut(BaseModel):
    """A single assessment question (correct answers are never exposed)."""

    question_id: str | int = Field(..., description="Stable question identifier.")
    type: Literal["mcq", "coding", "subjective"] = Field(
        ..., description="Question format."
    )
    question: str = Field(..., description="Question stem (prose).")
    topic_name: str | None = Field(None, description="Catalog topic name, if any.")
    topic_modality: str | None = Field(
        None,
        description="Topic delivery modality (`pyodide`, `jupyter`, etc.).",
    )
    coding_editor_language: str | None = Field(
        None,
        description="Monaco editor language id for in-browser coding questions.",
    )
    options: list[Any] = Field(
        default_factory=list,
        description="MCQ options (empty for non-MCQ types).",
    )
    code: str | None = Field(
        None,
        description="Optional inline code snippet displayed with the question.",
    )
    sample_test_cases: list[SampleTestCaseOut] = Field(
        default_factory=list,
        description="Optional sample I/O examples for function/class coding tasks.",
    )
    coding_hint: str | None = Field(
        None,
        description="Optional beginner nudge for coding questions (never the full solution).",
    )

    @field_validator("coding_hint", mode="before")
    @classmethod
    def strip_coding_hint(cls, v: object) -> str | None:
        if v is None:
            return None
        s = str(v).strip()
        if s.lower().startswith("hint:"):
            s = s[5:].strip()
        return s or None


class TimerState(BaseModel):
    """Server-side timer state for timed assessments."""

    started_at: str = Field(..., description="ISO-8601 UTC timestamp when the attempt started.")
    expires_at: str = Field(
        ..., description="ISO-8601 UTC timestamp when the main submission window closes."
    )
    notebook_expires_at: str = Field(
        ...,
        description="ISO-8601 UTC timestamp when the notebook grace period ends.",
    )
    server_now: str = Field(..., description="Current server time (ISO-8601 UTC).")
    submitted_at: str | None = Field(
        None,
        description="ISO-8601 UTC timestamp of submission, or `null` if not yet submitted.",
    )


class AssessmentResponse(BaseModel):
    """Assessment metadata and questions for participants or admin preview."""

    assessment_id: str
    language_code: str | None = None
    routing_flag: str = Field(
        "pyodide",
        description="How coding questions are delivered (`pyodide` or `jupyter`).",
    )
    topic_names: list[str] = Field(default_factory=list)
    jupyter_topic_names: list[str] = Field(default_factory=list)
    is_timed: bool = False
    duration_minutes: int | None = None
    notebook_grace_minutes: int | None = None
    allow_pyodide_paste: bool = False
    notebook_expected: bool = False
    notebook_ready: bool = False
    expected_notebook_coding_count: int = 0
    actual_notebook_coding_count: int = 0
    already_submitted: bool = False
    timer: TimerState | None = None
    questions: list[QuestionOut] = Field(default_factory=list)
    found: bool = Field(..., description="`false` when the assessment id has no questions.")

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "assessment_id": "550e8400-e29b-41d4-a716-446655440000",
                    "language_code": "python",
                    "routing_flag": "pyodide",
                    "topic_names": ["Python Basics"],
                    "jupyter_topic_names": [],
                    "is_timed": False,
                    "duration_minutes": None,
                    "notebook_grace_minutes": None,
                    "notebook_expected": False,
                    "notebook_ready": False,
                    "expected_notebook_coding_count": 0,
                    "actual_notebook_coding_count": 0,
                    "already_submitted": False,
                    "timer": None,
                    "questions": [
                        {
                            "question_id": "1",
                            "type": "mcq",
                            "question": "What does `len([1, 2, 3])` return?",
                            "topic_name": "Python Basics",
                            "topic_modality": "pyodide",
                            "coding_editor_language": None,
                            "options": ["1", "2", "3"],
                        }
                    ],
                    "found": True,
                }
            ]
        }
    )


class QuestionResult(BaseModel):
    """Per-question grading outcome."""

    question_id: str
    score: float = Field(..., description="Score from 0.0 to 1.0.")
    feedback: str
    correct: bool


class SubmitAssessmentResponse(BaseModel):
    """Aggregated grading result after answer submission."""

    assessment_id: str
    user_id: str = Field(
        ...,
        description="Combined label `employee_id | participant_name`.",
    )
    score: float = Field(..., description="Average score across graded questions (0.0–1.0).")
    achieved_total: float = Field(
        ...,
        description="Sum of per-question scores on the 0.0–1.0 scale.",
    )
    max_total: float = Field(
        ...,
        description="Maximum achievable total (one point per graded question).",
    )
    feedback: str = Field(..., description="Newline-separated per-question feedback.")
    questions_graded: int
    question_results: list[QuestionResult]
    certificate_offer: dict[str, Any] | None = Field(
        None,
        description="Present when the participant qualifies for a Tier 1 certificate after submit.",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "assessment_id": "550e8400-e29b-41d4-a716-446655440000",
                    "user_id": "EMP-10042 | Jane Doe",
                    "score": 0.85,
                    "achieved_total": 1.7,
                    "max_total": 2.0,
                    "feedback": "Q1: Good solution.\nQ2: Correct option.",
                    "questions_graded": 2,
                    "question_results": [
                        {
                            "question_id": "1",
                            "score": 0.9,
                            "feedback": "Good solution.",
                            "correct": True,
                        },
                        {
                            "question_id": "2",
                            "score": 0.8,
                            "feedback": "Correct option.",
                            "correct": True,
                        },
                    ],
                }
            ]
        }
    )


class NotebookSubmitResponse(BaseModel):
    """Result of uploading a graded Jupyter notebook."""

    assessment_id: str
    user_id: str = Field(
        ...,
        description="Participant label (typically `employee_id | name`).",
    )
    code: str = Field(..., description="Concatenated code cells from the notebook.")
    outputs: str = Field(..., description="Concatenated cell outputs.")
    metadata: dict[str, Any] = Field(default_factory=dict)
    score: float = Field(..., description="Average score across code cells (0.0–1.0).")
    feedback: str

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "assessment_id": "550e8400-e29b-41d4-a716-446655440000",
                    "user_id": "EMP-10042 | Jane Doe",
                    "code": "def solve():\n    return 42",
                    "outputs": "42",
                    "metadata": {},
                    "score": 0.75,
                    "feedback": "Q1: Partial credit.\nQ2: Well done.",
                }
            ]
        }
    )
