import unittest

from bot.mailer import build_email
from tests.fixtures import paper, stats_for


class BuildEmailTest(unittest.TestCase):
    def setUp(self):
        self.peer = {
            "Gliomas": [paper(f"Paper {i}", impact=10 - i) for i in range(5)],
            "Microglia": [paper("<script>x</script> & friends", impact=5.0)],
        }
        self.preprints = {"Gliomas": [paper("Pre", source="arXiv")], "Microglia": []}

    def test_subject_counts_and_date(self):
        subject, _, _ = build_email(stats_for(self.peer, self.preprints), self.peer, self.preprints)
        self.assertEqual(subject, "Literature Digest — 19 Oct 2026 · 6 papers, 1 preprint")

    def test_warning_prefix(self):
        stats = stats_for(self.peer, self.preprints, warnings=["fetch_arxiv failed"])
        subject, text, html = build_email(stats, self.peer, self.preprints)
        self.assertTrue(subject.startswith("⚠ "))
        self.assertIn("fetch_arxiv failed", text)
        self.assertIn("fetch_arxiv failed", html)

    def test_top_picks_limited_to_three_and_escaped(self):
        _, text, html = build_email(stats_for(self.peer, self.preprints), self.peer, self.preprints)
        self.assertIn("Paper 2", html)
        self.assertNotIn("Paper 3", html)
        self.assertNotIn("Paper 3", text)
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertIn("IF 10.0", text)


if __name__ == "__main__":
    unittest.main()
