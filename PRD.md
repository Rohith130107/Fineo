# PRD — XAUUSD MT5 Confluence Trading Bot

## 1. Overview
A Python-based automated trading system that connects to a MetaTrader 5 (MT5) terminal
and trades a single instrument — **XAUUSD (Gold/USD)** — using a confluence of three
independent signal sources: price action structure, order flow (tick-derived), and
macroeconomic news filtering. The bot places and manages trades directly via MT5's
`order_send` API on a demo account first, then live with small capital.

## 2. Goals
- Automate entries/exits on XAUUSD only, no other instruments.
- Combine price action + order flow as directional signals, with news acting as a
  gate/filter rather than a signal source.
- Enforce strict, non-negotiable risk management (position sizing, SL/TP, daily loss cap).
- Be backtestable on historical tick data before any live execution.
- Run unattended for extended periods (session-aware, news-aware).

## 3. Non-Goals
- No multi-pair support (single-instrument only, hardcode to XAUUSD).
- No web dashboard/UI in v1 — CLI/logs only.
- No genuine Level 2 order book unless the connected broker exposes `market_book_get`;
  otherwise use the tick-derived proxy defined in section 5.2.
- No portfolio/multi-strategy management.
- No fully autonomous news-trading of the release itself in v1 (see 5.3 — defensive mode
  is the default).

## 4. System Architecture

```
                     ┌─────────────────────┐
                     │   MT5 Connection      │
                     │   Layer                │
                     └──────────┬───────────┘
                                │
        ┌───────────────────────┼───────────────────────┐
        │                       │                       │
┌───────▼────────┐   ┌──────────▼─────────┐   ┌─────────▼─────────┐
│ Price Action     │   │ Order Flow          │   │ News Filter        │
│ Module           │   │ Module              │   │ Module             │
└───────┬────────┘   └──────────┬─────────┘   └─────────┬─────────┘
        │                       │                       │
        └───────────────────────┼───────────────────────┘
                                │
                     ┌──────────▼───────────┐
                     │  Confluence Decision   │
                     │  Engine                │
                     └──────────┬───────────┘
                                │
                     ┌──────────▼───────────┐
                     │  Risk Management       │
                     │  Layer                 │
                     └──────────┬───────────┘
                                │
                     ┌──────────▼───────────┐
                     │  Order Execution       │
                     │  (order_send)          │
                     └───────────────────────┘
```

## 5. Functional Requirements

### 5.1 Price Action Module
- **Timeframes:** primary M5/M15, with H1 for higher-timeframe bias.
- **Swing detection:** identify swing highs/lows using a fractal or N-bar pivot method.
- **Structure:** detect Break of Structure (BOS) and Change of Character (CHoCH) off
  the swing points to determine trend direction/bias.
- **S/R levels:** build a dynamic support/resistance map from:
  - prior swing highs/lows
  - London session open/high/low
  - NY session open/high/low
  - prior day high/low
- **Output:** a directional bias (long / short / neutral) + confidence score (0–1) +
  nearest key level distance.

### 5.2 Order Flow Module (tick-derived proxy)
- **Data source:** `copy_ticks_range` (bid/ask/last/volume).
- **Method:** classify each tick as buy-side or sell-side pressure (uptick/downtick vs.
  prior tick, or bid/ask crossing heuristic), aggregate into a rolling delta over a
  configurable window (e.g., last N minutes).
- **Fallback preference:** if the connected broker exposes `market_book_get` (real DOM),
  prefer that over the tick-derived proxy.
- **Output:** directional pressure score (-1 to +1) and a flag for absorption/exhaustion
  (delta diverging from price).

### 5.3 News Filter Module
- **Data source:** economic calendar API (Finnhub or TradingEconomics free tier).
- **Relevant events for XAUUSD:** NFP, CPI, FOMC rate decisions/statements, Fed
  chair speeches, DXY-moving macro releases.
- **Modes (configurable, default = Defensive):**
  - **Defensive:** block new entries and optionally flatten open positions in a
    ±15-minute window around high-impact releases.
  - **Aggressive (v2/optional):** allow entries after the release using the post-news
    impulse candle, with widened SL.
- **Output:** boolean `blackout_active` flag + upcoming event list with impact level.

### 5.4 Confluence Decision Engine
- Combines the three module outputs into a single trade decision.
- **Default rule:** require at least 2 of 3 signals in agreement (price action direction
  + order flow direction, or price action + no news blackout) before firing an order.
- News module acts purely as a **gate** — it can block a trade but does not generate
  directional signals on its own (in Defensive mode).
- All weights/thresholds must be configurable via a config file, not hardcoded.

### 5.5 Risk Management Layer (non-negotiable)
- **Position sizing:** fixed % risk per trade (default 0.5–1% of account equity).
- **Stop loss / take profit:** ATR-based, recalculated per trade given XAUUSD's variable
  volatility.
- **Daily loss circuit breaker:** disable new entries once daily loss threshold
  (configurable, e.g. 3%) is hit; existing positions may still be managed/closed.
- **Max concurrent positions:** configurable, default = 1 (single position at a time
  given single-pair scope).

### 5.6 Execution Layer
- Uses `MetaTrader5` Python package: `initialize()`, `symbol_info_tick()`,
  `order_send()`, `positions_get()`.
- Must handle and log: connection drops, requote/slippage rejection, partial fills.
- All trades logged with entry reason (which modules agreed), timestamp, size, SL/TP.

### 5.7 Backtesting
- Vectorized backtester (not MT5's built-in Strategy Tester) using historical tick/bar
  data pulled via `copy_rates_from` / `copy_ticks_range`.
- Must reproduce the exact confluence logic used live (shared codebase, not a
  reimplementation).
- Output: win rate, profit factor, max drawdown, average R multiple, trade log.

### 5.8 Paper Trading
- Runs full live logic against a demo MT5 account for a minimum 2–4 week validation
  period before real capital is used.

## 6. Tech Stack
- **Language:** Python 3.11+
- **MT5 connection:** `MetaTrader5` official package
- **Data/backtest:** `pandas`, `numpy`, optionally `vectorbt` or `backtrader` for
  backtest harness
- **News API:** Finnhub or TradingEconomics (config-swappable)
- **Config:** `.env` / YAML config file (never hardcoded secrets; add to `.gitignore`)
- **Logging:** structured logs (JSON or CSV) per trade + module decision trail

## 7. Configuration Parameters (all must be externally configurable)
| Parameter | Default |
|---|---|
| Risk per trade | 0.5–1% |
| Max daily loss | 3% |
| Confluence threshold | 2 of 3 signals |
| News blackout window | ±15 min |
| Order flow lookback window | configurable (e.g. 15 min) |
| Timeframes used | M5, M15, H1 |
| Max concurrent positions | 1 |

## 8. Milestones
1. MT5 connection layer verified on demo account (tick/rate fetch + order_send round trip)
2. Price action module built + unit tested
3. Order flow module built + unit tested
4. News filter module built + integrated
5. Confluence engine + risk layer integrated
6. Backtest harness validated against historical XAUUSD data
7. Paper trading run (2–4 weeks minimum)
8. Go-live decision gate (based on paper trading results)

## 9. Success Metrics
- Backtest profit factor > 1.3 with max drawdown under a defined threshold (e.g. 15%)
- Paper trading results directionally consistent with backtest (no major logic drift)
- Zero unhandled crashes / connection-drop failures over a 2-week unattended run
- All trades traceable to the exact module signals that triggered them

## 10. Open Questions / Decisions Needed
- Which broker/account will be used, and does it expose real DOM via `market_book_get`?
- Finnhub vs TradingEconomics for the news feed — pricing/rate limits to confirm.
- Defensive vs Aggressive news mode as the eventual default for live trading.
- VPS/always-on hosting plan for 24/7 XAUUSD market coverage.
