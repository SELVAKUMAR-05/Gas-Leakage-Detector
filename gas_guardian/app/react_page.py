import json
from pathlib import Path

from PySide6.QtCore import QObject, QUrl, Slot
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QVBoxLayout, QWidget


class DashboardBridge(QObject):
    def __init__(self, window):
        super().__init__()
        self.window = window

    @Slot(result=str)
    def get_state(self) -> str:
        return json.dumps(self.window.web_state())

    @Slot()
    def connect_hardware(self):
        self.window._connect_hardware()

    @Slot()
    def disconnect_hardware(self):
        self.window._disconnect_hardware()

    @Slot()
    def toggle_demo(self):
        self.window._toggle_demo()

    @Slot(str)
    def apply_settings(self, payload: str):
        self.window._apply_web_settings(payload)

    @Slot()
    def refresh_history(self):
        self.window._refresh_history()

    @Slot()
    def refresh_ports(self):
        self.window._refresh_ports()

    @Slot()
    def export_history(self):
        self.window._export_history_dialog()


class ReactDashboardPage(QWidget):
    def __init__(self, window):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.view = QWebEngineView(self)
        self.channel = QWebChannel(self.view.page())
        self.bridge = DashboardBridge(window)
        self.channel.registerObject("bridge", self.bridge)
        self.view.page().setWebChannel(self.channel)
        self.view.setUrl(QUrl.fromLocalFile(str(Path(__file__).resolve().parent.parent / "web" / "index.html")))
        layout.addWidget(self.view)