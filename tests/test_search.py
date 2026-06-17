from __future__ import annotations

import unittest
from pathlib import Path

from sound_barrier_query.models import StandardClause
from sound_barrier_query.search import SearchEngine
from sound_barrier_query.xlsx_loader import load_workbook_clauses, load_workbook_tables


WORKBOOK = Path(__file__).resolve().parents[1] / "docs" / "国内声屏障标准汇总表.xlsx"
FOREIGN_WORKBOOK = Path(__file__).resolve().parents[1] / "docs" / "国外及香港声屏障标准汇总表本.xlsx"


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

    def test_fuzzy_search_prioritises_item_match_over_long_requirement_match(self):
        engine = SearchEngine(
            [
                StandardClause("材料A", 2, 4, "材料A", "密度", "标准A", "80~120"),
                StandardClause(
                    "材料B",
                    2,
                    4,
                    "材料B",
                    "其他项目",
                    "标准B",
                    "这是一段很长的技术要求文本，其中只在要求内容中提到密度指标。",
                ),
            ]
        )

        payload = engine.fuzzy_search("密度")

        self.assertEqual(payload["results"][0]["item"], "密度")

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

    def test_material_table_returns_empty_payload_for_unknown_material(self):
        table = self.engine.material_table("不存在材料")

        self.assertEqual(table["material"], "不存在材料")
        self.assertEqual(table["title"], "未找到 不存在材料 的标准信息")
        self.assertEqual(table["base_columns"], [])
        self.assertEqual(table["standard_columns"], [])
        self.assertEqual(table["rows"], [])
        self.assertEqual(table["error"], "material_not_found")

    def test_fuzzy_search_filters_material_table_by_item_terms(self):
        tables = load_workbook_tables(WORKBOOK)
        engine = SearchEngine(load_workbook_clauses(WORKBOOK), tables=tables)

        payload = engine.fuzzy_search("岩棉的厚度")

        self.assertEqual(payload["result_type"], "material_table")
        self.assertEqual(payload["matched_material"], "岩棉")
        self.assertIn("厚度", payload["matched_terms"])
        self.assertEqual(payload["missing_terms"], [])
        self.assertIn("“岩棉”和关键词“厚度”", payload["summary"])
        self.assertIn("下方展示相关标准条目", payload["summary"])
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
        self.assertIn("未检索到“岩棉 + 不存在指标”的直接条目", payload["summary"])
        self.assertIn("已为你展示“岩棉”的完整标准信息", payload["summary"])
        self.assertEqual(len(payload["table"]["rows"]), len(full_table["rows"]))


if __name__ == "__main__":
    unittest.main()
