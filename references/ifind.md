# iFinD pitfalls and conventions

Tool: `<ifind-plugin-root>/scripts/ifind_tool.py call --api-name ifind_get_price --params-json '{...}'`
Probe plugin root from the skills index entry for `ifind` (managed plugin dir, `scripts/` lives at plugin root, not under `skills/`).

## Table of contents

- Code formats (futures, indices, commodities, stocks)
- Call constraints
- Failure modes and fixes
- Response shape

## Code formats

| Asset | Code | Example | Notes |
|---|---|---|---|
| CN futures main-continuous | `<SYM>8888.<EXCH>` | `RB8888.SHF`, `I8888.DCE`, `TA8888.CZC`, `SC8888.INE`, `SI8888.GFE` | NOT `888` (that is Wind convention), NOT `RB0`, NOT `RBL8` |
| CN index | `<6digits>.SH/.SZ` | `000300.SH`, `399006.SZ` | works in `get_price` |
| SGE spot precious metal | `AU9999.SHG`, `AG9999.SHG` | | works; `.SHG` suffix |
| CFFEX financial futures | NONE | `IF8888.CFE/.CFX/.CFFEX` all rejected | API only accepts `.SH/.HK/.SZ/.BJ` style securities; no futures-index codes |
| Bond yield series | NONE | `CGB10Y.*` rejected | no yield-type series in this API |
| US/HK stocks | `AAPL.O`, `0700.HK` | | per iFinD docs; `.US` only in realtime API |

Exchange suffix map: SHF=SHFE, DCE=Dalian, CZC=Zhengzhou, INE=INE, GFE=GFEX.

## Call constraints

- Max date range: 3 years per call. Chunk 11-year history into 4 calls (e.g. 2015-11~2018-10, 2018-11~2021-10, 2021-11~2024-10, 2024-11~now).
- Max 3 tickers per call (comma-separated). One ticker per call is fine and simpler for retry logic.
- Always pass `adjust: "none"` for futures main-continuous (back-adjusted prices hide the roll gap; for CTA research keep raw close and compute returns from prices carefully).
- `interval: "D"` for daily.

## Failure modes and fixes

| Symptom | Meaning | Fix |
|---|---|---|
| `EMPTY_DATA - Response data is empty` | no data for code+range, OR code exists but not listed yet, OR transient rate limit | retry once after 4-6 s; if still empty, try a recent window to distinguish "listed late" from "wrong code" |
| `PARAMETER_ERROR - Suffix .X is invalid` | unsupported exchange suffix | check suffix map; CFFEX/GFEX variants differ (GFE works, CFE does not) |
| `PARAMETER_ERROR - Invalid stock code` | missing suffix | add exchange suffix |
| random empty results in a long batch | rate limiting | sleep 0.5-1 s between calls; retry failed segments at the end of the batch |

## Response shape

Success prints a JSON text with `data_preview`. The script also writes the CSV to `file_path` when given. Columns: `open,high,low,close,volume,thscode,time,...`.

- Futures: `time` = ISO date string.
- Indices: `time` = integer `yyyymmdd` (e.g. `20100104`). Parse with `pd.to_datetime(s, format="%Y%m%d")` or `to_datetime(s.astype(str), format="%Y%m%d")`. A bare `pd.to_datetime(int_series)` produces 1970-01-01 timestamps — this bug shipped to production once; always print the first row after saving.