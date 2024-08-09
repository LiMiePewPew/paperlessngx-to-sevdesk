import glob
import json
import os
import signal
import string
import time
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import requests
from requests import Response

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class Config:
    paperlessngx_url: str = None
    paperlessngx_token: str = None
    paperlessngx_filter_tag_id: str = None
    paperlessngx_filter_document_type_id: str = None
    sevdesk_token: str = None
    from_email: str = None
    to_email: str = None
    subject: str = None
    body: str = None
    smtp_server: str = None
    smtp_port: int = None
    login: str = None
    password: str = None
    run_interval: int = None

    def is_valid(self):
        required_fields = [
            self.paperlessngx_url, self.paperlessngx_token, self.sevdesk_token,
            self.from_email, self.to_email, self.smtp_server, self.smtp_port,
            self.login, self.password
        ]
        return all(required_fields)


sevdesk_url: Final[str] = "https://my.sevdesk.de/api/v1"
last_downloaded_document_id: int = 0

try:
    config = Config(
        paperlessngx_url=os.getenv('PAPERLESSNGX_URL') or "",
        paperlessngx_token=os.getenv('PAPERLESSNGX_TOKEN') or "",
        paperlessngx_filter_tag_id=os.getenv('PAPERLESSNGX_FILTER_TAG_ID') or 0,
        paperlessngx_filter_document_type_id=os.getenv('PAPERLESSNGX_FILTER_DOCUMENT_TYPE_ID') or 0,
        from_email=os.getenv('EMAIL_ACCOUNT') or "",
        to_email="autobox@sevdesk.email",
        subject="Invoice",
        body="Invoice",
        smtp_server=os.getenv('SMTP_SERVER') or "",
        smtp_port=int(os.getenv('SMTP_PORT')) or 0,
        login=os.getenv('LOGIN') or "",
        password=os.getenv('PASSWORD') or "",
        run_interval=int(os.getenv('RUN_INTERVAL')) or 300,
    )
except ValueError as e:
    logger.error(f"Error parsing environment variables: {e}")
    exit(1)


def paperlessngx_get(path: str) -> Response:
    try:
        response = requests.get(
            config.paperlessngx_url + path,
            allow_redirects=False,
            headers={"Authorization": "Token " + config.paperlessngx_token}
        )
        response.raise_for_status()
        return response
    except requests.RequestException as e:
        logger.error(f"Error fetching from Paperless NGX: {e}")
        return None


def paperlessngx_lookup_new_documents():
    global last_downloaded_document_id

    lookup_url = ("/api/documents/?query=added:%5B-1%20week%20to%20now%5D" +
                  "&sort=created" +
                  "&reverse=1")

    if config.paperlessngx_filter_tag_id:
        lookup_url += "&tags__id__all=" + config.paperlessngx_filter_tag_id

    if config.paperlessngx_filter_document_type_id:
        lookup_url += "&document_type__id__in=" + config.paperlessngx_filter_document_type_id

    response = paperlessngx_get(lookup_url)
    if not response:
        return

    data = json.loads(response.content)
    new_document_ids = sorted(data['all'])
    if last_downloaded_document_id == 0:
        if new_document_ids:
            last_downloaded_document_id = new_document_ids[-1]
        return

    for current_document_id in new_document_ids:
        if current_document_id <= last_downloaded_document_id:
            continue

        logger.info(f"Downloading {current_document_id}")
        response = paperlessngx_get(f"/api/documents/{current_document_id}/download/")
        if response:
            file = Path(f"workdir/{current_document_id}.pdf")
            file.parent.mkdir(parents=True, exist_ok=True)  # Ensure directory exists
            file.write_bytes(response.content)
            last_downloaded_document_id = current_document_id


def send_workdir_to_sevdesk():
    for file in glob.glob("workdir/*.pdf"):
        logger.info(f"Uploading {file}")
        if send_email_with_attachment(file):
            os.unlink(file)
        else:
            logger.error(f"Failed to upload {file}")


def send_email_with_attachment(attachment_path):
    msg = MIMEMultipart()
    msg['From'] = config.from_email
    msg['To'] = config.to_email
    msg['Subject'] = config.subject

    msg.attach(MIMEText(config.body, 'plain'))

    try:
        with open(attachment_path, "rb") as attachment:
            part = MIMEBase('application', 'octet-stream')
            part.set_payload(attachment.read())
            encoders.encode_base64(part)
            part.add_header('Content-Disposition', f'attachment; filename={os.path.basename(attachment_path)}')
            msg.attach(part)
    except Exception as e:
        logger.error(f"Failed to attach file: {e}")
        return False

    try:
        server = smtplib.SMTP(config.smtp_server, config.smtp_port)
        server.starttls()
        server.login(config.login, config.password)
        server.sendmail(config.from_email, config.to_email, msg.as_string())
        server.quit()
        logger.info("Email sent successfully!")
        return True
    except Exception as e:
        logger.error(f"Failed to send email: {e}")
        return False


def graceful_shutdown(signum, frame):
    logger.info("Received shutdown signal. Exiting...")
    exit(0)


def main():
    signal.signal(signal.SIGINT, graceful_shutdown)
    signal.signal(signal.SIGTERM, graceful_shutdown)

    if not config.is_valid():
        logger.error("Config invalid")
        logger.error("You need to at least specify the following environment variables:")
        logger.error("- PAPERLESSNGX_URL")
        logger.error("- PAPERLESSNGX_TOKEN")
        logger.error("- SEVDESK_TOKEN")
        exit(1)

    while True:
        paperlessngx_lookup_new_documents()
        send_workdir_to_sevdesk()
        time.sleep(config.run_interval)


if __name__ == '__main__':
    main()