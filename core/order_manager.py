from __future__ import annotations

from datetime import datetime, timezone

from models.order import Order

try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    mt5 = None  # type: ignore[assignment]
    MT5_AVAILABLE = False


class OrderManager:
    def get_open_orders(self) -> list[Order]:
        if not MT5_AVAILABLE:
            return []

        positions = mt5.positions_get()
        if positions is None:
            return []

        orders: list[Order] = []
        for pos in positions:
            order_type = "BUY" if pos.type == mt5.POSITION_TYPE_BUY else "SELL"

            tick = mt5.symbol_info_tick(pos.symbol)
            if tick is not None:
                # BUY positions are closed at bid; SELL positions are closed at ask
                current_price = tick.bid if pos.type == mt5.POSITION_TYPE_BUY else tick.ask
            else:
                current_price = pos.price_current

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
                open_time=datetime.fromtimestamp(pos.time, tz=timezone.utc),
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

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": pos.symbol,
            "volume": round(volume, 2),
            "type": mt5.ORDER_TYPE_SELL if pos.type == mt5.POSITION_TYPE_BUY else mt5.ORDER_TYPE_BUY,
            "position": ticket,
            "price": tick.bid if pos.type == mt5.POSITION_TYPE_BUY else tick.ask,
            "deviation": 20,
            "magic": 0,
            "comment": "MT5Manager close",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request)
        if result is None:
            code, desc = mt5.last_error()
            return False, f"order_send failed [{code}]: {desc}"

        if result.retcode == mt5.TRADE_RETCODE_DONE:
            return True, ""

        return False, result.comment

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
        volume = round(pos.volume * percent / 100, 2)

        if volume < 0.01:
            return False, f"Computed volume {volume} is below minimum 0.01"

        return self.close_order(ticket, volume)
