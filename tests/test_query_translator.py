import unittest

from bot.main import parse_topics
from bot.query_translator import _fallback, _normalise, _user_message, _with_key_terms


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
            {"topic": "CAR myeloid", "hints": ["CAR-M", " CAR macrophage "], "criteria": " strict "},
            {"topic": "imaging", "hints": [["imaging", "histology"], "spatial transcriptomics"]},
        ])
        self.assertEqual(parsed, [
            {"topic": "plain topic", "hints": [], "criteria": ""},
            {"topic": "CAR myeloid", "hints": [["CAR-M", "CAR macrophage"]], "criteria": "strict"},
            {"topic": "imaging", "hints": [["imaging", "histology"], ["spatial transcriptomics"]],
             "criteria": ""},
        ])

    def test_hints_are_added_to_the_prompt(self):
        self.assertEqual(_user_message("x", None), 'Topic: "x"')
        self.assertIn('Key terms: ("CAR-M" OR "CAR macrophage")',
                      _user_message("x", [["CAR-M", "CAR macrophage"]]))
        self.assertIn("Inclusion criteria: both", _user_message("x", criteria="both"))


class KeyTermQueryTest(unittest.TestCase):
    def test_key_term_variant_is_always_appended(self):
        base = {"display": "D", "pubmed": ["groq query"], "arxiv": [], "biorxiv": [["imaging"]]}
        out = _with_key_terms(base, [["imaging", "Live imaging"], ["spatial transcriptomics"]])

        self.assertEqual(out["pubmed"], [
            "groq query",
            '("imaging"[tiab] OR "Live imaging"[tiab]) AND ("spatial transcriptomics"[tiab])',
        ])
        self.assertEqual(out["arxiv"], [
            'cat:q-bio AND ("imaging" OR "Live imaging") AND ("spatial transcriptomics")',
        ])
        self.assertEqual(out["biorxiv"], [
            ["imaging"],
            ["imaging", "spatial transcriptomics"],
            ["live imaging", "spatial transcriptomics"],
        ])
        self.assertEqual(base["pubmed"], ["groq query"])

    def test_no_hints_leaves_queries_unchanged(self):
        base = {"display": "D", "pubmed": ["q"], "arxiv": [], "biorxiv": []}
        self.assertEqual(_with_key_terms(base, []), base)


if __name__ == "__main__":
    unittest.main()
