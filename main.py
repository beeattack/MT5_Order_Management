from __future__ import annotations

import sys
import os

from PySide6.QtWidgets import QApplication, QPushButton
from PySide6.QtGui import QIcon
from PySide6.QtCore import QObject, QEvent, Qt

from core.mt5_connector  import MT5Connector
from core.order_manager  import OrderManager
from core.history_manager import HistoryManager
from ui.main_window      import MainWindow


class PointerCursorFilter(QObject):
    """Show a hand cursor over enabled push-buttons, app-wide.

    Installed on the QApplication so it also covers buttons created
    dynamically (per-row action buttons, dashboard chips, etc.). Qt
    stylesheets don't support a `cursor` property, so this is the
    reliable way to do it in one place.
    """

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.Enter and isinstance(obj, QPushButton):
            obj.setCursor(
                Qt.CursorShape.PointingHandCursor if obj.isEnabled()
                else Qt.CursorShape.ArrowCursor
            )
        return False


def _icon_path() -> str:
    # Works both from source and from PyInstaller bundle
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "app_icon.ico")


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("MT5 Order Manager")
    icon = QIcon(_icon_path())
    if not icon.isNull():
        app.setWindowIcon(icon)

    cursor_filter = PointerCursorFilter()
    app.installEventFilter(cursor_filter)

    connector  = MT5Connector()
    order_mgr  = OrderManager()
    history_mgr = HistoryManager()

    window = MainWindow(connector, order_mgr, history_mgr)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
