from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any

class OrderType(Enum):
    BUY = "BUY"
    SELL = "SELL"

class TradeSignal(Enum):
    BUY = "BUY"
    SELL = "SELL"
    NEUTRAL = "NEUTRAL"

@dataclass
class BarData:
    time: datetime
    open: float
    high: float
    low: float
    close: float
    tick_volume: int
    spread: int
    real_volume: int

@dataclass
class TickData:
    time: datetime
    bid: float
    ask: float
    last: float
    volume: int
    flags: int

@dataclass
class SignalOutput:
    module_name: str
    signal: TradeSignal
    confidence: float  # 0.0 to 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class Position:
    ticket: int
    symbol: str
    type: OrderType
    volume: float
    price_open: float
    sl: float
    tp: float
    price_current: float
    profit: float
    time: datetime

@dataclass
class TradeOrder:
    symbol: str
    order_type: OrderType
    volume: float
    price: Optional[float] = None
    sl: Optional[float] = None
    tp: Optional[float] = None
    comment: str = ""
