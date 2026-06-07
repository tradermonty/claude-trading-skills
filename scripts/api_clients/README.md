# API Provider Catalog

**Scope: repo-level / Claude-Code tooling only.** This layer is for ad-hoc
research, exploration, and orchestration from the repo root. It is **not**
to be imported from packaged `.skill` runtimes.

**Why this is repo-level only:** `scripts/package_skills.py` bundles only a
single `skills/<name>/` tree into each `.skill` ZIP. A skill that did
`from scripts.api_clients import …` would `ImportError` once installed from
its packaged form. Per-skill API consolidation is tracked separately
(see Issue #115 — vendor / generator approach for the *packaged* clients).

## Quick start (from the repo root)

```python
from scripts.api_clients.polygon_client import PolygonClient
from scripts.api_clients.news_client import NewsClient

# All clients auto-load keys from ~/.claude/secrets/tradermonty.env (mode 600).
poly = PolygonClient()
bars = poly.get_aggs("NVDA", "day", "2026-01-01", "2026-05-27")

news = NewsClient()
items = news.search_news("Fed rate cut", days=3, limit=20)
```

Offline mocked unit tests (run in CI):
```bash
pytest scripts/api_clients/tests/ -q
```

Optional live smoke test (requires keys; not part of the offline gate):
```bash
python3 scripts/api_clients/tests/test_smoke.py
```

## Provider matrix

| Provider | Module | Key env var | Free tier | Best used for |
|---|---|---|---|---|
| **Polygon.io** | `polygon_client.PolygonClient` | `POLYGON_API_KEY` | 5 req/min, EOD | OHLCV, news, fundamentals — replaces yfinance everywhere |
| **Marketaux + Newsdata IO** | `news_client.NewsClient` | `MARKETAUX_API_KEY`, `NEWSDATA_API_KEY` | 100/day each | Ticker-tagged news + sentiment — replaces WebSearch |
| **EIA** | `eia_client.EIAClient` | `EIA_API_KEY` | Unlimited | Power demand, gas prices, spark spread → Power Infrastructure theme |
| **Polymarket** | `polymarket_client.PolymarketClient` | (public Gamma API) | Unlimited | Consensus probability for catalysts → what-is-priced-in framework |
| **Finnhub** | `finnhub_client.FinnhubClient` | `FINNHUB_API_KEY` | 60 req/min | Economic + earnings calendars (free alt to FMP) |
| **Alpaca** | (`portfolio-manager` skill, MCP) | `ALPACA_API_KEY` + `ALPACA_API_SECRET` | Free paper | Portfolio reads only — no execution |
| **HuggingFace / DeepSeek / Kimi** | (skill-level via `LLM_PROVIDER`) | `HF_TOKEN`, `DEEPSEEK_API_KEY`, `KIMI_API_KEY` | Varies | LLM-axis reviewer, narrative synthesis |
| **Telegram** | (alerting only, no client yet) | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | Free | Push notifications |
| **Apify** | (not wrapped) | `APIFY_API_KEY` | Pay-as-you-go | Future: replace finvizfinance with Apify actor |

## OFF-LIMITS

These keys exist in the secrets file but the project's hard constraints (see `CLAUDE.md`) forbid using them:

- **OANDA** (`OANDA_API_TOKEN`) — forex broker SDK belongs to a separate project; no broker execution here
- **Binance** (`BINANCE_API_KEY`) — no auto-trade; crypto execution outside project scope

If you find yourself reaching for these, stop. The constraint exists to keep the manual-review gate intact.

## Key file location

All keys live at:
```
~/.claude/secrets/tradermonty.env   (mode 600, outside repo)
```

The file is auto-loaded on first `get_api_key()` call. Supports two formats:
```bash
# Shell-export style:
export POLYGON_API_KEY="abc123"
FOO=bar

# Provider-block style:
Provider  :Marketeaux
API Key   :<your_key_value_here>
```

## Use-cases (Claude-Code / repo-root sessions only)

These wrappers are convenient when running ad-hoc analysis from the repo
root, e.g. comparing tickers, doing pre/during/post research, or exploring
a new theme. They are **not** a drop-in replacement for the per-skill
clients that already ship inside `skills/<name>/scripts/` — those need to
remain self-contained inside their `.skill` bundles.

| Question you'd ask from the repo root | Wrapper that helps |
|---|---|
| "What did NVDA/AAPL do over the last 6 months?" | `PolygonClient.get_aggs(...)` |
| "What's the latest news + sentiment for these tickers?" | `NewsClient.get_market_news(tickers=[...])` |
| "Is power demand inflecting?" | `EIAClient.electricity_demand(...)` / `power_demand_yoy()` |
| "What's the implied probability of a Fed cut?" | `PolymarketClient.search_markets(...)` |
| "When's the next CPI / NFP print?" | `FinnhubClient.economic_calendar()` |

**For per-skill API consolidation** (the packaged path that ships inside
each `.skill`), see Issue #115 — that's a separate vendor / generator
design, not direct imports from `scripts/`.

## Design rules for new clients

1. **Always go through `get_api_key()`** — never read `os.environ` directly. Centralizes the secrets-file load.
2. **Mark required vs optional** with `required=False`; let users wire one provider without forcing all.
3. **Throttle internally**, don't push that responsibility to callers. Free-tier limits are real.
4. **Return dataclasses, not raw dicts**, so the schema is discoverable and type-checkable.
5. **Don't echo key values** in error messages. Use `***REDACTED***` where logging.
6. **Handle 429 with a single backoff + retry**, not infinite loops.
