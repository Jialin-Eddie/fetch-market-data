# Wind pitfalls and conventions

Router: `wind-mcp-skill/scripts/cli.mjs call <server_type> <tool_name> '<inline_json>'`.
`cd` to the skill dir first. Params are inline JSON only (`ensure_ascii=True` from Python).

## Table of contents

- Server routing
- EDB (`economic_data`) rules and failure modes
- CLI mechanics and encoding
- Known permission gaps

## Server routing

| Need | server_type | tool |
|---|---|---|
| Find EDB indicator code | `economic_data` | `search_economic_indicator` (question only) |
| EDB time series | `economic_data` | `query_economic_indicator_data` |
| A-share/ETF quote, K-line | `stock_data` | see references/stock.md of wind skill |
| Index K-line | `index_data` | see references/index.md |

`stock_data` and `index_data` do NOT recognize futures main-continuous codes (`RB8888.SHF` -> "未识别到有效的金融标的"). Do not retry them against futures.

## EDB rules

- Time range: `beginDate` + `endDate` (`yyyy-MM-dd`) OR `observation` (count as string). One is required. Never put dates inside `question`.
- Daily-frequency indicators with wide ranges fail (observed: S0059749 full range -> API_CALL_ERROR). Chunk into 4-5 year windows.
- Natural-language `question` matching can pick the WRONG indicator. Observed: "中国城镇调查失业率" matched "IMF预测：中国：失业率". Always run `search_economic_indicator` first, then pass the exact `Mxxxxxxx`/`Sxxxxxxx` code as `question`.
- `search_economic_indicator` returns CSV preview with columns `code,name,unit,source,updateDate,beginDate,endDate,freq`. The beginDate field tells you coverage before you spend a query call.

## Response parsing

- Success stdout: `{"content":[{"type":"text","text":"...notice...saved to <path>.csv..."}]}`.
- The inner `text` is a PYTHON-DICT-REPR (single quotes), NOT JSON. Do not `json.loads` it. Regex out the saved path: `re.search(r"saved to (.+?\.csv)", out)`.
- Saved CSV columns: `code,name,unit,source,updateDate,beginDate,endDate,freq,date,value`. Parse `date` with `format="%Y%m%d"`.
- Failure envelope: `{"ok":false,"error":{"code":..., "message":...}}`. Codes: `INVALID_PARAMS_JSON`, `TOOL_RUNTIME_ERROR` (backend, includes original message), `RATE_LIMIT_ERROR`, etc.

## CLI mechanics

- `@scripts/request.json` file syntax: NOT supported (`Unexpected token '@'`). Inline JSON only.
- Chinese text in argv: use `json.dumps(params, ensure_ascii=True)`.
- Decode child stdout with UTF-8 + errors="replace"; default GBK decode crashes on Chinese (observed on managed Python 3.12 / Windows).
- Do not write temp param files into the skill directory.

## Known permission gaps (as of 2026-11)

- `S0059749` 中债国债到期收益率：10年 -> "受限指标已剔除：无权限". Do not retry; pick a proxy (7d reverse-repo rate, LPR, or SSE bond index `000012.SH` via iFinD).
- Unemployment （城镇调查失业率 M5650805): coverage starts 2018-01 (NBS publication limit, not a tool bug).
- LPR, 7d reverse-repo: coverage starts ~2021 (series publication limit).