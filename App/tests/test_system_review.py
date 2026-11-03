from __future__ import annotations

import sys
import unittest
from pathlib import Path


TOOLS = Path(__file__).resolve().parents[1] / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import review_systems  # noqa: E402


class SystemReviewTests(unittest.TestCase):
    def test_inventory_has_stable_complete_id_sequence(self) -> None:
        entries = review_systems.inventory_entries()
        self.assertEqual(list(entries), [f"FE9-SYS-{number:03d}" for number in range(1, 385)])

    def test_repository_review_metadata_is_consistent(self) -> None:
        errors, state = review_systems.review_repository()
        self.assertEqual(errors, [])
        self.assertEqual(len(state), 384)

    def test_committed_dashboard_is_current(self) -> None:
        errors, state = review_systems.review_repository()
        self.assertEqual(errors, [])
        self.assertIsNone(review_systems.update_or_check_report(state, write=False))


if __name__ == "__main__":
    unittest.main()
