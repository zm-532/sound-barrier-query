from __future__ import annotations

import unittest
from pathlib import Path

from sound_barrier_query.xlsx_loader import load_workbook_clauses, load_workbook_tables


WORKBOOK = Path(__file__).resolve().parents[1] / "docs" / "国内声屏障标准汇总表.xlsx"
FOREIGN_WORKBOOK = Path(__file__).resolve().parents[1] / "docs" / "国外及香港声屏障标准汇总表本.xlsx"


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


if __name__ == "__main__":
    unittest.main()
