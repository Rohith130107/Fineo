from datetime import datetime, timedelta, timezone
import pandas as pd
import numpy as np
import pytest
from src.price_action import PriceActionAnalyzer, SwingPoint, SRLevel
from src.models import TradeSignal

@pytest.fixture
def sample_rates():
    # Construct synthetic candles with known highs and lows
    times = [datetime(2025, 1, 10, 8, 0, tzinfo=timezone.utc) + timedelta(minutes=5 * i) for i in range(30)]

    # Prices moving up then down
    opens = [2000 + i for i in range(30)]
    highs = [2000 + i + 1 for i in range(30)]
    lows = [2000 + i - 1 for i in range(30)]
    closes = [2000 + i + 0.5 for i in range(30)]

    # Inject explicit Swing High at index 10
    highs[10] = 2050.0
    opens[10] = 2040.0
    closes[10] = 2045.0

    # Inject explicit Swing Low at index 20
    lows[20] = 1950.0
    opens[20] = 1960.0
    closes[20] = 1955.0

    df = pd.DataFrame({
        'time': times,
        'open': opens,
        'high': highs,
        'low': lows,
        'close': closes,
        'tick_volume': [100] * 30,
        'spread': [10] * 30,
        'real_volume': [10] * 30
    })
    return df

def test_swing_detection(sample_rates):
    pa = PriceActionAnalyzer(pivot_left_bars=2, pivot_right_bars=2)
    swings = pa.find_swings(sample_rates)

    swing_highs = [s for s in swings if s.is_high]
    swing_lows = [s for s in swings if not s.is_high]

    assert len(swing_highs) >= 1
    assert any(s.price == 2050.0 and s.index == 10 for s in swing_highs)

    assert len(swing_lows) >= 1
    assert any(s.price == 1950.0 and s.index == 20 for s in swing_lows)

def test_structure_and_choch():
    pa = PriceActionAnalyzer(pivot_left_bars=2, pivot_right_bars=2)
    # Create dataset with clear uptrend then break of low (CHoCH)
    times = [datetime(2025, 1, 10, 8, 0, tzinfo=timezone.utc) + timedelta(minutes=5 * i) for i in range(15)]

    prices = [100, 102, 105, 103, 108, 104, 102, 95, 90, 88, 85, 80, 78, 75, 70]
    df = pd.DataFrame({
        'time': times,
        'open': prices,
        'high': [p + 1 for p in prices],
        'low': [p - 1 for p in prices],
        'close': prices,
        'tick_volume': [100] * 15,
        'spread': [10] * 15,
        'real_volume': [10] * 15
    })

    swings = pa.find_swings(df)
    structure = pa.analyze_structure(df, swings)
    assert structure.trend in [TradeSignal.BUY, TradeSignal.SELL, TradeSignal.NEUTRAL]

def test_session_sr_levels():
    pa = PriceActionAnalyzer()
    # Data across two days
    times = [
        datetime(2025, 1, 9, 10, 0, tzinfo=timezone.utc),
        datetime(2025, 1, 9, 15, 0, tzinfo=timezone.utc),
        datetime(2025, 1, 10, 9, 0, tzinfo=timezone.utc),
        datetime(2025, 1, 10, 14, 0, tzinfo=timezone.utc),
    ]
    df = pd.DataFrame({
        'time': times,
        'open': [2000, 2010, 2020, 2030],
        'high': [2005, 2015, 2025, 2035],
        'low': [1995, 2005, 2015, 2025],
        'close': [2002, 2012, 2022, 2032],
        'tick_volume': [100] * 4,
        'spread': [10] * 4,
        'real_volume': [10] * 4
    })

    levels = pa.calculate_session_sr_levels(df)
    names = [l.name for l in levels]
    assert "Prior Day High" in names
    assert "Prior Day Low" in names
    assert "London Open" in names
    assert "NY Open" in names

def test_price_action_evaluation(sample_rates):
    pa = PriceActionAnalyzer()
    output = pa.evaluate(sample_rates, higher_df=sample_rates)
    assert output.module_name == "price_action"
    assert 0.0 <= output.confidence <= 1.0
    assert "trend" in output.metadata
