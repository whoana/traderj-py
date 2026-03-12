FROM python:3.13-slim AS base

WORKDIR /app

RUN pip install --no-cache-dir poetry && \
    poetry config virtualenvs.create false

# Install shared package
COPY shared/ /app/shared/
RUN cd /app/shared && pip install --no-cache-dir -e .

# Install engine dependencies
COPY engine/pyproject.toml engine/poetry.lock* /app/engine/
RUN cd /app/engine && poetry install --no-interaction --no-root

COPY engine/ /app/engine/

# --- Development target ---
FROM base AS dev
CMD ["python", "-m", "engine"]

# --- Production target ---
FROM base AS production
RUN cd /app/engine && poetry install --no-interaction --no-root --only main
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser
CMD ["python", "-m", "engine"]
