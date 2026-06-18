"""Assessment ID generation and validation (``services.ids``).

Covers the ``ASM-XXXXXXXX`` public format, uniqueness, backward-compatible
UUID acceptance for legacy rows, and strict rejection of malformed IDs.
See TEST_GUIDE.md § IDs and low-level utilities.
"""

from __future__ import annotations

import unittest
import uuid

from services.ids import (
    generate_assessment_id,
    is_valid_assessment_id,
    normalize_assessment_id,
)


class TestAssessmentIds(unittest.TestCase):
    """Public assessment identifiers must be stable, unique, and validated."""

    def test_generate_format(self) -> None:
        """New IDs match ASM- plus eight Crockford base32 characters."""
        aid = generate_assessment_id()
        self.assertRegex(aid, r"^ASM-[0-9A-Z]{8}$")

    def test_generate_unique(self) -> None:
        """100 consecutive generations must not collide."""
        ids = {generate_assessment_id() for _ in range(100)}
        self.assertEqual(len(ids), 100)

    def test_accepts_legacy_uuid(self) -> None:
        """Pre-migration UUID primary keys remain valid after normalization."""
        legacy = str(uuid.uuid4())
        self.assertTrue(is_valid_assessment_id(legacy))
        self.assertEqual(normalize_assessment_id(f"  {legacy}  "), legacy)

    def test_accepts_asm_id(self) -> None:
        """Canonical ASM IDs pass validation; whitespace is trimmed."""
        self.assertTrue(is_valid_assessment_id("ASM-A8DK2PQX"))
        self.assertEqual(normalize_assessment_id(" ASM-A8DK2PQX "), "ASM-A8DK2PQX")

    def test_rejects_invalid_ids(self) -> None:
        """Malformed, lowercase, or overlong IDs are rejected; normalize raises."""
        for bad in ("", "ASM-short", "asm-a8dk2pqx", "ASM-A8DK2PQX-extra", "not-a-uuid"):
            self.assertFalse(is_valid_assessment_id(bad))
        with self.assertRaises(ValueError):
            normalize_assessment_id("ASM-badchars")


if __name__ == "__main__":
    unittest.main()
