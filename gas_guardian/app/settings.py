import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class AppSettings:
    port: str = "COM5"
    baud_rate: int = 9600
    threshold: int = 400
    graph_duration: int = 90
    theme: str = "Dark"
    pc_sound: bool = True
    email_enabled: bool = False
    email_recipient: str = ""
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_sender: str = ""
    smtp_username: str = ""
    smtp_security: str = "STARTTLS"


class SettingsStore:
    def __init__(self, path: Path):
        self.path = path

    def load(self) -> AppSettings:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            return AppSettings(
                port=str(raw.get("port", "COM5")),
                baud_rate=self._bounded_int(raw.get("baud_rate"), 9600, {9600, 19200, 38400, 57600, 115200}),
                threshold=self._bounded_int(raw.get("threshold"), 400, range(0, 1024)),
                graph_duration=self._bounded_int(raw.get("graph_duration"), 90, range(10, 601)),
                theme=raw.get("theme") if raw.get("theme") in {"Dark", "Light"} else "Dark",
                pc_sound=raw.get("pc_sound") if isinstance(raw.get("pc_sound"), bool) else True,
                email_enabled=raw.get("email_enabled") if isinstance(raw.get("email_enabled"), bool) else False,
                email_recipient=str(raw.get("email_recipient") or ""),
                smtp_host=str(raw.get("smtp_host") or "smtp.gmail.com"),
                smtp_port=self._bounded_int(raw.get("smtp_port"), 587, range(1, 65536)),
                smtp_sender=str(raw.get("smtp_sender") or ""),
                smtp_username=str(raw.get("smtp_username") or ""),
                smtp_security=raw.get("smtp_security") if raw.get("smtp_security") in {"STARTTLS", "SSL/TLS", "None"} else "STARTTLS",
            )
        except (OSError, ValueError, TypeError, AttributeError):
            return AppSettings()

    def save(self, settings: AppSettings) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(asdict(settings), indent=2), encoding="utf-8")
        temporary.replace(self.path)

    @staticmethod
    def _bounded_int(value, default: int, allowed) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return default
        return parsed if parsed in allowed else default
