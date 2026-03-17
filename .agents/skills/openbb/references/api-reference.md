# OpenBB Atomic API Reference

Every API below is independently callable. Combine freely to build custom research flows.

All examples use `provider="yfinance"` (free, no key) unless noted otherwise.
Output format: `.to_df()` returns pandas DataFrame; `.to_json()` returns JSON string.

## Table of Contents

- [Equity](#equity)
- [Economy / Macro](#economy--macro)
- [Quantitative Analysis](#quantitative-analysis)
- [Technical Analysis](#technical-analysis)
- [Crypto](#crypto)
- [Forex](#forex)
- [ETF](#etf)
- [Derivatives / Options](#derivatives--options)
- [Commodity](#commodity)
- [Fixed Income](#fixed-income)
- [News](#news)
- [Index](#index)
- [Regulators](#regulators)
- [Common FRED Series Codes](#common-fred-series-codes)

---

## Equity

### Company Profile
```python
obb.equity.profile("AAPL", provider="yfinance")
# Returns: name, sector, industry, market_cap, description, employees, website, country
```

### Price — Historical OHLCV
```python
obb.equity.price.historical("AAPL", provider="yfinance", start_date="2024-01-01", end_date="2024-12-31")
# Returns: date, open, high, low, close, volume, adj_close
```

### Price — Real-time Quote
```python
obb.equity.price.quote("AAPL", provider="yfinance")
# Returns: last_price, open, high, low, volume, prev_close, change, change_percent, market_cap
```

### Income Statement
```python
obb.equity.fundamental.income("AAPL", provider="yfinance", limit=4, period="annual")
# period: "annual" | "quarter"
# Returns: revenue, cost_of_revenue, gross_profit, operating_income, net_income, eps, ebitda
```

### Balance Sheet
```python
obb.equity.fundamental.balance("AAPL", provider="yfinance", limit=4, period="annual")
# Returns: total_assets, total_liabilities, total_equity, cash, total_debt, current_assets, current_liabilities
```

### Cash Flow Statement
```python
obb.equity.fundamental.cash("AAPL", provider="yfinance", limit=4, period="annual")
# Returns: operating_cash_flow, investing_cash_flow, financing_cash_flow, free_cash_flow, capex
```

### Financial Ratios
```python
obb.equity.fundamental.ratios("AAPL", provider="yfinance", limit=4)
# Returns: pe_ratio, pb_ratio, ps_ratio, roe, roa, debt_to_equity, current_ratio, quick_ratio
```

### Key Metrics
```python
obb.equity.fundamental.metrics("AAPL", provider="yfinance")
# Returns: revenue_per_share, net_income_per_share, market_cap, pe_ratio, eps, dividend_yield
```

### Dividends
```python
obb.equity.fundamental.dividends("AAPL", provider="yfinance")
# Returns: ex_date, payment_date, amount, declaration_date
```

### Analyst Consensus
```python
obb.equity.estimates.consensus("AAPL", provider="yfinance")
# Returns: target_high, target_low, target_mean, target_median, recommendation
# For more complete estimates: provider="fmp" (paid)
```

### Institutional Ownership
```python
obb.equity.ownership.institutional("AAPL", provider="yfinance")
# Returns: holder, shares, date_reported, change, change_percent, value
```

### Peer Companies
```python
obb.equity.compare.peers("AAPL", provider="yfinance")
# Returns: list of peer symbols in same sector/industry
```

### Stock Screener
```python
obb.equity.screener(provider="yfinance")
# Preset-based screening. Available presets vary by provider.
# yfinance presets: day_gainers, day_losers, most_actives, undervalued_growth, etc.
```

---

## Economy / Macro

All macro APIs default to `provider="fred"` (free key required).

### GDP
```python
obb.economy.gdp.nominal(provider="fred")
# Returns: date, value (nominal GDP in billions USD)
```

### CPI / Inflation
```python
obb.economy.cpi(provider="fred")
# Returns: date, value (CPI index value)
```

### Interest Rate
```python
obb.economy.interest_rate(provider="fred")
# Returns: date, value (federal funds effective rate)
```

### Unemployment
```python
obb.economy.unemployment(provider="fred")
# Returns: date, value (unemployment rate %)
```

### Custom FRED Series
```python
obb.economy.fred_series(symbol="DGS10", provider="fred")
# Returns: date, value (any FRED series — see Common FRED Series Codes below)
```

### Economic Calendar
```python
obb.economy.calendar(provider="fred")
# Returns: date, event, actual, forecast, previous
```

---

## Quantitative Analysis

Quantitative APIs operate on previously fetched price data (OBBject from price.historical):

```python
# Step 1: Fetch data
data = obb.equity.price.historical("AAPL", provider="yfinance", start_date="2023-01-01")

# Step 2: Apply quantitative analysis
sharpe = obb.quantitative.performance.sharpe_ratio(data=data)
sortino = obb.quantitative.performance.sortino_ratio(data=data)
omega = obb.quantitative.performance.omega_ratio(data=data)
capm = obb.quantitative.capm(data=data, benchmark="SPY")
norm = obb.quantitative.normality(data=data)
stats = obb.quantitative.stats(data=data)
```

### Rolling Statistics
```python
rolling_vol = obb.quantitative.rolling.stdev(data=data, window=21)   # 21-day rolling volatility
rolling_mean = obb.quantitative.rolling.mean(data=data, window=21)
rolling_skew = obb.quantitative.rolling.skew(data=data, window=63)
rolling_kurt = obb.quantitative.rolling.kurtosis(data=data, window=63)
```

---

## Technical Analysis

Technical APIs also operate on previously fetched price data:

```python
data = obb.equity.price.historical("AAPL", provider="yfinance", start_date="2023-01-01")

# Moving Averages
sma20 = obb.technical.sma(data=data, length=20)
sma60 = obb.technical.sma(data=data, length=60)
ema12 = obb.technical.ema(data=data, length=12)

# Oscillators
rsi = obb.technical.rsi(data=data, length=14)
macd_data = obb.technical.macd(data=data, fast=12, slow=26, signal=9)
stoch = obb.technical.stoch(data=data)

# Volatility
bb = obb.technical.bbands(data=data, length=20, std=2)
atr = obb.technical.atr(data=data, length=14)
kc = obb.technical.kc(data=data)           # Keltner Channels
dc = obb.technical.donchian(data=data)     # Donchian Channels

# Trend
adx = obb.technical.adx(data=data, length=14)
aroon = obb.technical.aroon(data=data, length=25)
ichimoku = obb.technical.ichimoku(data=data)

# Volume
obv = obb.technical.obv(data=data)
vwap = obb.technical.vwap(data=data)
ad = obb.technical.ad(data=data)           # Accumulation/Distribution

# Advanced
fib = obb.technical.fib(data=data)         # Fibonacci retracement
cg = obb.technical.cg(data=data)           # Center of Gravity
fisher = obb.technical.fisher(data=data)   # Fisher Transform
zlma = obb.technical.zlma(data=data)       # Zero-Lag Moving Average
```

---

## Crypto

```python
# Historical OHLCV
obb.crypto.price.historical("BTC-USD", provider="yfinance")
# Supported symbols: BTC-USD, ETH-USD, BNB-USD, SOL-USD, etc.
```

---

## Forex

```python
# Currency pairs
obb.forex.pairs(provider="yfinance")

# Historical exchange rate
obb.forex.price.historical("EURUSD", provider="yfinance")
# or via ECB (no key):
obb.forex.price.historical("EURUSD", provider="ecb")
```

---

## ETF

```python
# ETF price history
obb.etf.historical("SPY", provider="yfinance")

# ETF holdings / constituents
obb.etf.holdings("SPY", provider="yfinance")

# ETF info / profile
obb.etf.info("SPY", provider="yfinance")
```

---

## Derivatives / Options

```python
# Options chain (free via CBOE for US equities)
obb.derivatives.options.chains("AAPL", provider="cboe")
# Returns: strike, expiration, option_type, bid, ask, volume, open_interest, implied_volatility
```

---

## Commodity

```python
# Commodity prices via yfinance
obb.commodity.price.historical("GC=F", provider="yfinance")    # Gold
obb.commodity.price.historical("CL=F", provider="yfinance")    # Crude Oil
obb.commodity.price.historical("SI=F", provider="yfinance")    # Silver
obb.commodity.price.historical("NG=F", provider="yfinance")    # Natural Gas
```

---

## Fixed Income

```python
# Bond rates
obb.fixedincome.rate.ameribor(provider="fred")
obb.fixedincome.government.treasury_rates(provider="fred")
# Treasury yield curve via FRED series: DGS1MO, DGS3MO, DGS6MO, DGS1, DGS2, DGS5, DGS10, DGS30
```

---

## News

```python
# World financial news
obb.news.world(provider="biztoc", limit=10)

# Company-specific news
obb.news.company(symbol="AAPL", provider="biztoc", limit=10)
# Note: biztoc requires free API key
```

---

## Index

```python
# Major index data
obb.index.price.historical("^GSPC", provider="yfinance")   # S&P 500
obb.index.price.historical("^IXIC", provider="yfinance")   # NASDAQ
obb.index.price.historical("^DJI", provider="yfinance")    # Dow Jones
obb.index.price.historical("000001.SS", provider="yfinance")  # Shanghai Composite
```

---

## Regulators

```python
# SEC filings search
obb.regulators.sec.search(query="AAPL", provider="sec")
# Returns: company filings list (10-K, 10-Q, 8-K, etc.)
```

---

## Common FRED Series Codes

Use with `obb.economy.fred_series(symbol="CODE", provider="fred")`:

| Code | Description |
|------|-------------|
| `DGS10` | 10-Year Treasury Constant Maturity Rate |
| `DGS2` | 2-Year Treasury Constant Maturity Rate |
| `T10Y2Y` | 10-Year minus 2-Year Treasury Spread (yield curve) |
| `VIXCLS` | CBOE Volatility Index (VIX) |
| `FEDFUNDS` | Federal Funds Effective Rate |
| `CPIAUCSL` | CPI for All Urban Consumers (seasonally adjusted) |
| `UNRATE` | Civilian Unemployment Rate |
| `M2SL` | M2 Money Supply |
| `GDP` | Gross Domestic Product |
| `UMCSENT` | University of Michigan Consumer Sentiment |
| `HOUST` | Housing Starts |
| `INDPRO` | Industrial Production Index |
| `PCE` | Personal Consumption Expenditures |
| `DEXUSEU` | US Dollar / Euro Exchange Rate |
| `DEXCHUS` | China Yuan / US Dollar Exchange Rate |
| `SP500` | S&P 500 Index (via FRED) |
| `BAMLH0A0HYM2` | High-Yield Corporate Bond Spread |
| `DCOILWTICO` | Crude Oil WTI Spot Price |
| `GOLDAMGBD228NLBM` | Gold Fixing Price (London) |
