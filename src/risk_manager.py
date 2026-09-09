import logging
from dataclasses import dataclass
from datetime import datetime, date, timezone
from typing import Optional, Tuple, Dict, Any, List
import pandas as pd
import numpy as np
from src.models import TradeOrder, OrderType, Position

logger = logging.getLogger(__name__)

@dataclass
class RiskCheckResult:
    allowed: bool
    reason: str
    volume: float = 0.0
    sl: float = 0.0
    tp: float = 0.0

class RiskManager:
    """
    Risk Management Layer (non-negotiable):
    - Position sizing: Fixed % risk per trade (e.g. 1% of account equity)
    - Stop Loss / Take Profit: ATR-based (e.g., SL = 1.5x ATR, TP = 3.0x ATR)
    - Daily Loss Circuit Breaker: disables new entries once daily loss >= max_daily_loss_pct (e.g., 3%)
    - Concurrent position limit: max 1 active trade
    """
    def __init__(self,
                 risk_per_trade_pct: float = 0.01,
                 max_daily_loss_pct: float = 0.03,
                 max_concurrent_positions: int = 1,
                 atr_period: int = 14,
                 atr_sl_multiplier: float = 1.5,
                 atr_tp_multiplier: float = 3.0,
                 contract_size: float = 100.0, # 1 lot XAUUSD = 100 oz
                 min_lot: float = 0.01,
                 max_lot: float = 100.0):
        self.risk_per_trade_pct = risk_per_trade_pct
        self.max_daily_loss_pct = max_daily_loss_pct
        self.max_concurrent_positions = max_concurrent_positions
        self.atr_period = atr_period
        self.atr_sl_multiplier = atr_sl_multiplier
        self.atr_tp_multiplier = atr_tp_multiplier
        self.contract_size = contract_size
        self.min_lot = min_lot
        self.max_lot = max_lot

        self.current_date: Optional[date] = None
        self.daily_start_equity: float = 0.0
        self.circuit_breaker_tripped: bool = False

    def reset_daily_if_needed(self, current_equity: float, current_time: datetime) -> None:
        today = current_time.date()
        if self.current_date != today:
            self.current_date = today
            self.daily_start_equity = current_equity
            self.circuit_breaker_tripped = False
            logger.info(f"Daily reset: Date={today}, Starting Equity={current_equity}")

    def calculate_atr(self, rates_df: pd.DataFrame) -> float:
        if len(rates_df) < self.atr_period + 1:
            return 2.0 # Default fallback ATR for XAUUSD (~$2.00)

        df = rates_df.copy()
        highs = df['high'].values
        lows = df['low'].values
        closes = df['close'].values

        tr_list = []
        for i in range(1, len(df)):
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]),
                abs(lows[i] - closes[i - 1])
            )
            tr_list.append(tr)

        atr = float(np.mean(tr_list[-self.atr_period:]))
        return atr if atr > 0 else 2.0

    def check_trade_allowed(self,
                            order_type: OrderType,
                            current_price: float,
                            account_info: Dict[str, Any],
                            rates_df: pd.DataFrame,
                            open_positions: List[Position],
                            current_time: Optional[datetime] = None) -> RiskCheckResult:
        if current_time is None:
            current_time = datetime.now(timezone.utc)

        balance = account_info.get("balance", 10000.0)
        equity = account_info.get("equity", balance)

        self.reset_daily_if_needed(equity, current_time)

        # 1. Circuit Breaker Check
        daily_loss_pct = (self.daily_start_equity - equity) / self.daily_start_equity if self.daily_start_equity > 0 else 0.0
        if daily_loss_pct >= self.max_daily_loss_pct or self.circuit_breaker_tripped:
            self.circuit_breaker_tripped = True
            return RiskCheckResult(
                allowed=False,
                reason=f"Circuit breaker active: Daily loss ({daily_loss_pct*100:.2f}%) exceeded limit ({self.max_daily_loss_pct*100:.2f}%)"
            )

        # 2. Max Concurrent Positions Check
        if len(open_positions) >= self.max_concurrent_positions:
            return RiskCheckResult(
                allowed=False,
                reason=f"Max concurrent positions reached ({len(open_positions)}/{self.max_concurrent_positions})"
            )

        # 3. ATR and SL/TP Distance
        atr = self.calculate_atr(rates_df)
        sl_dist = atr * self.atr_sl_multiplier
        tp_dist = atr * self.atr_tp_multiplier

        if order_type == OrderType.BUY:
            sl_price = current_price - sl_dist
            tp_price = current_price + tp_dist
        else:
            sl_price = current_price + sl_dist
            tp_price = current_price - tp_dist

        # 4. Position Sizing based on fixed % risk
        risk_amount = equity * self.risk_per_trade_pct
        # Risk = Volume * contract_size * sl_dist
        volume = risk_amount / (self.contract_size * sl_dist)
        volume = round(volume, 2)
        volume = max(self.min_lot, min(self.max_lot, volume))

        return RiskCheckResult(
            allowed=True,
            reason="Trade approved by risk manager",
            volume=volume,
            sl=round(sl_price, 2),
            tp=round(tp_price, 2)
        )
