import datetime
import re
from html import unescape
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, HRFlowable, PageBreak
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER


def build_pdf(results_by_keyword: dict[str, list[dict]], output_path: str, warnings: list[str] | None = None) -> None:
    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=2.5 * cm,
        rightMargin=2.5 * cm,
        topMargin=2.5 * cm,
        bottomMargin=2.5 * cm,
    )

    styles = _make_styles()
    story = []

    today = datetime.date.today().strftime("%B %d, %Y")
    story.append(Paragraph("Literature Digest", styles["title"]))
    story.append(Paragraph(today, styles["subtitle"]))
    story.append(Spacer(1, 0.5 * cm))

    total = sum(len(v) for v in results_by_keyword.values())
    story.append(Paragraph(
        f"Found <b>{total}</b> new papers across {len(results_by_keyword)} keyword(s).",
        styles["body"]
    ))
    if warnings:
        story.append(Spacer(1, 0.2 * cm))
        story.append(Paragraph(
            f"<b>⚠ {len(warnings)} source(s) failed to fetch</b> — results may be incomplete.",
            styles["body"]
        ))
        for w in warnings:
            story.append(Paragraph(f"&nbsp;&nbsp;• {_strip_html(w)}", styles["source"]))
        story.append(Spacer(1, 0.4 * cm))

    story.append(Spacer(1, 0.8 * cm))

    for keyword, papers in results_by_keyword.items():
        story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#2c5f8a")))
        story.append(Spacer(1, 0.2 * cm))
        story.append(Paragraph(keyword, styles["keyword_heading"]))
        story.append(Paragraph(
            f"{len(papers)} paper{'s' if len(papers) != 1 else ''}",
            styles["count"]
        ))
        story.append(Spacer(1, 0.4 * cm))

        if not papers:
            story.append(Paragraph("No new publications found for this keyword.", styles["body"]))
            story.append(Spacer(1, 0.5 * cm))
            continue

        for i, paper in enumerate(papers, 1):
            story.extend(_paper_block(paper, i, styles))

        story.append(Spacer(1, 0.5 * cm))

    doc.build(story)


def _strip_html(text: str) -> str:
    """Remove HTML tags, unescape entities, then re-escape XML-special chars
    so ReportLab's paragraph parser never sees bare & < > in plain text."""
    text = re.sub(r'<[^>]+>', '', text)      # strip tags
    text = unescape(text).strip()            # decode &amp; &lt; etc.
    # re-escape for ReportLab XML parser (but don't double-escape)
    text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    return text


def _paper_block(paper: dict, index: int, styles: dict) -> list:
    elements = []

    title = _strip_html(paper.get("title", "Untitled"))
    elements.append(Paragraph(f"{index}. {title}", styles["paper_title"]))

    ref = _format_reference(paper)
    elements.append(Paragraph(ref, styles["reference"]))

    source_badge = f'[{paper.get("source", "")}]'
    url = paper.get("url", "")
    if url:
        source_text = f'{source_badge} <a href="{url}" color="#2c5f8a">{url}</a>'
    else:
        source_text = source_badge
    elements.append(Paragraph(source_text, styles["source"]))

    abstract = _strip_html(paper.get("abstract", ""))
    if abstract:
        if len(abstract) > 800:
            abstract = abstract[:797] + "..."
        elements.append(Spacer(1, 0.15 * cm))
        elements.append(Paragraph(abstract, styles["abstract"]))

    elements.append(Spacer(1, 0.5 * cm))
    return elements


def _format_reference(paper: dict) -> str:
    authors = _strip_html(paper.get("authors", ""))
    date = paper.get("date", "")
    title = _strip_html(paper.get("title", ""))
    journal = _strip_html(paper.get("journal", ""))
    doi = paper.get("doi", "")

    parts = []
    if authors:
        parts.append(authors)
    if date:
        parts.append(f"({date})")
    if title:
        parts.append(f"<i>{title}</i>")
    if journal:
        parts.append(journal)
    if doi:
        parts.append(f"https://doi.org/{doi}")

    return ". ".join(parts) + "." if parts else ""


def _make_styles() -> dict:
    base = getSampleStyleSheet()
    accent = colors.HexColor("#2c5f8a")

    return {
        "title": ParagraphStyle(
            "title", parent=base["Normal"],
            fontSize=22, textColor=accent,
            spaceAfter=4, alignment=TA_CENTER, fontName="Helvetica-Bold",
        ),
        "subtitle": ParagraphStyle(
            "subtitle", parent=base["Normal"],
            fontSize=11, textColor=colors.grey,
            spaceAfter=6, alignment=TA_CENTER,
        ),
        "keyword_heading": ParagraphStyle(
            "keyword_heading", parent=base["Normal"],
            fontSize=15, textColor=accent,
            spaceBefore=4, spaceAfter=2, fontName="Helvetica-Bold",
        ),
        "count": ParagraphStyle(
            "count", parent=base["Normal"],
            fontSize=9, textColor=colors.grey, spaceAfter=4,
        ),
        "paper_title": ParagraphStyle(
            "paper_title", parent=base["Normal"],
            fontSize=11, fontName="Helvetica-Bold",
            spaceBefore=4, spaceAfter=3,
        ),
        "reference": ParagraphStyle(
            "reference", parent=base["Normal"],
            fontSize=9, textColor=colors.HexColor("#444444"), spaceAfter=2,
        ),
        "source": ParagraphStyle(
            "source", parent=base["Normal"],
            fontSize=8, textColor=colors.grey, spaceAfter=3,
        ),
        "abstract": ParagraphStyle(
            "abstract", parent=base["Normal"],
            fontSize=9, leading=13,
            leftIndent=10, textColor=colors.HexColor("#333333"),
        ),
        "body": ParagraphStyle(
            "body", parent=base["Normal"],
            fontSize=10, leading=14,
        ),
    }
