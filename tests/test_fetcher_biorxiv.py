import unittest
from unittest import mock

from bot import fetcher


def _page(items, total):
    resp = mock.Mock()
    resp.json.return_value = {"collection": items, "messages": [{"total": total}]}
    return resp


def _item(doi, title, abstract=""):
    return {"doi": doi, "title": title, "abstract": abstract, "authors": "A; B", "date": "2026-10-20"}


class RxivTest(unittest.TestCase):
    def setUp(self):
        fetcher._RXIV_PAGE_CACHE.clear()

    def test_keyword_groups_need_all_terms_of_any_group(self):
        groups = [["myeloid", "glioma"], ["spatial transcriptomic"]]
        self.assertTrue(fetcher._rxiv_matches("Myeloid cells shape GLIOMA growth", groups))
        self.assertTrue(fetcher._rxiv_matches("Spatial transcriptomics atlas", groups))
        self.assertFalse(fetcher._rxiv_matches("Myeloid cells in the lung", groups))

    def test_pages_by_returned_size_and_caches_window(self):
        pages = [
            _page([_item(f"10.1/{i}", "glioma macrophages") for i in range(30)], 45),
            _page([_item(f"10.1/{i}", "other topic") for i in range(30, 45)], 45),
        ]
        with mock.patch.object(fetcher.requests, "get", side_effect=pages) as get, \
                mock.patch.object(fetcher.time, "sleep"):
            first = fetcher.fetch_rxiv("biorxiv", [["glioma"]], 7, 100)
            second = fetcher.fetch_rxiv("biorxiv", [["other"]], 7, 100)

        self.assertEqual(get.call_count, 2)
        self.assertIn("/30/json", get.call_args_list[1].args[0])
        self.assertEqual(len(first), 30)
        self.assertEqual(len(second), 15)

    def test_skips_repeated_versions_of_same_preprint(self):
        page = _page([_item("10.1/x", "glioma v1"), _item("10.1/x", "glioma v2")], 2)
        with mock.patch.object(fetcher.requests, "get", return_value=page):
            papers = fetcher.fetch_rxiv("biorxiv", [["glioma"]], 7, 10)
        self.assertEqual([p["title"] for p in papers], ["glioma v1"])


class MedrxivTest(unittest.TestCase):
    def setUp(self):
        fetcher._RXIV_PAGE_CACHE.clear()

    def test_medrxiv_uses_its_own_server_and_labels(self):
        page = _page([_item("10.1101/m", "glioma trial")], 1)
        with mock.patch.object(fetcher.requests, "get", return_value=page) as get:
            papers = fetcher.fetch_rxiv("medrxiv", [["glioma"]], 7, 10)
        self.assertIn("/details/medrxiv/", get.call_args.args[0])
        self.assertEqual(papers[0]["source"], "medRxiv")
        self.assertEqual(papers[0]["journal"], "medRxiv preprint")
        self.assertEqual(papers[0]["author_list"], ["A", "B"])


class FetchAllTest(unittest.TestCase):
    def test_runs_every_variant_and_merges_duplicates(self):
        def pubmed(q, *args):
            return [{"source": "PubMed", "title": q, "doi": "10.1/SAME" if q == "a" else "10.1/same"}]

        queries = {"display": "T", "pubmed": ["a", "b"], "arxiv": [], "biorxiv": []}
        with mock.patch.object(fetcher, "fetch_pubmed", side_effect=pubmed) as fp:
            papers, warnings = fetcher.fetch_all(queries, 7, 25, 60)

        self.assertEqual(fp.call_count, 2)
        self.assertEqual(fp.call_args.args, ("b", 7, 25, 60))
        self.assertEqual(len(papers), 1)
        self.assertEqual(warnings, [])


if __name__ == "__main__":
    unittest.main()
