import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any

from src.config import load_config
from src.mt5_factory import get_mt5_connector
from src.mt5_base import MT5BaseConnector
from src.price_action import PriceActionAnalyzer
from src.order_flow import OrderFlowAnalyzer
from src.news_filter import NewsFilterModule
from src.confluence_engine import ConfluenceEngine
from src.risk_manager import RiskManager
from src.models import TradeSignal, OrderType, TradeOrder

logger = logging.getLogger(__name__)

class PaperTradingRunner:
    """
    Live / Paper Trading Runner for XAUUSD Confluence Trading Bot.
    Runs tick/bar iteration against MT5 demo account with structured logging.
    """
    def __init__(self, config_path: str = "config.yaml", connector: Optional[MT5BaseConnector] = None):
        self.config = load_config(config_path)
        self.symbol = self.config.get("symbol", "XAUUSD")

        self.connector = connector or get_mt5_connector(self.config)

        pa_cfg = self.config.get("price_action", {})
        self.primary_tf = pa_cfg.get("timeframes", {}).get("primary", "M5")
        self.higher_tf = pa_cfg.get("timeframes", {}).get("higher", "H1")
        self.pa_analyzer = PriceActionAnalyzer(
            pivot_left_bars=pa_cfg.get("pivot_left_bars", 2),
            pivot_right_bars=pa_cfg.get("pivot_right_bars", 2)
        )

        of_cfg = self.config.get("order_flow", {})
        self.of_analyzer = OrderFlowAnalyzer(
            lookback_minutes=of_cfg.get("lookback_minutes", 15)
        )

        news_cfg = self.config.get("news", {})
        self.news_filter = NewsFilterModule(
            provider=news_cfg.get("provider", "finnhub"),
            api_key=news_cfg.get("api_key", ""),
            blackout_before_min=news_cfg.get("blackout_before_min", 15),
            blackout_after_min=news_cfg.get("blackout_after_min", 15)
        )

        conf_cfg = self.config.get("confluence", {})
        self.confluence_engine = ConfluenceEngine(
            min_signals_required=conf_cfg.get("min_signals_required", 2)
        )

        risk_cfg = self.config.get("risk", {})
        self.risk_manager = RiskManager(
            risk_per_trade_pct=risk_cfg.get("risk_per_trade_pct", 0.01),
            max_daily_loss_pct=risk_cfg.get("max_daily_loss_pct", 0.03),
            max_concurrent_positions=risk_cfg.get("max_concurrent_positions", 1),
            atr_period=risk_cfg.get("atr_period", 14),
            atr_sl_multiplier=risk_cfg.get("atr_sl_multiplier", 1.5),
            atr_tp_multiplier=risk_cfg.get("atr_tp_multiplier", 3.0)
        )

        self._running = False

    def initialize(self) -> bool:
        logger.info("Initializing MT5 Connection...")
        if not self.connector.connect():
            logger.error("Failed to connect to MT5 terminal.")
            return False

        logger.info("Fetching initial news calendar events...")
        self.news_filter.fetch_events()
        return True

    def run_cycle(self) -> Dict[str, Any]:
        """
        Executes a single signal pipeline cycle:
        1. Query open positions and account status
        2. Fetch market rates (M5 & H1) and ticks
        3. Evaluate Price Action, Order Flow, and News blackout
        4. Confluence evaluation
        5. Risk management check & Order execution
        """
        now = datetime.now(timezone.utc)
        acct_info = self.connector.get_account_info()
        open_positions = self.connector.get_positions(self.symbol)

        # Fetch rates
        primary_rates = self.connector.fetch_rates(self.symbol, self.primary_tf, 100)
        higher_rates = self.connector.fetch_rates(self.symbol, self.higher_tf, 100)

        # Fetch ticks for order flow
        date_from = now - timedelta(minutes=15)
        ticks = self.connector.fetch_ticks(self.symbol, date_from, now)

        # Get latest tick
        latest_tick = self.connector.get_symbol_info_tick(self.symbol)
        current_price = latest_tick.ask if latest_tick else (primary_rates['close'].iloc[-1] if not primary_rates.empty else 2000.0)

        # Module evaluation
        pa_output = self.pa_analyzer.evaluate(primary_rates, higher_df=higher_rates)
        of_output = self.of_analyzer.evaluate(ticks, rates_df=primary_rates)
        blackout_active, active_events = self.news_filter.is_blackout_active(current_time=now)

        decision = self.confluence_engine.evaluate(pa_output, of_output, blackout_active)

        execution_result = None
        if decision.action in [TradeSignal.BUY, TradeSignal.SELL]:
            order_type = OrderType.BUY if decision.action == TradeSignal.BUY else OrderType.SELL
            risk_res = self.risk_manager.check_trade_allowed(
                order_type=order_type,
                current_price=current_price,
                account_info=acct_info,
                rates_df=primary_rates,
                open_positions=open_positions,
                current_time=now
            )

            if risk_res.allowed:
                order = TradeOrder(
                    symbol=self.symbol,
                    order_type=order_type,
                    volume=risk_res.volume,
                    price=current_price,
                    sl=risk_res.sl,
                    tp=risk_res.tp,
                    comment=f"Confluence trade (conf={decision.confidence:.2f})"
                )
                execution_result = self.connector.send_order(order)
                logger.info(f"ORDER SENT: {execution_result}")
            else:
                logger.info(f"Trade blocked by risk manager: {risk_res.reason}")

        return {
            "timestamp": now.isoformat(),
            "decision": decision.action.value,
            "confidence": decision.confidence,
            "reasons": decision.reasons,
            "blackout_active": blackout_active,
            "execution": execution_result
        }

    def start_loop(self, poll_interval_sec: float = 5.0, max_cycles: Optional[int] = None) -> None:
        if not self.initialize():
            return

        self._running = True
        cycle_count = 0

        logger.info(f"Starting paper trading loop for {self.symbol}...")
        try:
            while self._running:
                cycle_count += 1
                res = self.run_cycle()
                logger.info(f"Cycle {cycle_count}: Decision={res['decision']} Conf={res['confidence']:.2f}")

                if max_cycles and cycle_count >= max_cycles:
                    break

                time.sleep(poll_interval_sec)
        except KeyboardInterrupt:
            logger.info("Paper trading loop stopped by user.")
        finally:
            self.connector.disconnect()
            self._running = False

    def stop(self) -> None:
        self._running = False
