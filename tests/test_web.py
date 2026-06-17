from __future__ import annotations

import json
import unittest
from pathlib import Path
from uuid import uuid4

from sound_barrier_query.assistant import StandardAssistant
from sound_barrier_query.config import LLMConfig
from sound_barrier_query.llm import LLMError
from sound_barrier_query.search import SearchEngine
from sound_barrier_query.web import QueryApi, build_api, create_handler
from sound_barrier_query.xlsx_loader import load_workbook_clauses


WORKBOOK = Path(__file__).resolve().parents[1] / "docs" / "国内声屏障标准汇总表.xlsx"
TEST_TEMP_DIR = Path(__file__).resolve().parents[1] / ".tmp" / "tests"
TEST_TEMP_DIR.mkdir(parents=True, exist_ok=True)


def _test_directory(name: str) -> Path:
    directory = TEST_TEMP_DIR / f"{name}-{uuid4().hex}"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _run_handler(api, method, path, body, content_length=None):
    from io import BytesIO
    from email.message import Message

    handler_cls = create_handler(api)
    handler = handler_cls.__new__(handler_cls)

    raw_body = body.encode("utf-8") if isinstance(body, str) else body
    handler.rfile = BytesIO(raw_body)
    handler.wfile = BytesIO()
    handler.path = path
    handler.command = method
    handler.request_version = "HTTP/1.1"
    handler.client_address = ("127.0.0.1", 0)

    class _Server:
        pass

    handler.server = _Server()
    handler.requestline = f"{method} {path} HTTP/1.1"

    headers = Message()
    headers["Content-Length"] = content_length or str(len(raw_body))
    if raw_body:
        headers["Content-Type"] = "application/json"
    handler.headers = headers

    if method == "POST":
        handler.do_POST()
    else:
        handler.do_GET()
    raw = handler.wfile.getvalue()
    head, _, body_bytes = raw.partition(b"\r\n\r\n")
    status_line = head.splitlines()[0].decode("latin-1")
    status = int(status_line.split(" ", 2)[1])
    return {"status": status, "body": body_bytes}


class TestWebApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.api = build_api(WORKBOOK)

    def test_search_payload_shape(self):
        payload = self.api.search("岩棉", "product")

        self.assertEqual(payload["query"], "岩棉")
        self.assertEqual(payload["mode"], "product")
        self.assertTrue(payload["results"])

    def test_material_table_payload_shape(self):
        payload = self.api.material_table("岩棉")

        self.assertEqual(payload["material"], "岩棉")
        self.assertTrue(payload["standard_columns"])
        self.assertTrue(payload["rows"])

    def test_meta_groups_domestic_and_foreign_materials(self):
        payload = self.api.meta()
        groups = {str(group["name"]): group["materials"] for group in payload["material_groups"]}

        self.assertIn("国内标准", groups)
        self.assertIn("国外及香港", groups)
        self.assertIn("岩棉", groups["国内标准"])
        self.assertIn("欧洲声屏障技术标准", groups["国外及香港"])

    def test_assistant_payload_shape(self):
        payload = self.api.assistant("岩棉密度有什么要求")

        self.assertIn("summary", payload)
        self.assertTrue(payload["clauses"])

    def test_meta_reports_ai_configured_status(self):
        payload = self.api.meta()
        self.assertIn("ai_configured", payload)
        self.assertIsInstance(payload["ai_configured"], bool)

    def test_fuzzy_search_payload_shape(self):
        payload = self.api.fuzzy_search("岩棉的厚度")

        self.assertEqual(payload["query"], "岩棉的厚度")
        self.assertEqual(payload["result_type"], "material_table")
        self.assertIn("summary", payload)
        self.assertEqual(payload["matched_material"], "岩棉")
        self.assertTrue(payload["table"]["rows"])


class TestChatApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = SearchEngine(load_workbook_clauses(WORKBOOK))
        cls.config = LLMConfig("https://example.com/v1", "test-key", "test-model")

    def _build_api_with(self, llm_caller):
        return QueryApi(
            engine=self.engine,
            assistant_service=StandardAssistant(self.engine, config=self.config, llm_caller=llm_caller),
            llm_config=self.config,
        )

    def test_chat_returns_empty_message_warning(self):
        api = self._build_api_with(llm_caller=lambda *_: "unused")

        payload = api.chat("")

        self.assertEqual(payload["error"], "empty_message")
        self.assertEqual(payload["sources"], [])
        self.assertIn("请输入", payload["answer"])

    def test_chat_returns_no_match_message_when_retrieval_empty(self):
        api = self._build_api_with(
            llm_caller=lambda messages: self.fail("LLM 不应在空检索时被调用")
        )

        payload = api.chat("qwerasdfzxcv")

        self.assertNotIn("error", payload)
        self.assertIn("未检索到", payload["answer"])
        self.assertEqual(payload["sources"], [])

    def test_chat_returns_llm_answer_and_sources(self):
        captured: dict = {}

        def fake_caller(messages):
            captured["messages"] = messages
            return "根据检索结果，岩棉密度应满足 80~120 kg/m³。"

        api = self._build_api_with(llm_caller=fake_caller)

        payload = api.chat("岩棉的国内标准和项目名称")

        self.assertEqual(payload["answer"], "根据检索结果，岩棉密度应满足 80~120 kg/m³。")
        self.assertNotIn("error", payload)
        self.assertTrue(payload["sources"], "应当返回至少一条来源")
        # 注入的 messages 应该包含 system + user，且 user 内容里包含问题
        self.assertEqual(captured["messages"][0].role, "system")
        self.assertEqual(captured["messages"][1].role, "user")
        self.assertIn("岩棉的国内标准和项目名称", captured["messages"][1].content)
        first = payload["sources"][0]
        self.assertIn("product", first)
        self.assertIn("item", first)
        self.assertIn("standard", first)
        self.assertIn("requirement", first)
        self.assertIn("source_id", first)
        self.assertIn("sheet", first)

    def test_chat_strips_think_blocks_from_llm_answer(self):
        api = self._build_api_with(
            llm_caller=lambda messages: "<think>内部推理过程</think>\n**岩棉**相关要求如下：\n- 密度：80~120"
        )

        payload = api.chat("岩棉的国内标准和项目名称")

        self.assertNotIn("<think>", payload["answer"])
        self.assertNotIn("内部推理过程", payload["answer"])
        self.assertIn("**岩棉**", payload["answer"])

    def test_chat_reports_config_missing(self):
        api = QueryApi(
            engine=self.engine,
            assistant_service=StandardAssistant(self.engine, config=None),
            llm_config=None,
        )

        payload = api.chat("岩棉的国内标准")

        self.assertEqual(payload["error"], "config_missing")
        self.assertIn("AI接口未配置完整", payload["answer"])
        self.assertEqual(payload["sources"], [])

    def test_chat_propagates_llm_error_message(self):
        def boom(messages):
            raise LLMError("AI助手暂时无法回答，请稍后重试。")

        api = self._build_api_with(llm_caller=boom)

        payload = api.chat("岩棉的国内标准")

        self.assertEqual(payload["error"], "llm_failed")
        self.assertIn("AI助手暂时无法回答", payload["answer"])
        self.assertTrue(payload["sources"])

    def test_meta_unconfigured_when_env_file_missing(self):
        api = build_api(
            WORKBOOK,
            env_path=_test_directory("api-missing-env-file") / ".env",
        )
        self.assertFalse(api.meta()["ai_configured"])
        payload = api.chat("岩棉的国内标准")
        self.assertEqual(payload["error"], "config_missing")


class TestChatHttpHandler(unittest.TestCase):
    def test_post_chat_endpoint_invokes_llm_caller(self):
        engine = SearchEngine(load_workbook_clauses(WORKBOOK))
        config = LLMConfig("https://example.com/v1", "k", "m")
        api = QueryApi(
            engine=engine,
            assistant_service=StandardAssistant(engine, config=config, llm_caller=lambda messages: "ok"),
            llm_config=config,
        )
        response = _run_handler(api, "POST", "/api/chat", json.dumps({"message": "岩棉的国内标准"}))
        self.assertEqual(response["status"], 200)
        body = json.loads(response["body"].decode("utf-8"))
        self.assertEqual(body["answer"], "ok")
        self.assertTrue(body["sources"])

    def test_get_search_endpoint_still_works(self):
        api = build_api(WORKBOOK)
        response = _run_handler(api, "GET", "/api/search?mode=product&q=岩棉", "")
        self.assertEqual(response["status"], 200)
        body = json.loads(response["body"].decode("utf-8"))
        self.assertTrue(body["results"])

    def test_get_fuzzy_search_endpoint_returns_summary_and_table(self):
        api = build_api(WORKBOOK)
        response = _run_handler(api, "GET", "/api/fuzzy-search?q=岩棉的厚度", "")
        self.assertEqual(response["status"], 200)
        body = json.loads(response["body"].decode("utf-8"))
        self.assertIn("summary", body)
        self.assertEqual(body["matched_material"], "岩棉")
        self.assertEqual(body["result_type"], "material_table")
        self.assertTrue(body["table"]["rows"])

    def test_post_chat_invalid_json_returns_400(self):
        api = build_api(WORKBOOK)
        response = _run_handler(api, "POST", "/api/chat", "not-json")
        self.assertEqual(response["status"], 400)

    def test_post_chat_invalid_content_length_returns_400(self):
        api = build_api(WORKBOOK)
        response = _run_handler(
            api,
            "POST",
            "/api/chat",
            "{}",
            content_length="not-a-number",
        )
        self.assertEqual(response["status"], 400)

    def test_post_chat_oversized_body_returns_413(self):
        api = build_api(WORKBOOK)
        response = _run_handler(
            api,
            "POST",
            "/api/chat",
            "{}",
            content_length=str(65 * 1024),
        )
        self.assertEqual(response["status"], 413)

    def test_post_chat_endpoint_returns_404_for_unknown_path(self):
        api = build_api(WORKBOOK)
        response = _run_handler(api, "POST", "/api/unknown", "{}")
        self.assertEqual(response["status"], 404)


if __name__ == "__main__":
    unittest.main()
