"""Cold-start worker: run in a fresh Python process to time engine import+init+first call.

Prints one line starting with "WORKER_RESULT " that run_latency.py parses.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SAMPLE_TEXT = "This place was absolutely wonderful, we loved every bite."


def main() -> None:
    engine_name = sys.argv[1]
    from experiments.common import build_engine

    t0 = time.perf_counter()
    engine = build_engine(engine_name)
    init_s = time.perf_counter() - t0

    t1 = time.perf_counter()
    result = engine.analyze(SAMPLE_TEXT)
    first_call_s = time.perf_counter() - t1

    print("WORKER_RESULT " + json.dumps({
        "engine": engine_name,
        "init_s": round(init_s, 4),
        "first_call_s": round(first_call_s, 4),
        "label": result.label,
    }))


if __name__ == "__main__":
    main()
