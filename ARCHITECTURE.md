# MT5 Order Management - Architecture

## Tech Stack
- Python 3.10+
- PySide6 (Qt6) for Windows GUI
- MetaTrader5 Python library (official MT5 Python API)
- psutil for process detection

## Project Structure
```
MT5_Order_Management/
├── main.py                      # App entry point
├── requirements.txt
├── core/
│   ├── __init__.py
│   ├── mt5_connector.py         # MT5 detection & connection
│   ├── order_manager.py         # Open orders & close operations
│   └── history_manager.py       # Closed orders history
├── models/
│   ├── __init__.py
│   ├── order.py                 # Open order dataclass
│   └── history_entry.py         # History order dataclass
├── ui/
│   ├── __init__.py
│   ├── main_window.py           # QMainWindow, holds all panels
│   ├── connection_panel.py      # Connection status bar widget
│   ├── orders_panel.py          # Active orders table
│   └── history_panel.py         # History table with filters
└── utils/
    ├── __init__.py
    └── formatters.py            # Number/date helpers
```

## Core API Contracts

### MT5Connector (core/mt5_connector.py)
```python
class MT5Connector:
    def detect() -> bool          # True if terminal64.exe/terminal.exe in process list
    def connect(login, password, server) -> bool   # mt5.initialize()
    def disconnect()                               # mt5.shutdown()
    def is_connected() -> bool
```

### OrderManager (core/order_manager.py)
```python
class OrderManager:
    def get_open_orders() -> list[Order]           # mt5.positions_get()
    def close_order(ticket, volume) -> bool        # mt5.order_send() with TRADE_ACTION_DEAL
    def close_percent(ticket, percent) -> bool     # close_order(ticket, position.volume * percent)
```

### HistoryManager (core/history_manager.py)
```python
class HistoryManager:
    def get_history(from_dt, to_dt) -> list[HistoryEntry]   # mt5.history_deals_get()
    def calculate_win_rate(entries) -> float                # wins / total * 100
    def calculate_summary(entries) -> dict                  # totals, wins, losses, net profit
```

## UI Layout

### Connection Panel (top bar, compact horizontal)
```
[● Status Label]  [Login: ___]  [Password: ___]  [Server: ___]  [Connect]  [Disconnect]
```
- Status colors: amber = MT5 Running (not connected), red = MT5 not found, green = Connected
- Connect button enabled only when MT5 is detected but not yet connected
- Disconnect button enabled only when connected

### Main Content (QTabWidget)
- Tab 1 "Active Orders": scrollable QTableWidget
  Columns: Ticket | Symbol | Type | Volume | Open Price | Current Price | SL | TP | Profit | Actions
  Actions column: [Close] [50%] [80%] [90%] — QPushButton in each row
  
- Tab 2 "History": 
  Top right: Win Rate label (large, bold, green if >50%, red if <50%)
  Filter bar: [From date] [To date] [Filter button]
  Table: Ticket | Symbol | Type | Volume | Open Price | Close Price | Profit | Open Time | Close Time
  Bottom summary: Total trades | Wins | Losses | Total Profit

## Threading Model
- QTimer polling every 2 seconds for position updates while connected
- All MT5 calls run on main thread (MT5 API is not thread-safe)
- UI updates via Qt signals

## Color Scheme (dark, compact)
- Background: #1a1a2e
- Panel: #16213e
- Accent: #0f3460
- Amber: #e8a838
- Green: #00b894
- Red: #e17055
- Text: #eaeaea
