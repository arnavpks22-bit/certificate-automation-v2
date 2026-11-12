
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
    Send one email with one or more PDF attachments.

    Example attachments:

    [
        ("Certificate_1.pdf", pdf_bytes_1),
        ("Certificate_2.pdf", pdf_bytes_2)
    ]

    The certificate_pdf and filename arguments are
    retained for compatibility with older code.
    """

    sender = str(sender).strip()
    recipient = str(recipient).strip()
    app_password = str(app_password).replace(" ", "")

    if not sender:
        raise ValueError("Sender email is required.")

    if not recipient:
        raise ValueError("Recipient email is required.")

    if not app_password:
        raise ValueError("Gmail App Password is required.")

    if not str(subject).strip():
        raise ValueError("Email subject is required.")

    if attachments is None:
        if certificate_pdf is None:
            raise ValueError(
                "No certificate attachments provided."
            )

        attachments = [
            (
                filename or "certificate.pdf",
                certificate_pdf
            )
        ]

    if not attachments:
        raise ValueError(
            "At least one PDF attachment is required."
        )

    message = EmailMessage()

    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = str(subject)

    message.set_content(str(body))

    # Attach every certificate to the same email.
    for attachment_name, pdf_bytes in attachments:

        if not isinstance(pdf_bytes, bytes):
            raise TypeError(
                "Certificate PDF must be bytes."
            )

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

    # Connect to Gmail using SSL.
    with smtplib.SMTP_SSL(
        "smtp.gmail.com",
        465,
        timeout=30
    ) as smtp:

        smtp.login(
            sender,
            app_password
        )

        smtp.send_message(message)

    return True
