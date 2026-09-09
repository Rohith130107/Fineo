from datetime import datetime, timedelta, timezone
import pandas as pd
import numpy as np
import pytest
from src.config import load_config
from src.backtest_harness import BacktestEngine

@pytest.fixture
def backtest_data():
    times = pd.date_range(start=datetime(2025, 1, 10, 0, 0, tzinfo=timezone.utc), periods=100, freq="5min")
    prices = 2000.0 + np.sin(np.linspace(0, 4 * np.pi, 100)) * 10.0

    df = pd.DataFrame({
        'time': times,
        'open': prices,
        'high': prices + 1.5,
        'low': prices - 1.5,
        'close': prices + 0.5,
        'tick_volume': [100] * 100,
        'spread': [10] * 100,
        'real_volume': [10] * 100
    })
    return df

def test_backtest_harness_run(backtest_data):
    config = load_config("config.yaml")
    engine = BacktestEngine(config=config, initial_balance=10000.0)

    result = engine.run(backtest_data)
    assert isinstance(result.total_trades, int)
    assert 0.0 <= result.win_rate <= 1.0
    assert isinstance(result.profit_factor, float)
    assert isinstance(result.max_drawdown, float)
