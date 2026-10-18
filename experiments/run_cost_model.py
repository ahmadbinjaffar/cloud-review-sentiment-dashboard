"""Experiment D — monthly cost model: AWS free tier vs pay-as-you-go vs t3.micro vs SaaS.

Workloads: 1K / 10K / 100K / 1M reviews per month. Every price is a current
published rate recorded with its source URL and access date (2026-10-15) in
results/cost_sources.json — nothing is invented; unverifiable items are marked
as such. Compute usage is measured from THIS pipeline (per-review processing
time, payload bytes), not assumed.

Outputs: results/cost_model.csv, results/cost_model_detail.json,
results/cost_sources.json, figures/cost_model.png.
"""
from __future__ import annotations

import json
import math
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from experiments.common import (
    load_corpus,
    run_metadata,
    save_fig,
    seed_everything,
    style_axes,
    write_csv,
    write_json,
)
from experiments.run_throughput import build_csv_content

WORKLOADS = (1_000, 10_000, 100_000, 1_000_000)
REVIEWS_PER_BATCH = 200          # MAX_REVIEWS: one ingest POST / one Lambda batch
LAMBDA_MEMORY_MB = 512           # SAM template function memory
DASHBOARD_GETS_PER_BATCH = 20    # assumption: 20 dashboard reads per upload batch
READS_PER_REVIEW = 10            # 20 page reads x 100 items / 200 reviews
LOG_BYTES_PER_REVIEW = 1_000     # assumption: ~1 KB log line per processed review

# --- published prices (source + date in SOURCES) --------------------------
P_LAMBDA_REQ_M = 0.20                # per 1M requests
P_LAMBDA_GB_S = 0.0000166667         # per GB-second (x86)
P_APIGW_REQ_M = 1.00                 # per 1M HTTP API requests
P_DYNAMO_WRITE_M = 0.625             # per 1M write request units (on-demand)
P_DYNAMO_READ_M = 0.125              # per 1M read request units (on-demand)
P_DYNAMO_GB = 0.25                   # per GB-month (standard)
P_S3_GB = 0.023                      # per GB-month (standard)
P_CW_INGEST_GB = 0.50                # per GB ingested (standard logs)
P_CW_STORAGE_GB = 0.03               # per GB-month archived
P_EC2_T3_MICRO_HR = 0.0104           # on-demand us-east-1
P_EBS_GP3_GB = 0.08                  # per GB-month
P_COMPREHEND_UNIT = 0.0001           # per unit = 100 chars, 300-char min/request
P_MONKEYLEARN_MONTH = 299.0          # starting price, third-party guide

# --- free-tier allowances (monthly) --------------------------------------
FT_LAMBDA_REQ = 1_000_000            # always free
FT_LAMBDA_GB_S = 400_000             # always free
FT_APIGW_REQ = 1_000_000             # legacy 12-month free tier
FT_DYNAMO_GB = 25                    # storage allowance
FT_DYNAMO_REQUESTS = 0.0             # 25 WCU/RCU cover PROVISIONED only; we use on-demand
FT_CW_INGEST_GB = 5.0                # shared 5 GB logs quota
FT_S3_GB = 5.0                       # legacy 12-month: 5 GB + 20K GET/2K PUT

SOURCES = [
    {"item": "AWS Lambda requests", "price": "$0.20 per 1M requests",
     "source": "aws.amazon.com/lambda/pricing (official) + costgoat.com/pricing/aws-lambda",
     "url": "https://aws.amazon.com/lambda/pricing/", "accessed": "2026-10-15", "status": "verified"},
    {"item": "AWS Lambda duration", "price": "$0.0000166667 per GB-s (x86)",
     "source": "aws.amazon.com/lambda/pricing (official worked example)",
     "url": "https://aws.amazon.com/lambda/pricing/", "accessed": "2026-10-15", "status": "verified"},
    {"item": "Lambda free tier", "price": "1M requests + 400,000 GB-s / month, always free",
     "source": "aws.amazon.com/lambda/pricing (official); perfsys.com/blog/aws-for-free",
     "url": "https://aws.amazon.com/lambda/pricing/", "accessed": "2026-10-15", "status": "verified"},
    {"item": "API Gateway HTTP API", "price": "$1.00 per 1M requests (first 300M), us-east-1",
     "source": "costgoat.com/pricing/amazon-api-gateway (official AWS pricing page cited)",
     "url": "https://costgoat.com/pricing/amazon-api-gateway", "accessed": "2026-10-15",
     "status": "verified-third-party"},
    {"item": "API Gateway free tier", "price": "1M API calls/month for 12 months (legacy accounts; newer accounts get credit instead)",
     "source": "builder.aws.com AWS Free Tier guide; costgoat.com",
     "url": "https://builder.aws.com/content/3IQ2c19Fk9N0wQdSXz5zvpp4QwK/aws-free-tier-whats-free-and-how-to-start",
     "accessed": "2026-10-15", "status": "verified-third-party (new-account caveat flagged)"},
    {"item": "DynamoDB on-demand writes", "price": "$0.625 per 1M write request units",
     "source": "spendark.com/blog/dynamodb-pricing-explained quoting AWS example; AWS free-tier page",
     "url": "https://aws.amazon.com/dynamodb/pricing", "accessed": "2026-10-15", "status": "verified"},
    {"item": "DynamoDB on-demand reads", "price": "$0.125 per 1M read request units",
     "source": "spendark.com/blog/dynamodb-pricing-explained; aws.amazon.com/dynamodb/pricing",
     "url": "https://aws.amazon.com/dynamodb/pricing", "accessed": "2026-10-15", "status": "verified"},
    {"item": "DynamoDB storage", "price": "$0.25 per GB-month (standard)",
     "source": "spendark.com/blog/dynamodb-pricing-explained; aws.amazon.com/dynamodb/pricing",
     "url": "https://aws.amazon.com/dynamodb/pricing", "accessed": "2026-10-15", "status": "verified"},
    {"item": "DynamoDB free tier", "price": "25 WCU + 25 RCU + 25 GB, but provisioned mode only",
     "source": "dev.to/kanywst/aws-free-hands-on; aws.amazon.com/dynamodb/pricing (25 WCU x $0.00065/hr)",
     "url": "https://aws.amazon.com/dynamodb/pricing", "accessed": "2026-10-15",
     "status": "verified — on-demand tables NOT covered, so requests are charged even 'in free tier'"},
    {"item": "S3 standard storage", "price": "$0.023 per GB-month",
     "source": "cloudzero.com/blog/s3-pricing", "url": "https://www.cloudzero.com/blog/s3-pricing",
     "accessed": "2026-10-15", "status": "verified-third-party"},
    {"item": "S3 free tier", "price": "5 GB + 20K GET + 2K PUT per month for 12 months",
     "source": "builder.aws.com AWS Free Tier guide",
     "url": "https://builder.aws.com/content/3IQ2c19Fk9N0wQdSXz5zvpp4QwK/aws-free-tier-whats-free-and-how-to-start",
     "accessed": "2026-10-15", "status": "verified-third-party (legacy 12-month)"},
    {"item": "CloudWatch Logs ingestion", "price": "$0.50 per GB (standard), first 5 GB free",
     "source": "aws.amazon.com/cloudwatch/pricing (official) + cloudzero.com/blog/cloudwatch-pricing",
     "url": "https://aws.amazon.com/cloudwatch/pricing", "accessed": "2026-10-15", "status": "verified"},
    {"item": "CloudWatch Logs storage", "price": "$0.03 per GB-month",
     "source": "aws.amazon.com/cloudwatch/pricing; spendark.com/blog/aws-cloudwatch-costs",
     "url": "https://aws.amazon.com/cloudwatch/pricing", "accessed": "2026-10-15", "status": "verified"},
    {"item": "EC2 t3.micro on-demand", "price": "$0.0104 per hour us-east-1 (~$7.59/month)",
     "source": "costgoat.com/pricing/amazon-ec2; aws.amazon.com/ec2/instance-types/t3",
     "url": "https://costgoat.com/pricing/amazon-ec2", "accessed": "2026-10-15", "status": "verified"},
    {"item": "EBS gp3 root volume", "price": "$0.08 per GB-month",
     "source": "costgoat.com/pricing/amazon-ec2", "url": "https://costgoat.com/pricing/amazon-ec2",
     "accessed": "2026-10-15", "status": "verified-third-party"},
    {"item": "AWS Comprehend DetectSentiment", "price": "$0.0001 per unit (1 unit = 100 chars, 300-char minimum per request)",
     "source": "cloudzero.com/blog/amazon-comprehend-pricing (0-10M unit tier)",
     "url": "https://www.cloudzero.com/blog/amazon-comprehend-pricing", "accessed": "2026-10-15",
     "status": "verified-third-party (tiered: $0.00005 above 10M units)"},
    {"item": "MonkeyLearn (managed SaaS)", "price": "starts around $299 per month",
     "source": "abstractapi.com/guides/other/best-sentiment-analysis-apis",
     "url": "https://www.abstractapi.com/guides/other/best-sentiment-analysis-apis",
     "accessed": "2026-10-15", "status": "UNVERIFIED third-party guide — vendor pricing page not consulted"},
    {"item": "EC2 free tier", "price": "750 hours t3.micro/month for 12 months (legacy accounts)",
     "source": "builder.aws.com AWS Free Tier guide", "url":
     "https://builder.aws.com/content/3IQ2c19Fk9N0wQdSXz5zvpp4QwK/aws-free-tier-whats-free-and-how-to-start",
     "accessed": "2026-10-15", "status": "verified-third-party (legacy 12-month)"},
]


def measure_pipeline(n: int = 500) -> dict:
    """Measure THIS pipeline: seconds per processed review + stored bytes per review."""
    from src.config import reset_settings_cache
    from src.handlers import processing
    from src.handlers.ingestion import parse_records
    from src.storage import get_storage, reset_storage_cache

    df = load_corpus()
    content = build_csv_content(df, n)
    saved_path = os.environ.get("SQLITE_PATH")
    try:
        with tempfile.TemporaryDirectory(prefix="cost_", ignore_cleanup_errors=True) as td:
            os.environ["SQLITE_PATH"] = str(Path(td) / "cost.db")
            reset_settings_cache()
            reset_storage_cache()
            store = get_storage()
            parsed = parse_records(content=content, filename="cost.csv")
            store.insert_reviews(parsed["records"])

            t0 = time.perf_counter()
            response = processing.handle_process(
                {"body": json.dumps({"limit": n, "engine": "vader"})})
            elapsed = time.perf_counter() - t0
            if response["statusCode"] != 200:
                raise RuntimeError(f"process failed during measurement: {response}")
            summary = json.loads(response["body"])["summary"]

            records = store.query({})
            processed_count = len(records)
            if processed_count == 0 or summary["processed"] != processed_count:
                raise RuntimeError(f"expected {processed_count} processed, got {summary}")
            bytes_per_review = sum(len(json.dumps(r, default=str)) for r in records) / processed_count
            store.close()
    finally:
        if saved_path is None:
            os.environ.pop("SQLITE_PATH", None)
        else:
            os.environ["SQLITE_PATH"] = saved_path
        reset_settings_cache()
        reset_storage_cache()

    return {"process_s_per_review": elapsed / processed_count,
            "bytes_per_review": bytes_per_review}


def model_aws(n: int, measured: dict) -> dict:
    """Per-component usage + pay-as-you-go cost + free-tier residual."""
    batches = math.ceil(n / REVIEWS_PER_BATCH)
    # "divisor" = price denominator: per-1M-request prices vs direct usage prices
    components = {
        "lambda_requests": {"usage": batches, "unit": "invocations", "price": P_LAMBDA_REQ_M,
                            "per": "1M", "divisor": 1_000_000, "free": FT_LAMBDA_REQ},
        "lambda_duration": {"usage": n * measured["process_s_per_review"] * LAMBDA_MEMORY_MB / 1024,
                            "unit": "GB-s", "price": P_LAMBDA_GB_S, "per": "GB-s",
                            "divisor": 1, "free": FT_LAMBDA_GB_S},
        "api_gateway": {"usage": batches + DASHBOARD_GETS_PER_BATCH * batches,
                        "unit": "requests", "price": P_APIGW_REQ_M, "per": "1M",
                        "divisor": 1_000_000, "free": FT_APIGW_REQ},
        "dynamodb_writes": {"usage": 2 * n, "unit": "write units", "price": P_DYNAMO_WRITE_M,
                            "per": "1M", "divisor": 1_000_000, "free": FT_DYNAMO_REQUESTS},
        "dynamodb_reads": {"usage": READS_PER_REVIEW * n, "unit": "read units",
                           "price": P_DYNAMO_READ_M, "per": "1M", "divisor": 1_000_000,
                           "free": FT_DYNAMO_REQUESTS},
        "dynamodb_storage": {"usage": n * measured["bytes_per_review"] / 1e9, "unit": "GB-month",
                             "price": P_DYNAMO_GB, "per": "GB", "divisor": 1, "free": FT_DYNAMO_GB},
        "cloudwatch_ingest": {"usage": n * LOG_BYTES_PER_REVIEW / 1e9, "unit": "GB",
                              "price": P_CW_INGEST_GB, "per": "GB", "divisor": 1,
                              "free": FT_CW_INGEST_GB},
        "s3_static_hosting": {"usage": 0.002, "unit": "GB-month", "price": P_S3_GB,
                              "per": "GB", "divisor": 1, "free": FT_S3_GB},
    }
    payg = 0.0
    free = 0.0
    for item in components.values():
        item["payg_usd"] = item["usage"] / item["divisor"] * item["price"]
        item["free_tier_usd"] = max(0.0, item["usage"] - item["free"]) / item["divisor"] * item["price"]
        payg += item["payg_usd"]
        free += item["free_tier_usd"]
    return {"components": components, "aws_payg_usd": payg, "aws_free_tier_usd": free}


def main() -> None:
    seed_everything()
    print("measuring pipeline (process time + payload size, 500 reviews)...")
    measured = measure_pipeline(500)
    print(f"  process: {measured['process_s_per_review']*1000:.2f} ms/review")
    print(f"  payload: {measured['bytes_per_review']:.0f} bytes/review")

    df = load_corpus()
    comprehend_units_per_review = sum(max(3, math.ceil(len(t) / 100))
                                      for t in df["text"].tolist()) / len(df)

    # capacity note from experiment C if it already ran
    throughput_note = "not measured yet (run run_throughput.py first)"
    throughput_csv = ROOT / "results" / "throughput_ingestion.csv"
    if throughput_csv.exists():
        thr = pd.read_csv(throughput_csv)
        best = thr.loc[thr["reviews_per_second"].idxmax()]
        throughput_note = (f"measured local ingestion up to {best['reviews_per_second']:.0f} "
                           f"reviews/s at batch {int(best['batch_size'])} (SQLite, this machine)")

    rows, detail = [], {"measured": measured,
                        "comprehend_units_per_review": round(comprehend_units_per_review, 3),
                        "assumptions": {
                            "reviews_per_batch": REVIEWS_PER_BATCH,
                            "lambda_memory_mb": LAMBDA_MEMORY_MB,
                            "dashboard_gets_per_upload_batch": DASHBOARD_GETS_PER_BATCH,
                            "dynamodb_reads_per_review": READS_PER_REVIEW,
                            "log_bytes_per_review": LOG_BYTES_PER_REVIEW,
                            "lambda_duration": "warm executions only (N x measured s/review); "
                                               "cold-start init excluded",
                            "throughput_note": throughput_note,
                        }, "workloads": {}}

    t3_micro_month = P_EC2_T3_MICRO_HR * 730 + 8 * P_EBS_GP3_GB

    for n in WORKLOADS:
        aws = model_aws(n, measured)
        batches = math.ceil(n / REVIEWS_PER_BATCH)
        units = n * comprehend_units_per_review

        def basis(text: str) -> str:
            return text

        options = [
            ("aws_free_tier", aws["aws_free_tier_usd"],
             basis(f"within free tier where applicable; residuals: Lambda {batches} inv + "
                   f"{aws['components']['lambda_duration']['usage']:.0f} GB-s, API GW "
                   f"{aws['components']['api_gateway']['usage']:.0f} req, CW "
                   f"{aws['components']['cloudwatch_ingest']['usage']:.2f} GB; "
                   "DynamoDB on-demand requests are never free")),
            ("aws_payg_after_free_tier", aws["aws_payg_usd"],
             basis("Lambda inv+GB-s + API GW req + DynamoDB writes/reads/storage + "
                   "CloudWatch logs + S3, no allowances"),
             ),
            ("ec2_t3_micro_vm", t3_micro_month,
             basis(f"$0.0104/h x 730 h + 8 GB gp3 x $0.08; flat regardless of volume; "
                   f"{throughput_note}")),
            ("managed_saaS_comprehend", units * P_COMPREHEND_UNIT,
             basis(f"{units:,.0f} units x $0.0001 (unit=100 chars, >=300 chars/request); "
                   "tiered rate drops above 10M units")),
            ("managed_saas_monkeylearn", P_MONKEYLEARN_MONTH,
             basis("flat starting price ~$299/mo (third-party guide, UNVERIFIED)")),
        ]
        for option, cost, why in options:
            rows.append({"workload_reviews_per_month": n, "option": option,
                         "monthly_cost_usd": round(cost, 4), "basis": why})

        detail["workloads"][str(n)] = {
            "aws_components": {k: {kk: (round(vv, 6) if isinstance(vv, float) else vv)
                                   for kk, vv in v.items()} for k, v in aws["components"].items()},
            "aws_free_tier_usd": round(aws["aws_free_tier_usd"], 4),
            "aws_payg_usd": round(aws["aws_payg_usd"], 4),
            "ec2_t3_micro_usd": round(t3_micro_month, 4),
            "comprehend_usd": round(units * P_COMPREHEND_UNIT, 4),
            "monkeylearn_usd": P_MONKEYLEARN_MONTH,
        }
        print(f"{n:>9,} reviews: free-tier ${aws['aws_free_tier_usd']:.4f} | "
              f"payg ${aws['aws_payg_usd']:.2f} | t3.micro ${t3_micro_month:.2f} | "
              f"comprehend ${units * P_COMPREHEND_UNIT:.2f} | monkeylearn ${P_MONKEYLEARN_MONTH:.0f}")

    frame = pd.DataFrame(rows)
    print("wrote", write_csv(frame, "cost_model.csv"))
    detail["metadata"] = run_metadata()
    write_json(detail, "cost_model_detail.json")
    write_json({"accessed": "2026-10-15", "region": "us-east-1", "sources": SOURCES},
               "cost_sources.json")

    # ---- figure --------------------------------------------------------
    options = [o for o in frame["option"].unique()]
    pretty = {"aws_free_tier": "AWS free tier",
              "aws_payg_after_free_tier": "AWS pay-as-you-go",
              "ec2_t3_micro_vm": "EC2 t3.micro",
              "managed_saaS_comprehend": "Comprehend API",
              "managed_saas_monkeylearn": "MonkeyLearn SaaS"}
    colors = {"aws_free_tier": "#16a34a", "aws_payg_after_free_tier": "#2563eb",
              "ec2_t3_micro_vm": "#f59e0b", "managed_saaS_comprehend": "#7c3aed",
              "managed_saas_monkeylearn": "#dc2626"}

    fig, ax = plt.subplots(figsize=(9.4, 4.2))
    x = np.arange(len(WORKLOADS))
    width = 0.16
    floor = 0.01  # log-scale floor so $0 stays visible
    for k, option in enumerate(options):
        values = [frame[(frame["workload_reviews_per_month"] == n) &
                        (frame["option"] == option)]["monthly_cost_usd"].iloc[0]
                  for n in WORKLOADS]
        drawn = [max(v, floor) for v in values]
        bars = ax.bar(x + (k - 2) * width, drawn, width, label=pretty[option],
                      color=colors[option])
        for b, v in zip(bars, values):
            label = "$0" if v < 0.005 else (f"${v:,.0f}" if v >= 100 else f"${v:.2f}")
            ax.text(b.get_x() + b.get_width() / 2, b.get_height() * 1.12, label,
                    ha="center", fontsize=6.5, rotation=90)
    ax.set_yscale("log")
    ax.set_xticks(x, [f"{n:,}" for n in WORKLOADS])
    ax.set_ylim(floor, 1000)
    style_axes(ax, "Estimated monthly cost by workload (log scale, 2026-10-15 prices)",
               "reviews per month", "USD / month (log)")
    ax.legend(fontsize=8, ncol=3)
    print("wrote", save_fig(fig, "cost_model.png"))
    print("cost model DONE")


if __name__ == "__main__":
    main()
