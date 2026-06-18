"""Pydantic models for employee profile and stats report (Stage 4)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class TopicPerformanceItem(BaseModel):
    topic_name: str
    questions_count: int
    average_percent: float
    attempts: int = Field(..., description="Distinct assessments that included this topic.")
    last_difficulty: str | None = None
    trend: Literal["up", "down", "flat"] | None = None
    sparkline: list[float] = Field(default_factory=list)


class EmployeeProfileResponse(BaseModel):
    employee_id: str
    scope: Literal["last_3", "full_history"]
    assessments_analyzed: int
    language_code: str | None = None
    topic_performance: list[TopicPerformanceItem] = Field(default_factory=list)
    explored_topic_names: list[str] = Field(default_factory=list)
    unexplored_topic_names: list[str] = Field(default_factory=list)
    weakest_topics: list[str] = Field(default_factory=list)
    recommended_difficulty_by_topic: dict[str, str] = Field(default_factory=dict)


class ReportSummary(BaseModel):
    assessments_completed: int
    questions_answered: int
    overall_percent_correct: float
    assessed_level_label: str = Field(
        default="Beginner",
        description="Highest difficulty tier the employee has been assessed at.",
    )
    proficiency_label: str = Field(
        ...,
        description="Progress message within assessed_level (not the next tier).",
    )
    total_time_seconds: int
    avg_assessment_time_seconds: int


class ReportLanguageTopicItem(BaseModel):
    topic_name: str
    questions_count: int
    mastered_count: int
    percent_correct: float
    last_difficulty: str | None = None
    trend: Literal["up", "down", "flat"] | None = None
    sparkline: list[float] = Field(default_factory=list)


class ReportLanguageSection(BaseModel):
    language_code: str
    language_label: str
    topics_covered: int
    topics_in_catalog: int
    questions_count: int
    percent_correct: float
    assessed_level_label: str = "Beginner"
    proficiency_label: str
    topics: list[ReportLanguageTopicItem] = Field(default_factory=list)


class ScoreTimelineItem(BaseModel):
    assessment_id: str
    submitted_at: str
    percent: float
    language_code: str | None = None


class QuestionTypeBreakdownItem(BaseModel):
    count: int
    percent_correct: float


class ReportMasterySection(BaseModel):
    mastered_count: int
    needs_practice_count: int


class ReportInsights(BaseModel):
    strengths: list[str] = Field(default_factory=list)
    focus_areas: list[str] = Field(default_factory=list)
    unexplored_topics: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class RadarTopicItem(BaseModel):
    topic_name: str
    latest_percent: float
    rolling_avg_percent: float


class WeakAreasImprovementRequest(BaseModel):
    employee_id: str = Field(..., min_length=1, max_length=64)
    language_code: str = Field(..., min_length=1, max_length=32)
    questions_requested: int = Field(default=15, ge=1, le=50)


class WeakAreasImprovementResponse(BaseModel):
    employee_id: str
    language_code: str
    questions_requested: int
    questions_delivered: int
    assessment_id: str | None = None
    availability_message: str | None = None
    topic_summary: str | None = None
    weak_topics: list[str] = Field(default_factory=list)


class NewAreasImprovementRequest(BaseModel):
    employee_id: str = Field(..., min_length=1, max_length=64)
    language_code: str = Field(..., min_length=1, max_length=32)
    questions_requested: int = Field(default=15, ge=1, le=50)
    topics_count: int = Field(
        default=5,
        ge=1,
        le=10,
        description="How many unexplored topics to include (higher tiers preferred).",
    )


class NewAreasImprovementResponse(BaseModel):
    employee_id: str
    language_code: str
    questions_requested: int
    questions_delivered: int
    assessment_id: str | None = None
    availability_message: str | None = None
    topic_summary: str | None = None
    selected_topics: list[str] = Field(default_factory=list)


class EmployeeReportResponse(BaseModel):
    title: str = "Skills Progress Report"
    report_version: str = "1.0"
    employee_id: str
    display_name: str = ""
    period: Literal["all_time", "last_90_days"]
    report_generated_at: str
    scope: Literal["full_history"] = "full_history"
    summary: ReportSummary
    languages: list[ReportLanguageSection] = Field(default_factory=list)
    score_timeline: list[ScoreTimelineItem] = Field(default_factory=list)
    question_type_breakdown: dict[str, QuestionTypeBreakdownItem] = Field(
        default_factory=dict
    )
    mastery: ReportMasterySection
    insights: ReportInsights
    radar_topics: list[RadarTopicItem] = Field(default_factory=list)
    cumulative_progress: list[dict[str, int | str]] = Field(
        default_factory=list,
        description="Cumulative correct/wrong counts keyed by submitted_at.",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "title": "Skills Progress Report",
                    "report_version": "1.0",
                    "employee_id": "E1001",
                    "display_name": "Test User",
                    "period": "all_time",
                    "report_generated_at": "2026-06-15T12:00:00Z",
                    "summary": {
                        "assessments_completed": 2,
                        "questions_answered": 10,
                        "overall_percent_correct": 72.0,
                        "proficiency_label": "Intermediate",
                        "total_time_seconds": 2400,
                        "avg_assessment_time_seconds": 1200,
                    },
                    "mastery": {"mastered_count": 3, "needs_practice_count": 1},
                    "insights": {
                        "strengths": ["OOP Basics"],
                        "focus_areas": ["Exception Handling"],
                        "unexplored_topics": ["Concurrency"],
                        "recommendations": [],
                    },
                }
            ]
        }
    )
