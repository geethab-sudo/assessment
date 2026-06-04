"""Tier 1 preset topic names must exist in seed catalog."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_PRESETS_PATH = _ROOT / "frontend" / "src" / "data" / "tier1EvaluationPresets.json"


def _seed_tier1_topic_names() -> set[str]:
    from scripts.seed_sample_catalog import SAMPLE

    names: set[str] = set()
    for block in SAMPLE:
        if block.get("code") != "py":
            continue
        for t in block.get("topics") or []:
            names.add(t["name"])
    return names


class TestTier1Presets(unittest.TestCase):
    def test_preset_topic_names_in_seed(self) -> None:
        data = json.loads(_PRESETS_PATH.read_text(encoding="utf-8"))
        seed_names = _seed_tier1_topic_names()
        missing: list[str] = []
        for preset in data.get("presets") or []:
            for row in preset.get("topics") or []:
                tname = (row.get("topic_name") or "").strip()
                if tname and tname not in seed_names:
                    missing.append(f"{preset.get('name')}: {tname}")
        self.assertEqual(missing, [], f"Topics not in seed: {missing}")

    def test_preset_totals_are_25(self) -> None:
        data = json.loads(_PRESETS_PATH.read_text(encoding="utf-8"))
        for preset in data.get("presets") or []:
            mcq = sum(int(t.get("mcq") or 0) for t in preset.get("topics") or [])
            coding = sum(int(t.get("coding") or 0) for t in preset.get("topics") or [])
            self.assertEqual(mcq, 15, preset.get("name"))
            self.assertEqual(coding, 10, preset.get("name"))
            self.assertEqual(mcq + coding, 25, preset.get("name"))

    def test_preset_durations(self) -> None:
        data = json.loads(_PRESETS_PATH.read_text(encoding="utf-8"))
        expected = {"Beginner": 60, "Intermediate": 90, "Advanced": 120}
        for preset in data.get("presets") or []:
            self.assertEqual(
                preset.get("target_duration_minutes"),
                expected[preset["name"]],
            )


if __name__ == "__main__":
    unittest.main()
