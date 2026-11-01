"""igo_open_data fetcher: FRED / Eurostat / ECB / OECD via one CLI, per-source pitfalls encoded.

Usage:
  # FRED: single call (long ranges OK), optional units transform
  python fetch_igo.py fetch --source fred --id DGS10 --start 2000-01-01 --end 2026-10-31 --out us10y.csv
  python fetch_igo.py fetch --source fred --id CPIAUCSL --units pc1 --start 2010-01-01 --end 2026-10-31 --out cpi.csv

  # ECB: daily series auto-chunked to 2-year windows (top=1000 caps ~3.8y of daily obs)
  python fetch_igo.py fetch --source ecb --key B.U2.EUR.4F.G_N_A.SV_C_YM.PY_10Y --start 2004-01-01 --end 2026-10-31 --out bund.csv

  # Eurostat: time filter max 20 values/call -> auto month-chunking; dict-repr dimensions parsed
  python fetch_igo.py fetch --source eurostat --dataset prc_hicp_manr --geo DE,FR --coicop CP00 --start 2010-01 --end 2026-12 --out hicp.csv

  # probe one source before a batch (2y window for daily, 24 months for monthly)
  python fetch_igo.py probe --source ecb --key B.U2.EUR.4F.G_N_A.SV_C_YM.PY_10Y

  # catalogue search
  python fetch_igo.py search --source fred --keyword "Japan CPI"

Set IGO_TOOL env var or pass --tool <igo_open_data_tool.py path>.
Output CSV always standardized to columns: time, value (+ geo for multi-geo eurostat).
"""
import argparse, ast, json, os, subprocess, sys, time
from pathlib import Path

import pandas as pd

TOOL_DEFAULT = os.environ.get("IGO_TOOL", "")
TOP_MAX = 1000            # hard cap for ecb/eurostat inline observations
EUROSTAT_TIME_MAX = 20    # max values per filter dimension per call
ECB_DAILY_CHUNK_YEARS = 2  # ~260 obs/yr; 2y=520, safe under TOP_MAX


def run(tool, source, api, params):
    return subprocess.run(
        [sys.executable, tool, "call", "--data-source", source, "--api-name", api,
         "--params-json", json.dumps(params)],
        capture_output=True, timeout=240)


def check(out, what):
    if out.returncode != 0:
        err = (out.stderr or b"").decode("utf-8", errors="replace") if isinstance(out.stderr, bytes) else str(out.stderr)
        print(f"[FAIL] {what}: {err[:250]}")
        return False
    return True


# ---------- FRED ----------

def fetch_fred(tool, sid, start, end, out, units=None):
    fp = Path("_igo_tmp.csv")
    params = {"id": sid, "start": start, "end": end, "filepath": str(fp), "limit": 10000}
    if units:
        params["units"] = units
    r = run(tool, "fred", "fred_query", params)
    if not (r.returncode == 0 and fp.exists()):
        fp.unlink(missing_ok=True)
        return check(r, f"fred {sid}")
    df = pd.read_csv(fp)
    fp.unlink()
    # FRED CSV shape: date, realtime_end, realtime_start, value
    cols = {c.lower(): c for c in df.columns}
    tcol = cols.get("date") or cols.get("observation_date") or df.columns[0]
    vcol = cols.get("value") or df.columns[-1]
    res = pd.DataFrame({"time": pd.to_datetime(df[tcol]), "value": pd.to_numeric(df[vcol], errors="coerce")})
    res.to_csv(out, index=False)
    print(f"[OK] fred/{sid} -> {out}: {len(res)} rows {res.time.iloc[0].date()} ~ {res.time.iloc[-1].date()}")
    return True


# ---------- ECB ----------

def fetch_ecb(tool, key, start, end, out):
    s, e = pd.Timestamp(start), pd.Timestamp(end)
    parts = []
    fp = Path("_igo_tmp.csv")
    while s <= e:
        ce = min(e, s + pd.DateOffset(years=ECB_DAILY_CHUNK_YEARS) - pd.Timedelta(days=1))
        params = {"dataflow": "YC" if key.split(".")[0] in ("B", "D", "W") else None,
                  "key": key, "start": str(s.date()), "end": str(ce.date()),
                  "filepath": str(fp), "top": TOP_MAX}
        params = {k: v for k, v in params.items() if v}
        ok = False
        for a in range(2):
            r = run(tool, "ecb", "ecb_query", params)
            if r.returncode == 0 and fp.exists() and fp.stat().st_size > 0:
                ok = True; break
            time.sleep(3 + 2 * a)
        if ok:
            df = pd.read_csv(fp)
            if len(df):
                parts.append(df[["time_period", "value"]])
        else:
            print(f"[WARN] ecb empty/failed segment {s.date()} ~ {ce.date()}")
        fp.unlink(missing_ok=True)
        s = ce + pd.Timedelta(days=1)
        time.sleep(0.5)
    if not parts:
        return False
    df = pd.concat(parts).drop_duplicates("time_period").sort_values("time_period")
    df.columns = ["time", "value"]
    df["time"] = pd.to_datetime(df["time"])
    df.to_csv(out, index=False)
    print(f"[OK] ecb/{key} -> {out}: {len(df)} rows {df.time.iloc[0].date()} ~ {df.time.iloc[-1].date()}")
    return True


# ---------- Eurostat ----------

def fetch_eurostat(tool, dataset, geos, coicop, start, end, out):
    months = pd.period_range(start, end, freq="M").astype(str).tolist()
    parts = []
    fp = Path("_igo_tmp.csv")
    for i in range(0, len(months), EUROSTAT_TIME_MAX):
        chunk = months[i:i + EUROSTAT_TIME_MAX]
        params = {"dataset": dataset,
                  "filters": {"geo": geos, "coicop": coicop, "time": chunk},
                  "filepath": str(fp), "top": TOP_MAX}
        ok = False
        for a in range(2):
            r = run(tool, "eurostat", "eurostat_query", params)
            if r.returncode == 0 and fp.exists() and fp.stat().st_size > 0:
                ok = True; break
            time.sleep(3 + 2 * a)
        if ok:
            df = pd.read_csv(fp)
            rows = []
            for _, row in df.iterrows():
                d = ast.literal_eval(row["dimensions"])
                rows.append({"geo": d["geo"]["code"],
                             "time": d["time"]["code"],
                             "value": row["value"]})
            if rows:
                parts.append(pd.DataFrame(rows))
        else:
            print(f"[WARN] eurostat empty/failed chunk {chunk[0]} ~ {chunk[-1]}")
        fp.unlink(missing_ok=True)
        time.sleep(0.5)
    if not parts:
        return False
    df = pd.concat(parts).drop_duplicates(["geo", "time"]).sort_values(["geo", "time"])
    df["time"] = pd.to_datetime(df["time"])
    df[["time", "geo", "value"]].to_csv(out, index=False)
    for g, sub in df.groupby("geo"):
        print(f"[OK] eurostat/{g} -> {out}: {len(sub)} rows {sub.time.iloc[0].date()} ~ {sub.time.iloc[-1].date()}")
    return True


# ---------- search ----------

def search(tool, source, keyword):
    api = {"fred": "fred_search", "eurostat": "eurostat_search", "oecd": "oecd_search"}.get(source)
    if not api:
        sys.exit(f"search not supported for {source}")
    r = run(tool, source, api, {"keyword": keyword, "limit": 15} if source == "fred" else {"keyword": keyword})
    out = r.stdout.decode("utf-8", errors="replace") if isinstance(r.stdout, bytes) else r.stdout
    import re
    ids = re.findall(r'"id":\s*"([^"]+)"', out)
    print(f"{source} candidates: {ids[:20]}")
    return ids


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["fetch", "probe", "search"])
    ap.add_argument("--source", required=True, choices=["fred", "ecb", "eurostat", "oecd"])
    ap.add_argument("--tool", default=TOOL_DEFAULT)
    ap.add_argument("--id", default="")
    ap.add_argument("--key", default="")
    ap.add_argument("--dataset", default="")
    ap.add_argument("--geo", default="")
    ap.add_argument("--coicop", default="CP00")
    ap.add_argument("--start", default="2010-01-01")
    ap.add_argument("--end", default="2026-10-31")
    ap.add_argument("--units", default=None)
    ap.add_argument("--keyword", default="")
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    if not a.tool:
        sys.exit("pass --tool <igo_open_data_tool.py path> or set IGO_TOOL")

    if a.mode == "search":
        search(a.tool, a.source, a.keyword)
        return
    if a.mode == "probe":
        if a.source == "ecb":
            a.start, a.end = "2025-01-01", "2026-10-31"
        elif a.source == "eurostat":
            a.start, a.end = "2025-01", "2026-10"
        else:
            a.start, a.end = "2025-01-01", "2026-10-31"
        a.out = a.out or "probe.csv"
    if a.source == "fred":
        ok = fetch_fred(a.tool, a.id, a.start, a.end, a.out, a.units)
    elif a.source == "ecb":
        ok = fetch_ecb(a.tool, a.key, a.start, a.end, a.out)
    else:
        ok = fetch_eurostat(a.tool, a.dataset, a.geo.split(","), a.coicop, a.start, a.end, a.out)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()