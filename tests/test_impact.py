import unittest
from unittest import mock

from bot import impact


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def _fake_openalex(url, params=None, timeout=None):
    """Minimal OpenAlex stand-in keyed on the endpoint and filter."""
    params = params or {}
    if url.endswith("/works"):
        # doi filter -> one work per DOI, alternating known/unknown journals
        return _FakeResponse({
            "results": [
                {
                    "doi": "https://doi.org/10.1/high",
                    "primary_location": {"source": {"id": "https://openalex.org/S_HIGH"}},
                },
                {
                    "doi": "https://doi.org/10.1/low",
                    "primary_location": {"source": {"id": "https://openalex.org/S_LOW"}},
                },
            ]
        })
    if url.endswith("/sources") and "filter" in params:
        return _FakeResponse({
            "results": [
                {"id": "https://openalex.org/S_HIGH", "summary_stats": {"2yr_mean_citedness": 12.5}},
                {"id": "https://openalex.org/S_LOW", "summary_stats": {"2yr_mean_citedness": 1.2}},
            ]
        })
    if url.endswith("/sources") and "search" in params:
        return _FakeResponse({"results": []})  # name lookup fails -> unknown
    raise AssertionError(f"unexpected call: {url} {params}")


class ImpactTest(unittest.TestCase):
    def setUp(self):
        impact._source_metric.clear()
        impact._name_to_source.clear()

    def test_annotate_sets_metric_from_doi(self):
        papers = [
            {"doi": "10.1/high", "journal": "Big Journal"},
            {"doi": "10.1/low", "journal": "Small Journal"},
        ]
        with mock.patch.object(impact.requests, "get", side_effect=_fake_openalex):
            impact.annotate_impact(papers)

        self.assertAlmostEqual(papers[0]["impact_factor"], 12.5)
        self.assertAlmostEqual(papers[1]["impact_factor"], 1.2)

    def test_unknown_journal_is_none_not_error(self):
        papers = [{"doi": "", "journal": "Journal of Nowhere"}]
        with mock.patch.object(impact.requests, "get", side_effect=_fake_openalex):
            impact.annotate_impact(papers)

        self.assertIsNone(papers[0]["impact_factor"])

    def test_network_failure_is_fail_open(self):
        papers = [{"doi": "10.1/high", "journal": "Big Journal"}]
        with mock.patch.object(impact.requests, "get", side_effect=RuntimeError("boom")):
            impact.annotate_impact(papers)

        self.assertIsNone(papers[0]["impact_factor"])

    def test_empty_list_makes_no_calls(self):
        with mock.patch.object(impact.requests, "get", side_effect=AssertionError):
            impact.annotate_impact([])


if __name__ == "__main__":
    unittest.main()
