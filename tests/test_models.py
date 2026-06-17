from __future__ import annotations

import unittest

from sound_barrier_query.models import StandardClause


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


if __name__ == "__main__":
    unittest.main()
