
import smtplib
import ssl
import streamlit as st

sender = str(st.secrets["email"]["sender"]).strip()
password = str(
    st.secrets["email"]["app_password"]
).replace(" ", "")

print("Testing Gmail SMTP on port 587...")

try:
    context = ssl.create_default_context()

    with smtplib.SMTP(
        "smtp.gmail.com",
        587,
        timeout=20
    ) as server:

        print("Connected to Gmail SMTP.")

        server.ehlo()

        print("Starting TLS...")

        server.starttls(context=context)

        print("TLS established.")

        server.ehlo()

        print("Authenticating...")

        server.login(sender, password)

        print("SUCCESS: Gmail authentication worked!")

except Exception as error:
    print("FAILED")
    print("Error type:", type(error).__name__)
    print("Error:", str(error))