from __future__ import annotations

import logging
import re
from collections import Counter
from collections.abc import Callable, Iterable
from typing import Any

from .aliases import (
    expand_query_with_aliases,
    item_terms_for_query,
    material_item_terms_for_query,
    scope_terms_for_query,
)
from .config import LLMConfig
from .llm import ChatMessage, LLMError, chat_completions
from .search import SearchEngine, normalize

logger = logging.getLogger("sound_barrier_query.assistant")

SYSTEM_PROMPT = (
    "你是“声屏障标准查询系统”的AI助手，"
    "只能依据用户问题下方提供的【检索上下文】中来自《国内声屏障标准汇总表》的真实条款进行回答。\n"
    "严格要求：\n"
    "1. 不得编造任何标准号、标准名称、项目名称、检测项目、技术要求或数值。\n"
    "2. 如果【检索上下文】中没有任何与用户问题相关的内容，必须明确回答："
    "“当前标准库未检索到相关内容”，并提示用户换一种说法。\n"
    "3. 回答时尽量使用中文，结构清晰，可适当引用原文技术要求，但不要逐条复述。\n"
    "4. 在回答中需要包含：涉及的产品/材料、项目名称（检测项目）、相关标准名称或标准号、"
    "技术要求摘要，以及来源信息（sheet!单元格）。\n"
    "5. 不要在回答里出现“我无法访问互联网/数据库”之类的免责声明；只基于上下文回答即可。"
)

NO_RESULT_MESSAGE = "当前标准库未检索到相关内容。"
CONFIG_MISSING_MESSAGE = "AI接口未配置完整，请检查 .env 中 BASE_URL/API_KEY/MODEL。"

LLMCaller = Callable[[list[ChatMessage]], str]


class StandardAssistant:
    def __init__(
        self,
        engine: SearchEngine,
        config: LLMConfig | None = None,
        llm_caller: LLMCaller | None = None,
    ):
        self.engine = engine
        self.config = config
        self._llm_caller = llm_caller

    def retrieve(self, question: str, limit: int = 12) -> list[dict[str, Any]]:
        return _retrieve(self.engine, question, limit)

    def answer(self, question: str, limit: int = 12) -> dict[str, Any]:
        """本地检索版回答：与历史 API 保持一致，不调用大模型。"""
        clauses = _retrieve(self.engine, question, limit)
        if not clauses:
            return {
                "summary": "未在当前声屏障标准库中检索到直接相关内容。",
                "clauses": [],
                "suggestions": ["尝试输入标准号、产品名称或检测项目关键词。"],
            }

        products = Counter(str(clause["product"]) for clause in clauses)
        items = Counter(str(clause["item"]) for clause in clauses)
        standards = {str(clause["standard"]) for clause in clauses}

        top_product = products.most_common(1)[0][0]
        top_items = "、".join(item for item, _ in items.most_common(3))
        summary = (
            f"检索到与“{question}”相关的 {len(clauses)} 条标准内容，"
            f"主要涉及 {top_product} 的 {top_items} 等要求，"
            f"覆盖 {len(standards)} 个标准或技术文件。以下结论均来自当前标准库条款。"
        )

        return {
            "summary": summary,
            "clauses": clauses,
            "suggestions": self._build_suggestions(clauses),
        }

    def answer_with_llm(
        self,
        question: str,
        clauses: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if not clauses:
            return {
                "answer": NO_RESULT_MESSAGE,
                "summary": NO_RESULT_MESSAGE,
                "clauses": [],
                "sources": [],
            }
        if self.config is None or not self.config.is_complete():
            return {
                "answer": CONFIG_MISSING_MESSAGE,
                "summary": CONFIG_MISSING_MESSAGE,
                "clauses": clauses,
                "sources": [to_source_dict(clause) for clause in clauses],
                "error": "config_missing",
            }

        messages = build_rag_messages(question, clauses)
        try:
            if self._llm_caller is not None:
                content = self._llm_caller(messages)
            else:
                content = chat_completions(self.config, messages)
        except LLMError as error:
            return {
                "answer": str(error),
                "summary": str(error),
                "clauses": clauses,
                "sources": [to_source_dict(clause) for clause in clauses],
                "error": "llm_failed",
            }

        text = clean_llm_answer(content) or NO_RESULT_MESSAGE
        return {
            "answer": text,
            "summary": text,
            "clauses": clauses,
            "sources": [to_source_dict(clause) for clause in clauses],
        }

    def _build_suggestions(self, clauses: list[dict[str, Any]]) -> list[str]:
        suggestions: list[str] = []
        for clause in clauses[:3]:
            suggestions.append(
                f"查看 {clause['product']} / {clause['item']} / {clause['standard']}"
            )
        return suggestions


def _match_product(engine: SearchEngine, expanded_question: str) -> tuple[str, list[dict[str, Any]]]:
    """Try to match a product/material from the expanded question.

    Searches engine.materials first (sheet names), then engine.products.
    Returns (matched_product, product_hits) or ("", []) if no match.
    """
    for product in sorted(engine.materials, key=len, reverse=True):
        if product and product in expanded_question:
            hits = engine.search_product(product, limit=max(len(engine.clauses), 48))
            strict_hits = [
                row for row in hits
                if normalize(str(row.get("sheet", ""))) == normalize(product)
                or normalize(str(row.get("product", ""))) == normalize(product)
            ]
            return product, (strict_hits if strict_hits else hits)

    for product in sorted(engine.products, key=len, reverse=True):
        if product and product in expanded_question:
            hits = engine.search_product(product, limit=max(len(engine.clauses), 48))
            return product, hits

    return "", []


def _rank_product_hits(
    product_hits: list[dict[str, Any]],
    matched_product: str,
    question: str,
    scope_terms: list[str],
) -> list[dict[str, Any]]:
    """Rank product hits by item-term relevance and scope filtering."""
    group_item_terms = material_item_terms_for_query(matched_product, question)
    if not group_item_terms:
        # Fall back: resolve item aliases (e.g. "隔音量" → "计权隔声量")
        # and look up matching items in the material's item groups.
        from .aliases import MATERIAL_ITEM_GROUPS, item_terms_for_query

        matched_items = item_terms_for_query(question)
        material_groups = MATERIAL_ITEM_GROUPS.get(matched_product, {})
        fallback_terms: list[str] = []
        for group_items in material_groups.values():
            for item in group_items:
                if normalize(item) in [normalize(mi) for mi in matched_items]:
                    fallback_terms.append(item)
        group_item_terms = list(dict.fromkeys(fallback_terms))

    if group_item_terms:
        return _filter_rows_by_exact_item_terms(product_hits, group_item_terms, scope_terms)
    return _filter_by_terms(product_hits, question, matched_product, scope_terms)


def _search_across_products(
    engine: SearchEngine,
    item_terms: list[str],
    scope_terms: list[str],
    limit: int,
) -> list[dict[str, Any]]:
    """Search across all materials by item terms, falling back to keyword search."""
    ranked = _search_by_item_terms(engine, item_terms, scope_terms, limit=limit * 4)
    if not ranked:
        expanded_question = expand_query_with_aliases(
            " ".join(item_terms) if item_terms else ""
        )
        ranked = _search_with_terms(engine, expanded_question, limit=limit * 4)
    return ranked


def _retrieve(engine: SearchEngine, question: str, limit: int) -> list[dict[str, Any]]:
    expanded_question = expand_query_with_aliases(question)
    scope_terms = scope_terms_for_query(question)
    item_terms = item_terms_for_query(question)
    logger.debug("retrieve: q=%r scope=%s items=%s", question[:60], scope_terms, item_terms[:3])

    matched_product, product_hits = _match_product(engine, expanded_question)

    if product_hits:
        ranked = _rank_product_hits(product_hits, matched_product, question, scope_terms)
    else:
        ranked = _search_across_products(engine, item_terms, scope_terms, limit)

    if not ranked and not product_hits:
        ranked = engine.search_keyword(expanded_question, limit=limit * 4)

    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for row in ranked:
        key = str(row.get("source_id", ""))
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(row)
        if len(deduped) >= limit:
            break
    return deduped


def _filter_by_terms(
    rows: list[dict[str, Any]],
    question: str,
    matched_product: str,
    scope_terms: list[str] | None = None,
) -> list[dict[str, Any]]:
    question_terms = _split_terms(question.replace(matched_product, " "))
    if not question_terms:
        return rows
    filtered = [
        row
        for row in rows
        if any(
            normalize(term)
            in normalize(f"{row.get('item', '')} {row.get('requirement', '')}")
            for term in question_terms
        )
    ]
    item_filtered = [
        row
        for row in filtered
        if any(
            len(normalize(term)) >= 3
            and normalize(term) in normalize(str(row.get("item", "")))
            for term in question_terms
        )
    ]
    item_prefix_filtered = [
        row
        for row in item_filtered
        if any(
            len(normalize(term)) >= 3
            and normalize(str(row.get("item", ""))).startswith(normalize(term))
            for term in question_terms
        )
    ]
    if item_prefix_filtered:
        filtered = item_prefix_filtered
    elif item_filtered:
        filtered = item_filtered
    standard_filtered = _filter_by_standard_scope(filtered, scope_terms or [])
    if standard_filtered:
        filtered = standard_filtered
    return sorted(
        filtered,
        key=lambda row: (
            -_term_match_score(row, question_terms, scope_terms or []),
            len(normalize(str(row.get("item", "")))),
        ),
    ) or rows


def _filter_by_standard_scope(rows: list[dict[str, Any]], scope_terms: list[str]) -> list[dict[str, Any]]:
    normalized_scope_terms = [normalize(term) for term in scope_terms if normalize(term)]
    if not normalized_scope_terms:
        return []
    return [
        row
        for row in rows
        if any(term in normalize(str(row.get("standard", ""))) for term in normalized_scope_terms)
    ]


def _filter_rows_by_exact_item_terms(
    rows: list[dict[str, Any]],
    item_terms: list[str],
    scope_terms: list[str],
) -> list[dict[str, Any]]:
    normalized_item_terms = [normalize(term) for term in item_terms if normalize(term)]
    if not normalized_item_terms:
        return []
    filtered = [
        row
        for row in rows
        if normalize(str(row.get("item", ""))) in normalized_item_terms
    ]
    scoped_rows = _filter_by_standard_scope(filtered, scope_terms)
    if scoped_rows:
        filtered = scoped_rows
    return sorted(
        filtered,
        key=lambda row: (
            normalized_item_terms.index(normalize(str(row.get("item", "")))),
            int(row.get("row", 0) or 0),
            int(row.get("column", 0) or 0),
        ),
    )


def _term_match_score(row: dict[str, Any], terms: list[str], scope_terms: list[str]) -> int:
    item = normalize(str(row.get("item", "")))
    requirement = normalize(str(row.get("requirement", "")))
    standard = normalize(str(row.get("standard", "")))
    haystack = f"{item} {requirement}"
    score = 0
    for term in terms:
        normalized_term = normalize(term)
        if not normalized_term:
            continue
        if item == normalized_term:
            score += 1000
        elif item.startswith(normalized_term):
            score += 750
        elif normalized_term in item:
            score += 500
        elif normalized_term in haystack:
            score += 100
        if normalized_term in standard:
            score += 200
    for term in scope_terms:
        normalized_term = normalize(term)
        if normalized_term and normalized_term in standard:
            score += 300
    return score


def _search_with_terms(
    engine: SearchEngine,
    question: str,
    limit: int,
) -> list[dict[str, Any]]:
    terms = _split_terms(question)
    if not terms:
        return []
    seen: dict[str, dict[str, Any]] = {}
    for term in terms:
        for row in engine.search_keyword(term, limit=limit):
            key = str(row.get("source_id", ""))
            if key in seen:
                continue
            seen[key] = row
            if len(seen) >= limit:
                break
        if len(seen) >= limit:
            break
    return list(seen.values())


def _search_by_item_terms(
    engine: SearchEngine,
    item_terms: list[str],
    scope_terms: list[str],
    limit: int,
) -> list[dict[str, Any]]:
    normalized_item_terms = [
        normalize(term)
        for term in item_terms
        if len(normalize(term)) >= 3
    ]
    if not normalized_item_terms:
        return []

    rows = [
        clause.as_dict()
        for clause in engine.clauses
        if any(term in normalize(clause.item) for term in normalized_item_terms)
    ]
    if not rows:
        return []

    scoped_rows = _filter_by_standard_scope(rows, scope_terms)
    if scoped_rows:
        rows = scoped_rows

    rows = sorted(
        rows,
        key=lambda row: (
            -_term_match_score(row, item_terms, scope_terms),
            str(row.get("sheet", "")),
            int(row.get("row", 0) or 0),
            int(row.get("column", 0) or 0),
        ),
    )
    return rows[:limit]


def to_source_dict(clause: dict[str, Any]) -> dict[str, str]:
    return {
        "product": str(clause.get("product", "")),
        "item": str(clause.get("item", "")),
        "standard": str(clause.get("standard", "")),
        "requirement": str(clause.get("requirement", "")),
        "source_id": str(clause.get("source_id", "")),
        "source_link": str(clause.get("source_link", "")),
        "sheet": str(clause.get("sheet", "")),
    }


def build_rag_messages(
    question: str, clauses: Iterable[dict[str, Any]]
) -> list[ChatMessage]:
    clauses_list = list(clauses)
    context = _format_context(clauses_list)
    user_prompt = (
        f"【检索上下文】\n{context}\n\n"
        f"【用户问题】\n{question}\n\n"
        "请基于【检索上下文】回答用户问题；如上下文与问题无关或信息不足，请明确说明“当前标准库未检索到相关内容”。"
    )
    return [
        ChatMessage(role="system", content=SYSTEM_PROMPT),
        ChatMessage(role="user", content=user_prompt),
    ]


_MAX_CONTEXT_CHARS = 6000
_MAX_REQUIREMENT_CHARS = 200


def _format_context(clauses: list[dict[str, Any]]) -> str:
    if not clauses:
        return "（无检索结果）"
    lines: list[str] = []
    total_chars = 0
    for index, clause in enumerate(clauses, start=1):
        product = clause.get("product", "")
        item = clause.get("item", "")
        standard = clause.get("standard", "")
        requirement = str(clause.get("requirement", ""))
        source_id = clause.get("source_id", "")
        if len(requirement) > _MAX_REQUIREMENT_CHARS:
            requirement = requirement[:_MAX_REQUIREMENT_CHARS] + "…"
        line = (
            f"{index}. 产品/材料：{product}；项目名称：{item}；"
            f"标准：{standard}；技术要求：{requirement}；来源：{source_id}"
        )
        if total_chars + len(line) > _MAX_CONTEXT_CHARS and lines:
            break
        lines.append(line)
        total_chars += len(line)
    return "\n".join(lines)


def _split_terms(question: str) -> list[str]:
    text = question
    for stop_word in ("有什么", "有哪些", "什么", "要求", "相关", "标准", "内容", "了解", "是", "哪些", "有哪些", "的"):
        text = text.replace(stop_word, " ")
    separators = " ，,。？?；;：:"
    terms: list[str] = []
    current = ""
    for char in text:
        if char in separators:
            if current:
                terms.append(current)
                current = ""
        else:
            current += char
    if current:
        terms.append(current)

    long_terms = [term for term in terms if len(term) >= 2]
    if not long_terms:
        return []

    # 仅对中文片段做 2-gram 滑窗，过滤掉纯 ASCII 噪音
    expanded: list[str] = []
    for term in long_terms:
        if _is_chinese(term) and len(term) > 3:
            expanded.append(term)
            for start in range(len(term) - 1):
                chunk = term[start:start + 2]
                if len(chunk) >= 2:
                    expanded.append(chunk)
        else:
            expanded.append(term)
    # 只保留含有中文的项，去重保持顺序
    seen: set[str] = set()
    result: list[str] = []
    for term in expanded:
        if not _is_chinese(term):
            continue
        if term not in seen:
            seen.add(term)
            result.append(term)
    return result


def _is_chinese(text: str) -> bool:
    return any("一" <= ch <= "鿿" for ch in text)


def clean_llm_answer(content: str | None) -> str:
    text = (content or "").strip()
    if not text:
        return ""
    text = re.sub(r"<think\b[^>]*>.*?</think>", "", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<think\b[^>]*>.*$", "", text, flags=re.IGNORECASE | re.DOTALL)
    return text.strip()
