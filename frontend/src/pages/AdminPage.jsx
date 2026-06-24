import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { apiFetch } from "../api";
import {
  buildConfirmBody,
  isFullBankRecycle,
} from "../lib/assessmentConfirm.js";
import SearchableLanguageSelect from "../components/SearchableLanguageSelect.jsx";
import {
  applyPreset,
  findPythonLanguageId,
  getTier1Presets,
  getPresetByName,
  presetNameToLevel,
} from "../lib/tier1Presets.js";

/** Build the topic string for the LLM from a catalog topic row. */
function buildTopicStringForApi(topicRow) {
  if (!topicRow) return "";
  const name = (topicRow.name || "").trim();
  const docs = Array.isArray(topicRow.related_documents) ? topicRow.related_documents : [];
  if (docs.length === 0) return name;
  const lines = docs.map((d) => {
    const title = (d.title || "").trim() || "Reference";
    if (d.url) return `- ${title}: ${d.url}`;
    if (d.path) return `- ${title}: ${d.path}`;
    return `- ${title}`;
  });
  return `${name}\n\nContext (reference materials):\n${lines.join("\n")}`;
}

/** Join multiple catalog topics for one assessment generation run. */
function buildMultiTopicString(topicRows) {
  if (!topicRows.length) return "";
  if (topicRows.length === 1) return buildTopicStringForApi(topicRows[0]);
  return topicRows
    .map(
      (row, i) =>
        `## Topic area ${i + 1} — ${(row.name || "Untitled").trim()}\n\n${buildTopicStringForApi(
          row
        )}`
    )
    .join("\n\n---\n\n");
}

/** Build the topic string when per-topic counts are specified. */
function buildPerTopicTopicString(selectedTopicRows, perTopicCounts) {
  if (!selectedTopicRows.length) return "";

  const header = `Please distribute the generated questions across the specific topic areas below according to the requested counts. Each topic area must get exactly the counts specified.
`;

  const sections = selectedTopicRows.map((row, i) => {
    const topicId = String(row.id);
    const counts = perTopicCounts[topicId] || { mcq: 0, coding: 0, subjective: 0 };
    const name = (row.name || "Untitled").trim();
    const docs = Array.isArray(row.related_documents) ? row.related_documents : [];

    const lines = docs.map((d) => {
      const title = (d.title || "").trim() || "Reference";
      if (d.url) return `- ${title}: ${d.url}`;
      if (d.path) return `- ${title}: ${d.path}`;
      return `- ${title}`;
    });

    const contextStr = lines.length > 0
      ? `\nContext (reference materials):\n${lines.join("\n")}`
      : "";

    const instructionStr = `Required questions for this specific topic:
- MCQ (Multiple-Choice Questions): ${counts.mcq || 0}
- Coding: ${counts.coding || 0}
- Subjective: ${counts.subjective || 0}`;

    return `## Topic area ${i + 1} — ${name}${contextStr}\n\n${instructionStr}`;
  });

  return `${header}\n${sections.join("\n\n---\n\n")}`;
}


export default function AdminPage() {
  const navigate = useNavigate();
  const [topicMode, setTopicMode] = useState("catalog"); // "catalog" | "custom"
  const [languages, setLanguages] = useState([]);
  const [languageId, setLanguageId] = useState("");
  const [topics, setTopics] = useState([]);
  /** Preserves selection order for preview / LLM. */
  const [selectedTopicIds, setSelectedTopicIds] = useState([]);
  const [loadingLanguages, setLoadingLanguages] = useState(true);
  const [loadingTopics, setLoadingTopics] = useState(false);
  const [catalogHint, setCatalogHint] = useState(null);

  const [customTopic, setCustomTopic] = useState("");
  /** When using custom free-text topic, optional catalog language for coding-question editor + LLM context. */
  const [customCodeLanguageId, setCustomCodeLanguageId] = useState("");

  const [level, setLevel] = useState("intermediate");
  const [typeMcq, setTypeMcq] = useState(true);
  const [typeCoding, setTypeCoding] = useState(true);
  const [typeSubjective, setTypeSubjective] = useState(false);
  const [countMcq, setCountMcq] = useState(2);
  const [countCoding, setCountCoding] = useState(2);
  const [countSubjective, setCountSubjective] = useState(1);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const [allocationMode, setAllocationMode] = useState("auto"); // "auto" | "per-topic"
  const [perTopicCounts, setPerTopicCounts] = useState({}); // { [topicId]: { mcq, coding, subjective } }

  const [isTimed, setIsTimed] = useState(false);
  const [allowPyodidePaste, setAllowPyodidePaste] = useState(false);
  const [includeSampleTestCases, setIncludeSampleTestCases] = useState(false);
  const [includeBeginnerCodingHints, setIncludeBeginnerCodingHints] = useState(false);
  const [certificateEnabled, setCertificateEnabled] = useState(false);
  const [durationMinutes, setDurationMinutes] = useState(45);
  const [notebookGraceMinutes, setNotebookGraceMinutes] = useState(5);

  const [usePresetTier1, setUsePresetTier1] = useState(false);
  const [selectedPresetName, setSelectedPresetName] = useState(null);
  const [showDistributionEditor, setShowDistributionEditor] = useState(false);
  const [presetMissingTopics, setPresetMissingTopics] = useState([]);

  const [questionSource, setQuestionSource] = useState("generate_new");
  const [targetEmployeeId, setTargetEmployeeId] = useState("");
  const [bankAvailability, setBankAvailability] = useState(null);
  const [generationProvider, setGenerationProvider] = useState("grok");
  /** null = health check pending or unavailable; only disable radios when explicitly false */
  const [groqConfigured, setGroqConfigured] = useState(null);
  const [geminiConfigured, setGeminiConfigured] = useState(null);

  const tier1Presets = useMemo(() => getTier1Presets(), []);

  const topicById = useMemo(
    () => Object.fromEntries(topics.map((t) => [String(t.id), t])),
    [topics]
  );

  const selectedTopicRows = useMemo(
    () => selectedTopicIds.map((id) => topicById[id]).filter(Boolean),
    [selectedTopicIds, topicById]
  );

  const resolvedTopic = useMemo(() => {
    if (topicMode !== "catalog") return customTopic.trim();
    if (usePresetTier1 || allocationMode === "per-topic") {
      return buildPerTopicTopicString(selectedTopicRows, perTopicCounts);
    }
    return buildMultiTopicString(selectedTopicRows);
  }, [topicMode, usePresetTier1, allocationMode, selectedTopicRows, perTopicCounts, customTopic]);

  const effectiveLevel = useMemo(() => {
    if (usePresetTier1 && selectedPresetName) {
      return presetNameToLevel(selectedPresetName);
    }
    return level;
  }, [usePresetTier1, selectedPresetName, level]);


  const loadLanguages = useCallback(async () => {
    setLoadingLanguages(true);
    setCatalogHint(null);
    try {
      const data = await apiFetch("/admin/languages");
      const list = data.languages ?? [];
      setLanguages(list);
      if (list.length === 0) {
        setCatalogHint(
          "No languages in the database yet. Add them under Admin → Catalog, or use a custom topic."
        );
      }
    } catch (e) {
      setCatalogHint(e.message);
      setLanguages([]);
    } finally {
      setLoadingLanguages(false);
    }
  }, []);

  const loadTopicsForLanguage = useCallback(async (lid) => {
    if (lid === "" || lid == null) {
      setTopics([]);
      setSelectedTopicIds([]);
      return;
    }
    setLoadingTopics(true);
    setCatalogHint(null);
    setSelectedTopicIds([]);
    try {
      const data = await apiFetch(
        `/admin/topics?language_id=${encodeURIComponent(lid)}`
      );
      const list = data.topics ?? [];
      setTopics(list);
      if (list.length === 0) {
        setCatalogHint(
          "No topics for this language. Add topics under Admin → Catalog or use a custom topic."
        );
      }
    } catch (e) {
      setTopics([]);
      setSelectedTopicIds([]);
      setCatalogHint(e.message);
    } finally {
      setLoadingTopics(false);
    }
  }, []);

  useEffect(() => {
    void loadLanguages();
  }, [loadLanguages]);

  useEffect(() => {
    apiFetch("/health")
      .then((data) => {
        setGroqConfigured(Boolean(data.groq_configured));
        setGeminiConfigured(Boolean(data.gemini_configured));
      })
      .catch(() => {
        /* Health unreachable — leave null; do not claim API keys are missing */
      });
  }, []);

  useEffect(() => {
    if (languageId === "") {
      setTopics([]);
      if (!usePresetTier1) {
        setSelectedTopicIds([]);
      }
      return;
    }
    void loadTopicsForLanguage(languageId);
  }, [languageId, loadTopicsForLanguage, usePresetTier1]);

  useEffect(() => {
    if (!usePresetTier1 || topicMode !== "catalog" || languages.length === 0) return;
    const pyId = findPythonLanguageId(languages);
    if (pyId && languageId !== pyId) {
      setLanguageId(pyId);
    }
  }, [usePresetTier1, topicMode, languages, languageId]);

  const applySelectedPreset = useCallback(
    (presetName) => {
      const preset = getPresetByName(presetName);
      if (!preset) return;
      const applied = applyPreset(preset, topics);
      setSelectedPresetName(presetName);
      setSelectedTopicIds(applied.selectedTopicIds);
      setPerTopicCounts(applied.perTopicCounts);
      setLevel(applied.level);
      setAllocationMode("per-topic");
      setTypeMcq(true);
      setTypeCoding(true);
      setTypeSubjective(false);
      setIsTimed(true);
      setDurationMinutes(applied.durationMinutes);
      setPresetMissingTopics(applied.missingTopicNames);
      setError(null);
    },
    [topics]
  );

  // Re-match preset topic ids when catalog topics finish loading (or after seeding).
  useEffect(() => {
    if (!usePresetTier1 || !selectedPresetName || loadingTopics) return;
    applySelectedPreset(selectedPresetName);
  }, [usePresetTier1, selectedPresetName, topics, loadingTopics, applySelectedPreset]);

  const handlePresetTier1Toggle = (enabled) => {
    setUsePresetTier1(enabled);
    setError(null);
    if (!enabled) {
      setSelectedPresetName(null);
      setShowDistributionEditor(false);
      setPresetMissingTopics([]);
      setCertificateEnabled(false);
      return;
    }
    setAllocationMode("per-topic");
    setShowDistributionEditor(false);
    setSelectedPresetName(null);
    setSelectedTopicIds([]);
    setPerTopicCounts({});
  };

  const handleSelectPresetCard = (presetName) => {
    applySelectedPreset(presetName);
    setShowDistributionEditor(true);
  };

  const handleResetPresetDistribution = () => {
    if (selectedPresetName) {
      applySelectedPreset(selectedPresetName);
    }
  };

  const addPresetTopic = (topicId) => {
    const sid = String(topicId);
    if (!sid || selectedTopicIds.includes(sid)) return;
    setSelectedTopicIds((prev) => [...prev, sid]);
    setPerTopicCounts((prev) => ({
      ...prev,
      [sid]: prev[sid] || { mcq: 0, coding: 0, subjective: 0 },
    }));
  };

  const removePresetTopic = (topicId) => {
    const sid = String(topicId);
    setSelectedTopicIds((prev) => prev.filter((x) => x !== sid));
    setPerTopicCounts((prev) => {
      const next = { ...prev };
      delete next[sid];
      return next;
    });
  };

  const toggleTopic = (id) => {
    const sid = String(id);
    setSelectedTopicIds((prev) => {
      const isAdding = !prev.includes(sid);
      if (isAdding) {
        setPerTopicCounts((old) => ({
          ...old,
          [sid]: old[sid] || { mcq: 1, coding: 0, subjective: 0 },
        }));
      }
      return isAdding ? [...prev, sid] : prev.filter((x) => x !== sid);
    });
  };

  const handlePerTopicCountChange = (topicId, type, val) => {
    const count = Math.min(30, Math.max(0, Number.parseInt(val, 10) || 0));
    setPerTopicCounts((prev) => ({
      ...prev,
      [topicId]: {
        ...(prev[topicId] || { mcq: 0, coding: 0, subjective: 0 }),
        [type]: count,
      },
    }));
  };


  const languageCodeForGenerate = useMemo(() => {
    if (topicMode === "catalog" && languageId) {
      const l = languages.find((x) => String(x.id) === String(languageId));
      return l?.code ? String(l.code).trim() : null;
    }
    if (topicMode === "custom" && typeCoding && customCodeLanguageId) {
      const l = languages.find((x) => String(x.id) === String(customCodeLanguageId));
      return l?.code ? String(l.code).trim() : null;
    }
    return null;
  }, [topicMode, languageId, typeCoding, customCodeLanguageId, languages]);

  /** Catalog language display name stored for Admin → Assessments (not the code). */
  const languageNameForGenerate = useMemo(() => {
    if (topicMode === "catalog" && languageId) {
      const l = languages.find((x) => String(x.id) === String(languageId));
      const name = (l?.name || "").trim();
      return name || null;
    }
    if (topicMode === "custom" && typeCoding && customCodeLanguageId) {
      const l = languages.find((x) => String(x.id) === String(customCodeLanguageId));
      const name = (l?.name || "").trim();
      return name || null;
    }
    return null;
  }, [topicMode, languageId, typeCoding, customCodeLanguageId, languages]);

  const topicNamesForGenerate = useMemo(() => {
    if (topicMode === "catalog") {
      const names = [];
      for (const id of selectedTopicIds) {
        const row = topicById[String(id)];
        const n = row ? String(row.name ?? "").trim() : "";
        if (n) names.push(n);
      }
      return names;
    }
    const t = customTopic.trim();
    if (!t) return [];
    const one = t.length > 200 ? `${t.slice(0, 200)}…` : t;
    return [one];
  }, [topicMode, selectedTopicIds, topicById, customTopic]);

  const totalCounts = useMemo(() => {
    let mcq = 0;
    let coding = 0;
    let subjective = 0;
    for (const id of selectedTopicIds) {
      const counts = perTopicCounts[id] || { mcq: 0, coding: 0, subjective: 0 };
      mcq += counts.mcq || 0;
      coding += counts.coding || 0;
      subjective += counts.subjective || 0;
    }
    return { mcq, coding, subjective };
  }, [selectedTopicIds, perTopicCounts]);

  const totalQuestionCount = useMemo(
    () => totalCounts.mcq + totalCounts.coding + totalCounts.subjective,
    [totalCounts]
  );

  useEffect(() => {
    if (questionSource !== "recycle_then_generate") {
      setBankAvailability(null);
      return;
    }
    if (
      topicMode !== "catalog" ||
      topicNamesForGenerate.length === 0 ||
      totalQuestionCount === 0
    ) {
      setBankAvailability(null);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const params = new URLSearchParams();
        for (const name of topicNamesForGenerate) {
          params.append("topic_names", name);
        }
        params.set("difficulty", effectiveLevel);
        params.set("n_requested", String(totalQuestionCount));
        const eid = targetEmployeeId.trim();
        if (eid) params.set("exclude_employee_id", eid);
        const data = await apiFetch(`/admin/question-bank/availability?${params}`);
        if (!cancelled) setBankAvailability(data);
      } catch {
        if (!cancelled) setBankAvailability(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [
    questionSource,
    topicNamesForGenerate,
    effectiveLevel,
    totalQuestionCount,
    targetEmployeeId,
    topicMode,
  ]);

  const buildTypesAndCounts = useMemo(() => {
    if (topicMode === "catalog" && (usePresetTier1 || allocationMode === "per-topic")) {
      const types = [];
      const questions_per_type = {};
      const { mcq, coding, subjective } = totalCounts;
      if (mcq > 0) {
        types.push("mcq");
        questions_per_type.mcq = mcq;
      }
      if (coding > 0) {
        types.push("coding");
        questions_per_type.coding = coding;
      }
      if (subjective > 0) {
        types.push("subjective");
        questions_per_type.subjective = subjective;
      }
      return { types, questions_per_type };
    }

    const types = [];
    const questions_per_type = {};
    if (typeMcq) {
      types.push("mcq");
      questions_per_type.mcq = Math.min(30, Math.max(1, countMcq));
    }
    if (typeCoding) {
      types.push("coding");
      questions_per_type.coding = Math.min(30, Math.max(1, countCoding));
    }
    if (typeSubjective) {
      types.push("subjective");
      questions_per_type.subjective = Math.min(30, Math.max(1, countSubjective));
    }
    return { types, questions_per_type };
  }, [topicMode, usePresetTier1, allocationMode, totalCounts, typeMcq, typeCoding, typeSubjective, countMcq, countCoding, countSubjective]);


  const handleGenerate = async () => {
    setError(null);
    setLoading(true);
    try {
      const { types, questions_per_type } = buildTypesAndCounts;
      if (types.length === 0) {
        throw new Error("Select at least one question type and set a count of at least 1 for each.");
      }
      if (topicMode === "custom" && !customTopic.trim()) {
        throw new Error("Enter a custom topic.");
      }
      if (topicMode === "catalog") {
        if (!languageId) {
          throw new Error("Select a language.");
        }
        if (selectedTopicRows.length === 0) {
          throw new Error("Select at least one topic from the list.");
        }
        if (!resolvedTopic.trim()) {
          throw new Error("Could not build topic text for the API.");
        }
      }
      if (usePresetTier1 && presetMissingTopics.length > 0) {
        throw new Error(
          `Catalog is missing preset topics. Run: python3 scripts/seed_sample_catalog.py\nMissing: ${presetMissingTopics.join("; ")}`
        );
      }
      if (usePresetTier1 && !selectedPresetName) {
        throw new Error("Select a Tier 1 preset: Beginner, Intermediate, or Advanced.");
      }

      // Build per_topic_config when using per-topic allocation mode
      let per_topic_config = {};
      if (
        topicMode === "catalog" &&
        (usePresetTier1 || allocationMode === "per-topic") &&
        selectedTopicIds.length > 0
      ) {
        for (const id of selectedTopicIds) {
          const row = topicById[String(id)];
          if (!row) continue;
          const counts = perTopicCounts[id] || { mcq: 0, coding: 0, subjective: 0 };
          per_topic_config[row.name] = {
            mcq: counts.mcq || 0,
            coding: counts.coding || 0,
            subjective: counts.subjective || 0,
          };
        }
      }

      // Build the shared payload used for both preview and (eventually) confirm
      const previewPayload = {
        topic: resolvedTopic,
        level: effectiveLevel,
        types,
        questions_per_type,
        ...(languageCodeForGenerate ? { language_code: languageCodeForGenerate } : {}),
        ...(languageNameForGenerate ? { language_label: languageNameForGenerate } : {}),
        topic_names: topicNamesForGenerate,
        ...(Object.keys(per_topic_config).length > 0 ? { per_topic_config } : {}),
        is_timed: isTimed,
        ...(isTimed
          ? {
              duration_minutes: durationMinutes,
              notebook_grace_minutes: notebookGraceMinutes,
            }
          : {}),
        allow_pyodide_paste: allowPyodidePaste,
        include_sample_test_cases: includeSampleTestCases,
        include_beginner_coding_hints: includeBeginnerCodingHints,
        certificate_enabled: usePresetTier1 && certificateEnabled,
        question_source: questionSource,
        generation_provider: generationProvider,
        ...(targetEmployeeId.trim()
          ? { target_employee_id: targetEmployeeId.trim() }
          : {}),
      };

      const data = await apiFetch("/admin/preview-questions", {
        method: "POST",
        authRole: "admin",
        body: JSON.stringify(previewPayload),
      });

      const previewMeta = data.meta ?? null;
      const questions = data.questions ?? [];

      // 100% bank-sourced recycle: skip review and save immediately
      if (isFullBankRecycle(previewMeta, questionSource)) {
        const saved = await apiFetch("/admin/confirm-assessment", {
          method: "POST",
          authRole: "admin",
          body: JSON.stringify(buildConfirmBody(previewPayload, questions)),
        });
        navigate("/admin/review", {
          state: {
            savedId: saved.assessment_id,
            savedStats: {
              bank: saved.bank_sourced_count ?? previewMeta.bank_sourced_count ?? 0,
              llm: saved.llm_generated_count ?? 0,
              messages: saved.shortage_messages ?? [],
            },
            recycledOnly: true,
          },
        });
        return;
      }

      navigate("/admin/review", {
        state: {
          questions,
          confirmPayload: previewPayload,
          previewMeta,
        },
      });
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const catalogReady =
    topicMode === "custom" ||
    (Boolean(languageId) &&
      !loadingTopics &&
      (usePresetTier1 ? topics.length > 0 : selectedTopicRows.length > 0));

  const hasAnyQuestions = useMemo(() => {
    if (topicMode === "catalog" && (usePresetTier1 || allocationMode === "per-topic")) {
      return totalCounts.mcq > 0 || totalCounts.coding > 0 || totalCounts.subjective > 0;
    }
    return typeMcq || typeCoding || typeSubjective;
  }, [topicMode, usePresetTier1, allocationMode, totalCounts, typeMcq, typeCoding, typeSubjective]);

  const generationProviderReady =
    generationProvider === "gemini"
      ? geminiConfigured !== false
      : groqConfigured !== false;

  const canGenerate =
    !loading &&
    generationProviderReady &&
    (topicMode === "catalog" ? catalogReady : customTopic.trim().length > 0) &&
    hasAnyQuestions &&
    (!usePresetTier1 || (selectedPresetName && presetMissingTopics.length === 0));


  return (
    <div className="page page--wide">
      <header className="header">
        <p className="page-eyebrow">Administrator</p>
        <h1>Generate assessment</h1>
        <p className="muted">
          Choose level, then catalog language and one or more topics (or a custom description).
          Set how many questions you want for each type. Assessments are stored in PostgreSQL.
        </p>
        <p className="muted" style={{ marginTop: "0.65rem" }}>
          <Link to="/admin/assessments">Browse assessments</Link>
          {" · "}
          <Link to="/admin/question-bank">Question bank</Link>
          {" · "}
          <Link to="/admin/catalog">Catalog</Link>
          {" · "}
          <Link to="/admin/submissions">Submissions</Link>
        </p>
      </header>

      <section className="card">
        <h2>Configuration</h2>
        <div className="bank-source-block">
          <h3 className="topic-preview-title">Generation model</h3>
          <div className="radio-group" role="radiogroup" aria-label="Generation model">
          <label className="radio-row">
            <input
              type="radio"
              name="generationProvider"
              value="grok"
              checked={generationProvider === "grok"}
              onChange={() => setGenerationProvider("grok")}
              disabled={groqConfigured === false}
            />
            Groq (Grok) — default
          </label>
          <label className="radio-row">
            <input
              type="radio"
              name="generationProvider"
              value="gemini"
              checked={generationProvider === "gemini"}
              onChange={() => setGenerationProvider("gemini")}
              disabled={geminiConfigured === false}
            />
            Gemini{geminiConfigured === false ? " (API key not configured)" : ""}
          </label>
          </div>
          <p className="muted small-print" style={{ marginTop: "0.5rem" }}>
            Used only when generating new questions. Answer grading always uses Groq.
          </p>
        </div>
        {topicMode === "catalog" && (
          <div className="bank-source-block">
            <h3 className="topic-preview-title">Question source</h3>
            <div className="radio-group" role="radiogroup" aria-label="Question source">
            <label className="radio-row">
              <input
                type="radio"
                name="questionSource"
                value="generate_new"
                checked={questionSource === "generate_new"}
                onChange={() => setQuestionSource("generate_new")}
              />
              Generate new (LLM only)
            </label>
            <label className="radio-row">
              <input
                type="radio"
                name="questionSource"
                value="recycle_then_generate"
                checked={questionSource === "recycle_then_generate"}
                onChange={() => setQuestionSource("recycle_then_generate")}
              />
              Recycle then generate (bank first, LLM for any shortfall)
            </label>
            </div>
            {questionSource === "recycle_then_generate" && (
              <>
                <label style={{ display: "block", marginTop: "0.75rem" }}>
                  Exclude mastered questions for employee (optional)
                  <input
                    type="text"
                    value={targetEmployeeId}
                    onChange={(e) => setTargetEmployeeId(e.target.value)}
                    placeholder="e.g. E1001"
                    style={{ display: "block", width: "100%", marginTop: "0.25rem" }}
                  />
                </label>
                {bankAvailability && (
                  <p className="muted" style={{ marginTop: "0.75rem" }} role="status">
                    Bank: <strong>{bankAvailability.available}</strong> of{" "}
                    <strong>{bankAvailability.requested}</strong> questions available
                    {bankAvailability.shortage > 0 ? (
                      <>
                        {" "}
                        — we will generate <strong>{bankAvailability.shortage}</strong> new
                      </>
                    ) : null}
                    .
                  </p>
                )}
              </>
            )}
          </div>
        )}
        <div className="grid">
          {!(usePresetTier1 && topicMode === "catalog") && (
            <label>
              Level
              <select value={level} onChange={(e) => setLevel(e.target.value)}>
                <option value="beginner">Beginner</option>
                <option value="intermediate">Intermediate</option>
                <option value="advanced">Advanced</option>
              </select>
              <span className="muted">Depth and difficulty of questions follow this level.</span>
            </label>
          )}
          <label>
            Content source
            <select
              value={topicMode}
              onChange={(e) => {
                const mode = e.target.value;
                setTopicMode(mode);
                setError(null);
                setSelectedTopicIds([]);
                if (mode === "custom") {
                  setUsePresetTier1(false);
                  setSelectedPresetName(null);
                  setShowDistributionEditor(false);
                }
              }}
            >
              <option value="catalog">Catalog: language + topics</option>
              <option value="custom">Custom free-text topic</option>
            </select>
          </label>
        </div>

        {topicMode === "catalog" && (
          <div className="stack" style={{ marginTop: "1rem" }}>
            <label className="preset-tier1-toggle">
              <input
                type="checkbox"
                checked={usePresetTier1}
                onChange={(e) => handlePresetTier1Toggle(e.target.checked)}
              />
              <span>
                <strong>Preset Tier 1 evaluation (Python)</strong>
                <span className="muted small-print" style={{ display: "block", marginTop: "0.25rem" }}>
                  Standard Beginner / Intermediate / Advanced combos — edit counts and duration before generating.
                </span>
              </span>
            </label>

            <SearchableLanguageSelect
              label="Language"
              inputId="gen-form-lang"
              languages={languages}
              value={languageId}
              onChange={(v) => {
                if (usePresetTier1) return;
                setLanguageId(v);
                setError(null);
              }}
              required
              disabled={loadingLanguages || usePresetTier1}
              hint={
                usePresetTier1
                  ? "Locked to Python for Tier 1 presets."
                  : "Search by name, code, or id. Add languages under Admin → Catalog if the list is empty."
              }
            />

            {usePresetTier1 && (
              <div className="tier1-preset-panel" role="group" aria-label="Tier 1 preset selection">
                <h3 className="tier1-preset-panel__title">Choose evaluation combo</h3>
                <div className="tier1-preset-cards">
                  {tier1Presets.map((preset) => {
                    const cardMcq = selectedPresetName === preset.name
                      ? totalCounts.mcq
                      : (preset.topics || []).reduce((s, t) => s + (t.mcq || 0), 0);
                    const cardCoding = selectedPresetName === preset.name
                      ? totalCounts.coding
                      : (preset.topics || []).reduce((s, t) => s + (t.coding || 0), 0);
                    const selected = selectedPresetName === preset.name;
                    return (
                      <button
                        key={preset.name}
                        type="button"
                        className={`tier1-preset-card${selected ? " tier1-preset-card--selected" : ""}`}
                        onClick={() => handleSelectPresetCard(preset.name)}
                        aria-pressed={selected}
                      >
                        <span className="tier1-preset-card__name">{preset.name}</span>
                        <span className="tier1-preset-card__meta muted small-print">
                          {cardMcq} MCQ · {cardCoding} coding · {cardMcq + cardCoding} total
                        </span>
                        <span className="tier1-preset-card__duration muted small-print">
                          Suggested ~{preset.target_duration_minutes} min (timed, editable below)
                        </span>
                        <p className="tier1-preset-card__desc small-print">{preset.description}</p>
                        <table className="tier1-preset-card__table">
                          <thead>
                            <tr>
                              <th scope="col">Topic</th>
                              <th scope="col">MCQ</th>
                              <th scope="col">Code</th>
                            </tr>
                          </thead>
                          <tbody>
                            {(preset.topics || []).map((t) => (
                              <tr key={t.topic_name}>
                                <td>{t.topic_name.replace(/^Tier 1 - /, "")}</td>
                                <td>{t.mcq}</td>
                                <td>{t.coding}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </button>
                    );
                  })}
                </div>

                {selectedPresetName && (
                  <div className="tier1-preset-actions">
                    <button
                      type="button"
                      className="tier1-action-btn"
                      onClick={() => setShowDistributionEditor((v) => !v)}
                    >
                      {showDistributionEditor ? "Hide distribution editor" : "Edit question distribution"}
                    </button>
                    {showDistributionEditor && (
                      <button
                        type="button"
                        className="tier1-action-btn"
                        onClick={handleResetPresetDistribution}
                      >
                        Reset to {selectedPresetName} preset
                      </button>
                    )}
                    <p className="tier1-preset-totals muted" aria-live="polite">
                      Current: <strong>{totalCounts.mcq} MCQ</strong> ·{" "}
                      <strong>{totalCounts.coding} coding</strong> ·{" "}
                      <strong>{totalCounts.mcq + totalCounts.coding + totalCounts.subjective} total</strong>
                      {effectiveLevel && (
                        <> · Level <strong>{effectiveLevel}</strong></>
                      )}
                    </p>
                  </div>
                )}

                {presetMissingTopics.length > 0 && (
                  <div className="error" role="alert" style={{ marginTop: "0.75rem" }}>
                    Missing catalog topics. Run{" "}
                    <code>python3 scripts/seed_sample_catalog.py</code>
                    <ul style={{ margin: "0.5rem 0 0 1rem" }}>
                      {presetMissingTopics.map((n) => (
                        <li key={n}>{n}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {selectedPresetName && (
                  <label className="preset-tier1-toggle tier1-certificate-toggle">
                    <input
                      type="checkbox"
                      checked={certificateEnabled}
                      onChange={(e) => setCertificateEnabled(e.target.checked)}
                    />
                    <span>
                      <strong>
                        Include Certificate Achievement at the end of this assessment
                      </strong>
                      <span
                        className="muted small-print"
                        style={{ display: "block", marginTop: "0.25rem", lineHeight: 1.5 }}
                      >
                        Certificate level is set automatically from the{" "}
                        <strong>{selectedPresetName}</strong> tier you selected. Participants who
                        score above 85% can download a completion certificate with their name when
                        they finish.
                      </span>
                    </span>
                  </label>
                )}

                {showDistributionEditor && selectedPresetName && (
                  <div className="tier1-distribution-editor">
                    {selectedTopicRows.length === 0 && (
                      <p className="muted small-print" role="status">
                        Preset topics are not in the catalog yet — add topics below or run{" "}
                        <code>python3 scripts/seed_sample_catalog.py</code>.
                      </p>
                    )}
                    <label className="tier1-add-topic">
                      Add topic from catalog
                      <select
                        defaultValue=""
                        onChange={(e) => {
                          if (e.target.value) {
                            addPresetTopic(e.target.value);
                            e.target.value = "";
                          }
                        }}
                      >
                        <option value="">— Select —</option>
                        {topics
                          .filter((t) => !selectedTopicIds.includes(String(t.id)))
                          .map((t) => (
                            <option key={t.id} value={t.id}>
                              {t.name}
                            </option>
                          ))}
                      </select>
                    </label>
                    {selectedTopicRows.map((t) => {
                      const tid = String(t.id);
                      return (
                        <div key={t.id} className="topic-preview-card">
                          <div className="tier1-distribution-editor__head">
                            <h4 className="topic-preview-h">{t.name}</h4>
                            <button
                              type="button"
                              className="tier1-action-btn tier1-remove-topic"
                              onClick={() => removePresetTopic(t.id)}
                            >
                              Remove
                            </button>
                          </div>
                          <div className="per-topic-inputs">
                            <div className="per-topic-input-group">
                              <span>MCQ:</span>
                              <input
                                type="number"
                                min={0}
                                max={30}
                                value={perTopicCounts[tid]?.mcq ?? 0}
                                onChange={(e) =>
                                  handlePerTopicCountChange(tid, "mcq", e.target.value)
                                }
                              />
                            </div>
                            <div className="per-topic-input-group">
                              <span>Coding:</span>
                              <input
                                type="number"
                                min={0}
                                max={30}
                                value={perTopicCounts[tid]?.coding ?? 0}
                                onChange={(e) =>
                                  handlePerTopicCountChange(tid, "coding", e.target.value)
                                }
                              />
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            )}

            {!usePresetTier1 && languageId && !loadingTopics && topics.length > 0 && (
              <div
                className="topic-pick-card"
                role="group"
                aria-labelledby="topic-pick-title"
              >
                <div className="topic-pick-card__head">
                  <div className="topic-pick-card__title-row">
                    <h3 id="topic-pick-title" className="topic-pick-card__title">
                      Topic selection
                    </h3>
                    {selectedTopicIds.length > 0 && (
                      <span className="topic-pick-card__badge" aria-live="polite">
                        {selectedTopicIds.length} selected
                      </span>
                    )}
                  </div>
                  <p className="topic-pick-card__lead">
                    Choose one or more areas from the catalog. The model uses your choices together as
                    the subject matter for this assessment.
                  </p>
                </div>
                <div
                  className="topic-pick-card__callout"
                  id="topic-pick-callout"
                  role="note"
                >
                  <span className="topic-pick-card__callout-icon" aria-hidden>
                    ⓘ
                  </span>
                  <p>
                    <strong>How it works:</strong> every selected topic is sent in one prompt. Questions
                    may combine ideas across your selections, not only a single line item.
                  </p>
                </div>
                <ul className="topic-pick-list" aria-label="Catalog topics to include">
                  {topics.map((t) => {
                    const idStr = String(t.id);
                    const on = selectedTopicIds.includes(idStr);
                    const refCount = Array.isArray(t.related_documents)
                      ? t.related_documents.length
                      : 0;
                    return (
                      <li key={t.id}>
                        <label
                          className={
                            on ? "topic-pick-item topic-pick-item--on" : "topic-pick-item"
                          }
                        >
                          <input
                            className="topic-pick-item__input"
                            type="checkbox"
                            checked={on}
                            onChange={() => toggleTopic(t.id)}
                          />
                          <span className="topic-pick-item__content">
                            <span className="topic-pick-item__name">
                              {t.name || `Topic #${t.id}`}
                            </span>
                            {refCount > 0 && (
                              <span className="topic-pick-item__meta">
                                {refCount} ref{refCount === 1 ? "" : "s"}
                              </span>
                            )}
                          </span>
                        </label>
                      </li>
                    );
                  })}
                </ul>
              </div>
            )}
            {languageId && loadingTopics && <p className="muted">Loading topics…</p>}
            {languageId && !loadingTopics && topics.length === 0 && (
              <p className="muted" role="status">
                No topics for this language.
              </p>
            )}
          </div>
        )}

        {topicMode === "custom" && (
          <div className="grid" style={{ marginTop: "0.75rem" }}>
            <label>
              Custom topic
              <input
                value={customTopic}
                onChange={(e) => setCustomTopic(e.target.value)}
                placeholder="e.g. Python FastAPI and REST APIs"
              />
            </label>
          </div>
        )}

        {topicMode === "custom" && typeCoding && (
          <div className="stack" style={{ marginTop: "1rem" }}>
            <SearchableLanguageSelect
              label="Programming language (code editor for participants)"
              inputId="gen-form-custom-code-lang"
              languages={languages}
              value={customCodeLanguageId}
              onChange={(v) => {
                setCustomCodeLanguageId(v);
                setError(null);
              }}
              required={false}
              disabled={loadingLanguages}
              hint="If you include coding questions, pick a language to set syntax highlighting. Optional."
            />
          </div>
        )}

        {!usePresetTier1 && topicMode === "catalog" && selectedTopicIds.length > 0 && (
          <div className="allocation-mode-selector" style={{ marginTop: "1rem", marginBottom: "1rem" }}>
            <label style={{ marginBottom: "0.4rem", display: "block" }}>
              Question Distribution
            </label>
            <div className="segmented-control">
              <button
                type="button"
                className={`segmented-control__btn ${allocationMode === "auto" ? "active" : ""}`}
                onClick={() => setAllocationMode("auto")}
              >
                Auto-distribute Questions
              </button>
              <button
                type="button"
                className={`segmented-control__btn ${allocationMode === "per-topic" ? "active" : ""}`}
                onClick={() => setAllocationMode("per-topic")}
              >
                Specify Per Topic
              </button>
            </div>
            <p className="muted small-print" style={{ marginTop: "0.4rem", marginBottom: 0 }}>
              {allocationMode === "auto"
                ? "Generate questions from a pool of selected topics. The AI decides how they are distributed."
                : "Set precise question counts for each chosen topic area individually."}
            </p>
          </div>
        )}

        {!usePresetTier1 && selectedTopicRows.length > 0 && topicMode === "catalog" && (
          <div className="topic-preview" aria-label="Selected topics summary">
            <h3 className="topic-preview-title">Selected topics</h3>
            {selectedTopicRows.map((t) => {
              const docs = Array.isArray(t.related_documents) ? t.related_documents : [];
              return (
                <div key={t.id} className="topic-preview-card">
                  <h4 className="topic-preview-h">{t.name || `Topic #${t.id}`}</h4>
                  
                  {allocationMode === "per-topic" && (
                    <div className="per-topic-inputs">
                      <div className="per-topic-input-group">
                        <span>MCQ:</span>
                        <input
                          type="number"
                          min={0}
                          max={30}
                          value={perTopicCounts[String(t.id)]?.mcq ?? 0}
                          onChange={(e) => handlePerTopicCountChange(String(t.id), "mcq", e.target.value)}
                        />
                      </div>
                      <div className="per-topic-input-group">
                        <span>Coding:</span>
                        <input
                          type="number"
                          min={0}
                          max={30}
                          value={perTopicCounts[String(t.id)]?.coding ?? 0}
                          onChange={(e) => handlePerTopicCountChange(String(t.id), "coding", e.target.value)}
                        />
                      </div>
                      <div className="per-topic-input-group">
                        <span>Subjective:</span>
                        <input
                          type="number"
                          min={0}
                          max={30}
                          value={perTopicCounts[String(t.id)]?.subjective ?? 0}
                          onChange={(e) => handlePerTopicCountChange(String(t.id), "subjective", e.target.value)}
                        />
                      </div>
                    </div>
                  )}

                  {docs.length === 0 ? (
                    <p className="muted small-print" style={{ margin: "0.5rem 0 0" }}>
                      No reference materials linked in the catalog. The topic title is still used in
                      the prompt.
                    </p>
                  ) : (
                    <>
                      <p className="small-print muted" style={{ margin: "0.5rem 0 0.5rem" }}>
                        References ({docs.length})
                      </p>
                      <ul className="topic-preview-reflist">
                        {docs.map((d, idx) => {
                          const title = (d?.title || "Reference").trim() || "Reference";
                          return (
                            <li key={idx}>
                              {d?.url && (
                                <a href={d.url} target="_blank" rel="noreferrer">
                                  {title}
                                </a>
                              )}
                              {d?.path && !d?.url && (
                                <span>
                                  {title} — <code className="cell-id">{d.path}</code>
                                </span>
                              )}
                              {!d?.url && !d?.path && <span>{title}</span>}
                            </li>
                          );
                        })}
                      </ul>
                    </>
                  )}
                </div>
              );
            })}
          </div>
        )}


        {!(usePresetTier1 && topicMode === "catalog") && (
          <>
        <h3 className="generate-subh" style={{ marginTop: "1.25rem" }}>
          Question types and counts
        </h3>
        <p className="muted small-print" style={{ marginTop: 0 }}>
          {topicMode === "catalog" && allocationMode === "per-topic"
            ? "Aggregated counts from individual topics selected above (read-only)."
            : "Enable each type and set how many questions of that type to generate (1–30 each). Counts are independent."}
        </p>
        <div className="type-count-grid">
          <div className="type-count-row">
            <label className="type-count-tog">
              <input
                type="checkbox"
                checked={topicMode === "catalog" && allocationMode === "per-topic" ? totalCounts.mcq > 0 : typeMcq}
                onChange={(e) => setTypeMcq(e.target.checked)}
                disabled={topicMode === "catalog" && allocationMode === "per-topic"}
              />{" "}
              MCQ
            </label>
            <label className="type-count-num">
              Count
              <input
                type="number"
                min={1}
                max={30}
                value={topicMode === "catalog" && allocationMode === "per-topic" ? totalCounts.mcq : countMcq}
                onChange={(e) =>
                  setCountMcq(Math.min(30, Math.max(1, Number.parseInt(e.target.value, 10) || 1)))
                }
                disabled={topicMode === "catalog" && allocationMode === "per-topic" ? true : !typeMcq}
              />
            </label>
          </div>
          <div className="type-count-row">
            <label className="type-count-tog">
              <input
                type="checkbox"
                checked={topicMode === "catalog" && allocationMode === "per-topic" ? totalCounts.coding > 0 : typeCoding}
                onChange={(e) => setTypeCoding(e.target.checked)}
                disabled={topicMode === "catalog" && allocationMode === "per-topic"}
              />{" "}
              Coding
            </label>
            <label className="type-count-num">
              Count
              <input
                type="number"
                min={1}
                max={30}
                value={topicMode === "catalog" && allocationMode === "per-topic" ? totalCounts.coding : countCoding}
                onChange={(e) =>
                  setCountCoding(
                    Math.min(30, Math.max(1, Number.parseInt(e.target.value, 10) || 1))
                  )
                }
                disabled={topicMode === "catalog" && allocationMode === "per-topic" ? true : !typeCoding}
              />
            </label>
          </div>
          <div className="type-count-row">
            <label className="type-count-tog">
              <input
                type="checkbox"
                checked={topicMode === "catalog" && allocationMode === "per-topic" ? totalCounts.subjective > 0 : typeSubjective}
                onChange={(e) => setTypeSubjective(e.target.checked)}
                disabled={topicMode === "catalog" && allocationMode === "per-topic"}
              />{" "}
              Subjective
            </label>
            <label className="type-count-num">
              Count
              <input
                type="number"
                min={1}
                max={30}
                value={topicMode === "catalog" && allocationMode === "per-topic" ? totalCounts.subjective : countSubjective}
                onChange={(e) =>
                  setCountSubjective(
                    Math.min(30, Math.max(1, Number.parseInt(e.target.value, 10) || 1))
                  )
                }
                disabled={topicMode === "catalog" && allocationMode === "per-topic" ? true : !typeSubjective}
              />
            </label>
          </div>
        </div>
          </>
        )}

        {catalogHint && !usePresetTier1 && (
          <p className="muted" role="status" style={{ marginTop: "0.75rem" }}>
            {catalogHint}
          </p>
        )}

        <div
          className="timed-assessment-config"
          style={{
            marginTop: "1.25rem",
            padding: "1rem 1.1rem",
            borderRadius: "10px",
            border: "1px solid rgba(0,0,0,0.1)",
            background: "rgba(0,0,0,0.02)",
          }}
        >
          <label className="type-count-tog" style={{ display: "block", marginBottom: "0.75rem" }}>
            <input
              type="checkbox"
              checked={isTimed}
              onChange={(e) => setIsTimed(e.target.checked)}
            />{" "}
            <strong>Timed assessment</strong>
          </label>
          {isTimed && (
            <div className="row" style={{ gap: "12px", flexWrap: "wrap" }}>
              <label className="type-count-num">
                Duration (minutes)
                <input
                  type="number"
                  min={1}
                  value={durationMinutes}
                  onChange={(e) => {
                    const n = Number.parseInt(e.target.value, 10);
                    setDurationMinutes(Number.isFinite(n) && n >= 1 ? n : 1);
                  }}
                />
              </label>
              <label className="type-count-num">
                Notebook upload grace (minutes)
                <input
                  type="number"
                  min={0}
                  value={notebookGraceMinutes}
                  onChange={(e) => {
                    const n = Number.parseInt(e.target.value, 10);
                    setNotebookGraceMinutes(Number.isFinite(n) && n >= 0 ? n : 0);
                  }}
                />
              </label>
            </div>
          )}
          {isTimed && (
            <p className="muted small-print" style={{ margin: "0.65rem 0 0 0", lineHeight: 1.5 }}>
              {usePresetTier1 && selectedPresetName
                ? `Suggested duration for ${selectedPresetName} is pre-filled — change minutes here if needed. `
                : null}
              Timer starts when the participant loads the test. At time zero, answers auto-submit.
              Grace minutes allow uploading the Jupyter notebook after the main timer ends.
            </p>
          )}
        </div>

        <div
          className="pyodide-paste-config"
          style={{
            marginTop: "1rem",
            padding: "0.85rem 1.1rem",
            borderRadius: "10px",
            border: "1px solid rgba(0,0,0,0.1)",
            background: "rgba(0,0,0,0.02)",
          }}
        >
          <label className="type-count-tog" style={{ display: "block" }}>
            <input
              type="checkbox"
              checked={allowPyodidePaste}
              onChange={(e) => setAllowPyodidePaste(e.target.checked)}
            />{" "}
            <strong>Allow copy-paste in Pyodide terminal</strong>
          </label>
          <p className="muted small-print" style={{ margin: "0.5rem 0 0 0", lineHeight: 1.5 }}>
            Off by default. When enabled, participants can paste into the in-browser coding editor
            (Pyodide / shell). MCQ copy blocking is unchanged.
          </p>
        </div>

        <div
          className="stage9-generation-config"
          style={{
            marginTop: "1rem",
            padding: "0.85rem 1.1rem",
            borderRadius: "10px",
            border: "1px solid rgba(0,0,0,0.1)",
            background: "rgba(0,0,0,0.02)",
          }}
        >
          <label className="type-count-tog" style={{ display: "block", marginBottom: "0.65rem" }}>
            <input
              type="checkbox"
              checked={includeSampleTestCases}
              onChange={(e) => setIncludeSampleTestCases(e.target.checked)}
            />{" "}
            <strong>Include test cases in some coding questions</strong>
          </label>
          <p className="muted small-print" style={{ margin: "0 0 0.85rem 0", lineHeight: 1.5 }}>
            Off by default. When enabled, function/class coding items may include a few sample
            input → output examples for self-validation (not every edge case).
          </p>
          <label className="type-count-tog" style={{ display: "block" }}>
            <input
              type="checkbox"
              checked={includeBeginnerCodingHints}
              onChange={(e) => setIncludeBeginnerCodingHints(e.target.checked)}
            />{" "}
            <strong>Include hints for beginner coding questions</strong>
          </label>
          <p className="muted small-print" style={{ margin: "0.5rem 0 0 0", lineHeight: 1.5 }}>
            Off by default. Short nudges only — never the full answer. Applies to beginner level
            coding questions when generated.
          </p>
        </div>

        <div style={{ marginTop: "1.1rem" }}>
          <button type="button" className="primary" onClick={handleGenerate} disabled={!canGenerate}>
            {loading ? "Working…" : "Generate assessment"}
          </button>
        </div>
      </section>

      {error && (
        <div className="error" role="alert">
          {error}
        </div>
      )}
    </div>
  );
}
