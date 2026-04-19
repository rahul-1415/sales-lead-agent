# Live Demo Walkthrough

## Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 14, Tailwind CSS — deployed on Vercel |
| Backend | FastAPI + Mangum — deployed on AWS Lambda |
| Queue | AWS SQS |
| Database | AWS DynamoDB |
| Storage | AWS S3 |
| AI Reasoning | Groq API (Llama 3.3 70B) |
| Infra-as-Code | AWS CloudFormation |
| CI/CD | GitHub Actions |

---

## Demo Flow

### 1. Upload a CSV of leads
- Click **Upload CSV** and select a file (e.g. `tests/leads-3.json`)
- The spinner appears and the **Processing Jobs** card shows the job in progress
- Behind the scenes: file → S3 → BatchOrchestrator Lambda → SQS → LeadProcessor Lambda (one invocation per lead)

### 2. Watch processing complete
- The Processing Jobs card transitions to **Processed Jobs** automatically (no refresh needed)
- Job stats show: total leads, priority / standard / research / rejected counts

### 3. View the enriched leads table
- Leads appear in the table with: Company, Industry, Size, Score (%), Action badge, AI Reasoning, Tags
- Click any **AI Reasoning** cell to expand the full Groq-generated explanation in a modal

### 4. Upload the same file again
- An amber banner appears: **"X duplicates skipped"**
- Demonstrates SHA-256 dedup key — same company+email fingerprint is detected cross-batch

### 5. Show the lead detail page
- Click any company name to see the full enriched lead: score breakdown, email validation, similarity results, tags

### 6. Export leads
- Click **Export** to download all leads as NDJSON

---

## Key Talking Points

### AI Agent Pipeline (per lead)
Each lead goes through 6 deterministic + AI steps:
1. **Email validation** — checks format and deliverability
2. **Company enrichment** — industry, size, HQ, funding, tech stack
3. **ICP similarity** — keyword match against 4 ideal customer profiles
4. **Score breakdown** — weighted sum across 5 dimensions (industry fit 30%, size fit 25%, geo 15%, activity 15%, ICP 15%)
5. **LLM reasoning** — Groq generates a plain-English explanation of the score
6. **Routing decision** — priority / standard / research / reject based on thresholds

### Why Groq, not Claude?
Groq's Llama 3.3 70B inference is ~10× faster than hosted Claude for short completions. Processing 50–100 leads concurrently in Lambda makes latency the bottleneck — sub-second p50 matters. The deterministic scoring pipeline carries the quantitative weight; LLM only explains it.

### Why serverless?
- **No idle cost** — Lambda charges only for actual processing time
- **Automatic scale** — SQS fans out to as many Lambda invocations as needed; a 500-lead batch runs in parallel, not sequentially
- **Decoupled** — API returns `job_id` instantly; processing happens asynchronously

### Security
- Groq API key stored as SSM SecureString — never in code or CloudFormation parameters
- Key rotation: update SSM only, no redeploy needed
- Lambda IAM role is least-privilege: scoped S3 ARNs, single SSM parameter, specific DynamoDB tables

---

## Test Files

| File | Contents |
|---|---|
| `tests/leads-1.json` | 3 leads — logistics, healthcare, manufacturing |
| `tests/leads-2.json` | 6 leads — mixed industries |
| `tests/leads-3.json` | 7 leads — includes duplicates from leads-1 to demo dedup |

---

## Production Endpoints

| Resource | Value |
|---|---|
| API Gateway | `https://zeix7o11u7.execute-api.us-east-1.amazonaws.com/production` |
| Frontend (Vercel) | your Vercel URL |
| DynamoDB leads table | `leads-production` |
| DynamoDB jobs table | `batch-jobs-production` |
| S3 input bucket | `sales-lead-agent-input-production-661952267320` |
| SQS queue | `sales-lead-agent-queue-production` |
| DLQ | `sales-lead-agent-dlq-production` |

---

## Ops Runbook

### Check live logs
```bash
aws logs tail /aws/lambda/sales-lead-agent-processor-production --follow
aws logs tail /aws/lambda/sales-lead-agent-api-production --follow
```

### Check queue depth
```bash
aws sqs get-queue-attributes \
  --queue-url https://sqs.us-east-1.amazonaws.com/661952267320/sales-lead-agent-queue-production \
  --attribute-names ApproximateNumberOfMessages ApproximateNumberOfMessagesNotVisible
```

### Check DLQ (failed leads)
```bash
aws sqs get-queue-attributes \
  --queue-url https://sqs.us-east-1.amazonaws.com/661952267320/sales-lead-agent-dlq-production \
  --attribute-names ApproximateNumberOfMessages
```

### Rotate Groq API key (no redeploy needed)
```bash
aws ssm put-parameter \
  --name /sales-lead-agent/groq-api-key \
  --value gsk_NEW_KEY \
  --type SecureString \
  --overwrite
```

### Redeploy Lambda after code change
```bash
cd backend
rm -rf package && pip install -r requirements.txt \
  --target ./package --platform manylinux2014_x86_64 --only-binary=:all: --upgrade
rm -rf ./package/boto3 ./package/boto3-*.dist-info \
       ./package/botocore ./package/botocore-*.dist-info \
       ./package/s3transfer ./package/s3transfer-*.dist-info \
       ./package/jmespath ./package/jmespath-*.dist-info
cp -r agent tools api.py lambda_handler.py config.py db.py storage.py sqs.py ./package/
cd package && zip -r ../sales-lead-agent.zip . -x "*.pyc" -x "*/__pycache__/*" && cd ..
aws s3 cp sales-lead-agent.zip s3://sales-lead-agent-lambda-zips/lambda/sales-lead-agent.zip
for fn in api processor orchestrator; do
  aws lambda update-function-code \
    --function-name sales-lead-agent-${fn}-production \
    --s3-bucket sales-lead-agent-lambda-zips \
    --s3-key lambda/sales-lead-agent.zip --publish
done
```
