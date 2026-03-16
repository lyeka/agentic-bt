# scripts/

当前保留的脚本：

## test_yfinance_ashare_quote.py

验证 `yfinance` 对某个 A 股 ticker 的最新报价可用性和时间延迟。

### 用法

```bash
.venv/bin/python scripts/test_yfinance_ashare_quote.py
.venv/bin/python scripts/test_yfinance_ashare_quote.py --symbol 000001.SZ
.venv/bin/python scripts/test_yfinance_ashare_quote.py --timeout 8
```
