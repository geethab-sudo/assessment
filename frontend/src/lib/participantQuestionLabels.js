/**
 * Display labels for participants (shuffled order).
 * Admin UIs keep canonical Q1, Q2, … by question_id for debugging.
 */

export function participantQuestionLabel(displayIndex, total) {
  return `Question ${displayIndex} of ${total}`;
}

/**
 * Rewrite backend feedback lines (Q{question_id}: …) to participant-facing labels.
 */
export function remapParticipantFeedback(feedback, questions) {
  if (!feedback || !questions?.length) return feedback ?? "";
  const total = questions.length;
  const indexByQid = Object.fromEntries(
    questions.map((q, i) => [String(q.question_id), i + 1])
  );
  let out = feedback;
  const qids = Object.keys(indexByQid).sort((a, b) => b.length - a.length);
  for (const qid of qids) {
    const label = participantQuestionLabel(indexByQid[qid], total);
    out = out.split(`Q${qid}:`).join(`${label}:`);
  }
  return out;
}
