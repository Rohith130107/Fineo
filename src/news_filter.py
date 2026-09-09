import logging
import requests
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any, Tuple

logger = logging.getLogger(__name__)

# Key high-impact macroeconomic event keywords for XAUUSD / USD
HIGH_IMPACT_KEYWORDS = [
    "NFP", "NON-FARM", "CPI", "INFLATION", "FOMC", "FED", "INTEREST RATE",
    "UNEMPLOYMENT", "GDP", "RETAIL SALES", "POWELL"
]

@dataclass
class NewsEvent:
    title: str
    country: str
    impact: str # "high", "medium", "low"
    event_time: datetime

class NewsFilterModule:
    """
    Economic Calendar News Filter.
    Supports Finnhub / TradingEconomics integration with fallback/mock capability.
    Operates in Defensive mode by default (blackout window ±15 min around high-impact events).
    """
    def __init__(self, provider: str = "finnhub", api_key: Optional[str] = None,
                 blackout_before_min: int = 15, blackout_after_min: int = 15,
                 mode: str = "defensive"):
        self.provider = provider.lower() if provider else "finnhub"
        self.api_key = api_key
        self.blackout_before = timedelta(minutes=blackout_before_min)
        self.blackout_after = timedelta(minutes=blackout_after_min)
        self.mode = mode.lower()
        self.cached_events: List[NewsEvent] = []
        self.last_fetch_time: Optional[datetime] = None

    def fetch_events(self, date_from: Optional[datetime] = None, date_to: Optional[datetime] = None) -> List[NewsEvent]:
        if not self.api_key:
            logger.info("No News API key provided. Returning empty event list.")
            return []

        now = datetime.now(timezone.utc)
        if date_from is None:
            date_from = now - timedelta(days=1)
        if date_to is None:
            date_to = now + timedelta(days=2)

        if self.provider == "finnhub":
            events = self._fetch_finnhub(date_from, date_to)
        elif self.provider in ["tradingeconomics", "te"]:
            events = self._fetch_tradingeconomics(date_from, date_to)
        else:
            logger.warning(f"Unknown news provider '{self.provider}'. Defaulting to empty events.")
            events = []

        self.cached_events = events
        self.last_fetch_time = now
        return events

    def _fetch_finnhub(self, date_from: datetime, date_to: datetime) -> List[NewsEvent]:
        url = "https://finnhub.io/api/v1/economic-calendar"
        params = {
            "from": date_from.strftime("%Y-%m-%d"),
            "to": date_to.strftime("%Y-%m-%d"),
            "token": self.api_key
        }
        try:
            resp = requests.get(url, params=params, timeout=10)
            if resp.status_code != 200:
                logger.error(f"Finnhub API returned status {resp.status_code}")
                return []
            data = resp.json().get("economicCalendar", [])
            events = []
            for item in data:
                country = item.get("country", "")
                if country not in ["US", "USD"]:
                    continue

                event_name = item.get("event", "")
                event_str = item.get("time", "") # format "YYYY-MM-DD HH:MM:SS"
                try:
                    event_time = datetime.strptime(event_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                except Exception:
                    continue

                impact = item.get("impact", "low").lower()

                # Boost impact if title matches high impact keyword
                if any(kw in event_name.upper() for kw in HIGH_IMPACT_KEYWORDS):
                    impact = "high"

                events.append(NewsEvent(
                    title=event_name,
                    country=country,
                    impact=impact,
                    event_time=event_time
                ))
            return events
        except Exception as e:
            logger.error(f"Error fetching Finnhub news: {e}")
            return []

    def _fetch_tradingeconomics(self, date_from: datetime, date_to: datetime) -> List[NewsEvent]:
        # TradingEconomics REST endpoint stub
        return []

    def is_blackout_active(self, current_time: Optional[datetime] = None, events: Optional[List[NewsEvent]] = None) -> Tuple[bool, List[NewsEvent]]:
        """
        Evaluates if the current_time falls into the blackout window of any high-impact news event.
        Returns (blackout_active: bool, impacting_events: List[NewsEvent])
        """
        if current_time is None:
            current_time = datetime.now(timezone.utc)
        elif current_time.tzinfo is None:
            current_time = current_time.replace(tzinfo=timezone.utc)

        events_to_check = events if events is not None else self.cached_events

        active_blackout = False
        impacting_events = []

        for ev in events_to_check:
            if ev.impact != "high":
                continue

            window_start = ev.event_time - self.blackout_before
            window_end = ev.event_time + self.blackout_after

            if window_start <= current_time <= window_end:
                active_blackout = True
                impacting_events.append(ev)

        return active_blackout, impacting_events
