---
name: openbb
description: "Financial data research via OpenBB Platform SDK. Covers equity fundamentals (financials, valuation, profile), macro economics (GDP, CPI, rates), quantitative analytics (Sharpe, CAPM), technical indicators, multi-asset data (crypto, forex, ETF, commodity, options), stock screening, and news. Use when: (1) user asks for fundamental analysis, financial statements, or valuation metrics, (2) user needs macro economic context (interest rates, inflation, unemployment), (3) user wants quantitative risk metrics (Sharpe ratio, Sortino, CAPM), (4) user requests multi-asset research beyond equities, (5) user asks to screen or filter stocks by criteria, (6) any financial data need beyond OHLCV price history."
---

# OpenBB — Financial Data Gateway

## Execution Model

OpenBB SDK runs via `bash` (not `compute` — sandbox blocks imports):

```bash
python3 -c "
from openbb import obb
result = obb.equity.profile('AAPL', provider='yfinance')
print(result.to_df().to_json(orient='records', date_format='iso'))
"
```

For multi-step queries, use a heredoc:

```bash
python3 << 'PYEOF'
from openbb import obb
import json

# Fetch multiple data points
profile = obb.equity.profile("AAPL", provider="yfinance").to_df()
ratios = obb.equity.fundamental.ratios("AAPL", provider="yfinance", limit=4).to_df()

print("=== PROFILE ===")
print(profile[["name", "sector", "industry", "market_cap", "description"]].to_json(orient="records"))
print("=== RATIOS ===")
print(ratios.to_json(orient="records", date_format="iso"))
PYEOF
```

**Error handling**: If a provider fails, retry with an alternate provider or inform the user.

## Setup

First-time usage requires installation and optional API key configuration.
Read [references/setup.md](references/setup.md) for complete setup guide including:
- Installation commands (minimal vs full)
- Free API key registration links (FRED, Finnhub, Alpha Vantage, Tiingo)
- Zero-key providers (yfinance, CBOE, ECB, IMF)
- Configuration methods and verification

## Capabilities Overview

All APIs are independent atomic operations — call any single one or combine freely.
For complete API catalog with examples, see [references/api-reference.md](references/api-reference.md).

### Equity (provider: yfinance — free, no key)
| API | Purpose |
|-----|---------|
| `obb.equity.profile(symbol)` | Company name, sector, market cap, description |
| `obb.equity.fundamental.income(symbol, limit=4)` | Income statement (revenue, net income, EPS) |
| `obb.equity.fundamental.balance(symbol, limit=4)` | Balance sheet (assets, liabilities, equity) |
| `obb.equity.fundamental.cash(symbol, limit=4)` | Cash flow (operating, investing, financing, FCF) |
| `obb.equity.fundamental.ratios(symbol, limit=4)` | PE, PB, ROE, debt-to-equity, current ratio |
| `obb.equity.fundamental.metrics(symbol)` | Revenue/share, EPS, market cap, growth rates |
| `obb.equity.fundamental.dividends(symbol)` | Dividend history and yield |
| `obb.equity.price.historical(symbol)` | OHLCV price data |
| `obb.equity.price.quote(symbol)` | Real-time quote snapshot |
| `obb.equity.estimates.consensus(symbol)` | Analyst consensus estimates |
| `obb.equity.ownership.institutional(symbol)` | Top institutional holders |
| `obb.equity.compare.peers(symbol)` | Peer company list |
| `obb.equity.screener(preset)` | Stock screening by criteria |

### Macro Economics (provider: fred — free key required)
| API | Purpose |
|-----|---------|
| `obb.economy.gdp.nominal(provider="fred")` | GDP nominal value |
| `obb.economy.cpi(provider="fred")` | Consumer Price Index / inflation |
| `obb.economy.interest_rate(provider="fred")` | Federal funds rate |
| `obb.economy.unemployment(provider="fred")` | Unemployment rate |
| `obb.economy.fred_series(symbol="DGS10")` | 10-Year Treasury yield |
| `obb.economy.fred_series(symbol="VIXCLS")` | VIX fear index |
| `obb.economy.fred_series(symbol="M2SL")` | M2 money supply |
| `obb.economy.calendar(provider="fred")` | Economic event calendar |

### Quantitative Analysis (operates on fetched price data)
| API | Purpose |
|-----|---------|
| `obb.quantitative.performance.sharpe_ratio(data)` | Risk-adjusted return |
| `obb.quantitative.performance.sortino_ratio(data)` | Downside risk-adjusted return |
| `obb.quantitative.performance.omega_ratio(data)` | Gain/loss probability ratio |
| `obb.quantitative.capm(data)` | Capital Asset Pricing Model |
| `obb.quantitative.normality(data)` | Distribution normality tests |
| `obb.quantitative.rolling.stdev(data)` | Rolling volatility |
| `obb.quantitative.stats(data)` | Comprehensive statistics |

### Technical Analysis (operates on fetched price data)
| API | Purpose |
|-----|---------|
| `obb.technical.sma/ema/wma(data, length)` | Moving averages |
| `obb.technical.rsi(data, length=14)` | Relative Strength Index |
| `obb.technical.macd(data)` | MACD oscillator |
| `obb.technical.bbands(data)` | Bollinger Bands |
| `obb.technical.adx(data)` | Average Directional Index |
| `obb.technical.atr(data)` | Average True Range |
| `obb.technical.ichimoku(data)` | Ichimoku Cloud |
| `obb.technical.vwap(data)` | Volume-Weighted Average Price |
| `obb.technical.stoch(data)` | Stochastic Oscillator |
| `obb.technical.obv(data)` | On-Balance Volume |

### Multi-Asset (mixed providers — see API reference for details)
| API | Purpose | Provider |
|-----|---------|----------|
| `obb.crypto.price.historical(symbol)` | Crypto OHLCV | yfinance (free) |
| `obb.forex.pairs()` | Forex pairs data | yfinance/ECB (free) |
| `obb.etf.historical(symbol)` | ETF price history | yfinance (free) |
| `obb.etf.holdings(symbol)` | ETF constituent holdings | yfinance (free) |
| `obb.derivatives.options.chains(symbol)` | Options chain | cboe (free) |
| `obb.commodity.price.historical(symbol)` | Commodity prices | yfinance (free) |
| `obb.fixedincome.rate.ameribor(provider="fred")` | Fixed income rates | fred (free key) |
| `obb.news.world()` / `obb.news.company(symbol)` | Financial news | benzinga/biztoc |

## Workflow Recipes

### A. Single Stock Deep Dive

1. `obb.equity.profile(symbol)` — what is this company
2. `obb.equity.fundamental.income(symbol, limit=4)` — revenue/profit trend
3. `obb.equity.fundamental.balance(symbol, limit=4)` — financial health
4. `obb.equity.fundamental.cash(symbol, limit=4)` — real cash generation
5. `obb.equity.fundamental.ratios(symbol, limit=4)` — valuation snapshot
6. Fetch OHLCV via `market_ohlcv` → `compute` for technical signals (existing tools)
7. `obb.economy.fred_series(symbol="DGS10")` + `obb.economy.fred_series(symbol="VIXCLS")` — macro context
8. Synthesize all dimensions → recommendation with confidence level
9. Save to `notebook/research/{symbol}/fundamentals-{date}.md`

### B. Macro Environment Assessment

1. `obb.economy.gdp.nominal()` — growth cycle position
2. `obb.economy.cpi()` — inflation trajectory
3. `obb.economy.interest_rate()` — monetary policy stance
4. `obb.economy.unemployment()` — labor market health
5. `obb.economy.fred_series(symbol="DGS10")` — risk-free rate
6. `obb.economy.fred_series(symbol="VIXCLS")` — market sentiment
7. Classify regime: expansion / peak / contraction / trough
8. Save to `notebook/reports/macro-{date}.md`

### C. Quantitative Risk Assessment

1. Fetch historical prices for target + benchmark (SPY)
2. `obb.quantitative.performance.sharpe_ratio(data)` — risk-adjusted return
3. `obb.quantitative.performance.sortino_ratio(data)` — downside risk focus
4. `obb.quantitative.capm(data)` — alpha and beta
5. `obb.quantitative.rolling.stdev(data)` — volatility trend
6. `obb.quantitative.normality(data)` — tail risk assessment
7. Save to `notebook/research/{symbol}/risk-{date}.md`

### D. Stock Screening

1. Define criteria with user (sector, cap range, PE range, etc.)
2. `obb.equity.screener(preset)` — initial filter
3. For top 5-10 results, run abbreviated deep dive (profile + ratios)
4. Rank by user's priority criteria
5. Save to `notebook/reports/screening-{date}.md`

## Provider Routing

| Market / Data | Primary (Free) | Fallback (Paid) |
|---------------|----------------|-----------------|
| US equity fundamentals | `yfinance` (no key) | `fmp` ($14/mo) |
| A-share fundamentals | `akshare` (no key) | `tushare` (800 pts) |
| Macro economics | `fred` (free key) | `oecd` (free) |
| US options | `cboe` (no key) | `intrinio` ($40/mo) |
| Crypto / Forex / ETF | `yfinance` (no key) | `polygon` ($9/mo) |

**A-share note**: yfinance covers A-share OHLCV but NOT financials. Use `provider="akshare"` for A-share fundamental data (requires `openbb-akshare` extension).

## Constraints

- **Rate limits**: yfinance may throttle — add `time.sleep(0.5)` between sequential calls
- **Token budget**: Use `limit=4` for quarterly data to avoid verbose output
- **Data freshness**: Financial statements are quarterly; macro data varies (monthly/quarterly)
- **Provider fallback**: If a provider returns error, try alternate provider before failing
- **Free tier coverage**: yfinance + FRED covers ~90% of use cases at zero cost

## Output Protocol

Save research output following project conventions:
- Single stock: `notebook/research/{symbol}/fundamentals-{date}.md`
- Macro assessment: `notebook/reports/macro-{date}.md`
- Risk analysis: `notebook/research/{symbol}/risk-{date}.md`
- Screening: `notebook/reports/screening-{date}.md`
- Update `memory.md` with major new findings via `edit` or `write`
