# MT5 Order Manager

A lightweight Windows desktop application for monitoring and managing open positions in MetaTrader 5 — with a built-in M1/M5 scalping auto-trader. Built with Python and PySide6.

![Python](https://img.shields.io/badge/Python-3.10+-blue) ![PySide6](https://img.shields.io/badge/PySide6-6.6+-green) ![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey)

---

## Features

- **One-click connect** to any already-running MT5 terminal — no login credentials required
- **Live order table** refreshed every 100 ms: symbol, type, volume, open price, current price, SL/TP, floating P&L, and open time
- **Symbol-aware prices** — 5-digit forex pairs and 2-digit metals each render with the correct precision
- **Live trend arrow** — each open order shows its symbol's current trend (▲ up / ▼ down / ~ choppy), ADX-based and refreshed in real time, in both normal and compact mode
- **Partial close** — close 50%, 80%, 90%, or 100% of any position from the action buttons
- **Close All** — close every open position in one click (with confirmation)
- **Trade history** — filter closed deals by date range, with net P&L (including commission and swap) and win rate
- **Performance dashboard** — full trade analytics (profit factor, expectancy, drawdown, equity curve, per-symbol/direction/source breakdowns) plus a rule-based "coach" that suggests improvements from your own history
- **Source tagging** — every order is marked 🤖 (auto-trader) or 👤 (manual) in all order views
- **Watchlist trend alerts** — monitor a list of symbols and get a sound alert when one enters a clear trend (ADX-based), so you can act when it's trending rather than choppy
- **Timezone selector** — convert all displayed broker times to a timezone of your choice
- **Auto Trade** — an H1 (1-hour) EMA + RSI pullback swing strategy with paper and live modes, risk-based position sizing, and safety guardrails
- **Compact mode** — a narrow always-on-top overlay that shows only the essentials so you can keep it beside any chart

---

## Requirements

- Windows 10 / 11
- MetaTrader 5 terminal **already running and logged in**
- Python 3.10+ (for running from source)

---

## Quick Start

### Option A — Run from source

```powershell
pip install -r requirements.txt
python main.py
```

### Option B — Run the pre-built executable

Download `MT5OrderManager.exe` from [Releases](../../releases), extract the folder, and run `MT5OrderManager.exe`. No Python installation needed. (Keep the `_internal` folder beside the executable.)

---

## Build Your Own Executable

```powershell
pip install pyinstaller
pyinstaller -y MT5OrderManager.spec
# Output: dist\MT5OrderManager\MT5OrderManager.exe
```

---

## How It Works

### Connection

The app scans running processes (`psutil`) for `terminal64.exe` / `terminal.exe`. When MT5 is detected, the **Connect** button becomes active. Clicking it calls `mt5.initialize()` with no credentials — it attaches to whichever MT5 terminal is already authenticated on your machine.

The status bar cycles through three states:

| State | Meaning |
|---|---|
| MT5 Not Found | No MT5 terminal process detected |
| MT5 Running | Terminal found, not yet connected |
| Connected — *Account Name* | Active connection, live data flowing |

### Order Refresh

Once connected, a 100 ms timer polls `mt5.positions_get()` and updates the table. Current price uses `tick.bid` for BUY positions and `tick.ask` for SELL positions (the actual close price), not the lagging `price_current` field from the position struct. Prices are formatted using each symbol's `digits`, so forex and metals both display correctly.

Each row also shows a **trend arrow** for its symbol — ▲ up, ▼ down, ~ choppy — using the same ADX classifier as the watchlist on M5 bars. It's computed per symbol and cached (recomputed at most every few seconds) so the fast refresh stays cheap, and it appears in both normal and compact mode.

### Server Time

MT5 reports all time fields in the **broker server's** timezone, not UTC. The app estimates the server→UTC offset from fresh tick times (`core/server_clock.py`), calibrated on connect and refined on every refresh. That offset is applied both when displaying times and when shifting history query ranges, and the timezone selector then converts to your chosen zone.

### Closing Positions

Partial-close volumes are snapped down to the symbol's `volume_step` and rejected below `volume_min`; a 100% close sends the exact position volume. Each close sends an `ORDER_TYPE_SELL` (for a BUY) or `ORDER_TYPE_BUY` (for a SELL) via `TRADE_ACTION_DEAL`, with the filling mode chosen from the symbol's allowed modes (IOC preferred, then FOK, else RETURN).

### Trade History

The History tab queries `mt5.history_deals_get(from, to)` and displays each closed deal with entry/exit prices, volume, and net profit. Profit and win/loss use the closing deal's net result (`profit + commission + swap + fee`); open time and price are resolved from the position's entry deal. The summary row shows total net P&L, winning trades, and win-rate percentage.

---

## Performance Dashboard

The **Dashboard** tab turns your closed-trade history into analytics over a selectable period (1W / 1M / 3M / YTD / All). Closing deals are first grouped into position-level trades (a position closed in several partials counts as one trade), then everything is derived from that:

- **Stat cards:** net P&L, profit factor, win rate, expectancy, average win/loss and payoff ratio, max drawdown, recovery factor, largest win/loss, longest losing streak, and average holding time.
- **Equity curve:** cumulative closed-trade P&L, drawn directly with `QPainter` (no charting dependency).
- **Breakdowns:** performance by symbol, by direction (BUY/SELL), and by source (🤖 auto vs 👤 manual).

### Insights — coaching from your own history

The dashboard also runs a **rule-based insights engine** that flags patterns and suggests behavioral fixes — e.g. "losers are bigger than winners," "EURUSD is dragging the account," "you hold losers longer than winners," or "auto is outperforming manual." Each insight is colored by severity and pairs a data finding with a concrete suggestion.

These are **descriptive, not predictive** — they summarize what already happened in your data, not what the market will do. Every rule is gated on sample size (nothing fires below 10 trades), and time-of-day/weekday patterns are presented as hypotheses to investigate, not rules to follow blindly.

---

## Auto Trade

The **Auto Trade** tab runs an automated trend-pullback strategy on the H1 (1-hour) timeframe (H4 is also selectable).

### Strategy — EMA + RSI pullback

- **Trend filter:** only go long when price is above EMA(50); only go short when below.
- **Trigger:** RSI(14) crossing back up through 40 (long) or down through 60 (short) — a shallow pullback resuming in the trend direction.
- **Stop loss:** `2.0 × ATR(14)`. **Take profit:** `2.0 × stop` (2:1 reward). A **time stop** closes the position after a configurable number of bars (default 24 = one day on H1).

Signals are evaluated only on **closed** bars (never the forming bar). The trigger requires a pullback that resumes in the trend direction while price holds the EMA, so entries are selective — a quiet log is normal, not a fault.

### Modes

| Mode | Behavior |
|---|---|
| **PAPER** (default) | Trades are simulated against live bid/ask (so spread cost is real). Nothing is sent to the broker. Use this to evaluate the strategy. |
| **LIVE** | Real market orders are sent via the order manager, tagged with a dedicated magic number so the bot only ever manages its own positions. Gated behind a confirmation dialog. |

> **Test in PAPER on a demo account first.** No strategy here is guaranteed profitable; validate it on your broker's data and spreads before going live.

### Guardrails

Position size is computed from a risk-per-trade percentage so a stop-out loses a fixed fraction of balance, snapped to the symbol's lot step. Before any entry the bot also enforces: a daily loss limit and profit target, a maximum number of concurrent positions, a spread gate (skip if spread is too wide relative to the stop), an optional trading-session window, and a hard **KILL** switch.

---

## Watchlist — Trend Alerts

The **Watchlist** tab monitors a list of symbols on a chosen timeframe and alerts you when one enters a **clear trend** — a better moment to open a trade than a choppy, range-bound market.

Symbols are chosen from a dropdown populated with your **MT5 Market Watch** symbols (loaded on connect). The timeframe selector offers **M1 / M5 / M30 / H1 / H4** (default H1).

### How a "clear trend" is decided

- **ADX** (Average Directional Index) measures trend *strength*. ADX ≥ 25 means a real trend; below that the market is treated as choppy and **no alert** fires.
- Direction must agree: **+DI > −DI and price above EMA(50)** → UP; the mirror → DOWN. If ADX is strong but the direction signals disagree, it stays choppy. This keeps alerts to genuinely clean setups.

### Alerts

When a symbol *transitions* into a clear UP or DOWN trend, the app fires an alert through three channels: a **sound**, a **Windows desktop notification**, and a **native MT5 alert** (see below). The alert is **edge-triggered** — it fires once at trend onset and re-arms on a flip or a return to choppy, so it won't repeat while a trend persists. A **mute** toggle (sound only) and a **Test** button (exercises all three channels) are provided. The table shows each symbol's live trend state, ADX, and +DI/−DI; trends are evaluated on **closed bars only**.

The watchlist (symbols, timeframe, mute) is saved to `~/.mt5_order_manager/watchlist.json` and restored on the next launch. Scanning runs only while connected and "Start Watching" is on.

### Native MT5 alerts (optional one-time setup)

The MT5 *Python* API cannot raise the terminal's own `Alert()`, so this is done with a small bridge: the app writes each alert to `<MT5 Common>\Files\mt5om_alerts.txt`, and an MQL5 indicator running in the terminal reads that file and raises a real MT5 alert. To enable it:

1. In MT5: **File → Open Data Folder**, then open `MQL5\Indicators\`.
2. Copy [`mt5_bridge/WatchlistAlertBridge.mq5`](mt5_bridge/WatchlistAlertBridge.mq5) into that folder.
3. Open it in **MetaEditor** and **Compile** (F7).
4. Drag **WatchlistAlertBridge** from the terminal's Navigator onto any chart and leave it attached.

Without this indicator the sound and desktop notification still work; only the in-terminal MT5 alert requires it.

**Mobile push notifications (optional):** set the indicator's `InpPushNotification` input to `true` to also push each alert to the MT5 mobile app. This requires **Tools → Options → Notifications** in the terminal: enable push notifications and enter your **MetaQuotes ID** (shown in the mobile app's settings). The `InpDesktopAlert` input controls the terminal popup; you can run either or both.

---

## Display Modes

| | Normal | Compact |
|---|---|---|
| Window size | Freely resizable (min 900×500) | Fixed width, height-only resizable |
| Always on top | No | Yes |
| Tabs | Dashboard + Active Orders + History + Watchlist + Auto Trade | Active Orders only |
| Columns shown | All | Symbol, Type, Volume, Profit |
| Account info | Name + Balance + Equity + P&L | Equity + P&L only |

Toggle between modes with the **Compact / Normal** button in the top-right corner.

---

## Help

The **Help** menu provides:

- **User Manual** — this document, rendered inside the app.
- **About** — app name, version, and project link. The version is also shown in the window title bar.

---

## Project Structure

```
MT5_Order_Management/
├── main.py                  # Entry point
├── version.py               # App version and identity
├── requirements.txt
├── MT5OrderManager.spec     # PyInstaller build config
├── core/
│   ├── mt5_connector.py     # MT5 process detection and connection
│   ├── order_manager.py     # Position reads, open and close logic
│   ├── history_manager.py   # Deal history queries and statistics
│   ├── server_clock.py      # Broker server → UTC offset estimation
│   ├── constants.py         # Auto-trade magic + source icon helpers
│   ├── analytics.py         # Performance stats + rule-based insights
│   ├── auto_trader.py       # Auto-trade orchestrator (paper + live)
│   ├── strategy.py          # EMA + RSI pullback strategy
│   ├── risk_manager.py      # Risk-based position sizing
│   ├── trend_detector.py    # ADX-based clear-trend vs choppy classifier
│   ├── watchlist.py         # Watchlist monitor + alert logic + persistence
│   ├── mt5_alert_bridge.py  # Writes alerts for the MT5 indicator to raise
│   └── indicators.py        # NumPy EMA / RSI / ATR / ADX
├── models/
│   ├── order.py             # Order dataclass
│   ├── history_entry.py     # HistoryEntry dataclass
│   └── signal.py            # Signal / PaperPosition dataclasses
├── ui/
│   ├── main_window.py       # Root window, menu, timers, wiring
│   ├── connection_panel.py  # Status bar + account stats + timezone
│   ├── orders_panel.py      # Live order table with action buttons
│   ├── history_panel.py     # History table + filter controls
│   ├── dashboard_panel.py   # Performance analytics + insights tab
│   ├── watchlist_panel.py   # Watchlist config + trend table + alert log
│   └── autotrade_panel.py   # Auto-trade config, stats, decision log
├── utils/
│   ├── timezone_manager.py  # Timezone conversion helpers
│   └── sound.py             # Non-blocking alert sound (winsound)
└── mt5_bridge/
    └── WatchlistAlertBridge.mq5  # MT5 indicator that raises native alerts
```

---

## Dependencies

| Package | Purpose |
|---|---|
| `MetaTrader5` | MT5 API (positions, history, order execution) |
| `PySide6` | Qt6 GUI framework |
| `psutil` | MT5 process detection |
| `numpy` | Technical indicators for the auto-trader |
| `tzdata` | Timezone database for the timezone selector |

---

## License

MIT
