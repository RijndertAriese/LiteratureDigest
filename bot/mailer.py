import base64
import datetime
import os
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import (
    Mail, Attachment, FileContent, FileName, FileType, Disposition
)


def send_digest(pdf_path: str, recipient: str, paper_count: int) -> None:
    api_key = os.environ["SENDGRID_API_KEY"]
    sender = os.environ["SENDGRID_SENDER_EMAIL"]

    today = datetime.date.today().strftime("%B %d, %Y")
    subject = f"Literature Digest — {today} ({paper_count} new paper{'s' if paper_count != 1 else ''})"

    body = (
        f"<p>Hi,</p>"
        f"<p>Your literature digest for <b>{today}</b> is attached. "
        f"It contains <b>{paper_count}</b> new paper{'s' if paper_count != 1 else ''} "
        f"from PubMed, arXiv, and bioRxiv.</p>"
        f"<p>— Literature Bot</p>"
    )

    message = Mail(
        from_email=sender,
        to_emails=recipient,
        subject=subject,
        html_content=body,
    )

    with open(pdf_path, "rb") as f:
        encoded = base64.b64encode(f.read()).decode()

    filename = f"literature_digest_{datetime.date.today().isoformat()}.pdf"
    attachment = Attachment(
        FileContent(encoded),
        FileName(filename),
        FileType("application/pdf"),
        Disposition("attachment"),
    )
    message.attachment = attachment

    client = SendGridAPIClient(api_key)
    response = client.send(message)
    print(f"[mail] sent — status {response.status_code}")
