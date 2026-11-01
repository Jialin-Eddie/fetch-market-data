"""Wind EDB fetcher: parses the saved-CSV path from CLI notice (never json.loads the inner text).

Usage:
  python fetch_wind_edb.py query M0039354 2011-01-01 2026-10-31 out.csv
  python fetch_wind_edb.py query "中国制造业PMI" 2011-01-01 2026-10-31 out.csv
  python fetch_wind_edb.py search "中国CPI"

Set WIND_SKILL_DIR env var, or pass --dir <wind-mcp-skill dir>.
"""
import argparse, json, re, shutil, subprocess, sys, time
from pathlib import Path

import pandas as pd

CLI = "scripts/cli.mjs"


def resolve_node():
    """node is not always on PATH for a bare CreateProcess; search common locations."""
    exe = shutil.which("node")
    if exe:
        return exe
    daimon_home = Path(__file__).resolve().parents[4]  # .../daimon-share/daimon
    for cand in [daimon_home / "command-process-owner/bin/node.exe",
                 daimon_home / "command-process-owner/bin/node.cmd"]:
        if cand.exists():
            return str(cand)
    kimi_dir = Path.home() / "AppData/Local/Programs/kimi-desktop/resources/resources/runtime/node.cmd"
    if kimi_dir.exists():
        return str(kimi_dir)
    sys.exit("node not found; install node or add it to PATH")


def call_cli(skill_dir, tool, params):
    payload = json.dumps(params, ensure_ascii=True)
    r = subprocess.run([resolve_node(), CLI, "call", "economic_data", tool, payload],
                       cwd=skill_dir, capture_output=True, timeout=180)
    out = r.stdout.decode("utf-8", errors="replace")
    return out


def saved_csv_path(out):
    m = re.search(r"saved to (.+?\.csv)", out)
    if not m:
        return None
    return m.group(1).replace("\\\\", "\\")


def query(skill_dir, question, begin, end, out_path, retries=2):
    params = {"question": question, "beginDate": begin, "endDate": end}
    for attempt in range(retries):
        out = call_cli(skill_dir, "query_economic_indicator_data", params)
        src = saved_csv_path(out)
        if src and Path(src).exists():
            df = pd.read_csv(src)
            df["time"] = pd.to_datetime(df["date"], format="%Y%m%d")
            df = df.dropna(subset=["value"]).sort_values("time")
            df[["time", "value"]].to_csv(out_path, index=False)
            meta = df.iloc[0]
            print(f"OK {out_path}: {len(df)} rows {df.time.iloc[0].date()} ~ {df.time.iloc[-1].date()} "
                  f"| {meta['name']} ({meta['unit']})")
            return True
        # surface the backend reason once
        if attempt == retries - 1:
            msg = re.search(r'"message":\s*"((?:[^"\\]|\\.)*)"', out)
            print(f"FAIL {question}: {msg.group(1)[:200] if msg else out[:200]}")
        time.sleep(4 + 2 * attempt)
    return False


def search(skill_dir, question):
    out = call_cli(skill_dir, "search_economic_indicator", {"question": question})
    src = saved_csv_path(out)
    if src:
        print(Path(src).read_text(encoding="utf-8")[:2000])
    else:
        print(out[:800])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["query", "search"])
    ap.add_argument("args", nargs="+")
    ap.add_argument("--dir", default="", help="wind-mcp-skill directory (or WIND_SKILL_DIR)")
    a = ap.parse_args()
    skill_dir = a.dir or __import__("os").environ.get("WIND_SKILL_DIR", "")
    if not skill_dir:
        sys.exit("pass --dir <wind-mcp-skill dir> or set WIND_SKILL_DIR")
    if a.mode == "search":
        search(skill_dir, a.args[0])
    else:
        question, begin, end, out = a.args
        sys.exit(0 if query(skill_dir, question, begin, end, out) else 1)


if __name__ == "__main__":
    main()