import argparse
import csv
import email.message
import email.utils
import io
import json
import math
import mimetypes
import queue
import smtplib
import ssl
import threading
import time
from dataclasses import asdict
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from serial import Serial, SerialException
from serial.tools import list_ports
import keyring

from app.database import EventDatabase
from app.models import parse_packet
from app.settings import AppSettings, SettingsStore


class DashboardService:
    def __init__(self, project_dir: Path):
        self.project_dir = project_dir
        self.data_dir = project_dir / "data"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.settings_store = SettingsStore(self.data_dir / "settings.json")
        self.settings = self.settings_store.load()
        self.database = EventDatabase(self.data_dir / "gas_guardian.db")
        self.ports = self.available_ports()
        self.lock = threading.RLock()
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
        self.readings: list[dict] = []
        self.event_count = self.database.count_leakage_events()
        self.is_demo = False
        self.is_connected = False
        self.reader_thread: threading.Thread | None = None
        self.reader_stop: threading.Event | None = None
        self.pending_threshold: int | None = None
        self.demo_thread: threading.Thread | None = None
        self.demo_stop = threading.Event()
        self.demo_index = 0
        self.email_queue: queue.Queue[dict | None] = queue.Queue()
        self.keyring_available = True
        try:
            self.smtp_password_saved = keyring.get_password("Gas Guardian", "smtp-password") is not None
        except Exception:
            self.keyring_available = False
            self.smtp_password_saved = False
        self.email_thread = threading.Thread(target=self._send_email_queue, daemon=True)
        self.email_thread.start()
        self._monitor_stop = threading.Event()
        self._monitor_thread = threading.Thread(target=self._monitor, daemon=True)
        self._monitor_thread.start()

    @staticmethod
    def available_ports() -> list[str]:
        try:
            return sorted(port.device for port in list_ports.comports())
        except (OSError, SerialException):
            return []

    def refresh_ports(self) -> list[str]:
        self.ports = self.available_ports()
        return list(self.ports)

    def state(self) -> dict:
        with self.lock:
            history = [dict(row) for row in self.database.recent_events(12)]
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
                "readings": list(self.readings),
                "history": history,
                "ports": list(self.ports),
                "email_supported": True,
                "smtp_password_saved": self.smtp_password_saved,
                "keyring_available": self.keyring_available,
                "settings": asdict(self.settings),
            }

    def connect(self, port: str | None = None, baud_rate: int | None = None):
        if self.is_demo:
            self.stop_demo()
        with self.lock:
            if self.reader_thread is not None and self.reader_thread.is_alive():
                raise RuntimeError("A serial connection is already active")
            selected_port = (port or self.settings.port).strip()
            selected_baud = baud_rate or self.settings.baud_rate
            if selected_baud not in {9600, 19200, 38400, 57600, 115200}:
                raise ValueError("Unsupported baud rate")
            if not selected_port:
                raise ValueError("Select an Arduino COM port in Settings")
            self.settings.port = selected_port
            self.settings.baud_rate = selected_baud
            self.settings_store.save(self.settings)
            self._clear_reading_state()
            self.sensor_data_message = f"Opening {selected_port}..."
            self.ui_message = f"Opening {selected_port}..."
            self.ui_error = False
            stop_event = threading.Event()
            thread = threading.Thread(
                target=self._read_serial,
                args=(selected_port, selected_baud, stop_event),
                daemon=True,
            )
            self.reader_stop = stop_event
            self.reader_thread = thread
            thread.start()

    def disconnect(self):
        with self.lock:
            thread = self.reader_thread
            stop_event = self.reader_stop
        if stop_event is not None:
            stop_event.set()
        if thread is not None and thread is not threading.current_thread():
            thread.join(1.5)
        with self.lock:
            if self.reader_thread is thread:
                self.reader_thread = None
                self.reader_stop = None
            self.is_connected = False
            self.connected_at = None
            self._clear_reading_state()
            self.sensor_data_message = "No live hardware data"
            self.ui_message = "Disconnected"
            self.ui_error = False

    def toggle_demo(self):
        if self.is_demo:
            self.stop_demo()
            return
        self.disconnect()
        with self.lock:
            self.is_demo = True
            self.sensor_data_state = "demo"
            self.sensor_data_message = "Starting simulated readings"
            self.ui_message = "Demo mode active; readings are simulated"
            self.demo_stop = threading.Event()
            stop_event = self.demo_stop
            thread = threading.Thread(target=self._run_demo, args=(stop_event,), daemon=True)
            self.demo_thread = thread
            thread.start()

    def stop_demo(self):
        with self.lock:
            stop_event = self.demo_stop
            thread = self.demo_thread
            stop_event.set()
        if thread is not None and thread is not threading.current_thread():
            thread.join(1.0)
        with self.lock:
            self.is_demo = False
            self.demo_thread = None
            self._clear_reading_state()
            self.sensor_data_message = "No live hardware data"
            self.ui_message = "Demo mode stopped"

    def apply_settings(self, values: dict):
        if not isinstance(values, dict):
            raise ValueError("Settings payload must be an object")
        if "smtp_password" in values or "clear_smtp_password" in values:
            raise ValueError("SMTP credentials are configured securely with: python -m app.configure_email")
        try:
            threshold = max(0, min(1023, int(values.get("threshold", self.settings.threshold))))
            graph_duration = max(10, min(600, int(values.get("graph_duration", self.settings.graph_duration))))
            baud_rate = int(values.get("baud_rate", self.settings.baud_rate))
            smtp_port = int(values.get("smtp_port", self.settings.smtp_port))
        except (TypeError, ValueError) as exc:
            raise ValueError("Threshold, graph duration, baud rate, and SMTP port must be numbers") from exc
        if baud_rate not in {9600, 19200, 38400, 57600, 115200}:
            raise ValueError("Unsupported baud rate")
        if not 1 <= smtp_port <= 65535:
            raise ValueError("SMTP port must be between 1 and 65535")
        theme = values.get("theme", self.settings.theme)
        if theme not in {"Dark", "Light"}:
            theme = self.settings.theme
        port = str(values.get("port", self.settings.port)).strip() or self.settings.port
        pc_sound = values.get("pc_sound", self.settings.pc_sound)
        if not isinstance(pc_sound, bool):
            pc_sound = self.settings.pc_sound
        email_enabled = values.get("email_enabled", self.settings.email_enabled)
        if not isinstance(email_enabled, bool):
            email_enabled = self.settings.email_enabled
        smtp_security = values.get("smtp_security", self.settings.smtp_security)
        if smtp_security not in {"STARTTLS", "SSL/TLS", "None"}:
            smtp_security = self.settings.smtp_security
        account_email = self.settings.smtp_username or self.settings.smtp_sender
        settings = AppSettings(
            port=port,
            baud_rate=baud_rate,
            threshold=threshold,
            graph_duration=graph_duration,
            theme=theme,
            pc_sound=pc_sound,
            email_enabled=email_enabled,
            email_recipient=str(values.get("email_recipient", self.settings.email_recipient)).strip(),
            smtp_host=str(values.get("smtp_host", self.settings.smtp_host)).strip(),
            smtp_port=smtp_port,
            smtp_sender=account_email,
            smtp_username=account_email,
            smtp_security=smtp_security,
        )
        if settings.email_enabled:
            self._validate_email_settings(asdict(settings))
        self.settings_store.save(settings)
        with self.lock:
            self.settings = settings
            self.pending_threshold = threshold
            value = self.current_value
            status = self.current_status
            self.ui_message = "Settings saved"
            self.ui_error = False
        if value is not None:
            status = "LEAKING" if value >= threshold else "NORMAL"
            self._accept_reading(value, datetime.now(), f"GAS,{value},{status}", status, self.is_demo)
        elif status is not None:
            with self.lock:
                self.current_status = status

    def export_csv(self) -> bytes:
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow(("ID", "Timestamp", "Sensor", "Status", "Threshold"))
        for row in reversed(self.database.recent_events(100000)):
            writer.writerow((row["id"], row["timestamp"], row["sensor_value"], row["status"], row["threshold"]))
        return output.getvalue().encode("utf-8-sig")

    def test_email(self):
        with self.lock:
            settings = asdict(self.settings)
        self._validate_email_settings(settings)
        self.email_queue.put({"kind": "test", "settings": settings})
        with self.lock:
            self.ui_message = f"Test email queued for {settings['email_recipient']}"
            self.ui_error = False

    def _validate_email_settings(self, settings: dict):
        if not settings["smtp_host"]:
            raise ValueError("Enter an SMTP server host")
        for label, field in (("sender", "smtp_sender"), ("recipient", "email_recipient")):
            address = email.utils.parseaddr(settings[field])[1]
            if not address or address.count("@") != 1 or address.startswith("@") or address.endswith("@"):
                raise ValueError(f"Enter a valid email {label} address")
        if not self._get_smtp_password():
            raise ValueError("Save a Google app password with: python -m app.configure_email")

    def _get_smtp_password(self) -> str | None:
        if not self.keyring_available:
            raise RuntimeError("Windows Credential Manager is unavailable")
        try:
            password = keyring.get_password("Gas Guardian", "smtp-password")
        except Exception as exc:
            raise RuntimeError(f"Could not read the saved SMTP password: {exc}") from exc
        if password is None:
            return None
        password = "".join(password.split())
        if not password.isascii() or not password.isalnum() or len(password) != 16:
            raise ValueError(
                "The saved Gmail credential is not a valid 16-character app password. "
                "Replace it with: python -m app.configure_email"
            )
        return password

    def _send_email_queue(self):
        while True:
            job = self.email_queue.get()
            try:
                if job is None:
                    return
                self._deliver_email(job)
                with self.lock:
                    self.ui_message = (
                        f"Test email sent to {job['settings']['email_recipient']}"
                        if job["kind"] == "test"
                        else f"Leak alert email sent to {job['settings']['email_recipient']}"
                    )
                    self.ui_error = False
            except Exception as exc:
                with self.lock:
                    if isinstance(exc, smtplib.SMTPAuthenticationError):
                        self.ui_message = (
                            "Gmail rejected the saved password. Create a Google app password and replace it with: "
                            "python -m app.configure_email"
                        )
                    elif isinstance(exc, UnicodeEncodeError):
                        self.ui_message = (
                            "The saved Gmail credential contains unsupported characters. Replace it with a "
                            "16-character Google app password using: python -m app.configure_email"
                        )
                    else:
                        self.ui_message = f"Email delivery failed: {exc}"
                    self.ui_error = True
            finally:
                self.email_queue.task_done()

    def _deliver_email(self, job: dict):
        settings = job["settings"]
        self._validate_email_settings(settings)
        message = email.message.EmailMessage()
        message["From"] = settings["smtp_sender"]
        message["To"] = settings["email_recipient"]
        if job["kind"] == "test":
            message["Subject"] = "Gas Guardian email test"
            message.set_content(
                "This is a test message from Gas Guardian.\n\n"
                "If you received this email, mail delivery is configured. Leak alerts are sent when a live reading changes to LEAKING."
            )
        else:
            value = job["value"] if job["value"] is not None else "Not provided by firmware"
            message["Subject"] = "Gas Guardian: gas leakage alert"
            message.set_content(
                "Gas Guardian detected a live gas alert.\n\n"
                f"Status: LEAKING\nSensor reading: {value}\nThreshold: {job['threshold']}\n"
                f"Time: {job['timestamp']}\nSerial data: {job['raw']}\n\n"
                "This prototype monitor is not a certified safety device. Follow your site's safety procedures."
            )
        password = self._get_smtp_password() if settings["smtp_username"] else None
        context = ssl.create_default_context()
        if settings["smtp_security"] == "SSL/TLS":
            server = smtplib.SMTP_SSL(settings["smtp_host"], settings["smtp_port"], timeout=10, context=context)
        else:
            server = smtplib.SMTP(settings["smtp_host"], settings["smtp_port"], timeout=10)
        with server:
            server.ehlo()
            if settings["smtp_security"] == "STARTTLS":
                server.starttls(context=context)
                server.ehlo()
            if settings["smtp_username"]:
                server.login(settings["smtp_username"], password)
            server.send_message(message)

    def close(self):
        self.disconnect()
        self.stop_demo()
        self._monitor_stop.set()
        self._monitor_thread.join(1.0)
        self.email_queue.put(None)
        self.email_thread.join(1.0)

    def _read_serial(self, port: str, baud_rate: int, stop_event: threading.Event):
        connection = None
        try:
            connection = Serial(port, baud_rate, timeout=0.4, write_timeout=0.5)
            with self.lock:
                self.is_connected = True
                self.connected_at = time.monotonic()
                threshold = self.settings.threshold
                self.sensor_data_state = "waiting"
                self.sensor_data_message = f"PORT OPEN · waiting for GAS packets on {port}"
                self.ui_message = f"Connected to {port}"
                self.ui_error = False
            connection.write(f"THRESHOLD,{threshold}\n".encode("ascii"))
            last_data_at = time.monotonic()
            timeout_reported = False
            while not stop_event.is_set():
                with self.lock:
                    pending_threshold = self.pending_threshold
                    self.pending_threshold = None
                if pending_threshold is not None:
                    connection.write(f"THRESHOLD,{pending_threshold}\n".encode("ascii"))
                raw = connection.readline().decode("ascii", errors="replace").strip()
                if not raw:
                    if not timeout_reported and time.monotonic() - last_data_at >= 3:
                        self._set_sensor_state("stale", "NO SERIAL DATA · check firmware, baud rate, and wiring")
                        timeout_reported = True
                    continue
                last_data_at = time.monotonic()
                timeout_reported = False
                packet = parse_packet(raw)
                with self.lock:
                    self.latest_raw = raw
                if packet is None:
                    self._set_sensor_state(
                        "invalid",
                        f"SERIAL FORMAT ERROR · expected GAS,<value>,<status>; received {raw[:48]}",
                    )
                    continue
                with self.lock:
                    self.last_sensor_packet_at = time.monotonic()
                    threshold = self.settings.threshold
                status = packet.firmware_status if packet.value is None else (
                    "LEAKING" if packet.value >= threshold else "NORMAL"
                )
                self._accept_reading(packet.value, packet.received_at, packet.raw, status, False)
        except (SerialException, OSError, ValueError) as exc:
            if not stop_event.is_set():
                with self.lock:
                    self.ui_message = f"Could not read {port}: {exc}"
                    self.ui_error = True
                    self.sensor_data_state = "stale"
                    self.sensor_data_message = "SERIAL CONNECTION ERROR · check the selected port"
        finally:
            if connection is not None:
                try:
                    connection.close()
                except (SerialException, OSError):
                    pass
            with self.lock:
                self.is_connected = False
                self.connected_at = None
                if self.reader_thread is threading.current_thread():
                    self.reader_thread = None
                    self.reader_stop = None

    def _run_demo(self, stop_event: threading.Event):
        while not stop_event.is_set():
            with self.lock:
                if not self.is_demo:
                    return
                self.demo_index += 1
                baseline = 220 + int(22 * math.sin(self.demo_index / 8))
                alert_cycle = self.demo_index % 50 in range(20, 31)
                value = min(1023, baseline + (self.settings.threshold + 80 if alert_cycle else 0))
                threshold = self.settings.threshold
            status = "LEAKING" if value >= threshold else "NORMAL"
            self._accept_reading(value, datetime.now(), f"GAS,{value},{status}  [DEMO]", status, True)
            stop_event.wait(0.5)

    def _accept_reading(self, value: int | None, timestamp: datetime, raw: str, status: str, demo: bool):
        with self.lock:
            previous_status = self.current_status
            self.current_value = value
            self.current_status = status
            if value is not None:
                self.maximum_value = max(self.maximum_value, value)
                self.readings.append({"value": value, "time": timestamp.isoformat()})
                del self.readings[:-90]
            self.latest_raw = raw
            self.sensor_data_state = "demo" if demo else "live"
            self.last_received_at = timestamp
            source = "SIMULATED DEMO DATA · not from an MQ-3 sensor" if demo else (
                "LIVE STATUS ONLY · firmware sent no ADC value" if value is None else "LIVE SENSOR DATA"
            )
            self.sensor_data_message = f"{source} · updated {timestamp.astimezone().strftime('%H:%M:%S')}"
            changed = previous_status != status
            if not demo and changed and (previous_status is not None or status == "LEAKING"):
                try:
                    self.database.record_transition(timestamp, value, status, self.settings.threshold)
                    self.event_count = self.database.count_leakage_events()
                except (OSError, RuntimeError, ValueError):
                    self.ui_message = "Could not save event history"
                    self.ui_error = True
            if not demo and changed and status == "LEAKING" and self.settings.pc_sound:
                self.ui_message = "GAS ALERT · threshold reached"
            if not demo and changed and status == "LEAKING" and self.settings.email_enabled:
                self.email_queue.put({
                    "kind": "alert",
                    "settings": asdict(self.settings),
                    "value": value,
                    "threshold": self.settings.threshold,
                    "timestamp": timestamp.astimezone().strftime("%Y-%m-%d %H:%M:%S %Z"),
                    "raw": raw,
                })
                self.ui_message = "GAS ALERT · email notification queued"
            if not demo and changed and status != "LEAKING":
                self.ui_message = "Reading returned to normal"

    def _monitor(self):
        while not self._monitor_stop.wait(1.0):
            with self.lock:
                if not self.is_connected or self.is_demo:
                    continue
                reference = self.last_sensor_packet_at or self.connected_at
                if reference is None or time.monotonic() - reference < 3:
                    continue
                age = int(time.monotonic() - reference)
                self.sensor_data_state = "stale"
                self.sensor_data_message = (
                    "NO VALID GAS PACKETS · check firmware and baud rate"
                    if self.last_sensor_packet_at is None
                    else f"SENSOR DATA STALE · last valid reading {age}s ago"
                )

    def _set_sensor_state(self, state: str, message: str):
        with self.lock:
            self.sensor_data_state = state
            self.sensor_data_message = message

    def set_message(self, message: str, error: bool = False):
        with self.lock:
            self.ui_message = message
            self.ui_error = error

    def _clear_reading_state(self):
        self.current_value = None
        self.current_status = None
        self.last_received_at = None
        self.last_sensor_packet_at = None
        self.maximum_value = 0
        self.latest_raw = ""
        self.sensor_data_state = "waiting"
        self.readings.clear()


def make_handler(service: DashboardService, web_dir: Path):
    resolved_web_dir = web_dir.resolve()

    class DashboardHandler(BaseHTTPRequestHandler):
        server_version = "GasGuardianLocal/1.0"

        def log_message(self, format: str, *args):
            return

        def do_GET(self):
            path = urlsplit(self.path).path
            try:
                if path == "/api/state":
                    self._send_json(service.state())
                elif path == "/api/ports":
                    self._send_json({"ports": service.refresh_ports()})
                elif path == "/api/export.csv":
                    self._send_bytes(
                        service.export_csv(),
                        "text/csv; charset=utf-8",
                        'attachment; filename="gas_guardian_history.csv"',
                    )
                else:
                    self._serve_file(path)
            except (OSError, RuntimeError, ValueError) as exc:
                self._send_json({"error": str(exc)}, 500)

        def do_POST(self):
            path = urlsplit(self.path).path
            try:
                payload = self._read_json()
                if path == "/api/connect":
                    service.connect(payload.get("port"), payload.get("baud_rate"))
                elif path == "/api/disconnect":
                    service.disconnect()
                elif path == "/api/demo":
                    service.toggle_demo()
                elif path == "/api/settings":
                    service.apply_settings(payload)
                elif path == "/api/email/test":
                    service.test_email()
                else:
                    self._send_json({"error": "Not found"}, 404)
                    return
                self._send_json({"ok": True})
            except (TypeError, ValueError, RuntimeError) as exc:
                service.set_message(str(exc), error=True)
                self._send_json({"error": str(exc)}, 400)
            except (OSError, SerialException) as exc:
                service.set_message(str(exc), error=True)
                self._send_json({"error": str(exc)}, 500)

        def _read_json(self) -> dict:
            length = int(self.headers.get("Content-Length", "0"))
            if length > 32768:
                raise ValueError("Request is too large")
            if length == 0:
                return {}
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("Request body must be a JSON object")
            return payload

        def _serve_file(self, path: str):
            relative = "index.html" if path == "/" else path.lstrip("/")
            target = (resolved_web_dir / relative).resolve()
            if not target.is_relative_to(resolved_web_dir) or not target.is_file():
                self._send_json({"error": "Not found"}, 404)
                return
            content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            if target.suffix == ".js":
                content_type = "text/javascript; charset=utf-8"
            elif target.suffix == ".css":
                content_type = "text/css; charset=utf-8"
            self._send_bytes(target.read_bytes(), content_type)

        def _send_json(self, payload: dict, status: int = 200):
            self._send_bytes(json.dumps(payload).encode("utf-8"), "application/json; charset=utf-8", status=status)

        def _send_bytes(self, content: bytes, content_type: str, disposition: str | None = None, status: int = 200):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            if disposition:
                self.send_header("Content-Disposition", disposition)
            self.end_headers()
            self.wfile.write(content)

    return DashboardHandler


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Gas Guardian as a local web application")
    parser.add_argument("--port", type=int, default=8765, help="Local HTTP port (default: 8765)")
    parser.add_argument("--host", default="127.0.0.1", help="Address to listen on (default: 127.0.0.1)")
    args = parser.parse_args()
    project_dir = Path(__file__).resolve().parent.parent
    service = DashboardService(project_dir)
    server = ThreadingHTTPServer((args.host, args.port), make_handler(service, project_dir / "web"))
    server.daemon_threads = True
    if args.host == "0.0.0.0":
        print(f"Gas Guardian is listening on all network interfaces at port {args.port}")
        print(f"On this computer, open http://127.0.0.1:{args.port}")
        print(f"On your phone, open http://<this-computer-ip>:{args.port} on the same Wi-Fi network")
    else:
        print(f"Gas Guardian is running at http://{args.host}:{args.port}")
    print("Keep this window open while using the dashboard. Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Gas Guardian...")
    finally:
        server.server_close()
        service.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())