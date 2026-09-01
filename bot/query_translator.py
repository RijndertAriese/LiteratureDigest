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
Convert a plain-English research topic into optimised search queries for three databases.

Return ONLY a valid JSON object with exactly these four keys:
  "pubmed"  – PubMed query using boolean AND/OR, quoted phrases, MeSH terms where helpful
  "arxiv"   – arXiv query using basic boolean AND/OR, prefixed with cat:q-bio to stay biomedical
  "biorxiv" – short phrase (2-5 words) for simple text matching; no boolean operators
  "display" – clean human-readable heading for the PDF section (title-case, ≤60 chars)

Rules:
- Use double-quotes around multi-word phrases inside the JSON strings
- Do NOT wrap the output in markdown code fences
- Return nothing except the JSON object

Example input:  "myeloid cells in brain cancers"
Example output:
{
  "pubmed": "(microglia OR \\"tumor-associated macrophage\\" OR \\"myeloid cells\\") AND (glioma OR glioblastoma OR \\"brain tumor\\")",
  "arxiv": "cat:q-bio AND (microglia OR myeloid) AND (glioma OR glioblastoma)",
  "biorxiv": "myeloid cells brain tumor",
  "display": "Myeloid Cells in Brain Cancers"
}
"""


def translate_topic(topic: str) -> dict:
    """
    Returns a dict with keys: pubmed, arxiv, biorxiv, display.
    Falls back to using the raw topic string for all sources if no API key is set.
    """
    api_key = os.environ.get("GROQ_API_KEY")

    if not api_key:
        print(f"[translate] no GROQ_API_KEY — using raw topic as query: {topic!r}")
        return _fallback(topic)

    try:
        client = Groq(api_key=api_key)

        response = client.chat.completions.create(
            model=os.environ.get("GROQ_MODEL", _DEFAULT_MODEL),
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": f'Topic: "{topic}"'},
            ],
            temperature=0.1,
            max_tokens=512,
        )

        text = response.choices[0].message.content.strip()

        # strip accidental markdown fences
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]

        result = json.loads(text)

        # validate expected keys
        for key in ("pubmed", "arxiv", "biorxiv", "display"):
            if key not in result:
                raise ValueError(f"missing key: {key}")

        print(f"[translate] {topic!r}")
        print(f"            pubmed  → {result['pubmed']}")
        print(f"            arxiv   → {result['arxiv']}")
        print(f"            biorxiv → {result['biorxiv']}")
        return result

    except Exception as e:
        print(f"[translate] failed ({e}) — falling back to raw topic")
        return _fallback(topic)


def _fallback(topic: str) -> dict:
    return {
        "pubmed": topic,
        "arxiv": f"cat:q-bio AND ({topic})",
        "biorxiv": topic,
        "display": topic.title(),
    }
