from PySide6.QtCore import Signal
from PySide6.QtWidgets import QCheckBox, QComboBox, QFormLayout, QFrame, QHBoxLayout, QLabel, QPushButton, QSpinBox, QVBoxLayout, QWidget

from app.settings import AppSettings


class SettingsPage(QWidget):
    settings_applied = Signal(object)

    def __init__(self, settings: AppSettings, ports: list[str]):
        super().__init__()
        self.settings = settings
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 26, 28, 24)
        root.setSpacing(18)
        title = QLabel("Settings")
        title.setObjectName("pageTitle")
        root.addWidget(title)
        panel = QFrame()
        panel.setObjectName("panel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(22, 20, 22, 20)
        form = QFormLayout()
        form.setHorizontalSpacing(28)
        form.setVerticalSpacing(16)
        self.port = QComboBox()
        self.port.setEditable(True)
        for port in sorted(set(ports + [settings.port, "COM5"])):
            self.port.addItem(port)
        self.port.setCurrentText(settings.port)
        self.refresh_ports_button = QPushButton("Refresh ports")
        port_wrap = QHBoxLayout()
        port_wrap.addWidget(self.port, 1)
        port_wrap.addWidget(self.refresh_ports_button)
        port_container = QWidget()
        port_container.setLayout(port_wrap)
        self.baud = QComboBox()
        for baud in (9600, 19200, 38400, 57600, 115200):
            self.baud.addItem(str(baud), baud)
        self.baud.setCurrentIndex(max(0, self.baud.findData(settings.baud_rate)))
        self.threshold = QSpinBox()
        self.threshold.setRange(0, 1023)
        self.threshold.setValue(settings.threshold)
        self.duration = QSpinBox()
        self.duration.setRange(10, 600)
        self.duration.setSuffix(" seconds")
        self.duration.setValue(settings.graph_duration)
        self.theme = QComboBox()
        self.theme.addItems(("Dark", "Light"))
        self.theme.setCurrentText(settings.theme)
        form.addRow("Arduino COM port", port_container)
        form.addRow("Baud rate", self.baud)
        form.addRow("Gas alert threshold", self.threshold)
        form.addRow("Graph time window", self.duration)
        form.addRow("Application theme", self.theme)
        layout.addLayout(form)
        self.pc_sound = QCheckBox("Play a PC alert sound when the state changes to leaking")
        self.pc_sound.setChecked(settings.pc_sound)
        layout.addWidget(self.pc_sound)
        self.apply_button = QPushButton("Save settings")
        self.apply_button.setObjectName("primaryButton")
        self.saved_label = QLabel("")
        self.saved_label.setObjectName("muted")
        buttons = QHBoxLayout()
        buttons.addWidget(self.apply_button)
        buttons.addWidget(self.saved_label)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        root.addWidget(panel)
        disclaimer = QLabel("This system is a prototype monitoring system. MQ-series sensor readings are not calibrated gas concentration measurements and should not be treated as a certified safety device.")
        disclaimer.setObjectName("disclaimer")
        disclaimer.setWordWrap(True)
        root.addWidget(disclaimer)
        root.addStretch(1)
        self.apply_button.clicked.connect(self._apply)
        self.refresh_ports_button.clicked.connect(self.refresh_ports)

    def refresh_ports(self, ports: list[str] | None = None):
        current = self.port.currentText().strip()
        if ports is None:
            from app.serial_manager import SerialManager
            ports = SerialManager.available_ports()
        self.port.clear()
        for port in sorted(set(ports + [current, "COM5"])):
            if port:
                self.port.addItem(port)
        self.port.setCurrentText(current)

    def _apply(self):
        settings = AppSettings(
            port=self.port.currentText().strip() or "COM5",
            baud_rate=int(self.baud.currentData()),
            threshold=self.threshold.value(),
            graph_duration=self.duration.value(),
            theme=self.theme.currentText(),
            pc_sound=self.pc_sound.isChecked(),
            email_enabled=self.settings.email_enabled,
            email_recipient=self.settings.email_recipient,
            smtp_host=self.settings.smtp_host,
            smtp_port=self.settings.smtp_port,
            smtp_sender=self.settings.smtp_sender,
            smtp_username=self.settings.smtp_username,
            smtp_security=self.settings.smtp_security,
        )
        self.settings = settings
        self.saved_label.setText("Saved")
        self.settings_applied.emit(settings)
