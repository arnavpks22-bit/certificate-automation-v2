
from hashlib import sha256
from io import BytesIO
from zipfile import ZipFile, ZIP_DEFLATED
from xml.sax.saxutils import escape
import re
import json

import pandas as pd
import streamlit as st

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.utils import ImageReader

from certificates import create_certificate
from email_service import send_certificate


# ==========================================
# PAGE CONFIGURATION
# ==========================================

st.set_page_config(
    page_title="MiraeTech Certificate Automation",
    page_icon="📜",
    layout="wide"
)

st.title("MiraeTech Certificate Automation")

st.write(
    "Upload participant details, customize name placement, "
    "generate personalized certificates, and send emails."
)


# ==========================================
# CONFIGURATION
# ==========================================

FIELDS = {
    "Name": [
        "Name",
        "Student Name",
        "Participant Name",
        "Full Name"
    ],
    "Email": [
        "Email",
        "Student Email",
        "Email Address",
        "Personal Email"
    ]
}

EMAIL_PATTERN = r"[^@\s]+@[^@\s]+\.[^@\s]+"
TOKEN_PATTERN = r"\{\{\s*([^{}]+?)\s*\}\}"


# ==========================================
# HELPER FUNCTIONS
# ==========================================

def suggest_column(columns, names):
    normalized = {
        name.strip().casefold()
        for name in names
    }

    for index, column in enumerate(columns, start=1):
        if str(column).strip().casefold() in normalized:
            return index

    return 0


def validate_students(data):
    data = data.copy().fillna("").reset_index(drop=True)

    errors = [[] for _ in range(len(data))]

    for field in ["Name", "Email"]:
        data[field] = data[field].astype(str).str.strip()

        for index, value in enumerate(data[field]):
            if not value:
                errors[index].append(f"Missing {field}")

    for index, email in enumerate(data["Email"]):
        if email and not re.fullmatch(EMAIL_PATTERN, email):
            errors[index].append("Invalid email address")

    normalized_emails = data["Email"].str.casefold()

    duplicates = (
        normalized_emails.duplicated(keep=False)
        & normalized_emails.ne("")
    )

    for index, duplicate in enumerate(duplicates):
        if duplicate:
            errors[index].append("Duplicate email address")

    report = data.copy()

    report.insert(
        0,
        "Source Row",
        range(2, len(data) + 2)
    )

    report["Issues"] = [
        "; ".join(items)
        for items in errors
    ]

    report["Status"] = [
        "Needs correction" if items else "Ready"
        for items in errors
    ]

    return report


def safe_filename(value):
    return (
        re.sub(
            r"[^A-Za-z0-9_-]+",
            "_",
            str(value)
        ).strip("_")[:60]
        or "Student"
    )


def render_email(template, student):
    return re.sub(
        TOKEN_PATTERN,
        lambda match: str(
            student.get(match.group(1).strip(), "")
        ),
        template
    )


def create_visual_preview(
    background_bytes,
    sample_name,
    name_x,
    name_y,
    name_font_size,
    name_color,
    name_width
):
    """
    Create a visual certificate preview using Pillow.

    The generated PDF remains the final reference.
    """

    if background_bytes:
        image = Image.open(
            BytesIO(background_bytes)
        ).convert("RGB")
    else:
        image = Image.new(
            "RGB",
            (1200, 849),
            "white"
        )

    # Limit preview dimensions for performance.
    image.thumbnail((1400, 1400))

    image = image.copy()
    draw = ImageDraw.Draw(image)

    width, height = image.size

    center_x = width * name_x / 100
    center_y = height * name_y / 100

    text_area_width = width * name_width / 100

    text_area_width = min(
        text_area_width,
        2 * min(center_x, width - center_x)
    )

    # Scale PDF font size to preview pixels.
    scale = width / 841.89

    font_size = max(
        8,
        int(name_font_size * scale)
    )

    font_paths = [
        "C:/Windows/Fonts/arialbd.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf"
    ]

    def load_font(size):
        for path in font_paths:
            try:
                return ImageFont.truetype(
                    path,
                    size
                )
            except OSError:
                continue

        return ImageFont.load_default()

    # Fit the name inside the selected area.
    font = load_font(font_size)

    for size in range(font_size, 7, -1):
        font = load_font(size)

        bbox = draw.textbbox(
            (0, 0),
            sample_name,
            font=font
        )

        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]

        if (
            text_width <= text_area_width
            and text_height <= 42 * scale
        ):
            break

    # Draw selected name area.
    left = center_x - text_area_width / 2
    right = center_x + text_area_width / 2

    draw.rectangle(
        [
            left,
            center_y - 25 * scale,
            right,
            center_y + 25 * scale
        ],
        outline="#B7A06B",
        width=2
    )

    # Draw name centered at selected position.
    draw.text(
        (center_x, center_y),
        sample_name,
        font=font,
        fill=name_color,
        anchor="mm"
    )

    return image


# ==========================================
# STEP 1: UPLOAD SPREADSHEET
# ==========================================

st.subheader("1. Upload Student Details")

uploaded = st.file_uploader(
    "Upload Excel or CSV",
    type=["xlsx", "csv"]
)

if uploaded is None:
    st.stop()

file_bytes = uploaded.getvalue()
file_key = sha256(file_bytes).hexdigest()

try:
    if uploaded.name.lower().endswith(".csv"):
        students = pd.read_csv(
            BytesIO(file_bytes),
            dtype=str,
            keep_default_na=False
        )
    else:
        students = pd.read_excel(
            BytesIO(file_bytes),
            dtype=str,
            keep_default_na=False
        )

    students = students.fillna("").reset_index(drop=True)

except Exception as error:
    st.error(f"Unable to read spreadsheet: {error}")
    st.stop()

if students.empty:
    st.warning("No student records found.")
    st.stop()

st.success(
    f"Loaded {len(students)} student records."
)

preview = students.copy()

preview.insert(
    0,
    "S.No.",
    range(1, len(preview) + 1)
)

st.dataframe(
    preview,
    hide_index=True,
    use_container_width=True
)


# ==========================================
# STEP 2: COLUMN MAPPING
# ==========================================

st.subheader("2. Match Columns")

columns = list(students.columns)
options = [None] + columns
mapping = {}

for field, aliases in FIELDS.items():
    mapping[field] = st.selectbox(
        f"{field} *",
        options,
        index=suggest_column(columns, aliases),
        format_func=lambda value: (
            "Not selected"
            if value is None
            else str(value)
        ),
        key=f"{file_key}_mapping_{field}"
    )


# ==========================================
# STEP 3: CERTIFICATE BACKGROUND
# ==========================================

st.subheader("3. Certificate Background")

background_file = st.file_uploader(
    "Upload Certificate Template (PNG/JPG)",
    type=["png", "jpg", "jpeg"],
    key="certificate_background"
)

background_bytes = (
    background_file.getvalue()
    if background_file is not None
    else None
)

if background_bytes:
    try:
        Image.open(
            BytesIO(background_bytes)
        ).verify()
    except Exception:
        st.error("Invalid certificate background image.")
        st.stop()
else:
    st.info(
        "No template uploaded. "
        "A plain white background will be used."
    )


# ==========================================
# STEP 4: CERTIFICATE NAME EDITOR
# ==========================================

st.subheader("4. Customize Certificate Name")

st.write(
    "Adjust the name position to match your "
    "certificate template."
)

sample_name = st.text_input(
    "Sample Participant Name",
    value="Sample Participant",
    key="sample_certificate_name"
)

left_col, right_col = st.columns(2)

with left_col:
    name_x = st.slider(
        "Horizontal Position (%)",
        min_value=5,
        max_value=95,
        value=50,
        step=1,
        key="name_x"
    )

    name_y = st.slider(
        "Vertical Position (%)",
        min_value=5,
        max_value=95,
        value=49,
        step=1,
        key="name_y"
    )

with right_col:
    name_font_size = st.slider(
        "Name Font Size",
        min_value=12,
        max_value=60,
        value=28,
        step=1,
        key="name_font_size"
    )

    name_width = st.slider(
        "Name Area Width (%)",
        min_value=20,
        max_value=90,
        value=65,
        step=1,
        key="name_width"
    )

name_color = st.color_picker(
    "Name Font Color",
    value="#14234B",
    key="name_color"
)

st.caption(
    "The selected coordinates represent the center "
    "of the participant's name."
)

try:
    visual_preview = create_visual_preview(
        background_bytes=background_bytes,
        sample_name=sample_name or "Sample Participant",
        name_x=name_x,
        name_y=name_y,
        name_font_size=name_font_size,
        name_color=name_color,
        name_width=name_width
    )

    st.image(
        visual_preview,
        caption="Live Name Placement Preview",
        use_container_width=True
    )

except Exception as error:
    st.error(f"Unable to create preview: {error}")
    st.stop()


# ==========================================
# EXACT PDF PREVIEW
# ==========================================

st.write("**Check the actual generated PDF**")

try:
    sample_pdf = create_certificate(
        {
            "Name": sample_name or "Sample Participant",
            "Email": "preview@example.com"
        },
        background_bytes=background_bytes,
        name_x=name_x,
        name_y=name_y,
        name_font_size=name_font_size,
        name_color=name_color,
        name_width=name_width
    )

    st.download_button(
        "Download Sample Certificate PDF",
        data=sample_pdf,
        file_name="sample_certificate.pdf",
        mime="application/pdf"
    )

except Exception as error:
    st.error(f"PDF preview error: {error}")
    st.stop()


# ==========================================
# SESSION SIGNATURE
# ==========================================

placement_settings = {
    "name_x": name_x,
    "name_y": name_y,
    "name_font_size": name_font_size,
    "name_color": name_color,
    "name_width": name_width
}

signature = sha256(
    file_bytes
    + json.dumps(
        mapping,
        sort_keys=True
    ).encode()
    + (background_bytes or b"")
    + json.dumps(
        placement_settings,
        sort_keys=True
    ).encode()
).hexdigest()

if st.session_state.get("batch_signature") != signature:
    st.session_state["batch_signature"] = signature

    for key in [
        "validation_report",
        "validated_data",
        "certificate_records",
        "sending_results",
        "sending_signature"
    ]:
        st.session_state.pop(key, None)


# ==========================================
# STEP 5: VALIDATE STUDENTS
# ==========================================

st.subheader("5. Validate Student Data")

if st.button(
    "Validate Student Data",
    type="primary"
):
    if mapping["Name"] is None or mapping["Email"] is None:
        st.error(
            "Please select both Name and Email columns."
        )

    elif mapping["Name"] == mapping["Email"]:
        st.error(
            "Name and Email must use different columns."
        )

    else:
        mapped = pd.DataFrame({
            "Name": students[
                mapping["Name"]
            ].astype(str).str.strip(),

            "Email": students[
                mapping["Email"]
            ].astype(str).str.strip()
        })

        report = validate_students(mapped)

        st.session_state["validation_report"] = report

        st.session_state["validated_data"] = mapped.loc[
            report["Status"].eq("Ready")
        ].copy()

        st.session_state.pop(
            "certificate_records",
            None
        )

        st.session_state.pop(
            "sending_results",
            None
        )

        st.session_state.pop(
            "sending_signature",
            None
        )

if "validation_report" not in st.session_state:
    st.stop()

report = st.session_state["validation_report"]
valid_students = st.session_state["validated_data"]

invalid = report.loc[
    report["Status"].ne("Ready")
]

col1, col2 = st.columns(2)

col1.metric(
    "Valid Students",
    len(valid_students)
)

col2.metric(
    "Records With Errors",
    len(invalid)
)

st.dataframe(
    report,
    hide_index=True,
    use_container_width=True
)

if not invalid.empty:
    st.warning(
        "Some records have errors. "
        "Correct them in the spreadsheet and upload again."
    )

    st.download_button(
        "Download Error Report",
        data=invalid.to_csv(
            index=False
        ).encode("utf-8-sig"),
        file_name="validation_errors.csv",
        mime="text/csv"
    )

if valid_students.empty:
    st.stop()


# ==========================================
# STEP 6: GENERATE CERTIFICATES
# ==========================================

st.subheader("6. Generate Certificates")

if st.button(
    "Generate Certificates",
    type="primary"
):
    records = []
    progress = st.progress(0)

    for number, (source_index, row) in enumerate(
        valid_students.iterrows(),
        start=1
    ):
        student = row.to_dict()

        filename = (
            f"{number:04d}_"
            f"{safe_filename(student['Name'])}.pdf"
        )

        try:
            pdf = create_certificate(
                student,
                background_bytes=background_bytes,
                name_x=name_x,
                name_y=name_y,
                name_font_size=name_font_size,
                name_color=name_color,
                name_width=name_width
            )

            records.append({
                "student": student,
                "filename": filename,
                "pdf": pdf,
                "source_row": int(source_index) + 2,
                "error": ""
            })

        except Exception as error:
            records.append({
                "student": student,
                "filename": filename,
                "pdf": None,
                "source_row": int(source_index) + 2,
                "error": str(error)
            })

        progress.progress(
            number / len(valid_students)
        )

    st.session_state["certificate_records"] = records

    st.session_state.pop(
        "sending_results",
        None
    )

    st.session_state.pop(
        "sending_signature",
        None
    )


records = st.session_state.get(
    "certificate_records",
    []
)

successful = [
    record
    for record in records
    if record["pdf"] is not None
]

failed = [
    record
    for record in records
    if record["pdf"] is None
]

if failed:
    st.error(
        f"{len(failed)} certificates failed to generate."
    )

    st.dataframe(
        pd.DataFrame([
            {
                "Row": record["source_row"],
                "Name": record["student"]["Name"],
                "Error": record["error"]
            }
            for record in failed
        ]),
        hide_index=True
    )

if not successful:
    st.stop()

st.success(
    f"{len(successful)} certificates generated!"
)


# ==========================================
# STEP 7: DOWNLOAD ZIP
# ==========================================

st.subheader("7. Download Certificates")

zip_buffer = BytesIO()

with ZipFile(
    zip_buffer,
    "w",
    compression=ZIP_DEFLATED
) as archive:
    for record in successful:
        archive.writestr(
            record["filename"],
            record["pdf"]
        )

st.download_button(
    f"Download All {len(successful)} Certificates",
    data=zip_buffer.getvalue(),
    file_name="certificates.zip",
    mime="application/zip"
)


# ==========================================
# STEP 8: PERSONALIZED EMAIL
# ==========================================

st.subheader("8. Personalized Email")

st.caption(
    "Supported placeholders: {{Name}}, {{Email}}"
)

subject_template = st.text_input(
    "Email Subject",
    value="Congratulations on Your Participation!",
    key="email_subject"
)

body_template = st.text_area(
    "Email Message",
    height=250,
    value=(
        "Dear {{Name}},\n\n"
        "Congratulations!\n\n"
        "Your personalized Certificate of Achievement "
        "is attached as a PDF.\n\n"
        "Thank you for participating in our event.\n\n"
        "Best regards,\n"
        "Organizing Team"
    ),
    key="email_body"
)

unknown = sorted({
    token.strip()
    for token in re.findall(
        TOKEN_PATTERN,
        subject_template + "\n" + body_template
    )
    if token.strip() not in FIELDS
})

if unknown:
    st.error(
        "Unknown placeholders: "
        + ", ".join(unknown)
    )
    st.stop()

if not subject_template.strip() or not body_template.strip():
    st.warning(
        "Email subject and message cannot be empty."
    )
    st.stop()

if "\n" in subject_template or "\r" in subject_template:
    st.error(
        "Email subject must be a single line."
    )
    st.stop()


# ==========================================
# STEP 9: EMAIL PREVIEW
# ==========================================

st.subheader("9. Preview Email")

selected_index = st.selectbox(
    "Select Student to Preview",
    range(len(successful)),
    format_func=lambda index: (
        f"{successful[index]['student']['Name']} "
        f"({successful[index]['student']['Email']})"
    ),
    key=f"preview_{signature}"
)

record = successful[selected_index]

st.write(
    "**To:**",
    record["student"]["Email"]
)

st.write(
    "**Subject:**",
    render_email(
        subject_template,
        record["student"]
    )
)

st.text(
    render_email(
        body_template,
        record["student"]
    )
)

st.write(
    "**Attachment:**",
    record["filename"]
)

st.download_button(
    "Download Preview Certificate",
    data=record["pdf"],
    file_name=record["filename"],
    mime="application/pdf"
)


# ==========================================
# STEP 10: SENDER EMAIL CONFIGURATION
# ==========================================

st.subheader("10. Send Certificates")

st.write("**Sender Email Configuration**")

sender = st.text_input(
    "Sender Gmail Address",
    placeholder="example@gmail.com",
    key="sender_email"
).strip()

app_password = st.text_input(
    "Gmail App Password",
    type="password",
    placeholder="Enter your 16-character App Password",
    key="sender_app_password"
).replace(" ", "")

st.caption(
    "Use a Google App Password, "
    "not your regular Gmail password."
)

email_configured = bool(
    sender
    and re.fullmatch(EMAIL_PATTERN, sender)
    and len(app_password) == 16
)

if not sender or not app_password:
    st.warning(
        "Enter your Gmail address and App Password "
        "before sending certificates."
    )

elif not re.fullmatch(EMAIL_PATTERN, sender):
    st.error("Enter a valid sender email address.")

elif len(app_password) != 16:
    st.error(
        "Gmail App Password must contain 16 characters."
    )

else:
    st.success(
        "Credentials entered. Ready to attempt sending."
    )


# ==========================================
# SEND CERTIFICATES
# ==========================================

if email_configured:
    st.write("**Sender:**", sender)

    recipients = pd.DataFrame([
        {
            "Name": item["student"]["Name"],
            "Email": item["student"]["Email"],
            "Certificate": item["filename"]
        }
        for item in successful
    ])

    st.dataframe(
        recipients,
        hide_index=True,
        use_container_width=True
    )

    email_signature = sha256(
        (
            signature
            + subject_template
            + body_template
            + sender
        ).encode("utf-8")
    ).hexdigest()

    if (
        st.session_state.get("sending_signature")
        != email_signature
    ):
        st.session_state.pop(
            "sending_results",
            None
        )

        st.session_state[
            "sending_signature"
        ] = email_signature

    already_submitted = (
        "sending_results" in st.session_state
    )

    if already_submitted:
        st.warning(
            "This batch has already been submitted "
            "during this session. Check Gmail Sent "
            "before sending again."
        )

    confirmed = st.checkbox(
        "I have verified the recipients and "
        "authorize sending these certificates."
    )

    if st.button(
        "Send Certificates",
        type="primary",
        disabled=not confirmed or already_submitted
    ):
        progress = st.progress(0)

        st.session_state["sending_results"] = [
            {
                "Name": item["student"]["Name"],
                "Email": item["student"]["Email"],
                "Status": "Not yet attempted"
            }
            for item in successful
        ]

        for index, item in enumerate(successful):
            student = item["student"]

            st.session_state[
                "sending_results"
            ][index]["Status"] = (
                "Attempted — awaiting result"
            )

            try:
                send_certificate(
                    sender=sender,
                    app_password=app_password,
                    recipient=student["Email"],
                    subject=render_email(
                        subject_template,
                        student
                    ),
                    body=render_email(
                        body_template,
                        student
                    ),
                    certificate_pdf=item["pdf"],
                    filename=item["filename"]
                )

                status = "Accepted by Gmail"

            except Exception as error:
                status = (
                    "Not confirmed — check Gmail Sent "
                    "before retrying"
                )

                st.warning(
                    f"Sending status uncertain for "
                    f"{student['Email']}: {error}"
                )

            st.session_state[
                "sending_results"
            ][index]["Status"] = status

            progress.progress(
                (index + 1) / len(successful)
            )


# ==========================================
# STEP 11: SENDING REPORT
# ==========================================

if "sending_results" in st.session_state:
    st.subheader("11. Sending Results")

    results_table = pd.DataFrame(
        st.session_state["sending_results"]
    )

    st.dataframe(
        results_table,
        hide_index=True,
        use_container_width=True
    )

    st.download_button(
        "Download Sending Report",
        data=results_table.to_csv(
            index=False
        ).encode("utf-8-sig"),
        file_name="sending_report.csv",
        mime="text/csv"
    )

    st.info(
        "Gmail acceptance does not guarantee inbox "
        "delivery. Check Gmail Sent before retrying "
        "any uncertain deliveries."
    )
