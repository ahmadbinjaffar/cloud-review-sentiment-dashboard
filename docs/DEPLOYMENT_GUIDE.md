# Deployment Guide — AWS (serverless, free-tier)

> **Status: nothing has been deployed.** This guide and the scripts it describes
> are opt-in; they only act when *you* run them with AWS credentials configured.
> The default daily workflow stays 100 % local (`scripts/run_local.ps1`).

## 1. Architecture on AWS

```
CSV/JSON drop ──► S3 uploads bucket ──(ObjectCreated)──┐
                                                       ▼
Browser ──► API Gateway (HTTP API) ──────────► Lambda (single entry point:
   ▲                                            src.handlers.router.lambda_handler)
   │                                                  │  ingest / process / query
   │                                                  ▼
   │                                            DynamoDB (reviews table)
   │
   └── static dashboard ◄── S3 website bucket     CloudWatch Logs (function + API)
```

One Lambda serves every route — the exact same `lambda_handler` the local
FastAPI server calls. S3 upload events hit the same function (the router
detects `Records[].s3` payloads). Defined in `infrastructure/template.yaml`
(AWS SAM).

## 2. Prerequisites

| Tool | Install | Check |
|---|---|---|
| AWS CLI v2 | https://docs.aws.amazon.com/cli/ | `aws --version` |
| AWS SAM CLI | https://docs.aws.amazon.com/serverless-application-model/ | `sam --version` |
| Python 3.12 runtime | provided by Lambda; local build just needs python + pip | `python --version` |
| AWS account | free tier is enough at this scale | `aws sts get-caller-identity` |

Configure credentials once (`aws configure`, or an AWS profile / SSO). Never
commit credentials — `samconfig.toml` may hold account/region only.

## 3. Deploy

```powershell
cd Cloud_Project
.\scripts\deploy.ps1 -StackName reviewpulse-dev -Region us-east-1
# optional: use the Hugging Face engine instead of offline VADER
.\scripts\deploy.ps1 -SentimentEngine huggingface -HfToken hf_xxx
```

What the script does:

1. Verifies `aws` + `sam` are installed and credentials resolve.
2. Stages a **clean** Lambda bundle in `infrastructure/.build/`
   (only `src/` + `lambda-requirements.txt` — never `.venv`, `data/`, or logs).
3. `sam build` + `sam deploy` with `CAPABILITY_IAM`.
4. `aws s3 sync dashboard/ → website bucket` (unless `-SkipDashboardSync`).
5. Prints the API URL, dashboard URL, bucket names, table name.

Typical first run: ~3–5 minutes. The stack creates **no billable always-on
resources** (Lambda, HTTP API, DynamoDB on-demand, S3, CloudWatch logs).

## 4. Using the deployed pipeline

| Action | How |
|---|---|
| Open dashboard | `DashboardUrl` output (S3 website) |
| Query API | `ApiUrl` output — identical routes to the local server (`/summary`, `/reviews`, `/trends`, `/keywords`, `/process`, …) |
| Bulk-ingest | Upload CSV/JSON under `s3://<uploads-bucket>/uploads/` → automatic ingestion by the S3 event; or `POST /ingest` with `{filename, content}` |
| Process | `POST /process {"limit": 200}` (VADER runs inside Lambda — zero external AI cost) |
| Point the local dashboard at the cloud API | `http://…/ui/?apiBase=https://<api>` |

## 5. Parameters

| Parameter | Default | Notes |
|---|---|---|
| `ProjectName` | `reviewpulse` | name prefix |
| `Environment` | `dev` | `dev` / `prod` |
| `SentimentEngine` | `vader` | `vader`/`textblob` run offline in Lambda; `huggingface` calls the Inference API |
| `HfToken` | *(empty, NoEcho)* | only for the `huggingface` engine |
| `NeutralThreshold` | `0.15` | neutral band (proposal's 3-class rule) |
| `LogRetentionDays` | `14` | CloudWatch retention |

## 6. Least-privilege IAM (what the Lambda role can do)

- **DynamoDB**: `GetItem/PutItem/UpdateItem/DeleteItem/Batch*/Query/Scan/DescribeTable`
  on the one reviews table only.
- **S3**: `s3:GetObject` on `uploads/*` of the uploads bucket only (reads files
  that triggered the event).
- **Logs**: `CreateLogStream`/`PutLogEvents` on its own log group.
- No `s3:*`, no `dynamodb:*`, no IAM, no VPC, no KMS grants. The dashboard
  bucket is public-read for website hosting only; the uploads bucket blocks all
  public access and auto-expires objects after 30 days.

## 7. Free-tier notes

At the prototype scale (≈1.2 K reviews) every service stays inside its monthly
always-free allowance (Lambda 1 M requests, API GW 1 M requests, DynamoDB 25
RCU/WCU, S3 5 GB, CloudWatch 5 GB logs). See the live estimate panel in the
dashboard, `experiments/RESULTS_SUMMARY.md` (§ d), and `results/cost_model.csv`
with `results/cost_sources.json` (every price carries its source URL).

## 8. Teardown

```powershell
.\scripts\teardown.ps1 -StackName reviewpulse-dev -Region us-east-1
```

Empties both buckets, then `sam delete`. Verify in the AWS console that no
resources remain (S3 + CloudWatch log groups are the usual stragglers).

## 9. Troubleshooting

| Symptom | Fix |
|---|---|
| `sam: command not found` | install SAM CLI, reopen the terminal |
| `Unable to locate credentials` | `aws configure` or set `AWS_PROFILE` |
| Deploy hangs on changeset | check region; the script uses `--no-confirm-changeset` |
| Dashboard loads but API calls fail (CORS) | the HTTP API is created with CORS enabled by SAM defaults; redeploy |
| S3 upload doesn't ingest | key must be under `uploads/`; check Lambda logs in CloudWatch |
| Lambda import errors | only `src/` is packaged; keep imports inside the `src` package |
