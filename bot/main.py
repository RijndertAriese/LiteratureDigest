import os
import sys
import tempfile

import yaml

from bot.fetcher import fetch_all
from bot.impact import annotate_impact
from bot.pdf_builder import build_pdf
from bot.mailer import send_digest
from bot.query_translator import translate_topic

_PREPRINT_SOURCES = {"arXiv", "bioRxiv"}


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
    if not isinstance(topics, list) or not all(isinstance(t, str) and t.strip() for t in topics):
        errors.append("config.yaml: 'topics' is missing or empty")

    recipient = cfg.get("recipient_email")
    placeholder_emails = {"your@email.com", "you@example.com"}
    if (
        not isinstance(recipient, str)
        or not recipient.strip()
        or recipient in placeholder_emails
        or recipient.endswith("@example.com")
    ):
        errors.append("RECIPIENT_EMAIL secret (or config.yaml recipient_email) is not set")

    for key in ("interval_days", "max_results_per_source"):
        value = cfg.get(key, 7 if key == "interval_days" else 25)
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            errors.append(f"config.yaml: '{key}' must be a positive integer")

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


def main() -> None:
    cfg = load_config()
    validate_config(cfg)

    topics: list[str] = cfg["topics"]
    days: int = cfg.get("interval_days", 7)
    max_results: int = cfg.get("max_results_per_source", 25)
    min_if: float = float(cfg.get("min_impact_factor", 0) or 0)
    always_include: list[str] = [s.lower() for s in cfg.get("always_include_journals", [])]
    recipient: str = cfg["recipient_email"]

    filter_note = f", impact factor ≥ {min_if:g}" if min_if else ""
    print(f"[run] {len(topics)} topic(s), last {days} days{filter_note}")

    peer_by_topic: dict[str, list[dict]] = {}
    preprint_by_topic: dict[str, list[dict]] = {}
    warnings: list[str] = []
    dropped_total = 0

    for topic in topics:
        print(f"\n[topic] {topic!r}")
        queries = translate_topic(topic)
        display = queries["display"]

        papers, topic_warnings = fetch_all(queries, days, max_results)
        warnings.extend(topic_warnings)

        peer = [p for p in papers if p["source"] not in _PREPRINT_SOURCES]
        preprints = [p for p in papers if p["source"] in _PREPRINT_SOURCES]

        annotate_impact(peer)
        if min_if:
            peer, dropped = filter_by_impact(peer, min_if, always_include)
            dropped_total += dropped
            if dropped:
                print(f"        filtered out {dropped} peer-reviewed paper(s) below IF {min_if:g}")

        peer_by_topic[display] = peer
        preprint_by_topic[display] = preprints
        print(f"        → {len(peer)} peer-reviewed, {len(preprints)} preprint(s)")

    peer_total = sum(len(v) for v in peer_by_topic.values())
    preprint_total = sum(len(v) for v in preprint_by_topic.values())
    total = peer_total + preprint_total
    dropped_note = f", {dropped_total} below IF threshold" if min_if else ""
    print(
        f"\n[run] total: {peer_total} peer-reviewed + {preprint_total} preprint(s)"
        f"{dropped_note}, {len(warnings)} source warning(s)"
    )

    if total == 0 and not warnings:
        print("[run] nothing to send — exiting")
        sys.exit(0)
    if total == 0:
        print("[run] no papers found, but source warnings occurred — sending warning digest")

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        pdf_path = tmp.name

    build_pdf(peer_by_topic, pdf_path, warnings=warnings, preprints_by_keyword=preprint_by_topic)
    print(f"[pdf] built → {pdf_path}")

    send_digest(pdf_path, recipient, peer_total, warnings=warnings, preprint_count=preprint_total)


if __name__ == "__main__":
    main()
