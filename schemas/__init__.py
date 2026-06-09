"""Pydantic schemas for API request/response bodies and OpenAPI documentation."""

from schemas.admin import (
    AssessmentsListResponse,
    GenerateAssessmentBody,
    GenerateAssessmentResponse,
    LanguageCreateBody,
    SubmissionsListResponse,
    TopicCreateBody,
)
from schemas.assessment import (
    AssessmentResponse,
    NotebookSubmitResponse,
    SubmitAssessmentBody,
    SubmitAssessmentResponse,
)
from schemas.auth import ClientLoginResponse, LoginBody, LoginResponse
from schemas.catalog import LanguagesResponse, LanguageResponse, TopicResponse, TopicsResponse
from schemas.common import ErrorDetail, HealthResponse, OkDeletedResponse, ValidationErrorResponse

__all__ = [
    "AssessmentResponse",
    "AssessmentsListResponse",
    "ClientLoginResponse",
    "ErrorDetail",
    "GenerateAssessmentBody",
    "GenerateAssessmentResponse",
    "HealthResponse",
    "LanguageCreateBody",
    "LanguageResponse",
    "LanguagesResponse",
    "LoginBody",
    "LoginResponse",
    "NotebookSubmitResponse",
    "OkDeletedResponse",
    "SubmissionsListResponse",
    "SubmitAssessmentBody",
    "SubmitAssessmentResponse",
    "TopicCreateBody",
    "TopicResponse",
    "TopicsResponse",
    "ValidationErrorResponse",
]
