import unittest
from unittest import mock

from bot import fetcher


class FetcherArxivTest(unittest.TestCase):
    def test_shared_arxiv_client_is_throttled(self):
        self.assertEqual(fetcher._ARXIV_CLIENT.page_size, 25)
        self.assertGreaterEqual(fetcher._ARXIV_CLIENT.delay_seconds, 10.0)
        self.assertGreaterEqual(fetcher._ARXIV_CLIENT.num_retries, 6)
        self.assertIsInstance(fetcher._ARXIV_CLIENT._session, fetcher._TimeoutSession)

    def test_rate_limit_warning_omits_api_url(self):
        warning = fetcher._fetch_warning(
            "fetch_arxiv",
            "Pediatric Brain Tumor Microenvironment",
            Exception(
                "Page request resulted in HTTP 429 "
                "(https://export.arxiv.org/api/query?search_query=cat%3Aq-bio)"
            ),
        )

        self.assertIn("HTTP 429", warning)
        self.assertIn("rate limited", warning)
        self.assertNotIn("export.arxiv.org", warning)

    def test_arxiv_timeout_session_sets_default_timeout(self):
        session = fetcher._TimeoutSession()
        observed = {}

        def fake_request(self, method, url, **kwargs):
            observed.update(kwargs)

        with mock.patch.object(fetcher.requests.Session, "request", fake_request):
            session.get("https://example.org")

        self.assertEqual(observed["timeout"], fetcher._ARXIV_TIMEOUT_SECONDS)


if __name__ == "__main__":
    unittest.main()
