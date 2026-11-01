---
name: fetch-market-data
description: Battle-tested playbook for bulk-downloading market data (Chinese futures, indices, macro series) via iFinD, Wind EDB, FRED, Eurostat and OECD plugins. Use when the task involves fetching price/EDB/quote time series, building a data pool, or when data calls fail with empty results, permission errors, wrong-indicator matches, encoding errors, or rate limits. Covers probe-first discipline, chunking, retry, and post-write validation.
---

# Fetch Market Data

Download bulk market data from paid data plugins without wasting quota on failed calls.
Language style: STE-inspired simplified English (short sentences, imperative mood).

## Source routing

| Data needed | Source | Call path |
|---|---|---|
| CN futures / CN index / US-CN-HK stock daily | iFinD | `<ifind-plugin>/scripts/ifind_tool.py call` |
| CN macro EDB | Wind | `wind-mcp-skill/scripts/cli.mjs call economic_data ...` |
| US / OECD-country macro, FX, commodity spot | FRED | `igo_open_data/scripts/igo_open_data_tool.py call` |
| EU inflation (HICP), EU statistics | Eurostat | same tool as FRED |
| Euro-area daily yields (Bund proxy) | ECB | same tool, dataflow `YC` |
| CFFEX financial futures (IF/T/TF...) | NONE works | iFinD rejects `.CFE`; Wind quote tools reject futures codes. Use spot index instead |
| CN 10Y bond yield | NONE works | Wind EDB `S0059749` needs paid permission; FRED has no CN yield. Use 7d reverse-repo rate or SSE bond index `000012.SH` |

Read ONLY the reference file for the source you routed to. Do not load all three.
- iFinD routed → read [references/ifind.md](references/ifind.md) only.
- Wind routed → read [references/wind.md](references/wind.md) only.
- FRED/Eurostat/OECD routed → read [references/fred-eurostat.md](references/fred-eurostat.md) only.

Rationale: paid plugins charge per call. Loading the wrong source's pitfalls does not break anything, but reading 3 files when 1 is needed wastes context and invites cross-source confusion (e.g. Wind's `888` convention vs iFinD's `8888`).

## Universal workflow

1. **Probe first.** Send one call for one symbol and one short window. Confirm the code format and the response shape. Do not send a batch of untested codes.
2. **Chunk long ranges.** iFinD: max 3 years per call. Wind daily EDB: wide ranges fail; use 4-5 year chunks. FRED: single call is fine up to ~20 years.
3. **Retry bounded.** On failure: wait 4-6 s, retry once. On second failure: skip, record, retry that segment later. Do not loop.
4. **Merge with `drop_duplicates(time)`** after concatenating chunks.
5. **Validate every saved file** before reporting: row count, min/max date, NaN count, duplicate count, max gap. See [scripts/validate_pool.py](scripts/validate_pool.py).
6. **Record the pool**: keep a `DATA_POOL.md` with file, indicator, frequency, range, unit, source, and known gaps.

## Time column hazards (hit in production)

- iFinD futures: `time` is ISO string (`2025-11-03`). Parse with `pd.to_datetime`.
- iFinD indices (`000300.SH` etc.): `time` is integer `yyyymmdd`. Parse with `format="%Y%m%d"`. If you parse it without a format, pandas treats it as nanoseconds and you get year-1970 dates. Always check the first saved row.
- Wind EDB saved CSV: columns `code,name,unit,...,date,value`; `date` is integer `yyyymmdd`.
- FRED CSV: first column is ISO date string.

## Windows process hazards

- Run plugin CLIs through `subprocess.run(..., capture_output=True)` and decode with `stdout.decode("utf-8", errors="replace")`. Default GBK decode of node/python child stdout throws `UnicodeDecodeError` on Chinese text.
- Wind CLI `@scripts/request-xxx.json` param-file syntax is NOT supported. Pass inline JSON with `ensure_ascii=True`.
- Do not write param files into the Wind skill root.

## Quota discipline

- Paid plugins charge per call even for empty results. Probe, then batch.
- Search APIs (`fred_search`, Wind `search_economic_indicator`) are cheaper than wrong guesses. Use them to confirm IDs before `query` calls.
- Do not retry `EMPTY_DATA` as a network error. It means: no data for that code+range (wrong code, or listed later, or restricted).

## Bundled scripts

- [scripts/fetch_ifind.py](scripts/fetch_ifind.py) — iFinD batch downloader (probe/fetch/batch modes, 3-year auto-chunk, robust time parsing, retry). Tested 54 symbols.
- [scripts/fetch_wind_edb.py](scripts/fetch_wind_edb.py) — Wind EDB fetcher that parses the saved-CSV path from the CLI notice. Tested 16 indicators.
- [scripts/fetch_igo.py](scripts/fetch_igo.py) — FRED / ECB / Eurostat / OECD in one CLI: fred single-call with `units` transform; ecb daily auto-chunk to 2y windows (top=1000 cap); eurostat auto month-chunking (20-value time filter cap) with dict-repr parsing. Tested on all three sources.
- [scripts/validate_pool.py](scripts/validate_pool.py) — validate all CSVs in a directory and print the inventory table.