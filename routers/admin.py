"""Admin API routes — GET is public; mutating routes require admin JWT."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response
from fastapi.responses import FileResponse

from openapi_config import ERROR_503, admin_crud_errors, auth_error_responses
from routers.deps import require_admin
from schemas.admin import (
    AssessmentsListResponse,
    ConfirmAssessmentBody,
    GenerateAssessmentBody,
    GenerateAssessmentResponse,
    LanguageCreateBody,
    PatchQuestionBody,
    SubmissionsListResponse,
    TopicCreateBody,
    QuestionBankListResponse,
    BankAvailabilityResponse,
)
from schemas.assessment import AssessmentResponse
from schemas.certificate import AdminIssueCertificateBody
from schemas.certificate import (
    CertificateIssuerSettingsBody,
    CertificateIssuerSettingsResponse,
)
from schemas.certificate_layout import (
    CertificateLayoutSavedResponse,
    CertificateTemplateListResponse,
    CertificateTemplateItem,
    CertificateTemplatePreviewBody,
    TemplateLayoutBody,
)
from schemas.catalog import LanguageResponse, LanguagesResponse, TopicResponse, TopicsResponse
from schemas.common import OkDeletedResponse
from schemas.improvement import EmployeeReportResponse
from services import assessment_service, audit_log, catalog_service, db_service, question_bank_service
from services import certificate_service, employee_profile_service
from services import platform_settings_service

admin_router = APIRouter(
    prefix="/admin",
    tags=["admin"],
)

# Admin-only routes that live outside the /admin prefix (legacy path).
admin_ops_router = APIRouter(
    tags=["admin"],
)


@admin_router.get(
    "/question-bank",
    summary="Browse question bank",
    response_model=QuestionBankListResponse,
    responses={
        200: {"description": "List of all questions in the bank with stats."},
        **admin_crud_errors(include_404=False, include_auth=False),
    },
)
def admin_get_question_bank(
    topic_name: str | None = None,
    difficulty: str | None = None,
    language_code: str | None = None,
    question_type: str | None = None,
) -> QuestionBankListResponse:
    """Browse the reusable question bank."""
    rows = question_bank_service.get_bank_stats(
        topic_name=topic_name,
        difficulty=difficulty,
        language_code=language_code,
        question_type=question_type,
    )
    return QuestionBankListResponse(questions=rows)


@admin_router.get(
    "/question-bank/availability",
    summary="Check reusable question availability",
    response_model=BankAvailabilityResponse,
    responses={
        200: {"description": "Availability metrics per topic and total shortage."},
        **admin_crud_errors(include_404=False, include_auth=False),
    },
)
def admin_get_bank_availability(
    topic_names: list[str] = Query(...),
    difficulty: str = Query(...),
    n_requested: int = Query(...),
    exclude_employee_id: str | None = None,
) -> BankAvailabilityResponse:
    """Check how many questions are available in the bank before generating."""
    data = question_bank_service.get_bank_availability(
        topic_names=topic_names,
        difficulty=difficulty,
        n_requested=n_requested,
        exclude_employee_id=exclude_employee_id,
    )
    return BankAvailabilityResponse(**data)


@admin_router.get(
    "/assessments",
    summary="List all assessments",
    response_model=AssessmentsListResponse,
    responses={
        200: {"description": "Assessment summaries ordered by creation date (newest first)."},
        **admin_crud_errors(include_404=False, include_auth=False),
    },
)
def admin_list_assessments() -> AssessmentsListResponse:
    """Return metadata for every assessment (shared and client-scoped)."""
    return AssessmentsListResponse(assessments=db_service.list_assessments_summary())


@admin_router.get(
    "/assessment/{assessment_id}",
    summary="Preview assessment questions",
    response_model=AssessmentResponse,
    responses={
        200: {"description": "Same shape as the public participant view (no correct answers)."},
        **admin_crud_errors(include_auth=False),
    },
)
def admin_get_assessment_preview(
    assessment_id: Annotated[
        str,
        Path(
            description="UUID of the assessment to preview.",
            examples=["550e8400-e29b-41d4-a716-446655440000"],
        ),
    ],
) -> AssessmentResponse:
    """
    Load questions for admin preview before sharing with participants.

    Does not require `employee_id`; questions are in canonical (unshuffled) order.
    """
    aid = assessment_id.strip()
    data = assessment_service.get_assessment_for_user(aid)
    if not data.get("found"):
        raise HTTPException(status_code=404, detail="Assessment not found")
    return AssessmentResponse.model_validate(data)


@admin_router.delete(
    "/assessments/{assessment_id}",
    summary="Delete an assessment",
    response_model=OkDeletedResponse,
    dependencies=[Depends(require_admin)],
    responses={
        200: {"description": "Assessment, its questions, and all submissions removed."},
        **admin_crud_errors(),
    },
)
def admin_delete_assessment(
    request: Request,
    assessment_id: Annotated[
        str,
        Path(
            description="UUID of the assessment to delete.",
            examples=["550e8400-e29b-41d4-a716-446655440000"],
        ),
    ],
) -> OkDeletedResponse:
    """
    Permanently delete an assessment and all related questions, attempts, and submissions.

    This action cannot be undone.
    """
    aid = assessment_id.strip()
    if not aid:
        raise HTTPException(status_code=400, detail="Assessment ID is required")
    try:
        db_service.delete_assessment(aid)
    except ValueError as e:
        msg = str(e)
        status = 404 if msg == "Assessment not found" else 400
        raise HTTPException(status_code=status, detail=msg) from e
    audit_log.admin_action(
        request,
        action="assessment.delete",
        resource="assessment",
        resource_id=aid,
    )
    return OkDeletedResponse(ok=True, deleted=aid)


@admin_router.get(
    "/submissions",
    summary="List all submissions",
    response_model=SubmissionsListResponse,
    responses={
        200: {"description": "All graded answer rows, newest first."},
        **admin_crud_errors(include_404=False, include_auth=False),
    },
)
def admin_list_submissions() -> SubmissionsListResponse:
    """
    Return every submission row across all assessments for the admin submissions dashboard.
    """
    return SubmissionsListResponse(submissions=db_service.list_all_submissions())


@admin_router.get(
    "/languages",
    summary="List catalog languages",
    response_model=LanguagesResponse,
    responses={
        200: {"description": "All languages in the reference catalog."},
        **admin_crud_errors(include_404=False, include_auth=False),
    },
)
def admin_list_languages() -> LanguagesResponse:
    """List programming languages available when generating assessments."""
    return LanguagesResponse(languages=catalog_service.list_languages())


@admin_router.post(
    "/languages",
    summary="Create catalog language",
    response_model=LanguageResponse,
    status_code=200,
    dependencies=[Depends(require_admin)],
    responses={
        200: {"description": "Language created."},
        **admin_crud_errors(include_404=False),
    },
)
def admin_create_language(request: Request, body: LanguageCreateBody) -> LanguageResponse:
    """
    Add a new language to the catalog.

    **Validation**: `code` must be unique (HTTP 400 if duplicate).
    """
    try:
        result = LanguageResponse(
            language=catalog_service.create_language(code=body.code, name=body.name)
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    audit_log.admin_action(
        request,
        action="catalog.language.create",
        resource="language",
        resource_id=result.language.id,
    )
    return result


@admin_router.put(
    "/languages/{language_id}",
    summary="Update catalog language",
    response_model=LanguageResponse,
    dependencies=[Depends(require_admin)],
    responses={
        200: {"description": "Language updated."},
        **admin_crud_errors(),
    },
)
def admin_update_language(
    request: Request,
    language_id: Annotated[
        int,
        Path(description="Primary key of the language row.", examples=[1], ge=1),
    ],
    body: LanguageCreateBody,
) -> LanguageResponse:
    """
    Update an existing catalog language's `code` and `name`.

    Returns HTTP 404 if `language_id` does not exist.
    """
    try:
        result = LanguageResponse(
            language=catalog_service.update_language(
                language_id=language_id, code=body.code, name=body.name
            )
        )
    except ValueError as e:
        msg = str(e)
        status = 404 if msg == "Language not found" else 400
        raise HTTPException(status_code=status, detail=msg) from e
    audit_log.admin_action(
        request,
        action="catalog.language.update",
        resource="language",
        resource_id=language_id,
    )
    return result


@admin_router.get(
    "/topics",
    summary="List catalog topics",
    response_model=TopicsResponse,
    responses={
        200: {"description": "Topics, optionally filtered by `language_id`."},
        **admin_crud_errors(include_404=False, include_auth=False),
    },
)
def admin_list_topics(
    language_id: Annotated[
        int | None,
        Query(
            description="When set, return only topics for this language id.",
            examples=[1],
            ge=1,
        ),
    ] = None,
) -> TopicsResponse:
    """List catalog topics used when configuring assessment generation."""
    return TopicsResponse(topics=catalog_service.list_topics(language_id=language_id))


@admin_router.post(
    "/topics",
    summary="Create catalog topic",
    response_model=TopicResponse,
    dependencies=[Depends(require_admin)],
    responses={
        200: {"description": "Topic created."},
        **admin_crud_errors(include_404=False),
    },
)
def admin_create_topic(request: Request, body: TopicCreateBody) -> TopicResponse:
    """
    Add a topic under a catalog language.

    **Validation**: `language_id` must exist; topic name must be unique per language.
    """
    try:
        docs = [d.model_dump(exclude_none=True) for d in body.related_documents]
        result = TopicResponse(
            topic=catalog_service.create_topic(
                language_id=body.language_id,
                name=body.name,
                related_documents=docs,
            )
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    audit_log.admin_action(
        request,
        action="catalog.topic.create",
        resource="topic",
        resource_id=result.topic.id,
    )
    return result


@admin_router.put(
    "/topics/{topic_id}",
    summary="Update catalog topic",
    response_model=TopicResponse,
    dependencies=[Depends(require_admin)],
    responses={
        200: {"description": "Topic updated."},
        **admin_crud_errors(),
    },
)
def admin_update_topic(
    request: Request,
    topic_id: Annotated[
        int,
        Path(description="Primary key of the topic row.", examples=[10], ge=1),
    ],
    body: TopicCreateBody,
) -> TopicResponse:
    """Update topic name, language, and related documents."""
    try:
        docs = [d.model_dump(exclude_none=True) for d in body.related_documents]
        result = TopicResponse(
            topic=catalog_service.update_topic(
                topic_id=topic_id,
                language_id=body.language_id,
                name=body.name,
                related_documents=docs,
            )
        )
    except ValueError as e:
        msg = str(e)
        status = 404 if msg == "Topic not found" else 400
        raise HTTPException(status_code=status, detail=msg) from e
    audit_log.admin_action(
        request,
        action="catalog.topic.update",
        resource="topic",
        resource_id=topic_id,
    )
    return result


@admin_router.delete(
    "/topics/{topic_id}",
    summary="Delete catalog topic",
    response_model=OkDeletedResponse,
    dependencies=[Depends(require_admin)],
    responses={
        200: {"description": "Topic removed from the catalog."},
        **admin_crud_errors(),
    },
)
def admin_delete_topic(
    request: Request,
    topic_id: Annotated[
        int,
        Path(description="Primary key of the topic to delete.", examples=[10], ge=1),
    ],
) -> OkDeletedResponse:
    """Delete a catalog topic by id. Returns HTTP 404 if not found."""
    try:
        catalog_service.delete_topic(topic_id=topic_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    audit_log.admin_action(
        request,
        action="catalog.topic.delete",
        resource="topic",
        resource_id=topic_id,
    )
    return OkDeletedResponse(ok=True, deleted=topic_id)


@admin_ops_router.post(
    "/generate-assessment",
    summary="Generate assessment via LLM",
    response_model=GenerateAssessmentResponse,
    dependencies=[Depends(require_admin)],
    responses={
        200: {"description": "Questions generated and persisted; returns new `assessment_id`."},
        400: admin_crud_errors(include_404=False)[400],
        401: auth_error_responses()[401],
        403: auth_error_responses(include_403=True)[403],
        422: admin_crud_errors(include_404=False)[422],
        500: admin_crud_errors(include_404=False)[500],
        503: ERROR_503,
    },
)
def generate_assessment(
    request: Request,
    body: GenerateAssessmentBody,
) -> GenerateAssessmentResponse:
    """
    Generate assessment questions with the LLM and persist them as a **shared** assessment.

    **Authentication**: admin JWT required.

    **Validation highlights**:
    - `level`: `beginner`, `intermediate`, or `advanced`
    - `types`: subset of `mcq`, `coding`, `subjective`
    - `questions_per_type`: keys must match `types`; counts 1–30 each
    - `is_timed`: when `true`, `duration_minutes` is required

    Returns HTTP 503 when the selected generation provider API key is not configured.
    """
    try:
        result = assessment_service.create_assessment(
            topic=body.topic.strip(),
            level=body.level,
            types=body.types,
            questions_per_type=body.questions_per_type,
            language_code=body.language_code,
            language_label=body.language_label,
            topic_names=body.topic_names,
            per_topic_config=body.per_topic_config or {},
            is_timed=body.is_timed,
            duration_minutes=body.duration_minutes,
            notebook_grace_minutes=body.notebook_grace_minutes,
            question_source=body.question_source,
            target_employee_id=body.target_employee_id,
            allow_pyodide_paste=body.allow_pyodide_paste,
            include_sample_test_cases=body.include_sample_test_cases,
            include_beginner_coding_hints=body.include_beginner_coding_hints,
            generation_provider=body.generation_provider,
        )
        response = GenerateAssessmentResponse.model_validate(result)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Generation failed: {e}") from e
    audit_log.admin_action(
        request,
        action="assessment.generate",
        resource="assessment",
        resource_id=response.assessment_id,
    )
    return response


@admin_router.post(
    "/preview-questions",
    summary="Generate questions for admin review",
    dependencies=[Depends(require_admin)],
    responses={
        200: {"description": "LLM-generated questions with correct answers for review."},
        **admin_crud_errors(include_404=False),
        503: ERROR_503,
    },
)
def preview_questions(request: Request, body: GenerateAssessmentBody) -> dict:
    """
    Generate questions via LLM without persisting. Returns correct answers for review.

    Call ``POST /admin/confirm-assessment`` to save after editing.
    """
    try:
        return assessment_service.preview_questions(
            topic=body.topic.strip(),
            level=body.level,
            types=body.types,
            questions_per_type=body.questions_per_type,
            topic_names=body.topic_names,
            per_topic_config=body.per_topic_config or {},
            question_source=body.question_source,
            target_employee_id=body.target_employee_id,
            include_sample_test_cases=body.include_sample_test_cases,
            include_beginner_coding_hints=body.include_beginner_coding_hints,
            generation_provider=body.generation_provider,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Preview generation failed: {e}") from e


@admin_router.post(
    "/confirm-assessment",
    summary="Persist reviewed assessment questions",
    response_model=GenerateAssessmentResponse,
    dependencies=[Depends(require_admin)],
    responses={
        200: {"description": "Reviewed questions saved as a new assessment."},
        **admin_crud_errors(include_404=False),
        503: ERROR_503,
    },
)
def confirm_assessment(request: Request, body: ConfirmAssessmentBody) -> GenerateAssessmentResponse:
    """Persist the reviewed (and possibly edited) question list to the database."""
    try:
        questions = [q.model_dump() for q in body.questions]
        result = assessment_service.confirm_assessment(
            questions,
            topic=body.topic.strip(),
            level=body.level,
            language_code=body.language_code,
            language_label=body.language_label,
            topic_names=body.topic_names,
            per_topic_config=body.per_topic_config or {},
            is_timed=body.is_timed,
            duration_minutes=body.duration_minutes,
            notebook_grace_minutes=body.notebook_grace_minutes,
            allow_pyodide_paste=body.allow_pyodide_paste,
            certificate_enabled=body.certificate_enabled,
            certificate_level=body.level if body.certificate_enabled else None,
        )
        response = GenerateAssessmentResponse.model_validate(result)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Confirm failed: {e}") from e
    audit_log.admin_action(
        request,
        action="assessment.confirm",
        resource="assessment",
        resource_id=response.assessment_id,
    )
    return response


@admin_router.get(
    "/employee-report",
    summary="Employee skills progress report",
    response_model=EmployeeReportResponse,
    dependencies=[Depends(require_admin)],
    responses={
        200: {"description": "Full cross-assessment stats report for one employee."},
        **admin_crud_errors(include_404=False),
    },
)
def admin_employee_report(
    employee_id: Annotated[
        str,
        Query(min_length=1, max_length=64, description="Participant employee id."),
    ],
    period: Annotated[
        str,
        Query(description="`all_time` or `last_90_days`."),
    ] = "all_time",
    language_code: Annotated[
        str | None,
        Query(max_length=32, description="Optional catalog language code filter."),
    ] = None,
) -> EmployeeReportResponse:
    """Admin view of the shippable employee stats report."""
    period_norm = period.strip().lower()
    if period_norm not in ("all_time", "last_90_days"):
        raise HTTPException(
            status_code=400,
            detail="period must be all_time or last_90_days",
        )
    try:
        data = employee_profile_service.get_employee_report(
            employee_id.strip(),
            language_code=language_code,
            period=period_norm,  # type: ignore[arg-type]
        )
        return EmployeeReportResponse.model_validate(data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@admin_router.patch(
    "/assessment/{assessment_id}/question/{question_id}",
    summary="Update a single saved question",
    dependencies=[Depends(require_admin)],
    responses={
        200: {"description": "Question updated."},
        **admin_crud_errors(),
    },
)
def patch_assessment_question(
    assessment_id: Annotated[str, Path(description="UUID of the assessment.")],
    question_id: Annotated[str, Path(description="Question id within the assessment.")],
    body: PatchQuestionBody,
) -> dict:
    """Post-hoc correction of one question on an already-saved assessment."""
    import json

    from services.ids import normalize_assessment_id

    try:
        aid = normalize_assessment_id(assessment_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid assessment ID format") from None

    options_str: str | None = None
    if body.options is not None:
        options_str = json.dumps(body.options, ensure_ascii=False)
    updated = db_service.update_assessment_question(
        aid,
        question_id.strip(),
        question=body.question,
        code_snippet=body.code_snippet,
        options=options_str,
        correct_answer=body.correct_answer,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Question not found")
    return {"ok": True, "assessment_id": aid, "question_id": question_id.strip()}


@admin_router.get(
    "/certificate/issuer-settings",
    summary="Certificate issuer organization and verification copy",
    description="Return the issuing organization name and verification page intro shown on LinkedIn and public verify URLs.",
    response_model=CertificateIssuerSettingsResponse,
    dependencies=[Depends(require_admin)],
)
def get_certificate_issuer_settings() -> CertificateIssuerSettingsResponse:
    data = platform_settings_service.get_certificate_issuer_settings()
    return CertificateIssuerSettingsResponse.model_validate(data)


@admin_router.put(
    "/certificate/issuer-settings",
    summary="Save certificate issuer organization and verification copy",
    description="Update the issuing organization name (LinkedIn Issuing organization field) and verification page intro text.",
    response_model=CertificateIssuerSettingsResponse,
    dependencies=[Depends(require_admin)],
)
def save_certificate_issuer_settings(
    request: Request,
    body: CertificateIssuerSettingsBody,
) -> CertificateIssuerSettingsResponse:
    try:
        data = platform_settings_service.save_certificate_issuer_settings(
            organization_name=body.organization_name,
            verification_intro=body.verification_intro,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    audit_log.admin_action(
        request,
        action="certificate.issuer.save",
        resource="platform_settings",
        resource_id="certificate_issuer",
    )
    return CertificateIssuerSettingsResponse.model_validate(data)


@admin_router.get(
    "/certificate/templates",
    summary="List certificate templates and calibration status",
    description="Return JPG certificate templates, calibration flags, and mapped difficulty levels.",
    response_model=CertificateTemplateListResponse,
    dependencies=[Depends(require_admin)],
)
def list_certificate_templates() -> CertificateTemplateListResponse:
    items = certificate_service.list_certificate_templates()
    sig = certificate_service.signature_path()
    layout = certificate_service.load_layout()
    templates = []
    for t in items:
        layout_body = None
        if t.layout:
            try:
                from schemas.certificate_layout import TemplateLayoutBody

                layout_body = TemplateLayoutBody.model_validate(t.layout)
            except Exception:
                layout_body = None
        templates.append(
            CertificateTemplateItem(
                filename=t.filename,
                width=t.width,
                height=t.height,
                calibrated=t.calibrated,
                levels=t.levels,
                layout=layout_body,
            )
        )
    uncalibrated = sum(1 for t in templates if not t.calibrated)
    return CertificateTemplateListResponse(
        templates=templates,
        uncalibrated_count=uncalibrated,
        signature_file=str(layout.get("signature_file") or "signature.png"),
        signature_present=sig.is_file(),
    )


@admin_router.get(
    "/certificate/templates/{filename}/background",
    summary="Certificate template background image (for layout editor)",
    description="Serve the raw template image for the admin layout calibration UI.",
    dependencies=[Depends(require_admin)],
    responses={404: {"description": "Template not found."}},
)
def get_certificate_template_background(
    filename: str = Path(..., description="Template filename, e.g. Begineer.jpg"),
) -> FileResponse:
    try:
        name = certificate_service.validate_template_filename(filename)
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    path = certificate_service.certificates_dir() / name
    return FileResponse(path, media_type="image/jpeg", filename=name)


@admin_router.put(
    "/certificate/templates/{filename}/layout",
    summary="Save name/date/signature layout for one template",
    description="Persist click-calibrated field positions for one certificate template.",
    response_model=CertificateLayoutSavedResponse,
    dependencies=[Depends(require_admin)],
)
def save_certificate_template_layout(
    request: Request,
    filename: str,
    body: TemplateLayoutBody,
) -> CertificateLayoutSavedResponse:
    try:
        certificate_service.save_template_layout(
            filename,
            body.model_dump(),
        )
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    audit_log.admin_action(
        request,
        action="certificate.layout.save",
        resource="certificate_template",
        resource_id=filename.strip(),
    )
    return CertificateLayoutSavedResponse(ok=True, filename=filename.strip())


@admin_router.post(
    "/certificate/templates/{filename}/preview",
    summary="Preview certificate with draft or saved layout",
    description="Render a JPEG preview using draft or saved layout coordinates.",
    dependencies=[Depends(require_admin)],
    responses={
        200: {"description": "JPEG preview.", "content": {"image/jpeg": {}}},
        400: {"description": "Invalid layout or template."},
    },
)
def preview_certificate_template(
    filename: str,
    body: CertificateTemplatePreviewBody,
) -> Response:
    try:
        fields = body.layout.model_dump() if body.layout else None
        result = certificate_service.render_certificate_template(
            filename,
            body.display_name,
            fields=fields,
        )
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Preview failed: {e}") from e
    return Response(
        content=result.image_bytes,
        media_type=result.media_type,
        headers={"Content-Disposition": f'inline; filename="{result.filename}"'},
    )


@admin_router.post(
    "/certificate/issue",
    summary="Manually issue a Tier 1 certificate",
    description="Admin grant: render and record a certificate without a score gate.",
    dependencies=[Depends(require_admin)],
    responses={
        200: {"description": "JPEG certificate file.", "content": {"image/jpeg": {}}},
        **auth_error_responses(),
        400: {"description": "Invalid level or missing display name."},
        500: {"description": "Rendering failed."},
    },
)
def admin_issue_certificate(
    request: Request,
    body: AdminIssueCertificateBody,
) -> Response:
    """Admin grant: render certificate with chosen name and level (no score gate)."""
    try:
        result, issued_id = certificate_service.issue_certificate(
            employee_id=body.employee_id,
            display_name=body.display_name,
            level=body.level,
            assessment_id=body.assessment_id,
            score=None,
            issued_by="admin",
            language_code=body.language_code,
            language_label=body.language_label,
        )
        audit_log.admin_action(
            request,
            action="certificate.issue",
            resource="certificate",
            resource_id=str(issued_id),
        )
        return Response(
            content=result.image_bytes,
            media_type=result.media_type,
            headers={
                "Content-Disposition": f'attachment; filename="{result.filename}"',
            },
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Certificate issue failed: {e}") from e
