# FRED / Eurostat / OECD pitfalls and conventions

Tool: `igo_open_data/scripts/igo_open_data_tool.py call --data-source <src> --api-name <api> --params-json '{...}'`.
`fred_query` and `eurostat_query` require `filepath` (CSV output).

## Table of contents

- FRED series ID patterns (OECD harmonized)
- Known stale / missing series
- FRED call rules
- Eurostat call rules

## FRED series ID patterns

US: use canonical IDs (`GDPC1`, `CPIAUCSL`, `UNRATE`, `GS10`, `GS2`, `FEDFUNDS`, `INDPRO`, `PPIACO`, `RSXFS`, `HOUST`, `M2SL`, `DTWEXBGS`, `VIXCLS`, `PAYEMS`, `PCEPI`, `CPILFESL`, `UMCSENT`, `T10Y2Y`, `BAMLH0A0HYM2`, `DCOILWTICO`, `DCOILBRENTEU`, `DHHNGSP`, `DEXCHUS`...).

OECD harmonized (via FRED):
| Indicator | Pattern | Example |
|---|---|---|
| CPI YoY monthly | `CPALTT01<CC>M659N` | `CPALTT01DEM659N` (DE), `CPALTT01FRM659N`, `CPALTT01GBM659N`, `CPALTT01CAM659N`, `CPALTT01INM659N`, `CPALTT01BRM659N`, `CPALTT01JPM659N` |
| CPI YoY quarterly | `CPALTT01<CC>Q659N` | `CPALTT01AUQ659N` (AU is quarterly) |
| Harmonized unemployment | `LRHUTTTT<CC>M156S` | `LRHUTTTTDEM156S` |
| Long-term (10Y) interest | `IRLTLT01<CC>M156N` | `IRLTLT01DEM156N`, `IRLTLT01USM156N` |
| Real GDP quarterly | `CLVMNACSCAB1GQ<CC2>` | `...DE`, `FR`, `JP` work; `EA19` works; `GB`/`CA`/`AU`/`KO` DO NOT |
| Real GDP quarterly alt | `NGDPRSAXDC<CC2>Q` | `NGDPRSAXDCAUQ`, `...BRQ` work |
| Real GDP quarterly alt 2 | `NAEXKP01<CC2>Q189S` | `NAEXKP01CAQ189S`, `NAEXKP01KRQ189S` |

Country codes: 2-letter for GDP patterns, e.g. DE/FR/JP/AU/BR/KR; Korea uses `KR`/`KRM` (not `KO`).

YoY from an index series: pass `units: "pc1"`. List: `lin, chg, ch1, pch, pc1, pca, cch, cca, log`.

## Known stale / missing series (verified 2026-11)

- Japan CPI (all `CPALTT01JP*`, `JPNCPIALLMINMEI`, `JPNCPALTT01CTGYM`): stale, ends 2022-04 or 2021-06. No fresh monthly source on FRED. Annual fallback: `FPCPITOTLZGJPN` (World Bank, 2000~).
- DE/FR CPI `CPALTT01*M659N`: stale, ends 2025-03. Fresh alternative: Eurostat HICP (below), ends 2025-12.
- India, Brazil: no `IRLTLT01*` (not in OECD long-term set). No GB/IN quarterly real GDP ID found.
- Australia CPI: quarterly, not monthly.
- `US_HY_spread` (`BAMLH0A0HYM2`): starts 2023-10 in current feed.

## FRED call rules

- `fred_query`: pass exact `id` + `start` + `limit: 10000` (default limit 1000 truncates long daily series).
- `fred_search` keyword search returns annual/per-capita junk first for broad queries like "Germany real GDP OECD". Prefer probing candidate IDs directly (they are cheap and fail fast) over paging search.
- Failure on wrong ID: `API_CALL_ERROR - FRED API returned HTTP 400 ... series does not exist.` Retry with the next candidate ID.

## Eurostat call rules (`eurostat_query`)

- `top` must be 1..1000. No way to raise it.
- `filters` dimension values: max 20 values per dimension per call. For monthly series over 16 years (204 months), loop 20-month chunks.
- For `prc_hicp_manr` the `time` filter accepts a LIST of `YYYY-MM` strings. Passing a range string (`>=2010-01`) or `startPeriod` is REJECTED.
- Full wildcard keys explode past the 16 MB download limit. Always filter `geo` + `coicop` + `time`.
- Key must match the DSD dimension count exactly. `prc_hicp_manr` requires 8 segments: `REF_AREA.FREQ.METHODOLOGY.MEASURE.UNIT_MEASURE.EXPENDITURE.ADJUSTMENT.TRANSFORMATION`. Wrong segment count -> `PARAMETER_ERROR` with the expected list in the message (use it).
- Saved CSV columns: `observation_index, dimensions, value, status, flags, flag_labels` where `dimensions` is a PYTHON-DICT-REPR string. Parse with `ast.literal_eval`, then read `d["geo"]["code"]`, `d["time"]["code"]`.
- Recommended filter set for DE/FR all-items HICP YoY: `{"geo": ["DE","FR"], "coicop": "CP00", "time": [<list of YYYY-MM>]}.

## ECB call rules (`ecb_query`) — daily yields for euro area

Dataflow `YC` (Yield Curves), dimensions `FREQ.REF_AREA.CURRENCY.PROVIDER_FM.INSTRUMENT_FM.PROVIDER_FM_ID.DATA_TYPE_FM`.

- 10Y euro-area AAA spot rate key: `B.U2.EUR.4F.G_N_A.SV_C_YM.PY_10Y` (daily, from 2004-09). This is the euro-area AAA curve — a close proxy for the German Bund; it is NOT Bund-specific.
- `start`/`end` format MUST match the series frequency. For daily (FREQ=B) use full dates `YYYY-MM-DD`. Passing a bare year (`2004`) -> `PARAMETER_ERROR - period format must match series frequency B (daily)`.
- `top` caps observations per call at 1000. A daily series is ~260 obs/year, so a 4-year chunk TRUNCATES and silently cuts the tail of each chunk. Use <=2-year chunks (observed in testing: 4y chunks produced hidden gaps that had to be repaired).
- Saved CSV columns are flat: `FREQ,...,time_period,value,status_id,status_name`. No dict-repr parsing needed (unlike Eurostat).
- Japan daily JGB yield: NOT available on FRED (only monthly `IRLTLT01JPM156N`) or ECB. Do not search repeatedly; record the gap.