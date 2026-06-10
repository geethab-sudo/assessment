import presetData from "../data/tier1EvaluationPresets.json";

export const TIER1_PRESET_DATA = presetData;

export function getTier1Presets() {
  return presetData.presets ?? [];
}

export function getPresetByName(name) {
  return getTier1Presets().find((p) => p.name === name) ?? null;
}

/** API level string from preset display name. */
export function presetNameToLevel(name) {
  return (name || "").trim().toLowerCase();
}

export function findPythonLanguageId(languages) {
  const code = (presetData.language_code || "py").toLowerCase();
  const row = (languages || []).find(
    (l) => String(l.code || "").trim().toLowerCase() === code
  );
  return row ? String(row.id) : "";
}

/**
 * Apply preset rows to catalog topics by exact topic_name match.
 * @returns {{ selectedTopicIds: string[], perTopicCounts: Record<string, {mcq,coding,subjective}>, level: string, durationMinutes: number, missingTopicNames: string[] }}
 */
export function applyPreset(preset, catalogTopics) {
  const byName = Object.fromEntries(
    (catalogTopics || []).map((t) => [(t.name || "").trim(), t])
  );
  const selectedTopicIds = [];
  const perTopicCounts = {};
  const missingTopicNames = [];

  for (const row of preset.topics || []) {
    const tname = (row.topic_name || "").trim();
    const cat = byName[tname];
    if (!cat) {
      missingTopicNames.push(tname);
      continue;
    }
    const id = String(cat.id);
    if (!selectedTopicIds.includes(id)) {
      selectedTopicIds.push(id);
    }
    perTopicCounts[id] = {
      mcq: Number(row.mcq) || 0,
      coding: Number(row.coding) || 0,
      subjective: 0,
    };
  }

  return {
    selectedTopicIds,
    perTopicCounts,
    level: presetNameToLevel(preset.name),
    durationMinutes: preset.target_duration_minutes ?? 60,
    missingTopicNames,
  };
}

export function validatePresetAgainstCatalog(preset, catalogTopics) {
  const { missingTopicNames } = applyPreset(preset, catalogTopics);
  return {
    ok: missingTopicNames.length === 0,
    missingTopicNames,
  };
}

export function sumPresetTotals(perTopicCounts) {
  let mcq = 0;
  let coding = 0;
  let subjective = 0;
  for (const counts of Object.values(perTopicCounts || {})) {
    mcq += counts.mcq || 0;
    coding += counts.coding || 0;
    subjective += counts.subjective || 0;
  }
  return { mcq, coding, subjective, total: mcq + coding + subjective };
}

