# Architecture Decision Records

This document tracks key technical and design decisions made during the development of the Sales Lead Agent. Each entry records what was decided, why, and what alternatives were considered.

---

## ADR-001 — Groq + Llama 3.3 70B for LLM Reasoning

**Decision:** Use Groq API (`llama-3.3-70b-versatile`) for lead reasoning instead of a hosted Anthropic model.

> **Update:** Originally used `llama-3.1-70b-versatile`; Groq decommissioned it. Migrated to `llama-3.3-70b-versatile` — same interface, stronger reasoning.

**Rationale:**
- Free tier: 14,400 requests/day — sufficient for demo and testing without incurring cost
- OpenAI-compatible API: trivial to swap for GPT-4 or Claude via a one-line model change
- ~10× faster inference than hosted models, which matters when processing large batches concurrently in Lambda
- No AWS Bedrock setup required for the initial demo

**Trade-off:** Llama 3.1 70B produces slightly less nuanced reasoning than Claude Opus/Sonnet. Acceptable for a sales lead scoring demo; the deterministic scoring pipeline (ScoreBreakdown) carries the quantitative weight anyway.

**Files:** `backend/agent/orchestrator.py`, `backend/config.py`

---

## ADR-002 — fastembed over sentence-transformers for Embeddings

**Decision:** Use `fastembed` (BAAI/bge-small-en-v1.5, ONNX Runtime) for ICP similarity search instead of `sentence-transformers`.

**Rationale:**
- `sentence-transformers` pulls in PyTorch (~1–2 GB), which blows past Lambda's 250 MB deployment ZIP limit
- `fastembed` uses ONNX Runtime (~55 MB total) — Lambda-compatible with room to spare
- No API key required — fully local inference, no external latency
- BAAI/bge-small-en-v1.5 delivers strong semantic similarity for company descriptions at small model size

**Trade-off:** Slightly lower embedding quality vs. larger models, but more than adequate for cosine-similarity ICP matching.

**Files:** `backend/tools/embeddings.py`

---

## ADR-003 — In-Memory Store for Local Development

**Decision:** When `ENVIRONMENT=local`, use Python dicts (`_local_leads`, `_local_jobs`) in `api.py` instead of mocking DynamoDB/S3/SQS.

**Rationale:**
- Eliminates the need for LocalStack or AWS credentials during development
- Upload endpoint runs the full agent pipeline synchronously and returns immediately — fast feedback loop
- Queue depth returns `0`, download endpoint returns `501 Not Implemented` — honest stubs, not silent failures
- The same application code runs in both local and prod modes; only the data layer differs

**Trade-off:** In-memory state resets on server restart. Acceptable for local testing; prod always uses DynamoDB.

**Files:** `backend/api.py:66`, `backend/config.py`

---

## ADR-004 — sqs.py Instead of queue.py

**Decision:** Name the SQS helper module `sqs.py`, not `queue.py`.

**Rationale:**
- Python's stdlib has a `queue` module used by `urllib3` (via `queue.LifoQueue`)
- A file named `queue.py` in the backend directory shadowed the stdlib import, causing `AttributeError` on uvicorn startup before any request was served
- Renaming to `sqs.py` is precise (it only wraps SQS) and eliminates the shadowing permanently

**Files:** `backend/sqs.py`

---

## ADR-005 — FastAPI Route Ordering: /leads/export Before /leads/{lead_id}

**Decision:** Register the `GET /leads/export` route before `GET /leads/{lead_id}` in `api.py`.

**Rationale:**
- FastAPI matches routes in registration order
- With `{lead_id}` registered first, the string `"export"` was matched as a lead ID, returning a 404 instead of the export handler
- Moving `/leads/export` above `/leads/{lead_id}` fixes the match without any other code changes

**Files:** `backend/api.py:276`

---

## ADR-006 — Blob Download for Lead Export

**Decision:** The `exportLeads()` frontend function fetches the NDJSON response as a `Blob`, creates an object URL, and programmatically clicks a hidden `<a>` element to trigger the download.

**Rationale:**
- Setting `<a href="/leads/export" download>` works only for same-origin URLs; it navigates cross-origin (`:3000` → `:8000`) instead of downloading
- The Blob + `URL.createObjectURL()` approach works cross-origin and gives full control over the filename
- Object URL is revoked immediately after the click to avoid memory leaks

**Files:** `frontend/src/lib/api.ts:62`

---

## ADR-007 — ConfirmDialog for Destructive Actions

**Decision:** Destructive actions (Clear All Leads) show a modal `ConfirmDialog` with a warning banner, rather than using `window.confirm()`.

**Rationale:**
- `window.confirm()` is not styleable, blocks the JS thread, and is disabled in some browser contexts (iframes, certain policies)
- The custom dialog focuses the Cancel button by default — safer UX, prevents accidental deletion
- Closes on Escape key and backdrop click — consistent with modal conventions
- The warning banner ("This action cannot be undone") is styled in red inside the dialog for emphasis

**Files:** `frontend/src/components/ConfirmDialog.tsx`

---

## ADR-008 — localStorage for Processed Job History

**Decision:** Completed job IDs are persisted in `localStorage` (key: `sla:processed_jobs`) so the "Processed Jobs" section survives page refresh.

**Rationale:**
- Active jobs (`processingIds`) are React state — ephemeral by design, shown only while the browser tab is open
- Completed jobs are historical — users should be able to see them after refresh without a backend query
- Hydration happens after mount (`useEffect`) to avoid SSR mismatch between server and client HTML
- Job details are fetched live from `GET /jobs/{job_id}` — localStorage stores only IDs, not stale data

**Files:** `frontend/src/hooks/usePersistedJobs.ts`

---

## ADR-009 — 2.5-Second Minimum Processing Spinner Display

**Decision:** The UploadForm processing spinner is shown for a minimum of 2,500 ms after upload, even if the job completes faster.

**Rationale:**
- In local mode, the backend processes leads synchronously before returning the HTTP response — by the time `onUploaded` fires, the job is already `completed`
- Without a minimum duration, the processing spinner appears and disappears in < 100 ms (invisible to the user)
- 2.5 s gives the user enough time to register that processing happened; in AWS async mode the delay is 0 ms (jobs always take longer than 2.5 s)
- Implemented via `jobStartTimes` ref tracking when each job was added, with `setTimeout(delay)` in `onJobComplete`

**Files:** `frontend/src/app/page.tsx`

---

## ADR-010 — Duplicate Lead Detection via SHA-256 Dedup Key

**Decision:** Compute a deterministic 16-character hex fingerprint for each lead (`dedup_key`) from normalized company name + email (or website fallback). Leads matching an existing `dedup_key` are skipped before any LLM or enrichment calls.

**Rationale:**
- Uploading the same file twice previously created duplicate records with different random UUIDs — wasting Groq API quota and polluting the lead list
- A content-based hash allows deduplication without a separate lookup table or secondary index
- Normalizing the company string (lowercase, strip punctuation, collapse whitespace) means "Acme, Inc." and "Acme Inc" are treated as the same lead
- Both intra-batch (same file has duplicate rows) and cross-batch (same lead uploaded before) are handled in a single pass before `process_batch()` is called
- `dedup_key` is stored on `EnrichedLead` so future lookups require no recomputation

**Production upgrade path:** Add a DynamoDB GSI on `dedup_key` and query per-lead before SQS enqueue — O(1) per lead vs. current full-table scan approach in the AWS path.

**Files:** `backend/agent/models.py` (`compute_dedup_key`), `backend/api.py` (`_upload_local`), `backend/agent/orchestrator.py`

---

## ADR-011 — SQS send_message_batch for Fan-Out

**Decision:** Use `send_message_batch` (up to 10 messages per call) when enqueueing leads to SQS, rather than one `send_message` call per lead.

**Rationale:**
- A 100-lead batch with individual sends = 100 SQS API calls; with batching = 10 calls — 10× reduction in API calls and latency
- SQS `send_message_batch` is idempotent per message ID — no additional complexity
- Stays within the SQS 256 KB per-batch message size limit for typical lead payloads

**Files:** `backend/sqs.py`

---

## ADR-012 — ReportBatchItemFailures for Lambda SQS Processing

**Decision:** The Lambda SQS handler returns `batchItemFailures` rather than throwing an exception on partial failures.

**Rationale:**
- Throwing causes SQS to retry the entire batch — leads that succeeded get reprocessed (and re-enriched), wasting quota
- `ReportBatchItemFailures` tells SQS exactly which message IDs failed — only those are retried
- Combined with a DLQ (`maxReceiveCount: 3`), persistently failing leads land in the DLQ for inspection rather than blocking the queue
- CloudFormation sets `FunctionResponseTypes: [ReportBatchItemFailures]` on the event source mapping

**Files:** `backend/lambda_handler.py`, `infrastructure/cloudformation.yaml`

---

## ADR-014 — Groq API Key Stored as SSM SecureString, Fetched at Lambda Cold Start

**Decision:** The Groq API key is stored as an SSM SecureString. Lambda functions receive only the SSM **path** as an environment variable (`GROQ_API_KEY_PATH`) and fetch the key via boto3 at cold start.

**Rationale:**
- CloudFormation does not support `{{resolve:ssm-secure:...}}` dynamic references in `AWS::Lambda::Function` environment variables — it is an explicit AWS limitation
- A plain `NoEcho` CloudFormation parameter works but requires a full stack redeploy every time the key is rotated
- Fetching from SSM at runtime decouples key rotation from infrastructure changes: update SSM → next Lambda cold start picks up the new value automatically
- The key is still encrypted at rest (KMS) as a SecureString; the Lambda role has `ssm:GetParameter` scoped to the exact parameter ARN — no over-permissioning

**To rotate the key (no redeploy needed):**
```bash
aws ssm put-parameter \
  --name /sales-lead-agent/groq-api-key \
  --value gsk_NEW_KEY \
  --type SecureString \
  --overwrite
```

**Local dev fallback:** When `GROQ_API_KEY_PATH` is not set, `config.py` falls back to `GROQ_API_KEY` from `.env`.

**Alternatives considered:**
- `NoEcho` CloudFormation parameter — simpler but requires redeploy to rotate
- `{{resolve:ssm-secure:...}}` — rejected, not supported in Lambda env vars
- AWS Secrets Manager — same runtime-fetch pattern but adds cost; SSM is sufficient for a single API key

**Files:** `backend/config.py` (`_resolve_groq_key`), `infrastructure/cloudformation.yaml` (IAM + env var), `.github/workflows/deploy.yml`

---

## ADR-015 — Replace fastembed/onnxruntime with Stdlib Jaccard Similarity

**Decision:** Remove `fastembed` and `onnxruntime` from dependencies. Replace embedding-based ICP similarity with a pure-Python Jaccard keyword overlap.

**Rationale:**
- `onnxruntime` unzips to ~150 MB; combined with other deps the Lambda ZIP exceeded the 250 MB unzipped limit and could not be deployed
- Lambda container images (10 GB limit) would solve the size issue but add ECR complexity — overkill for a demo
- Jaccard similarity over stop-word-filtered word sets is sufficient for lead scoring: it correctly identifies logistics/healthcare/manufacturing matches against ICP seed examples
- Zero additional dependencies — pure stdlib (`re`, `math`) — ZIP stays under 5 MB unzipped

**Trade-off:** Lower semantic precision than vector embeddings (e.g. "freight" and "logistics" won't match unless both words appear). Acceptable for a demo; a production upgrade would restore embeddings via a Lambda Layer or container image.

**Files:** `backend/tools/embeddings.py`, `backend/requirements.txt`

---

## ADR-016 — DynamoDB Requires Decimal, Not Float

**Decision:** All numeric values written to DynamoDB are converted to `Decimal` via a JSON round-trip (`json.loads(json.dumps(obj), parse_float=Decimal)`). Values read back are converted to `float` via `json.loads(json.dumps(obj, default=str))`.

**Rationale:**
- boto3's DynamoDB SDK raises `TypeError: Float types are not supported` for any Python `float` — including values inside nested dicts/lists
- Pydantic models use `float` throughout (`confidence_score`, `weighted_total`, score breakdown fields)
- The safest conversion is a JSON round-trip: `json.dumps` serialises floats to JSON numbers, `parse_float=Decimal` deserialises them as `Decimal` — no manual field enumeration needed
- The inverse (`default=str`) serialises `Decimal` back to strings then parses them as standard floats for Pydantic

**Files:** `backend/db.py` (`_floats_to_decimals`, `_decimals_to_floats`)

---

## ADR-017 — DynamoDB Nested Map Updates Require Aliased Path Syntax

**Decision:** When updating nested attributes in DynamoDB (e.g. `stats.processed`), use `ExpressionAttributeNames` with separate aliases for each path segment (`#s` → `stats`, `#processed` → `processed`) and reference them as `#s.#processed` in the `UpdateExpression`.

**Rationale:**
- DynamoDB `ExpressionAttributeNames` maps a placeholder to a single attribute name — not a dotted path
- Using `"#processed": "stats.processed"` creates (or updates) a top-level attribute literally named `"stats.processed"` instead of the nested field — stats were silently never incrementing
- The correct nested syntax is `ADD #s.#processed :v` with `{"#s": "stats", "#processed": "processed"}` — each segment aliased separately
- This was the root cause of job stats never updating and jobs never reaching `COMPLETED` status

**Files:** `backend/lambda_handler.py` (`_update_job_progress`)

---

## ADR-018 — Job Completion Detection in Lead Processor

**Decision:** After each lead is processed, `_update_job_progress` uses `ReturnValues="ALL_NEW"` to get the post-update stats atomically. If `processed + errors >= total`, a second `update_item` sets `status = "completed"`.

**Rationale:**
- The batch orchestrator doesn't know when all leads finish — it only fans out messages
- A separate "completion checker" Lambda or Step Functions state machine would add complexity
- Using `ReturnValues="ALL_NEW"` on the existing atomic ADD gives the updated counts in the same call — no extra read needed
- The last lead to finish (whichever Lambda invocation that is) triggers the completion write — safe because DynamoDB updates are atomic and the condition `done >= total` is monotonically true once reached

**Files:** `backend/lambda_handler.py` (`_update_job_progress`)

---

## ADR-019 — Cross-Platform Lambda ZIP via pip --platform Flag

**Decision:** Build the Lambda deployment ZIP on macOS using `pip install --platform manylinux2014_x86_64 --only-binary=:all:` to download Linux x86_64 wheels directly, without Docker.

**Rationale:**
- Lambda runs on Linux x86_64; pip on Apple Silicon downloads `darwin` wheels with ARM `.so` files — incompatible with Lambda
- Docker (`public.ecr.aws/lambda/python:3.12`) solves this but requires Docker Desktop with sufficient disk space (hit I/O errors in practice)
- `--platform manylinux2014_x86_64 --only-binary=:all:` instructs pip to fetch pre-built Linux wheels from PyPI directly — no compilation, no Docker needed
- After install, `boto3`/`botocore`/`s3transfer`/`jmespath` are deleted (~26 MB saved) since Lambda's managed runtime already includes them

**Trade-off:** Fails if a package has no pre-built Linux wheel on PyPI. All packages in this project (`pydantic-core`, `groq`, `fastapi`, etc.) have manylinux wheels — no issue in practice.

**Files:** `backend/requirements.txt`, deploy instructions

---

## ADR-013 — CORS: Explicit Origin Allowlist

**Decision:** In local mode, CORS `allow_origins` is an explicit list `["http://localhost:3000", "http://127.0.0.1:3000"]` rather than `["*"]`.

**Rationale:**
- `"*"` does not work with credentialed requests and is bad practice even in dev
- Explicit list mirrors production behavior (a specific frontend domain) — avoids surprises when switching environments
- `is_local` flag in `config.py` controls which list is used; `.env` is loaded by walking up the directory tree from `backend/` so the flag resolves correctly regardless of working directory

**Files:** `backend/api.py:50`, `backend/config.py`

---

## ADR-020 — Idempotent Lead Storage via Conditional DynamoDB Write

**Decision:** `db.put_lead()` uses a `ConditionExpression="attribute_not_exists(lead_id)"` conditional write and returns `True` if the item was stored, `False` if it already existed. The Lambda handler only increments job stats when `put_lead` returns `True`.

**Rationale:**
- SQS guarantees at-least-once delivery — a lead message can be retried after a transient error
- Without idempotency, a retried message would re-process and re-store the same lead, inflating `processed` stats and potentially exceeding `total`, breaking the completion check
- DynamoDB conditional writes are atomic — no separate read-then-write race condition
- The boolean return value lets the caller decide whether to count the lead without requiring a second read
- `ConditionalCheckFailedException` from boto3 is the expected "already exists" signal and is caught explicitly; all other `ClientError` exceptions are re-raised

**Files:** `backend/db.py` (`put_lead`), `backend/lambda_handler.py` (`lead_processor`)

---

## ADR-021 — DynamoDB Scan Requires Explicit `Limit` for Cursor Pagination

**Decision:** `db.scan_leads()` passes `Limit` directly to the DynamoDB `scan()` call and returns `response.get("LastEvaluatedKey")` as the pagination cursor. The API endpoint accepts a `cursor` (base64-encoded JSON) and `limit` parameter.

**Rationale:**
- Without a `Limit`, DynamoDB scans the entire table and never returns `LastEvaluatedKey` — pagination was impossible; the frontend was capped at 20 items regardless of how many leads existed
- With `Limit=N`, DynamoDB stops after examining N items and returns `LastEvaluatedKey` if more items exist — one scan call per page
- `FilterExpression` is applied after `Limit` — the actual returned count may be less than `Limit` if many items fail the score filter; this is a known DynamoDB scan trade-off acceptable for a demo
- The cursor is JSON-serialized and base64-encoded for URL safety; the API decodes it back to a DynamoDB key on subsequent requests

**Files:** `backend/db.py` (`scan_leads`), `backend/api.py` (`list_leads`)

---

## ADR-022 — React Ref Guard for Single-Fire Polling Callback

**Decision:** `JobStatusCard` uses a `completedFired = useRef(false)` guard to ensure `onComplete(jobId)` is called exactly once, even though `useJobStatus` continues polling after completion.

**Rationale:**
- `useJobStatus` polls `/jobs/{jobId}` every second; once the job reaches `completed` or `failed`, subsequent polls return the same terminal status
- Each poll triggers a state update → React re-runs the `useEffect` → `onComplete` was being called on every subsequent render cycle, not just the first
- A `useRef` flag persists across re-renders without causing a re-render itself — it's the correct primitive for "fire once" logic
- Alternatives (polling stop, status caching) would require more invasive changes to `useJobStatus`; the ref guard is local to `JobStatusCard` and self-contained

**Files:** `frontend/src/components/JobStatusCard.tsx`

---

## ADR-023 — Cursor-Based Frontend Pagination with History Array

**Decision:** `useLeads` maintains a `cursors` ref array where `cursors[n]` holds the DynamoDB cursor needed to fetch page `n+1`. Page 1 uses no cursor (`undefined`). Previous-page navigation reuses the stored cursor for that page index.

**Rationale:**
- DynamoDB cursor-based pagination is forward-only by design — there is no built-in "previous page" cursor
- Storing the cursor for each page as it is fetched allows backward navigation: `cursors[page-2]` is the cursor for the page before the current one
- The array is stored in a `useRef` (not `useState`) so updates don't trigger re-renders
- When `scoreMin` changes, the cursor array is reset to `[undefined]` and the user returns to page 1 — ensures filters don't mix cursor state from a different dataset
- Page size is fixed at 20 per page matching the DynamoDB `Limit` — consistent UX

**Files:** `frontend/src/hooks/useLeads.ts`, `frontend/src/app/page.tsx`

---

## ADR-024 — Voyage AI Multimodal Embeddings with Jaccard Fallback

**Decision:** ICP similarity search uses Voyage AI (`voyage-multimodal-3.5` → `voyage-multimodal-3` probe order) when `VOYAGE_API_KEY` is available. Falls back to Jaccard keyword similarity if the key is unset, the package is not installed, or any API call fails (including rate limit / quota exhaustion).

**Rationale:**
- Semantic embeddings capture meaning ("freight" ≈ "logistics") whereas Jaccard only matches exact tokens
- Keeping Jaccard as a fallback means the Lambda ZIP stays tiny (no onnxruntime) and the system degrades gracefully when the Voyage free tier is exhausted
- Voyage API key stored as SSM SecureString (`/sales-lead-agent/voyage-api-key`) — same rotation pattern as Groq, no redeploy needed
- `_init_voyage()` probes models at cold start; whichever responds becomes the active model for the container lifetime
- `match_reason` on each `SimilarityResult` records which method was used (`voyage-multimodal-3.5` or `Jaccard`) for observability

**Files:** `backend/tools/embeddings.py`, `backend/config.py`, `infrastructure/cloudformation.yaml`

---

## ADR-025 — Orchestrator Owns All Fan-Out; API Only Uploads to S3

**Decision:** `_upload_aws()` in `api.py` uploads the file to S3 and creates the DynamoDB job record, but does **not** enqueue to SQS. The `batch_orchestrator` Lambda (triggered by S3 ObjectCreated) exclusively owns dedup filtering and SQS fan-out.

**Rationale:**
- The original design had the API enqueue directly to SQS AND the orchestrator enqueue again on the S3 trigger — every lead was processed twice
- Double-enqueue wasted Groq API calls and caused inflated `processed` counts in job stats
- The `put_lead` conditional write prevented double-storage, but doubled LLM costs
- Removing the enqueue from the API makes the orchestrator the single source of truth for what gets processed

**Files:** `backend/api.py` (`_upload_aws`), `backend/lambda_handler.py` (`batch_orchestrator`)

---

## ADR-026 — Dedup Key GSI for O(1) Cross-Batch Duplicate Detection on AWS

**Decision:** A `dedup_key-index` GSI (`KEYS_ONLY` projection) is added to the leads DynamoDB table. The orchestrator queries this GSI per-lead before enqueuing to SQS. If the key exists, the lead is skipped.

**Rationale:**
- Without a GSI, cross-batch dedup requires a full table scan per lead — O(N×M) for N leads against M existing records
- `KEYS_ONLY` projection minimises storage cost (only `lead_id` and `dedup_key` are stored in the index)
- Both intra-batch (via `seen` set) and cross-batch (via GSI query) dedup happen in the orchestrator before any SQS enqueue — no LLM calls wasted on duplicates

**Production note:** Leads stored before this feature was added have no `dedup_key` attribute and are invisible to the GSI — they cannot cause false-positive matches.

**Files:** `backend/db.py` (`lead_exists_by_dedup_key`), `backend/lambda_handler.py` (`batch_orchestrator`), `infrastructure/cloudformation.yaml`

---

## ADR-027 — Immediate Job Completion When All Leads Are Duplicates

**Decision:** If the orchestrator's dedup pass results in zero unique leads, the job is immediately set to `completed` with `total=0` and `duplicates=N` in stats — no SQS messages are sent.

**Rationale:**
- When all leads are duplicates, `total=0` after dedup. The processor completion check is `total > 0 and done >= total` — with `total=0` this is always `False`, leaving the job permanently stuck in `processing`
- Completing immediately is semantically correct: there is genuinely nothing left to process
- The `duplicates` counter in job stats provides visibility into why the job completed with zero leads processed

**Files:** `backend/lambda_handler.py` (`batch_orchestrator`)

---

## ADR-028 — Separate Count Scan for Accurate Total in Paginated List

**Decision:** `db.count_leads()` performs a `Select=COUNT` DynamoDB scan (no item data transferred) to get the real total count. This is called separately from `scan_leads()` on each `GET /leads` request.

**Rationale:**
- `scan_leads()` returns only one page of items — `len(items)` equals the page size (20), not the total
- The frontend was showing "Leads (showing: 20 / 20)" on every page because `total` was set to `len(items)`
- `Select=COUNT` scans all pages internally but transfers no item payloads — significantly cheaper than fetching all items
- Acceptable for a demo dataset; production would use a separate counter attribute maintained by Lambda on each write

**Files:** `backend/db.py` (`count_leads`), `backend/api.py` (`list_leads`)

---

## ADR-029 — Manual Deploy Trigger; Tests Run on Every Push

**Decision:** The GitHub Actions workflow runs lint + tests on every push to any branch. Build and deploy only run when manually triggered (`workflow_dispatch`) with an environment choice (staging / production).

**Rationale:**
- Auto-deploying on every push to `main` caused unintended production deploys during rapid iteration
- Separating concerns: CI (always) vs CD (intentional) — engineers can commit freely without fear of accidental deploys
- `workflow_dispatch` with an environment dropdown gives explicit control; `permissions: contents: write` allows the deploy job to create release tags
- Black formatting is enforced via a local pre-commit hook rather than blocking every push

**Files:** `.github/workflows/deploy.yml`
