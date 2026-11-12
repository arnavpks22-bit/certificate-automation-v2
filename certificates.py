
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.platypus import Paragraph


def create_certificate(
    student,
    template=None,
    background_bytes=None,
    name_x=50,
    name_y=49,
    name_font_size=28,
    name_color="#14234B",
    name_width=65
):
    """
    Generate one personalized certificate PDF.

    Position values are percentages from the top-left.
    name_x and name_y represent the name's center.

    Returns PDF bytes.
    """

    if not isinstance(student, dict):
        raise TypeError("Student must be a dictionary.")

    name = str(student.get("Name", "")).strip()

    if not name:
        raise ValueError("Student name cannot be empty.")

    if not 0 < name_x < 100:
        raise ValueError("Invalid horizontal position.")

    if not 0 < name_y < 100:
        raise ValueError("Invalid vertical position.")

    if not 10 <= name_width <= 100:
        raise ValueError("Invalid name area width.")

    if not 8 <= name_font_size <= 100:
        raise ValueError("Invalid name font size.")

    width = 841.89
    height = 595.28

    output = BytesIO()
    pdf = canvas.Canvas(
        output,
        pagesize=(width, height)
    )

    # Draw uploaded certificate background.
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
            0, 0, width, height,
            fill=1, stroke=0
        )

    center_x = width * name_x / 100
    center_y = height * (1 - name_y / 100)

    text_width = width * name_width / 100
    text_width = min(
        text_width,
        2 * min(center_x, width - center_x)
    )

    if text_width <= 0:
        raise ValueError("Name area is too close to the edge.")

    safe_name = escape(name)
    paragraph = None
    text_height = 0

    # Automatically reduce font size for long names.
    for font_size in range(int(name_font_size), 7, -1):
        style = ParagraphStyle(
            name="CertificateName",
            fontName="Helvetica-Bold",
            fontSize=font_size,
            leading=font_size * 1.15,
            alignment=TA_CENTER,
            textColor=colors.HexColor(name_color),
            spaceBefore=0,
            spaceAfter=0,
            splitLongWords=True
        )

        paragraph = Paragraph(safe_name, style)
        _, text_height = paragraph.wrap(text_width, height)

        if text_height <= 42:
            break

    if text_height > 42:
        raise ValueError(
            "Participant name is too long for the selected area."
        )

    paragraph.drawOn(
        pdf,
        center_x - text_width / 2,
        center_y - text_height / 2
    )

    pdf.showPage()
    pdf.save()

    return output.getvalue()
