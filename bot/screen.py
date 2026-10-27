"""
Relevance screening with Groq.

Several broad query variants per topic catch more papers but also off-topic
hits. Groq reads each candidate's title and abstract and keeps only those that
genuinely address the topic, with a one-line reason shown in the digest. It
also writes a short summary of each topic's week. Both fail open: without an
API key or when a call fails, papers are kept unscreened and summaries skipped.
"""

import json
import os

from groq import Groq

from bot.query_translator import _DEFAULT_MODEL, _user_message

_BATCH = 12
_ABSTRACT_CHARS = 600

_SYSTEM_PROMPT = """\
You screen scientific papers for a researcher's weekly literature digest.
Given a research topic and numbered papers (title + abstract), decide which
papers are relevant: the topic is a main subject of the paper, not a passing
mention. Be inclusive when a paper clearly contributes to the topic, e.g. a new
method, mechanism, model or clinical result in that area; reviews count.
Exclude papers that only share a keyword.
When inclusion criteria are given, they are strict: a paper must meet them,
however close its subject is to the topic.

For each relevant paper give a reason of at most 20 words saying what it
contributes to the topic (the finding or method, not "this paper is relevant").

Return ONLY a JSON object:
{"relevant": [{"id": <paper number>, "reason": "<at most 20 words>"}]}
"""

_SUMMARY_PROMPT = """You write the weekly overview for one topic of a researcher's literature digest.
Given the topic and this week's papers (title + why each is relevant), write 2-3
plain sentences on what is new: the main themes, notable findings or methods.
Mention specifics; do not list every paper or repeat titles verbatim.
No preamble (do not start with "This week"), no markdown.
Return ONLY a JSON object: {"summary": "<text>"}
"""


def screen_papers(
    topic: str,
    papers: list[dict],
    hints: list[list[str]] | None = None,
    criteria: str | None = None,
) -> tuple[list[dict], int, bool]:
    """
    Return ``(kept, rejected_count, complete)``. Rejected titles are logged so
    the screen's strictness can be checked in the run log.

    ``complete`` is False when a batch failed and was kept unscreened.
    Without ``GROQ_API_KEY`` nothing is screened (callers check for the key).
    """
    api_key = os.environ.get("GROQ_API_KEY")
    if not papers or not api_key:
        return papers, 0, True

    client = Groq(api_key=api_key, max_retries=5)
    kept: list[dict] = []
    complete = True
    for start in range(0, len(papers), _BATCH):
        batch = papers[start:start + _BATCH]
        try:
            relevant = _screen_batch(client, topic, hints, criteria, batch)
            for i, p in enumerate(batch, 1):
                if i in relevant:
                    if relevant[i]:
                        p["reason"] = relevant[i]
                    kept.append(p)
                else:
                    print(f"        [off-topic] {p.get('title', '').strip()[:110]}")
        except Exception as e:
            print(f"[screen] batch failed ({e}) — keeping {len(batch)} paper(s) unscreened")
            kept.extend(batch)
            complete = False

    return kept, len(papers) - len(kept), complete


def _screen_batch(
    client: Groq,
    topic: str,
    hints: list[list[str]] | None,
    criteria: str | None,
    batch: list[dict],
) -> dict[int, str]:
    """Return ``{paper_number: reason}`` for the relevant papers of one batch."""
    listing = "\n\n".join(
        f"[{i}] {p.get('title', '').strip()}\n{(p.get('abstract') or '')[:_ABSTRACT_CHARS]}"
        for i, p in enumerate(batch, 1)
    )
    response = client.chat.completions.create(
        model=os.environ.get("GROQ_MODEL") or _DEFAULT_MODEL,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": f"{_user_message(topic, hints, criteria)}\n\nPapers:\n\n{listing}"},
        ],
        temperature=0,
        seed=7,
        reasoning_effort="low",
        response_format={"type": "json_object"},
        max_completion_tokens=2048,
    )
    text = (response.choices[0].message.content or "").strip()
    return _parse_relevant(json.loads(text))


def _parse_relevant(payload: dict) -> dict[int, str]:
    """Accept [{"id": 1, "reason": "..."}] and, as a fallback, plain [1, "3"]."""
    relevant = payload.get("relevant")
    if not isinstance(relevant, list):
        raise ValueError("response has no 'relevant' list")
    out: dict[int, str] = {}
    for item in relevant:
        reason = ""
        if isinstance(item, dict):
            reason = str(item.get("reason") or "").strip()
            item = item.get("id")
        number = str(item).strip("[] ")
        if number.isdigit():
            out[int(number)] = reason
    return out


def summarise_topic(topic: str, papers: list[dict]) -> str | None:
    """2-3 sentence overview of this week's papers for ``topic``, or None."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not papers or not api_key:
        return None

    listing = "\n".join(
        f"- {p.get('title', '').strip()}"
        + (f" — {p['reason']}" if p.get("reason") else "")
        for p in papers
    )
    try:
        client = Groq(api_key=api_key, max_retries=5)
        response = client.chat.completions.create(
            model=os.environ.get("GROQ_MODEL") or _DEFAULT_MODEL,
            messages=[
                {"role": "system", "content": _SUMMARY_PROMPT},
                {"role": "user", "content": f'Topic: "{topic}"\n\nPapers:\n{listing}'},
            ],
            temperature=0,
            seed=7,
            reasoning_effort="low",
            response_format={"type": "json_object"},
            max_completion_tokens=2048,
        )
        text = (response.choices[0].message.content or "").strip()
        summary = str(json.loads(text).get("summary") or "").strip()
        return summary or None
    except Exception as e:
        print(f"[screen] summary failed for {topic!r} ({e})")
        return None
