import os
import time
import datetime
import requests
import arxiv
from Bio import Entrez

Entrez.email = (
    os.environ.get("NCBI_EMAIL")
    or os.environ.get("SENDGRID_SENDER_EMAIL")
    or "literature-bot@example.com"
)
NCBI_API_KEY = os.environ.get("NCBI_API_KEY")
if NCBI_API_KEY:
    Entrez.api_key = NCBI_API_KEY

_ARXIV_TIMEOUT_SECONDS = 20


class _TimeoutSession(requests.Session):
    def request(self, method: str, url: str, **kwargs):
        kwargs.setdefault("timeout", _ARXIV_TIMEOUT_SECONDS)
        return super().request(method, url, **kwargs)


def _make_arxiv_client() -> arxiv.Client:
    client = arxiv.Client(page_size=25, delay_seconds=10.0, num_retries=6)
    client._session = _TimeoutSession()
    return client


_ARXIV_CLIENT = _make_arxiv_client()


def _date_n_days_ago(n: int) -> datetime.date:
    return datetime.date.today() - datetime.timedelta(days=n)


# ── PubMed ────────────────────────────────────────────────────────────────────

def fetch_pubmed(keyword: str, days: int, max_results: int) -> list[dict]:
    since_date = _date_n_days_ago(days)
    today_date = datetime.date.today()
    since = since_date.strftime("%Y/%m/%d")
    today = today_date.strftime("%Y/%m/%d")

    # PubMed's Entrez date is only a candidate window. Some old papers are
    # indexed or modified recently, so each fetched record is post-filtered by
    # its exact electronic/publication date below.
    candidate_limit = max(max_results * 20, 100)
    handle = Entrez.esearch(
        db="pubmed",
        term=f"({keyword})",
        retmax=candidate_limit,
        sort="pub_date",
        datetype="edat",
        mindate=since,
        maxdate=today,
    )
    record = Entrez.read(handle)
    handle.close()

    ids = record["IdList"]
    if not ids:
        return []

    handle = Entrez.efetch(db="pubmed", id=ids, rettype="xml", retmode="xml")
    records = Entrez.read(handle)
    handle.close()

    papers = []
    for article in records["PubmedArticle"]:
        try:
            medline = article["MedlineCitation"]
            art = medline["Article"]

            title = str(art.get("ArticleTitle", ""))
            abstract_texts = art.get("Abstract", {}).get("AbstractText", [])
            abstract = " ".join(str(t) for t in abstract_texts) if abstract_texts else ""

            authors_list = art.get("AuthorList", [])
            authors = _format_authors([
                f"{a.get('LastName', '')} {a.get('Initials', '')}".strip()
                for a in authors_list if "LastName" in a
            ])

            journal = art.get("Journal", {}).get("Title", "")
            published_on = _pubmed_exact_publication_date(article)
            if published_on is None or not since_date <= published_on <= today_date:
                continue

            pub_date = _format_date(published_on)
            doi = _pubmed_doi(article)

            papers.append({
                "source": "PubMed",
                "title": title,
                "authors": authors,
                "journal": journal,
                "date": pub_date,
                "abstract": abstract,
                "doi": doi,
                "url": f"https://pubmed.ncbi.nlm.nih.gov/{medline['PMID']}/",
            })
            if len(papers) >= max_results:
                break
        except Exception:
            continue

    return papers


def _pubmed_exact_publication_date(article: dict) -> datetime.date | None:
    """
    Return an exact publication date suitable for recency filtering.

    PubMed's Entrez date tracks indexing, not publication. For a "last N days"
    digest, prefer the electronic article date, then explicit epublish/ahead of
    print history entries, and only then an exact journal issue date.
    """
    art = article["MedlineCitation"]["Article"]

    for d in art.get("ArticleDate", []):
        parsed = _parse_pubmed_date(
            str(d.get("Year", "")),
            str(d.get("Month", "")),
            str(d.get("Day", "")),
        )
        if parsed:
            return parsed

    try:
        for hist in article["PubmedData"]["History"]:
            status = str(hist.attributes.get("PubStatus", ""))
            if status not in {"epublish", "aheadofprint"}:
                continue
            parsed = _parse_pubmed_date(
                str(hist.get("Year", "")),
                str(hist.get("Month", "")),
                str(hist.get("Day", "")),
            )
            if parsed:
                return parsed
    except Exception:
        pass

    try:
        pub = art["Journal"]["JournalIssue"]["PubDate"]
        return _parse_pubmed_date(
            str(pub.get("Year", "")),
            str(pub.get("Month", "")),
            str(pub.get("Day", "")),
        )
    except Exception:
        return None


def _parse_pubmed_date(year: str, month: str, day: str) -> datetime.date | None:
    """Parse a PubMed date tuple. Returns None if any field is missing or invalid.

    Day is required — callers that want to accept month-only dates should
    handle the None return themselves. This is intentional: journal issue
    dates often have no Day, and without a Day we cannot verify recency.
    """
    if not year or not month or not day:
        return None

    try:
        year_num = int(year)
        day_num = int(day)
    except ValueError:
        return None

    try:
        month_num = int(month)
    except ValueError:
        try:
            month_num = datetime.datetime.strptime(month[:3], "%b").month
        except ValueError:
            return None

    try:
        return datetime.date(year_num, month_num, day_num)
    except ValueError:
        return None


def _format_date(date: datetime.date) -> str:
    return date.strftime("%Y %b %d")


def _pubmed_doi(article: dict) -> str:
    try:
        for id_obj in article["PubmedData"]["ArticleIdList"]:
            if str(id_obj.attributes.get("IdType", "")) == "doi":
                return str(id_obj)
    except Exception:
        pass
    return ""


# ── arXiv ─────────────────────────────────────────────────────────────────────

def fetch_arxiv(keyword: str, days: int, max_results: int) -> list[dict]:
    since = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)

    query = _ensure_arxiv_category(keyword)

    search = arxiv.Search(
        query=query,
        max_results=max_results,
        sort_by=arxiv.SortCriterion.SubmittedDate,
        sort_order=arxiv.SortOrder.Descending,
    )

    papers = []
    for result in _ARXIV_CLIENT.results(search):
        if result.published < since:
            break
        papers.append({
            "source": "arXiv",
            "title": result.title,
            "authors": _format_authors([str(a) for a in result.authors]),
            "journal": result.journal_ref or "arXiv preprint",
            "date": result.published.strftime("%Y %b"),
            "abstract": result.summary.replace("\n", " "),
            "doi": result.doi or "",
            "url": result.entry_id,
        })

    return papers


# ── bioRxiv ───────────────────────────────────────────────────────────────────

def fetch_biorxiv(keyword: str, days: int, max_results: int) -> list[dict]:
    since = _date_n_days_ago(days).strftime("%Y-%m-%d")
    today = datetime.date.today().strftime("%Y-%m-%d")

    papers = []
    cursor = 0

    while len(papers) < max_results:
        resp = requests.get(
            f"https://api.biorxiv.org/details/biorxiv/{since}/{today}/{cursor}/json",
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
        collection = data.get("collection", [])
        if not collection:
            break

        kw_lower = keyword.lower()
        for item in collection:
            text = f"{item.get('title', '')} {item.get('abstract', '')}".lower()
            if kw_lower in text:
                doi = item.get("doi", "")
                papers.append({
                    "source": "bioRxiv",
                    "title": item.get("title", ""),
                    "authors": _format_authors(item.get("authors", "").split("; ")),
                    "journal": "bioRxiv preprint",
                    "date": item.get("date", ""),
                    "abstract": item.get("abstract", ""),
                    "doi": doi,
                    "url": f"https://doi.org/{doi}" if doi else "",
                })
            if len(papers) >= max_results:
                break

        total = int(data.get("messages", [{}])[0].get("total", 0))
        cursor += 100
        if cursor >= total:
            break
        time.sleep(0.5)

    return papers


# ── helpers ───────────────────────────────────────────────────────────────────

def _format_authors(names: list[str]) -> str:
    names = [n.strip() for n in names if n.strip()]
    if not names:
        return ""
    if len(names) <= 3:
        return ", ".join(names)
    return f"{names[0]}, {names[1]}, {names[2]} et al."


def _ensure_arxiv_category(query: str) -> str:
    """Keep arXiv searches scoped if the translator omits a category filter."""
    if "cat:" in query:
        return query
    return f"(cat:q-bio OR cat:eess.SP) AND ({query})"


def _fetch_warning(source_name: str, display: str, error: Exception) -> str:
    detail = str(error)
    if source_name == "fetch_arxiv":
        if "HTTP 429" in detail:
            detail = (
                "arXiv rate limited the request (HTTP 429); "
                "try again later or reduce max_results_per_source"
            )
        elif isinstance(error, requests.exceptions.Timeout):
            detail = "arXiv request timed out; try again later"
    return f"{source_name} failed for '{display}': {detail}"


def fetch_all(queries: dict, days: int, max_results: int) -> tuple[list[dict], list[str]]:
    """
    queries: dict with keys "pubmed", "arxiv", "biorxiv" — one optimised
             search string per source, as produced by query_translator.

    Returns (papers, warnings) so callers can surface fetch failures in the digest.
    """
    source_fns = [
        (fetch_pubmed,  queries.get("pubmed",  queries.get("display", ""))),
        (fetch_arxiv,   queries.get("arxiv",   queries.get("display", ""))),
        (fetch_biorxiv, queries.get("biorxiv", queries.get("display", ""))),
    ]

    results = []
    warnings = []
    for fn, query in source_fns:
        if not query:
            continue
        try:
            batch = fn(query, days, max_results)
            results.extend(batch)
        except Exception as e:
            msg = _fetch_warning(fn.__name__, queries.get("display", query), e)
            print(f"[warn] {msg}")
            warnings.append(msg)

    seen: set[str] = set()
    deduped = []
    for paper in results:
        doi = paper.get("doi", "")
        key = doi if doi else paper["title"].lower()[:80]
        if key not in seen:
            seen.add(key)
            deduped.append(paper)

    return deduped, warnings
