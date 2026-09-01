import datetime
import os
import smtplib
from email.message import EmailMessage
from html import escape


def _env(*names: str) -> str | None:
    """Return the first set (non-empty) environment variable among names."""
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return None


def send_digest(pdf_path: str, recipient: str, paper_count: int, warnings: list[str] | None = None) -> None:
    host = os.environ["SMTP_HOST"]
    port = int(os.environ.get("SMTP_PORT", "587"))
    username = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_PASSWORD")
    # From address defaults to the SMTP username (usually an email address).
    sender = _env("SENDER_EMAIL", "SMTP_SENDER_EMAIL") or username
    if not sender:
        raise RuntimeError("No sender address: set SENDER_EMAIL or SMTP_USER")

    today = datetime.date.today().strftime("%B %d, %Y")
    subject = f"Literature Digest — {today} ({paper_count} new paper{'s' if paper_count != 1 else ''})"

    warning_block = ""
    if warnings:
        items = "".join(f"<li>{escape(w)}</li>" for w in warnings)
        warning_block = (
            f"<p><b>⚠ {len(warnings)} source(s) failed to fetch</b> — "
            f"results may be incomplete:<ul>{items}</ul></p>"
        )

    body = (
        f"<p>Hi,</p>"
        f"<p>Your literature digest for <b>{today}</b> is attached. "
        f"It contains <b>{paper_count}</b> new paper{'s' if paper_count != 1 else ''} "
        f"from PubMed, arXiv, and bioRxiv.</p>"
        f"{warning_block}"
        f"<p>— Literature Bot</p>"
    )

    message = EmailMessage()
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(
        "Your literature digest is attached (view this message as HTML for details)."
    )
    message.add_alternative(body, subtype="html")

    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()

    filename = f"literature_digest_{datetime.date.today().isoformat()}.pdf"
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
