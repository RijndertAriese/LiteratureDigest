"""
Translates plain-English research topics into database-optimised search queries
using Gemini Flash. Falls back to the raw topic string if the API key is absent.
"""

import json
import os

from google import genai

_SYSTEM_PROMPT = """\
You are a scientific literature search expert.
Convert a plain-English research topic into optimised search queries for three databases.

Return ONLY a valid JSON object with exactly these four keys:
  "pubmed"  – PubMed query using boolean AND/OR, quoted phrases, MeSH terms where helpful
  "arxiv"   – arXiv query using basic boolean AND/OR
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
  "arxiv": "(microglia OR myeloid) AND (glioma OR glioblastoma)",
  "biorxiv": "myeloid cells brain tumor",
  "display": "Myeloid Cells in Brain Cancers"
}
"""


def translate_topic(topic: str) -> dict:
    """
    Returns a dict with keys: pubmed, arxiv, biorxiv, display.
    Falls back to using the raw topic string for all sources if no API key is set.
    """
    api_key = os.environ.get("GEMINI_API_KEY")

    if not api_key:
        print(f"[translate] no GEMINI_API_KEY — using raw topic as query: {topic!r}")
        return _fallback(topic)

    try:
        client = genai.Client(api_key=api_key)

        # Discover which models are actually available on this account/region
        available = {
            m.name.split("/")[-1]
            for m in client.models.list()
            if "generateContent" in (getattr(m, "supported_actions", None) or [])
        }
        print(f"[translate] available models: {sorted(available)}")

        # Prefer lightweight flash models; fall back down the list
        _preference = [
            "gemini-2.0-flash-lite",
            "gemini-1.5-flash",
            "gemini-1.5-flash-8b",
            "gemini-2.0-flash",
            "gemini-2.5-flash-preview-05-20",
        ]
        model_name = next(
            (m for m in _preference if m in available),
            next(iter(m for m in available if "flash" in m), None),
        )
        if not model_name:
            raise RuntimeError("No usable Gemini model found on this account")

        print(f"[translate] using model: {model_name}")
        response = client.models.generate_content(
            model=model_name,
            contents=f"{_SYSTEM_PROMPT}\n\nTopic: \"{topic}\"",
        )

        text = response.text.strip()

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
        "arxiv": topic,
        "biorxiv": topic,
        "display": topic.title(),
    }
