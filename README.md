# Certificate Automation — simplified

Upload a CSV with `Name,Email`, then click **Send Emails**. The certificate design and email text are built in. No template upload, column mapping, preview, or separate generation step.

## Setup

1. Install Python dependencies: `pip install -r requirements.txt`
2. Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml`.
3. Fill in your sender Gmail address and a Google App Password (requires 2-Step Verification). Never commit the real secrets file.
4. Run: `streamlit run app.py`
5. Upload a UTF-8 CSV containing `Name` and `Email` headers, then click **Send Emails**.

The app validates all records before sending. It sends one email per participant with their PDF attached. The certificate design can be customized in `make_certificate()` inside `app.py`.

**Important:** Sending emails is irreversible. Test with your own address first. Gmail has sending limits. A failed batch may be partially sent; do not resend the full file without excluding recipients who already received it. Streamlit session state only prevents repeat sends of the same file during the current session, not across restarts.
