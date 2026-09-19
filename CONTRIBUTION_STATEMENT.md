# Contribution Statement

**Team:** *The Three Musketeers*

**Topic:** *Topic 3 — AI News Briefing Service*

**Repository:** *https://github.com/aliasefoglu/topic-3-news-briefing*

**Final tag:** `v1.0-final`

**Submission date:** *2026-09-19*

---

## Member A — Ali Huseynli (`@aliasefoglu`)

**Owned (sole author of these files / PRs):**

- `src/config.py`
- `src/models.py`
- `src/repository.py`
- `src/cli.py`
- Project tooling and configuration files
- Full-pipeline demo script
- Database, storage, configuration, and password-security support/test files

**Relevant commits:**

- `Initial commit`
- `my first commit`
- `API and Configuration files added`
- `Files for database management added`
- `The file to test the storage is added`
- `The file for the configuration testing added`
- `The file for the password security added`
- `The error in the project was solved`
- `Full pipeline demo script added`
- `Add project tooling configuration`

**Co-owned (paired or substantially edited):**

- Overall project integration
- Main-branch integration of team feature branches
- Final repository organization and integration

**Reviewed (PRs reviewed and merged):**

- PR #2 — Elshan's branch
- PR #3 — Alish's branch

**Approximate share of commits:** **41.7%**

---

## Member B — Alish Hajiyev (`@alishhajiyev`)

**Owned (sole author of these files / PRs):**

- `src/services/ai_service.py`
- `src/services/digest_builder.py`
- `src/services/scheduler.py`
- Login and signup functionality
- Preferences page
- `Dockerfile`

**Relevant commits:**

- `Added AI service wrapper`
- `Added digest builder`
- `Added digest tests`
- `Added daily scheduler`
- `Added login and signup pages`
- `Added preferences page`
- `Added Dockerfile`

**Co-owned (paired or substantially edited):**

- AI summarization integration
- Application-level integration with the project pipeline
- Final branch integration through PR #3

**Reviewed (PRs reviewed and merged):**

- Participated in review and integration of team components

**Approximate share of commits:** **33.3%**

---

## Member C — Elshan Samadzada (`@elshansamadzada7`)

**Owned (sole author of these files / PRs):**

- `src/services/fetch_service.py`
- `src/services/dedup.py`
- `src/services/pipeline.py`
- Fetch service tests
- Deduplication tests

**Relevant commits:**

- `fetch services added`
- `Two-stage deduplication`
- `Orchestrates fetch → dedup → summarize → digest`
- `Fetch service tests`
- `Dedup tests`

**Co-owned (paired or substantially edited):**

- Fetch → dedup → summarize → digest workflow
- Integration of news ingestion and processing components
- Final pipeline integration

**Reviewed (PRs reviewed and merged):**

- Participated in review of integrated project components

**Approximate share of commits:** **25.0%**

---

## AI Tool Disclosure

We used AI coding assistants during development as development and review support. AI-generated suggestions were reviewed, adapted, tested, and integrated by the team.

| Module / file | Assistant | What we did with it |
|---|---|---|
| `src/services/ai_service.py` | AI coding assistant | Used for implementation suggestions; the team reviewed and adapted the implementation to the project's architecture. |
| `src/services/pipeline.py` | AI coding assistant | Used for structural and implementation suggestions; the final logic was reviewed and tested by the team. |
| `src/services/fetch_service.py` | AI coding assistant | Used for implementation suggestions for news fetching; the team reviewed and adjusted the implementation. |
| `src/services/dedup.py` | AI coding assistant | Used for suggestions related to article deduplication; the final implementation was reviewed and tested. |
| Test files | AI coding assistant | Used to suggest test cases and test structures; the team reviewed and adapted the relevant cases. |
| Project configuration and documentation | AI coding assistant | Used for drafting and checking configuration/documentation; the final content was reviewed by the team. |

We affirm that we **can defend every line of code** in this repository during the oral defense. AI assistance was used as a development aid, while implementation decisions, testing, debugging, integration, and final review were performed by the team.

---

## Signatures

By signing below, we affirm that:

- The contributions described above are accurate.
- The commit percentages reflect actual repository history, not artificially split commits.
- Every line of code in the repository can be defended by at least one team member.
- AI assistant usage has been disclosed as described above.

| Member | Signature | Date |
|---|---|---|
| *Ali Huseynli* | __________________________ | *2026-09-19* |
| *Alish Hajiyev* | __________________________ | *2026-09-19* |
| *Elshan Samadzada* | __________________________ | *2026-09-19* |