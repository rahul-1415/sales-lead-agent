# System Design — Sales Lead Agent

## Architecture Overview

Serverless pipeline on AWS: API Gateway → Lambda (FastAPI/Mangum) → SQS → Lambda (processor) → DynamoDB + S3.
Frontend is Next.js deployed on Vercel, calling the API Gateway endpoint.

```
CSV / JSON upload
    │
    ▼
API Gateway → ApiFunction (FastAPI/Mangum)
                    │
                    ├─ Writes job record to DynamoDB (batch_jobs table)
                    └─ Stores raw file to S3 (input bucket)
                              │  (S3 ObjectCreated trigger)
                              ▼
                    BatchOrchestratorFunction
                              │
                    ┌─────────┴──────────────────┐
                    │  Dedup filter               │
                    │  - compute dedup_key/lead   │
                    │  - query dedup_key-index GSI│
                    │  - skip existing leads      │
                    └─────────┬──────────────────┘
                              │  (one SQS msg per unique lead)
                              ▼
                         LeadQueue (SQS)
                              │
                              ▼
                    LeadProcessorFunction
                              │
                    ┌─────────┴─────────────┐
                    │   SalesLeadAgent       │
                    │  (per-lead pipeline)   │
                    │  1. Email validation   │
                    │  2. Company enrichment │
                    │  3. Embedding / RAG    │
                    │  4. Score breakdown    │
                    │  5. LLM reasoning      │
                    │  6. Routing action     │
                    └─────────┬─────────────┘
                              │
                    DynamoDB (leads table) + S3 (output bucket)
```

---

## Key Technical & Design Decisions

### 1. Groq for LLM Reasoning (not Claude/OpenAI)
**Decision**: Use Groq (Llama 3.3 70B) for the per-lead reasoning step.

**Why**: Groq's inference is ~10x faster than hosted Claude for short completions. Processing batches of 50–100 leads concurrently in Lambda makes latency the bottleneck — Groq's sub-second p50 matters here. Claude is used for the agentic orchestration layer (this repo) where reasoning quality matters more than speed.

**Tradeoff**: Less reasoning quality vs Claude Opus, but sufficient for structured lead scoring prose.

---

### 2. Deterministic Scoring + LLM Explanation (not pure LLM scoring)
**Decision**: Score is computed deterministically from a `ScoreBreakdown` (weighted sum of 5 components). The LLM only explains the score in plain English — it does not produce the score.

**Why**: Pure LLM scoring is non-deterministic, hard to audit, and expensive. Deterministic scoring is reproducible and fast; the LLM adds the human-readable justification on top.

**Components and weights**:
| Component | Weight |
|---|---|
| Industry fit | 30% |
| Company size fit | 25% |
| Geographic fit | 15% |
| Recent activity (funding/hiring) | 15% |
| Similarity to ICP | 15% |

---

### 3. SHA-256 Dedup Key for Duplicate Lead Detection
**Decision**: Each lead gets a 16-char hex dedup key: `SHA-256(normalize(company) + "|" + normalize(email ?? website ?? ""))[:16]`.

**Why**: Re-uploading the same CSV would otherwise reprocess every lead, waste Groq API calls, and pollute the lead list with duplicates. The key is stable across minor variations ("Acme, Inc." and "Acme Inc" hash identically).

**Scope**: Both intra-batch (same file) and cross-batch (against all previously stored leads).

**Implementation**: `compute_dedup_key()` in `backend/agent/models.py`, checked in `_upload_local()` in `backend/api.py`.

---

### 4. Groq API Key — SSM SecureString fetched at Lambda Cold Start
**Decision**: The Groq API key is stored as an SSM SecureString. Lambda functions receive only the SSM **path** as an env var (`GROQ_API_KEY_PATH`) and fetch the value via boto3 at cold start.

**Why**: CloudFormation does not support `{{resolve:ssm-secure:...}}` in Lambda environment variables (hard AWS limitation). A plain `NoEcho` CloudFormation parameter works but requires a full stack redeploy to rotate the key. Fetching from SSM at runtime means key rotation only requires updating SSM — no CloudFormation redeploy, no code change.

**How to rotate the key**:
```bash
aws ssm put-parameter \
  --name /sales-lead-agent/groq-api-key \
  --value gsk_NEW_KEY \
  --type SecureString \
  --overwrite
```
Next Lambda cold start picks up the new value automatically.

**IAM**: Lambda execution role has `ssm:GetParameter` scoped to the exact parameter ARN.

**Local dev**: Falls back to `GROQ_API_KEY` in `.env` when `GROQ_API_KEY_PATH` is not set.

---

### 5. CloudFormation Circular Dependency Resolution
**Decision**: Lambda env vars reference S3 bucket names via `!Sub`-constructed strings instead of `!Ref InputBucket` / `!GetAtt InputBucket.Arn`.

**Why**: The dependency graph `InputBucket → BatchOrchestratorFunction → LambdaExecutionRole → InputBucket` creates a circular reference that CloudFormation cannot resolve. Breaking one edge by using a predictable name (`sales-lead-agent-input-${Environment}-${AWS::AccountId}`) instead of a resource reference resolves the cycle.

---

### 6. SQS Visibility Timeout ≥ Lambda Timeout
**Decision**: SQS visibility timeout is set to 300s; Lead Processor Lambda timeout is 270s.

**Why**: If Lambda times out mid-batch, the SQS message must stay invisible long enough for the timeout to complete. If visibility timeout < Lambda timeout, the message becomes visible again while Lambda is still processing, causing duplicate processing.

---

### 7. Pydantic v2 `@computed_field` for `weighted_total`
**Decision**: `ScoreBreakdown.weighted_total` uses `@computed_field @property` instead of `@property`.

**Why**: Pydantic v2 does not serialize bare `@property` fields. Without `@computed_field`, `weighted_total` is excluded from `.model_dump()` and JSON responses, causing the frontend to display `NaN%`. The `@computed_field` decorator opts the property into serialization explicitly.

---

### 8. Sequential Processing Within Lambda, SQS Parallelism Across Lambdas
**Decision**: `process_batch()` iterates leads sequentially. Parallelism comes from multiple Lambda invocations triggered by SQS.

**Why**: Concurrent threading inside a single Lambda invocation adds complexity and thread-safety concerns (shared Groq client). SQS naturally fans out to multiple Lambda instances, each processing its chunk sequentially. Simpler code, same throughput.

---

### 9. Voyage AI Embeddings with Jaccard Fallback
**Decision**: ICP similarity uses Voyage AI (`voyage-multimodal-3.5` → `voyage-multimodal-3`) when `VOYAGE_API_KEY` is set; falls back to stdlib Jaccard keyword overlap otherwise.

**Why**: `onnxruntime` unzips to ~150 MB, exceeding the Lambda 250 MB ZIP limit. Voyage API keeps the ZIP under 5 MB while providing semantic similarity ("freight" ≈ "logistics"). Jaccard fallback ensures the system works even when the API key is unset or the free tier is exhausted. Key stored in SSM SecureString — same rotation pattern as Groq.

---

### 10. DynamoDB Decimal Conversion on All Reads and Writes
**Decision**: All floats are converted to `Decimal` before writing to DynamoDB, and back to `float` after reading, via JSON round-trips in `db.py`.

**Why**: boto3's DynamoDB SDK rejects Python `float` with `TypeError` — even floats nested inside dicts or lists. A JSON round-trip (`parse_float=Decimal`) is the safest conversion — no manual field enumeration, handles arbitrary nesting.

---

### 11. Job Completion Detected by Last Lead Processor
**Decision**: After each lead is stored, `_update_job_progress` reads the updated stats back (`ReturnValues="ALL_NEW"`) and marks the job `completed` if `processed + errors >= total`.

**Why**: No central coordinator knows when all leads finish. The last Lambda invocation to complete naturally detects completion via atomic counter comparison. No extra reads, no polling loop, no Step Functions needed.

---

## Infrastructure

| Resource | Purpose |
|---|---|
| API Gateway (HTTP) | Public endpoint, routes to ApiFunction |
| ApiFunction (Lambda) | FastAPI app via Mangum; handles upload, job status, lead list |
| LeadProcessorFunction (Lambda) | Processes leads from SQS; runs SalesLeadAgent pipeline |
| BatchOrchestratorFunction (Lambda) | Triggered by S3 ObjectCreated; splits large batches into SQS messages |
| SQS (LeadQueue) | Decouples upload from processing; enables parallel Lambda scaling |
| DynamoDB (leads) | Stores enriched leads; GSI on `batch_id` and `dedup_key` |
| DynamoDB (batch_jobs) | Tracks job lifecycle and stats |
| S3 (input) | Stores raw uploaded files; triggers BatchOrchestratorFunction |
| S3 (output) | Stores enriched lead JSON results |
| SSM Parameter Store | Stores Groq and Voyage AI API keys as SecureStrings |
| CloudWatch Alarms | Lambda error rate and DLQ depth monitoring |
| GitHub Actions | CI (lint + test on every push); CD (manual `workflow_dispatch`) |
