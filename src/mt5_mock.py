import logging
from datetime import datetime, timezone
import pandas as pd
from typing import List, Optional, Dict, Any
from src.mt5_base import MT5BaseConnector
from src.models import TickData, Position, TradeOrder, OrderType

logger = logging.getLogger(__name__)

class MT5MockConnector(MT5BaseConnector):
    def __init__(self, account_balance: float = 10000.0, account_equity: float = 10000.0):
        self._connected = False
        self.account_balance = account_balance
        self.account_equity = account_equity
        self.positions: Dict[int, Position] = {}
        self.next_ticket = 10001
        self.mock_rates: Dict[str, pd.DataFrame] = {}
        self.mock_ticks: Dict[str, pd.DataFrame] = {}
        self.current_tick: Optional[TickData] = TickData(
            time=datetime.now(timezone.utc),
            bid=2000.0,
            ask=2000.5,
            last=2000.25,
            volume=1,
            flags=0
        )

    def connect(self) -> bool:
        self._connected = True
        logger.info("MT5 Mock Connector connected successfully.")
        return True

    def disconnect(self) -> None:
        self._connected = False
        logger.info("MT5 Mock Connector disconnected.")

    def is_connected(self) -> bool:
        return self._connected

    def fetch_rates(self, symbol: str, timeframe: str, count: int) -> pd.DataFrame:
        if symbol in self.mock_rates:
            return self.mock_rates[symbol].tail(count)

        # Generate dummy rates DataFrame
        times = pd.date_range(end=datetime.now(timezone.utc), periods=count, freq="5min")
        df = pd.DataFrame({
            'time': times,
            'open': [2000.0 + i * 0.1 for i in range(count)],
            'high': [2001.0 + i * 0.1 for i in range(count)],
            'low': [1999.0 + i * 0.1 for i in range(count)],
            'close': [2000.5 + i * 0.1 for i in range(count)],
            'tick_volume': [100] * count,
            'spread': [50] * count,
            'real_volume': [10] * count
        })
        return df

    def fetch_ticks(self, symbol: str, date_from: datetime, date_to: datetime) -> pd.DataFrame:
        if symbol in self.mock_ticks:
            return self.mock_ticks[symbol]

        times = pd.date_range(start=date_from, end=date_to, freq="1s")
        if len(times) == 0:
            times = pd.date_range(end=datetime.now(timezone.utc), periods=10, freq="1s")

        df = pd.DataFrame({
            'time': times,
            'bid': [2000.0] * len(times),
            'ask': [2000.5] * len(times),
            'last': [2000.25] * len(times),
            'volume': [1] * len(times),
            'flags': [0] * len(times)
        })
        return df

    def get_symbol_info_tick(self, symbol: str) -> Optional[TickData]:
        return self.current_tick

    def get_positions(self, symbol: Optional[str] = None) -> List[Position]:
        pos_list = list(self.positions.values())
        if symbol:
            pos_list = [p for p in pos_list if p.symbol == symbol]
        return pos_list

    def get_account_info(self) -> Dict[str, Any]:
        return {
            "balance": self.account_balance,
            "equity": self.account_equity,
            "margin": 0.0,
            "free_margin": self.account_equity,
            "leverage": 100,
            "currency": "USD"
        }

    def send_order(self, order: TradeOrder) -> Dict[str, Any]:
        if not self._connected:
            return {"retcode": -1, "comment": "Not connected"}

        ticket = self.next_ticket
        self.next_ticket += 1

        price = order.price if order.price else (self.current_tick.ask if order.order_type == OrderType.BUY else self.current_tick.bid)

        pos = Position(
            ticket=ticket,
            symbol=order.symbol,
            type=order.order_type,
            volume=order.volume,
            price_open=price,
            sl=order.sl if order.sl else 0.0,
            tp=order.tp if order.tp else 0.0,
            price_current=price,
            profit=0.0,
            time=datetime.now(timezone.utc)
        )
        self.positions[ticket] = pos
        logger.info(f"Mock Order executed: {order.order_type.value} {order.volume} {order.symbol} @ {price}, ticket={ticket}")
        return {
            "retcode": 10009, # TRADE_RETCODE_DONE in MT5
            "order": ticket,
            "price": price,
            "volume": order.volume,
            "comment": "Request executed in mock mode"
        }

    def close_position(self, ticket: int) -> Dict[str, Any]:
        if ticket in self.positions:
            pos = self.positions.pop(ticket)
            logger.info(f"Mock Position closed: ticket={ticket}, symbol={pos.symbol}")
            return {"retcode": 10009, "comment": "Closed in mock mode"}
        return {"retcode": -1, "comment": "Position not found"}
