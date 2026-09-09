from datetime import datetime, timedelta, timezone
import pytest
from src.news_filter import NewsFilterModule, NewsEvent

def test_blackout_window_detection():
    news_mod = NewsFilterModule(blackout_before_min=15, blackout_after_min=15)

    event_time = datetime(2025, 1, 10, 13, 30, tzinfo=timezone.utc)
    nfp_event = NewsEvent(
        title="US Non-Farm Payrolls",
        country="US",
        impact="high",
        event_time=event_time
    )

    # 10 minutes before event -> inside blackout
    t_before = datetime(2025, 1, 10, 13, 20, tzinfo=timezone.utc)
    is_active, events = news_mod.is_blackout_active(current_time=t_before, events=[nfp_event])
    assert is_active is True
    assert len(events) == 1

    # Exact event time -> inside blackout
    is_active, events = news_mod.is_blackout_active(current_time=event_time, events=[nfp_event])
    assert is_active is True

    # 10 minutes after event -> inside blackout
    t_after = datetime(2025, 1, 10, 13, 40, tzinfo=timezone.utc)
    is_active, events = news_mod.is_blackout_active(current_time=t_after, events=[nfp_event])
    assert is_active is True

    # 30 minutes before event -> outside blackout
    t_outside = datetime(2025, 1, 10, 13, 0, tzinfo=timezone.utc)
    is_active, events = news_mod.is_blackout_active(current_time=t_outside, events=[nfp_event])
    assert is_active is False
    assert len(events) == 0

def test_low_impact_event_no_blackout():
    news_mod = NewsFilterModule()
    event_time = datetime(2025, 1, 10, 13, 30, tzinfo=timezone.utc)
    low_event = NewsEvent(
        title="US Wholesale Inventories",
        country="US",
        impact="low",
        event_time=event_time
    )

    is_active, events = news_mod.is_blackout_active(current_time=event_time, events=[low_event])
    assert is_active is False
