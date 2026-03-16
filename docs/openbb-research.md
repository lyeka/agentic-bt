# OpenBB 平台调研报告 — AgenticBT 集成可行性分析

> 调研日期：2026-03-12
> 调研目的：评估 OpenBB 平台对 AgenticBT 投资助手系统的集成价值、免费数据覆盖度、A 股方案可行性

## 一、OpenBB 是什么

OpenBB 是一个 **开源金融数据路由平台**（MIT License），定位为 Bloomberg Terminal 的免费替代品（Bloomberg 年费 ~$24,000）。核心理念：**Connect once, consume everywhere** — 通过统一 API 访问 100+ 数据源，无论数据来自 Yahoo Finance 还是 Bloomberg，代码零改动。

### 产品线

| 产品 | 定位 | 用户 | 付费 |
|------|------|------|------|
| **OpenBB Platform** | 开源 Python SDK + REST API | 开发者、量化 | **完全免费** |
| **OpenBB CLI** | 命令行工具（Platform 的壳） | 交易员 | **完全免费** |
| **OpenBB Workspace** | Web UI + AI Copilot | 分析师团队 | Community 免费 / Pro 付费 |
| **OpenBB Bot** | Slack/Teams 集成 | 团队协作 | Free / $8.99 / $16.99 月 |

> **关键结论**：我们只需要 **OpenBB Platform（Python SDK）**，完全免费、完全开源。

### 技术架构

```
用户请求 → Router 层（定义端点 + 数据模型）→ Provider 层（外部 API）→ TET 管道（Transform-Extract-Transform）→ 标准化数据
```

- **Router 层**：定义 `obb.equity.price.historical()` 等端点和返回模型
- **Provider 层**：每个数据源是独立扩展包（`openbb-yfinance`、`openbb-fred`），可随时插拔
- **TET 管道**：参数验证 → 调用外部 API → 结果标准化

```python
# 基础用法
from openbb import obb

# Yahoo Finance（零 Key）
aapl = obb.equity.price.historical("AAPL", provider="yfinance").to_df()

# 切换数据源只改一个参数
aapl = obb.equity.price.historical("AAPL", provider="fmp").to_df()

# 宏观经济（FRED，免费 Key）
gdp = obb.economy.gdp.nominal(provider="fred").to_df()
```

---

## 二、OpenBB 数据能力全景

### 2.1 模块清单

| 模块 | 访问方式 | 覆盖范围 | 我们系统现有? |
|------|---------|---------|-------------|
| **equity** | `obb.equity.*` | 股票价格、财务报表、估值、分析师评级、分红、拆股 | ✅ 价格有（yfinance），❌ 财务/估值缺 |
| **crypto** | `obb.crypto.*` | 加密货币价格、市值 | ❌ 完全缺失 |
| **economy** | `obb.economy.*` | GDP、CPI、失业率、央行数据、利率 | ❌ 完全缺失 |
| **forex** | `obb.forex.*` | 外汇汇率、交叉汇率 | ❌ 完全缺失 |
| **derivatives** | `obb.derivatives.*` | 期权链、期货数据 | ❌ 完全缺失 |
| **fixedincome** | `obb.fixedincome.*` | 债券收益率、信用利差 | ❌ 完全缺失 |
| **index** | `obb.index.*` | 主要指数（S&P 500、纳斯达克等） | ❌ 完全缺失 |
| **etf** | `obb.etf.*` | ETF 数据和持仓 | ❌ 完全缺失 |
| **commodity** | `obb.commodity.*` | 能源、金属、农产品 | ❌ 完全缺失 |
| **news** | `obb.news.*` | 金融新闻聚合 | ⚠️ web_search 部分覆盖 |
| **regulators** | `obb.regulators.*` | SEC 报告、披露 | ❌ 完全缺失 |

### 2.2 equity 模块详细能力（与我们最相关）

| 子模块 | 功能 | 示例 |
|--------|------|------|
| `equity.price.historical` | OHLCV 历史价格 | `obb.equity.price.historical("AAPL")` |
| `equity.price.quote` | 实时报价 | `obb.equity.price.quote("AAPL")` |
| `equity.fundamental.income` | 损益表 | `obb.equity.fundamental.income("AAPL")` |
| `equity.fundamental.balance` | 资产负债表 | `obb.equity.fundamental.balance("AAPL")` |
| `equity.fundamental.cash` | 现金流量表 | `obb.equity.fundamental.cash("AAPL")` |
| `equity.fundamental.ratios` | 财务比率（PE/PB/ROE/负债率） | `obb.equity.fundamental.ratios("AAPL")` |
| `equity.fundamental.metrics` | 关键指标 | `obb.equity.fundamental.metrics("AAPL")` |
| `equity.fundamental.revenue_per_geography` | 地域营收分布 | `obb.equity.fundamental.revenue_per_geography("AAPL")` |
| `equity.fundamental.dividends` | 分红历史 | `obb.equity.fundamental.dividends("AAPL")` |
| `equity.estimates.consensus` | 分析师一致预期 | `obb.equity.estimates.consensus("AAPL")` |
| `equity.ownership.institutional` | 机构持股 | `obb.equity.ownership.institutional("AAPL")` |
| `equity.compare.peers` | 同行对比 | `obb.equity.compare.peers("AAPL")` |
| `equity.profile` | 公司概况（行业/市值/描述） | `obb.equity.profile("AAPL")` |
| `equity.screener` | 股票筛选器 | `obb.equity.screener(...)` |

### 2.3 economy 模块详细能力

| 子模块 | 功能 | 来源 |
|--------|------|------|
| `economy.gdp.nominal` | GDP 名义值 | FRED/OECD |
| `economy.cpi` | 消费者价格指数 | FRED/OECD |
| `economy.unemployment` | 失业率 | FRED/OECD |
| `economy.interest_rate` | 基准利率 | FRED/ECB |
| `economy.calendar` | 经济日历（非农/CPI 公布日等） | Econdb/Nasdaq |
| `economy.indicators` | 各类宏观指标 | FRED |
| `economy.money_measures` | 货币供应量（M1/M2） | FRED |
| `economy.house_price_index` | 房价指数 | FRED |

---

## 三、收费情况详解

### 3.1 OpenBB 本身的收费

| 组件 | 价格 | 说明 |
|------|------|------|
| **OpenBB Platform (Python SDK)** | **永久免费** | MIT License，所有代码开源 |
| **OpenBB CLI** | **永久免费** | Platform 的命令行封装 |
| **Workspace Community** | **免费** | 个人用，Copilot 20 次/天 |
| **Workspace Pro** | 按座位收费 | 团队协作、RBAC、SSO、Excel 插件 |
| **Bot Free** | **免费** | 基础 Slack/Teams |
| **Bot Chrysalis** | $8.99/月 | 更多功能 |
| **Bot Monarch** | $16.99/月 | 企业级 |

> **结论**：我们只用 Platform SDK，**OpenBB 本身零成本**。

### 3.2 数据提供商（Provider）收费 — 这是真正的成本点

#### 完全免费（无需 API Key）

| Provider | 数据类型 | 限制 | 覆盖 |
|----------|---------|------|------|
| **Yahoo Finance** | 股票/ETF/加密/期货价格、财务报表、分析师评级 | 高频调用可能被限流 | 全球市场 |
| **CBOE** | 期权链数据 | 无 | 美股期权 |
| **ECB** | 欧洲央行利率、汇率 | 无 | 欧元区 |
| **IMF** | 国际货币基金数据 | 无 | 全球宏观 |
| **SEC EDGAR** | 10-K/10-Q 财务报告原文 | 无 | 美股 |
| **Congress.gov** | 美国国会立法数据 | 无 | 美国政策 |
| **CFTC** | 商品期货持仓报告 | 无 | 商品期货 |

#### 免费 API Key（注册即得）

| Provider | 数据类型 | 免费额度 | 注册方式 |
|----------|---------|---------|---------|
| **FRED** | 宏观经济（GDP/CPI/利率/失业率/M2 等） | **无限制** | fredaccount.stlouisfed.org |
| **Finnhub** | 美股日线 + 新闻 + 基本面 | 60 次/分钟 | finnhub.io |
| **Alpha Vantage** | 股票/外汇/加密 | 5 次/分钟，500 次/天 | alphavantage.co |
| **Polygon.io** | 美股实时/延迟报价 | 5 次/分钟（Starter 免费） | polygon.io |
| **Nasdaq Data Link** | 另类数据 | 有限 | data.nasdaq.com |
| **Biztoc** | 金融新闻聚合 | 有限 | biztoc.com |
| **Tiingo** | 美股/加密/外汇 | 1000 请求/天 | tiingo.com |

#### 付费

| Provider | 数据类型 | 起步价 |
|----------|---------|--------|
| **Financial Modeling Prep (FMP)** | 全球股票基本面 | $14/月起 |
| **Intrinio** | 美股基本面 + 期权 | $40/月起 |
| **IEX Cloud** | 实时美股数据 | $9/月起 |
| **Benzinga** | 新闻 + 评级 | 联系销售 |
| **Refinitiv/LSEG** | 机构级数据 | 企业级定价 |
| **Bloomberg** | 机构级全品种 | ~$20,000/年 |

### 3.3 免费方案覆盖度评估

**仅用 Yahoo Finance + FRED（零成本）可覆盖的场景：**

| 场景 | 覆盖度 | 说明 |
|------|--------|------|
| 美股 OHLCV 价格 | 100% | yfinance 完美覆盖 |
| 美股财务三表 | 90% | yfinance 提供近 4 年年报/季报 |
| 美股估值指标 | 85% | PE/PB/ROE 等通过 yfinance |
| 美股分析师评级 | 60% | yfinance 有部分，完整需 FMP |
| A 股 OHLCV | 80% | yfinance 支持（有延迟），Tushare 更好 |
| A 股财务报表 | 10% | yfinance 覆盖差，需 Tushare/AKShare |
| 宏观经济数据 | 95% | FRED 几乎无限（美国/全球） |
| 期权链 | 70% | CBOE 免费（美股主流标的） |
| 加密货币 | 90% | yfinance 覆盖主流币种 |
| 外汇 | 80% | yfinance/ECB 覆盖主要货币对 |
| 指数成分 | 50% | yfinance 部分支持 |
| ETF 持仓 | 40% | yfinance 有限，完整需付费 |

---

## 四、我们系统的集成分析

### 4.1 现有能力 vs OpenBB 新增能力

```
                       现有 AgenticBT                    OpenBB 新增
                    +------------------+              +------------------+
  技术面            | OHLCV 价格  [有]  |              | 已有，无需重复     |
  (technician)      | 6 种指标    [有]  |              |                   |
                    | compute 沙箱[有]  |              |                   |
                    +------------------+              +------------------+
                    +------------------+              +------------------+
  基本面            | 完全缺失    [缺]  |    -->       | 财务三表     [新]  |
  (需新建)          |                   |              | 估值指标     [新]  |
                    |                   |              | 公司概况     [新]  |
                    |                   |              | 分析师评级   [新]  |
                    +------------------+              +------------------+
                    +------------------+              +------------------+
  宏观面            | 完全缺失    [缺]  |    -->       | GDP/CPI/利率 [新]  |
  (需新建)          |                   |              | 失业率/M2    [新]  |
                    |                   |              | 经济日历     [新]  |
                    +------------------+              +------------------+
                    +------------------+              +------------------+
  信息面            | web_search  [有]  |              | news 模块         |
  (researcher)      | web_fetch   [有]  |              | （与现有重叠）     |
                    +------------------+              +------------------+
                    +------------------+              +------------------+
  新资产类别        | 仅股票      [缺]  |    -->       | 加密货币     [新]  |
  (扩展)            |                   |              | 外汇         [新]  |
                    |                   |              | 期权/期货    [新]  |
                    |                   |              | ETF          [新]  |
                    |                   |              | 商品         [新]  |
                    +------------------+              +------------------+
```

### 4.2 推荐集成的数据（按优先级）

#### P0 — 高价值 + 免费（必须集成）

| 数据 | OpenBB API | Provider | 成本 | 理由 |
|------|-----------|----------|------|------|
| **公司概况** | `obb.equity.profile()` | yfinance | 免费 | Agent 做决策前必须了解标的是什么 |
| **损益表** | `obb.equity.fundamental.income()` | yfinance | 免费 | 营收/利润趋势是基本面核心 |
| **资产负债表** | `obb.equity.fundamental.balance()` | yfinance | 免费 | 财务健康度评估 |
| **现金流量表** | `obb.equity.fundamental.cash()` | yfinance | 免费 | 自由现金流 = 真实赚钱能力 |
| **财务比率** | `obb.equity.fundamental.ratios()` | yfinance | 免费 | PE/PB/ROE 快速估值 |

#### P1 — 高价值 + 免费 Key（强烈推荐）

| 数据 | OpenBB API | Provider | 成本 | 理由 |
|------|-----------|----------|------|------|
| **GDP** | `obb.economy.gdp.nominal()` | FRED | 免费 Key | 宏观环境判断 |
| **CPI/通胀** | `obb.economy.cpi()` | FRED | 免费 Key | 利率预期 -> 股市走向 |
| **联邦基金利率** | `obb.economy.interest_rate()` | FRED | 免费 Key | 流动性环境 |
| **失业率** | `obb.economy.unemployment()` | FRED | 免费 Key | 经济周期判断 |
| **10 年期国债收益率** | FRED DGS10 | FRED | 免费 Key | 风险溢价 / 估值锚 |
| **VIX 恐慌指数** | FRED VIXCLS | FRED | 免费 Key | 市场情绪温度计 |

#### P2 — 中等价值 + 免费（可选）

| 数据 | OpenBB API | Provider | 成本 | 理由 |
|------|-----------|----------|------|------|
| **期权链** | `obb.derivatives.options.chains()` | CBOE | 免费 | 隐含波动率 / 异常持仓 |
| **加密货币** | `obb.crypto.price.historical()` | yfinance | 免费 | 扩展资产类别 |
| **外汇** | `obb.forex.pairs()` | yfinance/ECB | 免费 | 跨境投资汇率风险 |
| **分红历史** | `obb.equity.fundamental.dividends()` | yfinance | 免费 | 红利策略 |
| **机构持股** | `obb.equity.ownership.institutional()` | yfinance | 免费 | 聪明钱动向 |

#### P3 — 需付费（未来考虑）

| 数据 | Provider | 成本 | 理由 |
|------|----------|------|------|
| 分析师一致预期（完整） | FMP | $14/月 | 更精准的估值锚 |
| 实时数据流 | IEX Cloud | $9/月 | 日内交易需求 |
| 全球股票基本面 | Intrinio | $40/月 | A 股/港股/欧股深度数据 |

### 4.3 架构集成方式

**核心判断**：OpenBB 不应替代现有 MarketAdapter（OHLCV 数据），而应作为**独立的数据维度**并行存在。

```
现有路径（保持不变）:
  Agent -> market_ohlcv -> MarketAdapter -> yfinance/tushare -> OHLCV DataFrame

新增路径（独立并行）:
  Agent -> equity_fundamentals -> OpenBB Adapter -> OpenBB SDK -> 财务数据 JSON
  Agent -> equity_profile     -> OpenBB Adapter -> OpenBB SDK -> 公司概况 JSON
  Agent -> macro_data         -> OpenBB Adapter -> OpenBB SDK -> 宏观数据 JSON
```

**设计要点**：
1. **Optional Dependency** — `pip install -e ".[openbb]"` 可选安装，不安装时所有现有功能不受影响
2. **薄包装层** — `src/agent/adapters/openbb.py` 集中所有 SDK 调用，单一变更点
3. **工具层** — 新建 `fundamentals.py` 和 `macro.py`，遵循现有 `register(kernel)` 模式
4. **条件注册** — runtime.py 中 `try/except ImportError` 静默跳过
5. **新子代理** — `fundamentalist` 子代理：工具白名单 `[equity_fundamentals, equity_profile, compute]`

### 4.4 Agent 能力升级后的典型工作流

```
用户: "帮我分析 AAPL 值不值得买"

Agent 决策链:
  1. ask_technician("分析 AAPL 技术面")
     -> market_ohlcv -> compute -> SMA/RSI/MACD/BB
     -> 输出: 趋势 bullish, RSI 中性, MACD 金叉

  2. ask_fundamentalist("分析 AAPL 基本面")         <-- 新能力
     -> equity_profile -> "Apple Inc., Technology, $3.2T"
     -> equity_fundamentals(income_statement) -> 营收/利润趋势
     -> equity_fundamentals(ratios) -> PE 34, PB 52, ROE 157%
     -> 输出: 盈利能力强, 估值偏高, 负债健康

  3. ask_researcher("查 AAPL 最近新闻")
     -> web_search + web_fetch -> 新闻/事件/风险

  4. macro_data("FEDFUNDS") + macro_data("DGS10")   <-- 新能力
     -> 利率环境: 降息周期, 利好成长股

  5. 主 Agent 整合四维信息，做出决策
     -> "技术面向好 + 基本面强但估值高 + 降息利好 -> 建议小仓位建仓"
```

---

## 五、风险与注意事项

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| **yfinance 限流** | 高频调用被封 IP | 控制请求间隔，Agent 级别做 rate limit |
| **yfinance 数据质量** | 财务数据可能不完整/延迟 | 关键决策交叉验证，description 提示 LLM |
| **A 股基本面** | yfinance 覆盖差 | 后续可接 AKShare/Tushare 做 OpenBB Provider |
| **OpenBB 版本更新** | API 可能变动 | 薄包装层隔离，版本锁定 |
| **FRED Key 泄露** | 安全风险 | .env 管理，.gitignore 保护 |
| **Token 消耗** | 财务数据返回量大 | 工具 limit 参数控制，默认 4 期 |

---

## 六、A 股基本面数据深度方案

### 6.1 问题本质

OpenBB 默认的 yfinance provider 对美股基本面覆盖 ~90%，但对 A 股基本面覆盖 ~10%。中国大陆用户使用 yfinance 还有 VPN 障碍。这是 OpenBB 在中国市场的核心短板。

### 6.2 三条路径对比

#### 路径 A：AKShare（推荐 — 完全免费 + 已有 OpenBB 扩展）

**AKShare** 是国内开发者维护的开源 Python 金融数据接口库（MIT License），从新浪财经、东方财富、同花顺等公开网站抓取数据，**完全免费，无需 API Key，无积分限制**。

| 维度 | 详情 |
|------|------|
| **安装** | `pip install akshare` |
| **成本** | **永久免费** |
| **认证** | **无需任何 Key/Token** |
| **A 股财务三表** | 东方财富源：按报告期/年度/单季度全覆盖 |
| **财务关键指标** | 新浪财经源：PE/PB/ROE 等 |
| **A 股行情** | 日线/分钟级 |
| **分红/送转** | 历史分红送转记录 |
| **十大股东** | 流通股东 + 实控人链条 |
| **资金流向** | 主力/散户资金流向（东财） |
| **沪深港通** | 北向/南向资金流数据 |
| **限流** | 频繁调用可能被封 IP（爬虫本质） |
| **数据质量** | 网页爬取，偶尔格式变化导致接口失效 |
| **OpenBB 扩展** | 已有 `openbb_akshare` 社区扩展（github.com/finanalyzer/openbb_akshare） |

**关键 API 清单（A 股财务）：**

```python
import akshare as ak

# 损益表（东方财富，按年度）
ak.stock_profit_sheet_by_yearly_em(symbol="600519")

# 资产负债表（东方财富，按报告期）
ak.stock_balance_sheet_by_report_em(symbol="600519")

# 现金流量表（东方财富，按年度）
ak.stock_cash_flow_sheet_by_yearly_em(symbol="600519")

# 财务摘要（新浪财经）
ak.stock_financial_abstract(symbol="600519")

# 基本面指标（市盈率/市净率/市销率）
ak.stock_a_lg_indicator(stock="600519")

# 三表也可从新浪源获取
ak.stock_financial_report_sina(stock="sh600519", symbol="利润表")
```

**OpenBB 统一接口（通过 openbb_akshare 扩展）：**

```python
from openbb import obb

# 安装扩展后，可以用统一接口访问 A 股
data = obb.equity.price.historical("600519", provider="akshare").to_df()
```

#### 路径 B：Tushare Pro（需积分，财务数据门槛高）

| 维度 | 详情 |
|------|------|
| **安装** | `pip install tushare` |
| **成本** | 注册免费，高级接口需积分 |
| **认证** | Token（注册即得） |
| **积分制度** | 注册 100 分 + 完善信息 20 分 = **120 分基础** |
| **财务报表门槛** | **需要 800 积分**（注册后远不够） |
| **每日基本面** | **需要 2000-5000 积分** |
| **获取积分** | 推荐注册 50 分/人、高校用户免费、付费 200 元 = 2000 分 |
| **数据质量** | 最高（专业金融数据库级别） |
| **A 股行情** | 日线/分钟（我们已集成 TushareAdapter） |
| **稳定性** | 专业 API，不是爬虫 |

**积分墙的现实**：

```
注册后基础积分: 120 分
  stock_basic (基础信息): 够用（120 分）
  daily (日线行情): 够用（120 分）  <-- 我们现在用的
  fina_indicator (财务指标): 需要 800 分
  income (损益表): 需要 800 分
  balancesheet (资产负债表): 需要 800 分
  cashflow (现金流量表): 需要 800 分
  daily_basic (每日基本面): 需要 2000-5000 分
```

> **结论**：Tushare 数据质量最高，但免费额度无法覆盖财务报表。除非付费 200 元或有高校身份，否则基本面数据不可用。

#### 路径 C：直接用 AKShare（不通过 OpenBB）

如果不追求 OpenBB 统一接口的优雅，可以直接在我们的 adapter 层调用 AKShare API，绕过 OpenBB。

**优点**：少一层抽象，少一个依赖
**缺点**：失去 Provider 切换能力（A 股/美股要写不同的数据清洗代码），未来无法复用 OpenBB 生态

### 6.3 推荐方案

```
                    美股基本面              A 股基本面
                 +--------------+     +--------------+
  OpenBB 统一层  | obb.equity.* |     | obb.equity.* |
                 | provider=    |     | provider=    |
                 |  "yfinance"  |     |  "akshare"   |
                 +------+-------+     +------+-------+
                        |                    |
  数据源层        Yahoo Finance          AKShare (东财/新浪)
                   (免费, 零Key)          (免费, 零Key)
                        |                    |
                        +--------+-----------+
                                 |
  我们的 adapter   src/agent/adapters/openbb.py
                                 |
  工具层           src/agent/tools/fundamentals.py
                                 |
  Agent 层                 fundamentalist 子代理
```

**分阶段**：
- **Phase 1**：先用 OpenBB + yfinance 做美股基本面（零成本验证架构）
- **Phase 2**：安装 `openbb_akshare` 扩展，同一套工具自动支持 A 股
- **备选**：如果 `openbb_akshare` 扩展不稳定，在 `adapters/openbb.py` 中直接调用 AKShare API 做 fallback

### 6.4 A 股可获取的免费数据（AKShare 完整清单）

| 数据类别 | 接口 | 数据源 | 免费 |
|---------|------|--------|------|
| **损益表**（年度） | `stock_profit_sheet_by_yearly_em` | 东方财富 | 是 |
| **损益表**（季报） | `stock_profit_sheet_by_quarterly_em` | 东方财富 | 是 |
| **资产负债表**（年度） | `stock_balance_sheet_by_yearly_em` | 东方财富 | 是 |
| **现金流量表**（年度） | `stock_cash_flow_sheet_by_yearly_em` | 东方财富 | 是 |
| **财务摘要** | `stock_financial_abstract` | 新浪财经 | 是 |
| **PE/PB/PS** | `stock_a_lg_indicator` | 乐咕乐股 | 是 |
| **个股研报** | `stock_research_report_em` | 东方财富 | 是 |
| **分红送转** | `stock_history_dividend_detail` | 东方财富 | 是 |
| **十大流通股东** | `stock_circulate_stock_holder_em` | 东方财富 | 是 |
| **资金流向** | `stock_individual_fund_flow` | 东方财富 | 是 |
| **北向资金** | `stock_hsgt_north_net_flow_in_em` | 东方财富 | 是 |
| **行业分类** | `stock_board_industry_name_em` | 东方财富 | 是 |
| **龙虎榜** | `stock_lhb_detail_em` | 东方财富 | 是 |
| **融资融券** | `stock_margin_detail_szse` | 深交所 | 是 |
| **大宗交易** | `stock_blocktrade_detail_daily_em` | 东方财富 | 是 |

> **全部免费，无需任何认证。** 但本质是爬虫，高频调用可能被限流。

### 6.5 A 股方案风险评估

| 风险 | 严重度 | 缓解措施 |
|------|--------|---------|
| **AKShare 接口变更** | 中 | 爬虫依赖网页结构，定期更新 akshare 版本 |
| **IP 限流** | 中 | 加请求间隔（`time.sleep(0.5)`）、本地缓存已获取的财务数据 |
| **openbb_akshare 扩展不稳定** | 中 | 社区项目，可能跟不上 OpenBB 版本；备选方案：直接调 AKShare |
| **数据延迟** | 低 | 财务报表本身是季度更新，延迟几小时无影响 |
| **数据准确性** | 低 | 东财/新浪数据来源可靠，但偶有格式错误 |

---

## 七、总结

| 维度 | 结论 |
|------|------|
| **OpenBB 定位** | 金融数据路由中间层，不是数据库，是数据转换器 |
| **成本** | SDK 永久免费；Yahoo Finance + FRED + AKShare 覆盖 90%+ 需求，零成本 |
| **核心价值** | 补全基本面 + 宏观面认知维度，从技术分析单腿走路升级为全面投研 |
| **集成方式** | Optional dependency + 独立数据维度 + 条件注册，零侵入现有架构 |
| **优先级** | P0 基本面（免费）-> P1 宏观（免费 Key）-> P2 A 股基本面（AKShare 免费）-> P3 衍生品/多资产 |
| **美股基本面** | OpenBB + yfinance（免费，覆盖 90%） |
| **A 股基本面** | AKShare（完全免费，东方财富/新浪源，已有 OpenBB 扩展） |
| **Tushare 限制** | 财务数据需 800 积分（注册仅 120），不推荐作为免费基本面方案 |

---

## 八、参考资源

- [OpenBB 官网](https://openbb.co/) / [GitHub](https://github.com/OpenBB-finance/OpenBB)
- [OpenBB 文档](https://docs.openbb.co/) / [Python SDK](https://docs.openbb.co/python)
- [OpenBB 定价](https://openbb.co/pricing/)
- [OpenBB 数据提供商列表](https://my.openbb.co/app/platform/data-providers)
- [OpenBB A 股扩展博文](https://openbb.co/blog/extending-openbb-for-a-share-and-hong-kong-stock-analysis-with-akshare-and-tushare)
- [openbb_akshare GitHub](https://github.com/finanalyzer/openbb_akshare)
- [AKShare 官方文档](https://akshare.akfamily.xyz/) / [GitHub](https://github.com/akfamily/akshare)
- [AKShare 股票数据字典](https://akshare.akfamily.xyz/data/stock/stock.html)
- [Tushare Pro 积分权限](https://tushare.pro/document/1?doc_id=108)
- [FRED API](https://fredaccount.stlouisfed.org/)
- [OpenBB TET 数据管道设计](https://openbb.co/blog/the-openbb-platform-data-pipeline)
- [OpenBB 架构博客](https://openbb.co/blog/exploring-the-architecture-behind-the-openbb-platform)
