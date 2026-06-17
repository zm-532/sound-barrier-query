from __future__ import annotations

import unittest
from pathlib import Path

from sound_barrier_query.assistant import StandardAssistant
from sound_barrier_query.search import SearchEngine
from sound_barrier_query.xlsx_loader import load_workbook_clauses


WORKBOOK = Path(__file__).resolve().parents[1] / "docs" / "国内声屏障标准汇总表.xlsx"


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

    def test_retrieve_filters_material_hits_before_truncating(self):
        clauses = self.assistant.retrieve("金属单元板的降噪系数要求")

        self.assertTrue(clauses, "应检索到金属单元板降噪系数条款")
        self.assertTrue(
            all(clause["sheet"] == "金属单元板" for clause in clauses),
            "应优先保留金属单元板工作表内的条款",
        )
        self.assertTrue(
            any(clause["item"] == "降噪系数" for clause in clauses),
            "应包含 Excel 第 48 行的降噪系数条款",
        )
        self.assertTrue(all(clause["item"] == "降噪系数" for clause in clauses))
        self.assertEqual(clauses[0]["item"], "降噪系数")
        self.assertNotEqual(clauses[0]["item"], "刻度标尺")

    def test_retrieve_understands_railway_metal_board_sound_insulation_aliases(self):
        clauses = self.assistant.retrieve("铁路金属板的隔声量是多少")

        self.assertTrue(clauses, "应检索到铁路金属板隔声量条款")
        self.assertTrue(all(clause["sheet"] == "金属单元板" for clause in clauses))
        self.assertTrue(all(clause["item"] == "计权隔声量" for clause in clauses))
        self.assertTrue(
            all(
                any(keyword in str(clause["standard"]) for keyword in ("铁路", "TB", "Q/CR"))
                for clause in clauses
            ),
            "铁路问法应优先返回铁路相关标准列",
        )

    def test_retrieve_understands_metal_absorbing_board_sound_insulation_aliases(self):
        clauses = self.assistant.retrieve("金属吸声板隔音量")

        self.assertTrue(clauses)
        self.assertTrue(all(clause["sheet"] == "金属单元板" for clause in clauses))
        self.assertTrue(all(clause["item"] == "计权隔声量" for clause in clauses))

    def test_retrieve_understands_acrylic_transparent_board_aliases(self):
        clauses = self.assistant.retrieve("加筋亚克力透明板透光率要求")

        self.assertTrue(clauses)
        self.assertTrue(all(clause["sheet"] == "亚克力板" for clause in clauses))
        self.assertTrue(any("透光率" in str(clause["item"]) for clause in clauses))
        self.assertTrue(str(clauses[0]["item"]).startswith("透光率"))

    def test_retrieve_searches_item_across_materials_when_material_is_omitted(self):
        clauses = self.assistant.retrieve("公路声屏障防火要求等级")

        self.assertTrue(clauses, "应跨材料检索到公路声屏障防火条款")
        self.assertTrue(all(clause["item"] == "防火性能" for clause in clauses))
        self.assertTrue(
            all(any(keyword in str(clause["standard"]) for keyword in ("公路", "JT/T")) for clause in clauses)
        )
        sheets = {clause["sheet"] for clause in clauses}
        self.assertIn("金属单元板", sheets)
        self.assertIn("非金属单元板", sheets)

    def test_retrieve_uses_material_item_groups_for_broad_mechanical_queries(self):
        clauses = self.assistant.retrieve("岩棉的力学要求")

        self.assertTrue(clauses, "应检索到岩棉力学类条款")
        self.assertTrue(all(clause["sheet"] == "岩棉" for clause in clauses))
        items = {str(clause["item"]) for clause in clauses}
        self.assertEqual(items, {"垂直于表面的抗拉强度kPa", "压缩强度kPa"})
        self.assertTrue(any(clause["source_id"] == "岩棉!D12" for clause in clauses))
        self.assertTrue(any(clause["source_id"] == "岩棉!D13" for clause in clauses))

    def test_retrieve_returns_empty_for_known_unrelated_query(self):
        clauses = self.assistant.retrieve("qwerasdfzxcv")
        self.assertEqual(clauses, [])


if __name__ == "__main__":
    unittest.main()
