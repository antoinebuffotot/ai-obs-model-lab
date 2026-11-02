FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# dtctl (Dynatrace CLI), used by the agent as a read-only tool once the participants have configured it.
# A pinned release is downloaded and verified; if that fails the image still builds and the agent reports
# "dtctl not installed" (check the build output for "dtctl ... installed" or "WARNING").
ARG DTCTL_VERSION=0.45.0
COPY install-dtctl.sh /tmp/install-dtctl.sh
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates     && rm -rf /var/lib/apt/lists/*     && sh /tmp/install-dtctl.sh "$DTCTL_VERSION"     && rm -f /tmp/install-dtctl.sh

WORKDIR /srv
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
