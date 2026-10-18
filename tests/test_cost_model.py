"""Regression tests for the cost model arithmetic (per-1M pricing semantics).

A bug where per-million prices were multiplied by raw counts instead of
millions produced a $2,606/month estimate for 1,000 reviews; these tests pin
the correct arithmetic.
"""
from __future__ import annotations

import pytest

from experiments.run_cost_model import (
    P_COMPREHEND_UNIT,
    P_DYNAMO_READ_M,
    P_DYNAMO_WRITE_M,
    P_EC2_T3_MICRO_HR,
    model_aws,
)

MEASURED = {"process_s_per_review": 0.008, "bytes_per_review": 732.0}


def test_per_million_prices_divide_by_a_million():
    aws = model_aws(1000, MEASURED)
    comp = aws["components"]
    assert comp["dynamodb_writes"]["payg_usd"] == pytest.approx(2000 / 1_000_000 * P_DYNAMO_WRITE_M)
    assert comp["dynamodb_reads"]["payg_usd"] == pytest.approx(10_000 / 1_000_000 * P_DYNAMO_READ_M)
    assert comp["lambda_requests"]["payg_usd"] == pytest.approx(5 / 1_000_000 * 0.20)


def test_small_workload_is_dirt_cheap_on_aws():
    aws = model_aws(1000, MEASURED)
    assert aws["aws_payg_usd"] < 1.0          # cents, not dollars
    assert aws["aws_free_tier_usd"] <= aws["aws_payg_usd"] + 1e-12


def test_free_tier_residual_is_only_never_waived_items():
    # DynamoDB on-demand requests are charged even inside the free tier (A23);
    # everything else at 1K reviews is within allowances.
    aws = model_aws(1000, MEASURED)
    comp = aws["components"]
    residual = sum(v["free_tier_usd"] for k, v in comp.items() if not k.startswith("dynamodb_"))
    assert residual == pytest.approx(0.0)
    assert aws["aws_free_tier_usd"] == pytest.approx(comp["dynamodb_writes"]["free_tier_usd"]
                                                     + comp["dynamodb_reads"]["free_tier_usd"])


def test_costs_scale_linearly_with_workload():
    a = model_aws(10_000, MEASURED)
    b = model_aws(100_000, MEASURED)

    def variable_part(aws):
        # every component except the fixed 2 MB static-hosting bucket
        return sum(v["payg_usd"] for k, v in aws["components"].items()
                   if k != "s3_static_hosting")

    assert variable_part(b) == pytest.approx(variable_part(a) * 10, rel=1e-9)


def test_t3_micro_flat_and_saaS_helpers():
    from experiments.run_cost_model import P_EBS_GP3_GB, P_MONKEYLEARN_MONTH

    flat = P_EC2_T3_MICRO_HR * 730 + 8 * P_EBS_GP3_GB
    assert flat == pytest.approx(8.232, abs=1e-9)
    # Comprehend: 3-unit minimum per review -> $0.0003 floor per review
    assert 3 * P_COMPREHEND_UNIT == pytest.approx(0.0003)
    assert P_MONKEYLEARN_MONTH == 299.0
