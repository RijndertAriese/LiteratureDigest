"""
Journal-quality lookup via the OpenAlex API.

There is no free, licensed source for the Clarivate Journal Impact Factor, so we
use OpenAlex's ``2yr_mean_citedness`` — the same citations-per-recent-paper ratio
the JIF is built on, recomputed from open citation data. It tracks the real JIF
closely enough to gate out low-tier / predatory journals.

The lookup is best-effort: any network or data problem leaves a paper's
``impact_factor`` as ``None`` (callers treat unknown journals as "keep").
"""

import os

import requests

_OPENALEX = "https://api.openalex.org"
_TIMEOUT = 15
_CHUNK = 50  # OpenAlex allows up to 50 OR-values per filter

# Per-process caches so a journal is only looked up once per run.
_source_metric: dict[str, float | None] = {}   # source id -> 2yr mean citedness
_name_to_source: dict[str, str | None] = {}     # lowercased journal name -> source id


def _mailto() -> str:
    return (
        os.environ.get("OPENALEX_EMAIL")
        or os.environ.get("NCBI_EMAIL")
        or os.environ.get("SENDER_EMAIL")
        or os.environ.get("SMTP_USER")
        or "literature-bot@example.com"
    )


def _params(extra: dict) -> dict:
    return {"mailto": _mailto(), **extra}


def _normalise_doi(doi: str) -> str:
    doi = (doi or "").strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if doi.startswith(prefix):
            doi = doi[len(prefix):]
    return doi


def _short_id(openalex_id: str) -> str:
    """'https://openalex.org/S123' -> 'S123'."""
    return openalex_id.rstrip("/").rsplit("/", 1)[-1]


def _chunks(seq: list, size: int):
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


def annotate_impact(papers: list[dict]) -> None:
    """
    Add ``paper["impact_factor"]`` (float or None) to each paper in place.

    ``None`` means the journal could not be resolved or has no metric — callers
    decide whether that passes a threshold.
    """
    if not papers:
        return

    doi_to_source: dict[str, str] = {}
    unresolved: list[dict] = []

    dois = [_normalise_doi(p.get("doi", "")) for p in papers]
    dois = [d for d in dois if d]
    for chunk in _chunks(sorted(set(dois)), _CHUNK):
        doi_to_source.update(_sources_for_dois(chunk))

    # Map every paper to a source id (via DOI, then journal-name search).
    paper_source: dict[int, str | None] = {}
    for idx, paper in enumerate(papers):
        doi = _normalise_doi(paper.get("doi", ""))
        source_id = doi_to_source.get(doi) if doi else None
        if source_id is None:
            journal = (paper.get("journal") or "").strip()
            source_id = _source_for_name(journal) if journal else None
        paper_source[idx] = source_id

    # Batch-fetch metrics for all source ids we still don't have cached.
    missing = sorted({
        sid for sid in paper_source.values()
        if sid is not None and sid not in _source_metric
    })
    for chunk in _chunks(missing, _CHUNK):
        _load_source_metrics(chunk)

    for idx, paper in enumerate(papers):
        sid = paper_source[idx]
        paper["impact_factor"] = _source_metric.get(sid) if sid else None


def _sources_for_dois(dois: list[str]) -> dict[str, str]:
    """Return {normalised_doi: short_source_id} for a batch of DOIs."""
    try:
        resp = requests.get(
            f"{_OPENALEX}/works",
            params=_params({
                "filter": "doi:" + "|".join(dois),
                "select": "doi,primary_location",
                "per-page": _CHUNK,
            }),
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        out: dict[str, str] = {}
        for work in resp.json().get("results", []):
            source = (work.get("primary_location") or {}).get("source") or {}
            sid = source.get("id")
            doi = _normalise_doi(work.get("doi", ""))
            if sid and doi:
                out[doi] = _short_id(sid)
        return out
    except Exception as e:
        print(f"[impact] DOI batch lookup failed ({e})")
        return {}


def _source_for_name(journal: str) -> str | None:
    key = journal.lower()
    if key in _name_to_source:
        return _name_to_source[key]
    try:
        resp = requests.get(
            f"{_OPENALEX}/sources",
            params=_params({
                "search": journal,
                "select": "id,display_name,summary_stats",
                "per-page": 1,
            }),
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])
        if not results:
            _name_to_source[key] = None
            return None
        sid = _short_id(results[0]["id"])
        _name_to_source[key] = sid
        # We already have the stats in hand — cache them too.
        stats = results[0].get("summary_stats") or {}
        _source_metric[sid] = stats.get("2yr_mean_citedness")
        return sid
    except Exception as e:
        print(f"[impact] journal name lookup failed for {journal!r} ({e})")
        _name_to_source[key] = None
        return None


def _load_source_metrics(source_ids: list[str]) -> None:
    try:
        resp = requests.get(
            f"{_OPENALEX}/sources",
            params=_params({
                "filter": "ids.openalex:" + "|".join(source_ids),
                "select": "id,summary_stats",
                "per-page": _CHUNK,
            }),
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        for source in resp.json().get("results", []):
            sid = _short_id(source["id"])
            stats = source.get("summary_stats") or {}
            _source_metric[sid] = stats.get("2yr_mean_citedness")
    except Exception as e:
        print(f"[impact] source metric batch failed ({e})")

    # Mark anything still unresolved so we don't retry it this run.
    for sid in source_ids:
        _source_metric.setdefault(sid, None)
