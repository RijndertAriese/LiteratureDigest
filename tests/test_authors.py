import unittest

from bot.authors import author_key, matches_followed


class AuthorKeyTest(unittest.TestCase):
    def test_same_person_across_source_styles(self):
        expected = ("ariese", "h")
        self.assertEqual(author_key("Ariese HCR"), expected)          # PubMed
        self.assertEqual(author_key("Ariese, H. C. R."), expected)    # bioRxiv / medRxiv
        self.assertEqual(author_key("H.C.R. Ariese"), expected)       # arXiv
        self.assertEqual(author_key("Hendrik Ariese"), expected)

    def test_multi_word_surname_and_accents(self):
        self.assertEqual(author_key("van der Berg AB"), ("van der berg", "a"))
        self.assertEqual(author_key("Müller, J."), ("muller", "j"))

    def test_empty(self):
        self.assertIsNone(author_key(""))


class MatchesFollowedTest(unittest.TestCase):
    def test_returns_config_names_that_author_the_paper(self):
        paper = {"author_list": ["Smith J", "Ariese, H. C. R.", "Doe A"]}
        self.assertEqual(matches_followed(paper, ["Ariese HCR", "Jones K"]), ["Ariese HCR"])

    def test_different_initial_does_not_match(self):
        paper = {"author_list": ["Ariese P"]}
        self.assertEqual(matches_followed(paper, ["Ariese HCR"]), [])


if __name__ == "__main__":
    unittest.main()
