import threading
import time

from PySide6.QtCore import QThread, Signal
from serial import Serial, SerialException
from serial.tools import list_ports

from app.models import GasPacket, parse_packet


class SerialWorker(QThread):
    connection_changed = Signal(bool, str)
    packet_received = Signal(object)
    raw_received = Signal(str)
    error_occurred = Signal(str)

    def __init__(self, port: str, baud_rate: int, threshold: int):
        super().__init__()
        self.port = port
        self.baud_rate = baud_rate
        self._threshold = threshold
        self._threshold_lock = threading.Lock()
        self._stop_requested = threading.Event()

    @staticmethod
    def available_ports() -> list[str]:
        try:
            return sorted(port.device for port in list_ports.comports())
        except (OSError, SerialException):
            return []

    def request_stop(self):
        self._stop_requested.set()

    def set_threshold(self, threshold: int):
        with self._threshold_lock:
            self._threshold = threshold

    def run(self):
        serial_connection = None
        try:
            serial_connection = Serial(self.port, self.baud_rate, timeout=0.4, write_timeout=0.5)
            last_data_at = time.monotonic()
            timeout_reported = False
            with self._threshold_lock:
                threshold = self._threshold
            serial_connection.write(f"THRESHOLD,{threshold}\n".encode("ascii"))
            self.connection_changed.emit(True, self.port)
            while not self._stop_requested.is_set():
                with self._threshold_lock:
                    threshold = self._threshold
                    self._threshold = None
                if threshold is not None:
                    serial_connection.write(f"THRESHOLD,{threshold}\n".encode("ascii"))
                try:
                    line = serial_connection.readline().decode("ascii", errors="replace").strip()
                except SerialException as exc:
                    raise SerialException(f"Serial read failed: {exc}") from exc
                if not line:
                    if not timeout_reported and time.monotonic() - last_data_at >= 3:
                        self.error_occurred.emit("No serial data received for 3 seconds; check the board and USB connection.")
                        timeout_reported = True
                    continue
                last_data_at = time.monotonic()
                timeout_reported = False
                self.raw_received.emit(line)
                packet: GasPacket | None = parse_packet(line)
                if packet is not None:
                    self.packet_received.emit(packet)
        except (SerialException, OSError, ValueError) as exc:
            if not self._stop_requested.is_set():
                self.error_occurred.emit(f"Could not read {self.port}: {exc}")
        finally:
            if serial_connection is not None:
                try:
                    serial_connection.close()
                except (SerialException, OSError):
                    pass
            self.connection_changed.emit(False, self.port)


class SerialManager:
    """Small owner for a single serial worker; all reads happen off the GUI thread."""

    def __init__(self):
        self.worker: SerialWorker | None = None

    @staticmethod
    def available_ports() -> list[str]:
        return SerialWorker.available_ports()

    def connect(self, port: str, baud_rate: int, threshold: int, start: bool = True) -> SerialWorker:
        if self.worker is not None and self.worker.isRunning():
            raise RuntimeError("A serial connection is already active")
        self.worker = SerialWorker(port, baud_rate, threshold)
        if start:
            self.worker.start()
        return self.worker

    def disconnect(self):
        worker = self.worker
        if worker is not None and worker.isRunning():
            worker.request_stop()
            worker.wait(1500)
        self.worker = None
