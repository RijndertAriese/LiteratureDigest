import os
import time
import datetime
import requests
import arxiv
from Bio import Entrez

Entrez.email = "literature-bot@example.com"
NCBI_API_KEY = os.environ.get("NCBI_API_KEY")
if NCBI_API_KEY:
    Entrez.api_key = NCBI_API_KEY


def _date_n_days_ago(n: int) -> datetime.date:
    return datetime.date.today() - datetime.timedelta(days=n)


# ── PubMed ────────────────────────────────────────────────────────────────────

def fetch_pubmed(keyword: str, days: int, max_results: int) -> list[dict]:
    since = _date_n_days_ago(days).strftime("%Y/%m/%d")
    query = f'({keyword}) AND ("{since}"[Date - Publication] : "3000"[Date - Publication])'

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
            pub_date = _pubmed_date(art)
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


def _pubmed_date(art: dict) -> str:
    try:
        pub = art["Journal"]["JournalIssue"]["PubDate"]
        return f"{pub.get('Year', '')} {pub.get('Month', '')}".strip()
    except Exception:
        return ""


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

    # Restrict to biomedical / quantitative biology categories to avoid
    # irrelevant CS / engineering papers that mention "brain" incidentally
    biomedical_query = f"(cat:q-bio OR cat:eess.SP) AND ({keyword})"

    client = arxiv.Client()
    search = arxiv.Search(
        query=biomedical_query,
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

    url = f"https://api.biorxiv.org/details/biorxiv/{since}/{today}/0/json"
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


def fetch_all(queries: dict, days: int, max_results: int) -> list[dict]:
    """
    queries: dict with keys "pubmed", "arxiv", "biorxiv" — one optimised
             search string per source, as produced by query_translator.
    """
    source_fns = [
        (fetch_pubmed,  queries.get("pubmed",  queries.get("display", ""))),
        (fetch_arxiv,   queries.get("arxiv",   queries.get("display", ""))),
        (fetch_biorxiv, queries.get("biorxiv", queries.get("display", ""))),
    ]

    results = []
    for fn, query in source_fns:
        if not query:
            continue
        try:
            batch = fn(query, days, max_results)
            results.extend(batch)
        except Exception as e:
            print(f"[warn] {fn.__name__} failed for {query!r}: {e}")

    seen: set[str] = set()
    deduped = []
    for paper in results:
        doi = paper.get("doi", "")
        key = doi if doi else paper["title"].lower()[:80]
        if key not in seen:
            seen.add(key)
            deduped.append(paper)

    return deduped
