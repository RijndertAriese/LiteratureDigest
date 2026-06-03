"""
Translates plain-English research topics into database-optimised search queries
using Gemini Flash. Falls back to the raw topic string if the API key is absent.
"""

import json
import os

from google import genai
from google.genai import types

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
        response = client.models.generate_content(
            model="gemini-1.5-flash",
            contents=f'Topic: "{topic}"',
            config=types.GenerateContentConfig(
                system_instruction=_SYSTEM_PROMPT,
            ),
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
