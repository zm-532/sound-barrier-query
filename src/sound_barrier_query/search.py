from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable

from .models import StandardClause, StandardTable


@dataclass(frozen=True)
class SearchResult:
    score: int
    clause: StandardClause


class SearchEngine:
    def __init__(self, clauses: Iterable[StandardClause], tables: Iterable[StandardTable] | None = None):
        self.clauses = list(clauses)
        self.products = sorted({clause.product for clause in self.clauses})
        self.standards = sorted({clause.standard for clause in self.clauses})
        self.tables = list(tables or [])
        self.table_by_material = {table.material: table for table in self.tables}
        self.materials = (
            list(dict.fromkeys(table.material for table in self.tables))
            if self.tables
            else list(dict.fromkeys(clause.sheet for clause in self.clauses))
        )
        self.material_groups = self._material_groups()

    def search_standard(self, query: str, limit: int = 100) -> list[dict[str, str | int]]:
        needle = normalize(query)
        if not needle:
            return []
        matches = []
        for clause in self.clauses:
            standard = normalize(clause.standard)
            if needle in standard:
                matches.append(SearchResult(_score_text(needle, standard), clause))
        return _ranked_dicts(matches, limit)

    def search_product(self, query: str, limit: int = 100) -> list[dict[str, str | int]]:
        needle = normalize(query)
        if not needle:
            return []
        matches = []
        for clause in self.clauses:
            haystack = normalize(f"{clause.sheet} {clause.product}")
            if needle in haystack:
                matches.append(SearchResult(_score_text(needle, haystack), clause))
        return _ranked_dicts(matches, limit)

    def search_keyword(self, query: str, limit: int = 100) -> list[dict[str, str | int]]:
        needle = normalize(query)
        if not needle:
            return []
        matches = []
        for clause in self.clauses:
            haystack = normalize(
                f"{clause.sheet} {clause.product} {clause.item} {clause.standard} {clause.requirement}"
            )
            if needle in haystack:
                matches.append(SearchResult(_score_text(needle, haystack), clause))
        return _ranked_dicts(matches, limit)

    def compare_product(self, query: str) -> dict[str, dict[str, dict[str, str | int]]]:
        grouped: dict[str, dict[str, dict[str, str | int]]] = defaultdict(dict)
        for row in self.search_product(query, limit=1000):
            grouped[str(row["item"])][str(row["standard"])] = row
        return dict(grouped)

    def material_table(self, material: str) -> dict[str, object]:
        sheet_name = self._resolve_material(material)
        if sheet_name in self.table_by_material:
            table = self.table_by_material[sheet_name]
            return {
                "material": table.material,
                "title": table.title,
                "group": table.group,
                "base_columns": table.base_columns,
                "standard_columns": table.standard_columns,
                "rows": table.rows,
            }

        sheet_clauses = [clause for clause in self.clauses if clause.sheet == sheet_name]
        standard_columns = [
            standard
            for _, standard in sorted(
                {
                    (clause.column, clause.standard)
                    for clause in sheet_clauses
                },
                key=lambda pair: pair[0],
            )
        ]

        row_groups: dict[tuple[int, str, str], dict[str, str | int]] = {}
        for clause in sorted(sheet_clauses, key=lambda item: (item.row, item.column)):
            key = (clause.row, clause.product, clause.item)
            if key not in row_groups:
                row_groups[key] = {
                    "序号": len(row_groups) + 1,
                    "部件": clause.product,
                    "检测项目": clause.item,
                    "source_row": clause.row,
                }
                for standard in standard_columns:
                    row_groups[key][standard] = ""
            row_groups[key][clause.standard] = clause.requirement

        rows = list(row_groups.values())
        return {
            "material": sheet_name,
            "title": f"{sheet_name}技术要求",
            "group": sheet_clauses[0].group if sheet_clauses else "国内标准",
            "base_columns": ["序号", "部件", "检测项目"],
            "standard_columns": standard_columns,
            "rows": rows,
        }

    def fuzzy_search(self, query: str, limit: int = 100) -> dict[str, object]:
        text = (query or "").strip()
        if not text:
            return _empty_fuzzy_payload(query)

        material = self._find_material(text)
        if material:
            table = self.material_table(material)
            terms = _extract_search_terms(text, material)
            if not terms:
                return {
                    "query": text,
                    "result_type": "material_table",
                    "matched_material": material,
                    "matched_terms": [],
                    "missing_terms": [],
                    "summary": f"已识别到材料“{material}”，下方展示该材料的标准信息。",
                    "table": table,
                    "results": [],
                }

            rows = list(table.get("rows", []))
            matched_terms = [term for term in terms if any(_row_contains(row, term) for row in rows)]
            missing_terms = [term for term in terms if term not in matched_terms]
            filtered_rows = [row for row in rows if all(_row_contains(row, term) for term in matched_terms)]
            if matched_terms and filtered_rows:
                filtered_table = dict(table)
                filtered_table["rows"] = filtered_rows
                return {
                    "query": text,
                    "result_type": "material_table",
                    "matched_material": material,
                    "matched_terms": matched_terms,
                    "missing_terms": missing_terms,
                    "summary": _material_match_summary(material, matched_terms, missing_terms, len(filtered_rows)),
                    "table": filtered_table,
                    "results": [],
                }

            return {
                "query": text,
                "result_type": "material_table",
                "matched_material": material,
                "matched_terms": [],
                "missing_terms": terms,
                "summary": f"未检索到“{material} + {'、'.join(terms)}”的直接条目，已为你展示“{material}”的完整标准信息。",
                "table": table,
                "results": [],
            }

        terms = _extract_search_terms(text, "")
        results = self._search_terms(terms, limit) if terms else self.search_keyword(text, limit)
        summary = (
            f"已按关键词“{'、'.join(terms) if terms else text}”进行模糊检索，找到 {len(results)} 条相关标准内容。"
            if results
            else f"未检索到与“{text}”直接相关的标准内容。"
        )
        return {
            "query": text,
            "result_type": "clauses",
            "matched_material": "",
            "matched_terms": terms,
            "missing_terms": [] if results else terms,
            "summary": summary,
            "table": None,
            "results": results,
        }

    def _material_groups(self) -> list[dict[str, object]]:
        groups: dict[str, list[str]] = {}
        if self.tables:
            for table in self.tables:
                groups.setdefault(table.group, []).append(table.material)
        else:
            for clause in self.clauses:
                materials = groups.setdefault(clause.group, [])
                if clause.sheet not in materials:
                    materials.append(clause.sheet)
        return [{"name": name, "materials": materials} for name, materials in groups.items()]

    def _find_material(self, query: str) -> str:
        needle = normalize(query)
        for sheet in self.materials:
            if normalize(sheet) == needle:
                return sheet
        for sheet in self.materials:
            if normalize(sheet) and normalize(sheet) in needle:
                return sheet
        for sheet in self.materials:
            if needle and needle in normalize(sheet):
                return sheet
        return ""

    def _resolve_material(self, material: str) -> str:
        needle = normalize(material)
        for sheet in self.materials:
            if normalize(sheet) == needle:
                return sheet
        for sheet in self.materials:
            if needle in normalize(sheet):
                return sheet
        return self.materials[0] if self.materials else material

    def _search_terms(self, terms: list[str], limit: int) -> list[dict[str, str | int]]:
        if not terms:
            return []
        matches = []
        for clause in self.clauses:
            haystack = normalize(
                f"{clause.sheet} {clause.product} {clause.item} {clause.standard} {clause.requirement}"
            )
            matched_count = sum(1 for term in terms if normalize(term) in haystack)
            if matched_count:
                matches.append(SearchResult(matched_count * 100 + len(haystack), clause))
        return _ranked_dicts(matches, limit)

    def search(self, query: str, mode: str, limit: int = 100) -> list[dict[str, str | int]]:
        if mode == "standard":
            return self.search_standard(query, limit)
        if mode == "product":
            return self.search_product(query, limit)
        return self.search_keyword(query, limit)


def normalize(value: str) -> str:
    text = value.upper()
    text = text.replace("Ⅰ", "I").replace("Ⅱ", "II")
    text = re.sub(r"[\s　《》〈〉（）()第部分：:、，,。./\\\-—_]+", "", text)
    return text


def _empty_fuzzy_payload(query: str) -> dict[str, object]:
    return {
        "query": query,
        "result_type": "empty",
        "matched_material": "",
        "matched_terms": [],
        "missing_terms": [],
        "summary": "请输入要检索的材料、标准号或技术关键词。",
        "table": None,
        "results": [],
    }


def _extract_search_terms(query: str, material: str) -> list[str]:
    text = normalize(query)
    if material:
        text = text.replace(normalize(material), "")
    for stopword in _STOPWORDS:
        text = text.replace(stopword, "")
    return [text] if text else []


def _row_contains(row: dict[str, object], term: str) -> bool:
    haystack = normalize(" ".join(str(value) for value in row.values()))
    return normalize(term) in haystack


def _material_match_summary(material: str, matched_terms: list[str], missing_terms: list[str], count: int) -> str:
    matched_text = "、".join(matched_terms)
    if missing_terms:
        return (
            f"已识别到材料“{material}”和关键词“{matched_text}”，下方展示相关标准条目（共 {count} 行）；"
            f"未检索到关键词“{'、'.join(missing_terms)}”的直接条目。"
        )
    return f"已识别到材料“{material}”和关键词“{matched_text}”，下方展示相关标准条目（共 {count} 行）。"


def _score_text(needle: str, haystack: str) -> int:
    if haystack == needle:
        return 100
    if haystack.startswith(needle):
        return 80
    return max(1, 60 - haystack.find(needle))


def _ranked_dicts(matches: list[SearchResult], limit: int) -> list[dict[str, str | int]]:
    ranked = sorted(
        matches,
        key=lambda result: (
            -result.score,
            result.clause.sheet,
            result.clause.item,
            result.clause.standard,
            result.clause.source_id,
        ),
    )
    return [result.clause.as_dict() for result in ranked[:limit]]


_STOPWORDS = [
    "请问",
    "查询",
    "搜索",
    "关于",
    "相关",
    "有关",
    "内容",
    "信息",
    "国内",
    "国外",
    "标准",
    "要求",
    "项目名称",
    "有哪些",
    "是什么",
    "多少",
    "怎么",
    "的",
]
