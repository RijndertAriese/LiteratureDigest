import datetime
import unittest

from bot.fetcher import _pubmed_exact_publication_date


class PubMedHistoryDate(dict):
    def __init__(self, status: str, year: str, month: str, day: str):
        super().__init__({"Year": year, "Month": month, "Day": day})
        self.attributes = {"PubStatus": status}


def pubmed_article(
    *,
    article_dates: list[dict] | None = None,
    history_dates: list[PubMedHistoryDate] | None = None,
    journal_pub_date: dict | None = None,
) -> dict:
    return {
        "MedlineCitation": {
            "Article": {
                "ArticleDate": article_dates or [],
                "Journal": {
                    "JournalIssue": {
                        "PubDate": journal_pub_date or {},
                    },
                },
            },
        },
        "PubmedData": {
            "History": history_dates or [],
        },
    }


class PubMedExactPublicationDateTest(unittest.TestCase):
    def test_prefers_electronic_article_date_over_future_issue_date(self):
        article = pubmed_article(
            article_dates=[
                {"Year": "2026", "Month": "01", "Day": "30", "DateType": "Electronic"},
            ],
            journal_pub_date={"Year": "2026", "Month": "Dec", "Day": "31"},
        )

        self.assertEqual(
            _pubmed_exact_publication_date(article),
            datetime.date(2026, 1, 30),
        )

    def test_uses_epublish_history_when_article_date_is_absent(self):
        article = pubmed_article(
            history_dates=[
                PubMedHistoryDate("entrez", "2026", "6", "3"),
                PubMedHistoryDate("epublish", "2026", "6", "2"),
            ],
        )

        self.assertEqual(
            _pubmed_exact_publication_date(article),
            datetime.date(2026, 6, 2),
        )

    def test_ignores_indexing_dates_for_publication_filtering(self):
        article = pubmed_article(
            history_dates=[
                PubMedHistoryDate("pubmed", "2026", "6", "3"),
                PubMedHistoryDate("entrez", "2026", "6", "3"),
            ],
            journal_pub_date={"Year": "2026", "Month": "Jun"},
        )

        self.assertIsNone(_pubmed_exact_publication_date(article))


if __name__ == "__main__":
    unittest.main()
