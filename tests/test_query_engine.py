import json
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from sound_barrier_query.assistant import StandardAssistant
from sound_barrier_query.config import LLMConfig, load_llm_config
from sound_barrier_query.llm import ChatMessage, LLMError, chat_completions
from sound_barrier_query.models import StandardClause
from sound_barrier_query.search import SearchEngine
from sound_barrier_query.web import QueryApi, _source_payload, build_api, create_handler
from sound_barrier_query.xlsx_loader import load_workbook_clauses, load_workbook_tables


WORKBOOK = Path(__file__).resolve().parents[1] / "docs" / "国内声屏障标准汇总表.xlsx"
FOREIGN_WORKBOOK = Path(__file__).resolve().parents[1] / "docs" / "国外及香港声屏障标准汇总表本.xlsx"


class TestStandardClause(unittest.TestCase):
    def test_clause_source_id_contains_sheet_and_cell(self):
        clause = StandardClause(
            sheet="岩棉",
            row=3,
            column=4,
            product="岩棉",
            item="密度kg/m³",
            standard="GB/T 25975-2018",
            requirement="80~120",
        )

        self.assertEqual(clause.source_id, "岩棉!D3")


class TestWorkbookLoader(unittest.TestCase):
    def test_loads_real_workbook_clauses_with_source_ids(self):
        clauses = load_workbook_clauses(WORKBOOK)

        self.assertGreater(len(clauses), 100)
        density = [
            clause
            for clause in clauses
            if clause.product == "岩棉" and "密度" in clause.item and "80~120" in clause.requirement
        ]
        self.assertTrue(density)
        self.assertRegex(density[0].source_id, r"^岩棉![A-Z]+\d+$")

    def test_loads_foreign_and_hongkong_workbook_with_group(self):
        clauses = load_workbook_clauses(FOREIGN_WORKBOOK, group="国外及香港")

        self.assertTrue(clauses)
        self.assertTrue(any(clause.group == "国外及香港" for clause in clauses))
        self.assertTrue(any(clause.sheet == "欧洲声屏障技术标准" for clause in clauses))
        self.assertTrue(any("EN1793-1" in clause.requirement for clause in clauses))


class TestSearchEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = SearchEngine(load_workbook_clauses(WORKBOOK))

    def test_search_by_standard_number_ignores_spaces_and_slashes(self):
        results = self.engine.search_standard("Q/CR760")

        self.assertTrue(results)
        self.assertTrue(any("Q/CR 760-2020" in row["standard"] for row in results))

    def test_compare_product_groups_requirements_by_item(self):
        comparison = self.engine.compare_product("岩棉")

        self.assertIn("密度kg/m³", comparison)
        density = comparison["密度kg/m³"]
        self.assertTrue(any("Q/CR760" in standard.replace(" ", "") for standard in density))
        self.assertTrue(any("100~120" in value["requirement"] for value in density.values()))

    def test_search_keyword_returns_source_links(self):
        results = self.engine.search_keyword("面密度")

        self.assertTrue(results)
        self.assertTrue(any("面密度" in row["item"] for row in results))
        self.assertTrue(all(row["source_link"].startswith("#source=") for row in results[:10]))

    def test_material_table_keeps_excel_like_rows_and_standard_columns(self):
        table = self.engine.material_table("岩棉")

        self.assertEqual(table["material"], "岩棉")
        self.assertEqual(table["title"], "岩棉技术要求")
        self.assertEqual(table["base_columns"], ["序号", "部件", "检测项目"])
        self.assertTrue(table["standard_columns"])
        self.assertIn("Q/CR760-2020", table["standard_columns"][0].replace(" ", ""))
        self.assertEqual(table["rows"][0]["序号"], 1)
        self.assertEqual(table["rows"][0]["部件"], "岩棉")
        self.assertEqual(table["rows"][0]["检测项目"], "厚度mm")
        self.assertEqual(table["rows"][0][table["standard_columns"][0]], "≥50")
        density = table["rows"][1]
        self.assertEqual(density["检测项目"], "密度kg/m³")
        self.assertIn("100~120", list(density.values()))

    def test_loader_accepts_project_name_header_in_workbook(self):
        clauses = load_workbook_clauses(WORKBOOK)
        self.assertTrue(any(clause.sheet == "岩棉" and clause.item == "厚度mm" for clause in clauses))

    def test_foreign_material_table_keeps_source_headers(self):
        tables = load_workbook_tables(FOREIGN_WORKBOOK, group="国外及香港")
        engine = SearchEngine(load_workbook_clauses(FOREIGN_WORKBOOK, group="国外及香港"), tables=tables)

        table = engine.material_table("欧洲声屏障技术标准")

        self.assertEqual(table["group"], "国外及香港")
        self.assertEqual(table["base_columns"], ["序号", "项目名称"])
        self.assertEqual(table["standard_columns"], ["性能", "试验方法或计算", "设定值"])
        self.assertEqual(table["rows"][0]["项目名称"], "吸声系数DLα a")
        self.assertEqual(table["rows"][0]["试验方法或计算"], "EN1793-1(测试）")

    def test_fuzzy_search_filters_material_table_by_item_terms(self):
        tables = load_workbook_tables(WORKBOOK)
        engine = SearchEngine(load_workbook_clauses(WORKBOOK), tables=tables)

        payload = engine.fuzzy_search("岩棉的厚度")

        self.assertEqual(payload["result_type"], "material_table")
        self.assertEqual(payload["matched_material"], "岩棉")
        self.assertIn("厚度", payload["matched_terms"])
        self.assertEqual(payload["missing_terms"], [])
        self.assertIn("检索到", payload["summary"])
        table = payload["table"]
        self.assertEqual(table["material"], "岩棉")
        self.assertTrue(table["rows"])
        self.assertTrue(all("厚度" in "".join(str(value) for value in row.values()) for row in table["rows"]))

    def test_fuzzy_search_falls_back_to_material_when_item_missing(self):
        tables = load_workbook_tables(WORKBOOK)
        engine = SearchEngine(load_workbook_clauses(WORKBOOK), tables=tables)
        full_table = engine.material_table("岩棉")

        payload = engine.fuzzy_search("岩棉的不存在指标")

        self.assertEqual(payload["result_type"], "material_table")
        self.assertEqual(payload["matched_material"], "岩棉")
        self.assertIn("不存在指标", payload["missing_terms"])
        self.assertIn("未检索到", payload["summary"])
        self.assertEqual(len(payload["table"]["rows"]), len(full_table["rows"]))


class TestAssistant(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.assistant = StandardAssistant(SearchEngine(load_workbook_clauses(WORKBOOK)))

    def test_answer_summarizes_retrieved_clauses_with_sources(self):
        answer = self.assistant.answer("岩棉密度有什么要求")

        self.assertIn("summary", answer)
        self.assertIn("岩棉", answer["summary"])
        self.assertTrue(answer["clauses"])
        self.assertTrue(any("密度" in clause["item"] for clause in answer["clauses"]))
        self.assertTrue(all(clause["source_link"].startswith("#source=") for clause in answer["clauses"]))

    def test_retrieve_returns_relevant_clauses_for_sample_questions(self):
        questions = [
            "岩棉的国内标准和项目名称",
            "金属单元板面密度有哪些要求？",
            "PC板透光率相关标准是什么？",
            "隔声量相关内容有哪些？",
        ]
        for question in questions:
            with self.subTest(question=question):
                clauses = self.assistant.retrieve(question)
                self.assertTrue(clauses, f"未检索到与 {question!r} 相关的内容")
                self.assertTrue(all(clause.get("source_id") for clause in clauses))

    def test_retrieve_returns_empty_for_known_unrelated_query(self):
        clauses = self.assistant.retrieve("qwerasdfzxcv")
        self.assertEqual(clauses, [])


class TestLLMConfig(unittest.TestCase):
    def test_loads_env_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / ".env"
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
        with tempfile.TemporaryDirectory() as tmp:
            config = load_llm_config(Path(tmp) / ".env")
        self.assertFalse(config.is_complete())
        self.assertEqual(config.base_url, "")

    def test_build_api_accepts_uppercase_env_file_when_default_env_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / ".env"
            (Path(tmp) / ".ENV").write_text(
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
            assistant_service=StandardAssistant(self.engine, config=self.config),
            llm_config=self.config,
            llm_caller=llm_caller,
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
        from sound_barrier_query.llm import LLMError

        def boom(messages):
            raise LLMError("AI助手暂时无法回答，请稍后重试。")

        api = self._build_api_with(llm_caller=boom)

        payload = api.chat("岩棉的国内标准")

        self.assertEqual(payload["error"], "llm_failed")
        self.assertIn("AI助手暂时无法回答", payload["answer"])
        self.assertTrue(payload["sources"])

    def test_meta_unconfigured_when_env_file_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            api = build_api(WORKBOOK, env_path=Path(tmp) / ".env")
        self.assertFalse(api.meta()["ai_configured"])
        payload = api.chat("岩棉的国内标准")
        self.assertEqual(payload["error"], "config_missing")


class TestChatHttpHandler(unittest.TestCase):
    def test_post_chat_endpoint_invokes_llm_caller(self):
        engine = SearchEngine(load_workbook_clauses(WORKBOOK))
        config = LLMConfig("https://example.com/v1", "k", "m")
        api = QueryApi(
            engine=engine,
            assistant_service=StandardAssistant(engine, config=config),
            llm_config=config,
            llm_caller=lambda messages: "ok",
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

    def test_post_chat_endpoint_returns_404_for_unknown_path(self):
        api = build_api(WORKBOOK)
        response = _run_handler(api, "POST", "/api/unknown", "{}")
        self.assertEqual(response["status"], 404)


def _run_handler(api, method, path, body):
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
    headers["Content-Length"] = str(len(raw_body))
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


class TestStaticUi(unittest.TestCase):
    def test_home_navigation_and_library_assets_exist(self):
        static_dir = Path(__file__).resolve().parents[1] / "src" / "sound_barrier_query" / "static"
        html = (static_dir / "index.html").read_text(encoding="utf-8")
        css = (static_dir / "styles.css").read_text(encoding="utf-8")
        js = (static_dir / "app.js").read_text(encoding="utf-8")

        self.assertIn('id="home-view"', html)
        self.assertIn('id="library-view"', html)
        self.assertIn('id="assistant-view"', html)
        self.assertIn('id="nav-home"', html)
        self.assertIn('id="nav-library"', html)
        self.assertIn('id="nav-assistant"', html)
        self.assertIn('id="home-search"', html)
        self.assertIn('id="stat-clauses"', html)
        self.assertIn('id="stat-materials"', html)
        self.assertIn('id="stat-standards"', html)
        self.assertIn('id="nav-toggle"', html)
        self.assertIn("view-hidden", css)
        self.assertIn("sidebar-collapsed", css)
        self.assertIn("showView", js)
        self.assertIn("sidebar-collapsed", js)
        self.assertIn("material_groups", js)
        self.assertIn("renderNavGroup", js)
        self.assertIn("项目名称", js)

    def test_static_theme_uses_blue_white_palette(self):
        static_dir = Path(__file__).resolve().parents[1] / "src" / "sound_barrier_query" / "static"
        css = (static_dir / "styles.css").read_text(encoding="utf-8")

        self.assertIn("--accent: #2563eb", css)
        self.assertNotIn("#fbf6ea", css)
        self.assertNotIn("#fff8eb", css)
        self.assertNotIn("#f0dfbd", css)

    def test_chat_view_has_input_and_messages(self):
        static_dir = Path(__file__).resolve().parents[1] / "src" / "sound_barrier_query" / "static"
        html = (static_dir / "index.html").read_text(encoding="utf-8")
        css = (static_dir / "styles.css").read_text(encoding="utf-8")
        js = (static_dir / "app.js").read_text(encoding="utf-8")

        self.assertIn('id="chat-messages"', html)
        self.assertIn('id="chat-input"', html)
        self.assertIn('id="chat-send"', html)
        self.assertIn('id="chat-form"', html)
        self.assertIn(".chat-shell", css)
        self.assertIn(".chat-bubble", css)
        self.assertIn('fetch("/api/chat"', js)
        self.assertIn("submitChatMessage", js)
        self.assertIn("renderMarkdown", js)
        self.assertIn("renderMarkdownTable", js)
        self.assertIn(".chat-markdown table", css)
        self.assertNotIn("${escapeHtml(entry.answer || \"\")}", js)

    def test_home_ai_assistant_card_submits_into_chat(self):
        static_dir = Path(__file__).resolve().parents[1] / "src" / "sound_barrier_query" / "static"
        html = (static_dir / "index.html").read_text(encoding="utf-8")
        css = (static_dir / "styles.css").read_text(encoding="utf-8")
        js = (static_dir / "app.js").read_text(encoding="utf-8")

        self.assertIn('class="home-ai-card"', html)
        self.assertIn("AI助手", html)
        self.assertIn('id="home-ai-input"', html)
        self.assertIn('id="home-ai-form"', html)
        self.assertIn(".home-ai-card", css)
        self.assertIn("submitHomeAssistantQuestion", js)
        self.assertIn('showView("assistant")', js)
        self.assertIn("chatInputEl.value = question", js)

    def test_library_search_uses_fuzzy_endpoint_and_summary_panel(self):
        static_dir = Path(__file__).resolve().parents[1] / "src" / "sound_barrier_query" / "static"
        html = (static_dir / "index.html").read_text(encoding="utf-8")
        js = (static_dir / "app.js").read_text(encoding="utf-8")

        self.assertIn('id="assistant-panel"', html)
        self.assertIn("/api/fuzzy-search", js)
        self.assertIn("renderFuzzySearchResult", js)
        self.assertIn("renderSearchSummary", js)


if __name__ == "__main__":
    unittest.main()
