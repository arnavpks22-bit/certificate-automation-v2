
from hashlib import sha256
from io import BytesIO
from zipfile import ZipFile, ZIP_DEFLATED
import re
import json

import pandas as pd
import streamlit as st

from certificates import create_certificate
from email_service import send_certificate


# ==========================================
# PAGE CONFIGURATION
# ==========================================

st.set_page_config(
    page_title="Certificate Automation",
    page_icon="🎓",
    layout="wide"
)

st.title("🎓 Certificate Automation")

st.write(
    "Upload student details, generate personalized "
    "certificates, and send congratulatory emails."
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
    """Automatically match spreadsheet columns."""

    normalized = {
        name.strip().casefold()
        for name in names
    }

    for index, column in enumerate(columns, start=1):
        if str(column).strip().casefold() in normalized:
            return index

    return 0


def validate_students(data):
    """Validate names, emails and duplicates."""

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

    # Duplicate email detection
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
    """Create a safe filename."""

    return (
        re.sub(
            r"[^A-Za-z0-9_-]+",
            "_",
            str(value)
        ).strip("_")[:60]
        or "Student"
    )


def render_email(template, student):
    """Replace {{Name}} and {{Email}} placeholders."""

    return re.sub(
        TOKEN_PATTERN,
        lambda match: str(
            student.get(match.group(1).strip(), "")
        ),
        template
    )


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

st.success(f"Loaded {len(students)} student records.")

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
    "Upload Canva certificate image (PNG/JPG)",
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
        st.image(
            background_bytes,
            caption="Certificate Background",
            width=600
        )

    except Exception:

        st.error("Invalid background image.")
        st.stop()

else:

    st.info(
        "No background uploaded. "
        "Certificates will have a plain white background."
    )


# ==========================================
# SESSION STATE SIGNATURE
# ==========================================

signature = sha256(
    file_bytes
    + json.dumps(mapping, sort_keys=True).encode()
    + (background_bytes or b"")
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
# STEP 4: VALIDATE STUDENTS
# ==========================================

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
            "Name": students[mapping["Name"]].astype(str).str.strip(),
            "Email": students[mapping["Email"]].astype(str).str.strip()
        })

        report = validate_students(mapped)

        st.session_state["validation_report"] = report

        st.session_state["validated_data"] = mapped.loc[
            report["Status"].eq("Ready")
        ].copy()

        st.session_state.pop("certificate_records", None)
        st.session_state.pop("sending_results", None)
        st.session_state.pop("sending_signature", None)


if "validation_report" not in st.session_state:
    st.stop()

report = st.session_state["validation_report"]

valid_students = st.session_state["validated_data"]

invalid = report.loc[
    report["Status"].ne("Ready")
]

st.subheader("4. Validation Results")

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
# STEP 5: GENERATE CERTIFICATES
# ==========================================

st.subheader("5. Generate Certificates")

if st.button("Generate Certificates"):

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
                background_bytes=background_bytes
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

        progress.progress(number / len(valid_students))

    st.session_state["certificate_records"] = records
    st.session_state.pop("sending_results", None)
    st.session_state.pop("sending_signature", None)


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
# STEP 6: DOWNLOAD ZIP
# ==========================================

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
# STEP 7: EMAIL TEMPLATE
# ==========================================

st.subheader("6. Personalized Email")

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
    height=300,
    value=(
        "Dear {{Name}},\n\n"
        "Congratulations!\n\n"
        "We sincerely appreciate your participation "
        "and enthusiasm.\n\n"
        "Your dedication and involvement have been "
        "truly valuable, and we are delighted to "
        "recognize your efforts.\n\n"
        "Please find your personalized certificate "
        "attached to this email as a token of "
        "appreciation for your participation.\n\n"
        "Thank you once again for being a part "
        "of this experience. We wish you continued "
        "success in all your future endeavours!\n\n"
        "Best regards,\n"
        "Certificate Automation Team"
    ),
    key="email_body"
)


# ==========================================
# VALIDATE EMAIL TEMPLATE
# ==========================================

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
        "Unknown placeholders: " + ", ".join(unknown)
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
# STEP 8: PREVIEW EMAIL
# ==========================================

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
# STEP 9: EMAIL CONFIGURATION
# ==========================================

st.subheader("7. Send Certificates")

try:

    sender = str(
        st.secrets["email"]["sender"]
    ).strip()

    app_password = str(
        st.secrets["email"]["app_password"]
    ).replace(" ", "")

    email_configured = bool(sender and app_password)

except (FileNotFoundError, KeyError, TypeError):

    email_configured = False
    sender = ""
    app_password = ""


if not email_configured:

    st.warning(
        "Email is not configured. "
        "Add Gmail credentials to .streamlit/secrets.toml."
    )

else:

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

    if st.session_state.get("sending_signature") != email_signature:

        st.session_state.pop("sending_results", None)
        st.session_state["sending_signature"] = email_signature

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

        # Save attempts before sending to reduce
        # accidental duplicate submissions.
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

            st.session_state["sending_results"][index][
                "Status"
            ] = "Attempted — awaiting result"

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

            st.session_state["sending_results"][index][
                "Status"
            ] = status

            progress.progress(
                (index + 1) / len(successful)
            )


# ==========================================
# STEP 10: SENDING REPORT
# ==========================================

if "sending_results" in st.session_state:

    st.subheader("8. Sending Results")

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
