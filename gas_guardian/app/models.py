import re
from dataclasses import dataclass
from datetime import datetime


_GAS_PACKET = re.compile(
    r"^\s*(?:gas(?:\s+(?:level|value|reading))?)\s*[,=:]\s*"
    r"(\d{1,4})\s*(?:(?:[,;|]\s*|\s+)(?:status\s*[:=]\s*)?"
    r"(normal|safe|ok|leaking|alert|detected|danger))?\s*$",
    re.IGNORECASE,
)
_STATUS_ONLY_PACKET = re.compile(
    r"^(?:(?:gas|status)\s*[:,= -]?\s*)?"
    r"(normal|safe|ok|leaking|alert|detected|danger)$",
    re.IGNORECASE,
)
_NORMAL_STATUSES = {"NORMAL", "SAFE", "OK"}
_LEAK_STATUSES = {"LEAKING", "ALERT", "DETECTED", "DANGER"}


@dataclass(frozen=True)
class GasPacket:
    value: int | None
    firmware_status: str
    raw: str
    received_at: datetime


def parse_packet(line: str) -> GasPacket | None:
    """Parse supported gas telemetry formats and reject invalid readings."""
    raw = line.strip().lstrip("\ufeff").strip()
    status_match = _STATUS_ONLY_PACKET.fullmatch(raw)
    if status_match is not None:
        status_label = status_match.group(1).upper()
        firmware_status = "NORMAL" if status_label in _NORMAL_STATUSES else "LEAKING"
        return GasPacket(None, firmware_status, raw, datetime.now())
    match = _GAS_PACKET.fullmatch(raw)
    if match is None:
        return None
    try:
        value = int(match.group(1))
    except ValueError:
        return None
    if not 0 <= value <= 1023:
        return None
    status_label = (match.group(2) or "").upper()
    if status_label in _NORMAL_STATUSES:
        firmware_status = "NORMAL"
    elif status_label in _LEAK_STATUSES:
        firmware_status = "LEAKING"
    else:
        firmware_status = "UNKNOWN"
    return GasPacket(value, firmware_status, raw, datetime.now())
