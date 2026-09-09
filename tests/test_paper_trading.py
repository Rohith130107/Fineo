from datetime import datetime, timezone
import pytest
from src.mt5_mock import MT5MockConnector
from src.paper_trading import PaperTradingRunner

def test_paper_trading_runner_cycle():
    mock_connector = MT5MockConnector()
    runner = PaperTradingRunner(config_path="config.yaml", connector=mock_connector)

    assert runner.initialize() is True

    cycle_res = runner.run_cycle()
    assert "timestamp" in cycle_res
    assert "decision" in cycle_res
    assert "confidence" in cycle_res
    assert isinstance(cycle_res["blackout_active"], bool)

    runner.start_loop(poll_interval_sec=0.1, max_cycles=2)
    assert runner.connector.is_connected() is False
