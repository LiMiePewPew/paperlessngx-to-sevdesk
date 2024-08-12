FROM python:3.12.4-slim

LABEL maintainer="Oliver Lippert <oliver@lipperts-web.de>"

ENV RUN_INTERVAL=300 \
    PAPERLESSNGX_URL="" \
    PAPERLESSNGX_TOKEN="" \
    PAPERLESSNGX_FILTER_TAG_ID=0 \
    PAPERLESSNGX_FILTER_DOCUMENT_TYPE_ID=0 \
    EMAIL_ACCOUNT="" \
    SMTP_SERVER="" \
    SMTP_PORT=0 \
    LOGIN="" \
    PASSWORD=""

VOLUME /app/workdir
COPY src/Pipfile* /app/
WORKDIR /app
RUN pip install --no-cache-dir pipenv && pipenv install --deploy --ignore-pipfile

COPY src /app

CMD ["pipenv", "run", "python", "main.py"]