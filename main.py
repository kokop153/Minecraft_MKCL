import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from launcher.logsetup import setup_logging

LOG_PATH = setup_logging(BASE_DIR)


def main():
    from PyQt5.QtCore import Qt
    from PyQt5.QtGui import QFont
    from PyQt5.QtWidgets import QApplication, QStyleFactory

    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv)
    app.setApplicationName("MKCL")
    app.setStyle(QStyleFactory.create("Fusion"))
    app.setFont(QFont("Microsoft YaHei UI", 10))

    from launcher.ui.main_window import AppContext, MainWindow
    ctx = AppContext(BASE_DIR)
    win = MainWindow(ctx)
    win.apply_theme()
    win.show()
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
