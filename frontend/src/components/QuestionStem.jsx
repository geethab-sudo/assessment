import { resolveQuestionStem } from "../lib/resolveQuestionStem.js";
import McqCodeBlock from "./McqCodeBlock.jsx";

/**
 * Question prose + optional highlighted code block (MCQ and other types).
 */
export default function QuestionStem({
  question,
  code,
  languageCode,
  className = "",
  protectCodeFromCopy = false,
}) {
  const { prose, code: block, highlightLanguage } = resolveQuestionStem(
    question,
    code,
    languageCode
  );

  if (!prose && !block) return null;

  return (
    <div className={`question-stem-block${className ? ` ${className}` : ""}`}>
      {prose ? <p className="question-stem">{prose}</p> : null}
      {block ? (
        <McqCodeBlock
          code={block}
          language={highlightLanguage}
          protectFromCopy={protectCodeFromCopy}
        />
      ) : null}
    </div>
  );
}
