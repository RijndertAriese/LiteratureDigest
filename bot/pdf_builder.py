import re
from html import escape, unescape
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, HRFlowable, PageBreak, KeepTogether,
    Table, TableStyle,
)
from reportlab.lib.enums import TA_CENTER, TA_RIGHT

from bot.formatting import (
    FOLLOWED_TOPIC, badges, date_window, display_date, impact_label, paper_link, plural,
)

ACCENT = colors.HexColor("#2c5f8a")
_ABSTRACT_LIMIT = 800


def build_pdf(
    stats: dict,
    peer_by_topic: dict[str, list[dict]],
    preprint_by_topic: dict[str, list[dict]],
    output_path: str,
) -> None:
    today = display_date(stats["end"])
    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=2.2 * cm,
        rightMargin=2.2 * cm,
        topMargin=2.2 * cm,
        bottomMargin=2.2 * cm,
        title=f"Literature Digest — {today}",
        author="LiteratureDigest",
    )

    styles = _make_styles()
    peer_anchors = {name: f"peer-{i}" for i, name in enumerate(peer_by_topic)}
    preprint_anchors = {name: f"pre-{i}" for i, name in enumerate(preprint_by_topic)}

    story = [
        Paragraph("Literature Digest", styles["title"]),
        Paragraph(_header_line(stats), styles["subtitle"]),
        Spacer(1, 0.5 * cm),
        _overview_table(stats, peer_anchors, styles),
    ]
    if stats["warnings"]:
        story += [Spacer(1, 0.4 * cm), _warning_box(stats["warnings"], styles)]
    story.append(Spacer(1, 0.8 * cm))

    summaries = {t["name"]: t.get("summary") for t in stats["topics"]}
    for name, papers in peer_by_topic.items():
        empty = ("No new peer-reviewed papers by followed authors this period."
                 if name == FOLLOWED_TOPIC else "No new peer-reviewed papers this period.")
        story.extend(_topic_section(
            name, papers, peer_anchors, styles, empty_text=empty, summary=summaries.get(name),
        ))

    if stats["preprint_total"]:
        story += [
            PageBreak(),
            Paragraph("Preprints", styles["title"]),
            Paragraph("Not peer-reviewed · no impact-factor filter applied · newest first",
                      styles["subtitle"]),
            Spacer(1, 0.6 * cm),
        ]
        for name, papers in preprint_by_topic.items():
            if papers:
                story.extend(_topic_section(name, papers, preprint_anchors, styles))

    def footer(canvas, doc_):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.grey)
        canvas.drawString(doc_.leftMargin, 1.2 * cm, f"Literature Digest · {today}")
        canvas.drawRightString(
            A4[0] - doc_.rightMargin, 1.2 * cm, f"page {canvas.getPageNumber()}"
        )
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)


def _header_line(stats: dict) -> str:
    line = date_window(stats)
    if stats["min_if"]:
        line += f" · minimum journal IF {stats['min_if']:g}"
    if stats.get("screened"):
        line += " · relevance-screened"
    return line


def _overview_table(stats: dict, anchors: dict[str, str], styles: dict) -> Table:
    show_dropped = bool(stats["min_if"])
    show_off_topic = bool(stats.get("screened"))
    header = (["Topic", "Papers", "Preprints"]
              + (["Below IF"] if show_dropped else [])
              + (["Off-topic"] if show_off_topic else []))
    rows = [[Paragraph(f"<b>{h}</b>", styles["cell_head"] if i else styles["cell_head_left"])
             for i, h in enumerate(header)]]

    for t in stats["topics"]:
        link = f'<a href="#{anchors[t["name"]]}" color="#2c5f8a">{_strip_html(t["name"])}</a>'
        row = [Paragraph(link, styles["cell"]),
               Paragraph(str(t["peer"]), styles["cell_num"]),
               Paragraph(str(t["preprints"]), styles["cell_num"])]
        if show_dropped:
            row.append(Paragraph(str(t["dropped"]), styles["cell_num_muted"]))
        if show_off_topic:
            row.append(Paragraph(str(t.get("off_topic", 0)), styles["cell_num_muted"]))
        rows.append(row)

    totals = [Paragraph("<b>Total</b>", styles["cell"]),
              Paragraph(f"<b>{stats['peer_total']}</b>", styles["cell_num"]),
              Paragraph(f"<b>{stats['preprint_total']}</b>", styles["cell_num"])]
    if show_dropped:
        dropped = sum(t["dropped"] for t in stats["topics"])
        totals.append(Paragraph(f"<b>{dropped}</b>", styles["cell_num_muted"]))
    if show_off_topic:
        off = sum(t.get("off_topic", 0) for t in stats["topics"])
        totals.append(Paragraph(f"<b>{off}</b>", styles["cell_num_muted"]))
    rows.append(totals)

    num_w = 2.6 * cm if len(header) <= 4 else 2.2 * cm
    widths = [None] + [num_w] * (len(header) - 1)
    table = Table(rows, colWidths=widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor("#f2f6fa")]),
        ("LINEABOVE", (0, -1), (-1, -1), 1, ACCENT),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return table


def _warning_box(warnings: list[str], styles: dict) -> Table:
    lines = [Paragraph(
        f"<b>Warning: {plural(len(warnings), 'source')} failed to fetch</b> — results may be incomplete.",
        styles["body"],
    )]
    lines += [Paragraph(f"• {_strip_html(w)}", styles["warning_item"]) for w in warnings]
    box = Table([[lines]], colWidths=["100%"])
    box.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fff4e5")),
        ("BOX", (0, 0), (-1, -1), 0.75, colors.HexColor("#e0a040")),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return box


def _topic_section(
    name: str,
    papers: list[dict],
    anchors: dict[str, str],
    styles: dict,
    empty_text: str = "No new publications found for this topic.",
    summary: str | None = None,
) -> list:
    unique = [p for p in papers if not p.get("duplicate_of")]
    repeats = [p for p in papers if p.get("duplicate_of")]

    count = plural(len(unique), "paper")
    if repeats:
        count += f" · {len(repeats)} also listed under another topic"
    heading = KeepTogether([
        HRFlowable(width="100%", thickness=1.5, color=ACCENT),
        Spacer(1, 0.2 * cm),
        Paragraph(f'<a name="{anchors[name]}"/>{_strip_html(name)}', styles["keyword_heading"]),
        Paragraph(count, styles["count"]),
        Spacer(1, 0.3 * cm),
    ])
    elements = [heading]
    if summary:
        elements += [_summary_box(summary, styles), Spacer(1, 0.35 * cm)]

    if not papers:
        elements += [Paragraph(empty_text, styles["empty"]), Spacer(1, 0.5 * cm)]
        return elements

    for i, paper in enumerate(unique, 1):
        elements.append(KeepTogether(_paper_block(paper, i, styles)))

    if repeats:
        elements.append(Paragraph("Also matches this topic:", styles["count"]))
        for p in repeats:
            target = anchors.get(p["duplicate_of"])
            see = _strip_html(p["duplicate_of"])
            if target:
                see = f'<a href="#{target}" color="#2c5f8a">{see}</a>'
            elements.append(Paragraph(
                f"• {_strip_html(p.get('title', 'Untitled'))} — see {see}",
                styles["repeat"],
            ))

    elements.append(Spacer(1, 0.5 * cm))
    return elements


def _summary_box(summary: str, styles: dict) -> Table:
    box = Table(
        [[Paragraph(f"<b>This week:</b> {_strip_html(summary)}", styles["summary"])]],
        colWidths=["100%"],
    )
    box.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f2f6fa")),
        ("LINEBEFORE", (0, 0), (0, -1), 2.5, ACCENT),
        ("LEFTPADDING", (0, 0), (-1, -1), 9),
        ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return box


def _strip_html(text: str) -> str:
    """Remove HTML tags, unescape entities, then re-escape XML-special chars
    so ReportLab's paragraph parser never sees bare & < > in plain text."""
    text = re.sub(r'<[^>]+>', '', text or "")   # strip tags
    text = unescape(text).strip()               # decode &amp; &lt; etc.
    # re-escape for ReportLab XML parser (but don't double-escape)
    text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    return text


def _truncate(text: str, limit: int = _ABSTRACT_LIMIT) -> str:
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0].rstrip(",;:.")
    return cut + " …"


def _paper_block(paper: dict, index: int, styles: dict) -> list:
    title = _strip_html(paper.get("title") or "Untitled")
    link = paper_link(paper)
    if link:
        title = f'<a href="{escape(link, quote=True)}">{title}</a>'
    elements = [
        Paragraph(f"{index}. {title}", styles["paper_title"]),
        Paragraph(_meta_line(paper), styles["meta"]),
    ]

    authors = _strip_html(paper.get("authors", ""))
    if authors:
        elements.append(Paragraph(authors, styles["authors"]))

    if paper.get("also_in"):
        others = ", ".join(_strip_html(t) for t in paper["also_in"])
        elements.append(Paragraph(f"Also matches: {others}", styles["authors"]))

    if paper.get("reason"):
        elements.append(Paragraph(f"Why: {_strip_html(paper['reason'])}", styles["reason"]))

    abstract = _strip_html(_truncate(paper.get("abstract", "")))
    if abstract:
        elements += [Spacer(1, 0.1 * cm), Paragraph(abstract, styles["abstract"])]

    elements.append(Spacer(1, 0.45 * cm))
    return elements


def _meta_line(paper: dict) -> str:
    """'[Review] <i>Journal</i> · IF 12.3 · 15 Oct 2026 · PubMed · Free PDF'."""
    tags = "".join(
        f'<font backColor="#e3ecf5" color="#2c5f8a" size="7.5">&nbsp;{_strip_html(b)}&nbsp;</font> '
        for b in badges(paper)
    )
    parts = []
    journal = _strip_html(paper.get("journal", ""))
    if journal and not journal.endswith(" preprint"):  # 'bioRxiv preprint' repeats the source
        parts.append(f"<i>{journal}</i>")
    impact = impact_label(paper)
    if paper.get("impact_whitelisted"):
        parts.append(f'<font color="#2c5f8a">{impact}</font>')
    elif impact:
        parts.append(f"<b>{impact}</b>")
    date = display_date(paper.get("date", ""))
    if date:
        parts.append(date)
    source = paper.get("source", "")
    url = paper.get("url", "")
    if source and url:
        parts.append(f'<a href="{escape(url, quote=True)}" color="#2c5f8a">{source}</a>')
    elif source:
        parts.append(source)
    if paper.get("oa_url"):
        parts.append(f'<a href="{escape(paper["oa_url"], quote=True)}" color="#2a7a3b">Free PDF</a>')
    return tags + " · ".join(parts)


def _make_styles() -> dict:
    base = getSampleStyleSheet()
    normal = base["Normal"]

    def style(name, **kw):
        return ParagraphStyle(name, parent=normal, **kw)

    return {
        "title": style("title", fontSize=22, leading=26, textColor=ACCENT,
                       spaceAfter=4, alignment=TA_CENTER, fontName="Helvetica-Bold"),
        "subtitle": style("subtitle", fontSize=10, textColor=colors.grey,
                          spaceAfter=6, alignment=TA_CENTER),
        "keyword_heading": style("keyword_heading", fontSize=15, leading=19, textColor=ACCENT,
                                 spaceBefore=4, spaceAfter=2, fontName="Helvetica-Bold"),
        "count": style("count", fontSize=9, textColor=colors.grey, spaceAfter=4),
        "paper_title": style("paper_title", fontSize=11, leading=14,
                             fontName="Helvetica-Bold", spaceBefore=4, spaceAfter=2),
        "meta": style("meta", fontSize=9, leading=12,
                      textColor=colors.HexColor("#333333"), spaceAfter=1),
        "authors": style("authors", fontSize=8.5, leading=11, textColor=colors.grey),
        "reason": style("reason", fontSize=8.5, leading=11, textColor=ACCENT,
                        fontName="Helvetica-Oblique", spaceBefore=1),
        "summary": style("summary", fontSize=9.5, leading=13.5,
                         textColor=colors.HexColor("#333333")),
        "abstract": style("abstract", fontSize=9, leading=13, leftIndent=10,
                          textColor=colors.HexColor("#333333")),
        "body": style("body", fontSize=10, leading=14),
        "empty": style("empty", fontSize=10, leading=14, textColor=colors.grey,
                       fontName="Helvetica-Oblique"),
        "repeat": style("repeat", fontSize=9, leading=12, leftIndent=10,
                        textColor=colors.HexColor("#444444")),
        "warning_item": style("warning_item", fontSize=8.5, leading=11, leftIndent=6,
                              textColor=colors.HexColor("#5a4a2a")),
        "cell": style("cell", fontSize=9.5, leading=12),
        "cell_head": style("cell_head", fontSize=9, leading=11,
                           textColor=colors.white, alignment=TA_RIGHT),
        "cell_head_left": style("cell_head_left", fontSize=9, leading=11, textColor=colors.white),
        "cell_num": style("cell_num", fontSize=9.5, leading=12, alignment=TA_RIGHT),
        "cell_num_muted": style("cell_num_muted", fontSize=9.5, leading=12,
                                alignment=TA_RIGHT, textColor=colors.grey),
    }
