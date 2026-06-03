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


def _date_n_days_ago(n: int) -> datetime.date:
    return datetime.date.today() - datetime.timedelta(days=n)


# ── PubMed ────────────────────────────────────────────────────────────────────

def fetch_pubmed(keyword: str, days: int, max_results: int) -> list[dict]:
    since = _date_n_days_ago(days).strftime("%Y/%m/%d")
    today = datetime.date.today().strftime("%Y/%m/%d")

    # Use [Date - Entrez] (when PubMed indexed the paper) instead of
    # [Date - Publication] (journal issue date). This correctly excludes
    # papers with future issue dates (e.g. "2026 Dec" for a Jan epub)
    # while including genuinely new epub-ahead-of-print papers.
    query = f'({keyword}) AND ("{since}"[Date - Entrez] : "{today}"[Date - Entrez])'

    handle = Entrez.esearch(db="pubmed", term=query, retmax=max_results, sort="pub_date")
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
            pub_date = _pubmed_date(art, article)
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
        except Exception:
            continue

    return papers


def _pubmed_date(art: dict, article: dict) -> str:
    """
    Return the actual online publication date, not the future journal issue date.

    Priority:
      1. ArticleDate with DateType="Electronic"  — epub date (most accurate)
      2. PubmedData History entry with status "pubmed" — date added to PubMed
      3. Journal issue PubDate                   — last resort (may be future)
    """
    today = datetime.date.today()

    # 1. Electronic publication date
    for d in art.get("ArticleDate", []):
        try:
            year, month = int(str(d["Year"])), int(str(d["Month"]))
            if datetime.date(year, month, 1) <= today:
                month_name = datetime.date(year, month, 1).strftime("%b")
                return f"{year} {month_name}"
        except Exception:
            continue

    # 2. PubMed entry date from history
    try:
        for hist in article["PubmedData"]["History"]:
            if str(hist.attributes.get("PubStatus", "")) in ("pubmed", "entrez"):
                year, month = int(str(hist["Year"])), int(str(hist["Month"]))
                if datetime.date(year, month, 1) <= today:
                    month_name = datetime.date(year, month, 1).strftime("%b")
                    return f"{year} {month_name}"
    except Exception:
        pass

    # 3. Journal issue date — only if not in the future
    try:
        pub = art["Journal"]["JournalIssue"]["PubDate"]
        year_str = str(pub.get("Year", ""))
        month_str = str(pub.get("Month", "1"))
        if year_str:
            year = int(year_str)
            # month may be a name ("Jan") or number
            try:
                month = int(month_str)
            except ValueError:
                month = datetime.datetime.strptime(month_str[:3], "%b").month
            if datetime.date(year, month, 1) <= today:
                return f"{year} {pub.get('Month', '')}".strip()
    except Exception:
        pass

    return "epub ahead of print"


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

    client = arxiv.Client()
    search = arxiv.Search(
        query=query,
        max_results=max_results,
        sort_by=arxiv.SortCriterion.SubmittedDate,
        sort_order=arxiv.SortOrder.Descending,
    )

    papers = []
    for result in client.results(search):
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
            msg = f"{fn.__name__} failed for '{queries.get('display', query)}': {e}"
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
