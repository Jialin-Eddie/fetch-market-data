"""Validate every CSV in a directory: rows, date range, NaN, duplicates, max calendar gap.

Usage: python validate_pool.py <dir> [--max-gap-days 15] [--strict]
Exit code: non-zero only if duplicates or unparseable time column found.
NaN counts are reported as WARN, not failure: daily series from FRED/ECB legitimately
contain NaN on non-trading days (observed: VIX, term spread, HY spread). Use --strict
to also fail on NaN.
"""
import argparse
import sys
from pathlib import Path

import pandas as pd


def rng(f):
    df = pd.read_csv(f)
    tcols = [c for c in df.columns if c.lower() in ("time", "date")
             or "observation" in c.lower() or "observation_date" in c.lower()]
    if not tcols:
        return None, f"no time column ({df.columns.tolist()[:5]})"
    t = pd.to_datetime(df[tcols[0]], errors="coerce")
    if t.isna().all():
        return None, "time column unparseable"
    return (df, t), None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dir")
    ap.add_argument("--max-gap-days", type=int, default=15)
    ap.add_argument("--strict", action="store_true", help="also fail on NaN")
    a = ap.parse_args()
    bad = 0
    files = sorted(Path(a.dir).glob("*.csv"))
    print(f"{'file':<32}{'rows':>7} {'start':<11}{'end':<11}{'NaN':>5}{'dup':>5}{'maxgap':>7}")
    for f in files:
        res, err = rng(f)
        if err:
            print(f"{f.name:<32} ERROR: {err}")
            bad += 1
            continue
        df, t = res
        nan = int(df.isna().sum().sum())
        dup = int(df.duplicated(subset=[t.name]).sum())
        gap = int(t.sort_values().diff().dt.days.max())
        flag = ""
        if dup:
            flag = "  <-- CHECK"
            bad += 1
        elif nan and a.strict:
            flag = "  <-- NaN (--strict)"
            bad += 1
        elif nan:
            flag = f"  (NaN {nan}, check calendar)"
        elif gap > a.max_gap_days:
            flag = f"  <-- GAP>{a.max_gap_days}d"
        print(f"{f.name:<32}{len(df):>7} {str(t.min().date()):<11}{str(t.max().date()):<11}"
              f"{nan:>5}{dup:>5}{gap:>7}{flag}")
    print(f"\n{len(files)} files, {bad} with problems")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()