import pytest
from src.confluence_engine import ConfluenceEngine
from src.models import SignalOutput, TradeSignal

def test_confluence_news_blackout_blocks():
    engine = ConfluenceEngine(min_signals_required=2)
    pa = SignalOutput("price_action", TradeSignal.BUY, 0.8)
    of = SignalOutput("order_flow", TradeSignal.BUY, 0.7)

    result = engine.evaluate(pa, of, blackout_active=True)
    assert result.action == TradeSignal.NEUTRAL
    assert result.blackout_active is True
    assert "BLOCKED" in result.reasons[0]

def test_confluence_pa_and_of_agreement():
    engine = ConfluenceEngine(min_signals_required=2, min_confidence=0.5)
    pa = SignalOutput("price_action", TradeSignal.BUY, 0.8)
    of = SignalOutput("order_flow", TradeSignal.BUY, 0.7)

    result = engine.evaluate(pa, of, blackout_active=False)
    assert result.action == TradeSignal.BUY
    assert result.confidence == 0.75
    assert result.blackout_active is False

def test_confluence_conflict():
    engine = ConfluenceEngine(min_signals_required=2)
    pa = SignalOutput("price_action", TradeSignal.BUY, 0.8)
    of = SignalOutput("order_flow", TradeSignal.SELL, 0.7)

    result = engine.evaluate(pa, of, blackout_active=False)
    assert result.action == TradeSignal.NEUTRAL
    assert any("CONFLICT" in r for r in result.reasons)

def test_confluence_single_signal_pass():
    engine = ConfluenceEngine(min_signals_required=2, min_confidence=0.5)
    pa = SignalOutput("price_action", TradeSignal.BUY, 0.8)
    of = SignalOutput("order_flow", TradeSignal.NEUTRAL, 0.0)

    result = engine.evaluate(pa, of, blackout_active=False)
    assert result.action == TradeSignal.BUY
    assert result.confidence == 0.8
