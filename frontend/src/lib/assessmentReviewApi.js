import { apiFetch } from "../api";
import { buildConfirmQuestions } from "./assessmentConfirm.js";

const PENDING_REVIEW_KEY = "admin_review_pending_v1";

/** Persist generate→review handoff across URL updates and full reloads. */
export function stashPendingReviewSession(session) {
  if (!session?.confirmPayload || !session?.questions?.length) {
    sessionStorage.removeItem(PENDING_REVIEW_KEY);
    return;
  }
  sessionStorage.setItem(PENDING_REVIEW_KEY, JSON.stringify(session));
}

export function readPendingReviewSession() {
  try {
    const raw = sessionStorage.getItem(PENDING_REVIEW_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed?.confirmPayload || !parsed?.questions?.length) return null;
    return parsed;
  } catch {
    return null;
  }
}

export function clearPendingReviewSession() {
  sessionStorage.removeItem(PENDING_REVIEW_KEY);
}

/** Build metadata payload for draft creation from generate/preview confirm payload. */
export function metadataFromConfirmPayload(confirmPayload, alias = null) {
  if (!confirmPayload) return null;
  const {
    question_source: questionSource,
    target_employee_id: _targetEmployeeId,
    types: _types,
    questions_per_type: _qpt,
    ...rest
  } = confirmPayload;
  return {
    ...rest,
    question_source: questionSource || "generate_new",
    ...(alias != null ? { alias: alias || null } : {}),
  };
}

export function loadReviewBundle(assessmentId) {
  return apiFetch(`/admin/assessment/${encodeURIComponent(assessmentId)}/review`, {
    authRole: "admin",
  });
}

export function createReviewDraft(metadata, questions = []) {
  return apiFetch("/admin/assessment/review/draft", {
    method: "POST",
    authRole: "admin",
    body: JSON.stringify({
      ...metadata,
      questions: buildConfirmQuestions(questions),
    }),
  });
}

export function saveReviewQuestion(assessmentId, questionId, question) {
  return apiFetch(
    `/admin/assessment/${encodeURIComponent(assessmentId)}/review/questions/${encodeURIComponent(questionId)}/save`,
    {
      method: "POST",
      authRole: "admin",
      body: JSON.stringify(question),
    }
  );
}

export function deleteReviewQuestion(assessmentId, questionId) {
  return apiFetch(
    `/admin/assessment/${encodeURIComponent(assessmentId)}/review/questions/${encodeURIComponent(questionId)}`,
    {
      method: "DELETE",
      authRole: "admin",
    }
  );
}

/** Ensure topic is non-empty (legacy assessments may only have topic_names). */
export function normalizeReviewMetadata(metadata) {
  if (!metadata) return null;
  const topic =
    (metadata.topic || "").trim() ||
    (Array.isArray(metadata.topic_names) && metadata.topic_names.length > 0
      ? metadata.topic_names.join(", ")
      : "Assessment");
  return { ...metadata, topic };
}

export function publishReview(assessmentId, questions, metadata = null) {
  const meta = normalizeReviewMetadata(metadata);
  return apiFetch(
    `/admin/assessment/${encodeURIComponent(assessmentId)}/review/publish`,
    {
      method: "POST",
      authRole: "admin",
      body: JSON.stringify({
        questions: buildConfirmQuestions(questions),
        ...(meta ? { metadata: meta } : {}),
      }),
    }
  );
}

export function regenerateReviewQuestion(body) {
  return apiFetch("/admin/assessment/review/regenerate-question", {
    method: "POST",
    authRole: "admin",
    body: JSON.stringify(body),
  });
}

export function patchAssessmentAlias(assessmentId, alias) {
  return apiFetch(`/admin/assessment/${encodeURIComponent(assessmentId)}/alias`, {
    method: "PATCH",
    authRole: "admin",
    body: JSON.stringify({ alias: alias || null }),
  });
}

/** Mark question dirty after local edits (clears saved badge until re-saved). */
export function markQuestionDirty(question) {
  return { ...question, is_dirty: true };
}
