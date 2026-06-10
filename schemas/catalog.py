"""Catalog (languages and topics) response schemas."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class LanguageOut(BaseModel):
    """A programming language in the reference catalog."""

    id: int = Field(..., description="Primary key.")
    code: str = Field(..., description="Short language code (e.g. `python`).", max_length=32)
    name: str = Field(..., description="Display name.", max_length=128)


class LanguagesResponse(BaseModel):
    """List of catalog languages."""

    languages: list[LanguageOut]

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "languages": [
                        {"id": 1, "code": "python", "name": "Python"},
                        {"id": 2, "code": "javascript", "name": "JavaScript"},
                    ]
                }
            ]
        }
    )


class LanguageResponse(BaseModel):
    """Single language create/update response."""

    language: LanguageOut

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"language": {"id": 1, "code": "python", "name": "Python"}}]
        }
    )


class RelatedDocumentOut(BaseModel):
    """Reference document attached to a catalog topic."""

    title: str = Field(..., max_length=512)
    url: str | None = Field(None, max_length=2048)
    path: str | None = Field(None, max_length=2048)


class TopicOut(BaseModel):
    """A topic under a catalog language."""

    id: int
    language_id: int = Field(..., ge=1, description="Foreign key to `languages.id`.")
    name: str = Field(..., max_length=256)
    related_documents: list[RelatedDocumentOut] = Field(default_factory=list)


class TopicsResponse(BaseModel):
    """List of catalog topics, optionally filtered by language."""

    topics: list[TopicOut]

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "topics": [
                        {
                            "id": 10,
                            "language_id": 1,
                            "name": "Python Basics",
                            "related_documents": [
                                {"title": "Official docs", "url": "https://docs.python.org"}
                            ],
                        }
                    ]
                }
            ]
        }
    )


class TopicResponse(BaseModel):
    """Single topic create/update response."""

    topic: TopicOut

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "topic": {
                        "id": 10,
                        "language_id": 1,
                        "name": "Python Basics",
                        "related_documents": [],
                    }
                }
            ]
        }
    )
