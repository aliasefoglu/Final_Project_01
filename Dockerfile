# ---- Build stage: compile/install dependencies only ----
FROM python:3.12-slim AS builder

WORKDIR /app

# build-essential is only needed to build any dependency without a
# prebuilt wheel for this platform; it never ends up in the final image.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# ---- Runtime stage: just the installed packages + our code ----
FROM python:3.12-slim AS runtime

WORKDIR /app

# Copy only the installed site-packages from the builder stage -- no
# compiler toolchain ends up in the shipped image (multi-stage build).
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# The provided ai/ package (unmodified), our SE layer, and the sample data
# the pipeline reads at startup (data/rss_feeds.txt, data/user_profile.json).
COPY ai/ ./ai/
COPY src/ ./src/
COPY data/ ./data/
COPY tests/ ./tests/

RUN mkdir -p /app/digests

EXPOSE 8000

# Default process: the scheduler (long-running, generates digests on a
# cron schedule). Override the command for one-off runs, e.g.:
#   docker compose run --rm app python -m src.cli run-daily --user khagani
#   docker compose run --rm app uvicorn src.api:app --host 0.0.0.0 --port 8000
CMD ["python", "-m", "src.scheduler"]
