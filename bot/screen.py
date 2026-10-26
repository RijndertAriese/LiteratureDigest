"""
Relevance screening with Groq.

Several broad query variants per topic catch more papers but also off-topic
hits. Groq reads each candidate's title and abstract and keeps only those that
genuinely address the topic. Screening fails open: if the API key is missing or
a batch call fails, that batch is kept unscreened.
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

Return ONLY a JSON object: {"relevant": [<numbers of relevant papers>]}
"""


def screen_papers(
    topic: str,
    papers: list[dict],
    hints: list[str] | None = None,
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
                    kept.append(p)
                else:
                    print(f"        [off-topic] {p.get('title', '').strip()[:110]}")
        except Exception as e:
            print(f"[screen] batch failed ({e}) — keeping {len(batch)} paper(s) unscreened")
            kept.extend(batch)
            complete = False

    return kept, len(papers) - len(kept), complete


def _screen_batch(
    client: Groq, topic: str, hints: list[str] | None, criteria: str | None, batch: list[dict]
) -> set[int]:
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
    relevant = json.loads(text).get("relevant")
    if not isinstance(relevant, list):
        raise ValueError("response has no 'relevant' list")
    numbers = (str(n).strip("[] ") for n in relevant)
    return {int(n) for n in numbers if n.isdigit()}
