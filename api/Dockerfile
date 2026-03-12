FROM python:3.13-slim AS base

WORKDIR /app

RUN pip install --no-cache-dir poetry && \
    poetry config virtualenvs.create false

# Install shared package
COPY shared/ /app/shared/
RUN cd /app/shared && pip install --no-cache-dir -e .

# Install API dependencies
COPY api/pyproject.toml api/poetry.lock* /app/api/
RUN cd /app/api && poetry install --no-interaction --no-root

COPY api/ /app/api/

# --- Development target ---
FROM base AS dev
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# --- Production target ---
FROM base AS production
RUN cd /app/api && poetry install --no-interaction --no-root --only main
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser
EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
