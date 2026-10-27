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


class EmailExtrasTest(unittest.TestCase):
    def test_followed_listed_in_full_first_with_summary_reason_and_oa(self):
        from bot.formatting import FOLLOWED_TOPIC
        peer = {
            FOLLOWED_TOPIC: [paper(f"Own {i}", followed=["Ariese HCR"]) for i in range(5)],
            "Gliomas": [paper("Top", impact=9.0, reason="Shows CSF1R blockade works.",
                              oa_url="https://pmc.example/top.pdf",
                              article_types=["Journal Article", "Review"])],
        }
        preprints = {FOLLOWED_TOPIC: [], "Gliomas": []}
        stats = stats_for(peer, preprints)
        stats["topics"][1]["summary"] = "Myeloid & checkpoint themes."

        _, text, html = build_email(stats, peer, preprints)

        self.assertIn("Own 4", html)                       # not capped at 3
        self.assertLess(html.index("Followed authors"), html.index("Gliomas</h3>"))
        self.assertIn("★ Ariese HCR", html)
        self.assertIn("Myeloid &amp; checkpoint themes.", html)
        self.assertIn("Shows CSF1R blockade works.", html)
        self.assertIn("https://pmc.example/top.pdf", html)
        self.assertIn("[Review] Top", text)
        self.assertIn("Why: Shows CSF1R blockade works.", text)


if __name__ == "__main__":
    unittest.main()
