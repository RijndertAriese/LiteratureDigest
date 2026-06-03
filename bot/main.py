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
        cfg = yaml.safe_load(f)

    if os.environ.get("RECIPIENT_EMAIL"):
        cfg["recipient_email"] = os.environ["RECIPIENT_EMAIL"]

    return cfg


def main() -> None:
    cfg = load_config()
    topics: list[str] = cfg["topics"]
    days: int = cfg.get("interval_days", 7)
    max_results: int = cfg.get("max_results_per_source", 25)
    recipient: str = cfg["recipient_email"]

    print(f"[run] {len(topics)} topic(s), last {days} days")

    results_by_topic: dict[str, list[dict]] = {}

    for topic in topics:
        print(f"\n[topic] {topic!r}")
        queries = translate_topic(topic)
        display = queries["display"]

        papers = fetch_all(queries, days, max_results)
        results_by_topic[display] = papers
        print(f"        → {len(papers)} papers")

    total = sum(len(v) for v in results_by_topic.values())
    print(f"\n[run] total: {total} papers")

    if total == 0:
        print("[run] nothing to send — exiting")
        sys.exit(0)

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        pdf_path = tmp.name

    build_pdf(results_by_topic, pdf_path)
    print(f"[pdf] built → {pdf_path}")

    send_digest(pdf_path, recipient, total)


if __name__ == "__main__":
    main()
