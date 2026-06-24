"""Stage 11A: generation provider routing (Groq vs Gemini)."""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from schemas.admin import GenerateAssessmentBody
from services.llm.providers import (
    assert_generation_provider_configured,
    generation_provider_configured,
    normalize_generation_provider,
)
from services.llm_service import generate_questions


class TestGeminiModelChain(unittest.TestCase):
    def test_default_chain_order(self) -> None:
        from services.llm.gemini_provider import resolve_gemini_model_chain

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GEMINI_MODEL_CHAIN", None)
            os.environ.pop("GEMINI_MODEL", None)
            self.assertEqual(
                resolve_gemini_model_chain(),
                [
                    "gemini-3.1-pro-preview",
                    "gemini-3.5-flash",
                    "gemini-3-flash-preview",
                    "gemini-2.5-flash",
                ],
            )

    def test_gemini_model_chain_env_override(self) -> None:
        from services.llm.gemini_provider import resolve_gemini_model_chain

        with patch.dict(
            os.environ,
            {"GEMINI_MODEL_CHAIN": "gemini-2.5-flash,gemini-3.5-flash"},
            clear=False,
        ):
            self.assertEqual(
                resolve_gemini_model_chain(),
                ["gemini-2.5-flash", "gemini-3.5-flash"],
            )

    @patch("services.llm.gemini_provider._generate_once")
    @patch("services.llm.gemini_provider._get_client")
    def test_retries_chain_on_high_demand(
        self, mock_client: MagicMock, mock_generate: MagicMock
    ) -> None:
        from google.genai import errors as genai_errors

        from services.llm.gemini_provider import chat_json_text

        mock_client.return_value = MagicMock()
        mock_generate.side_effect = [
            genai_errors.ServerError(
                503,
                {"error": {"code": 503, "message": "high demand", "status": "UNAVAILABLE"}},
            ),
            '{"ok": true}',
        ]
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GEMINI_MODEL_CHAIN", None)
            os.environ.pop("GEMINI_MODEL", None)
            result = chat_json_text("test")
        self.assertEqual(result, '{"ok": true}')
        self.assertEqual(mock_generate.call_count, 2)
        self.assertEqual(
            mock_generate.call_args_list[0].args[1],
            "gemini-3.1-pro-preview",
        )
        self.assertEqual(
            mock_generate.call_args_list[1].args[1],
            "gemini-3.5-flash",
        )


class TestGenerationProviderSchema(unittest.TestCase):
  def test_default_is_grok(self) -> None:
      body = GenerateAssessmentBody.model_validate(
          {
              "topic": "Python",
              "level": "beginner",
              "types": ["mcq"],
              "questions_per_type": {"mcq": 1},
          }
      )
      self.assertEqual(body.generation_provider, "grok")

  def test_rejects_unknown_provider(self) -> None:
      with self.assertRaises(ValueError):
          GenerateAssessmentBody.model_validate(
              {
                  "topic": "Python",
                  "level": "beginner",
                  "types": ["mcq"],
                  "questions_per_type": {"mcq": 1},
                  "generation_provider": "openai",
              }
          )


class TestProviderHelpers(unittest.TestCase):
  def test_normalize_generation_provider(self) -> None:
      self.assertEqual(normalize_generation_provider("Gemini"), "gemini")
      self.assertEqual(normalize_generation_provider("grok"), "grok")

  @patch.dict("os.environ", {"GROQ_API_KEY": "gsk_test", "GOOGLE_API_KEY1": ""}, clear=False)
  def test_generation_provider_configured(self) -> None:
      self.assertTrue(generation_provider_configured("grok"))
      self.assertFalse(generation_provider_configured("gemini"))

  @patch.dict("os.environ", {"GOOGLE_API_KEY1": "key", "GROQ_API_KEY": ""}, clear=False)
  def test_gemini_configured_only(self) -> None:
      self.assertTrue(generation_provider_configured("gemini"))
      self.assertFalse(generation_provider_configured("grok"))

  @patch.dict("os.environ", {"GOOGLE_API_KEY1": ""}, clear=False)
  def test_assert_gemini_missing_raises(self) -> None:
      with self.assertRaises(RuntimeError) as ctx:
          assert_generation_provider_configured("gemini")
      self.assertIn("GOOGLE_API_KEY1", str(ctx.exception))


class TestGenerateQuestionsRouting(unittest.TestCase):
  @patch("services.llm_service.chat_json_for_generation")
  def test_routes_to_selected_provider(self, mock_chat: MagicMock) -> None:
      mock_chat.return_value = (
          '{"questions":[{"id":1,"type":"mcq","question":"Q?","options":["a","b","c","d"],'
          '"answer":"a"}]}'
      )
      with patch(
          "services.llm_service.assert_generation_provider_configured"
      ):
          generate_questions(
              "Topic",
              "easy",
              ["mcq"],
              questions_per_type={"mcq": 1},
              assessment_id="ASM-test",
              generation_provider="gemini",
          )
      mock_chat.assert_called_once()
      self.assertEqual(mock_chat.call_args.args[0], "gemini")


class TestPreviewProvider503(unittest.TestCase):
  _env_patch: patch

  @classmethod
  def setUpClass(cls) -> None:
      cls._env_patch = patch.dict(
          os.environ,
          {
              "JWT_SECRET": "test-jwt-secret-generation-provider",
              "ADMIN_PASSWORD": "test-admin-password",
              "RATE_LIMIT_ENABLED": "false",
          },
          clear=False,
      )
      cls._env_patch.start()
      with (
          patch("dotenv.load_dotenv"),
          patch("services.database.init_db"),
          patch("services.database.ping_database", return_value=True),
          patch("services.audit_log.configure_audit_logging"),
      ):
          sys.modules.pop("app", None)
          from app import app

          cls.client = TestClient(app)

  @classmethod
  def tearDownClass(cls) -> None:
      cls._env_patch.stop()
      sys.modules.pop("app", None)

  def _admin_headers(self) -> dict[str, str]:
      from services import auth_service

      return {"Authorization": f"Bearer {auth_service.create_access_token('admin')}"}

  @patch("routers.admin.assessment_service.preview_questions")
  def test_preview_gemini_missing_key_returns_503(self, mock_preview: MagicMock) -> None:
      mock_preview.side_effect = RuntimeError("GOOGLE_API_KEY1 is not set.")
      res = self.client.post(
          "/admin/preview-questions",
          json={
              "topic": "Python",
              "level": "beginner",
              "types": ["mcq"],
              "questions_per_type": {"mcq": 1},
              "generation_provider": "gemini",
          },
          headers=self._admin_headers(),
      )
      self.assertEqual(res.status_code, 503)
      self.assertIn("GOOGLE_API_KEY1", res.json()["detail"])


if __name__ == "__main__":
  unittest.main()
