"""
Translates plain-English research topics into database-optimised search queries
using Groq. Falls back to the raw topic string if the API key is absent.

The default model can be overridden with the GROQ_MODEL environment variable.
"""

import json
import os

from groq import Groq

# Groq deprecated the Llama 3.x chat models on 2026-08-16; gpt-oss-20b is the
# recommended replacement for llama-3.1-8b-instant.
_DEFAULT_MODEL = "openai/gpt-oss-20b"

_SYSTEM_PROMPT = """\
You are a scientific literature search expert.
Convert a plain-English research topic into search queries for three databases.
Several query variants per database are combined, and every hit is later
screened for relevance, so favour recall: broad variants are welcome.

Return ONLY a valid JSON object with exactly these four keys:
  "pubmed"  – list of 3 PubMed queries (boolean AND/OR, quoted phrases, MeSH where helpful):
              1. focused: all core concepts of the topic
              2. broad: drop secondary qualifiers, but ALWAYS keep the concept that
                 makes the topic distinctive
              3. synonyms: same concepts as 1, phrased with alternative terms / MeSH
  "arxiv"   – list of 2 arXiv queries (basic boolean AND/OR), each prefixed with cat:q-bio
  "biorxiv" – list of 2-4 keyword groups for plain text matching; each group is a list
              of 1-3 single words or short phrases that must ALL appear in a preprint's
              title or abstract (case-insensitive). Prefer word stems that match
              variants, e.g. "macrophage" also matches "macrophages".
  "display" – clean human-readable heading for the PDF section (title-case, ≤60 chars)

Rules:
- Use double-quotes around multi-word phrases inside the JSON strings
- Do not restrict queries to a disease or tissue the topic does not mention
- Never swap a concept for a related but different one: e.g. "CAR myeloid cells"
  means CAR macrophages/monocytes (CAR-M), NOT CAR T cells
- When key terms are given, every query variant must use them (OR-ed with your
  own synonyms) and bioRxiv groups should include them
- Return nothing except the JSON object

Example input:  "myeloid cells in brain cancers"
Example output:
{
  "pubmed": [
    "(microglia OR \\"tumor-associated macrophage\\" OR \\"myeloid cells\\") AND (glioma OR glioblastoma OR \\"brain tumor\\")",
    "(microglia OR macrophage* OR myeloid) AND (glioma OR glioblastoma OR \\"brain neoplasms\\"[MeSH])",
    "(\\"Myeloid Cells\\"[MeSH] OR \\"Macrophages\\"[MeSH] OR \\"Microglia\\"[MeSH] OR monocyte*) AND (\\"Brain Neoplasms\\"[MeSH] OR medulloblastoma OR ependymoma OR \\"brain metastasis\\")"
  ],
  "arxiv": [
    "cat:q-bio AND (microglia OR myeloid OR macrophage) AND (glioma OR glioblastoma)",
    "cat:q-bio AND (macrophage OR myeloid) AND (\\"brain tumor\\" OR \\"brain cancer\\")"
  ],
  "biorxiv": [["myeloid", "glioma"], ["microglia", "glioblastoma"], ["macrophage", "brain tumo"]],
  "display": "Myeloid Cells in Brain Cancers"
}
"""

def translate_topic(
    topic: str, hints: list[str] | None = None, criteria: str | None = None
) -> dict:
    """
    Returns a dict with keys pubmed, arxiv (lists of query strings), biorxiv
    (list of keyword groups, each a list of terms) and display.
    Falls back to the raw topic string if no API key is set or the call fails.
    ``hints`` are key terms from config.yaml that every query should include;
    ``criteria`` is the topic's inclusion rule, given as context.
    """
    api_key = os.environ.get("GROQ_API_KEY")

    if not api_key:
        print(f"[translate] no GROQ_API_KEY — using raw topic as query: {topic!r}")
        return _fallback(topic)

    try:
        client = Groq(api_key=api_key, max_retries=5)

        response = client.chat.completions.create(
            model=os.environ.get("GROQ_MODEL") or _DEFAULT_MODEL,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": _user_message(topic, hints, criteria)},
            ],
            temperature=0,
            seed=7,
            # gpt-oss models spend tokens on reasoning before the answer; keep
            # the effort low and the budget generous so JSON still comes back.
            reasoning_effort="low",
            response_format={"type": "json_object"},
            max_completion_tokens=2048,
        )

        text = (response.choices[0].message.content or "").strip()
        if not text:
            raise ValueError("empty response from model")

        # strip accidental markdown fences
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]

        result = _normalise(json.loads(text))

        print(f"[translate] {topic!r}")
        for source in ("pubmed", "arxiv"):
            for q in result[source]:
                print(f"            {source:<7} → {q}")
        groups = " | ".join(" + ".join(g) for g in result["biorxiv"])
        print(f"            biorxiv → {groups}")
        return result

    except Exception as e:
        print(f"[translate] failed ({e}) — falling back to raw topic")
        return _fallback(topic)


def _user_message(
    topic: str, hints: list[str] | None = None, criteria: str | None = None
) -> str:
    message = f'Topic: "{topic}"'
    if hints:
        message += "\nKey terms: " + "; ".join(f'"{h}"' for h in hints)
    if criteria:
        message += f"\nInclusion criteria: {criteria}"
    return message


def _normalise(result: dict) -> dict:
    """Validate the model output and coerce single strings into lists."""
    if not isinstance(result, dict):
        raise ValueError("response is not a JSON object")
    for key in ("pubmed", "arxiv", "biorxiv", "display"):
        if key not in result:
            raise ValueError(f"missing key: {key}")

    out = {"display": str(result["display"]).strip()}
    for key in ("pubmed", "arxiv"):
        queries = result[key]
        if isinstance(queries, str):
            queries = [queries]
        out[key] = [str(q).strip() for q in queries if str(q).strip()]

    groups = result["biorxiv"]
    if isinstance(groups, str):
        groups = [groups.split()]
    out["biorxiv"] = [
        [t.strip().lower() for t in ([g] if isinstance(g, str) else g) if str(t).strip()]
        for g in groups
    ]
    out["biorxiv"] = [g for g in out["biorxiv"] if g]

    if not out["display"] or not out["pubmed"]:
        raise ValueError("empty display or pubmed queries")
    return out


_STOPWORDS = {
    "a", "an", "and", "or", "of", "in", "on", "for", "the", "with", "to", "by",
    "including", "combined", "between", "into", "from",
}


def _fallback(topic: str) -> dict:
    words = [w.strip("(),").lower() for w in topic.split()]
    keywords = [w for w in words if w and w not in _STOPWORDS]
    return {
        "pubmed": [topic],
        "arxiv": [f"cat:q-bio AND ({topic})"],
        "biorxiv": [keywords] if keywords else [],
        "display": topic.title(),
    }
