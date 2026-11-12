
import smtplib
from email.message import EmailMessage


def send_certificate(
    sender,
    app_password,
    recipient,
    subject,
    body,
    certificate_pdf=None,
    filename=None,
    attachments=None
):
    """
    Send one email containing multiple PDF attachments.

    attachments:
        [
            ("Participation_Certificate.pdf", pdf_bytes),
            ("Achievement_Certificate.pdf", pdf_bytes)
        ]

    The old certificate_pdf and filename arguments are
    retained for compatibility with earlier code.
    """

    sender = str(sender).strip()
    recipient = str(recipient).strip()
    app_password = str(app_password).replace(" ", "")

    if not sender or not recipient:
        raise ValueError("Sender and recipient are required.")

    if not app_password:
        raise ValueError("Gmail App Password is required.")

    if not subject or not str(subject).strip():
        raise ValueError("Email subject is required.")

    if attachments is None:
        if certificate_pdf is None:
            raise ValueError("No certificate attachments provided.")

        attachments = [
            (filename or "certificate.pdf", certificate_pdf)
        ]

    if not attachments:
        raise ValueError("Attachment list cannot be empty.")

    message = EmailMessage()
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = str(subject)
    message.set_content(str(body))

    for attachment_name, pdf_bytes in attachments:
        if not isinstance(pdf_bytes, bytes):
            raise TypeError("Certificate PDF must be bytes.")

        if not pdf_bytes.startswith(b"%PDF"):
            raise ValueError(
                f"Invalid PDF attachment: {attachment_name}"
            )

        message.add_attachment(
            pdf_bytes,
            maintype="application",
            subtype="pdf",
            filename=attachment_name
        )

    # Gmail SMTP over TLS.
    with smtplib.SMTP_SSL(
        "smtp.gmail.com",
        465,
        timeout=30
    ) as smtp:
        smtp.login(sender, app_password)
        smtp.send_message(message)

    return True
