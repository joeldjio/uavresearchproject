"""
Entry point: python -m tools.ui

Flags
-----
--legacy    Use old PySide6 QWidget UI (main_window.py) instead of QML.
"""

import sys


def main():
    if "--legacy" in sys.argv:
        import warnings

        warnings.warn(
            "The --legacy QWidget UI is deprecated and will be removed in a future version. "
            "Use the default QML UI instead (omit --legacy).",
            DeprecationWarning,
            stacklevel=1,
        )
        from PySide6.QtGui import QFont
        from PySide6.QtWidgets import QApplication, QMessageBox

        from tools.ui._version import VERSION
        from tools.ui.legacy.main_window import MainWindow

        app = QApplication(sys.argv)
        app.setApplicationName("SkyMeshX")
        app.setApplicationVersion(VERSION)
        app.setFont(QFont("Segoe UI", 10))

        # Show deprecation notice in UI
        msg = QMessageBox()
        msg.setWindowTitle("Legacy UI — Deprecated")
        msg.setText(
            "<b>The legacy QWidget UI is deprecated.</b><br><br>"
            "Start the app without <code>--legacy</code> to use the modern QML UI.<br>"
            "The legacy UI will be removed in a future version."
        )
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.exec()

        win = MainWindow()
        win.show()
        sys.exit(app.exec())
    else:
        from tools.ui.app import run

        sys.exit(run())


if __name__ == "__main__":
    main()
