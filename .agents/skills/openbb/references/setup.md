# OpenBB Setup Guide

## Installation

### Minimal (US equities + macro only)
```bash
pip install openbb openbb-yfinance openbb-fred
```

### Recommended (covers all free data sources)
```bash
pip install openbb openbb-yfinance openbb-fred openbb-ecb openbb-imf openbb-sec
```

### Full (all providers including paid)
```bash
pip install "openbb[all]"
```

### A-Share Support
```bash
pip install openbb-akshare
# or from community extension:
# pip install git+https://github.com/finanalyzer/openbb_akshare.git
```

### Quantitative & Technical Extensions
```bash
pip install openbb-quantitative openbb-technical openbb-charting
```

## API Key Configuration

### Zero-Key Providers (no registration needed)

| Provider | Data | Notes |
|----------|------|-------|
| **yfinance** | Equity price/fundamentals, crypto, forex, ETF | May throttle high-frequency calls |
| **CBOE** | US equity options chains | No limits |
| **ECB** | European Central Bank rates, EUR forex | No limits |
| **IMF** | International macro data | No limits |
| **SEC EDGAR** | US company filings (10-K, 10-Q) | No limits |
| **AKShare** | A-share price/fundamentals (via EastMoney/Sina) | Scraper-based, may throttle |

### Free-Key Providers (register to get key)

| Provider | Register URL | Free Tier | Data |
|----------|-------------|-----------|------|
| **FRED** | https://fredaccount.stlouisfed.org | **Unlimited** | US/global macro (GDP, CPI, rates, M2, VIX) |
| **Finnhub** | https://finnhub.io | 60 calls/min | US equity daily + news + fundamentals |
| **Alpha Vantage** | https://www.alphavantage.co | 5 calls/min, 500/day | Equity, forex, crypto |
| **Tiingo** | https://www.tiingo.com | 1000 requests/day | US equity, crypto, forex |
| **Polygon** | https://polygon.io | 5 calls/min (Starter) | US equity real-time/delayed |
| **Nasdaq Data Link** | https://data.nasdaq.com | Limited | Alternative data |
| **Biztoc** | https://biztoc.com | Limited | Financial news aggregation |

### Setting Keys

**Method 1: Python SDK**
```python
from openbb import obb
obb.user.credentials.fred_api_key = "YOUR_FRED_KEY"
obb.user.credentials.finnhub_api_key = "YOUR_FINNHUB_KEY"
obb.user.credentials.alpha_vantage_api_key = "YOUR_AV_KEY"
obb.user.credentials.tiingo_token = "YOUR_TIINGO_TOKEN"
```

**Method 2: Environment Variables**
```bash
export OPENBB_FRED_API_KEY="YOUR_FRED_KEY"
export OPENBB_FINNHUB_API_KEY="YOUR_FINNHUB_KEY"
export OPENBB_ALPHA_VANTAGE_API_KEY="YOUR_AV_KEY"
export OPENBB_TIINGO_TOKEN="YOUR_TIINGO_TOKEN"
```

**Method 3: .env file** (add to project root, ensure in .gitignore)
```
OPENBB_FRED_API_KEY=your_key_here
OPENBB_FINNHUB_API_KEY=your_key_here
```

## Verification

Test that installation works:

```bash
# Basic test (no key needed)
python3 -c "from openbb import obb; print(obb.equity.price.quote('AAPL', provider='yfinance').to_df()[['last_price','volume']].to_string())"

# FRED test (requires FRED key)
python3 -c "from openbb import obb; print(obb.economy.fred_series(symbol='DGS10', provider='fred').to_df().tail(5).to_string())"

# List available providers
python3 -c "from openbb import obb; print([p for p in dir(obb.equity.price.historical) if not p.startswith('_')])"
```

## Paid Providers (for future reference)

| Provider | Price | Data |
|----------|-------|------|
| FMP (Financial Modeling Prep) | $14/mo+ | Global equity fundamentals, full analyst estimates |
| IEX Cloud | $9/mo+ | Real-time US equity data |
| Intrinio | $40/mo+ | US fundamentals + options |
| Benzinga | Contact sales | News + analyst ratings |
| Polygon Premium | $29/mo+ | Unlimited US equity + options |
