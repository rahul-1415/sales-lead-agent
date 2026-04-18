# AI Sales Lead Generation Agent

An agentic, serverless AWS pipeline that ingests raw lead data, enriches it via LLM-powered tools, scores each lead, and surfaces results through a React dashboard.

## Architecture

```
Upload (CSV/JSON)
      │
API Gateway → Lambda (batch-orchestrator) → SQS
                                              │
                                         Lambda (lead-processor)
                                              │
                                    ┌─────────┴──────────┐
                                DynamoDB              S3 (output)
                                    │
                             React Dashboard
```

## Stack

| Layer | Tech |
|---|---|
| Agent | Python + Claude API |
| API | FastAPI + Mangum (Lambda) |
| Queue | SQS |
| Storage | DynamoDB + S3 |
| Infra | CloudFormation |
| CI/CD | GitHub Actions |
| Frontend | React + TypeScript + Tailwind |

## Local Dev

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cp ../.env.example ../.env   # fill in values
uvicorn api:app --reload
```

## Deploy

```bash
# Push infrastructure
aws cloudformation deploy \
  --template-file infrastructure/cloudformation.yaml \
  --stack-name sales-lead-agent \
  --capabilities CAPABILITY_IAM

# CI/CD handles Lambda deploys on push to main
```

## Testing

```bash
cd backend
pytest tests/ -v
```
