from __future__ import annotations

import unittest
from unittest.mock import patch

from app.deep_agent_runtime import (
    get_default_runtime_model_id,
    resolve_runtime_model,
    should_fallback_to_deepseek_chat,
)


class ModelSelectionTests(unittest.TestCase):
    def test_default_runtime_model_falls_back_to_deepseek_when_default_provider_has_no_key(self) -> None:
        with (
            patch("app.deep_agent_runtime._get_configured_default_model_id", return_value="claude-sonnet-4-5-20250929"),
            patch(
                "app.deep_agent_runtime._get_api_key",
                side_effect=lambda provider: {"deepseek": "deepseek-key"}.get(provider),
            ),
        ):
            self.assertEqual(get_default_runtime_model_id(), "deepseek-chat")

    def test_explicit_model_selection_does_not_silently_fallback_to_deepseek(self) -> None:
        with patch(
            "app.deep_agent_runtime._get_api_key",
            side_effect=lambda provider: {"deepseek": "deepseek-key"}.get(provider),
        ):
            self.assertEqual(resolve_runtime_model("gpt-5.2"), ("openai", "gpt-5.2"))

    def test_only_deepseek_reasoner_uses_same_provider_fallback(self) -> None:
        with patch(
            "app.deep_agent_runtime._get_api_key",
            side_effect=lambda provider: {"deepseek": "deepseek-key"}.get(provider),
        ):
            self.assertTrue(should_fallback_to_deepseek_chat("deepseek-reasoner"))
            self.assertFalse(should_fallback_to_deepseek_chat("gpt-5.2"))


if __name__ == "__main__":
    unittest.main()
