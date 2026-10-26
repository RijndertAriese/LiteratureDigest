import os
import smtplib
from email.message import EmailMessage
from html import escape

from bot.formatting import date_window, display_date, impact_label, paper_link, plural


def _env(*names: str) -> str | None:
    """Return the first set (non-empty) environment variable among names."""
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return None


_TOP_PICKS = 3
_ACCENT = "#2c5f8a"


def build_email(
    stats: dict,
    peer_by_topic: dict[str, list[dict]],
    preprint_by_topic: dict[str, list[dict]],
) -> tuple[str, str, str]:
    """Return ``(subject, plain_text, html)`` for the digest email."""
    today = display_date(stats["end"])
    peer_total, preprint_total = stats["peer_total"], stats["preprint_total"]
    warnings = stats["warnings"]

    counts = plural(peer_total, "paper")
    if preprint_total:
        counts += f", {plural(preprint_total, 'preprint')}"
    subject = f"Literature Digest — {today} · {counts}"
    if warnings:
        subject = "⚠ " + subject

    window = date_window(stats)
    if stats["min_if"]:
        window += f" · journals with IF ≥ {stats['min_if']:g}"

    picks = {
        name: [p for p in papers if not p.get("duplicate_of")][:_TOP_PICKS]
        for name, papers in peer_by_topic.items()
    }
    return subject, _plain_body(stats, window, picks), _html_body(stats, window, picks)


def _pick_meta(paper: dict) -> str:
    parts = [paper.get("journal", ""), impact_label(paper), display_date(paper.get("date", ""))]
    return " · ".join(p for p in parts if p)


def _plain_body(stats: dict, window: str, picks: dict[str, list[dict]]) -> str:
    lines = ["Literature Digest", window, ""]

    name_w = min(max([len(t["name"]) for t in stats["topics"]] + [5]), 50)
    lines.append(f"{'Topic':<{name_w}}  {'Papers':>6}  {'Preprints':>9}")
    for t in stats["topics"]:
        name = t["name"] if len(t["name"]) <= name_w else t["name"][:name_w - 1] + "…"
        lines.append(f"{name:<{name_w}}  {t['peer']:>6}  {t['preprints']:>9}")
    lines.append(f"{'Total':<{name_w}}  {stats['peer_total']:>6}  {stats['preprint_total']:>9}")

    if stats["warnings"]:
        lines += ["", f"⚠ {plural(len(stats['warnings']), 'source')} failed to fetch "
                      "— results may be incomplete:"]
        lines += [f"  - {w}" for w in stats["warnings"]]

    if any(picks.values()):
        lines += ["", "TOP PICKS"]
        for name, papers in picks.items():
            if not papers:
                continue
            lines += ["", name]
            for i, p in enumerate(papers, 1):
                lines.append(f"  {i}. {p.get('title', 'Untitled')}")
                lines.append(f"     {_pick_meta(p)}")
                link = paper_link(p)
                if link:
                    lines.append(f"     {link}")

    lines += ["", "The full digest with abstracts is attached (PDF).", "", "— Literature Bot"]
    return "\n".join(lines)


def _html_body(stats: dict, window: str, picks: dict[str, list[dict]]) -> str:
    cell = "padding:6px 10px;border-bottom:1px solid #e3e8ee;"
    num = cell + "text-align:right;"
    rows = "".join(
        f"<tr><td style='{cell}'>{escape(t['name'])}</td>"
        f"<td style='{num}'>{t['peer']}</td><td style='{num}'>{t['preprints']}</td></tr>"
        for t in stats["topics"]
    )
    table = (
        "<table cellspacing='0' cellpadding='0' "
        "style='border-collapse:collapse;font-size:14px;margin:12px 0 20px;'>"
        f"<tr style='background:{_ACCENT};color:#ffffff;'>"
        f"<th style='{cell}text-align:left;'>Topic</th>"
        f"<th style='{num}'>Papers</th><th style='{num}'>Preprints</th></tr>"
        f"{rows}"
        f"<tr><td style='{cell}font-weight:bold;'>Total</td>"
        f"<td style='{num}font-weight:bold;'>{stats['peer_total']}</td>"
        f"<td style='{num}font-weight:bold;'>{stats['preprint_total']}</td></tr>"
        "</table>"
    )

    warning_block = ""
    if stats["warnings"]:
        items = "".join(f"<li>{escape(w)}</li>" for w in stats["warnings"])
        warning_block = (
            "<div style='background:#fff4e5;border:1px solid #e0a040;padding:10px 14px;"
            "margin:0 0 20px;font-size:13px;'>"
            f"<b>⚠ {plural(len(stats['warnings']), 'source')} failed to fetch</b> "
            f"— results may be incomplete.<ul style='margin:6px 0 0;'>{items}</ul></div>"
        )

    pick_blocks = []
    for name, papers in picks.items():
        if not papers:
            continue
        items = []
        for p in papers:
            title = escape(p.get("title") or "Untitled")
            link = paper_link(p)
            if link:
                title = (f"<a href='{escape(link, quote=True)}' "
                         f"style='color:{_ACCENT};text-decoration:none;'>{title}</a>")
            items.append(
                f"<li style='margin:0 0 8px;'><span style='font-weight:bold;'>{title}</span><br>"
                f"<span style='color:#666666;font-size:13px;'>{escape(_pick_meta(p))}</span></li>"
            )
        pick_blocks.append(
            f"<h3 style='color:{_ACCENT};font-size:15px;margin:18px 0 6px;'>{escape(name)}</h3>"
            f"<ol style='padding-left:20px;margin:0;'>{''.join(items)}</ol>"
        )
    picks_html = ""
    if pick_blocks:
        picks_html = (
            "<h2 style='font-size:17px;margin:8px 0 0;'>Top picks</h2>"
            "<p style='color:#666666;font-size:13px;margin:2px 0 0;'>"
            f"Highest-impact journals first, up to {_TOP_PICKS} per topic.</p>"
            + "".join(pick_blocks)
        )

    return (
        "<div style='font-family:Helvetica,Arial,sans-serif;color:#222222;"
        "max-width:680px;line-height:1.4;'>"
        f"<h1 style='color:{_ACCENT};font-size:22px;margin:0;'>Literature Digest</h1>"
        f"<p style='color:#666666;margin:4px 0 0;'>{escape(window)}</p>"
        f"{table}{warning_block}{picks_html}"
        "<p style='margin:24px 0 0;font-size:13px;color:#666666;'>"
        "The full digest with abstracts is attached (PDF).<br>— Literature Bot</p>"
        "</div>"
    )


def send_digest(
    pdf_path: str,
    recipient: str,
    stats: dict,
    peer_by_topic: dict[str, list[dict]],
    preprint_by_topic: dict[str, list[dict]],
) -> None:
    host = os.environ["SMTP_HOST"]
    port = int(os.environ.get("SMTP_PORT", "587"))
    username = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_PASSWORD")
    # From address defaults to the SMTP username (usually an email address).
    sender = _env("SENDER_EMAIL", "SMTP_SENDER_EMAIL") or username
    if not sender:
        raise RuntimeError("No sender address: set SENDER_EMAIL or SMTP_USER")

    subject, text, html = build_email(stats, peer_by_topic, preprint_by_topic)

    message = EmailMessage()
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(text)
    message.add_alternative(html, subtype="html")

    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()

    filename = f"literature_digest_{stats['end'].isoformat()}.pdf"
    message.add_attachment(
        pdf_bytes, maintype="application", subtype="pdf", filename=filename
    )

    if port == 465:
        with smtplib.SMTP_SSL(host, port, timeout=60) as server:
            if username and password:
                server.login(username, password)
            server.send_message(message)
    else:
        with smtplib.SMTP(host, port, timeout=60) as server:
            server.starttls()
            if username and password:
                server.login(username, password)
            server.send_message(message)

    print(f"[mail] sent — to {recipient} via {host}:{port}")
