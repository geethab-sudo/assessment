"""Certificate public URL resolution."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from services.certificate_service import (  # noqa: E402
    _public_base_url,
    build_certificate_share_bundle,
    get_certificate_share_metadata_by_assessment,
)


class TestPublicBaseUrl(unittest.TestCase):
    def test_env_override(self) -> None:
        with patch.dict("os.environ", {"APP_PUBLIC_URL": "https://example.com/"}):
            self.assertEqual(_public_base_url(), "https://example.com")

    def test_forwarded_request_headers(self) -> None:
        request = MagicMock()
        request.headers.get.side_effect = lambda key: {
            "x-forwarded-proto": "http",
            "x-forwarded-host": "ec2-54-226-73-84.compute-1.amazonaws.com",
        }.get(key)
        request.url.scheme = "http"
        with patch.dict("os.environ", {}, clear=False):
            os_environ = __import__("os").environ
            os_environ.pop("APP_PUBLIC_URL", None)
            self.assertEqual(
                _public_base_url(request),
                "http://ec2-54-226-73-84.compute-1.amazonaws.com",
            )


class TestShareBundleUrls(unittest.TestCase):
    def test_build_share_bundle_uses_request_host(self) -> None:
        request = MagicMock()
        request.headers.get.side_effect = lambda key: {
            "x-forwarded-proto": "http",
            "x-forwarded-host": "ec2.example.com",
        }.get(key)
        request.url.scheme = "http"
        row = {
            "id": 3,
            "display_name": "Jane",
            "level": "intermediate",
            "language_label": "Python",
            "issued_at": "2026-06-26T10:00:00+00:00",
            "score": 0.92,
        }
        with patch.dict("os.environ", {}, clear=False):
            __import__("os").environ.pop("APP_PUBLIC_URL", None)
            bundle = build_certificate_share_bundle(row, request)
        self.assertEqual(
            bundle["verification_url"],
            "http://ec2.example.com/verify/certificate/3",
        )
        self.assertIn("ec2.example.com", bundle["linkedin_url"])


class TestShareMetadataByAssessment(unittest.TestCase):
    def test_latest_certificate_for_assessment(self) -> None:
        row = {
            "id": 9,
            "employee_id": "E1",
            "assessment_id": "ASM-RK9SVRP5",
            "display_name": "Jane",
            "level": "beginner",
            "language_label": "Python",
            "issued_at": "2026-06-26T10:00:00+00:00",
        }
        certs = MagicMock()
        certs.find_one.return_value = row
        with (
            patch("services.database.coll", return_value=certs),
            patch.dict("os.environ", {"APP_PUBLIC_URL": "http://deployed.example.com"}),
        ):
            meta = get_certificate_share_metadata_by_assessment(
                "E1",
                "ASM-RK9SVRP5",
            )
        self.assertEqual(meta["certificate_id"], 9)
        self.assertIn("/verify/certificate/9", meta["verification_url"])
        certs.find_one.assert_any_call(
            {"employee_id": "e1", "assessment_id": "ASM-RK9SVRP5"},
            sort=[("issued_at", -1)],
        )


if __name__ == "__main__":
    unittest.main()
