from __future__ import annotations

import argparse
import json
import logging
import mimetypes
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .assistant import LLMCaller, StandardAssistant, to_source_dict
from .config import LLMConfig, load_llm_config
from .search import SearchEngine
from .xlsx_loader import load_workbook_clauses, load_workbook_tables

DEFAULT_WORKBOOK = Path(__file__).resolve().parents[2] / "docs" / "国内声屏障标准汇总表.xlsx"
DEFAULT_FOREIGN_WORKBOOK = Path(__file__).resolve().parents[2] / "docs" / "国外及香港声屏障标准汇总表本.xlsx"
DEFAULT_ENV = Path(__file__).resolve().parents[2] / ".env"
STATIC_DIR = Path(__file__).resolve().parent / "static"
MAX_CHAT_BODY_BYTES = 64 * 1024
logger = logging.getLogger("sound_barrier_query")


@dataclass
class QueryApi:
    engine: SearchEngine
    assistant_service: StandardAssistant
    llm_config: LLMConfig | None = None
    llm_caller: LLMCaller | None = None

    def search(self, query: str, mode: str = "keyword") -> dict[str, object]:
        return {
            "query": query,
            "mode": mode,
            "results": self.engine.search(query, mode),
        }

    def fuzzy_search(self, query: str) -> dict[str, object]:
        return self.engine.fuzzy_search(query)

    def compare(self, product: str) -> dict[str, object]:
        return {
            "product": product,
            "comparison": self.engine.compare_product(product),
        }

    def material_table(self, material: str) -> dict[str, object]:
        return self.engine.material_table(material)

    def assistant(self, question: str) -> dict[str, object]:
        return self.assistant_service.answer(question)

    def chat(self, message: str) -> dict[str, object]:
        text = (message or "").strip()
        if not text:
            return {
                "answer": "请输入您要查询的问题。",
                "sources": [],
                "error": "empty_message",
            }

        if self.llm_config is None or not self.llm_config.is_complete():
            return {
                "answer": "AI接口未配置完整，请检查 .env 中 BASE_URL/API_KEY/MODEL。",
                "sources": [],
                "error": "config_missing",
            }

        clauses = self.assistant_service.retrieve(text)
        if not clauses:
            return {
                "answer": "当前标准库未检索到相关内容。",
                "sources": [],
            }

        response = self.assistant_service.answer_with_llm(text, clauses)
        payload: dict[str, object] = {
            "answer": response.get("answer", ""),
            "sources": response.get("sources", []),
        }
        error = response.get("error")
        if error:
            payload["error"] = error
        return payload

    def meta(self) -> dict[str, object]:
        return {
            "materials": self.engine.materials,
            "material_groups": self.engine.material_groups,
            "products": self.engine.products,
            "standards": self.engine.standards,
            "clause_count": len(self.engine.clauses),
            "ai_configured": bool(self.llm_config and self.llm_config.is_complete()),
        }


def build_api(
    workbook: str | Path = DEFAULT_WORKBOOK,
    foreign_workbook: str | Path | None = DEFAULT_FOREIGN_WORKBOOK,
    env_path: str | Path = DEFAULT_ENV,
    llm_caller: LLMCaller | None = None,
) -> QueryApi:
    clauses = load_workbook_clauses(workbook, group="国内标准")
    tables = load_workbook_tables(workbook, group="国内标准")
    if foreign_workbook is not None and Path(foreign_workbook).exists():
        clauses.extend(load_workbook_clauses(foreign_workbook, group="国外及香港"))
        tables.extend(load_workbook_tables(foreign_workbook, group="国外及香港"))
    engine = SearchEngine(clauses, tables=tables)
    values = load_llm_config(env_path)
    config = values if values.is_complete() else None
    assistant_service = StandardAssistant(engine, config=config, llm_caller=llm_caller)
    return QueryApi(
        engine=engine,
        assistant_service=assistant_service,
        llm_config=config,
        llm_caller=llm_caller,
    )


def create_handler(api: QueryApi, *, cors_origin: str = "") -> type[BaseHTTPRequestHandler]:
    class RequestHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path.startswith("/api/"):
                self._handle_api(parsed.path, parse_qs(parsed.query))
                return
            self._handle_static(parsed.path)

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/api/chat":
                self._handle_chat()
                return
            self._send_json({"error": "接口不存在"}, status=404)

        def do_OPTIONS(self) -> None:
            self.send_response(204)
            self._add_cors_headers()
            self.end_headers()

        def log_message(self, format: str, *args: object) -> None:
            logger.info("%s %s", self.client_address[0], format % args)

        def _handle_api(self, path: str, params: dict[str, list[str]]) -> None:
            query = _param(params, "q")
            logger.debug("API %s q=%r", path, query)
            if path == "/api/search":
                payload = api.search(query, _param(params, "mode", "keyword"))
            elif path == "/api/fuzzy-search":
                payload = api.fuzzy_search(query)
            elif path == "/api/compare":
                payload = api.compare(query)
            elif path == "/api/material-table":
                payload = api.material_table(query)
            elif path == "/api/assistant":
                payload = api.assistant(query)
            elif path == "/api/meta":
                payload = api.meta()
            else:
                self._send_json({"error": "接口不存在"}, status=404)
                return
            self._send_json(payload)

        def _handle_chat(self) -> None:
            try:
                length = int(self.headers.get("Content-Length", "0") or "0")
            except ValueError:
                self._send_json({"error": "Content-Length 必须是数字"}, status=400)
                return
            if length > MAX_CHAT_BODY_BYTES:
                self._send_json({"error": "请求体过大"}, status=413)
                return
            raw_body = self.rfile.read(length) if length else b""
            try:
                body = json.loads(raw_body.decode("utf-8")) if raw_body else {}
            except json.JSONDecodeError:
                self._send_json({"error": "请求体不是合法 JSON"}, status=400)
                return
            message = body.get("message", "") if isinstance(body, dict) else ""
            logger.debug("Chat request: %r", message[:80])
            payload = api.chat(message if isinstance(message, str) else "")
            self._send_json(payload)

        def _handle_static(self, path: str) -> None:
            relative = "index.html" if path in {"", "/"} else path.lstrip("/")
            file_path = (STATIC_DIR / relative).resolve()
            try:
                file_path.relative_to(STATIC_DIR)
            except ValueError:
                self.send_error(403)
                return
            if not file_path.exists() or not file_path.is_file():
                self.send_error(404)
                return
            content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
            data = file_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", f"{content_type}; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _send_json(self, payload: dict[str, object], status: int = 200) -> None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self._add_cors_headers()
            self.end_headers()
            self.wfile.write(data)

        def _add_cors_headers(self) -> None:
            if cors_origin:
                self.send_header("Access-Control-Allow-Origin", cors_origin)
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")

    return RequestHandler


def _param(params: dict[str, list[str]], name: str, default: str = "") -> str:
    values = params.get(name)
    if not values:
        return default
    return values[0].strip()


def main() -> None:
    parser = argparse.ArgumentParser(description="声屏障标准查询系统")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--workbook", default=str(DEFAULT_WORKBOOK))
    parser.add_argument("--foreign-workbook", default=str(DEFAULT_FOREIGN_WORKBOOK))
    parser.add_argument("--env", default=str(DEFAULT_ENV))
    parser.add_argument("--cors-origin", default="", help="CORS 允许的源，例如 http://localhost:3000")
    parser.add_argument("--log-level", default="INFO", help="日志级别：DEBUG/INFO/WARNING")
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    api = build_api(args.workbook, args.foreign_workbook, args.env)
    logger.info("声屏障标准查询系统已启动：http://%s:%s", args.host, args.port)
    logger.info(
        "AI接口配置状态：%s",
        "已配置" if api.meta().get("ai_configured") else "未配置（请检查 .env）",
    )
    try:
        server = ThreadingHTTPServer(
            (args.host, args.port), create_handler(api, cors_origin=args.cors_origin)
        )
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        try:
            server.server_close()
        except UnboundLocalError:
            pass


if __name__ == "__main__":
    main()
