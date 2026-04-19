# Architecture Decision Records

This document tracks key technical and design decisions made during the development of the Sales Lead Agent. Each entry records what was decided, why, and what alternatives were considered.

---

## ADR-001 — Groq + Llama 3.1 70B for LLM Reasoning

**Decision:** Use Groq API (`llama-3.1-70b-versatile`) for lead reasoning instead of a hosted Anthropic model.

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

## ADR-013 — CORS: Explicit Origin Allowlist

**Decision:** In local mode, CORS `allow_origins` is an explicit list `["http://localhost:3000", "http://127.0.0.1:3000"]` rather than `["*"]`.

**Rationale:**
- `"*"` does not work with credentialed requests and is bad practice even in dev
- Explicit list mirrors production behavior (a specific frontend domain) — avoids surprises when switching environments
- `is_local` flag in `config.py` controls which list is used; `.env` is loaded by walking up the directory tree from `backend/` so the flag resolves correctly regardless of working directory

**Files:** `backend/api.py:50`, `backend/config.py`
