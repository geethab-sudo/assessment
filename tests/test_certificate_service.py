"""Certificate layout calibration and rendering."""

from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from services.certificate_service import (  # noqa: E402
    _font_cache,
    discover_template_filenames,
    format_issue_date,
    is_template_calibrated,
    issue_certificate,
    list_certificate_templates,
    list_employee_certificates,
    load_layout,
    normalize_level,
    record_certificate_issued,
    render_certificate,
    render_certificate_template,
    score_qualifies_for_certificate,
    template_filename_for_level,
)


class TestCertificateService(unittest.TestCase):
    def test_normalize_level(self) -> None:
        self.assertEqual(normalize_level("Beginner"), "beginner")

    def test_score_threshold(self) -> None:
        self.assertTrue(score_qualifies_for_certificate(0.86))
        self.assertFalse(score_qualifies_for_certificate(0.85))

    def test_layout_has_templates(self) -> None:
        layout = load_layout()
        self.assertIn("templates", layout)
        self.assertIn("level_template", layout)
        self.assertIn("Begineer.jpg", layout["templates"])

    def test_tier1_templates_calibrated(self) -> None:
        for name in ("Begineer.jpg", "Intermediate.jpg", "Advanced.jpg"):
            self.assertTrue(is_template_calibrated(name), name)

    def test_templates_exist(self) -> None:
        for lv in ("beginner", "intermediate", "advanced"):
            self.assertTrue((Path(_ROOT / "certificates") / template_filename_for_level(lv)).is_file())

    def test_render_produces_jpeg_bytes(self) -> None:
        result = render_certificate(
            "beginner",
            "Test Student",
            issue_date=date(2026, 6, 22),
        )
        self.assertTrue(result.image_bytes.startswith(b"\xff\xd8"))
        self.assertIn("beginner", result.filename)
        self.assertGreater(len(result.image_bytes), 10_000)

    def test_date_format(self) -> None:
        self.assertEqual(format_issue_date(date(2026, 6, 22)), "June 22, 2026")

    def test_discover_excludes_signature(self) -> None:
        names = discover_template_filenames()
        self.assertNotIn("signature.jpg", names)
        self.assertNotIn("signature.png", names)

    def test_list_templates(self) -> None:
        items = list_certificate_templates()
        self.assertGreaterEqual(len(items), 3)

    def test_preview_name_font_size_affects_render(self) -> None:
        layout = load_layout()["templates"]["Begineer.jpg"]
        small = dict(layout)
        small["display_name"] = {**layout["display_name"], "size": 24}
        large = dict(layout)
        large["display_name"] = {**layout["display_name"], "size": 72}
        _font_cache.clear()
        small_img = render_certificate_template(
            "Begineer.jpg", "Font Size Test", fields=small
        )
        _font_cache.clear()
        large_img = render_certificate_template(
            "Begineer.jpg", "Font Size Test", fields=large
        )
        self.assertNotEqual(small_img.image_bytes, large_img.image_bytes)

    def test_record_certificate_includes_language_and_level(self) -> None:
        issued_id = record_certificate_issued(
            employee_id="E-cert-test",
            display_name="Language Test",
            level="intermediate",
            language_code="py",
            language_label="Python",
            score=0.91,
            issued_by="auto",
        )
        self.assertGreater(issued_id, 0)
        rows = list_employee_certificates("E-cert-test")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["level"], "intermediate")
        self.assertEqual(rows[0]["language_code"], "py")
        self.assertEqual(rows[0]["language_label"], "Python")
        self.assertEqual(rows[0]["display_name"], "Language Test")


class TestUncalibratedDetection(unittest.TestCase):
    def test_incomplete_layout_not_calibrated(self) -> None:
        self.assertFalse(
            is_template_calibrated(
                "fake.jpg",
                {"templates": {"fake.jpg": {"display_name": {"x_ratio": 0.5}}}},
            )
        )


if __name__ == "__main__":
    unittest.main()
