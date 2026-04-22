# Codebase Guide — Sales Lead Agent

A practical reference for understanding every layer of the system: what each file does, how the pieces connect, and why certain decisions were made. Read top-to-bottom the first time, then use it as a lookup when navigating unfamiliar code.

---

## Table of Contents

1. [What the system does](#1-what-the-system-does)
2. [Repository layout](#2-repository-layout)
3. [Architecture overview](#3-architecture-overview)
4. [Backend — module by module](#4-backend--module-by-module)
5. [Frontend — module by module](#5-frontend--module-by-module)
6. [Data flow: upload to completed job](#6-data-flow-upload-to-completed-job)
7. [Local vs AWS mode](#7-local-vs-aws-mode)
8. [Configuration and secrets](#8-configuration-and-secrets)
9. [Deployment](#9-deployment)
10. [Key design decisions (quick reference)](#10-key-design-decisions-quick-reference)

---

## 1. What the system does

A sales team uploads a CSV or JSON file of raw company leads. The system automatically:

1. Validates each contact email
2. Enriches each company (industry, size, location, tech stack, funding)
3. Compares each company against a set of Ideal Customer Profile (ICP) seed examples using semantic similarity (Voyage AI) or keyword overlap (Jaccard fallback)
4. Computes a deterministic confidence score broken down across 5 weighted components
5. Calls Groq (Llama 3.3 70B) to write a 2–3 sentence plain-English explanation of the score
6. Routes each lead to one of four actions: **Priority**, **Standard**, **Research**, or **Reject**
7. Surfaces results in a real-time dashboard with pagination, score filtering, and NDJSON export

---

## 2. Repository layout

```
sales-lead-agent/
├── backend/
│   ├── api.py                  FastAPI app (also the Lambda API handler entry point)
│   ├── lambda_handler.py       Lambda entry points: api_handler, lead_processor, batch_orchestrator
│   ├── config.py               Pydantic settings + SSM secret resolution
│   ├── db.py                   DynamoDB read/write helpers
│   ├── sqs.py                  SQS send/receive helpers
│   ├── storage.py              S3 upload/download + presigned URL helpers
│   ├── agent/
│   │   ├── models.py           All Pydantic data models + compute_dedup_key()
│   │   ├── orchestrator.py     SalesLeadAgent class + process_batch()
│   │   ├── scorer.py           Deterministic scoring + routing decision
│   │   └── prompts.py          Groq prompt builder + SYSTEM_PROMPT constant
│   ├── tools/
│   │   ├── email_validator.py  Format check + disposable domain list + DNS/MX lookup
│   │   ├── company_lookup.py   Mock enrichment DB + optional Clearbit API
│   │   ├── embeddings.py       Voyage AI embeddings + Jaccard fallback + ICP index
│   │   └── industry_classifier.py  ICP industry/size/geo/activity scoring functions
│   └── tests/
│       └── test_scorer.py      Unit tests for scorer + dedup key
├── frontend/
│   └── src/
│       ├── app/
│       │   ├── page.tsx            Main dashboard page
│       │   ├── leads/[id]/page.tsx Lead detail page
│       │   └── jobs/[id]/page.tsx  Job detail page
│       ├── components/
│       │   ├── UploadForm.tsx      File drag-and-drop upload
│       │   ├── JobStatusCard.tsx   Live-polling in-progress job card
│       │   ├── ProcessedJobCard.tsx Completed job summary card
│       │   ├── LeadTable.tsx       Paginated lead list table
│       │   ├── Analytics.tsx       Action distribution bar chart
│       │   ├── ScoreBreakdownCard.tsx Radar-style score breakdown
│       │   ├── ActionBadge.tsx     Coloured Priority/Standard/Research/Reject pill
│       │   ├── ScoreBar.tsx        Horizontal confidence bar
│       │   ├── QueueDepthBadge.tsx SQS queue depth indicator
│       │   └── ConfirmDialog.tsx   Destructive action confirmation modal
│       ├── hooks/
│       │   ├── useJobStatus.ts     Polls /jobs/{id} every 3 s until terminal state
│       │   ├── useLeads.ts         Paginated /leads fetch with cursor management
│       │   └── usePersistedJobs.ts Stores completed job IDs in localStorage
│       └── lib/
│           ├── api.ts              fetch() wrappers for every backend endpoint
│           └── types.ts            TypeScript mirrors of the backend Pydantic models
├── infrastructure/
│   └── cloudformation.yaml     Full AWS stack definition
├── docs/
│   ├── CODEBASE_GUIDE.md       This file
│   ├── SYSTEM_DESIGN.md        Architecture diagram + key technical decisions
│   └── ADR.md                  Architecture Decision Records (ADR-001 through ADR-029)
└── .github/
    └── workflows/
        └── deploy.yml          CI (lint + test on every push) + CD (manual deploy)
```

---

## 3. Architecture overview

### Local development

```
Browser (Next.js dev server :3000)
        │  HTTP
        ▼
FastAPI (uvicorn :8000)  ←→  In-memory dicts (_local_leads, _local_jobs)
        │
        └── process_batch() runs synchronously in-process
            └── SalesLeadAgent per batch
```

No AWS services needed locally. `ENVIRONMENT=local` in `.env` switches the entire backend into in-memory mode.

### Production (AWS)

```
Browser (Vercel)
        │  HTTPS
        ▼
API Gateway  →  ApiFunction (Lambda / FastAPI / Mangum)
                    │
                    ├── POST /leads/upload
                    │       │  1. Saves file to S3 (input bucket)
                    │       │  2. Creates job record in DynamoDB (batch_jobs)
                    │       └── Returns job_id immediately (202 Accepted)
                    │
                    ├── GET /jobs/{job_id}    ← frontend polls every 3 s
                    └── GET /leads            ← paginated lead list

S3 ObjectCreated trigger
        │
        ▼
BatchOrchestratorFunction (Lambda)
        │  1. Downloads file from S3
        │  2. Parses CSV/JSON → list[RawLead]
        │  3. Deduplicates: compute dedup_key per lead, query dedup_key-index GSI
        │  4a. All dupes → marks job COMPLETED immediately
        │  4b. Has unique leads → updates job stats, fans out one SQS msg per lead
        ▼
LeadQueue (SQS)
        │  one message per unique lead
        ▼
LeadProcessorFunction (Lambda)  [many instances in parallel]
        │  Triggered by SQS (batch size configurable)
        │  1. Parses RawLead from message body
        │  2. Runs SalesLeadAgent pipeline (7 steps)
        │  3. Writes EnrichedLead to DynamoDB (leads table)
        │  4. Atomically increments job stats
        │  5. If processed + errors >= total → marks job COMPLETED
        └── Returns batchItemFailures (only failed messages are retried)

DynamoDB
  leads table       → stores enriched leads; GSIs: batch_id-index, dedup_key-index
  batch_jobs table  → tracks job lifecycle; GSI: batch_id-index

S3 (output bucket)  → stores NDJSON result files (referenced via presigned URL)
```

---

## 4. Backend — module by module

### `config.py`

The single source of truth for all configuration. Uses `pydantic-settings` to load from `.env` and environment variables simultaneously.

**Key patterns:**
- `get_settings()` is decorated with `@lru_cache(maxsize=1)` — it's called once per Lambda cold start and the result is reused across all invocations in that container.
- `_resolve_ssm_or_env(ssm_path_env, direct_env)` — if an env var like `GROQ_API_KEY_PATH` is set, it fetches the secret from AWS SSM Parameter Store (SecureString). Otherwise it falls back to `GROQ_API_KEY` from `.env`. This means rotating a key in production only requires updating SSM — no redeploy.
- `settings.is_local` — checked throughout the codebase to switch between in-memory and DynamoDB/S3/SQS paths.

---

### `agent/models.py`

Defines every data structure in the system. The TypeScript types in `frontend/src/lib/types.ts` are hand-maintained mirrors of these.

**Key models:**

| Model | Purpose |
|---|---|
| `RawLead` | Input from the user: company, email, website, industry, employee count, location |
| `EnrichedLead` | The fully processed lead — contains the raw input plus all enrichment layers, score, reasoning, and routing action |
| `CompanyEnrichment` | Data returned by the company lookup tool |
| `EmailValidationResult` | Output of the email validation tool |
| `SimilarityResult` | One ICP match from the embedding search |
| `ScoreBreakdown` | Five sub-scores + `weighted_total` (a `@computed_field` so Pydantic serialises it) |
| `BatchJobStats` | Running counters: total, processed, duplicates, priority, standard, research, rejected, errors |
| `BatchJob` | A single upload job's lifecycle state (pending → processing → completed/failed) |
| `UploadResponse` | What the API returns immediately after upload: job_id, batch_id, lead_count, duplicate_count |

**`compute_dedup_key(company, contact_email, website)`** — module-level function. Produces a stable 16-char hex key from `normalize(company) + "|" + normalize(email ?? website ?? "")`. "Acme, Inc." and "Acme Inc" hash identically. Used in both the local upload path and the AWS orchestrator to detect duplicates before running any LLM calls.

---

### `agent/orchestrator.py`

Contains two things: the `SalesLeadAgent` class and the `process_batch()` function.

**`SalesLeadAgent`** orchestrates the 7-step pipeline for a single lead:

```
Step 1  _validate_email()      → EmailValidationResult
Step 2  _enrich_company()      → CompanyEnrichment
Step 3  _find_similar()        → list[SimilarityResult]
Step 4  build_score_breakdown() → ScoreBreakdown (deterministic, no LLM)
Step 5  adjust_for_email()     → float (small email validity penalty/boost)
Step 6  _generate_reasoning()  → str  (Groq / Llama 3.3 70B)
Step 7  decide_action()        → LeadAction (Priority/Standard/Research/Reject)
```

Every step catches its own exceptions and returns a safe default, so one failed API call (e.g. Clearbit down) never kills the entire lead or the batch.

The Groq client is instantiated once in `__init__` and reused across all leads in the batch.

**`process_batch(leads, batch_id, job_id, stats)`** — iterates leads sequentially, calling `agent.process()` on each. Updates the shared `stats` object in place. Called by both the local API path (synchronously) and the Lambda `lead_processor` (one lead per invocation).

---

### `agent/scorer.py`

Pure functions, no side effects, no LLM calls — fully unit-testable.

**`build_score_breakdown(enrichment, similarity_results)`** — calls `classify_and_score()` from `industry_classifier.py` to get sub-scores, then combines them with the top ICP similarity score into a `ScoreBreakdown`.

**`decide_action(score, email_result)`** — explicit decision tree:
- score ≥ 0.75 + valid email → `PRIORITY`
- score ≥ 0.75 + bad email → `RESEARCH` (great company, need to find contact)
- score ≥ 0.50 → `STANDARD`
- score ≥ 0.25 → `RESEARCH`
- below 0.25 → `REJECT`

**`adjust_for_email(score, email_result)`** — ±0.03/0.05 nudge. Keeps the confidence score honest without letting a missing email completely tank a strong company.

---

### `agent/prompts.py`

Two exports:

- **`SYSTEM_PROMPT`** — static string sent as the system turn to Groq. Establishes the persona: "senior sales analyst, concise, no invented facts."
- **`build_reasoning_prompt(company, enrichment, score_breakdown, similarity_results, email_valid)`** — builds the user-turn prompt. Injects all structured data (industry, size, funding, tech stack, score components, similar ICP companies) so the LLM produces grounded, specific reasoning rather than hallucinated generalisations.

---

### `tools/email_validator.py`

Three-layer validation, always returns `EmailValidationResult`, never raises:

1. **Format** — simplified RFC 5322 regex
2. **Disposable domain** — hardcoded blocklist (mailinator.com, etc.)
3. **DNS/MX** — `socket.gethostbyname()` with 3s timeout (confirms the domain resolves)

The DNS check is a lightweight proxy for MX record existence. For production, swap to `dnspython` for a real MX query.

---

### `tools/company_lookup.py`

**`enrich_company(company_name)`** — the entry point. Routes to Clearbit (if `CLEARBIT_API_KEY` is set) or the mock DB.

**Mock DB (`_MOCK_DB`)** — a small hardcoded dict with three companies ("Acme Logistics", "Nova Health", "Bright Retail"). Any company not in the dict gets a stub enrichment with `source="mock"`. This lets the system work end-to-end without any external API keys.

**Clearbit path** — calls `https://company.clearbit.com/v2/companies/find?name=...`. Falls back to mock on any error.

**`_classify_industry(text)`** — keyword matching against `_INDUSTRY_KEYWORDS` dict. Called on company descriptions to map free-text industry labels to the `IndustrySegment` enum.

**`_classify_size(employee_count)`** — bucket mapping: ≤50 → startup, ≤500 → SMB, ≤5000 → mid_market, 5000+ → enterprise.

---

### `tools/embeddings.py`

Handles ICP similarity search. Tries Voyage AI first; falls back to Jaccard keyword overlap if the key is missing, the API fails, or the free tier is exhausted.

**Cold-start flow:**
1. `build_icp_index()` is called once in `lambda_handler.py` at module load time
2. Always builds the Jaccard index (free, stdlib-only)
3. Calls `_init_voyage()` — probes `voyage-multimodal-3.5` then `voyage-multimodal-3` with a short test embed
4. If Voyage is available, embeds all four ICP seed examples and stores them as `(company, vector)` pairs in `_voyage_index`

**Per-lead flow (`find_similar_leads`):**
- If `_voyage_index` is populated: embed the query (company + description), compute cosine similarity against each ICP entry, return top-3 above zero
- Otherwise: tokenise the query, compute Jaccard against each ICP entry's token set, return top-3 above zero

**ICP seed examples** — four hardcoded companies that represent the ideal customer: a logistics company (Apex Freight), a healthcare tech company (MedCore Systems), a manufacturer (Ironbridge), and a trade brokerage (TradeLink). Leads that semantically resemble these score higher on `similarity_to_icp`.

---

### `tools/industry_classifier.py`

Defines the Ideal Customer Profile and maps enrichment data to sub-scores.

**ICP definition:**
- Industries: Logistics, Manufacturing, Healthcare
- Sizes: Mid-market, Enterprise
- Geographies: US, Canada, UK

**Scoring functions** (all return 0.0–1.0):
- `score_industry_fit` — 1.0 for ICP industries, 0.6 for Financial Services (adjacent), 0.5 for Technology, 0.2 for unknown
- `score_company_size_fit` — 1.0 for mid-market/enterprise, 0.5 for SMB, 0.1 for startup
- `score_geographic_fit` — 1.0 for US/Canada/UK, 0.7 for major EU markets, 0.3 for rest of world, 0.5 if unknown
- `score_recent_activity` — checks for funding round (Series B = +0.5, C/D = +0.6, A = +0.3) and enterprise tech stack (SAP, Salesforce, AWS, etc. = +0.4), capped at 1.0

---

### `db.py`

All DynamoDB interactions. Key patterns:

- **Float conversion** — DynamoDB rejects Python `float`. `_floats_to_decimals()` JSON-round-trips all data through `parse_float=Decimal` before writes. `_decimals_to_floats()` converts back after reads. This handles arbitrary nesting without manually enumerating fields.
- **`put_lead(lead)`** — uses `ConditionExpression="attribute_not_exists(lead_id)"` to make writes idempotent. Returns `True` if written, `False` if the lead already existed (SQS retry protection).
- **`lead_exists_by_dedup_key(dedup_key)`** — queries the `dedup_key-index` GSI with `Select=COUNT`. O(1) check, no item data read.
- **`count_leads(score_min)`** — full table scan with `Select=COUNT` and `FilterExpression`. Paginates internally until `LastEvaluatedKey` is absent. Returns the true count used by the frontend's `(showing: X / total)` display.
- **`scan_leads(score_min, limit, last_evaluated_key)`** — single scan page. The `LastEvaluatedKey` returned is JSON-encoded and passed back as the `cursor` in subsequent API calls.
- **`update_job_status(job_id, updates)`** — partial update using a dynamically built `SET` expression. Called by the orchestrator to flip job status.

---

### `sqs.py`

Thin wrappers around `boto3.client("sqs")`.

- **`enqueue_lead(lead, batch_id, job_id)`** — sends a single message. Used when the orchestrator processes one lead at a time.
- **`enqueue_batch(leads, batch_id, job_id)`** — uses `send_message_batch` (up to 10 per API call) to minimise SQS API calls for large batches.
- **`get_queue_depth()`** — returns `ApproximateNumberOfMessages` from SQS queue attributes. Displayed in the frontend's `QueueDepthBadge`.

---

### `storage.py`

Thin wrappers around `boto3.client("s3")`.

- **`upload_raw(file_bytes, key)`** — writes the raw uploaded file to the input bucket at `input/{batch_id}/{filename}`.
- **`download_raw(key)`** — used by the orchestrator to retrieve the file after the S3 trigger fires.
- **`save_results(leads, key)`** — serialises enriched leads as NDJSON to the output bucket.
- **`presigned_download_url(key)`** — generates a 1-hour presigned URL for the output file, returned by `GET /jobs/{job_id}/download`.

---

### `api.py`

The FastAPI application. Runs locally via `uvicorn api:app --reload` and in Lambda via `Mangum(app)`.

**Endpoints:**

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/leads/upload` | Upload CSV or JSON; local=sync, AWS=async |
| `POST` | `/leads/process` | Synchronous JSON batch (≤50 leads, returns results directly) |
| `GET` | `/leads` | Paginated lead list with `score_min` filter |
| `GET` | `/leads/export` | Download all leads as NDJSON (streaming) |
| `GET` | `/leads/{lead_id}` | Single lead detail |
| `GET` | `/jobs/{job_id}` | Job status (stats + lifecycle) |
| `GET` | `/jobs/{job_id}/download` | Presigned S3 URL for result file |
| `DELETE` | `/leads` | Clear all leads (local mode only) |
| `GET` | `/queue/depth` | SQS approximate message count |
| `GET` | `/health` | Health check |

**Local upload path (`_upload_local`):**
1. Builds `existing_keys` from `_local_leads` (dedup keys already stored)
2. Iterates incoming leads, computes `dedup_key`, skips if already seen
3. Runs `process_batch()` synchronously on unique leads
4. Stores results in `_local_leads` and `_local_jobs` dicts
5. Returns `UploadResponse` with `duplicate_count`

**AWS upload path (`_upload_aws`):**
1. Uploads raw file to S3
2. Creates a pending job record in DynamoDB
3. Returns `UploadResponse` immediately (the S3 trigger does the rest)

CORS is restricted to `localhost:3000` in local mode and the Vercel deployment URL in production.

---

### `lambda_handler.py`

Defines three Lambda handler functions in a single file (shared import cost on cold start):

**`api_handler`** — `Mangum(app)`, converts API Gateway events to ASGI and back. This is what runs when any HTTP request hits the API Gateway.

**`lead_processor(event, context)`** — triggered by SQS. Iterates `event["Records"]`, processes each lead through `process_batch()`, writes to DynamoDB, and calls `_update_job_progress()`. Returns `batchItemFailures` so SQS only retries the messages that actually failed (ReportBatchItemFailures mode).

**`_update_job_progress(job_id, stats)`** — atomically increments nested stats counters in DynamoDB using `ADD` expressions. After incrementing, reads back `ALL_NEW` and checks if `processed + errors >= total` — if so, marks the job `COMPLETED`. This is how the last Lambda invocation in a batch naturally detects completion without a coordinator.

**`batch_orchestrator(event, context)`** — triggered by S3 ObjectCreated. Parses the file, deduplicates against the `dedup_key-index` GSI, then either completes the job immediately (all duplicates) or updates job stats and fans out one SQS message per unique lead.

`build_icp_index()` is called at module level so the embedding index is built once per container lifetime (not per invocation).

---

## 5. Frontend — module by module

### `lib/api.ts`

One function per backend endpoint, all using a shared `request<T>()` wrapper that checks `res.ok` and throws on errors. `BASE_URL` comes from `NEXT_PUBLIC_API_URL` (set in Vercel env vars) or falls back to `http://localhost:8000`.

`exportLeads()` uses a browser trick: creates a hidden `<a>` element, clicks it to trigger the download, then revokes the object URL to free memory.

---

### `lib/types.ts`

TypeScript hand-mirrors of the backend Pydantic models. When you add a field to `models.py`, update `types.ts` too. The two key interfaces for the dashboard are `JobStatusResponse` (for live polling) and `EnrichedLead` (for the lead table).

---

### `hooks/useJobStatus.ts`

Polls `GET /jobs/{id}` every 3 seconds. Stops when the job reaches `completed` or `failed`. The timer is stored in a ref (not state) to avoid re-render loops. Returns `{ job, error }`.

---

### `hooks/useLeads.ts`

Manages paginated lead fetching with cursor-based navigation. Stores cursor values in a `useRef` array indexed by page number so back-navigation doesn't re-fetch. Resets to page 1 when `scoreMin` changes. Returns `{ leads, total, page, hasNext, hasPrev, loading, error, refresh, nextPage, prevPage }`.

---

### `hooks/usePersistedJobs.ts`

Stores completed job IDs in `localStorage` so the "Processed Jobs" section survives page refreshes. Exposes `addCompletedJob(id)` and `clearCompletedJobs()`.

---

### `app/page.tsx` (Dashboard)

The main page. Owns the top-level state:

- `processingIds` — job IDs currently being processed (drives the `JobStatusCard` grid)
- `completedIds` — from `usePersistedJobs` (drives the `ProcessedJobCard` grid)
- `dupSummary` — amber banner string shown after an upload with duplicates
- `scoreMin` — current filter value passed to `useLeads`

**Upload flow:**
1. `UploadForm` calls `onUploaded(res: UploadResponse)` on success
2. `onUploaded` pushes the `job_id` into `processingIds`, sets `dupSummary` if duplicates exist
3. A `JobStatusCard` renders for that `job_id` and starts polling
4. When the job completes, `onJobComplete` fires after a minimum 2.5 s display time, moves the ID from `processingIds` to `completedIds`, and refreshes the lead table

---

### `components/UploadForm.tsx`

Drag-and-drop file input (accepts `.csv` and `.json`). Shows a spinner while `isProcessing` is true. Calls `uploadLeads(file)` from `api.ts` and triggers `onUploaded` on success.

---

### `components/JobStatusCard.tsx`

Displays a live-updating job card: status icon, progress bar (`processed / total`), action breakdown grid (Priority/Standard/Research/Rejected counts), an amber duplicate banner when `status === "completed" && stats.duplicates > 0`, and an error count. Uses `useJobStatus` for polling. Fires `onComplete(jobId)` once when the terminal state is reached.

---

### `components/ProcessedJobCard.tsx`

Static version of `JobStatusCard` for the history section. Fetches the job once via `useJobStatus` (which stops polling on terminal state immediately). Renders the same layout but without the `onComplete` callback. Also shows the amber duplicate banner.

---

### `components/LeadTable.tsx`

Renders the paginated lead list. Each row shows company name, industry, size, location, `ActionBadge`, `ScoreBar`, and a link to the lead detail page. Shows a skeleton loader while `loading` is true.

---

### `components/Analytics.tsx`

Bar chart showing the distribution of `recommended_action` across the current page of leads. Uses plain CSS bars (no chart library dependency).

---

## 6. Data flow: upload to completed job

### Local mode (step-by-step)

```
1. User drops leads.csv on UploadForm
2. Browser → POST /leads/upload (multipart form)
3. api.py: _parse_csv() → list[RawLead]
4. api.py: compute_dedup_key() per lead → filter duplicates
5. api.py: process_batch(unique_leads, ...) runs in-process
      └── for each lead: SalesLeadAgent.process()
              ├── validate_email()
              ├── enrich_company()        (mock DB or Clearbit)
              ├── find_similar_leads()    (Voyage AI or Jaccard)
              ├── build_score_breakdown() (deterministic)
              ├── adjust_for_email()
              ├── _generate_reasoning()   (Groq / Llama 3.3 70B)
              └── decide_action()
6. Results stored in _local_leads dict
7. UploadResponse(job_id, batch_id, lead_count, duplicate_count) → Browser
8. Browser: useJobStatus polls /jobs/{job_id} → status="completed"
9. Browser: useLeads refreshes → lead table populates
```

### AWS mode (step-by-step)

```
1. User drops leads.csv on UploadForm
2. Browser → POST /leads/upload (multipart form)
3. ApiFunction Lambda:
   a. _parse_csv() → list[RawLead]
   b. storage.upload_raw() → S3 input bucket: input/{batch_id}/leads.csv
   c. db.put_job() → DynamoDB batch_jobs: status=PENDING
   d. UploadResponse(job_id, batch_id, lead_count) → Browser (202)

4. S3 ObjectCreated trigger fires → BatchOrchestratorFunction Lambda:
   a. download_raw(key) → raw bytes
   b. _parse_csv() → list[RawLead]
   c. For each lead: compute_dedup_key() → query dedup_key-index GSI
   d. Split into unique_leads + duplicate_count
   e. If unique_leads is empty:
        db.update_job_status() → status=COMPLETED, duplicates=N
      Else:
        db.update_job_status() → status=PROCESSING, total=len(unique_leads)
        sqs.enqueue_batch() → one SQS message per unique lead

5. SQS triggers LeadProcessorFunction Lambda (one per message, many in parallel):
   a. Parse RawLead from message body
   b. process_batch([raw_lead], ...)
        └── SalesLeadAgent.process() (7-step pipeline, same as local)
   c. db.put_lead() → DynamoDB leads table (conditional write, idempotent)
   d. _update_job_progress():
        - ADD stats.processed, stats.priority, etc. (atomic)
        - If processed + errors >= total → SET status=COMPLETED

6. Browser: useJobStatus polls /jobs/{job_id} every 3 s
7. Once status=COMPLETED: onJobComplete() fires → lead table refreshes
```

---

## 7. Local vs AWS mode

The entire backend switches behaviour based on a single check: `settings.is_local` (`ENVIRONMENT=local`).

| Concern | Local | AWS |
|---|---|---|
| Lead storage | `_local_leads` dict in RAM | DynamoDB `leads` table |
| Job storage | `_local_jobs` dict in RAM | DynamoDB `batch_jobs` table |
| File storage | Not needed (parsed in RAM) | S3 input + output buckets |
| Processing | Synchronous in the API process | Async: S3 → Orchestrator → SQS → Processor |
| Dedup | Checked against `_local_leads` | Checked against `dedup_key-index` GSI |
| Secrets | `.env` file | SSM Parameter Store |
| CORS | `localhost:3000` | Vercel deployment URL |

To run locally:

```bash
# Terminal 1 — backend
cd backend
uvicorn api:app --reload --port 8000

# Terminal 2 — frontend
cd frontend
npm run dev
```

---

## 8. Configuration and secrets

All config lives in `backend/config.py` as a `pydantic-settings` `BaseSettings` class.

**Environment variables (`.env` for local, Lambda env vars for production):**

```
GROQ_API_KEY          Groq API key (local only — in prod, use GROQ_API_KEY_PATH)
GROQ_API_KEY_PATH     SSM SecureString path, e.g. /sales-lead-agent/groq-api-key
VOYAGE_API_KEY        Voyage AI key (local only — in prod, use VOYAGE_API_KEY_PATH)
VOYAGE_API_KEY_PATH   SSM SecureString path, e.g. /sales-lead-agent/voyage-api-key
AWS_REGION            us-east-1
DYNAMODB_LEADS_TABLE  leads (or leads-production, leads-staging, etc.)
DYNAMODB_JOBS_TABLE   batch_jobs
S3_INPUT_BUCKET       Name of the input S3 bucket
S3_OUTPUT_BUCKET      Name of the output S3 bucket
SQS_QUEUE_URL         Full URL of the LeadQueue SQS queue
ENVIRONMENT           local | staging | production
LOG_LEVEL             INFO
LEAD_SCORE_PRIORITY_THRESHOLD  0.75
LEAD_SCORE_STANDARD_THRESHOLD  0.50
MAX_CONCURRENT_LEADS  10
```

**SSM secret rotation (no redeploy required):**
```bash
aws ssm put-parameter \
  --name /sales-lead-agent/groq-api-key \
  --value gsk_NEW_KEY \
  --type SecureString \
  --overwrite
```
The next Lambda cold start reads the new value automatically.

---

## 9. Deployment

### CI — runs on every push to any branch

`.github/workflows/deploy.yml` runs:
1. `pip install -r requirements.txt`
2. `flake8 .` (linting, configured in `backend/.flake8`)
3. `pytest tests/` (unit tests in `backend/tests/`)

### CD — manual only (`workflow_dispatch`)

Triggered from GitHub Actions UI. Steps:
1. Select environment: `staging` or `production`
2. Workflow zips the `backend/` directory (excluding `.venv/`)
3. Uploads zip to S3 deployment bucket
4. Updates Lambda function code (`aws lambda update-function-code`)
5. Deploys CloudFormation stack (`aws cloudformation deploy`)
6. Tags the release in git

Frontend deploys automatically to Vercel on every push to `main`.

### CloudFormation stack (`infrastructure/cloudformation.yaml`)

Creates the full AWS stack:

| Resource | Purpose |
|---|---|
| `ApiFunction` | Lambda running FastAPI via Mangum; triggered by API Gateway |
| `LeadProcessorFunction` | Lambda processing individual leads from SQS |
| `BatchOrchestratorFunction` | Lambda triggered by S3; parses file and fans out to SQS |
| `ApiGateway` (HTTP API) | Public endpoint routing all HTTP traffic to `ApiFunction` |
| `LeadQueue` (SQS) | Decouples orchestrator from processor; enables parallel Lambda scaling |
| `LeadQueue-DLQ` | Dead-letter queue for messages that fail all retries |
| `LeadsTable` (DynamoDB) | Stores enriched leads; GSIs: `batch_id-index`, `dedup_key-index` |
| `BatchJobsTable` (DynamoDB) | Tracks job lifecycle; GSI: `batch_id-index` |
| `InputBucket` (S3) | Receives raw uploaded files; triggers `BatchOrchestratorFunction` |
| `OutputBucket` (S3) | Stores NDJSON result files |
| `SSM Parameters` | `GROQ_API_KEY_PATH` and `VOYAGE_API_KEY_PATH` for secret resolution |
| `LambdaExecutionRole` (IAM) | Grants Lambdas access to DynamoDB, S3, SQS, SSM, CloudWatch |
| `CloudWatchAlarms` | Lambda error rate + DLQ depth alarms |

---

## 10. Key design decisions (quick reference)

| Decision | Why |
|---|---|
| Groq (Llama 3.3 70B) for reasoning | ~10x faster than Claude for short completions; latency matters when processing batches concurrently in Lambda |
| Deterministic scoring + LLM explanation | Score is reproducible and auditable; LLM only adds the human-readable "why" |
| SHA-256 dedup key (16 chars) | Prevents duplicate processing on re-upload; stable across minor name variations |
| Orchestrator owns fan-out exclusively | Prevents double-processing that occurred when both API and S3 trigger were enqueuing to SQS |
| Immediate completion when all leads are duplicates | `total=0` means the `processed >= total` completion check would never fire |
| Voyage AI + Jaccard fallback | `onnxruntime` exceeds Lambda ZIP limit (250 MB); Voyage API keeps zip under 5 MB; Jaccard works with zero dependencies |
| SSM SecureString for API keys | Key rotation without redeployment; CloudFormation can't resolve `ssm-secure://` in Lambda env vars |
| `@computed_field` for `weighted_total` | Pydantic v2 doesn't serialise bare `@property` — without this, `weighted_total` is excluded from `.model_dump()` and the frontend sees `NaN%` |
| `SELECT COUNT` for `count_leads` | Avoids transferring item data just to get a total; paginated internally to handle tables larger than one DynamoDB scan page |
| `put_lead` with conditional write | Makes SQS retries idempotent — a message redelivered after a Lambda timeout won't double-count stats |
| `ReportBatchItemFailures` on SQS | Only failed messages are retried; a single bad lead doesn't block the whole batch |
| SQS visibility timeout (300s) ≥ Lambda timeout (270s) | If Lambda times out mid-batch, the message must stay invisible until the timeout completes; otherwise it reappears and gets processed twice |
