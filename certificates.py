
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
        {
            "Name": "Participant Name",
            "Email": "email@example.com"
        }

    Returns:
        PDF as bytes.
    """

    # ======================================
    # VALIDATE STUDENT
    # ======================================

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
    # CERTIFICATE BACKGROUND
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
    # NAME POSITION SETTINGS
    # ======================================

    # Center name horizontally on certificate
    center_x = width / 2

    # Name area width
    text_width = width * 0.65

    # Target name area, measured from top
    # Based on the provided certificate image
    name_center_from_top =1290

    # ======================================
    # TEXT DRAWING FUNCTION
    # ======================================

    def draw_text(
        text,
        center_top,
        size=28,
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

        # Automatically reduce font size
        # when the name is too long
        for font_size in range(size, 7, -1):

            style = ParagraphStyle(
                name="CertificateText",
                fontName=font_name,
                fontSize=font_size,
                leading=font_size * 1.15,
                alignment=TA_CENTER,
                textColor=colors.HexColor(color),
                spaceBefore=0,
                spaceAfter=0
            )

            paragraph = Paragraph(
                safe_text,
                style
            )

            _, text_height = paragraph.wrap(
                text_width,
                height
            )

            # Maximum allowed text height
            if text_height <= 42:
                break

        # Convert center position from top
        # into ReportLab bottom-based coordinates
        center_y = height - center_top

        # Center text vertically
        y = center_y - (text_height / 2)

        # Draw the name
        paragraph.drawOn(
            pdf,
            center_x - (text_width / 2),
            y
        )

    # ======================================
    # DRAW PARTICIPANT NAME
    # ======================================

    draw_text(
        text=name,
        center_top=name_center_from_top,
        size=28,
        bold=True,
        color="#14234B"
    )

    # ======================================
    # SAVE CERTIFICATE
    # ======================================

    pdf.showPage()
    pdf.save()

    return output.getvalue()
