import os
import sys
import tempfile

import yaml

from bot.fetcher import fetch_all
from bot.pdf_builder import build_pdf
from bot.mailer import send_digest
from bot.query_translator import translate_topic


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

    if not os.environ.get("SENDGRID_API_KEY"):
        errors.append("SENDGRID_API_KEY secret is not set")
    if not os.environ.get("SENDGRID_SENDER_EMAIL"):
        errors.append("SENDGRID_SENDER_EMAIL secret is not set")

    if errors:
        print("[error] Configuration problems found:")
        for e in errors:
            print(f"  • {e}")
        sys.exit(1)


def main() -> None:
    cfg = load_config()
    validate_config(cfg)

    topics: list[str] = cfg["topics"]
    days: int = cfg.get("interval_days", 7)
    max_results: int = cfg.get("max_results_per_source", 25)
    recipient: str = cfg["recipient_email"]

    print(f"[run] {len(topics)} topic(s), last {days} days")

    results_by_topic: dict[str, list[dict]] = {}
    warnings: list[str] = []

    for topic in topics:
        print(f"\n[topic] {topic!r}")
        queries = translate_topic(topic)
        display = queries["display"]

        papers, topic_warnings = fetch_all(queries, days, max_results)
        warnings.extend(topic_warnings)
        results_by_topic[display] = papers
        print(f"        → {len(papers)} papers")

    total = sum(len(v) for v in results_by_topic.values())
    print(f"\n[run] total: {total} papers, {len(warnings)} source warning(s)")

    if total == 0 and not warnings:
        print("[run] nothing to send — exiting")
        sys.exit(0)
    if total == 0:
        print("[run] no papers found, but source warnings occurred — sending warning digest")

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        pdf_path = tmp.name

    build_pdf(results_by_topic, pdf_path, warnings=warnings)
    print(f"[pdf] built → {pdf_path}")

    send_digest(pdf_path, recipient, total, warnings=warnings)


if __name__ == "__main__":
    main()
