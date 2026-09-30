import math
from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget

from app.charts import GasChart


class LiveMonitorPage(QWidget):
    def __init__(self, graph_duration: int, threshold: int):
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 26, 28, 24)
        root.setSpacing(15)
        title = QLabel("Live monitor")
        title.setObjectName("pageTitle")
        self.mode_badge = QLabel("HARDWARE DATA")
        self.mode_badge.setObjectName("modeBadge")
        header = QHBoxLayout()
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(self.mode_badge)
        root.addLayout(header)

        chart_frame = QFrame()
        chart_frame.setObjectName("panel")
        chart_layout = QVBoxLayout(chart_frame)
        chart_layout.setContentsMargins(14, 12, 14, 8)
        chart_title = QLabel("Gas sensor history")
        chart_title.setObjectName("sectionTitle")
        self.chart = GasChart(graph_duration)
        self.chart.set_threshold(threshold)
        chart_layout.addWidget(chart_title)
        chart_layout.addWidget(self.chart, 1)
        root.addWidget(chart_frame, 1)

        controls = QHBoxLayout()
        self.connect_button = QPushButton("Connect")
        self.connect_button.setObjectName("primaryButton")
        self.disconnect_button = QPushButton("Disconnect")
        self.disconnect_button.setEnabled(False)
        self.demo_button = QPushButton("Start Demo Mode")
        self.demo_button.setObjectName("demoButton")
        self.connection_text = QLabel("Arduino disconnected")
        self.connection_text.setObjectName("muted")
        controls.addWidget(self.connect_button)
        controls.addWidget(self.disconnect_button)
        controls.addWidget(self.demo_button)
        controls.addStretch(1)
        controls.addWidget(self.connection_text)
        root.addLayout(controls)

        serial_title_row = QHBoxLayout()
        serial_title = QLabel("Latest serial message")
        serial_title.setObjectName("sectionTitle")
        self.clear_button = QPushButton("Clear")
        self.clear_button.setObjectName("quietButton")
        serial_title_row.addWidget(serial_title)
        serial_title_row.addStretch(1)
        serial_title_row.addWidget(self.clear_button)
        root.addLayout(serial_title_row)
        self.serial_display = QPlainTextEdit()
        self.serial_display.setReadOnly(True)
        self.serial_display.setMaximumBlockCount(4)
        self.serial_display.setMaximumHeight(82)
        self.serial_display.setPlaceholderText("No serial data received")
        root.addWidget(self.serial_display)

        self.clear_button.clicked.connect(self.serial_display.clear)
        self.demo_index = 0

    def add_reading(self, timestamp: datetime, value: int, raw: str, demo: bool):
        self.chart.add_reading(timestamp, value)
        self.serial_display.setPlainText(raw)
        self.mode_badge.setText("DEMO MODE · SIMULATED" if demo else "HARDWARE DATA")
        self.mode_badge.setProperty("state", "demo" if demo else "hardware")
        self.mode_badge.style().unpolish(self.mode_badge)
        self.mode_badge.style().polish(self.mode_badge)

    def set_threshold(self, threshold: int):
        self.chart.set_threshold(threshold)

    def set_graph_duration(self, seconds: int):
        self.chart.set_duration(seconds)

    def set_connection(self, connected: bool, detail: str = ""):
        self.connection_text.setText(f"Connected · {detail}" if connected else "Arduino disconnected")
        self.connect_button.setEnabled(not connected)
        self.disconnect_button.setEnabled(connected)

    def set_demo(self, enabled: bool):
        self.demo_button.setText("Stop Demo Mode" if enabled else "Start Demo Mode")
        self.connect_button.setEnabled(not enabled)
        self.disconnect_button.setEnabled(not enabled)
        self.connection_text.setText("DEMO MODE · no Arduino connection" if enabled else "Arduino disconnected")
        self.mode_badge.setText("DEMO MODE · SIMULATED" if enabled else "HARDWARE DATA")
        self.mode_badge.setProperty("state", "demo" if enabled else "hardware")
        self.mode_badge.style().unpolish(self.mode_badge)
        self.mode_badge.style().polish(self.mode_badge)

    def make_demo_reading(self, threshold: int) -> tuple[int, str]:
        self.demo_index += 1
        baseline = 220 + int(22 * math.sin(self.demo_index / 8))
        in_alert_cycle = self.demo_index % 50 in range(20, 31)
        value = min(1023, baseline + (threshold + 80 if in_alert_cycle else 0))
        value = max(0, value)
        status = "LEAKING" if value >= threshold else "NORMAL"
        return value, f"GAS,{value},{status}  [DEMO]"
