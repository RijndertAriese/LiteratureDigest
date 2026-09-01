import unittest

from bot.main import filter_by_impact


def _paper(journal, impact):
    return {"source": "PubMed", "journal": journal, "impact_factor": impact}


class FilterByImpactTest(unittest.TestCase):
    def test_drops_below_threshold_keeps_at_or_above(self):
        peer = [
            _paper("Big Journal", 12.0),
            _paper("Small Journal", 1.5),
            _paper("Exactly", 3.5),
        ]
        kept, dropped = filter_by_impact(peer, 3.5, [])
        self.assertEqual([p["journal"] for p in kept], ["Big Journal", "Exactly"])
        self.assertEqual(dropped, 1)

    def test_unknown_metric_is_kept(self):
        peer = [_paper("New Journal", None)]
        kept, dropped = filter_by_impact(peer, 3.5, [])
        self.assertEqual(len(kept), 1)
        self.assertEqual(dropped, 0)

    def test_allowlist_substring_is_case_insensitive_and_wins(self):
        peer = [_paper("Neuro-Oncology", 1.1)]
        kept, dropped = filter_by_impact(peer, 3.5, ["neuro-oncology"])
        self.assertEqual(len(kept), 1)
        self.assertEqual(dropped, 0)
        self.assertTrue(kept[0]["impact_whitelisted"])

    def test_non_allowlisted_low_journal_marked_not_whitelisted(self):
        peer = [_paper("Predatory Weekly", 0.4)]
        kept, dropped = filter_by_impact(peer, 3.5, ["neuro-oncology"])
        self.assertEqual(kept, [])
        self.assertEqual(dropped, 1)
        self.assertFalse(peer[0]["impact_whitelisted"])


if __name__ == "__main__":
    unittest.main()
