import unittest

from bot.main import mark_cross_topic_duplicates, rank_papers
from tests.fixtures import paper


class RankPapersTest(unittest.TestCase):
    def test_whitelisted_then_impact_then_unknown_newest_first_on_ties(self):
        papers = [
            paper("unknown", impact=None),
            paper("low", impact=4.0),
            paper("high-old", impact=12.0, date="2026-10-13"),
            paper("high-new", impact=12.0, date="2026-10-18"),
            paper("whitelisted", impact=1.0, impact_whitelisted=True),
        ]
        ranked = [p["title"] for p in rank_papers(papers)]
        self.assertEqual(ranked, ["whitelisted", "high-new", "high-old", "low", "unknown"])


class CrossTopicDuplicatesTest(unittest.TestCase):
    def test_repeat_points_to_first_topic_by_doi_or_title(self):
        a1, a2 = paper("Shared", doi="10.1/x"), paper("Shared", doi="10.1/X")
        b1, b2 = paper("No DOI Paper"), paper("no doi paper")
        only = paper("Only here")
        peer = {"Topic A": [a1, b1], "Topic B": [a2, only], "Topic C": [b2]}

        mark_cross_topic_duplicates(peer, {})

        self.assertEqual(a2["duplicate_of"], "Topic A")
        self.assertEqual(b2["duplicate_of"], "Topic A")
        self.assertEqual(a1["also_in"], ["Topic B"])
        self.assertEqual(b1["also_in"], ["Topic C"])
        self.assertNotIn("duplicate_of", only)
        self.assertNotIn("duplicate_of", a1)


if __name__ == "__main__":
    unittest.main()
