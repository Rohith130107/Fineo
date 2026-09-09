from datetime import datetime, timezone
import pytest
from src.config import load_config
from src.models import TradeOrder, OrderType
from src.mt5_mock import MT5MockConnector

def test_load_config():
    config = load_config("config.yaml")
    assert config["symbol"] == "XAUUSD"
    assert config["price_action"]["timeframes"]["primary"] == "M5"

def test_mock_connector_connection():
    connector = MT5MockConnector()
    assert not connector.is_connected()
    assert connector.connect() is True
    assert connector.is_connected() is True

def test_mock_connector_fetch_rates_and_ticks():
    connector = MT5MockConnector()
    connector.connect()
    rates = connector.fetch_rates("XAUUSD", "M5", 50)
    assert len(rates) == 50
    assert "close" in rates.columns

    ticks = connector.fetch_ticks("XAUUSD", datetime.now(timezone.utc), datetime.now(timezone.utc))
    assert len(ticks) > 0
    assert "bid" in ticks.columns

def test_mock_connector_order_execution():
    connector = MT5MockConnector()
    connector.connect()

    order = TradeOrder(
        symbol="XAUUSD",
        order_type=OrderType.BUY,
        volume=0.1,
        sl=1990.0,
        tp=2020.0,
        comment="Test buy order"
    )

    res = connector.send_order(order)
    assert res["retcode"] == 10009
    positions = connector.get_positions("XAUUSD")
    assert len(positions) == 1
    assert positions[0].volume == 0.1
    assert positions[0].type == OrderType.BUY

    ticket = positions[0].ticket
    close_res = connector.close_position(ticket)
    assert close_res["retcode"] == 10009
    assert len(connector.get_positions("XAUUSD")) == 0
