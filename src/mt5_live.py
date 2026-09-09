import logging
from typing import List, Optional, Dict, Any
from datetime import datetime
import pandas as pd
from src.mt5_base import MT5BaseConnector
from src.models import TickData, Position, TradeOrder, OrderType

logger = logging.getLogger(__name__)

try:
    import MetaTrader5 as mt5
    HAS_MT5 = True
except ImportError:
    mt5 = None
    HAS_MT5 = False

TIMEFRAME_MAP = {}
if HAS_MT5:
    TIMEFRAME_MAP = {
        "M1": mt5.TIMEFRAME_M1,
        "M5": mt5.TIMEFRAME_M5,
        "M15": mt5.TIMEFRAME_M15,
        "M30": mt5.TIMEFRAME_M30,
        "H1": mt5.TIMEFRAME_H1,
        "H4": mt5.TIMEFRAME_H4,
        "D1": mt5.TIMEFRAME_D1,
    }

class MT5LiveConnector(MT5BaseConnector):
    def __init__(self, login: Optional[int] = None, password: Optional[str] = None, server: Optional[str] = None, path: Optional[str] = None):
        if not HAS_MT5:
            raise ImportError("MetaTrader5 package is not available on this system.")
        self.login = int(login) if login else None
        self.password = password
        self.server = server
        self.path = path
        self._connected = False

    def connect(self) -> bool:
        kwargs = {}
        if self.path:
            kwargs['path'] = self.path
        if self.login:
            kwargs['login'] = self.login
        if self.password:
            kwargs['password'] = self.password
        if self.server:
            kwargs['server'] = self.server

        if not mt5.initialize(**kwargs):
            logger.error(f"MT5 initialize failed, error code: {mt5.last_error()}")
            self._connected = False
            return False

        self._connected = True
        logger.info(f"Connected to MT5 terminal successfully. Account: {self.login}")
        return True

    def disconnect(self) -> None:
        if HAS_MT5:
            mt5.shutdown()
        self._connected = False
        logger.info("Disconnected from MT5.")

    def is_connected(self) -> bool:
        return self._connected

    def fetch_rates(self, symbol: str, timeframe: str, count: int) -> pd.DataFrame:
        tf = TIMEFRAME_MAP.get(timeframe, mt5.TIMEFRAME_M5)
        rates = mt5.copy_rates_from_pos(symbol, tf, 0, count)
        if rates is None or len(rates) == 0:
            logger.warning(f"Failed to fetch rates for {symbol} ({timeframe}): {mt5.last_error()}")
            return pd.DataFrame()

        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        return df

    def fetch_ticks(self, symbol: str, date_from: datetime, date_to: datetime) -> pd.DataFrame:
        ticks = mt5.copy_ticks_range(symbol, date_from, date_to, mt5.COPY_TICKS_ALL)
        if ticks is None or len(ticks) == 0:
            logger.warning(f"Failed to fetch ticks for {symbol}: {mt5.last_error()}")
            return pd.DataFrame()

        df = pd.DataFrame(ticks)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        return df

    def get_symbol_info_tick(self, symbol: str) -> Optional[TickData]:
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return None
        return TickData(
            time=datetime.fromtimestamp(tick.time),
            bid=tick.bid,
            ask=tick.ask,
            last=tick.last,
            volume=tick.volume,
            flags=tick.flags
        )

    def get_positions(self, symbol: Optional[str] = None) -> List[Position]:
        kwargs = {}
        if symbol:
            kwargs['symbol'] = symbol
        raw_positions = mt5.positions_get(**kwargs)
        if raw_positions is None:
            return []

        result = []
        for p in raw_positions:
            result.append(Position(
                ticket=p.ticket,
                symbol=p.symbol,
                type=OrderType.BUY if p.type == mt5.ORDER_TYPE_BUY else OrderType.SELL,
                volume=p.volume,
                price_open=p.price_open,
                sl=p.sl,
                tp=p.tp,
                price_current=p.price_current,
                profit=p.profit,
                time=datetime.fromtimestamp(p.time)
            ))
        return result

    def get_account_info(self) -> Dict[str, Any]:
        info = mt5.account_info()
        if info is None:
            return {}
        return info._asdict()

    def send_order(self, order: TradeOrder) -> Dict[str, Any]:
        tick = mt5.symbol_info_tick(order.symbol)
        if tick is None:
            return {"retcode": -1, "comment": "Failed to get symbol tick"}

        price = order.price
        if price is None:
            price = tick.ask if order.order_type == OrderType.BUY else tick.bid

        action_type = mt5.ORDER_TYPE_BUY if order.order_type == OrderType.BUY else mt5.ORDER_TYPE_SELL

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": order.symbol,
            "volume": order.volume,
            "type": action_type,
            "price": price,
            "sl": order.sl if order.sl else 0.0,
            "tp": order.tp if order.tp else 0.0,
            "deviation": 20,
            "magic": 123456,
            "comment": order.comment or "XAUUSD Bot Order",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request)
        if result is None:
            return {"retcode": -1, "comment": f"order_send returned None: {mt5.last_error()}"}
        return result._asdict()

    def close_position(self, ticket: int) -> Dict[str, Any]:
        positions = mt5.positions_get(ticket=ticket)
        if not positions:
            return {"retcode": -1, "comment": "Position not found"}

        pos = positions[0]
        tick = mt5.symbol_info_tick(pos.symbol)
        if tick is None:
            return {"retcode": -1, "comment": "Failed to get symbol tick for closing"}

        close_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
        price = tick.bid if pos.type == mt5.ORDER_TYPE_BUY else tick.ask

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": pos.symbol,
            "volume": pos.volume,
            "type": close_type,
            "position": ticket,
            "price": price,
            "deviation": 20,
            "magic": 123456,
            "comment": "Close Position",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request)
        if result is None:
            return {"retcode": -1, "comment": f"order_send failed: {mt5.last_error()}"}
        return result._asdict()
