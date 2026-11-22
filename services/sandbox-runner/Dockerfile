FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# UI screenshots of the student's pages (FR-09.8): docker compose build --build-arg SCREENSHOTS=1
ARG SCREENSHOTS=0
RUN if [ "$SCREENSHOTS" = "1" ]; then \
      pip install --no-cache-dir playwright==1.63.0 && playwright install --with-deps chromium; \
    fi

COPY app ./app

# Talks to the Docker daemon through the mounted socket (see docker-compose.yml).
EXPOSE 8008
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8008"]
