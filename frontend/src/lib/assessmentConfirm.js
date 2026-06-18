/** True when a preview/confirm question row came from the question bank. */
export function isBankQuestion(q) {
  return q?.bank_question_id != null;
}

/** Split preview questions into bank-sourced vs LLM-generated. */
export function partitionReviewQuestions(questions) {
  const bankQuestions = [];
  const llmQuestions = [];
  for (const q of questions || []) {
    if (isBankQuestion(q)) bankQuestions.push(q);
    else llmQuestions.push(q);
  }
  return { bankQuestions, llmQuestions };
}

/** Map UI question rows to the confirm-assessment API shape. */
export function buildConfirmQuestions(questions) {
  return (questions || []).map((q) => ({
    question_id: String(q.question_id),
    type: q.type,
    question: q.question,
    code_snippet: q.code_snippet ?? "",
    options: q.options ?? [],
    correct_answer: q.correct_answer ?? "",
    topic_name: q.topic_name ?? "",
    ...(q.bank_question_id != null ? { bank_question_id: q.bank_question_id } : {}),
  }));
}

/** Build POST /admin/confirm-assessment body (drops preview-only fields). */
export function buildConfirmBody(confirmPayload, questions) {
  const {
    question_source: _questionSource,
    target_employee_id: _targetEmployeeId,
    ...rest
  } = confirmPayload || {};
  return {
    ...rest,
    questions: buildConfirmQuestions(questions),
  };
}

/** Recycle run that filled entirely from the bank — safe to skip manual review. */
export function isFullBankRecycle(previewMeta, questionSource) {
  if (questionSource !== "recycle_then_generate") return false;
  const bank = previewMeta?.bank_sourced_count ?? 0;
  const llm = previewMeta?.llm_generated_count ?? 0;
  return bank > 0 && llm === 0;
}
