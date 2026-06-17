from __future__ import annotations

import json
import unittest
from pathlib import Path
from uuid import uuid4

from sound_barrier_query.config import LLMConfig, load_llm_config
from sound_barrier_query.llm import ChatMessage, LLMError, chat_completions
from sound_barrier_query.web import build_api


WORKBOOK = Path(__file__).resolve().parents[1] / "docs" / "国内声屏障标准汇总表.xlsx"
TEST_TEMP_DIR = Path(__file__).resolve().parents[1] / ".tmp" / "tests"
TEST_TEMP_DIR.mkdir(parents=True, exist_ok=True)


def _test_directory(name: str) -> Path:
    directory = TEST_TEMP_DIR / f"{name}-{uuid4().hex}"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


class TestLLMConfig(unittest.TestCase):
    def test_loads_env_file(self):
        env_path = _test_directory("loads-env-file") / ".env"
        env_path.write_text(
            "BASE_URL=https://example.com/v1\n"
            "API_KEY=secret-key\n"
            "MODEL=test-model\n",
            encoding="utf-8",
        )
        config = load_llm_config(env_path)
        self.assertEqual(config.base_url, "https://example.com/v1")
        self.assertEqual(config.api_key, "secret-key")
        self.assertEqual(config.model, "test-model")
        self.assertTrue(config.is_complete())

    def test_missing_keys_when_file_absent(self):
        config = load_llm_config(_test_directory("missing-env-file") / ".env")
        self.assertFalse(config.is_complete())
        self.assertEqual(config.base_url, "")

    def test_build_api_accepts_uppercase_env_file_when_default_env_missing(self):
        directory = _test_directory("uppercase-env-file")
        env_path = directory / ".env"
        (directory / ".ENV").write_text(
            "BASE_URL=https://example.com/v1\n"
            "API_KEY=secret-key\n"
            "MODEL=test-model\n",
            encoding="utf-8",
        )
        api = build_api(WORKBOOK, env_path=env_path)
        self.assertTrue(api.meta()["ai_configured"])

    def test_env_file_is_dot_env(self):
        env_path = Path(__file__).resolve().parents[1] / ".env"
        self.assertTrue(env_path.exists(), "项目根目录必须存在 .env 文件")
        config = load_llm_config(env_path)
        self.assertTrue(config.is_complete(), "项目 .env 必须包含 BASE_URL/API_KEY/MODEL")


class TestLLMClient(unittest.TestCase):
    def test_chat_completions_uses_openai_compatible_payload(self):
        captured: dict = {}

        def fake_poster(url, headers, body):
            captured["url"] = url
            captured["headers"] = dict(headers)
            captured["body"] = json.loads(body.decode("utf-8"))
            return (
                200,
                {"Content-Type": "application/json"},
                json.dumps(
                    {"choices": [{"message": {"content": "ok"}}]},
                    ensure_ascii=False,
                ).encode("utf-8"),
            )

        config = LLMConfig(
            base_url="https://example.com/v1",
            api_key="k",
            model="m",
        )
        content = chat_completions(
            config,
            [ChatMessage("system", "sys"), ChatMessage("user", "hi")],
            poster=fake_poster,
        )
        self.assertEqual(content, "ok")
        self.assertEqual(captured["url"], "https://example.com/v1/chat/completions")
        self.assertEqual(captured["headers"]["Authorization"], "Bearer k")
        self.assertEqual(captured["body"]["model"], "m")
        self.assertEqual(captured["body"]["messages"][0]["role"], "system")
        self.assertEqual(captured["body"]["messages"][1]["content"], "hi")

    def test_chat_completions_appends_chat_completions_to_base_url(self):
        captured: dict = {}

        def fake_poster(url, headers, body):
            captured["url"] = url
            return (
                200,
                {},
                json.dumps({"choices": [{"message": {"content": "ok"}}]}).encode("utf-8"),
            )

        chat_completions(
            LLMConfig("https://example.com/v1/", "k", "m"),
            [ChatMessage("user", "hi")],
            poster=fake_poster,
        )
        self.assertEqual(captured["url"], "https://example.com/v1/chat/completions")

    def test_chat_completions_raises_on_http_error(self):
        def fake_poster(url, headers, body):
            return (500, {}, b"server boom")

        with self.assertRaises(LLMError):
            chat_completions(
                LLMConfig("https://example.com/v1", "k", "m"),
                [ChatMessage("user", "hi")],
                poster=fake_poster,
            )

    def test_chat_completions_raises_when_config_incomplete(self):
        with self.assertRaises(LLMError):
            chat_completions(
                LLMConfig("", "k", "m"),
                [ChatMessage("user", "hi")],
            )


if __name__ == "__main__":
    unittest.main()
