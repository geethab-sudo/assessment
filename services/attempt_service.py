"""
Timed assessment attempts: per-participant deadlines and enforcement.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select

from services.database import get_session_factory
from services.models import Assessment, AssessmentAttempt, Submission

MIN_DURATION_MINUTES = 1
MIN_NOTEBOOK_GRACE_MINUTES = 0
DEFAULT_NOTEBOOK_GRACE_MINUTES = 5
MAIN_SUBMIT_SLACK_SECONDS = 2


def normalize_employee_id(employee_id: str) -> str:
    return employee_id.strip().casefold()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _parse_iso(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def validate_timed_config(
    is_timed: bool,
    duration_minutes: int | None,
    notebook_grace_minutes: int | None,
) -> tuple[int | None, int | None]:
    if not is_timed:
        return None, None
    if duration_minutes is None:
        raise ValueError("duration_minutes is required when is_timed is true")
    if duration_minutes < MIN_DURATION_MINUTES:
        raise ValueError(
            f"duration_minutes must be at least {MIN_DURATION_MINUTES} minute(s)"
        )
    grace = notebook_grace_minutes if notebook_grace_minutes is not None else DEFAULT_NOTEBOOK_GRACE_MINUTES
    if grace < MIN_NOTEBOOK_GRACE_MINUTES:
        raise ValueError(
            f"notebook_grace_minutes must be at least {MIN_NOTEBOOK_GRACE_MINUTES}"
        )
    return duration_minutes, grace


def user_has_submitted(assessment_id: str, employee_id: str) -> bool:
    """True if any submission exists for this assessment and employee (any question)."""
    eid = normalize_employee_id(employee_id)
    if not eid:
        return False
    prefix = f"{employee_id.strip()} |"
    sf = get_session_factory()
    with sf() as session:
        row = session.scalar(
            select(Submission.id)
            .where(
                Submission.assessment_id == assessment_id.strip(),
                Submission.user_id.ilike(f"{prefix}%"),
            )
            .limit(1)
        )
        if row is not None:
            return True
        # Case-insensitive employee id match on prefix
        rows = session.scalars(
            select(Submission.user_id).where(
                Submission.assessment_id == assessment_id.strip(),
            )
        ).all()
        for uid in rows:
            part = (uid or "").split("|", 1)[0].strip().casefold()
            if part == eid:
                return True
    return False


def _get_attempt_row(assessment_id: str, employee_id: str) -> AssessmentAttempt | None:
    eid = normalize_employee_id(employee_id)
    sf = get_session_factory()
    with sf() as session:
        return session.scalar(
            select(AssessmentAttempt).where(
                AssessmentAttempt.assessment_id == assessment_id.strip(),
                AssessmentAttempt.employee_id == eid,
            )
        )


def get_or_create_attempt(assessment: Assessment, employee_id: str) -> dict[str, Any]:
    """
    Return timer payload for a timed assessment. Creates attempt on first call.
    Raises ValueError if already submitted.
    """
    aid = assessment.assessment_id
    eid = normalize_employee_id(employee_id)
    if not eid:
        raise ValueError("employee_id is required for timed assessments")

    if user_has_submitted(aid, employee_id):
        raise ValueError("already_submitted")

    now = _utc_now()
    duration = assessment.duration_minutes or MIN_DURATION_MINUTES
    grace = assessment.notebook_grace_minutes or DEFAULT_NOTEBOOK_GRACE_MINUTES

    sf = get_session_factory()
    with sf() as session:
        row = session.scalar(
            select(AssessmentAttempt).where(
                AssessmentAttempt.assessment_id == aid,
                AssessmentAttempt.employee_id == eid,
            )
        )
        if not row:
            started = now
            expires = started + timedelta(minutes=duration)
            notebook_expires = expires + timedelta(minutes=grace)
            row = AssessmentAttempt(
                assessment_id=aid,
                employee_id=eid,
                started_at=_iso(started),
                expires_at=_iso(expires),
                notebook_expires_at=_iso(notebook_expires),
                submitted_at=None,
            )
            session.add(row)
            session.commit()
            session.refresh(row)

        return {
            "started_at": row.started_at,
            "expires_at": row.expires_at,
            "notebook_expires_at": row.notebook_expires_at,
            "server_now": _iso(now),
            "submitted_at": row.submitted_at,
        }


def mark_attempt_submitted(assessment_id: str, employee_id: str) -> None:
    eid = normalize_employee_id(employee_id)
    sf = get_session_factory()
    with sf() as session:
        row = session.scalar(
            select(AssessmentAttempt).where(
                AssessmentAttempt.assessment_id == assessment_id.strip(),
                AssessmentAttempt.employee_id == eid,
            )
        )
        if row and not row.submitted_at:
            row.submitted_at = _iso(_utc_now())
            session.commit()


def _deadlines_for(assessment_id: str, employee_id: str) -> tuple[datetime, datetime] | None:
    row = _get_attempt_row(assessment_id, employee_id)
    if not row:
        return None
    return _parse_iso(row.expires_at), _parse_iso(row.notebook_expires_at)


def assert_main_submit_allowed(assessment_id: str, employee_id: str, *, is_timed: bool) -> None:
    if not is_timed:
        return
    deadlines = _deadlines_for(assessment_id, employee_id)
    if not deadlines:
        raise ValueError("No timed attempt found. Load the assessment first.")
    expires_at, _ = deadlines
    now = _utc_now()
    if now > expires_at + timedelta(seconds=MAIN_SUBMIT_SLACK_SECONDS):
        raise ValueError("Assessment time has expired.")


def assert_notebook_submit_allowed(assessment_id: str, employee_id: str, *, is_timed: bool) -> None:
    if not is_timed:
        return
    deadlines = _deadlines_for(assessment_id, employee_id)
    if not deadlines:
        raise ValueError("No timed attempt found. Load the assessment first.")
    _, notebook_expires_at = deadlines
    if _utc_now() > notebook_expires_at:
        raise ValueError("Notebook upload grace period has ended.")


def parse_employee_id_from_user_label(user_id: str) -> str:
    """Extract employee id from ``empid | name`` label."""
    return (user_id or "").split("|", 1)[0].strip()
