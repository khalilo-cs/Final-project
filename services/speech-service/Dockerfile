FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# The local Whisper engine (about 100 MB of libraries; models are downloaded into the
# /models volume on first use). Build with --build-arg WHISPER=false to leave it out
# when a remote speech server is used instead.
ARG WHISPER=true
RUN if [ "$WHISPER" = "true" ]; then pip install --no-cache-dir "faster-whisper~=1.2.1"; fi

COPY app ./app

RUN useradd --system --no-create-home appuser && mkdir -p /models && chown appuser /models
USER appuser

EXPOSE 8010
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8010"]
