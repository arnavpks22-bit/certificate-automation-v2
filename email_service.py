
import smtplib
import ssl

from email.message import EmailMessage


def send_certificate(
    sender,
    app_password,
    recipient,
    subject,
    body,
    certificate_pdf,
    filename
):
    """
    Send a personalized certificate email
    through Gmail SMTP.
    """

    # ======================================
    # VALIDATE INPUTS
    # ======================================

    if not sender or not app_password:
        raise ValueError(
            "Gmail sender credentials are missing."
        )

    if not recipient:
        raise ValueError(
            "Recipient email is missing."
        )

    if not isinstance(certificate_pdf, bytes):
        raise TypeError(
            "Certificate must be PDF bytes."
        )

    if not certificate_pdf.startswith(b"%PDF-"):
        raise ValueError(
            "Invalid PDF attachment."
        )

    if "\n" in subject or "\r" in subject:
        raise ValueError(
            "Email subject must be a single line."
        )

    # ======================================
    # CREATE EMAIL
    # ======================================

    message = EmailMessage()

    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = subject

    message.set_content(body)

    # ======================================
    # ATTACH CERTIFICATE
    # ======================================

    message.add_attachment(
        certificate_pdf,
        maintype="application",
        subtype="pdf",
        filename=filename
    )

    # ======================================
    # SEND THROUGH GMAIL
    # ======================================

    context = ssl.create_default_context()

    with smtplib.SMTP_SSL(
        "smtp.gmail.com",
        465,
        context=context,
        timeout=30
    ) as server:

        server.login(
            sender,
            app_password
        )

        refused = server.send_message(message)

        if refused:
            raise RuntimeError(
                f"Gmail rejected recipients: {refused}"
            )