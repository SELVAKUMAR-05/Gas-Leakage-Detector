from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog, QHeaderView, QLabel, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QHBoxLayout, QWidget


class HistoryPage(QWidget):
    def __init__(self):
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 26, 28, 24)
        root.setSpacing(16)
        header = QHBoxLayout()
        title = QLabel("Event history")
        title.setObjectName("pageTitle")
        self.export_button = QPushButton("Export History")
        self.export_button.setObjectName("primaryButton")
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.setObjectName("quietButton")
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(self.refresh_button)
        header.addWidget(self.export_button)
        root.addLayout(header)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(("Timestamp", "Sensor", "Status", "Threshold"))
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in range(1, 4):
            self.table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.empty_label = QLabel("No state changes have been recorded yet.")
        self.empty_label.setObjectName("muted")
        root.addWidget(self.table, 1)
        root.addWidget(self.empty_label)
        self.export_button.clicked.connect(self._choose_export_path)
        self.export_requested = None

    def _choose_export_path(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export event history", "gas_guardian_history.csv", "CSV files (*.csv)")
        if path and self.export_requested is not None:
            self.export_requested(path)

    def populate(self, rows):
        self.table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            sensor_value = str(row["sensor_value"]) if row["sensor_value"] is not None else "N/A"
            values = (row["timestamp"].replace("T", " "), sensor_value, row["status"], str(row["threshold"]))
            for column_index, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column_index == 1 or column_index == 3:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                if column_index == 2:
                    item.setForeground(Qt.GlobalColor.red if value == "LEAKING" else Qt.GlobalColor.darkGreen)
                self.table.setItem(row_index, column_index, item)
        self.empty_label.setVisible(not rows)
