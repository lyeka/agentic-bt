from __future__ import annotations

import pandas as pd
import pytest

from athenaclaw.integrations.futu.config import FutuTradeConfig
from athenaclaw.integrations.futu.trade_adapter import FutuTradeAdapter
from athenaclaw.trading import SubmitLimitOrderIntent, TradeError, TradeErrorCode, encode_account_ref


class _FakeFutu:
    RET_OK = 0

    class TrdEnv:
        SIMULATE = "SIMULATE"
        REAL = "REAL"

    class OrderType:
        NORMAL = "NORMAL"

    class TrdSide:
        BUY = "BUY"
        SELL = "SELL"

    class ModifyOrderOp:
        CANCEL = "CANCEL"


class _FakeManager:
    def __init__(self, context) -> None:
        self._context = context

    def trade_context(self):
        return self._context


class _ListAccountsContext:
    def get_acc_list(self):
        return (
            0,
            pd.DataFrame(
                [
                    {
                        "acc_id": 1001,
                        "trd_env": "SIMULATE",
                        "acc_type": "CASH",
                        "uni_card_num": None,
                        "card_num": None,
                        "security_firm": None,
                        "sim_acc_type": "STOCK",
                        "trdmarket_auth": ["US"],
                        "acc_status": "ACTIVE",
                        "acc_role": None,
                        "jp_acc_type": [],
                    },
                    {
                        "acc_id": 1002,
                        "trd_env": "SIMULATE",
                        "acc_type": "MARGIN",
                        "uni_card_num": None,
                        "card_num": None,
                        "security_firm": None,
                        "sim_acc_type": "OPTION",
                        "trdmarket_auth": ["HK"],
                        "acc_status": "ACTIVE",
                        "acc_role": None,
                        "jp_acc_type": [],
                    },
                ]
            ),
        )


class _PreviewContext:
    def __init__(self, *, markets: list[str], max_buy: float = 5.0, session: str = "RTH") -> None:
        self.markets = markets
        self.max_buy = max_buy
        self.session = session
        self.preview_calls = 0

    def get_acc_list(self):
        return (
            0,
            pd.DataFrame(
                [
                    {
                        "acc_id": 1001,
                        "trd_env": "SIMULATE",
                        "acc_type": "CASH",
                        "uni_card_num": None,
                        "card_num": None,
                        "security_firm": None,
                        "sim_acc_type": "STOCK",
                        "trdmarket_auth": self.markets,
                        "acc_status": "ACTIVE",
                        "acc_role": None,
                        "jp_acc_type": [],
                    }
                ]
            ),
        )

    def acctradinginfo_query(self, **_kwargs):
        self.preview_calls += 1
        return (
            0,
            pd.DataFrame(
                [
                    {
                        "max_cash_buy": self.max_buy,
                        "max_cash_and_margin_buy": self.max_buy,
                        "max_position_sell": 0.0,
                        "session": self.session,
                    }
                ]
            ),
        )


def _make_adapter(context) -> FutuTradeAdapter:
    adapter = FutuTradeAdapter(config=FutuTradeConfig())
    adapter._manager = _FakeManager(context)
    return adapter


def test_futu_list_accounts_exposes_markets_kind_status_and_extra(monkeypatch):
    monkeypatch.setattr("athenaclaw.integrations.futu.trade_adapter._load_futu", lambda: _FakeFutu)
    adapter = _make_adapter(_ListAccountsContext())

    accounts = adapter.list_accounts()

    assert len(accounts) == 2
    us_account = accounts[0]
    hk_option = accounts[1]

    assert us_account.supported_markets == ("US",)
    assert us_account.account_status == "active"
    assert us_account.account_kind == "stock"
    assert us_account.is_simulated is True
    assert us_account.extra["sim_acc_type"] == "STOCK"
    assert us_account.extra["trdmarket_auth"] == ["US"]
    assert "simulate" in us_account.display_name
    assert "US" in us_account.display_name
    assert "stock" in us_account.display_name

    assert hk_option.supported_markets == ("HK",)
    assert hk_option.account_kind == "option"


def test_futu_preview_rejects_unsupported_market_before_provider_call(monkeypatch):
    monkeypatch.setattr("athenaclaw.integrations.futu.trade_adapter._load_futu", lambda: _FakeFutu)
    context = _PreviewContext(markets=["HK"])
    adapter = _make_adapter(context)
    intent = SubmitLimitOrderIntent(
        account_ref=encode_account_ref(broker="futu", env="simulate", account_id="1001"),
        symbol="AAPL",
        side="buy",
        quantity=1,
        limit_price=180.0,
    )

    with pytest.raises(TradeError) as exc:
        adapter.preview_limit_order(intent)

    assert exc.value.code == TradeErrorCode.ACCOUNT_MARKET_UNSUPPORTED
    assert context.preview_calls == 0


def test_futu_preview_returns_soft_warning_and_limits(monkeypatch):
    monkeypatch.setattr("athenaclaw.integrations.futu.trade_adapter._load_futu", lambda: _FakeFutu)
    context = _PreviewContext(markets=["US"], max_buy=5.0, session="RTH")
    adapter = _make_adapter(context)
    intent = SubmitLimitOrderIntent(
        account_ref=encode_account_ref(broker="futu", env="simulate", account_id="1001"),
        symbol="AAPL",
        side="buy",
        quantity=1,
        limit_price=180.0,
    )

    preview = adapter.preview_limit_order(intent)

    assert preview is not None
    assert preview.max_buy == 5.0
    assert tuple(preview.warnings) == ("provider session=RTH",)
    assert context.preview_calls == 1
