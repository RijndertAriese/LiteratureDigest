import unittest

from bot.fetcher import _NON_PAPER_TYPES, _pubmed_article_types
from bot.formatting import badges


class ArticleTypeTest(unittest.TestCase):
    def test_reads_publication_types(self):
        art = {"PublicationTypeList": ["Journal Article", "Review"]}
        self.assertEqual(_pubmed_article_types(art), ["Journal Article", "Review"])
        self.assertEqual(_pubmed_article_types({}), [])

    def test_notices_are_not_papers(self):
        for kind in ("Published Erratum", "Comment", "Editorial", "Retraction of Publication"):
            self.assertIn(kind, _NON_PAPER_TYPES)
        for kind in ("Journal Article", "Review", "Clinical Trial, Phase II", "Letter"):
            self.assertNotIn(kind, _NON_PAPER_TYPES)


class BadgesTest(unittest.TestCase):
    def test_type_badges(self):
        paper = {"source": "PubMed",
                 "article_types": ["Journal Article", "Systematic Review", "Review",
                                   "Clinical Trial, Phase II", "Randomized Controlled Trial"]}
        self.assertEqual(badges(paper), ["Systematic review", "Clinical trial"])

    def test_preprint_and_followed(self):
        paper = {"source": "medRxiv", "article_types": [], "followed": ["Ariese HCR"]}
        self.assertEqual(badges(paper), ["Preprint", "Followed: Ariese HCR"])


if __name__ == "__main__":
    unittest.main()
