from datetime import datetime, timezone
import pandas as pd
import pytest
from src.risk_manager import RiskManager
from src.models import OrderType, Position

@pytest.fixture
def sample_rates():
    times = pd.date_range(end=datetime.now(timezone.utc), periods=20, freq="5min")
    df = pd.DataFrame({
        'time': times,
        'open': [2000.0] * 20,
        'high': [2002.0] * 20,
        'low': [1998.0] * 20,
        'close': [2000.0] * 20,
        'tick_volume': [100] * 20,
        'spread': [10] * 20,
        'real_volume': [10] * 20
    })
    return df

def test_risk_manager_approved_trade(sample_rates):
    rm = RiskManager(risk_per_trade_pct=0.01, atr_sl_multiplier=1.5, atr_tp_multiplier=3.0)
    account_info = {"balance": 10000.0, "equity": 10000.0}

    res = rm.check_trade_allowed(
        order_type=OrderType.BUY,
        current_price=2000.0,
        account_info=account_info,
        rates_df=sample_rates,
        open_positions=[]
    )

    assert res.allowed is True
    assert res.volume > 0.0
    assert res.sl < 2000.0
    assert res.tp > 2000.0

def test_circuit_breaker_tripped(sample_rates):
    rm = RiskManager(max_daily_loss_pct=0.03)
    # Start equity = 10000
    rm.reset_daily_if_needed(10000.0, datetime.now(timezone.utc))

    # Account equity dropped to 9600 (4% loss)
    account_info = {"balance": 10000.0, "equity": 9600.0}

    res = rm.check_trade_allowed(
        order_type=OrderType.BUY,
        current_price=2000.0,
        account_info=account_info,
        rates_df=sample_rates,
        open_positions=[]
    )

    assert res.allowed is False
    assert "Circuit breaker active" in res.reason

def test_max_concurrent_positions(sample_rates):
    rm = RiskManager(max_concurrent_positions=1)
    account_info = {"balance": 10000.0, "equity": 10000.0}

    pos = Position(
        ticket=1, symbol="XAUUSD", type=OrderType.BUY, volume=0.1,
        price_open=2000.0, sl=1990.0, tp=2020.0, price_current=2000.0,
        profit=0.0, time=datetime.now(timezone.utc)
    )

    res = rm.check_trade_allowed(
        order_type=OrderType.BUY,
        current_price=2000.0,
        account_info=account_info,
        rates_df=sample_rates,
        open_positions=[pos]
    )

    assert res.allowed is False
    assert "Max concurrent positions" in res.reason
