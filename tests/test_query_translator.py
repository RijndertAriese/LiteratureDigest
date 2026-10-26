import unittest

from bot.main import parse_topics
from bot.query_translator import _fallback, _normalise, _user_message


class NormaliseTest(unittest.TestCase):
    def test_coerces_strings_to_lists_and_lowercases_keywords(self):
        out = _normalise({
            "pubmed": "glioma AND myeloid",
            "arxiv": ["cat:q-bio AND glioma"],
            "biorxiv": [["Glioma", "Myeloid"], "microglia"],
            "display": "Myeloid Cells",
        })
        self.assertEqual(out["pubmed"], ["glioma AND myeloid"])
        self.assertEqual(out["biorxiv"], [["glioma", "myeloid"], ["microglia"]])

    def test_missing_key_raises(self):
        with self.assertRaises(ValueError):
            _normalise({"pubmed": ["x"], "arxiv": [], "display": "D"})


class FallbackTest(unittest.TestCase):
    def test_fallback_uses_topic_and_content_words(self):
        out = _fallback("live imaging combined with spatial transcriptomics")
        self.assertEqual(out["pubmed"], ["live imaging combined with spatial transcriptomics"])
        self.assertEqual(out["biorxiv"], [["live", "imaging", "spatial", "transcriptomics"]])


class TopicHintsTest(unittest.TestCase):
    def test_parse_topics_accepts_strings_and_hint_dicts(self):
        parsed = parse_topics([
            " plain topic ",
            {"topic": "CAR myeloid", "hints": ["CAR-M", " CAR macrophage "]},
        ])
        self.assertEqual(parsed, [("plain topic", []), ("CAR myeloid", ["CAR-M", "CAR macrophage"])])

    def test_hints_are_added_to_the_prompt(self):
        self.assertEqual(_user_message("x", None), 'Topic: "x"')
        self.assertIn('Key terms: "CAR-M"; "CAR macrophage"',
                      _user_message("x", ["CAR-M", "CAR macrophage"]))


if __name__ == "__main__":
    unittest.main()
