
from hashlib import sha256
from io import BytesIO
from zipfile import ZipFile, ZIP_DEFLATED
import json
import re

import pandas as pd
import streamlit as st
from PIL import Image, ImageDraw, ImageFont

from certificates import create_certificate, FONT_OPTIONS
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
    "Generate one or two personalized certificates "
    "per participant and send them in a single email."
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
        if email and not re.fullmatch(
            EMAIL_PATTERN,
            email
        ):
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
        or "Participant"
    )


def render_email(template, student):
    return re.sub(
        TOKEN_PATTERN,
        lambda match: str(
            student.get(match.group(1).strip(), "")
        ),
        template
    )


# ==========================================
# PREVIEW FONT HANDLING
# ==========================================

def load_preview_font(font_name, size):
    """
    Find an approximate matching font for Pillow.

    PDF generation uses the selected ReportLab font.
    """

    font_files = {
        "Helvetica": [
            "C:/Windows/Fonts/arial.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"
        ],
        "Helvetica-Bold": [
            "C:/Windows/Fonts/arialbd.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf"
        ],
        "Helvetica-Oblique": [
            "C:/Windows/Fonts/ariali.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Italic.ttf"
        ],
        "Times-Roman": [
            "C:/Windows/Fonts/times.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSerif-Regular.ttf"
        ],
        "Times-Bold": [
            "C:/Windows/Fonts/timesbd.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSerif-Bold.ttf"
        ],
        "Times-Italic": [
            "C:/Windows/Fonts/timesi.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSerif-Italic.ttf"
        ],
        "Courier": [
            "C:/Windows/Fonts/cour.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationMono-Regular.ttf"
        ],
        "Courier-Bold": [
            "C:/Windows/Fonts/courbd.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationMono-Bold.ttf"
        ],
        "Courier-Oblique": [
            "C:/Windows/Fonts/couri.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationMono-Italic.ttf"
        ]
    }

    paths = font_files.get(font_name, [])

    for path in paths:
        try:
            return ImageFont.truetype(
                path,
                max(8, int(size))
            )
        except OSError:
            continue

    return ImageFont.load_default()


# ==========================================
# VISUAL PREVIEW
# ==========================================

def make_preview(
    background_bytes,
    sample_name,
    settings
):
    """
    Create an approximate image preview.

    Download the sample PDF for exact output.
    """

    image = Image.open(
        BytesIO(background_bytes)
    ).convert("RGB")

    image.thumbnail((1400, 1400))
    image = image.copy()

    draw = ImageDraw.Draw(image)

    width, height = image.size

    center_x = width * settings["name_x"] / 100
    center_y = height * settings["name_y"] / 100

    area_width = width * settings["name_width"] / 100

    area_width = min(
        area_width,
        2 * min(center_x, width - center_x)
    )

    scale = width / 841.89

    initial_size = max(
        8,
        int(settings["name_font_size"] * scale)
    )

    font = load_preview_font(
        settings["name_font"],
        initial_size
    )

    # Reduce preview font size for long names.
    for size in range(initial_size, 7, -1):

        font = load_preview_font(
            settings["name_font"],
            size
        )

        bbox = draw.textbbox(
            (0, 0),
            sample_name,
            font=font
        )

        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]

        if (
            text_width <= area_width
            and text_height <= 42 * scale
        ):
            break

    # Show the selected name area.
    draw.rectangle(
        [
            center_x - area_width / 2,
            center_y - 25 * scale,
            center_x + area_width / 2,
            center_y + 25 * scale
        ],
        outline="#B7A06B",
        width=2
    )

    draw.text(
        (center_x, center_y),
        sample_name,
        font=font,
        fill=settings["name_color"],
        anchor="mm"
    )

    return image


# ==========================================
# CERTIFICATE TEMPLATE EDITOR
# ==========================================

def template_editor(number):
    """
    Configure one certificate template.

    Returns:
        background_bytes, settings
    """

    st.markdown(f"#### Certificate {number}")

    background_file = st.file_uploader(
        f"Upload Certificate {number} Template",
        type=["png", "jpg", "jpeg"],
        key=f"background_{number}"
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
            st.error(
                f"Invalid Certificate {number} template."
            )
            st.stop()

    else:
        st.info(
            f"Upload a PNG/JPG template for Certificate {number}."
        )

    sample_name = st.text_input(
        f"Sample Name - Certificate {number}",
        value="Sample Participant",
        key=f"sample_name_{number}"
    )

    left, right = st.columns(2)

    with left:
        name_x = st.slider(
            f"Horizontal Position - Certificate {number} (%)",
            min_value=5,
            max_value=95,
            value=50,
            key=f"name_x_{number}"
        )

        name_y = st.slider(
            f"Vertical Position - Certificate {number} (%)",
            min_value=5,
            max_value=95,
            value=49,
            key=f"name_y_{number}"
        )

    with right:
        name_font_size = st.slider(
            f"Font Size - Certificate {number}",
            min_value=12,
            max_value=60,
            value=28,
            key=f"font_size_{number}"
        )

        name_width = st.slider(
            f"Name Area Width - Certificate {number} (%)",
            min_value=20,
            max_value=90,
            value=65,
            key=f"name_width_{number}"
        )

    name_font = st.selectbox(
        f"Font Family - Certificate {number}",
        options=FONT_OPTIONS,
        index=1,
        key=f"name_font_{number}"
    )

    name_color = st.color_picker(
        f"Font Color - Certificate {number}",
        value="#14234B",
        key=f"name_color_{number}"
    )

    settings = {
        "name_x": name_x,
        "name_y": name_y,
        "name_font_size": name_font_size,
        "name_width": name_width,
        "name_color": name_color,
        "name_font": name_font
    }

    if background_bytes:

        try:
            preview = make_preview(
                background_bytes,
                sample_name or "Sample Participant",
                settings
            )

            st.image(
                preview,
                caption=(
                    f"Certificate {number} "
                    "Name Placement Preview"
                ),
                use_container_width=True
            )

            sample_pdf = create_certificate(
                {
                    "Name": sample_name or "Sample Participant",
                    "Email": "preview@example.com"
                },
                background_bytes=background_bytes,
                **settings
            )

            st.download_button(
                f"Download Certificate {number} Sample PDF",
                data=sample_pdf,
                file_name=f"certificate_{number}_sample.pdf",
                mime="application/pdf",
                key=f"sample_pdf_{number}"
            )

        except Exception as error:
            st.error(
                f"Certificate {number} preview error: {error}"
            )

    return background_bytes, settings


# ==========================================
# STEP 1: UPLOAD SPREADSHEET
# ==========================================

st.subheader("1. Upload Participant Details")

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
    st.error(
        f"Unable to read spreadsheet: {error}"
    )
    st.stop()

if students.empty:
    st.warning("No participant records found.")
    st.stop()

st.success(
    f"Loaded {len(students)} participant records."
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
# STEP 2: MATCH COLUMNS
# ==========================================

st.subheader("2. Match Columns")

columns = list(students.columns)
options = [None] + columns

mapping = {}

for field, aliases in FIELDS.items():

    mapping[field] = st.selectbox(
        f"{field} *",
        options,
        index=suggest_column(
            columns,
            aliases
        ),
        format_func=lambda value: (
            "Not selected"
            if value is None
            else str(value)
        ),
        key=f"{file_key}_mapping_{field}"
    )


# ==========================================
# STEP 3: SELECT CERTIFICATE COUNT
# ==========================================

st.subheader("3. Certificate Configuration")

certificate_count = st.radio(
    "How many certificates per participant?",
    options=[1, 2],
    index=0,
    horizontal=True,
    key="certificate_count"
)

st.info(
    f"Each participant will receive "
    f"{certificate_count} certificate(s) "
    "in one email."
)


# ==========================================
# STEP 4: CUSTOMIZE TEMPLATES
# ==========================================

st.subheader("4. Customize Certificate Templates")

templates = []

if certificate_count == 1:

    background_1, settings_1 = template_editor(1)

    templates.append({
        "number": 1,
        "background": background_1,
        "settings": settings_1
    })

else:

    tab1, tab2 = st.tabs([
        "Certificate 1",
        "Certificate 2"
    ])

    with tab1:
        background_1, settings_1 = template_editor(1)

    with tab2:
        background_2, settings_2 = template_editor(2)

    templates.extend([
        {
            "number": 1,
            "background": background_1,
            "settings": settings_1
        },
        {
            "number": 2,
            "background": background_2,
            "settings": settings_2
        }
    ])


# Require all selected templates.
missing_templates = [
    item["number"]
    for item in templates
    if not item["background"]
]

if missing_templates:
    st.warning(
        "Upload all selected certificate templates "
        "before continuing."
    )
    st.stop()


# ==========================================
# BATCH SIGNATURE
# ==========================================

configuration = {
    "certificate_count": certificate_count,
    "templates": [
        {
            "number": item["number"],
            "settings": item["settings"],
            "background_hash": sha256(
                item["background"]
            ).hexdigest()
        }
        for item in templates
    ]
}

signature = sha256(
    file_bytes
    + json.dumps(
        mapping,
        sort_keys=True
    ).encode()
    + json.dumps(
        configuration,
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
# STEP 5: VALIDATE PARTICIPANTS
# ==========================================

st.subheader("5. Validate Participant Data")

if st.button(
    "Validate Participant Data",
    type="primary"
):

    if (
        mapping["Name"] is None
        or mapping["Email"] is None
    ):
        st.error(
            "Please select Name and Email columns."
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

        for key in [
            "certificate_records",
            "sending_results",
            "sending_signature"
        ]:
            st.session_state.pop(key, None)


if "validation_report" not in st.session_state:
    st.stop()

report = st.session_state["validation_report"]
valid_students = st.session_state["validated_data"]

invalid = report.loc[
    report["Status"].ne("Ready")
]

col1, col2 = st.columns(2)

col1.metric(
    "Valid Participants",
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
        "Correct the spreadsheet and upload it again."
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

total_expected = (
    len(valid_students) * certificate_count
)

st.info(
    f"{len(valid_students)} participants × "
    f"{certificate_count} certificate(s) = "
    f"{total_expected} PDF files."
)

if st.button(
    "Generate All Certificates",
    type="primary"
):

    records = []
    progress = st.progress(0)

    for number, (source_index, row) in enumerate(
        valid_students.iterrows(),
        start=1
    ):

        student = row.to_dict()

        attachments = []
        error_message = ""

        try:

            for item in templates:

                pdf_bytes = create_certificate(
                    student,
                    background_bytes=item["background"],
                    **item["settings"]
                )

                base_name = safe_filename(
                    student["Name"]
                )

                filename = (
                    f"{number:04d}_"
                    f"{base_name}_"
                    f"Certificate_{item['number']}.pdf"
                )

                attachments.append(
                    (filename, pdf_bytes)
                )

        except Exception as error:

            error_message = str(error)

            # Do not send incomplete certificate sets.
            attachments = []

        records.append({
            "student": student,
            "attachments": attachments,
            "source_row": int(source_index) + 2,
            "error": error_message
        })

        progress.progress(
            number / len(valid_students)
        )

    st.session_state["certificate_records"] = records

    for key in [
        "sending_results",
        "sending_signature"
    ]:
        st.session_state.pop(key, None)


records = st.session_state.get(
    "certificate_records",
    []
)

successful = [
    record
    for record in records
    if len(record["attachments"]) == certificate_count
]

failed = [
    record
    for record in records
    if len(record["attachments"]) != certificate_count
]

if failed:

    st.error(
        f"Certificate generation failed for "
        f"{len(failed)} participants."
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
        hide_index=True,
        use_container_width=True
    )

if not successful:
    st.stop()

total_generated = (
    len(successful) * certificate_count
)

st.success(
    f"Successfully generated {total_generated} "
    f"certificates for {len(successful)} participants."
)


# ==========================================
# STEP 7: DOWNLOAD CERTIFICATES
# ==========================================

st.subheader("7. Download Certificates")

zip_buffer = BytesIO()

with ZipFile(
    zip_buffer,
    "w",
    compression=ZIP_DEFLATED
) as archive:

    for record in successful:

        for filename, pdf_bytes in record["attachments"]:

            archive.writestr(
                filename,
                pdf_bytes
            )

st.download_button(
    f"Download All {total_generated} Certificates",
    data=zip_buffer.getvalue(),
    file_name="miraetech_certificates.zip",
    mime="application/zip"
)


# ==========================================
# STEP 8: PERSONALIZED EMAIL
# ==========================================

st.subheader("8. Personalized Email")

st.caption(
    "Available placeholders: {{Name}}, {{Email}}"
)

subject_template = st.text_input(
    "Email Subject",
    value="Your Certificate(s) of Achievement",
    key="email_subject"
)

body_template = st.text_area(
    "Email Message",
    height=250,
    value=(
        "Dear {{Name}},\n\n"
        "Congratulations!\n\n"
        "Please find your personalized certificate(s) "
        "attached to this email.\n\n"
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

if (
    not subject_template.strip()
    or not body_template.strip()
):
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
# STEP 9: PREVIEW EMAIL
# ==========================================

st.subheader("9. Preview Email and Attachments")

selected_index = st.selectbox(
    "Select Participant",
    range(len(successful)),
    format_func=lambda index: (
        f"{successful[index]['student']['Name']} "
        f"({successful[index]['student']['Email']})"
    ),
    key=f"preview_{signature}"
)

record = successful[selected_index]
student = record["student"]

st.write(
    "**To:**",
    student["Email"]
)

st.write(
    "**Subject:**",
    render_email(
        subject_template,
        student
    )
)

st.text(
    render_email(
        body_template,
        student
    )
)

st.write(
    f"**Attachments:** {certificate_count} PDF file(s)"
)

for attachment_number, (filename, pdf_bytes) in enumerate(
    record["attachments"],
    start=1
):

    st.download_button(
        f"Download Preview - Certificate {attachment_number}",
        data=pdf_bytes,
        file_name=filename,
        mime="application/pdf",
        key=(
            f"preview_pdf_"
            f"{attachment_number}_{signature}"
        )
    )


# ==========================================
# STEP 10: GMAIL CONFIGURATION
# ==========================================

st.subheader("10. Send Certificates")

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
    and re.fullmatch(
        EMAIL_PATTERN,
        sender
    )
    and len(app_password) == 16
)

if not sender or not app_password:

    st.warning(
        "Enter your Gmail address and App Password."
    )

elif not re.fullmatch(EMAIL_PATTERN, sender):

    st.error(
        "Enter a valid sender email address."
    )

elif len(app_password) != 16:

    st.error(
        "Gmail App Password must contain 16 characters."
    )

else:

    st.success(
        "Credentials entered. Ready to attempt sending."
    )


# ==========================================
# STEP 11: SEND CERTIFICATES
# ==========================================

if email_configured:

    recipients = pd.DataFrame([
        {
            "Name": item["student"]["Name"],
            "Email": item["student"]["Email"],
            "Attachments": certificate_count
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

        st.session_state["sending_signature"] = (
            email_signature
        )

    already_submitted = (
        "sending_results" in st.session_state
    )

    if already_submitted:

        st.warning(
            "This batch has already been submitted "
            "during this session. Check Gmail Sent "
            "before retrying."
        )

    confirmed = st.checkbox(
        "I have verified the recipients and "
        "certificate attachments, and authorize sending."
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
                "Attachments": certificate_count,
                "Status": "Not yet attempted"
            }
            for item in successful
        ]

        for index, item in enumerate(successful):

            student = item["student"]

            st.session_state[
                "sending_results"
            ][index]["Status"] = (
                "Attempted - awaiting result"
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
                    attachments=item["attachments"]
                )

                status = "Accepted by Gmail"

            except Exception as error:

                status = (
                    "Not confirmed - check Gmail Sent "
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
# STEP 12: SENDING REPORT
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
        "uncertain deliveries."
    )
