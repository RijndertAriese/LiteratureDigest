import os
import tempfile
import unittest

from bot.main import mark_cross_topic_duplicates
from bot.pdf_builder import _truncate, build_pdf
from tests.fixtures import paper, stats_for


class BuildPdfTest(unittest.TestCase):
    def test_builds_with_markup_ampersands_empty_topic_and_duplicates(self):
        peer = {
            "Topic <A> & More": [
                paper("<i>Italic</i> title & co", impact=9.1, doi="10.1/a"),
                paper("Whitelisted", impact=1.0, impact_whitelisted=True),
            ],
            "Topic B": [paper("<i>Italic</i> title & co", impact=9.1, doi="10.1/a")],
            "Empty Topic": [],
        }
        preprints = {
            "Topic <A> & More": [paper("Preprint", source="bioRxiv", journal="bioRxiv preprint")],
            "Topic B": [],
            "Empty Topic": [],
        }
        mark_cross_topic_duplicates(peer, preprints)
        stats = stats_for(peer, preprints, warnings=["fetch_arxiv failed for 'x & y': <timeout>"])

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "digest.pdf")
            build_pdf(stats, peer, preprints, path)
            self.assertGreater(os.path.getsize(path), 1000)

    def test_builds_with_followed_badges_reasons_summary_and_oa(self):
        from bot.formatting import FOLLOWED_TOPIC
        peer = {
            FOLLOWED_TOPIC: [paper("Own paper", followed=["Ariese HCR"], doi="10.1/own")],
            "Topic": [
                paper("Own paper", followed=["Ariese HCR"], doi="10.1/own"),
                paper("Review & more", impact=8.0, reason="Maps <TAM> states.",
                      oa_url="https://pmc.example/a?x=1&y=2",
                      article_types=["Review", "Clinical Trial, Phase I"]),
            ],
        }
        preprints = {FOLLOWED_TOPIC: [paper("Own preprint", source="medRxiv")], "Topic": []}
        mark_cross_topic_duplicates(peer, preprints)
        stats = stats_for(peer, preprints)
        stats["topics"][1]["summary"] = "Two themes: TAMs & imaging."

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "digest.pdf")
            build_pdf(stats, peer, preprints, path)
            self.assertGreater(os.path.getsize(path), 1000)

    def test_truncate_cuts_on_word_boundary(self):
        text = "word " * 300
        cut = _truncate(text, 50)
        self.assertTrue(cut.endswith(" …"))
        self.assertLessEqual(len(cut), 52)
        self.assertNotIn("wor …", cut)


if __name__ == "__main__":
    unittest.main()
