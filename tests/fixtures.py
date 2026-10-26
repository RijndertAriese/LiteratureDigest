import datetime


def paper(title, journal="J", impact=None, date="2026-10-15", doi="", source="PubMed", **extra):
    return {
        "source": source,
        "title": title,
        "authors": "Doe J, Roe R",
        "journal": journal,
        "date": date,
        "abstract": "Background text. " * 80,
        "doi": doi,
        "url": "https://example.org/?a=1&b=2",
        "impact_factor": impact,
        **extra,
    }


def stats_for(peer_by_topic, preprint_by_topic, warnings=(), min_if=3.5):
    topics = [
        {
            "name": name,
            "peer": sum(not p.get("duplicate_of") for p in peer_by_topic[name]),
            "preprints": sum(not p.get("duplicate_of") for p in preprint_by_topic.get(name, [])),
            "dropped": 1,
        }
        for name in peer_by_topic
    ]
    return {
        "start": datetime.date(2026, 10, 12),
        "end": datetime.date(2026, 10, 19),
        "days": 7,
        "min_if": min_if,
        "warnings": list(warnings),
        "topics": topics,
        "peer_total": sum(t["peer"] for t in topics),
        "preprint_total": sum(t["preprints"] for t in topics),
    }
