import logging
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from datetime import datetime
import pandas as pd
from src.models import BarData, TickData, Position, TradeOrder, OrderType

logger = logging.getLogger(__name__)

class MT5BaseConnector(ABC):
    @abstractmethod
    def connect(self) -> bool:
        pass

    @abstractmethod
    def disconnect(self) -> None:
        pass

    @abstractmethod
    def is_connected(self) -> bool:
        pass

    @abstractmethod
    def fetch_rates(self, symbol: str, timeframe: str, count: int) -> pd.DataFrame:
        pass

    @abstractmethod
    def fetch_ticks(self, symbol: str, date_from: datetime, date_to: datetime) -> pd.DataFrame:
        pass

    @abstractmethod
    def get_symbol_info_tick(self, symbol: str) -> Optional[TickData]:
        pass

    @abstractmethod
    def get_positions(self, symbol: Optional[str] = None) -> List[Position]:
        pass

    @abstractmethod
    def get_account_info(self) -> Dict[str, Any]:
        pass

    @abstractmethod
    def send_order(self, order: TradeOrder) -> Dict[str, Any]:
        pass

    @abstractmethod
    def close_position(self, ticket: int) -> Dict[str, Any]:
        pass
