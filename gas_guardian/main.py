import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from app.main_window import MainWindow


def main() -> int:
    application = QApplication(sys.argv)
    application.setApplicationName("Gas Guardian")
    application.setOrganizationName("Gas Guardian")
    window = MainWindow(Path(__file__).resolve().parent)
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
