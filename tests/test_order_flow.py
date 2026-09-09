from datetime import datetime, timedelta, timezone
import pandas as pd
import numpy as np
import pytest
from src.order_flow import OrderFlowAnalyzer
from src.models import TradeSignal

@pytest.fixture
def sample_ticks():
    times = [datetime(2025, 1, 10, 10, 0, tzinfo=timezone.utc) + timedelta(seconds=i) for i in range(100)]
    # Generate 100 ticks with mostly upticks (buying pressure)
    bids = [2000.0 + (i * 0.05) for i in range(100)]
    asks = [b + 0.5 for b in bids]
    lasts = [b + 0.25 for b in bids]
    volumes = [2] * 100

    df = pd.DataFrame({
        'time': times,
        'bid': bids,
        'ask': asks,
        'last': lasts,
        'volume': volumes,
        'flags': [0] * 100
    })
    return df

def test_classify_ticks(sample_ticks):
    of = OrderFlowAnalyzer()
    classified = of.classify_ticks(sample_ticks)
    assert 'direction' in classified.columns
    assert 'delta' in classified.columns
    assert (classified['direction'] == 1).sum() > 90

def test_order_flow_metrics_and_eval(sample_ticks):
    of = OrderFlowAnalyzer(delta_threshold=0.2)
    rates_df = pd.DataFrame({
        'close': [2000.0, 2005.0]
    })
    output = of.evaluate(sample_ticks, rates_df=rates_df)

    assert output.module_name == "order_flow"
    assert output.signal == TradeSignal.BUY
    assert output.confidence > 0.5
    assert output.metadata["net_delta"] > 0

def test_order_flow_sell_signal():
    of = OrderFlowAnalyzer(delta_threshold=0.2)
    times = [datetime(2025, 1, 10, 10, 0, tzinfo=timezone.utc) + timedelta(seconds=i) for i in range(50)]
    bids = [2000.0 - (i * 0.1) for i in range(50)]
    asks = [b + 0.5 for b in bids]

    df = pd.DataFrame({
        'time': times,
        'bid': bids,
        'ask': asks,
        'last': bids,
        'volume': [3] * 50,
        'flags': [0] * 50
    })

    output = of.evaluate(df)
    assert output.signal == TradeSignal.SELL
    assert output.metadata["net_delta"] < 0

def test_absorption_flag():
    of = OrderFlowAnalyzer()
    times = [datetime(2025, 1, 10, 10, 0, tzinfo=timezone.utc) + timedelta(seconds=i) for i in range(50)]
    bids = [2000.0 + (i * 0.01) for i in range(50)] # Price barely moves

    df = pd.DataFrame({
        'time': times,
        'bid': bids,
        'ask': [b + 0.5 for b in bids],
        'last': bids,
        'volume': [10] * 50,
        'flags': [0] * 50
    })

    classified = of.classify_ticks(df)
    metrics = of.compute_metrics(classified, recent_price_change=0.05) # Small price change
    assert metrics.absorption_flag is True
