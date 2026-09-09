import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
import pandas as pd
import numpy as np

from src.models import TradeSignal, OrderType
from src.price_action import PriceActionAnalyzer
from src.order_flow import OrderFlowAnalyzer
from src.news_filter import NewsFilterModule
from src.confluence_engine import ConfluenceEngine
from src.risk_manager import RiskManager

logger = logging.getLogger(__name__)

@dataclass
class BacktestTrade:
    entry_time: datetime
    exit_time: Optional[datetime]
    type: OrderType
    entry_price: float
    exit_price: Optional[float]
    volume: float
    sl: float
    tp: float
    pnl: float = 0.0
    exit_reason: str = ""

@dataclass
class BacktestResult:
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    total_pnl: float
    profit_factor: float
    max_drawdown: float
    max_drawdown_pct: float
    trades: List[BacktestTrade]

class BacktestEngine:
    """
    Vectorized & Sequential Historical Backtesting Harness.
    Uses exact shared signal pipeline: Price Action, Order Flow, News Filter, Confluence Engine, and Risk Manager.
    """
    def __init__(self,
                 config: dict,
                 initial_balance: float = 10000.0,
                 contract_size: float = 100.0):
        self.config = config
        self.initial_balance = initial_balance
        self.contract_size = contract_size

        pa_cfg = config.get("price_action", {})
        self.pa_analyzer = PriceActionAnalyzer(
            pivot_left_bars=pa_cfg.get("pivot_left_bars", 2),
            pivot_right_bars=pa_cfg.get("pivot_right_bars", 2)
        )

        of_cfg = config.get("order_flow", {})
        self.of_analyzer = OrderFlowAnalyzer(
            lookback_minutes=of_cfg.get("lookback_minutes", 15)
        )

        news_cfg = config.get("news", {})
        self.news_filter = NewsFilterModule(
            provider=news_cfg.get("provider", "finnhub"),
            api_key=news_cfg.get("api_key", ""),
            blackout_before_min=news_cfg.get("blackout_before_min", 15),
            blackout_after_min=news_cfg.get("blackout_after_min", 15)
        )

        conf_cfg = config.get("confluence", {})
        self.confluence_engine = ConfluenceEngine(
            min_signals_required=conf_cfg.get("min_signals_required", 2)
        )

        risk_cfg = config.get("risk", {})
        self.risk_manager = RiskManager(
            risk_per_trade_pct=risk_cfg.get("risk_per_trade_pct", 0.01),
            max_daily_loss_pct=risk_cfg.get("max_daily_loss_pct", 0.03),
            max_concurrent_positions=risk_cfg.get("max_concurrent_positions", 1),
            atr_period=risk_cfg.get("atr_period", 14),
            atr_sl_multiplier=risk_cfg.get("atr_sl_multiplier", 1.5),
            atr_tp_multiplier=risk_cfg.get("atr_tp_multiplier", 3.0),
            contract_size=contract_size
        )

    def run(self, rates_df: pd.DataFrame, ticks_df: Optional[pd.DataFrame] = None) -> BacktestResult:
        if rates_df.empty or len(rates_df) < 30:
            return BacktestResult(
                total_trades=0, winning_trades=0, losing_trades=0,
                win_rate=0.0, total_pnl=0.0, profit_factor=0.0,
                max_drawdown=0.0, max_drawdown_pct=0.0, trades=[]
            )

        balance = self.initial_balance
        equity = balance
        peak_equity = equity
        max_drawdown = 0.0
        max_drawdown_pct = 0.0

        open_trade: Optional[BacktestTrade] = None
        closed_trades: List[BacktestTrade] = []

        window_size = 30 # Min bars for price action calculation

        for i in range(window_size, len(rates_df)):
            curr_slice = rates_df.iloc[:i+1]
            curr_bar = curr_slice.iloc[-1]
            curr_time = pd.to_datetime(curr_bar['time'])
            if curr_time.tzinfo is None:
                curr_time = curr_time.replace(tzinfo=timezone.utc)

            curr_open = float(curr_bar['open'])
            curr_high = float(curr_bar['high'])
            curr_low = float(curr_bar['low'])
            curr_close = float(curr_bar['close'])

            # 1. Manage existing open trade (SL/TP check)
            if open_trade is not None:
                hit_sl = False
                hit_tp = False

                if open_trade.type == OrderType.BUY:
                    if curr_low <= open_trade.sl:
                        hit_sl = True
                        exit_p = open_trade.sl
                    elif curr_high >= open_trade.tp:
                        hit_tp = True
                        exit_p = open_trade.tp
                else: # SELL
                    if curr_high >= open_trade.sl:
                        hit_sl = True
                        exit_p = open_trade.sl
                    elif curr_low <= open_trade.tp:
                        hit_tp = True
                        exit_p = open_trade.tp

                if hit_sl or hit_tp:
                    pnl_per_oz = (exit_p - open_trade.entry_price) if open_trade.type == OrderType.BUY else (open_trade.entry_price - exit_p)
                    pnl = pnl_per_oz * open_trade.volume * self.contract_size

                    open_trade.exit_time = curr_time
                    open_trade.exit_price = exit_p
                    open_trade.pnl = pnl
                    open_trade.exit_reason = "TakeProfit" if hit_tp else "StopLoss"

                    closed_trades.append(open_trade)
                    balance += pnl
                    equity = balance
                    open_trade = None

                    if equity > peak_equity:
                        peak_equity = equity
                    dd = peak_equity - equity
                    dd_pct = dd / peak_equity if peak_equity > 0 else 0.0
                    if dd > max_drawdown:
                        max_drawdown = dd
                    if dd_pct > max_drawdown_pct:
                        max_drawdown_pct = dd_pct

            # 2. Check for new trade entry if no trade open
            if open_trade is None:
                # Price Action evaluation
                pa_output = self.pa_analyzer.evaluate(curr_slice)

                # Order Flow evaluation
                if ticks_df is not None and not ticks_df.empty:
                    slice_ticks = ticks_df[ticks_df['time'] <= curr_time].tail(200)
                    of_output = self.of_analyzer.evaluate(slice_ticks, rates_df=curr_slice)
                else:
                    # Synthetic ticks proxy from bar
                    of_output = self.of_analyzer.evaluate(pd.DataFrame(), rates_df=curr_slice)

                # News gate
                blackout_active, _ = self.news_filter.is_blackout_active(current_time=curr_time)

                # Confluence
                decision = self.confluence_engine.evaluate(pa_output, of_output, blackout_active)

                if decision.action in [TradeSignal.BUY, TradeSignal.SELL]:
                    order_type = OrderType.BUY if decision.action == TradeSignal.BUY else OrderType.SELL
                    acct_info = {"balance": balance, "equity": equity}

                    risk_res = self.risk_manager.check_trade_allowed(
                        order_type=order_type,
                        current_price=curr_close,
                        account_info=acct_info,
                        rates_df=curr_slice,
                        open_positions=[],
                        current_time=curr_time
                    )

                    if risk_res.allowed:
                        open_trade = BacktestTrade(
                            entry_time=curr_time,
                            exit_time=None,
                            type=order_type,
                            entry_price=curr_close,
                            exit_price=None,
                            volume=risk_res.volume,
                            sl=risk_res.sl,
                            tp=risk_res.tp
                        )

        # Calculate statistics
        tot_trades = len(closed_trades)
        wins = [t for t in closed_trades if t.pnl > 0]
        losses = [t for t in closed_trades if t.pnl <= 0]

        win_count = len(wins)
        loss_count = len(losses)
        win_rate = float(win_count / tot_trades) if tot_trades > 0 else 0.0

        tot_win_pnl = sum(t.pnl for t in wins)
        tot_loss_pnl = abs(sum(t.pnl for t in losses))
        profit_factor = float(tot_win_pnl / tot_loss_pnl) if tot_loss_pnl > 0 else (float('inf') if tot_win_pnl > 0 else 0.0)

        tot_pnl = sum(t.pnl for t in closed_trades)

        return BacktestResult(
            total_trades=tot_trades,
            winning_trades=win_count,
            losing_trades=loss_count,
            win_rate=win_rate,
            total_pnl=tot_pnl,
            profit_factor=profit_factor,
            max_drawdown=max_drawdown,
            max_drawdown_pct=max_drawdown_pct,
            trades=closed_trades
        )
