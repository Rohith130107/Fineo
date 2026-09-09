import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any
import pandas as pd
import numpy as np
from src.models import TradeSignal, SignalOutput

logger = logging.getLogger(__name__)

@dataclass
class OrderFlowMetrics:
    total_volume: int
    buy_volume: int
    sell_volume: int
    net_delta: int
    delta_ratio: float # net_delta / total_volume (-1.0 to 1.0)
    absorption_flag: bool
    exhaustion_flag: bool

class OrderFlowAnalyzer:
    """
    Order Flow Analyzer using tick data (`copy_ticks_range` proxy or DOM)
    to compute cumulative volume delta, aggressor pressure, and order flow divergences.
    """
    def __init__(self, lookback_minutes: int = 15, delta_threshold: float = 0.2):
        self.lookback_minutes = lookback_minutes
        self.delta_threshold = delta_threshold

    def classify_ticks(self, ticks_df: pd.DataFrame) -> pd.DataFrame:
        """
        Classifies each tick as Buy (+1) or Sell (-1) aggressor side.
        - Uses bid/ask crossing heuristic if bid/ask available.
        - Falls back to tick price change (uptick/downtick rule) if price change > 0 or < 0.
        """
        if ticks_df.empty:
            return ticks_df

        df = ticks_df.copy()

        # Determine tick price: 'last' if available and > 0, else 'bid'
        if 'last' in df.columns and (df['last'] > 0).any():
            prices = df['last'].values
        elif 'bid' in df.columns:
            prices = df['bid'].values
        else:
            prices = df['close'].values if 'close' in df.columns else np.zeros(len(df))

        volumes = df['volume'].values if 'volume' in df.columns else np.ones(len(df))

        # Tick direction via uptick/downtick rule
        price_diffs = np.diff(prices, prepend=prices[0])
        directions = np.where(price_diffs > 0, 1, np.where(price_diffs < 0, -1, 0))

        # Forward fill zero directions (zero-tick rule)
        for i in range(1, len(directions)):
            if directions[i] == 0:
                directions[i] = directions[i - 1]

        # If all were zero, default to 1
        if (directions == 0).all():
            directions[:] = 1

        df['direction'] = directions
        df['buy_vol'] = np.where(directions == 1, volumes, 0)
        df['sell_vol'] = np.where(directions == -1, volumes, 0)
        df['delta'] = directions * volumes

        return df

    def compute_metrics(self, classified_ticks: pd.DataFrame, recent_price_change: float = 0.0) -> OrderFlowMetrics:
        """
        Computes rolling volume delta and checks for absorption/exhaustion flags.
        - Absorption: High delta with minimal price movement (delta diverges from price).
        - Exhaustion: Very low volume / delta at extreme prices.
        """
        if classified_ticks.empty:
            return OrderFlowMetrics(
                total_volume=0, buy_volume=0, sell_volume=0, net_delta=0,
                delta_ratio=0.0, absorption_flag=False, exhaustion_flag=False
            )

        buy_vol = int(classified_ticks['buy_vol'].sum())
        sell_vol = int(classified_ticks['sell_vol'].sum())
        total_vol = buy_vol + sell_vol
        net_delta = buy_vol - sell_vol

        delta_ratio = float(net_delta / total_vol) if total_vol > 0 else 0.0

        # Absorption heuristic: High delta (|delta_ratio| > 0.4) but near zero price change
        absorption_flag = False
        if abs(delta_ratio) > 0.4 and abs(recent_price_change) < 0.2:
            absorption_flag = True

        # Exhaustion heuristic: low relative volume while price moving fast
        exhaustion_flag = False
        if total_vol < 50 and abs(recent_price_change) > 1.0:
            exhaustion_flag = True

        return OrderFlowMetrics(
            total_volume=total_vol,
            buy_volume=buy_vol,
            sell_volume=sell_vol,
            net_delta=net_delta,
            delta_ratio=delta_ratio,
            absorption_flag=absorption_flag,
            exhaustion_flag=exhaustion_flag
        )

    def evaluate(self, ticks_df: pd.DataFrame, rates_df: Optional[pd.DataFrame] = None) -> SignalOutput:
        if ticks_df.empty:
            return SignalOutput(
                module_name="order_flow",
                signal=TradeSignal.NEUTRAL,
                confidence=0.0,
                metadata={"reason": "No tick data available"}
            )

        classified = self.classify_ticks(ticks_df)

        recent_price_change = 0.0
        if rates_df is not None and not rates_df.empty and len(rates_df) >= 2:
            recent_price_change = float(rates_df['close'].iloc[-1] - rates_df['close'].iloc[-2])

        metrics = self.compute_metrics(classified, recent_price_change)

        if metrics.delta_ratio > self.delta_threshold:
            signal = TradeSignal.BUY
            confidence = min(abs(metrics.delta_ratio), 1.0)
        elif metrics.delta_ratio < -self.delta_threshold:
            signal = TradeSignal.SELL
            confidence = min(abs(metrics.delta_ratio), 1.0)
        else:
            signal = TradeSignal.NEUTRAL
            confidence = 0.0

        # Reduce confidence if absorption is detected (buyer/seller being absorbed)
        if metrics.absorption_flag:
            confidence *= 0.5

        return SignalOutput(
            module_name="order_flow",
            signal=signal,
            confidence=float(confidence),
            metadata={
                "total_volume": metrics.total_volume,
                "buy_volume": metrics.buy_volume,
                "sell_volume": metrics.sell_volume,
                "net_delta": metrics.net_delta,
                "delta_ratio": metrics.delta_ratio,
                "absorption": metrics.absorption_flag,
                "exhaustion": metrics.exhaustion_flag
            }
        )
