import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import {
  createDifficultyImprovementAssessment,
  createNewAreasAssessment,
  createWeakAreasAssessment,
  fetchEmployeeProfile,
  fetchEmployeeReport,
} from "../lib/employeeReportApi.js";

const WEAK_THRESHOLD = 70;
const NEW_AREAS_TOPIC_LIMIT = 5;
const STEP_UP_TOPIC_LIMIT = 5;

const DIFFICULTY_RANK = { beginner: 1, intermediate: 2, advanced: 3 };

function topicRowClass(percent, isWeak, isStepUp) {
  if (isWeak) return "improve-topic-row improve-topic-row--weak";
  if (isStepUp) return "improve-topic-row improve-topic-row--step-up";
  return "improve-topic-row";
}

function formatAvailabilityMessage(text) {
  if (!text) return null;
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={i}>{part.slice(2, -2)}</strong>;
    }
    return part;
  });
}

function parsePathParam(value) {
  if (value === "weak" || value === "new" || value === "difficulty") return value;
  return null;
}

function profileScopeForPath(path) {
  return path === "weak" ? "last_3" : "full_history";
}

function isStepUpReady(topic, recommendedByTopic) {
  const last = (topic.last_difficulty || "beginner").toLowerCase();
  const target = (recommendedByTopic[topic.topic_name] || last).toLowerCase();
  return (DIFFICULTY_RANK[target] || 1) > (DIFFICULTY_RANK[last] || 1);
}

export default function ImprovementPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const employeeIdParam = searchParams.get("employee_id") || "";
  const languageParam = searchParams.get("language_code") || "";

  const [employeeId, setEmployeeId] = useState(employeeIdParam);
  const [languageCode, setLanguageCode] = useState(languageParam);
  const [evaluatedLanguages, setEvaluatedLanguages] = useState([]);
  const [languagesLoading, setLanguagesLoading] = useState(false);
  const [selectedPath, setSelectedPath] = useState(parsePathParam(searchParams.get("path")));

  const [profile, setProfile] = useState(null);
  const [profileLoading, setProfileLoading] = useState(false);
  const [profileError, setProfileError] = useState(null);

  const [creating, setCreating] = useState(false);
  const [createResult, setCreateResult] = useState(null);
  const [createError, setCreateError] = useState(null);

  const profileFetchKey = useRef("");

  const languageLocked = evaluatedLanguages.length === 1;
  const hasEvaluatedLanguages = evaluatedLanguages.length > 0;

  useEffect(() => {
    setEmployeeId(employeeIdParam);
  }, [employeeIdParam]);

  useEffect(() => {
    setSelectedPath(parsePathParam(searchParams.get("path")));
  }, [searchParams]);

  useEffect(() => {
    const eid = employeeIdParam.trim();
    if (!eid) {
      setEvaluatedLanguages([]);
      return;
    }

    let cancelled = false;
    (async () => {
      setLanguagesLoading(true);
      try {
        const report = await fetchEmployeeReport({
          employeeId: eid,
          period: "all_time",
        });
        if (cancelled) return;

        const langs = (report.languages || [])
          .map((lang) => ({
            code: lang.language_code,
            label: lang.language_label || lang.language_code,
          }))
          .filter((lang) => lang.code);

        setEvaluatedLanguages(langs);

        if (langs.length === 1) {
          setLanguageCode(langs[0].code);
        } else if (
          languageParam &&
          langs.some((l) => l.code === languageParam)
        ) {
          setLanguageCode(languageParam);
        } else if (langs.length > 1) {
          setLanguageCode(langs[0].code);
        } else {
          setLanguageCode("");
        }
      } catch {
        if (!cancelled) {
          setEvaluatedLanguages([]);
          setLanguageCode("");
        }
      } finally {
        if (!cancelled) setLanguagesLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [employeeIdParam, languageParam]);

  const loadProfile = useCallback(async () => {
    const eid = employeeId.trim();
    const lang = languageCode.trim();
    const scope = profileScopeForPath(selectedPath);

    if (!eid) {
      setProfileError("Enter your employee ID to continue.");
      setProfile(null);
      return;
    }
    if (!lang) {
      setProfileError("Complete an assessment first to unlock language-specific practice.");
      setProfile(null);
      return;
    }

    const fetchKey = `${eid}:${lang}:${scope}`;
    profileFetchKey.current = fetchKey;
    setProfileLoading(true);
    setProfileError(null);
    setCreateResult(null);
    setCreateError(null);

    try {
      const data = await fetchEmployeeProfile({
        employeeId: eid,
        scope,
        languageCode: lang,
      });
      if (profileFetchKey.current !== fetchKey) return;
      setProfile(data);
    } catch (err) {
      if (profileFetchKey.current !== fetchKey) return;
      setProfile(null);
      setProfileError(err.message || "Could not load your profile.");
    } finally {
      if (profileFetchKey.current === fetchKey) {
        setProfileLoading(false);
      }
    }
  }, [employeeId, languageCode, selectedPath]);

  useEffect(() => {
    if (
      (selectedPath === "weak" ||
        selectedPath === "new" ||
        selectedPath === "difficulty") &&
      employeeId.trim() &&
      languageCode.trim()
    ) {
      loadProfile();
    }
  }, [selectedPath, employeeId, languageCode, loadProfile]);

  const weakTopicSet = useMemo(() => {
    return new Set(profile?.weakest_topics || []);
  }, [profile]);

  const recommendedByTopic = profile?.recommended_difficulty_by_topic || {};

  const stepUpTopics = useMemo(() => {
    return (profile?.topic_performance || []).filter((topic) =>
      isStepUpReady(topic, recommendedByTopic)
    );
  }, [profile, recommendedByTopic]);

  const stepUpTopicSet = useMemo(() => {
    return new Set(stepUpTopics.map((t) => t.topic_name));
  }, [stepUpTopics]);

  const unexploredTopics = profile?.unexplored_topic_names || [];

  const setPath = (path) => {
    const next = new URLSearchParams(searchParams);
    if (path) next.set("path", path);
    else next.delete("path");
    if (employeeId.trim()) next.set("employee_id", employeeId.trim());
    if (languageCode.trim()) next.set("language_code", languageCode.trim());
    setSearchParams(next, { replace: true });
  };

  const handleSelectPath = (path) => {
    setSelectedPath(path);
    setProfile(null);
    setCreateResult(null);
    setCreateError(null);
    setPath(path);
  };

  const handleLanguageChange = (code) => {
    if (languageLocked) return;
    setLanguageCode(code);
    setProfile(null);
    const next = new URLSearchParams(searchParams);
    if (code) next.set("language_code", code);
    else next.delete("language_code");
    setSearchParams(next, { replace: true });
  };

  const handleStartPractice = async () => {
    const eid = employeeId.trim();
    const lang = languageCode.trim();
    if (!eid || !lang) {
      setCreateError("Employee ID and language are required.");
      return;
    }
    setCreating(true);
    setCreateError(null);
    setCreateResult(null);
    try {
      let data;
      if (selectedPath === "new") {
        data = await createNewAreasAssessment({
          employeeId: eid,
          languageCode: lang,
          topicsCount: NEW_AREAS_TOPIC_LIMIT,
        });
      } else if (selectedPath === "difficulty") {
        data = await createDifficultyImprovementAssessment({
          employeeId: eid,
          languageCode: lang,
          topicsCount: STEP_UP_TOPIC_LIMIT,
        });
      } else {
        data = await createWeakAreasAssessment({
          employeeId: eid,
          languageCode: lang,
        });
      }
      setCreateResult(data);
      if (data.assessment_id) {
        navigate("/client", {
          state: { assessmentId: data.assessment_id, employeeId: eid },
        });
      }
    } catch (err) {
      setCreateError(err.message || "Could not create practice assessment.");
    } finally {
      setCreating(false);
    }
  };

  const canStartWeak =
    profile?.assessments_analyzed > 0 && (profile?.weakest_topics?.length || 0) > 0;

  const canStartNew =
    profile?.assessments_analyzed > 0 && unexploredTopics.length > 0;

  const canStartDifficulty =
    profile?.assessments_analyzed > 0 && stepUpTopics.length > 0;

  const langLabel =
    evaluatedLanguages.find((l) => l.code === languageCode)?.label || languageCode;

  return (
    <div className="page improve-page">
      <header className="header">
        <p className="page-eyebrow">Personalized practice</p>
        <h1>Help me improve</h1>
        <p className="muted">
          Choose a practice path based on your assessment history. Practice assessments use
          questions from our bank only — no new AI-generated content.
        </p>
        <p className="muted small-print">
          <Link to="/client">← Back to take test</Link>
          {employeeId.trim() && (
            <>
              {" · "}
              <Link
                to={`/client/my-report?employee_id=${encodeURIComponent(employeeId.trim())}`}
              >
                View my report →
              </Link>
            </>
          )}
        </p>
      </header>

      <section className="card">
        <h2>Your details</h2>
        <div className="row">
          <label className="grow">
            Employee ID
            <input
              value={employeeId}
              onChange={(e) => setEmployeeId(e.target.value)}
              placeholder="e.g. C002"
              autoComplete="username"
            />
          </label>
          <label className="grow">
            Language
            {languageLocked ? (
              <input
                value={
                  evaluatedLanguages[0]?.label ||
                  evaluatedLanguages[0]?.code ||
                  languageCode
                }
                readOnly
                disabled
                title="Based on your assessment history"
              />
            ) : (
              <select
                value={languageCode}
                onChange={(e) => handleLanguageChange(e.target.value)}
                disabled={languagesLoading || !hasEvaluatedLanguages}
              >
                {!hasEvaluatedLanguages && (
                  <option value="">
                    {languagesLoading ? "Loading…" : "No assessed languages yet"}
                  </option>
                )}
                {evaluatedLanguages.map((lang) => (
                  <option key={lang.code} value={lang.code}>
                    {lang.label}
                  </option>
                ))}
              </select>
            )}
          </label>
        </div>
        {languageLocked && (
          <p className="muted small-print">
            Practice is scoped to {evaluatedLanguages[0]?.label || "your assessed language"} —
            the only language in your history so far.
          </p>
        )}
        {!languagesLoading && !hasEvaluatedLanguages && employeeId.trim() && (
          <p className="muted small-print">
            Complete at least one assessment before using Help me improve.
          </p>
        )}
      </section>

      {!selectedPath && (
        <section className="card">
          <h2>Choose a path</h2>
          <div className="improve-options">
            <button
              type="button"
              className="improve-option improve-option--active"
              onClick={() => handleSelectPath("weak")}
              disabled={!employeeId.trim() || !languageCode.trim()}
            >
              <h3>Improve my weak areas</h3>
              <p className="muted">
                Extra practice on topics below {WEAK_THRESHOLD}% in your last 3 assessments.
              </p>
            </button>
            <button
              type="button"
              className="improve-option improve-option--active"
              onClick={() => handleSelectPath("new")}
              disabled={!employeeId.trim() || !languageCode.trim()}
            >
              <h3>Explore new areas</h3>
              <p className="muted">
                Try catalog topics you have not been assessed on yet (full history).
              </p>
            </button>
            <button
              type="button"
              className="improve-option improve-option--active"
              onClick={() => handleSelectPath("difficulty")}
              disabled={!employeeId.trim() || !languageCode.trim()}
            >
              <h3>Step up difficulty</h3>
              <p className="muted">
                Harder bank questions on familiar topics when your scores qualify (≥75%
                beginner, ≥80% intermediate).
              </p>
            </button>
          </div>
        </section>
      )}

      {selectedPath === "weak" && (
        <section className="card">
          <div className="improve-section-header">
            <h2>Improve my weak areas</h2>
            <button
              type="button"
              className="link-button"
              onClick={() => {
                setSelectedPath(null);
                setProfile(null);
                setPath(null);
              }}
            >
              ← All paths
            </button>
          </div>

          {(profileLoading || languagesLoading) && (
            <p className="muted">Loading your last 3 assessments…</p>
          )}
          {profileError && <p className="error">{profileError}</p>}

          {profile && !profileLoading && (
            <>
              <p className="muted small-print">
                Analyzing {profile.assessments_analyzed} recent assessment
                {profile.assessments_analyzed === 1 ? "" : "s"} for {langLabel}. Weak topics
                are below {WEAK_THRESHOLD}% average.
              </p>

              {profile.weakest_topics?.length > 0 && (
                <div className="improve-topic-summary">
                  <p className="improve-topic-summary-lead">
                    Based on your last 3 assessments, we recommend extra practice on:
                  </p>
                  <ul className="improve-weak-topic-list">
                    {profile.weakest_topics.map((t) => (
                      <li key={t}>{t}</li>
                    ))}
                  </ul>
                </div>
              )}

              <div className="table-wrap">
                <table className="data-table emp-report-topic-table">
                  <thead>
                    <tr>
                      <th>Topic</th>
                      <th>Questions</th>
                      <th>Avg %</th>
                      <th>Assessments</th>
                      <th>Last level</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(profile.topic_performance || []).map((topic) => (
                      <tr
                        key={topic.topic_name}
                        className={topicRowClass(
                          topic.average_percent,
                          weakTopicSet.has(topic.topic_name),
                          false
                        )}
                      >
                        <td>
                          {topic.topic_name}
                          {weakTopicSet.has(topic.topic_name) && (
                            <span className="improve-weak-badge"> weak</span>
                          )}
                        </td>
                        <td>{topic.questions_count}</td>
                        <td>{Math.round(topic.average_percent)}%</td>
                        <td>{topic.attempts}</td>
                        <td>{topic.last_difficulty || "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {!profile.weakest_topics?.length && profile.assessments_analyzed > 0 && (
                <p className="muted">
                  No topics scored below {WEAK_THRESHOLD}% in your last 3 assessments.
                </p>
              )}

              {profile.assessments_analyzed === 0 && (
                <p className="muted">
                  Complete at least one assessment to unlock personalized practice.
                </p>
              )}

              {createResult?.availability_message && !createResult.assessment_id && (
                <p className="improve-availability" role="status">
                  {formatAvailabilityMessage(createResult.availability_message)}
                </p>
              )}

              {createError && <p className="error">{createError}</p>}

              <div className="improve-actions">
                <button
                  type="button"
                  onClick={handleStartPractice}
                  disabled={
                    creating || !employeeId.trim() || !languageCode.trim() || !canStartWeak
                  }
                >
                  {creating ? "Creating…" : "Start practice assessment"}
                </button>
              </div>
            </>
          )}
        </section>
      )}

      {selectedPath === "new" && (
        <section className="card">
          <div className="improve-section-header">
            <h2>Explore new areas</h2>
            <button
              type="button"
              className="link-button"
              onClick={() => {
                setSelectedPath(null);
                setProfile(null);
                setPath(null);
              }}
            >
              ← All paths
            </button>
          </div>

          {(profileLoading || languagesLoading) && (
            <p className="muted">Loading your assessment history…</p>
          )}
          {profileError && <p className="error">{profileError}</p>}

          {profile && !profileLoading && (
            <>
              <p className="muted small-print">
                Based on your full history in {langLabel}, these catalog topics have not
                appeared in any of your {profile.assessments_analyzed} assessment
                {profile.assessments_analyzed === 1 ? "" : "s"}. Practice pulls up to{" "}
                {NEW_AREAS_TOPIC_LIMIT} topics in learning-path order: Intermediate preset
                gaps first, then Advanced, then Tier 2 topics.
              </p>

              {unexploredTopics.length > 0 ? (
                <div className="improve-topic-summary improve-topic-summary--new">
                  <p className="improve-topic-summary-lead">
                    Topics you have not tried yet ({unexploredTopics.length} in catalog):
                  </p>
                  <ul className="improve-weak-topic-list">
                    {unexploredTopics.map((t) => (
                      <li key={t}>{t}</li>
                    ))}
                  </ul>
                </div>
              ) : (
                <p className="muted">
                  You have explored all catalog topics for this language. Try weak areas or
                  step up difficulty when available.
                </p>
              )}

              {createResult?.selected_topics?.length > 0 && (
                <div className="improve-topic-summary">
                  <p className="improve-topic-summary-lead">Selected for this practice run:</p>
                  <ul className="improve-weak-topic-list">
                    {createResult.selected_topics.map((t) => (
                      <li key={t}>{t}</li>
                    ))}
                  </ul>
                </div>
              )}

              {createResult?.availability_message && !createResult.assessment_id && (
                <p className="improve-availability" role="status">
                  {formatAvailabilityMessage(createResult.availability_message)}
                </p>
              )}

              {createError && <p className="error">{createError}</p>}

              <div className="improve-actions">
                <button
                  type="button"
                  onClick={handleStartPractice}
                  disabled={
                    creating || !employeeId.trim() || !languageCode.trim() || !canStartNew
                  }
                >
                  {creating ? "Creating…" : "Start practice on new topics"}
                </button>
              </div>
            </>
          )}
        </section>
      )}

      {selectedPath === "difficulty" && (
        <section className="card">
          <div className="improve-section-header">
            <h2>Step up difficulty</h2>
            <button
              type="button"
              className="link-button"
              onClick={() => {
                setSelectedPath(null);
                setProfile(null);
                setPath(null);
              }}
            >
              ← All paths
            </button>
          </div>

          {(profileLoading || languagesLoading) && (
            <p className="muted">Loading your full assessment history…</p>
          )}
          {profileError && <p className="error">{profileError}</p>}

          {profile && !profileLoading && (
            <>
              <p className="muted small-print">
                Based on your full history in {langLabel}, topics where you scored well enough
                qualify for harder bank questions at the next level. We select up to{" "}
                {STEP_UP_TOPIC_LIMIT} topics, strongest performers first.
              </p>

              {stepUpTopics.length > 0 ? (
                <div className="improve-topic-summary improve-topic-summary--step-up">
                  <p className="improve-topic-summary-lead">
                    Ready to step up ({stepUpTopics.length} topic
                    {stepUpTopics.length === 1 ? "" : "s"}):
                  </p>
                  <ul className="improve-weak-topic-list">
                    {stepUpTopics.map((t) => (
                      <li key={t.topic_name}>
                        {t.topic_name} — {t.last_difficulty || "beginner"} →{" "}
                        {recommendedByTopic[t.topic_name]}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : (
                <p className="muted">
                  No topics are ready for a harder level yet. Score at least 75% on beginner
                  topics (or 80% on intermediate) to unlock step-up practice.
                </p>
              )}

              <div className="table-wrap">
                <table className="data-table emp-report-topic-table">
                  <thead>
                    <tr>
                      <th>Topic</th>
                      <th>Avg %</th>
                      <th>Last level</th>
                      <th>Recommended</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(profile.topic_performance || []).map((topic) => (
                      <tr
                        key={topic.topic_name}
                        className={topicRowClass(
                          topic.average_percent,
                          false,
                          stepUpTopicSet.has(topic.topic_name)
                        )}
                      >
                        <td>
                          {topic.topic_name}
                          {stepUpTopicSet.has(topic.topic_name) && (
                            <span className="improve-step-up-badge"> step-up</span>
                          )}
                        </td>
                        <td>{Math.round(topic.average_percent)}%</td>
                        <td>{topic.last_difficulty || "—"}</td>
                        <td>{recommendedByTopic[topic.topic_name] || "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {createResult?.selected_topics?.length > 0 && (
                <div className="improve-topic-summary">
                  <p className="improve-topic-summary-lead">Selected for this practice run:</p>
                  <ul className="improve-weak-topic-list">
                    {createResult.selected_topics.map((t) => (
                      <li key={t}>
                        {t}
                        {createResult.target_difficulty_by_topic?.[t]
                          ? ` (${createResult.target_difficulty_by_topic[t]})`
                          : ""}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {createResult?.availability_message && !createResult.assessment_id && (
                <p className="improve-availability" role="status">
                  {formatAvailabilityMessage(createResult.availability_message)}
                </p>
              )}

              {createError && <p className="error">{createError}</p>}

              <div className="improve-actions">
                <button
                  type="button"
                  onClick={handleStartPractice}
                  disabled={
                    creating ||
                    !employeeId.trim() ||
                    !languageCode.trim() ||
                    !canStartDifficulty
                  }
                >
                  {creating ? "Creating…" : "Start harder practice assessment"}
                </button>
              </div>
            </>
          )}
        </section>
      )}
    </div>
  );
}
