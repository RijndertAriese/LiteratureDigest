import os
import time
import datetime
import requests
import arxiv
from Bio import Entrez

Entrez.email = (
    os.environ.get("NCBI_EMAIL")
    or os.environ.get("SENDER_EMAIL")
    or os.environ.get("SMTP_USER")
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

def fetch_pubmed(
    keyword: str, days: int, max_results: int, max_age_days: int | None = None
) -> list[dict]:
    """
    Papers that entered PubMed in the last ``days`` days (Entrez date) and were
    published at most ``max_age_days`` ago (defaults to ``days``).
    """
    today_date = datetime.date.today()
    since = _date_n_days_ago(days).strftime("%Y/%m/%d")
    today = today_date.strftime("%Y/%m/%d")
    oldest_date = _date_n_days_ago(max(max_age_days or days, days))

    # The Entrez date marks when a record entered PubMed, so each paper falls in
    # exactly one weekly window. Journals often deposit papers weeks after they
    # go online; those are kept up to ``max_age_days`` old. Old back-catalogue
    # records that are merely (re)indexed now are dropped by the exact
    # electronic/publication date below.
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
            abstract = _pubmed_abstract(art.get("Abstract", {}).get("AbstractText", []))

            authors_list = art.get("AuthorList", [])
            authors = _format_authors([
                f"{a.get('LastName', '')} {a.get('Initials', '')}".strip()
                for a in authors_list if "LastName" in a
            ])

            journal = art.get("Journal", {}).get("Title", "")
            published_on = _pubmed_exact_publication_date(article)
            if published_on is None or not oldest_date <= published_on <= today_date:
                continue

            doi = _pubmed_doi(article)

            papers.append({
                "source": "PubMed",
                "title": title,
                "authors": authors,
                "journal": journal,
                "date": published_on.isoformat(),
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


def _pubmed_abstract(sections: list) -> str:
    """Join abstract sections, keeping structured labels (BACKGROUND:, METHODS: ...)."""
    parts = []
    for section in sections:
        text = str(section).strip()
        label = getattr(section, "attributes", {}).get("Label", "")
        if label and text:
            parts.append(f"{str(label).upper()}: {text}")
        elif text:
            parts.append(text)
    return " ".join(parts)


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
            "date": result.published.date().isoformat(),
            "abstract": result.summary.replace("\n", " "),
            "doi": result.doi or "",
            "url": result.entry_id,
        })

    return papers


# ── bioRxiv ───────────────────────────────────────────────────────────────────

_BIORXIV_PAGE_CACHE: dict[tuple[str, str], list[dict]] = {}


def _biorxiv_window(since: str, today: str) -> list[dict]:
    """All bioRxiv preprints posted in [since, today], fetched once per run."""
    key = (since, today)
    if key in _BIORXIV_PAGE_CACHE:
        return _BIORXIV_PAGE_CACHE[key]

    items: list[dict] = []
    cursor = 0
    while True:
        resp = requests.get(
            f"https://api.biorxiv.org/details/biorxiv/{since}/{today}/{cursor}/json",
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        collection = data.get("collection", [])
        if not collection:
            break
        items.extend(collection)
        # The page size is set by the API (currently 30), so advance by what came back.
        cursor += len(collection)
        total = int(data.get("messages", [{}])[0].get("total", 0))
        if cursor >= total:
            break
        time.sleep(0.3)

    _BIORXIV_PAGE_CACHE[key] = items
    return items


def _biorxiv_matches(text: str, groups: list[list[str]]) -> bool:
    """True if every term of at least one keyword group occurs in ``text``."""
    text = text.lower()
    return any(group and all(term.lower() in text for term in group) for group in groups)


def fetch_biorxiv(groups: list[list[str]], days: int, max_results: int) -> list[dict]:
    """bioRxiv preprints from the last ``days`` days matching any keyword group."""
    since = _date_n_days_ago(days).strftime("%Y-%m-%d")
    today = datetime.date.today().strftime("%Y-%m-%d")

    papers = []
    seen: set[str] = set()
    for item in _biorxiv_window(since, today):
        doi = item.get("doi", "")
        # Revised preprints appear once per version; keep the first.
        if doi in seen:
            continue
        text = f"{item.get('title', '')} {item.get('abstract', '')}"
        if not _biorxiv_matches(text, groups):
            continue
        seen.add(doi)
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


def fetch_all(
    queries: dict, days: int, max_results: int, max_age_days: int | None = None
) -> tuple[list[dict], list[str]]:
    """
    queries: dict from query_translator — "pubmed" and "arxiv" are lists of
             query strings, "biorxiv" a list of keyword groups. Results of all
             variants are merged and de-duplicated.

    Returns (papers, warnings) so callers can surface fetch failures in the digest.
    """
    display = queries.get("display", "")
    jobs = [
        ("fetch_pubmed", lambda q: fetch_pubmed(q, days, max_results, max_age_days), q)
        for q in queries.get("pubmed", [])
    ] + [
        ("fetch_arxiv", lambda q: fetch_arxiv(q, days, max_results), q)
        for q in queries.get("arxiv", [])
    ]
    if queries.get("biorxiv"):
        groups = queries["biorxiv"]
        jobs.append(("fetch_biorxiv", lambda q: fetch_biorxiv(q, days, max_results), groups))

    results = []
    warnings = []
    for name, fn, query in jobs:
        try:
            results.extend(fn(query))
        except Exception as e:
            msg = _fetch_warning(name, display, e)
            print(f"[warn] {msg}")
            if msg not in warnings:
                warnings.append(msg)

    seen: set[str] = set()
    deduped = []
    for paper in results:
        doi = (paper.get("doi") or "").lower()
        key = doi if doi else paper["title"].lower()[:80]
        if key not in seen:
            seen.add(key)
            deduped.append(paper)

    return deduped, warnings
