from datetime import datetime

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt
from PySide6.QtWidgets import QFrame, QGraphicsOpacityEffect, QGridLayout, QLabel, QProgressBar, QVBoxLayout, QWidget


class MetricCard(QFrame):
    def __init__(self, title: str, value: str = "--", subtitle: str = "", kind: str = "default"):
        super().__init__()
        self.setObjectName("metricCard")
        self.setProperty("kind", kind)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        title_label = QLabel(title.upper())
        title_label.setObjectName("eyebrow")
        self.value_label = QLabel(value)
        self.value_label.setObjectName("metricValue")
        self.subtitle_label = QLabel(subtitle)
        self.subtitle_label.setObjectName("muted")
        layout.addWidget(title_label)
        layout.addWidget(self.value_label)
        layout.addWidget(self.subtitle_label)
        layout.addStretch(1)

    def set_value(self, value: str, subtitle: str | None = None):
        self.value_label.setText(value)
        if subtitle is not None:
            self.subtitle_label.setText(subtitle)


class DashboardPage(QWidget):
    def __init__(self):
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 26, 28, 24)
        root.setSpacing(18)
        title = QLabel("System overview")
        title.setObjectName("pageTitle")
        self.connection_label = QLabel("Arduino disconnected")
        self.connection_label.setObjectName("connectionBadge")
        self.connection_label.setProperty("state", "disconnected")
        header = QGridLayout()
        header.addWidget(title, 0, 0)
        header.addWidget(self.connection_label, 0, 1, Qt.AlignmentFlag.AlignRight)
        root.addLayout(header)
        self.sensor_data_label = QLabel("No sensor data yet")
        self.sensor_data_label.setObjectName("sensorDataLabel")
        self.sensor_data_label.setProperty("state", "waiting")
        self.sensor_data_label.setWordWrap(True)
        root.addWidget(self.sensor_data_label)

        self.alert = QFrame()
        self.alert.setObjectName("statusBanner")
        self.alert.setProperty("state", "normal")
        alert_layout = QVBoxLayout(self.alert)
        alert_layout.setContentsMargins(22, 17, 22, 17)
        self.status_title = QLabel("NORMAL")
        self.status_title.setObjectName("statusTitle")
        self.status_description = QLabel("No elevated gas reading detected")
        self.status_description.setObjectName("statusDescription")
        alert_layout.addWidget(self.status_title)
        alert_layout.addWidget(self.status_description)
        self.alert_effect = QGraphicsOpacityEffect(self.alert)
        self.alert_effect.setOpacity(1.0)
        self.alert.setGraphicsEffect(self.alert_effect)
        self.alert_animation = QPropertyAnimation(self.alert_effect, b"opacity", self)
        self.alert_animation.setDuration(260)
        self.alert_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        root.addWidget(self.alert)

        grid = QGridLayout()
        grid.setSpacing(14)
        self.current_card = MetricCard("Gas level", "--", "0 / 1023", "level")
        self.maximum_card = MetricCard("Session maximum", "--", "since application start", "maximum")
        self.threshold_card = MetricCard("Alert threshold", "400", "analog sensor units", "threshold")
        self.events_card = MetricCard("Leakage events", "0", "recorded state changes", "events")
        grid.addWidget(self.current_card, 0, 0)
        grid.addWidget(self.maximum_card, 0, 1)
        grid.addWidget(self.threshold_card, 0, 2)
        grid.addWidget(self.events_card, 0, 3)
        root.addLayout(grid)

        lower = QGridLayout()
        lower.setSpacing(14)
        level_frame = QFrame()
        level_frame.setObjectName("panel")
        level_layout = QVBoxLayout(level_frame)
        level_layout.setContentsMargins(20, 17, 20, 18)
        level_heading = QLabel("Live gas level")
        level_heading.setObjectName("sectionTitle")
        self.level_text = QLabel("Waiting for sensor data")
        self.level_text.setObjectName("levelText")
        self.gauge = QProgressBar()
        self.gauge.setRange(0, 1023)
        self.gauge.setValue(0)
        self.gauge.setTextVisible(False)
        self.gauge.setFixedHeight(12)
        self.gauge_animation = QPropertyAnimation(self.gauge, b"value", self)
        self.gauge_animation.setDuration(420)
        self.gauge_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.percent_label = QLabel("--% of ADC range")
        self.percent_label.setObjectName("muted")
        level_layout.addWidget(level_heading)
        level_layout.addSpacing(12)
        level_layout.addWidget(self.level_text)
        level_layout.addWidget(self.gauge)
        level_layout.addWidget(self.percent_label)

        outputs_frame = QFrame()
        outputs_frame.setObjectName("panel")
        outputs_layout = QVBoxLayout(outputs_frame)
        outputs_layout.setContentsMargins(20, 17, 20, 18)
        outputs_layout.addWidget(QLabel("Arduino outputs"))
        self.red_led = QLabel("●  Red LED     OFF")
        self.green_led = QLabel("●  Green LED   OFF")
        self.buzzer = QLabel("●  Buzzer       OFF")
        for label, device in ((self.red_led, "red"), (self.green_led, "green"), (self.buzzer, "buzzer")):
            label.setObjectName("outputState")
            label.setProperty("device", device)
            label.setProperty("state", "off")
            outputs_layout.addWidget(label)
        outputs_layout.addStretch(1)
        lower.addWidget(level_frame, 0, 0, 1, 2)
        lower.addWidget(outputs_frame, 0, 2, 1, 2)
        root.addLayout(lower)

        self.updated_label = QLabel("Last update: --")
        self.updated_label.setObjectName("muted")
        root.addWidget(self.updated_label)
        root.addStretch(1)

    def update_reading(self, value: int, status: str, threshold: int, maximum: int, event_count: int, timestamp: datetime, demo: bool = False):
        leaking = status == "LEAKING"
        state = "leaking" if leaking else "normal"
        state_changed = self.alert.property("state") != state
        self.status_title.setText("GAS LEAKING" if leaking else "NORMAL")
        self.status_description.setText("Threshold reached. Check the area and follow site safety procedures." if leaking else "No elevated gas reading detected")
        self.alert.setProperty("state", state)
        self.alert.style().unpolish(self.alert)
        self.alert.style().polish(self.alert)
        if state_changed:
            self.alert_animation.stop()
            self.alert_animation.setStartValue(0.78)
            self.alert_animation.setEndValue(1.0)
            self.alert_animation.start()
        self.current_card.set_value(str(value), f"{value} / 1023  ·  {value / 1023 * 100:.1f}%")
        self.maximum_card.set_value(str(maximum), "since application start")
        self.threshold_card.set_value(str(threshold), "analog sensor units")
        self.events_card.set_value(str(event_count), "recorded leakage entries")
        self.level_text.setText(f"{value} / 1023")
        self.gauge_animation.stop()
        self.gauge_animation.setStartValue(self.gauge.value())
        self.gauge_animation.setEndValue(value)
        self.gauge_animation.start()
        self.gauge.setProperty("state", "leaking" if leaking else "normal")
        self.gauge.style().unpolish(self.gauge)
        self.gauge.style().polish(self.gauge)
        self.percent_label.setText(f"{value / 1023 * 100:.1f}% of ADC range")
        red_on = leaking
        green_on = not leaking
        self.red_led.setText(f"●  Red LED     {'ON' if red_on else 'OFF'}")
        self.green_led.setText(f"●  Green LED   {'ON' if green_on else 'OFF'}")
        self.buzzer.setText(f"●  Buzzer       {'ON' if leaking else 'OFF'}")
        self._set_output_state(self.red_led, red_on)
        self._set_output_state(self.green_led, green_on)
        self._set_output_state(self.buzzer, leaking)
        self.updated_label.setText(f"Last update: {timestamp.astimezone().strftime('%Y-%m-%d  %H:%M:%S')}")
        if demo:
            self.set_sensor_data_state("demo", f"DEMO SIMULATION  ·  updated {timestamp.astimezone().strftime('%H:%M:%S')}")
        else:
            self.set_sensor_data_state("live", f"LIVE SENSOR DATA  ·  updated {timestamp.astimezone().strftime('%H:%M:%S')}")

    @staticmethod
    def _set_output_state(label: QLabel, active: bool):
        label.setProperty("state", "on" if active else "off")
        label.style().unpolish(label)
        label.style().polish(label)

    def set_connection(self, connected: bool, detail: str = ""):
        self.connection_label.setText(f"Arduino connected · {detail}" if connected else "Arduino disconnected")
        self.connection_label.setProperty("state", "connected" if connected else "disconnected")
        self.connection_label.style().unpolish(self.connection_label)
        self.connection_label.style().polish(self.connection_label)
        if connected:
            self.set_sensor_data_state("waiting", "PORT OPEN  ·  waiting for valid GAS packets")
        else:
            self.set_sensor_data_state("waiting", "No live hardware data")

    def set_sensor_data_state(self, state: str, message: str):
        self.sensor_data_label.setText(message)
        self.sensor_data_label.setProperty("state", state)
        self.sensor_data_label.style().unpolish(self.sensor_data_label)
        self.sensor_data_label.style().polish(self.sensor_data_label)

    def set_demo(self, enabled: bool):
        if enabled:
            self.connection_label.setText("DEMO MODE · simulated data")
            self.connection_label.setProperty("state", "demo")
            self.connection_label.style().unpolish(self.connection_label)
            self.connection_label.style().polish(self.connection_label)
