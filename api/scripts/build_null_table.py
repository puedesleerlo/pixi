"""Precompute the null-calibration table for the polysemy verdict (spec §6.4).

S_null95[N] = 95th percentile over 200 draws of the max silhouette (k in {2,3}) of N
isotropic-Gaussian points in 8-d. Silhouette is scale-invariant, so one number per N suffices.

Usage: api/.venv/bin/python api/scripts/build_null_table.py [--max-n 80]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pixie.verdict import null_max_silhouettes, _TABLE_PATH, K_VALUES  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-n", type=int, default=8)
    ap.add_argument("--max-n", type=int, default=80)
    ap.add_argument("--n-null", type=int, default=200)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    t0 = time.time()
    s95, s50, s99 = {}, {}, {}
    for n in range(args.min_n, args.max_n + 1):
        best = null_max_silhouettes(n, 1.0, args.n_null, args.seed)
        s95[str(n)] = round(float(np.percentile(best, 95)), 5)
        s50[str(n)] = round(float(np.percentile(best, 50)), 5)
        s99[str(n)] = round(float(np.percentile(best, 99)), 5)
        print(f"N={n:3d}  S_null50={s50[str(n)]:.3f}  S_null95={s95[str(n)]:.3f}  S_null99={s99[str(n)]:.3f}", flush=True)
    out = {
        "description": "95th pct of max silhouette (k in K_VALUES) over n_null draws of N isotropic Gaussian points in 8-d, rescaled to V=1.",
        "n_null": args.n_null, "seed": args.seed, "k_values": list(K_VALUES), "dims": 8,
        "s95": s95, "s50": s50, "s99": s99,
    }
    with open(_TABLE_PATH, "w") as f:
        json.dump(out, f, indent=1)
    print(f"wrote {_TABLE_PATH} in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
