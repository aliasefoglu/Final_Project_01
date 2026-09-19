# AI News Briefing Service

**Team:** The Three Musketeers — Alish Hajiyev, Ali Huseynli, Elsen Samadzada
**Course:** AI-ENG-110 Software Engineering, AI Academy (National AI Center) — Final Project, Topic 3
**Repository:** https://github.com/aliasefoglu/News-Briefing

## Overview

AI News Briefing Service is a scheduled news aggregation system that collects articles from multiple sources, removes duplicate and near-duplicate stories, summarizes the remaining articles with an LLM, and generates a personalized daily news digest.

The system is designed around a simple pipeline:

```text
News Sources
    │
    │  RSS + HTML
    ▼
Concurrent Fetching
    │
    │  asyncio + httpx
    ▼
Two-Stage Deduplication
    │
    │  URL/content hash
    │  Jaccard similarity
    ▼
AI Service
    │
    │  summarize + label
    │  retries + timeout + cache
    ▼
Digest Builder
    │
    │  user preferences
    ▼
Daily Markdown Digest
```

The project also includes a PostgreSQL-backed storage layer, a command-line interface, a daily scheduler, and a bonus FastAPI web interface.

## Main Features

* Fetches news concurrently from **6 sources**: 5 RSS feeds and 1 directly scraped HTML page.
* Uses `asyncio` and `httpx` with a configurable semaphore to limit concurrent requests.
* Performs **two-stage duplicate detection**:

  * canonical URL and SHA-256 content hash checks;
  * word-shingle Jaccard similarity for near-duplicate articles.
* Wraps the course-provided AI package behind a separate `AIService`.
* Uses retries with exponential backoff and per-call timeouts for AI requests.
* Stores AI results in PostgreSQL using the article content hash as the cache key.
* Continues processing when an individual source or AI request fails.
* Builds personalized digests according to each user's topic preferences and excluded sources.
* Provides both a CLI and an APScheduler-based daily execution mode.
* Includes a bonus FastAPI web UI with signup, login, preferences, and digest viewing.
* Runs the complete application stack with Docker Compose.
* Includes automated tests, coverage reporting, and type checking.

## Architecture

The application is separated into several layers so that fetching, processing, AI calls, storage, and orchestration remain independent.

```text
                    ┌─────────────────────┐
                    │     News Sources    │
                    │  5 RSS + 1 HTML     │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │   Fetch Service     │
                    │ asyncio + httpx     │
                    │ retries + timeout   │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │    Deduplication    │
                    │                     │
                    │ URL / content hash  │
                    │ Jaccard similarity  │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │     AIService       │
                    │                     │
                    │ summarize + label   │
                    │ retry + cache       │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │   Digest Builder    │
                    │                     │
                    │ user preferences    │
                    │ topic grouping      │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │  Markdown Digest    │
                    │ YYYY-MM-DD-user.md  │
                    └─────────────────────┘
```

The `ai/` package was provided by the course and is kept unchanged. The rest of the application is built around it through the `AIService` wrapper.

## Requirements

* Python 3.12
* PostgreSQL 16
* Docker and Docker Compose (recommended)
* An API key for one supported LLM provider:

  * Anthropic
  * OpenAI
  * Google Gemini
* An embedding provider supported by the project configuration

## Local Setup

Clone the repository:

```bash
git clone https://github.com/aliasefoglu/News-Briefing.git
cd News-Briefing
```

Create and activate a virtual environment:

```bash
python -m venv .venv
```

Windows:

```bash
.venv\Scripts\activate
```

Linux/macOS:

```bash
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements-dev.txt
```

Create the environment file:

```bash
cp .env.example .env
```

Then add the required API keys and configuration values to `.env`.

### PostgreSQL

If PostgreSQL is not already running, a local Docker container can be started with:

```bash
docker run -d \
  --name pg \
  -e POSTGRES_PASSWORD=dev \
  -e POSTGRES_DB=newsbrief \
  -p 5432:5432 \
  postgres:16
```

## Configuration

The application reads its configuration from environment variables and `.env` through `src/config.py`.

| Variable                         | Default                     | Description                                            |
| -------------------------------- | --------------------------- | ------------------------------------------------------ |
| `LLM_PROVIDER`                   | `anthropic`                 | LLM provider: `anthropic`, `openai`, or `gemini`       |
| `LLM_MODEL`                      | `claude-sonnet-4-6`         | Provider-specific model ID                             |
| `ANTHROPIC_API_KEY`              | —                           | Anthropic API key                                      |
| `OPENAI_API_KEY`                 | —                           | OpenAI API key                                         |
| `GOOGLE_API_KEY`                 | —                           | Google Gemini API key                                  |
| `EMBEDDING_PROVIDER`             | `openai`                    | `openai` or `gemini`                                   |
| `EMBEDDING_MODEL`                | `text-embedding-3-small`    | Embedding model ID                                     |
| `DATABASE_URL`                   | PostgreSQL local connection | PostgreSQL connection string                           |
| `DIGESTS_DIR`                    | `./digests`                 | Directory for generated digests                        |
| `LOG_LEVEL`                      | `INFO`                      | Application logging level                              |
| `DEDUP_NEAR_DUPLICATE_THRESHOLD` | `0.70`                      | Jaccard similarity threshold                           |
| `FETCH_TIMEOUT_SECONDS`          | `15`                        | HTTP request timeout                                   |
| `MAX_PARALLEL_FETCHES`           | `8`                         | Maximum concurrent fetches                             |
| `HTML_SCRAPE_URL`                | BBC World                   | HTML source listing page                               |
| `HTML_SCRAPE_SOURCE_NAME`        | `BBC World (scraped)`       | Display name of the scraped source                     |
| `SESSION_SECRET_KEY`             | `change-me-in-production`   | Secret used for web sessions                           |
| `AI_DRY_RUN`                     | `false`                     | Skip real LLM calls when enabled                       |
| `MAX_ARTICLES_PER_RUN`           | unset                       | Optional article limit for development/free-tier usage |
| `NEWSBRIEF_USERS`                | `khagani`                   | Comma-separated scheduler users                        |
| `NEWSBRIEF_SCHEDULE_HOUR`        | `6`                         | Daily scheduler hour                                   |
| `NEWSBRIEF_SCHEDULE_MINUTE`      | `0`                         | Daily scheduler minute                                 |

Do not commit `.env` to the repository. Use `.env.example` as the configuration template.

## Running the Application

### Daily CLI Run

Run the pipeline for a user:

```bash
python -m src.cli run-daily --user khagani
```

The generated digest is written to:

```text
digests/YYYY-MM-DD-khagani.md
```

The logs include information about fetching, duplicate detection, cache hits, and AI processing.

### Demo Script

The project also includes a small script that runs the real pipeline and prints the resulting digest:

```bash
python scripts/demo.py --user khagani
```

### Scheduler

To start the daily scheduler:

```bash
python -m src.scheduler
```

The scheduler runs the configured users once per day according to:

```text
NEWSBRIEF_SCHEDULE_HOUR
NEWSBRIEF_SCHEDULE_MINUTE
```

### Web Interface

Start the FastAPI application with:

```bash
uvicorn src.api:app --host 0.0.0.0 --port 8000
```

Then open:

```text
http://localhost:8000
```

Available routes include:

```text
/
 /signup
 /login
 /logout
 /preferences
 /digest
```

The web interface allows users to create an account, select their preferred topics, exclude sources, and view their generated digest.

A sample output from a full run is available in the `artefacts/` directory.

## Docker

The recommended way to run the complete system is Docker Compose.

Create the environment file:

```bash
cp .env.example .env
```

Add the required API key(s), then run:

```bash
docker compose up --build
```

The Compose configuration starts:

```text
db    → PostgreSQL 16
app   → scheduler / application
web   → FastAPI web interface
```

For a one-time run without waiting for the scheduler:

```bash
docker compose run --rm app \
  python -m src.cli run-daily --user khagani
```

Generated digests are stored in the host `./digests` directory through a bind mount.

## Deduplication

Duplicate detection happens in two stages.

### Stage 1 — Exact Duplicate Detection

The first stage is intentionally cheap.

The system checks:

* canonicalized URLs;
* SHA-256 content hashes.

Previously processed URLs are also stored in PostgreSQL, allowing duplicates to be detected across different runs.

### Stage 2 — Near-Duplicate Detection

Articles that pass the first stage are compared using word-shingle Jaccard similarity.

The default threshold is:

```text
0.70
```

An article is rejected when its similarity with an already-kept article is greater than or equal to this threshold.

This helps remove cases where different URLs contain essentially the same story.

| Stage | Method                               | Reject condition                 |
| ----- | ------------------------------------ | -------------------------------- |
| 1     | Canonical URL + SHA-256 content hash | URL or content already processed |
| 2     | Word-shingle Jaccard similarity      | Similarity ≥ `0.70`              |

## AI Processing and Caching

The course-provided `ai/` package is treated as an external dependency.

Application code communicates with it through:

```text
AIService
```

The wrapper is responsible for:

* retry handling;
* exponential backoff;
* per-call timeouts;
* logging;
* persistent caching.

The cache is keyed by the article's content hash.

This means that unchanged article content does not require another LLM request. If the article content changes, it receives a different hash and can be processed again.

## Graceful Degradation

The pipeline is designed so that one failure does not stop the entire daily run.

For example:

```text
Source A ── success
Source B ── success
Source C ── failed
Source D ── success
        │
        ▼
   Continue with
   available articles
```

If a source fails, the failure is logged and processing continues with the remaining sources.

The same principle is applied to AI processing: an unsuccessful AI call is logged and skipped rather than terminating the complete digest generation process.

## Performance Benchmark

We compared sequential and concurrent fetching using 20 fetch operations distributed across the configured sources.

The sequential version used:

```text
max_parallel = 1
```

The concurrent version used:

```text
max_parallel = 8
```

### Result

| Workload |  N | Sequential | Concurrent | Speedup |
| -------- | -: | ---------: | ---------: | ------: |
| Fetch    | 20 |    13.79 s |     3.00 s |    4.6× |

The concurrent implementation was approximately **4.6× faster** for this test workload.

The result is not expected to reach the theoretical 8× maximum because different sources have different response times, and one source experienced a failure followed by retry/backoff during the benchmark.

Network conditions can also affect the measured values.

Reproduce the benchmark with:

```bash
python scripts/bench.py --N 20 --max-parallel 8
```

## Testing

The project includes automated tests for the main application components.

Tests are designed to run offline:

* the AI layer is mocked;
* HTTP requests are intercepted with `respx`;
* external services are not required for the test suite.

Run the complete test suite:

```bash
pytest --cov=src --cov-report=term-missing
```

Run the provided AI smoke tests:

```bash
pytest tests/test_ai_smoke.py
```

Latest project result:

```text
69 tests passing
86.7% coverage
Minimum required coverage: 60%
```

Coverage is enforced through `fail_under` in `pyproject.toml`.

### Type Checking

Run mypy with:

```bash
mypy --explicit-package-bases \
     --disable-error-code=import-untyped \
     src
```

## Project Structure

```text
.
├── ai/                         # Course-provided package — unchanged
│
├── src/
│   ├── config.py               # Environment and typed settings
│   ├── models.py               # Pydantic models
│   │
│   ├── services/
│   │   ├── ai_service.py       # AI wrapper and caching
│   │   └── fetch_service.py    # RSS and HTML fetching
│   │
│   ├── core/
│   │   ├── dedup.py            # Duplicate detection
│   │   └── digest_builder.py   # Personalized digest generation
│   │
│   ├── concurrency/
│   │   └── pipeline.py         # Pipeline orchestration
│   │
│   ├── storage/
│   │   ├── repository.py       # PostgreSQL access
│   │   └── schema.sql          # Database schema
│   │
│   ├── cli.py                  # CLI entry point
│   ├── scheduler.py            # Daily scheduler
│   ├── api.py                  # FastAPI application
│   ├── security.py             # Web authentication helpers
│   ├── templates/              # HTML templates
│   └── static/                 # CSS/static assets
│
├── tests/                      # Automated tests
├── scripts/
│   ├── demo.py                 # Full-pipeline demo
│   └── bench.py                # Fetch benchmark
│
├── data/                       # Sample input data
├── artefacts/                  # Sample generated output
├── report/                     # Project report
├── presentation/               # Final presentation
│
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── requirements-dev.txt
├── pyproject.toml
└── .env.example
```

## Design Decisions

### Separate Fetching from Processing

Fetching is isolated from deduplication and AI processing. This makes it easier to add another news source without changing the rest of the pipeline.

The source abstraction is based on:

```text
NewsSource
├── RssSource
└── HtmlScrapeSource
```

A new source can therefore be added by implementing its fetching logic while keeping the orchestration layer unchanged.

### Concurrency with a Bound

The application uses asynchronous HTTP requests, but it does not allow unlimited concurrency.

A semaphore controls the number of active fetches:

```text
MAX_PARALLEL_FETCHES = 8
```

This provides the performance benefit of concurrent I/O while keeping the number of simultaneous requests bounded.

### AI Behind a Wrapper

Business logic does not communicate directly with Anthropic, OpenAI, or Gemini SDKs.

Instead:

```text
Pipeline
   │
   ▼
AIService
   │
   ▼
Course-provided ai package
   │
   ▼
Selected LLM provider
```

This keeps provider-specific details in one place and makes the rest of the application easier to test.

### Content-Based Cache

The AI cache uses the article's content hash instead of its URL.

This is intentional: the same URL can contain updated content, while unchanged content should not trigger another LLM request.

## Team Contributions

| Member              | Main Ownership                                                                                             |
| ------------------- | ---------------------------------------------------------------------------------------------------------- |
| **Alish Hajiyev**   | `ai_service.py`, `digest_builder.py`, `scheduler.py`, `Dockerfile`, `README`, `test_digest.py`             |
| **Ali Huseynli**    | `config.py`, `models.py`, `repository.py`, `cli.py`, `requirements.txt`, `.env.example`, `test_storage.py` |
| **Elsen Samadzada** | `fetch_service.py`, `dedup.py`, `pipeline.py`, `test_fetch.py`, `test_dedup.py`                            |

The detailed contribution breakdown is provided separately in the signed contribution statement.

## Sample Output

A sample result of a complete pipeline execution is included in:

```text
artefacts/
```

The generated digest contains the processed articles grouped according to the user's selected topics and preferences.

## License / Academic Use

This repository was developed as the final project for:

```text
AI-ENG-110 — Software Engineering
AI Academy — National AI Center
Topic 3: AI News Briefing Service
```

The `ai/` package included in the repository was provided as part of the course and was not modified by the team.
