import os
from src.mt5_base import MT5BaseConnector
from src.mt5_mock import MT5MockConnector

def get_mt5_connector(config: dict) -> MT5BaseConnector:
    # Always prefer MT5LiveConnector if MetaTrader5 is installed and running,
    # otherwise fallback to MT5MockConnector for testing / non-Windows environments.
    mt5_cfg = config.get("mt5", {})
    try:
        from src.mt5_live import MT5LiveConnector
        connector = MT5LiveConnector(
            login=mt5_cfg.get("login"),
            password=mt5_cfg.get("password"),
            server=mt5_cfg.get("server"),
            path=mt5_cfg.get("path")
        )
        return connector
    except ImportError:
        return MT5MockConnector()
