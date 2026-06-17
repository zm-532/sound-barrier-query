from __future__ import annotations

import unittest

from sound_barrier_query.aliases import expand_query_with_aliases


class TestDomainAliases(unittest.TestCase):
    def test_expands_material_item_and_scope_aliases(self):
        expanded = expand_query_with_aliases("铁路金属板的隔声量是多少")

        self.assertIn("金属单元板", expanded)
        self.assertIn("计权隔声量", expanded)
        self.assertIn("铁路", expanded)


if __name__ == "__main__":
    unittest.main()
