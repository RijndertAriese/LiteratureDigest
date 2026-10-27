"""
Author-name matching for the followed-authors watchlist.

Sources write names differently — PubMed "Ariese HCR", bioRxiv "Ariese, H. C. R.",
arXiv "H.C.R. Ariese" — so names are compared on (last name, first initial).
Common surnames can therefore match other people with the same first initial.
"""

import re
import unicodedata


def _plain(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    return "".join(c for c in text if not unicodedata.combining(c)).lower().strip()


def author_key(name: str) -> tuple[str, str] | None:
    """Return ``(last_name, first_initial)`` in lowercase ASCII, or None."""
    name = (name or "").strip()
    if not name:
        return None

    if "," in name:                                   # "Ariese, H. C. R."
        last, rest = name.split(",", 1)
    else:
        tokens = name.split()
        if len(tokens) == 1:
            return (_plain(tokens[0]), "")
        if re.fullmatch(r"[A-Z]{1,4}", tokens[-1]):   # "Ariese HCR" (PubMed)
            last, rest = " ".join(tokens[:-1]), tokens[-1]
        else:                                         # "H.C.R. Ariese" / "Rijndert Ariese"
            last, rest = tokens[-1], tokens[0]

    letters = re.sub(r"[^A-Za-z]", "", _plain(rest))
    return (_plain(last), letters[:1])


def matches_followed(paper: dict, followed: list[str]) -> list[str]:
    """Followed names (as written in config) that are authors of ``paper``."""
    wanted = {author_key(f): f for f in followed if author_key(f)}
    hits = []
    for name in paper.get("author_list", []):
        key = author_key(name)
        if key in wanted and wanted[key] not in hits:
            hits.append(wanted[key])
    return hits
