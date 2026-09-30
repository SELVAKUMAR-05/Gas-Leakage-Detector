from collections import deque
from datetime import datetime, timedelta

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure


class GasChart(FigureCanvasQTAgg):
    def __init__(self, duration_seconds: int = 90, parent=None):
        self.figure = Figure(figsize=(8, 3.4), dpi=100, tight_layout=True)
        self.axes = self.figure.add_subplot(111)
        super().__init__(self.figure)
        self.setParent(parent)
        self.duration_seconds = duration_seconds
        self.samples = deque()
        self.threshold = 400
        self.dark = True
        self._style()

    def _style(self, dark: bool | None = None):
        if dark is not None:
            self.dark = dark
        background = "#171d22" if self.dark else "#ffffff"
        foreground = "#d9e1e5" if self.dark else "#263238"
        self.figure.set_facecolor(background)
        self.axes.set_facecolor(background)
        self.axes.tick_params(colors=foreground, labelsize=8)
        for spine in self.axes.spines.values():
            spine.set_color("#39444b" if dark else "#d5dde1")
        self.axes.grid(color="#39444b" if dark else "#d5dde1", alpha=0.55, linewidth=0.6)
        self.axes.set_ylabel("Sensor value (0-1023)", color=foreground)
        self.axes.set_xlabel("Time", color=foreground)
        self.figure.tight_layout()

    def set_theme(self, dark: bool):
        self.dark = dark
        self.redraw()

    def set_duration(self, seconds: int):
        self.duration_seconds = seconds
        self.redraw()

    def set_threshold(self, threshold: int):
        self.threshold = threshold
        self.redraw()

    def add_reading(self, timestamp: datetime, value: int):
        self.samples.append((timestamp, value))
        self._prune(timestamp)
        self.redraw(timestamp)

    def _prune(self, now: datetime):
        cutoff = now - timedelta(seconds=self.duration_seconds)
        while self.samples and self.samples[0][0] < cutoff:
            self.samples.popleft()

    def redraw(self, now: datetime | None = None):
        if now is None:
            now = self.samples[-1][0] if self.samples else datetime.now()
        self._prune(now)
        self.axes.clear()
        self._style()
        if self.samples:
            times = [item[0] for item in self.samples]
            values = [item[1] for item in self.samples]
            self.axes.plot(times, values, color="#39c5a1", linewidth=1.8)
            self.axes.fill_between(times, values, color="#39c5a1", alpha=0.1)
            self.axes.set_xlim(now - timedelta(seconds=self.duration_seconds), now)
        else:
            self.axes.set_xlim(now - timedelta(seconds=self.duration_seconds), now)
            self.axes.text(0.5, 0.5, "Waiting for sensor data", ha="center", va="center", color="#91a0a8", transform=self.axes.transAxes)
        self.axes.axhline(self.threshold, color="#f06457", linestyle="--", linewidth=1.5, label=f"Threshold {self.threshold}")
        self.axes.set_ylim(0, 1023)
        self.axes.legend(loc="upper left", frameon=False, labelcolor="#d9e1e5", fontsize=8)
        self.draw_idle()
