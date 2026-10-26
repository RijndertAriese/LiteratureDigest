import datetime
import os
import sys
import tempfile

import yaml

from bot.fetcher import fetch_all
from bot.formatting import PREPRINT_SOURCES
from bot.impact import annotate_impact
from bot.pdf_builder import build_pdf
from bot.mailer import send_digest
from bot.query_translator import translate_topic
from bot.screen import screen_papers


def load_config(path: str = "config.yaml") -> dict:
    with open(path) as f:
        cfg = yaml.safe_load(f) or {}

    if not isinstance(cfg, dict):
        return {"_config_error": "config.yaml must contain key/value settings"}

    if os.environ.get("RECIPIENT_EMAIL"):
        cfg["recipient_email"] = os.environ["RECIPIENT_EMAIL"]

    return cfg


def validate_config(cfg: dict) -> None:
    """Fail fast with a clear message if required config/secrets are missing."""
    errors = []

    if cfg.get("_config_error"):
        errors.append(cfg["_config_error"])

    topics = cfg.get("topics")
    if not isinstance(topics, list) or not topics:
        errors.append("config.yaml: 'topics' is missing or empty")
    else:
        for t in topics:
            if isinstance(t, str) and t.strip():
                continue
            if (
                isinstance(t, dict)
                and isinstance(t.get("topic"), str) and t["topic"].strip()
                and isinstance(t.get("hints", []), list)
                and all(isinstance(h, str) for h in t.get("hints", []))
            ):
                continue
            errors.append(
                f"config.yaml: topic {t!r} must be a string or "
                "{topic: <text>, hints: [<terms>]}"
            )

    recipient = cfg.get("recipient_email")
    placeholder_emails = {"your@email.com", "you@example.com"}
    if (
        not isinstance(recipient, str)
        or not recipient.strip()
        or recipient in placeholder_emails
        or recipient.endswith("@example.com")
    ):
        errors.append("RECIPIENT_EMAIL secret (or config.yaml recipient_email) is not set")

    defaults = {"interval_days": 7, "max_results_per_source": 25, "max_age_days": 60}
    for key, default in defaults.items():
        value = cfg.get(key, default)
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            errors.append(f"config.yaml: '{key}' must be a positive integer")

    if not isinstance(cfg.get("relevance_screen", True), bool):
        errors.append("config.yaml: 'relevance_screen' must be true or false")

    min_if = cfg.get("min_impact_factor", 0)
    if isinstance(min_if, bool) or not isinstance(min_if, (int, float)) or min_if < 0:
        errors.append("config.yaml: 'min_impact_factor' must be a non-negative number")

    allow = cfg.get("always_include_journals", [])
    if not isinstance(allow, list) or not all(isinstance(s, str) for s in allow):
        errors.append("config.yaml: 'always_include_journals' must be a list of strings")

    if not os.environ.get("SMTP_HOST"):
        errors.append("SMTP_HOST secret is not set")
    if not (
        os.environ.get("SENDER_EMAIL")
        or os.environ.get("SMTP_SENDER_EMAIL")
        or os.environ.get("SMTP_USER")
    ):
        errors.append("SENDER_EMAIL (or SMTP_USER) secret is not set")

    if errors:
        print("[error] Configuration problems found:")
        for e in errors:
            print(f"  • {e}")
        sys.exit(1)


def parse_topics(entries: list) -> list[tuple[str, list[str]]]:
    """Config topics are strings or {topic, hints} dicts → [(topic, hints)]."""
    parsed = []
    for entry in entries:
        if isinstance(entry, dict):
            parsed.append((entry["topic"].strip(), [h.strip() for h in entry.get("hints", [])]))
        else:
            parsed.append((entry.strip(), []))
    return parsed


def filter_by_impact(
    peer: list[dict], min_if: float, always_include: list[str]
) -> tuple[list[dict], int]:
    """
    Keep peer-reviewed papers whose journal clears ``min_if``.

    A paper is kept when its journal name matches an ``always_include`` substring
    (case-insensitive), when its metric is unknown (fail-open), or when the
    metric is at least ``min_if``. Sets ``impact_whitelisted`` on each paper.
    Returns ``(kept_papers, dropped_count)``.
    """
    kept = []
    for p in peer:
        journal = (p.get("journal") or "").lower()
        whitelisted = any(s in journal for s in always_include)
        p["impact_whitelisted"] = whitelisted
        metric = p.get("impact_factor")
        if whitelisted or metric is None or metric >= min_if:
            kept.append(p)
    return kept, len(peer) - len(kept)


def rank_papers(papers: list[dict]) -> list[dict]:
    """
    Order peer-reviewed papers for display: always-included journals first,
    then known impact factor (high to low), then unknown; newest first on ties.
    """
    def tier(p: dict) -> tuple:
        if p.get("impact_whitelisted"):
            return (0, 0.0)
        impact = p.get("impact_factor")
        if impact is None:
            return (2, 0.0)
        return (1, -impact)

    by_date = sorted(papers, key=lambda p: p.get("date", ""), reverse=True)
    return sorted(by_date, key=tier)


def mark_cross_topic_duplicates(*groups: dict[str, list[dict]]) -> None:
    """
    Flag papers that already appeared under an earlier topic.

    Topics are visited in order across all groups (peer-reviewed, then
    preprints). A repeat gets ``duplicate_of`` set to the first topic it
    appeared under; the first copy collects the other topics in ``also_in``.
    """
    first_seen: dict[str, tuple[str, dict]] = {}
    for group in groups:
        for topic, papers in group.items():
            for p in papers:
                key = (p.get("doi") or p.get("title", "").lower()[:80]).lower()
                if key not in first_seen:
                    first_seen[key] = (topic, p)
                    p.setdefault("also_in", [])
                    continue
                first_topic, original = first_seen[key]
                p["duplicate_of"] = first_topic
                if topic not in original["also_in"]:
                    original["also_in"].append(topic)


def _unique(papers: list[dict]) -> list[dict]:
    return [p for p in papers if not p.get("duplicate_of")]


def _print_summary(stats: dict) -> None:
    rows = [
        (t["name"], t["peer"], t["preprints"], t["dropped"], t.get("off_topic", 0))
        for t in stats["topics"]
    ]
    totals = ("Total", *(sum(r[i] for r in rows) for i in (1, 2, 3, 4)))
    width = min(max(len(r[0]) for r in rows + [totals]), 60)

    def line(cells) -> str:
        name = cells[0] if len(cells[0]) <= width else cells[0][:width - 1] + "…"
        return f"      {name:<{width}}" + "".join(f"  {c:>9}" for c in cells[1:])

    header = line(("Topic", "peer", "preprint", "below IF", "off-topic"))
    rule = "      " + "-" * (len(header) - 6)
    print("\n[run] summary")
    print(header)
    print(rule)
    for row in rows:
        print(line(row))
    print(rule)
    print(line(totals))
    if stats["warnings"]:
        print(f"      ⚠ {len(stats['warnings'])} source warning(s)")


def main() -> None:
    cfg = load_config()
    validate_config(cfg)

    topics = parse_topics(cfg["topics"])
    days: int = cfg.get("interval_days", 7)
    max_results: int = cfg.get("max_results_per_source", 25)
    max_age: int = cfg.get("max_age_days", 60)
    screen: bool = cfg.get("relevance_screen", True) and bool(os.environ.get("GROQ_API_KEY"))
    min_if: float = float(cfg.get("min_impact_factor", 0) or 0)
    always_include: list[str] = [s.lower() for s in cfg.get("always_include_journals", [])]
    recipient: str = cfg["recipient_email"]

    filter_note = f", impact factor ≥ {min_if:g}" if min_if else ""
    print(f"[run] {len(topics)} topic(s), last {days} days{filter_note}")
    if cfg.get("relevance_screen", True) and not screen:
        print("[run] no GROQ_API_KEY — relevance screening disabled")

    peer_by_topic: dict[str, list[dict]] = {}
    preprint_by_topic: dict[str, list[dict]] = {}
    dropped_by_topic: dict[str, int] = {}
    off_topic_by_topic: dict[str, int] = {}
    warnings: list[str] = []

    for topic, hints in topics:
        hint_note = f" (key terms: {', '.join(hints)})" if hints else ""
        print(f"\n[topic] {topic!r}{hint_note}")
        queries = translate_topic(topic, hints)
        display = queries["display"]

        papers, topic_warnings = fetch_all(queries, days, max_results, max_age)
        warnings.extend(topic_warnings)

        off_topic = 0
        if screen:
            found = len(papers)
            papers, off_topic, complete = screen_papers(topic, papers, hints)
            print(f"        screened {found} candidate(s) → {len(papers)} relevant")
            if not complete:
                warnings.append(f"relevance screen incomplete for '{display}'; "
                                "some papers are unscreened")

        peer = [p for p in papers if p["source"] not in PREPRINT_SOURCES]
        preprints = [p for p in papers if p["source"] in PREPRINT_SOURCES]

        annotate_impact(peer)
        dropped = 0
        if min_if:
            peer, dropped = filter_by_impact(peer, min_if, always_include)
            if dropped:
                print(f"        filtered out {dropped} peer-reviewed paper(s) below IF {min_if:g}")

        peer_by_topic[display] = rank_papers(peer)
        preprint_by_topic[display] = sorted(
            preprints, key=lambda p: p.get("date", ""), reverse=True
        )
        dropped_by_topic[display] = dropped
        off_topic_by_topic[display] = off_topic
        print(f"        → {len(peer)} peer-reviewed, {len(preprints)} preprint(s)")

    mark_cross_topic_duplicates(peer_by_topic, preprint_by_topic)

    today = datetime.date.today()
    stats = {
        "start": today - datetime.timedelta(days=days),
        "end": today,
        "days": days,
        "min_if": min_if,
        "screened": screen,
        "warnings": warnings,
        "topics": [
            {
                "name": name,
                "peer": len(_unique(peer_by_topic[name])),
                "preprints": len(_unique(preprint_by_topic[name])),
                "dropped": dropped_by_topic[name],
                "off_topic": off_topic_by_topic[name],
            }
            for name in peer_by_topic
        ],
    }
    stats["peer_total"] = sum(t["peer"] for t in stats["topics"])
    stats["preprint_total"] = sum(t["preprints"] for t in stats["topics"])
    _print_summary(stats)

    total = stats["peer_total"] + stats["preprint_total"]
    if total == 0 and not warnings:
        print("[run] nothing to send — exiting")
        sys.exit(0)
    if total == 0:
        print("[run] no papers found, but source warnings occurred — sending warning digest")

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        pdf_path = tmp.name

    build_pdf(stats, peer_by_topic, preprint_by_topic, pdf_path)
    print(f"[pdf] built → {pdf_path}")

    send_digest(pdf_path, recipient, stats, peer_by_topic, preprint_by_topic)

if __name__ == "__main__":
    main()
