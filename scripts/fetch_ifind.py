"""iFinD batch price downloader (battle-tested on 54 futures symbols + indices).

Usage:
  python fetch_ifind.py probe RB8888.SHF
  python fetch_ifind.py fetch RB8888.SHF 2015-11-01 2026-10-31 out.csv
  python fetch_ifind.py batch symbols.json outdir   # symbols.json: {"CODE.NAME": "label", ...}

Reads IFIND_TOOL env var or falls back to a managed-plugin guess path passed via --tool.
Prints first/last row and row count after every save. Never trusts the time column dtype.
"""
import argparse, json, os, subprocess, sys, time
from pathlib import Path

import pandas as pd

TOOL_DEFAULT = os.environ.get("IFIND_TOOL", "")
CHUNK_YEARS = 3  # iFinD hard limit: 3 years per call


def run_tool(tool, params):
    return subprocess.run(
        [sys.executable, tool, "call", "--api-name", "ifind_get_price",
         "--params-json", json.dumps(params)],
        capture_output=True, text=True, timeout=180)


def parse_time_col(s):
    s = s.astype(str).str.strip()
    is_yyyymmdd = s.str.fullmatch(r"\d{8}")
    out = pd.Series(pd.NaT, index=s.index, dtype="datetime64[ns]")
    out[is_yyyymmdd] = pd.to_datetime(s[is_yyyymmdd], format="%Y%m%d")
    out[~is_yyyymmdd] = pd.to_datetime(s[~is_yyyymmdd], errors="coerce")
    return out


def fetch_range(tool, ticker, start, end, tmp_path):
    """Chunk [start, end] into <=3y windows; merge; return DataFrame or None."""
    parts = []
    s = pd.Timestamp(start)
    e = pd.Timestamp(end)
    while s <= e:
        chunk_end = min(e, s + pd.DateOffset(years=CHUNK_YEARS) - pd.Timedelta(days=1))
        params = {"ticker": ticker, "start_date": str(s.date()), "end_date": str(chunk_end.date()),
                  "file_path": str(tmp_path), "interval": "D", "adjust": "none"}
        ok = False
        for attempt in range(2):
            r = run_tool(tool, params)
            if r.returncode == 0 and "EMPTY_DATA" not in r.stdout and tmp_path.exists() and tmp_path.stat().st_size > 0:
                ok = True
                break
            time.sleep(4 + 2 * attempt)
        if ok:
            df = pd.read_csv(tmp_path)
            if len(df):
                df["time"] = parse_time_col(df["time"])
                parts.append(df[["time", "open", "high", "low", "close", "volume"]])
        else:
            print(f"  [WARN] empty/failed segment {s.date()} ~ {chunk_end.date()}")
        tmp_path.unlink(missing_ok=True)
        s = chunk_end + pd.Timedelta(days=1)
        time.sleep(0.5)
    if not parts:
        return None
    df = pd.concat(parts, ignore_index=True).drop_duplicates("time").sort_values("time")
    df = df.dropna(subset=["time"])
    return df


def save_report(df, path):
    df.to_csv(path, index=False)
    yrs = (df["time"].iloc[-1] - df["time"].iloc[0]).days / 365.25
    print(f"  saved {path}: {len(df)} rows {df['time'].iloc[0].date()} ~ {df['time'].iloc[-1].date()} ({yrs:.1f}y)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["probe", "fetch", "batch"])
    ap.add_argument("args", nargs="+")
    ap.add_argument("--tool", default=TOOL_DEFAULT,
                    help="path to ifind_tool.py (required unless IFIND_TOOL set)")
    a = ap.parse_args()
    if not a.tool:
        sys.exit("pass --tool <ifind_plugin_root>/scripts/ifind_tool.py")

    tmp = Path("_ifind_tmp.csv")
    if a.mode == "probe":
        df = fetch_range(a.tool, a.args[0], "2025-10-01", "2025-12-31", tmp)
        print("PROBE", a.args[0], "->", "OK" if df is not None else "EMPTY/WRONG CODE")
        if df is not None:
            save_report(df, Path(f"probe_{a.args[0].replace('.', '_')}.csv"))
    elif a.mode == "fetch":
        ticker, start, end, out = a.args
        df = fetch_range(a.tool, ticker, start, end, tmp)
        if df is None:
            sys.exit(f"no data for {ticker}")
        save_report(df, Path(out))
    else:  # batch
        symbols = json.loads(Path(a.args[0]).read_text(encoding="utf-8"))
        outdir = Path(a.args[1]); outdir.mkdir(parents=True, exist_ok=True)
        for sym, _label in symbols.items():
            fp = outdir / f"{sym.replace('.', '_')}.csv"
            if fp.exists():
                print(f"skip {sym} (exists)")
                continue
            df = fetch_range(a.tool, sym, "2015-11-01", "2026-10-31", tmp)
            if df is not None:
                save_report(df, fp)
            else:
                print(f"EMPTY {sym}")
            time.sleep(1)


if __name__ == "__main__":
    main()