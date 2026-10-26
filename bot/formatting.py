"""Display helpers shared by the PDF and email renderers."""

import datetime

PREPRINT_SOURCES = {"arXiv", "bioRxiv"}


def display_date(value: str | datetime.date) -> str:
    """'2026-10-15' -> '15 Oct 2026'. Unparseable strings are returned as-is."""
    if not isinstance(value, datetime.date):
        try:
            value = datetime.date.fromisoformat(value)
        except (TypeError, ValueError):
            return value or ""
    return f"{value.day} {value:%b %Y}"


def date_window(stats: dict) -> str:
    """'12 – 19 Oct 2026 · last 7 days'."""
    start, end = stats["start"], stats["end"]
    if start.year != end.year:
        span = f"{display_date(start)} – {display_date(end)}"
    elif start.month != end.month:
        span = f"{start.day} {start:%b} – {display_date(end)}"
    else:
        span = f"{start.day} – {display_date(end)}"
    return f"{span} · last {stats['days']} day{'s' if stats['days'] != 1 else ''}"


def impact_label(paper: dict) -> str:
    """'IF 12.3', 'IF n/a', 'always included' or '' for preprints.

    Always-included journals hide their OpenAlex score: they are on the list
    precisely because that score understates them.
    """
    if paper.get("source") in PREPRINT_SOURCES:
        return ""
    if paper.get("impact_whitelisted"):
        return "always included"
    impact = paper.get("impact_factor")
    return f"IF {impact:.1f}" if isinstance(impact, (int, float)) else "IF n/a"


def paper_link(paper: dict) -> str:
    doi = paper.get("doi", "")
    return f"https://doi.org/{doi}" if doi else paper.get("url", "")


def plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"
