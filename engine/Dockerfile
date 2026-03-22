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

# Install API dependencies (fastapi, uvicorn for embedded mode)
RUN pip install --no-cache-dir fastapi uvicorn[standard]

# Copy API and scripts
COPY api/ /app/api/
COPY scripts/ /app/scripts/

# /data 디렉토리 생성 (SQLite 볼륨 마운트 지점)
RUN mkdir -p /data

RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app /data
USER appuser
CMD ["python", "-u", "-m", "scripts.run_paper"]
