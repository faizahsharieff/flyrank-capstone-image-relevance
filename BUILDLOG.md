# Build Log

Implementation milestones recorded on 2026-09-30. Gemini calls in automated tests use mocks; no live provider output is claimed here.

## Phase 1 - Application foundation

- Added FastAPI health route, database configuration/base, dependency declarations, environment template, ignore rules, and setup README.
- Validation: health endpoint test passed.

## Phase 2 - Persistence and migrations

- Added SQLAlchemy models for images, metadata, posts, suggestions, reviews, jobs, and cost logs; configured Alembic and initial PostgreSQL schema.
- Validation: model relationships and tests passed; migration applied to local PostgreSQL.

## Phase 3 - Image understanding

- Added Pydantic metadata schema and Gemini Flash vision service with structured responses, validation, retry behavior, and confidence review flag.
- Validation: mocked vision and schema tests passed; no live Gemini call was used for test evidence.

## Phase 4 - Background image processing

- Added image batch job, job status endpoints, metadata persistence, retries, idempotent completion checks, and per-call vision cost logging.
- Validation: mocked worker and API tests passed. Worker failures are logged for diagnosis.

## Phase 5 - Semantic embeddings

- Added Gemini embedding service and PostgreSQL JSONB vectors/source hashes for image captions and post title/content. Reused cost logs for embedding calls.
- Validation: mocked embedding and idempotency tests passed; migration `0003_semantic_embeddings` applied locally.

## Phase 6 - Similarity ranking

- Added NumPy cosine similarity, database-backed candidate ranking, and `GET /posts/{post_id}/images`.
- Validation: deterministic vectors verified red fox ranking above wolf/dog in unit tests.

## Phase 7 - Mismatch guard

- Added configurable similarity/confidence thresholds and subject/category compatibility checks. The API returns `no_confident_match` when no candidate passes.
- Validation: fox acceptance, wolf rejection, low similarity/confidence, category mismatch, and no-match tests passed.

## Phase 8 - Review workflow

- Added suggestion inspection and approve/reject endpoints backed by `Review` records.
- Validation: mocked API tests covered inspection, persistence, invalid decisions, and nonexistent suggestions.

## Phase 9 - Evaluation

- Added `scripts/evaluate.py` for guarded top-1 evaluation and failure explanations.
- Dataset state at the last check: `data/eval.json` had 10 labeled examples; a captured run reported top-1 precision of 0.20. Pair-to-image label correctness still requires human review.

## Phase 10 - Submission preparation

- Expanded README, Docker Compose configuration, seed script, `capstone.yaml`, and evidence/build-log templates.
- Validation: full suite reported 61 passed; Compose configuration and seed CLI were checked.

## Article creation workflow

- Added `POST /posts` with Pydantic validation, persistence, and reuse of the existing embedding helper/service and cost tracking.
- Validation: full suite reported 65 passed, including mocked create/embedding/matcher workflow tests.

## Suggestion persistence handoff

- Connected guarded matching to PostgreSQL `Suggestion` upserts. Accepted responses expose `suggestion_id`; rejected decisions retain guard explanations and are inspectable. A unique `(post_id, image_id)` constraint makes repeated matching idempotent and preserves related reviews.
- Added migration `0004_persist_match_suggestions`; applied locally. Alembic reported `0004_persist_match_suggestions (head)`.
- Validation: affected matcher/guard/review/post tests reported 29 passed; full suite reported 68 passed. One existing Starlette/httpx deprecation warning remained.

## Final verification - 2026-10-19

- Local database status: 50 image records; 21 completed, 29 failed, 0 pending, and 0 processing. PostgreSQL 16 was healthy and Alembic reported `0004_persist_match_suggestions (head)`.
- Retrieved a successful `GET /posts/6/images?limit=5` response from existing stored embeddings, without calling Gemini or regenerating embeddings. Post 6, “The Behaviour of Jackals,” returned accepted image 2 (`jackal_01.jpg`) with similarity `0.8021871805192398` (approximately `0.8022`). The response also reported a hyena candidate rejected for subject mismatch.
- Repository virtual-environment test run: `68 passed, 1 warning`. The tests mock Gemini and use fake/in-memory database sessions; they do not establish live Gemini behavior or full PostgreSQL integration.
- Gemini image processing was reported to have encountered HTTP 429 quota/rate limiting. This is operator-reported and was not independently reproduced; current quota availability and the cause of every failed image were not verified. No Gemini calls were made during this verification.

## AI Assistance and Development Reflection

AI coding assistance was used during backend development, code review, debugging, and documentation preparation.

The implementation work covered FastAPI routes, SQLAlchemy models, Alembic migrations, Gemini integration, semantic matching, mismatch validation, and suggestion persistence.

**Challenges and corrections:**
- The operator reported a Gemini HTTP 429 quota/rate-limit response. It was not independently reproduced, so the exact quota condition and current availability are unverified. Instead of triggering further AI requests, verification continued using previously stored database records and embeddings.
- Running tests with the system Python interpreter produced two failures due to a Google GenAI SDK compatibility difference. Using the repository's virtual environment resolved this issue, and all 68 tests passed.
- Documentation was updated to reflect implemented article creation and suggestion persistence, removing outdated descriptions of those features as incomplete.
- The matching workflow was checked using a real stored jackal article and image. The API accepted the jackal image and rejected the hyena candidate for subject mismatch.

**Remaining limitations:**

Image processing is incomplete. The operator reported HTTP 429 quota/rate limiting, but the exact cause of every failed image and current quota availability have not been independently verified. AI cost logging exists, but automated budget enforcement is not implemented.

Automated tests use mocked integrations; they are not presented as proof of live Gemini availability.