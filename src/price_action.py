import logging
from dataclasses import dataclass, field
from datetime import datetime, time, timezone
from typing import List, Dict, Optional, Tuple
import pandas as pd
import numpy as np
from src.models import TradeSignal, SignalOutput

logger = logging.getLogger(__name__)

@dataclass
class SwingPoint:
    index: int
    time: datetime
    price: float
    is_high: bool # True for Swing High, False for Swing Low

@dataclass
class MarketStructure:
    trend: TradeSignal # BUY (Bullish), SELL (Bearish), or NEUTRAL
    last_bos: Optional[SwingPoint] = None
    last_choch: Optional[SwingPoint] = None
    recent_swings: List[SwingPoint] = field(default_factory=list)

@dataclass
class SRLevel:
    name: str
    price: float
    level_type: str # 'support' or 'resistance'

class PriceActionAnalyzer:
    def __init__(self, pivot_left_bars: int = 2, pivot_right_bars: int = 2):
        self.pivot_left = pivot_left_bars
        self.pivot_right = pivot_right_bars

    def find_swings(self, df: pd.DataFrame) -> List[SwingPoint]:
        """
        Detects swing highs and lows using N-bar pivot logic.
        Swing High: high > max(left N highs) and high > max(right N highs).
        Swing Low: low < min(left N lows) and low < min(right N lows).
        """
        swings: List[SwingPoint] = []
        if len(df) < (self.pivot_left + self.pivot_right + 1):
            return swings

        highs = df['high'].values
        lows = df['low'].values
        times = df['time'].values

        for i in range(self.pivot_left, len(df) - self.pivot_right):
            current_high = highs[i]
            left_highs = highs[i - self.pivot_left:i]
            right_highs = highs[i + 1:i + 1 + self.pivot_right]

            if current_high > max(left_highs) and current_high > max(right_highs):
                swings.append(SwingPoint(
                    index=i,
                    time=pd.to_datetime(times[i]),
                    price=float(current_high),
                    is_high=True
                ))

            current_low = lows[i]
            left_lows = lows[i - self.pivot_left:i]
            right_lows = lows[i + 1:i + 1 + self.pivot_right]

            if current_low < min(left_lows) and current_low < min(right_lows):
                swings.append(SwingPoint(
                    index=i,
                    time=pd.to_datetime(times[i]),
                    price=float(current_low),
                    is_high=False
                ))

        swings.sort(key=lambda s: s.index)
        return swings

    def analyze_structure(self, df: pd.DataFrame, swings: List[SwingPoint]) -> MarketStructure:
        """
        Determines market structure (BOS, CHoCH) and current trend.
        - Bullish BOS: Price breaks above prior swing high during an uptrend.
        - Bearish BOS: Price breaks below prior swing low during a downtrend.
        - CHoCH: Price breaks key opposite swing point reversing trend.
        """
        if not swings:
            return MarketStructure(trend=TradeSignal.NEUTRAL, recent_swings=[])

        current_trend = TradeSignal.NEUTRAL
        last_bos = None
        last_choch = None

        closes = df['close'].values

        active_swing_high: Optional[SwingPoint] = None
        active_swing_low: Optional[SwingPoint] = None

        for swing in swings:
            if swing.is_high:
                active_swing_high = swing
            else:
                active_swing_low = swing

            swing_idx = swing.index
            # Check price behavior after the swing point formation
            for idx in range(swing_idx + 1, len(df)):
                close_p = closes[idx]

                if active_swing_high and close_p > active_swing_high.price:
                    if current_trend == TradeSignal.BUY:
                        last_bos = active_swing_high
                    elif current_trend in (TradeSignal.SELL, TradeSignal.NEUTRAL):
                        last_choch = active_swing_high
                        current_trend = TradeSignal.BUY
                    active_swing_high = None # Broken

                if active_swing_low and close_p < active_swing_low.price:
                    if current_trend == TradeSignal.SELL:
                        last_bos = active_swing_low
                    elif current_trend in (TradeSignal.BUY, TradeSignal.NEUTRAL):
                        last_choch = active_swing_low
                        current_trend = TradeSignal.SELL
                    active_swing_low = None # Broken

        return MarketStructure(
            trend=current_trend,
            last_bos=last_bos,
            last_choch=last_choch,
            recent_swings=swings[-5:] if swings else []
        )

    def calculate_session_sr_levels(self, df: pd.DataFrame) -> List[SRLevel]:
        """
        Builds dynamic support/resistance map from:
        - Prior day high/low
        - London session open/high/low (08:00 - 16:00 UTC)
        - NY session open/high/low (13:00 - 21:00 UTC)
        """
        levels: List[SRLevel] = []
        if df.empty:
            return levels

        df_copy = df.copy()
        if not pd.api.types.is_datetime64_any_dtype(df_copy['time']):
            df_copy['time'] = pd.to_datetime(df_copy['time'])

        # Prior Day High / Low
        df_copy['date'] = df_copy['time'].dt.date
        unique_dates = df_copy['date'].unique()
        if len(unique_dates) >= 2:
            prior_date = unique_dates[-2]
            prior_day_df = df_copy[df_copy['date'] == prior_date]
            levels.append(SRLevel("Prior Day High", float(prior_day_df['high'].max()), "resistance"))
            levels.append(SRLevel("Prior Day Low", float(prior_day_df['low'].min()), "support"))

        # Session levels for current date
        latest_date = unique_dates[-1]
        today_df = df_copy[df_copy['date'] == latest_date]

        # London Session (08:00 - 16:00 UTC)
        london_df = today_df[(today_df['time'].dt.hour >= 8) & (today_df['time'].dt.hour < 16)]
        if not london_df.empty:
            levels.append(SRLevel("London Open", float(london_df['open'].iloc[0]), "support"))
            levels.append(SRLevel("London High", float(london_df['high'].max()), "resistance"))
            levels.append(SRLevel("London Low", float(london_df['low'].min()), "support"))

        # NY Session (13:00 - 21:00 UTC)
        ny_df = today_df[(today_df['time'].dt.hour >= 13) & (today_df['time'].dt.hour < 21)]
        if not ny_df.empty:
            levels.append(SRLevel("NY Open", float(ny_df['open'].iloc[0]), "support"))
            levels.append(SRLevel("NY High", float(ny_df['high'].max()), "resistance"))
            levels.append(SRLevel("NY Low", float(ny_df['low'].min()), "support"))

        return levels

    def evaluate(self, primary_df: pd.DataFrame, higher_df: Optional[pd.DataFrame] = None) -> SignalOutput:
        """
        Combines primary timeframe (M5/M15) and higher timeframe (H1) analysis into SignalOutput.
        """
        if primary_df.empty:
            return SignalOutput(
                module_name="price_action",
                signal=TradeSignal.NEUTRAL,
                confidence=0.0,
                metadata={"reason": "Primary dataframe is empty"}
            )

        primary_swings = self.find_swings(primary_df)
        primary_structure = self.analyze_structure(primary_df, primary_swings)
        sr_levels = self.calculate_session_sr_levels(primary_df)

        confidence = 0.5
        signal = primary_structure.trend

        higher_trend = TradeSignal.NEUTRAL
        if higher_df is not None and not higher_df.empty:
            htf_swings = self.find_swings(higher_df)
            htf_structure = self.analyze_structure(higher_df, htf_swings)
            higher_trend = htf_structure.trend

            if signal != TradeSignal.NEUTRAL:
                if higher_trend == signal:
                    confidence += 0.35 # Alignment with higher timeframe
                elif higher_trend != TradeSignal.NEUTRAL and higher_trend != signal:
                    confidence -= 0.25 # Conflict with higher timeframe

        current_price = float(primary_df['close'].iloc[-1])
        nearest_level = None
        min_dist = float('inf')

        for lvl in sr_levels:
            dist = abs(current_price - lvl.price)
            if dist < min_dist:
                min_dist = dist
                nearest_level = lvl

        confidence = float(np.clip(confidence, 0.0, 1.0))

        return SignalOutput(
            module_name="price_action",
            signal=signal,
            confidence=confidence,
            metadata={
                "trend": signal.value,
                "higher_trend": higher_trend.value,
                "swing_count": len(primary_swings),
                "nearest_sr_level": nearest_level.name if nearest_level else None,
                "nearest_sr_distance": min_dist if nearest_level else None,
                "last_bos": primary_structure.last_bos.price if primary_structure.last_bos else None,
                "last_choch": primary_structure.last_choch.price if primary_structure.last_choch else None,
            }
        )
