
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.platypus import Paragraph


def create_certificate(student, template=None, background_bytes=None):
    """
    Generate a personalized certificate PDF.

    student:
        {"Name": "Participant Name", "Email": "email@example.com"}

    Returns:
        PDF as bytes.
    """

    if not isinstance(student, dict):
        raise TypeError("Student must be a dictionary.")

    name = str(student.get("Name", "")).strip()

    if not name:
        raise ValueError("Student name cannot be empty.")

    output = BytesIO()

    # A4 landscape dimensions
    width = 841.89
    height = 595.28

    pdf = canvas.Canvas(
        output,
        pagesize=(width, height)
    )

    # ======================================
    # BACKGROUND
    # ======================================

    if background_bytes:

        try:

            background = ImageReader(
                BytesIO(background_bytes)
            )

            pdf.drawImage(
                background,
                0,
                0,
                width=width,
                height=height,
                preserveAspectRatio=False,
                mask="auto"
            )

        except Exception as error:

            raise ValueError(
                "Unable to process certificate background."
            ) from error

    else:

        pdf.setFillColor(colors.white)

        pdf.rect(
            0,
            0,
            width,
            height,
            fill=1,
            stroke=0
        )

    # ======================================
    # TEXT POSITION
    # ======================================

    center_x = width * 0.45

    text_width = width * 0.64

    def draw_text(
        text,
        top,
        size=30,
        bold=True,
        color="#14234B"
    ):

        safe_text = escape(str(text))

        font_name = (
            "Helvetica-Bold"
            if bold
            else "Helvetica"
        )

        paragraph = None
        text_height = 0

        # Reduce font size for longer names
        for font_size in range(size, 7, -1):

            style = ParagraphStyle(
                name="CertificateText",
                fontName=font_name,
                fontSize=font_size,
                leading=font_size * 1.25,
                alignment=TA_CENTER,
                textColor=colors.HexColor(color)
            )

            paragraph = Paragraph(
                safe_text,
                style
            )

            _, text_height = paragraph.wrap(
                text_width,
                height
            )

            if text_height <= 44:
                break

        # Convert top-based position to PDF coordinates
        y = height - top - text_height

        paragraph.drawOn(
            pdf,
            center_x - text_width / 2,
            y
        )

    # ======================================
    # STUDENT NAME
    # ======================================

    draw_text(
        text=name,
        top=218,
        size=30,
        bold=True
    )

    pdf.showPage()
    pdf.save()

    return output.getvalue()