# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the App

```powershell
# Install dependencies
pip install -r requirements.txt

# Run from source
python main.py
```

## Building the Executable

```powershell
# Build a distributable Windows .exe using PyInstaller
pyinstaller MT5OrderManager.spec

# Output: dist/MT5OrderManager/MT5OrderManager.exe
```

The `.spec` file is already configured with the correct `collect_all` hooks for MetaTrader5 and numpy, and excludes unused PySide6 modules to keep the bundle small.

## Architecture

The app connects to a locally running MT5 terminal (detected via `psutil` process scan) and manages open positions. All MT5 API calls run on the **main thread** — the MT5 library is not thread-safe.

**Data flow:**
1. `MT5Connector` detects/connects to MT5 terminal via `mt5.initialize()` (no login/password — connects to whichever terminal is already authenticated)
2. `OrderManager` reads positions via `mt5.positions_get()` and closes them via `mt5.order_send()` with `TRADE_ACTION_DEAL`
3. `HistoryManager` fetches closed deals via `mt5.history_deals_get()`
4. `MainWindow` wires everything together with two `QTimer` loops: 3-second MT5 detection poll and 100ms order refresh (only the active one runs at a time)

**Signal flow in `MainWindow`:**
- `ConnectionPanel` emits `connect_requested` / `disconnect_requested` → main window calls connector
- `OrdersPanel` emits `close_order_requested(ticket, percent)` → main window calls `order_mgr.close_percent()`
- `HistoryPanel` emits `filter_requested(from_dt, to_dt)` → main window calls `history_mgr`

## Key Conventions

- **Connection model**: `mt5.initialize()` with no arguments — relies on the already-running MT5 terminal. No credentials are collected or used.
- **Partial close**: volumes are snapped down to the symbol's `volume_step` and rejected below `volume_min` (from `symbol_info`). 100% closes send the exact position volume. Filling mode is chosen from the symbol's allowed modes (IOC preferred, then FOK, else RETURN).
- **Server time**: MT5 reports all time fields in the broker server's timezone, not UTC. `core/server_clock.py` estimates the server→UTC offset from fresh tick times; it's used both for displaying times and for shifting history query ranges. Calibrated on connect, refined on every order refresh.
- **Price display**: prices are formatted with the symbol's `digits` (carried on `Order`/`HistoryEntry`), so 5-digit forex pairs and 2-digit metals both render correctly.
- **History stats**: profit and win/loss use the closing deal's net result (`profit + commission + swap + fee`). Open time/price come from the position's first entry deal (matched via `position_id`); a per-position lookup happens only when the entry falls outside the queried range.
- **Current price**: BUY positions show `tick.bid` (close price), SELL positions show `tick.ask` — not `price_current` from the position struct, which can lag.
- **Global QSS**: all styling is defined in `COLORS` dict and `_GLOBAL_QSS` in `main_window.py` — no per-widget stylesheets elsewhere.
- **MT5 import guard**: both `mt5_connector.py` and `order_manager.py` guard the `import MetaTrader5` with try/except so the app launches on machines without MT5 installed (shows appropriate error states).
