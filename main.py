from __future__ import annotations

import sys
import os

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon

from core.mt5_connector  import MT5Connector
from core.order_manager  import OrderManager
from core.history_manager import HistoryManager
from ui.main_window      import MainWindow


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

    connector  = MT5Connector()
    order_mgr  = OrderManager()
    history_mgr = HistoryManager()

    window = MainWindow(connector, order_mgr, history_mgr)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
