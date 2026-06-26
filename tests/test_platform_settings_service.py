"""Platform settings (certificate issuer organization)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from services.platform_settings_service import (  # noqa: E402
    DEFAULT_ORGANIZATION_NAME,
    get_certificate_issuer_settings,
    save_certificate_issuer_settings,
)


class TestPlatformSettingsService(unittest.TestCase):
    def test_default_organization_name(self) -> None:
        with patch("services.database.coll") as coll_mock:
            coll_mock.return_value.find_one.return_value = None
            settings = get_certificate_issuer_settings()
        self.assertEqual(settings["organization_name"], DEFAULT_ORGANIZATION_NAME)
        self.assertIn(DEFAULT_ORGANIZATION_NAME, settings["verification_intro"])

    def test_save_and_read_issuer_settings(self) -> None:
        stored: dict | None = None

        def update_one(filter_doc: dict, update: dict, upsert: bool = False) -> None:
            nonlocal stored
            stored = update["$set"]

        coll = MagicMock()
        coll.find_one.return_value = None
        coll.update_one.side_effect = update_one

        with patch("services.database.coll", return_value=coll):
            saved = save_certificate_issuer_settings(
                organization_name="Wekan Enterprise Solutions",
                verification_intro="Custom verification intro.",
            )
            self.assertEqual(saved["organization_name"], "Wekan Enterprise Solutions")
            coll.find_one.return_value = stored
            loaded = get_certificate_issuer_settings()
        self.assertEqual(loaded["organization_name"], "Wekan Enterprise Solutions")
        self.assertEqual(loaded["verification_intro"], "Custom verification intro.")


if __name__ == "__main__":
    unittest.main()
