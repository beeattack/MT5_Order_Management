# MT5 Order Manager

A lightweight Windows desktop application for monitoring and managing open positions in MetaTrader 5, built with Python and PySide6.

![Python](https://img.shields.io/badge/Python-3.10+-blue) ![PySide6](https://img.shields.io/badge/PySide6-6.6+-green) ![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey)

---

## Features

- **One-click connect** to any already-running MT5 terminal — no login credentials required
- **Live order table** refreshed every second: symbol, type, volume, open price, current price, SL/TP, and floating P&L
- **Partial close** — close 25%, 50%, 75%, or 100% of any position from the action buttons
- **Close All** — close every open position in one click (with confirmation)
- **Trade history** — filter closed deals by date range with a summary of net P&L and win rate
- **Compact mode** — a narrow always-on-top overlay that shows only the essentials so you can keep it beside any chart

---

## Screenshots

### Normal Mode
Full-width window with all columns, account stats, and trade history tab.

### Compact Mode
Pinned always-on-top overlay with fixed width. Shows symbol, type, volume, current price, P&L, and action buttons. Account name is hidden; equity is always visible.

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

Download `MT5OrderManager.exe` from [Releases](../../releases), extract the folder, and run `MT5OrderManager.exe`. No Python installation needed.

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
| MT5 Detected | Terminal found, not yet connected |
| Connected — *Account Name* | Active connection, live data flowing |

### Order Refresh

Once connected, a 1-second timer polls `mt5.positions_get()` and updates the table. Current price uses `tick.bid` for BUY positions and `tick.ask` for SELL positions (the actual close price), not the lagging `price_current` field from the position struct.

### Closing Positions

Partial closes are computed as `round(volume × percent / 100, 2)`. Orders below 0.01 lots are rejected. Each close sends an `ORDER_TYPE_SELL` (for BUY) or `ORDER_TYPE_BUY` (for SELL) via `TRADE_ACTION_DEAL` with `ORDER_FILLING_IOC`.

### Trade History

The History tab queries `mt5.history_deals_get(from, to)` and displays each closed deal with entry/exit prices, volume, and net profit. The summary row shows total P&L, number of winning trades, and win rate percentage.

---

## Display Modes

| | Normal | Compact |
|---|---|---|
| Window size | Freely resizable (min 900×500) | Fixed width, height-only resizable |
| Always on top | No | Yes |
| Tabs | Active Orders + History | Active Orders only |
| Columns shown | All | Symbol, Type, Volume, Current Price, Profit |
| Account info | Name + Balance + Equity + P&L | Equity + P&L only |

Toggle between modes with the **Compact / Normal** button in the top-right corner.

---

## Project Structure

```
MT5_Order_Management/
├── main.py                  # Entry point
├── requirements.txt
├── MT5OrderManager.spec     # PyInstaller build config
├── core/
│   ├── mt5_connector.py     # MT5 process detection and connection
│   ├── order_manager.py     # Open position reads and close logic
│   └── history_manager.py   # Deal history queries and statistics
├── models/
│   ├── order.py             # Order dataclass
│   └── history_entry.py     # HistoryEntry dataclass
├── ui/
│   ├── main_window.py       # Root window, timers, wiring
│   ├── connection_panel.py  # Status bar + account stats
│   ├── orders_panel.py      # Live order table with action buttons
│   └── history_panel.py     # History table + filter controls
└── utils/
    └── formatters.py
```

---

## Dependencies

| Package | Purpose |
|---|---|
| `MetaTrader5` | MT5 API (positions, history, order execution) |
| `PySide6` | Qt6 GUI framework |
| `psutil` | MT5 process detection |

---

## License

MIT
