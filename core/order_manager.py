from __future__ import annotations

import math

from core import server_clock
from models.order import Order

try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    mt5 = None  # type: ignore[assignment]
    MT5_AVAILABLE = False

# symbol_info().filling_mode flag bits (MQL5 SYMBOL_FILLING_*); the Python
# package doesn't export these constants
_SYMBOL_FILLING_FOK = 1
_SYMBOL_FILLING_IOC = 2


class OrderManager:
    def __init__(self) -> None:
        # digits/step/min don't change during a session — cache per symbol
        self._symbol_info_cache: dict[str, object] = {}

    def _symbol_info(self, symbol: str):
        info = self._symbol_info_cache.get(symbol)
        if info is None:
            info = mt5.symbol_info(symbol)
            if info is not None:
                self._symbol_info_cache[symbol] = info
        return info

    @staticmethod
    def _filling_mode(info) -> int:
        """Pick a filling mode the symbol actually allows (IOC preferred for
        partial closes, then FOK); RETURN for market/exchange execution."""
        flags = getattr(info, "filling_mode", 0) if info else 0
        if flags & _SYMBOL_FILLING_IOC:
            return mt5.ORDER_FILLING_IOC
        if flags & _SYMBOL_FILLING_FOK:
            return mt5.ORDER_FILLING_FOK
        return mt5.ORDER_FILLING_RETURN

    @staticmethod
    def _snap_volume(volume: float, info) -> float:
        """Snap a volume down to the symbol's lot step."""
        step = getattr(info, "volume_step", 0.01) if info else 0.01
        if step <= 0:
            step = 0.01
        snapped = math.floor(volume / step + 1e-9) * step
        return round(snapped, 8)

    def get_open_orders(self) -> list[Order]:
        if not MT5_AVAILABLE:
            return []

        positions = mt5.positions_get()
        if positions is None:
            return []

        # One tick fetch per symbol per refresh, not per position
        ticks: dict[str, object] = {}
        for pos in positions:
            if pos.symbol not in ticks:
                ticks[pos.symbol] = mt5.symbol_info_tick(pos.symbol)

        orders: list[Order] = []
        for pos in positions:
            order_type = "BUY" if pos.type == mt5.POSITION_TYPE_BUY else "SELL"

            tick = ticks[pos.symbol]
            if tick is not None:
                # BUY positions are closed at bid; SELL positions are closed at ask
                current_price = tick.bid if pos.type == mt5.POSITION_TYPE_BUY else tick.ask
                ts = tick.time_msc / 1000.0 if getattr(tick, "time_msc", 0) else tick.time
                server_clock.update_from_tick_time(ts)
            else:
                current_price = pos.price_current

            info = self._symbol_info(pos.symbol)
            digits = getattr(info, "digits", 2) if info else 2

            orders.append(Order(
                ticket=pos.ticket,
                symbol=pos.symbol,
                order_type=order_type,
                volume=pos.volume,
                open_price=pos.price_open,
                current_price=current_price,
                sl=pos.sl,
                tp=pos.tp,
                profit=pos.profit,
                open_time=server_clock.server_ts_to_utc(pos.time),
                digits=digits,
            ))

        return orders

    def close_order(self, ticket: int, volume: float) -> tuple[bool, str]:
        if not MT5_AVAILABLE:
            return False, "MetaTrader5 package is not installed"

        positions = mt5.positions_get(ticket=ticket)
        if not positions:
            return False, f"Position {ticket} not found"

        pos = positions[0]
        tick = mt5.symbol_info_tick(pos.symbol)
        if tick is None:
            return False, f"Could not get tick data for {pos.symbol}"

        info = self._symbol_info(pos.symbol)
        volume = min(self._snap_volume(volume, info), pos.volume)
        if volume <= 0:
            return False, f"Volume {volume:g} is not closable for {pos.symbol}"

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": pos.symbol,
            "volume": volume,
            "type": mt5.ORDER_TYPE_SELL if pos.type == mt5.POSITION_TYPE_BUY else mt5.ORDER_TYPE_BUY,
            "position": ticket,
            "price": tick.bid if pos.type == mt5.POSITION_TYPE_BUY else tick.ask,
            "deviation": 20,
            "magic": 0,
            "comment": "MT5Manager close",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": self._filling_mode(info),
        }

        result = mt5.order_send(request)
        if result is None:
            code, desc = mt5.last_error()
            return False, f"order_send failed [{code}]: {desc}"

        if result.retcode == mt5.TRADE_RETCODE_DONE:
            return True, ""

        return False, f"[{result.retcode}] {result.comment}"

    def close_all_orders(self) -> tuple[int, int, list[str]]:
        """Close every open position. Returns (closed, failed, error_list)."""
        if not MT5_AVAILABLE:
            return 0, 0, ["MetaTrader5 package is not installed"]
        positions = mt5.positions_get()
        if not positions:
            return 0, 0, []
        closed, failed, errors = 0, 0, []
        for pos in positions:
            ok, err = self.close_order(pos.ticket, pos.volume)
            if ok:
                closed += 1
            else:
                failed += 1
                errors.append(f"#{pos.ticket}: {err}")
        return closed, failed, errors

    def close_percent(self, ticket: int, percent: float) -> tuple[bool, str]:
        if not MT5_AVAILABLE:
            return False, "MetaTrader5 package is not installed"

        positions = mt5.positions_get(ticket=ticket)
        if not positions:
            return False, f"Position {ticket} not found"

        pos = positions[0]
        if percent >= 100:
            # Full close — send the exact position volume, no rounding
            return self.close_order(ticket, pos.volume)

        info = self._symbol_info(pos.symbol)
        volume = self._snap_volume(pos.volume * percent / 100, info)
        vol_min = getattr(info, "volume_min", 0.01) if info else 0.01

        if volume < vol_min:
            return False, f"Computed volume {volume:g} is below the symbol minimum {vol_min:g}"

        return self.close_order(ticket, volume)
