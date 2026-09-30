from datetime import datetime
from pathlib import Path
import csv
import json
import sqlite3
import time

from PySide6.QtCore import QTimer
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QApplication, QFileDialog, QMainWindow, QMessageBox

from app.database import EventDatabase
from app.models import parse_packet
from app.react_page import ReactDashboardPage
from app.serial_manager import SerialManager
from app.settings import AppSettings, SettingsStore
from app.widgets.dashboard import DashboardPage
from app.widgets.history import HistoryPage
from app.widgets.live_monitor import LiveMonitorPage
from app.widgets.settings_page import SettingsPage


class MainWindow(QMainWindow):
    def __init__(self, project_dir: Path):
        super().__init__()
        self.project_dir = project_dir
        self.data_dir = project_dir / "data"
        self.database_error = ""
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self.database_error = f"Local data directory unavailable: {exc}"
        self.settings_store = SettingsStore(self.data_dir / "settings.json")
        self.settings = self.settings_store.load()
        self.serial_manager = SerialManager()
        self.database: EventDatabase | None = None
        try:
            self.database = EventDatabase(self.data_dir / "gas_guardian.db")
        except (OSError, RuntimeError, ValueError, sqlite3.Error) as exc:
            self.database_error = f"History database unavailable: {exc}"

        self.current_value: int | None = None
        self.current_status: str | None = None
        self.last_received_at: datetime | None = None
        self.last_sensor_packet_at: float | None = None
        self.connected_at: float | None = None
        self.maximum_value = 0
        self.latest_raw = ""
        self.sensor_data_state = "waiting"
        self.sensor_data_message = "No live hardware data"
        self.ui_message = ""
        self.ui_error = False
        self.web_readings: list[dict] = []
        self.event_count = self._leakage_count()
        self.is_demo = False
        self.is_connected = False
        self._build_ui()
        self._apply_theme()
        self._refresh_history()
        if self.database_error:
            self._set_message(self.database_error, error=True)

        self.demo_timer = QTimer(self)
        self.demo_timer.setInterval(500)
        self.demo_timer.timeout.connect(self._demo_tick)
        self.sensor_freshness_timer = QTimer(self)
        self.sensor_freshness_timer.setInterval(1000)
        self.sensor_freshness_timer.timeout.connect(self._check_sensor_freshness)
        self.sensor_freshness_timer.start()
        self.live_page.connect_button.clicked.connect(self._connect_hardware)
        self.live_page.disconnect_button.clicked.connect(self._disconnect_hardware)
        self.live_page.demo_button.clicked.connect(self._toggle_demo)
        self.history_page.refresh_button.clicked.connect(self._refresh_history)
        self.history_page.export_requested = self._export_history
        self.settings_page.settings_applied.connect(self._apply_settings)

    def _build_ui(self):
        self.setWindowTitle("Gas Guardian | Real-time gas monitoring")
        self.resize(1360, 900)
        self.setMinimumSize(900, 620)
        self.available_ports = SerialManager.available_ports()
        self.dashboard_page = DashboardPage()
        self.live_page = LiveMonitorPage(self.settings.graph_duration, self.settings.threshold)
        self.history_page = HistoryPage()
        self.settings_page = SettingsPage(self.settings, self.available_ports)
        self.react_page = ReactDashboardPage(self)
        self.setCentralWidget(self.react_page)

    def _connect_hardware(self):
        if self.is_demo:
            self._stop_demo()
        port = self.settings_page.port.currentText().strip() or self.settings.port
        baud = int(self.settings_page.baud.currentData())
        try:
            worker = self.serial_manager.connect(port, baud, self.settings.threshold, start=False)
        except RuntimeError as exc:
            self._set_message(str(exc), error=True)
            return
        worker.connection_changed.connect(self._on_connection_changed)
        worker.packet_received.connect(self._on_packet)
        worker.raw_received.connect(self._on_raw_message)
        worker.error_occurred.connect(self._on_serial_error)
        worker.start()
        self._set_message(f"Opening {port}…")

    def _disconnect_hardware(self):
        self.serial_manager.disconnect()
        self.is_connected = False
        self._clear_reading_state()
        self.dashboard_page.set_connection(False)
        self.live_page.set_connection(False)
        self._set_message("Disconnected")

    def _on_connection_changed(self, connected: bool, port: str):
        self.is_connected = connected
        if self.is_demo and not connected:
            return
        self.connected_at = time.monotonic() if connected else None
        self._clear_reading_state()
        self.dashboard_page.set_connection(connected, port)
        self.live_page.set_connection(connected, port)
        if connected:
            self._set_message(f"Connected to {port}")
        self.sensor_data_state = "waiting"
        self.sensor_data_message = "PORT OPEN · waiting for valid GAS packets" if connected else "No live hardware data"

    def _on_packet(self, packet):
        self.last_sensor_packet_at = time.monotonic()
        status = packet.firmware_status if packet.value is None else (
            "LEAKING" if packet.value >= self.settings.threshold else "NORMAL"
        )
        self._accept_reading(packet.value, packet.received_at, packet.raw, status, demo=False)

    def _on_raw_message(self, raw: str):
        if self.is_demo:
            return
        self.latest_raw = raw
        self.live_page.serial_display.setPlainText(raw)
        if self.is_connected and parse_packet(raw) is None:
            self.sensor_data_state = "invalid"
            self.sensor_data_message = "SERIAL FORMAT ERROR · unrecognized data; expected GAS,<value>,<status>"
            self.dashboard_page.set_sensor_data_state(
                "invalid",
                f"SERIAL FORMAT ERROR  ·  expected GAS,<value>,NORMAL or GAS,<value>,LEAKING  ·  received: {raw[:48]}",
            )

    def _on_serial_error(self, message: str):
        self._set_message(message, error=True)
        if self.is_connected and "No serial data" in message:
            self.sensor_data_state = "stale"
            self.sensor_data_message = "NO SENSOR DATA · check firmware, baud rate, and wiring"
            self.dashboard_page.set_sensor_data_state("stale", "NO SENSOR DATA  ·  check firmware, baud rate, and wiring")

    def _check_sensor_freshness(self):
        if not self.is_connected or self.is_demo:
            return
        now = time.monotonic()
        reference = self.last_sensor_packet_at or self.connected_at
        if reference is None or now - reference < 3:
            return
        age = int(now - reference)
        if self.last_sensor_packet_at is None:
            self.sensor_data_state = "stale"
            self.sensor_data_message = "NO VALID GAS PACKETS · check firmware and 9600 baud"
            self.dashboard_page.set_sensor_data_state(
                "stale", "NO VALID GAS PACKETS  ·  check firmware and 9600 baud"
            )
        else:
            self.sensor_data_state = "stale"
            self.sensor_data_message = f"SENSOR DATA STALE · last valid reading {age}s ago"
            self.dashboard_page.set_sensor_data_state(
                "stale", f"SENSOR DATA STALE  ·  last valid reading {age}s ago"
            )

    def _accept_reading(self, value: int | None, timestamp: datetime, raw: str, status: str, demo: bool):
        previous_status = self.current_status
        self.current_value = value
        self.current_status = status
        if value is not None:
            self.maximum_value = max(self.maximum_value, value)
        self.latest_raw = raw
        self.sensor_data_state = "demo" if demo else "live"
        self.last_received_at = timestamp
        if demo:
            source = "SIMULATED DEMO DATA · not from an MQ-3 sensor"
        elif value is None:
            source = "LIVE STATUS ONLY · firmware sent no ADC value"
        else:
            source = "LIVE SENSOR DATA"
        self.sensor_data_message = f"{source} · updated {timestamp.astimezone().strftime('%H:%M:%S')}"
        if value is not None:
            self.web_readings.append({"value": value, "time": timestamp.isoformat()})
            del self.web_readings[:-90]
        changed = previous_status != status
        if not demo and changed and (previous_status is not None or status == "LEAKING"):
            try:
                if self.database:
                    self.database.record_transition(timestamp, value, status, self.settings.threshold)
                    self.event_count = self.database.count_leakage_events()
            except (OSError, RuntimeError, ValueError, sqlite3.Error) as exc:
                self._set_message(f"Could not save event: {exc}", error=True)
        if value is not None:
            self.dashboard_page.update_reading(value, status, self.settings.threshold, self.maximum_value, self.event_count, timestamp, demo)
            self.live_page.add_reading(timestamp, value, raw, demo)
        if not demo and changed and status == "LEAKING" and self.settings.pc_sound:
            QApplication.beep()
        if not demo and changed:
            self._refresh_history()

    def _apply_settings(self, settings: AppSettings):
        try:
            self.settings_store.save(settings)
        except OSError as exc:
            self._set_message(f"Could not save settings: {exc}", error=True)
            return
        self.settings = settings
        self.settings_page.settings = settings
        self.live_page.set_threshold(settings.threshold)
        self.live_page.set_graph_duration(settings.graph_duration)
        self.live_page.chart.set_theme(settings.theme == "Dark")
        self._apply_theme()
        if self.serial_manager.worker is not None and self.serial_manager.worker.isRunning():
            self.serial_manager.worker.set_threshold(settings.threshold)
        if self.current_value is not None:
            status = "LEAKING" if self.current_value >= settings.threshold else "NORMAL"
            raw = f"GAS,{self.current_value},{status}" + (" [DEMO]" if self.is_demo else "")
            self._accept_reading(self.current_value, datetime.now(), raw, status, self.is_demo)
        self._set_message("Settings saved")

    def _toggle_demo(self):
        if self.is_demo:
            self._stop_demo()
            return
        if self.serial_manager.worker is not None and self.serial_manager.worker.isRunning():
            self.serial_manager.disconnect()
            self.is_connected = False
        self._clear_reading_state()
        self.is_demo = True
        self.live_page.set_demo(True)
        self.dashboard_page.set_demo(True)
        self._set_message("Demo mode active; readings are simulated")
        self.demo_timer.start()

    def _stop_demo(self):
        self.demo_timer.stop()
        self.is_demo = False
        self._clear_reading_state()
        self.live_page.set_demo(False)
        self.dashboard_page.set_connection(False)
        self._set_message("Demo mode stopped")

    def _clear_reading_state(self):
        self.current_value = None
        self.current_status = None
        self.last_received_at = None
        self.last_sensor_packet_at = None
        self.maximum_value = 0
        self.latest_raw = ""
        self.sensor_data_state = "waiting"
        self.sensor_data_message = "No live hardware data"
        self.web_readings.clear()

    def _demo_tick(self):
        value, raw = self.live_page.make_demo_reading(self.settings.threshold)
        status = "LEAKING" if value >= self.settings.threshold else "NORMAL"
        self._accept_reading(value, datetime.now(), raw, status, demo=True)

    def _refresh_history(self):
        if self.database is None:
            self.history_page.populate([])
            return
        try:
            self.history_page.populate(self.database.recent_events())
            self.event_count = self.database.count_leakage_events()
        except (OSError, RuntimeError, ValueError, sqlite3.Error) as exc:
            self._set_message(f"Could not load event history: {exc}", error=True)

    def _export_history(self, destination: str):
        if self.database is None:
            QMessageBox.warning(self, "Export unavailable", self.database_error or "The history database is unavailable.")
            return
        try:
            count = self.database.export_csv(Path(destination))
            self._set_message(f"Exported {count} history records")
        except (OSError, RuntimeError, ValueError, sqlite3.Error, csv.Error) as exc:
            QMessageBox.warning(self, "Export failed", f"Could not export history:\n{exc}")

    def _leakage_count(self) -> int:
        try:
            return self.database.count_leakage_events() if self.database else 0
        except (OSError, RuntimeError, ValueError, sqlite3.Error):
            return 0

    def _set_message(self, message: str, error: bool = False):
        self.ui_message = message
        self.ui_error = error

    def web_state(self) -> dict:
        history = []
        if self.database is not None:
            try:
                history = [dict(row) for row in self.database.recent_events(12)]
            except (OSError, RuntimeError, ValueError, sqlite3.Error):
                pass
        return {
            "connected": self.is_connected,
            "demo": self.is_demo,
            "port": self.settings.port,
            "value": self.current_value,
            "status": self.current_status,
            "maximum": self.maximum_value,
            "threshold": self.settings.threshold,
            "event_count": self.event_count,
            "raw": self.latest_raw,
            "sensor_state": self.sensor_data_state,
            "sensor_message": self.sensor_data_message,
            "message": self.ui_message,
            "message_error": self.ui_error,
            "updated": self.last_received_at.isoformat() if self.last_received_at else None,
            "readings": self.web_readings,
            "history": history,
            "ports": self.available_ports,
            "email_supported": False,
            "settings": {
                "port": self.settings.port,
                "baud_rate": self.settings.baud_rate,
                "threshold": self.settings.threshold,
                "graph_duration": self.settings.graph_duration,
                "theme": self.settings.theme,
                "pc_sound": self.settings.pc_sound,
                "email_enabled": self.settings.email_enabled,
                "email_recipient": self.settings.email_recipient,
                "smtp_host": self.settings.smtp_host,
                "smtp_port": self.settings.smtp_port,
                "smtp_sender": self.settings.smtp_sender,
                "smtp_username": self.settings.smtp_username,
                "smtp_security": self.settings.smtp_security,
            },
        }

    def _apply_web_settings(self, payload: str):
        try:
            values = json.loads(payload)
            threshold = max(0, min(1023, int(values.get("threshold", self.settings.threshold))))
            duration = max(10, min(600, int(values.get("graph_duration", self.settings.graph_duration))))
            baud_rate = int(values.get("baud_rate", self.settings.baud_rate))
            if baud_rate not in {9600, 19200, 38400, 57600, 115200}:
                baud_rate = self.settings.baud_rate
            theme = values.get("theme")
            if theme not in {"Dark", "Light"}:
                theme = self.settings.theme
            settings = AppSettings(
                port=str(values.get("port", self.settings.port)).strip() or self.settings.port,
                baud_rate=baud_rate,
                threshold=threshold,
                graph_duration=duration,
                theme=theme,
                pc_sound=bool(values.get("pc_sound", self.settings.pc_sound)),
                email_enabled=bool(values.get("email_enabled", self.settings.email_enabled)),
                email_recipient=str(values.get("email_recipient", self.settings.email_recipient)).strip(),
                smtp_host=str(values.get("smtp_host", self.settings.smtp_host)).strip() or "smtp.gmail.com",
                smtp_port=max(1, min(65535, int(values.get("smtp_port", self.settings.smtp_port)))),
                smtp_sender=str(values.get("smtp_sender", self.settings.smtp_sender)).strip(),
                smtp_username=str(values.get("smtp_username", self.settings.smtp_username)).strip(),
                smtp_security=values.get("smtp_security", self.settings.smtp_security),
            )
        except (AttributeError, TypeError, ValueError, json.JSONDecodeError) as exc:
            self._set_message(f"Invalid settings: {exc}", error=True)
            return
        self.settings_page.port.setCurrentText(settings.port)
        self.settings_page.baud.setCurrentIndex(max(0, self.settings_page.baud.findData(settings.baud_rate)))
        self._apply_settings(settings)

    def _export_history_dialog(self):
        destination, _ = QFileDialog.getSaveFileName(self, "Export event history", "gas_guardian_history.csv", "CSV files (*.csv)")
        if destination:
            self._export_history(destination)

    def _refresh_ports(self):
        self.available_ports = SerialManager.available_ports()
        self.settings_page.refresh_ports(self.available_ports)

    def _apply_theme(self):
        dark = self.settings.theme == "Dark"
        self.setStyleSheet(DARK_STYLESHEET if dark else LIGHT_STYLESHEET)
        if hasattr(self, "live_page"):
            self.live_page.chart.set_theme(dark)

    def closeEvent(self, event: QCloseEvent):
        self.demo_timer.stop()
        self.sensor_freshness_timer.stop()
        self.serial_manager.disconnect()
        event.accept()


DARK_STYLESHEET = """
QMainWindow { background: #11171b; }
QWidget { color: #e6ecee; font-family: 'Segoe UI'; font-size: 10pt; }
#sidebar { background: #171f24; border-right: 1px solid #2a353b; }
#brand { color: #f4f8f8; font-size: 19pt; font-weight: 800; }
#brandSubtitle, #eyebrow { color: #829199; font-size: 8pt; font-weight: 700; }
#navButton { border: 0; border-radius: 5px; text-align: left; padding: 11px 12px; color: #a8b5ba; background: transparent; }
#navButton:hover { color: #f3fbf8; background: #202b30; }
#navButton:checked { color: #f3fbf8; background: #26342f; border-left: 3px solid #39c5a1; padding-left: 9px; }
#sidebarNote { color: #839198; font-size: 8pt; border-top: 1px solid #2a353b; padding-top: 12px; }
#topbar { background: #171f24; border-bottom: 1px solid #2a353b; }
#topbarState { color: #a9b7bc; font-weight: 600; }
#pageTitle { font-size: 21pt; font-weight: 700; }
#sectionTitle { font-size: 11pt; font-weight: 650; }
#metricCard, #panel { background: #171f24; border: 1px solid #29363c; border-radius: 7px; }
#metricCard[kind="level"] { border-top: 2px solid #39c5a1; }
#metricCard[kind="maximum"] { border-top: 2px solid #6e9dde; }
#metricCard[kind="threshold"] { border-top: 2px solid #e4b75d; }
#metricCard[kind="events"] { border-top: 2px solid #ed786e; }
#metricValue { font-size: 22pt; font-weight: 700; color: #eff6f5; }
#muted, #statusDescription { color: #92a0a6; }
#sensorDataLabel { color: #f2c566; font-size: 8pt; font-weight: 700; padding-left: 2px; }
#sensorDataLabel[state="live"] { color: #62d3a5; }
#sensorDataLabel[state="demo"] { color: #f2c566; }
#sensorDataLabel[state="stale"], #sensorDataLabel[state="invalid"] { color: #ff8276; }
#statusBanner { border-radius: 7px; }
#statusBanner[state="normal"] { background: #18352e; border: 1px solid #2e6a55; }
#statusBanner[state="leaking"] { background: #3b2221; border: 1px solid #a84d45; }
#statusTitle { font-size: 17pt; font-weight: 800; }
#statusBanner[state="normal"] #statusTitle { color: #62d3a5; }
#statusBanner[state="leaking"] #statusTitle { color: #ff8276; }
#connectionBadge { padding: 7px 10px; border-radius: 4px; font-weight: 650; }
#connectionBadge[state="connected"] { background: #19372f; color: #6cd5aa; }
#connectionBadge[state="disconnected"] { background: #292f32; color: #a3afb3; }
#connectionBadge[state="demo"] { background: #493b20; color: #f2c566; }
#levelText { font-size: 18pt; font-weight: 700; }
QProgressBar { background: #29343a; border: 0; border-radius: 6px; }
QProgressBar::chunk { background: #39c5a1; border-radius: 6px; }
QProgressBar[state="leaking"]::chunk { background: #f06457; }
#outputState { padding: 8px 0; color: #738188; }
#outputState[device="red"][state="on"] { color: #ff766b; font-weight: 700; }
#outputState[device="green"][state="on"] { color: #62d3a5; font-weight: 700; }
#outputState[device="buzzer"][state="on"] { color: #f2c566; font-weight: 700; }
QPushButton { background: #253137; color: #e2ebed; border: 1px solid #3a484e; border-radius: 5px; padding: 8px 13px; }
QPushButton:hover { background: #304047; }
QPushButton:disabled { color: #667379; background: #20282c; }
#primaryButton { background: #167a64; border: 1px solid #24957c; color: white; font-weight: 700; }
#primaryButton:hover { background: #1a8d73; }
#demoButton { color: #f2c566; }
#quietButton { background: transparent; }
#modeBadge { color: #78d8b6; font-weight: 700; font-size: 8pt; }
#modeBadge[state="demo"] { color: #f2c566; }
QPlainTextEdit, QTableWidget, QComboBox, QSpinBox { background: #12191d; border: 1px solid #36434a; border-radius: 4px; padding: 6px; selection-background-color: #167a64; }
QHeaderView::section { background: #202a2f; color: #aab7bc; border: 0; padding: 8px; }
QTableWidget { alternate-background-color: #182126; gridline-color: #2c383e; }
QCheckBox { spacing: 9px; }
#disclaimer { color: #e0bd73; background: #29271e; border-left: 3px solid #d5a94f; padding: 11px; }
#aboutText { color: #b7c3c7; font-size: 12pt; line-height: 1.5; max-width: 760px; }
#errorText { color: #ff8276; }
"""

LIGHT_STYLESHEET = """
QMainWindow { background: #f1f5f4; }
QWidget { color: #21312f; font-family: 'Segoe UI'; font-size: 10pt; }
#sidebar { background: #e4ece9; border-right: 1px solid #cbd7d3; }
#brand { color: #1c2d2a; font-size: 19pt; font-weight: 800; }
#brandSubtitle, #eyebrow { color: #657672; font-size: 8pt; font-weight: 700; }
#navButton { border: 0; border-radius: 5px; text-align: left; padding: 11px 12px; color: #50615d; background: transparent; }
#navButton:hover { color: #155744; background: #dce9e4; }
#navButton:checked { color: #155744; background: #c8e1d7; border-left: 3px solid #168b6d; padding-left: 9px; }
#sidebarNote, #muted, #statusDescription { color: #697a76; }
#sensorDataLabel { color: #926b16; font-size: 8pt; font-weight: 700; padding-left: 2px; }
#sensorDataLabel[state="live"] { color: #19734f; }
#sensorDataLabel[state="demo"] { color: #876210; }
#sensorDataLabel[state="stale"], #sensorDataLabel[state="invalid"] { color: #b5322a; }
#topbar { background: #ffffff; border-bottom: 1px solid #d8e1de; }
#topbarState { color: #425550; font-weight: 600; }
#pageTitle { font-size: 21pt; font-weight: 700; }
#sectionTitle { font-size: 11pt; font-weight: 650; }
#metricCard, #panel { background: #ffffff; border: 1px solid #d8e1de; border-radius: 7px; }
#metricCard[kind="level"] { border-top: 2px solid #168b6d; }
#metricCard[kind="maximum"] { border-top: 2px solid #547db5; }
#metricCard[kind="threshold"] { border-top: 2px solid #b98a22; }
#metricCard[kind="events"] { border-top: 2px solid #c74c43; }
#metricValue { font-size: 22pt; font-weight: 700; color: #1e302b; }
#statusBanner { border-radius: 7px; }
#statusBanner[state="normal"] { background: #def2e9; border: 1px solid #a1d1ba; }
#statusBanner[state="leaking"] { background: #fce8e5; border: 1px solid #e5aaa2; }
#statusTitle { font-size: 17pt; font-weight: 800; }
#statusBanner[state="normal"] #statusTitle { color: #19734f; }
#statusBanner[state="leaking"] #statusTitle { color: #b5322a; }
#connectionBadge { padding: 7px 10px; border-radius: 4px; font-weight: 650; }
#connectionBadge[state="connected"] { background: #def2e9; color: #19734f; }
#connectionBadge[state="disconnected"] { background: #e6e9e8; color: #687572; }
#connectionBadge[state="demo"] { background: #f8edcf; color: #876210; }
#levelText { font-size: 18pt; font-weight: 700; }
QProgressBar { background: #e1e8e5; border: 0; border-radius: 6px; }
QProgressBar::chunk { background: #168b6d; border-radius: 6px; }
QProgressBar[state="leaking"]::chunk { background: #c94137; }
#outputState { padding: 8px 0; color: #80908b; }
#outputState[device="red"][state="on"] { color: #bd372e; font-weight: 700; }
#outputState[device="green"][state="on"] { color: #19734f; font-weight: 700; }
#outputState[device="buzzer"][state="on"] { color: #876210; font-weight: 700; }
QPushButton { background: #e8efec; color: #29403a; border: 1px solid #cbd7d3; border-radius: 5px; padding: 8px 13px; }
QPushButton:hover { background: #dce8e3; }
QPushButton:disabled { color: #8a9692; background: #edf0ef; }
#primaryButton { background: #167a64; border: 1px solid #167a64; color: white; font-weight: 700; }
#demoButton { color: #876210; }
#quietButton { background: transparent; }
#modeBadge { color: #19734f; font-weight: 700; font-size: 8pt; }
#modeBadge[state="demo"] { color: #876210; }
QPlainTextEdit, QTableWidget, QComboBox, QSpinBox { background: #ffffff; border: 1px solid #cbd7d3; border-radius: 4px; padding: 6px; selection-background-color: #168b6d; }
QHeaderView::section { background: #e8efec; color: #425550; border: 0; padding: 8px; }
QTableWidget { alternate-background-color: #f6f9f8; gridline-color: #d8e1de; }
QCheckBox { spacing: 9px; }
#disclaimer { color: #765813; background: #f8edcf; border-left: 3px solid #d5a94f; padding: 11px; }
#aboutText { color: #425550; font-size: 12pt; }
#errorText { color: #b5322a; }
"""
