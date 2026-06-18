/** True when the participant provided a non-empty answer. */
export function isQuestionAnswered(answer) {
  return String(answer ?? "").trim().length > 0;
}

/** In-browser questions included in POST /submit-assessment (excludes Jupyter coding in mixed tests). */
export function getSubmittableQuestions(assessment) {
  if (!assessment?.questions?.length) return [];
  const isMixed = assessment.routing_flag === "mixed";
  return assessment.questions.filter(
    (q) => !(isMixed && q.type === "coding" && q.topic_modality === "jupyter")
  );
}

/** Count unanswered submittable questions. */
export function countUnansweredQuestions(assessment, answers) {
  const submittable = getSubmittableQuestions(assessment);
  const unanswered = submittable.filter(
    (q) => !isQuestionAnswered(answers[String(q.question_id)])
  ).length;
  return { unanswered, total: submittable.length };
}
