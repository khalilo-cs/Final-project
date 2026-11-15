FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
# Pango renders Arabic (shaping, right-to-left); Noto provides the Arabic fonts.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpango-1.0-0 libpangoft2-1.0-0 \
       fonts-noto-core fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /srv

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

RUN useradd --system --no-create-home appuser
USER appuser

EXPOSE 8009
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8009"]
