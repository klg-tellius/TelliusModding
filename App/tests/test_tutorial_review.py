from __future__ import annotations

import sys
import unittest
from pathlib import Path


TOOLS = Path(__file__).resolve().parents[1] / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from review_tutorials import MODDING, review_tutorials  # noqa: E402


class TutorialReviewTests(unittest.TestCase):
    def test_repository_tutorials_satisfy_staged_contract(self) -> None:
        errors, counts = review_tutorials()
        self.assertEqual(errors, [])
        self.assertEqual(sum(counts.values()), len(list(MODDING.glob("[0-9][0-9]-*.md"))))
        self.assertGreaterEqual(counts["draft"] + counts["verified"] + counts["published"], 4)


if __name__ == "__main__":
    unittest.main()
