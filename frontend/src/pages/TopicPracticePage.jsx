import { useCallback, useMemo, useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import TopicPracticePicker from "../components/TopicPracticePicker.jsx";
import {
  createFromTopicsAssessment,
  createNewAreasAssessment,
} from "../lib/employeeReportApi.js";
import { DEFAULT_QUICK_PRACTICE_QUESTIONS } from "../lib/improvementConstants.js";

function readPickerState(location) {
  const s = location.state;
  if (!s || typeof s !== "object") return null;
  const employeeId = typeof s.employeeId === "string" ? s.employeeId.trim() : "";
  const languageCode = typeof s.languageCode === "string" ? s.languageCode.trim() : "";
  const topics = Array.isArray(s.topics) ? s.topics : [];
  if (!employeeId || !languageCode || topics.length === 0) return null;
  return {
    employeeId,
    languageCode,
    languageLabel: typeof s.languageLabel === "string" ? s.languageLabel : languageCode,
    title: s.title || "Choose topics to practice",
    subtitle: s.subtitle || null,
    topics,
    initialSelected: Array.isArray(s.initialSelected) ? s.initialSelected : [],
    mode: s.mode === "new-areas" ? "new-areas" : "from-topics",
    returnTo: typeof s.returnTo === "string" ? s.returnTo : "/client/my-report",
    defaultQuestions:
      typeof s.defaultQuestions === "number" ? s.defaultQuestions : DEFAULT_QUICK_PRACTICE_QUESTIONS,
  };
}

export default function TopicPracticePage() {
  const location = useLocation();
  const navigate = useNavigate();
  const picker = useMemo(() => readPickerState(location), [location]);

  const [starting, setStarting] = useState(false);
  const [error, setError] = useState(null);

  const handleStart = useCallback(
    async (topicNames, questionCount) => {
      if (!picker) return;
      setStarting(true);
      setError(null);
      try {
        let data;
        if (picker.mode === "new-areas") {
          data = await createNewAreasAssessment({
            employeeId: picker.employeeId,
            languageCode: picker.languageCode,
            questionsRequested: questionCount,
            topicNames,
          });
        } else {
          data = await createFromTopicsAssessment({
            employeeId: picker.employeeId,
            languageCode: picker.languageCode,
            topicNames,
            questionsRequested: questionCount,
          });
        }
        if (data.assessment_id) {
          navigate("/client", {
            state: {
              assessmentId: data.assessment_id,
              employeeId: picker.employeeId,
            },
            replace: true,
          });
        } else {
          setError(data.availability_message || "Could not create a practice assessment.");
        }
      } catch (e) {
        setError(e.message || "Could not create practice assessment.");
      } finally {
        setStarting(false);
      }
    },
    [picker, navigate]
  );

  if (!picker) {
    return <Navigate to="/client/my-report" replace />;
  }

  return (
    <TopicPracticePicker
      layout="page"
      title={picker.title}
      subtitle={picker.subtitle}
      topics={picker.topics}
      initialSelected={picker.initialSelected}
      defaultQuestions={picker.defaultQuestions}
      employeeId={picker.employeeId}
      languageLabel={picker.languageLabel}
      backTo={picker.returnTo}
      onStart={handleStart}
      starting={starting}
      error={error}
    />
  );
}
