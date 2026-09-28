FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv

COPY pyproject.toml README.md ./
COPY app ./app
COPY workers ./workers
COPY applier ./applier
COPY alembic.ini ./
RUN pip install --no-cache-dir .
# Tectonic builds tailored resume PDFs
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
 && curl --proto '=https' --tlsv1.2 -fsSL https://drop-sh.fullyjustified.net | sh \
 && mv tectonic /usr/local/bin/ && apt-get purge -y curl && rm -rf /var/lib/apt/lists/*

EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
