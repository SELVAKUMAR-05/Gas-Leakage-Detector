const node = (type, props, ...children) => React.createElement(type, props, ...children);
const navItems = [
  { id: "overview", label: "Overview", icon: "◫" },
  { id: "live", label: "Live monitor", icon: "⌁" },
  { id: "events", label: "Event history", icon: "▤" },
  { id: "settings", label: "Settings", icon: "⚙" },
];

function statusLabel(state) {
  if (state.demo) return "DEMO MODE";
  return state.connected ? "ARDUINO ONLINE" : "ARDUINO OFFLINE";
}

function displayTime(value) {
  if (!value) return "Waiting for first reading";
  return new Date(value).toLocaleString([], { dateStyle: "medium", timeStyle: "medium" });
}

function SensorChart({ readings, threshold, active }) {
  const values = readings.length ? readings : [{ value: 0 }, { value: 0 }];
  const points = values.map((reading, index) => {
    const x = values.length < 2 ? 20 : 20 + index / (values.length - 1) * 760;
    const y = 210 - Math.max(0, Math.min(1023, reading.value)) / 1023 * 190;
    return `${x},${y}`;
  }).join(" ");
  const latest = values[values.length - 1];
  const latestX = values.length < 2 ? 20 : 780;
  const latestY = 210 - Math.max(0, Math.min(1023, latest.value)) / 1023 * 190;
  const latestClass = latest.value >= threshold ? "chart-current-alert" : "";
  const thresholdY = 210 - threshold / 1023 * 190;
  return node("svg", { className: "sensor-chart", viewBox: "0 0 800 230", role: "img", "aria-label": "Recent gas sensor readings" },
    node("defs", null,
      node("linearGradient", { id: "reading-fill", x1: "0", x2: "0", y1: "0", y2: "1" },
        node("stop", { offset: "0%", stopColor: "#a5d86e", stopOpacity: ".28" }),
        node("stop", { offset: "100%", stopColor: "#a5d86e", stopOpacity: "0" })),
      node("linearGradient", { id: "reading-line", x1: "0", x2: "1", y1: "0", y2: "0" },
        node("stop", { offset: "0%", stopColor: "#75b846" }),
        node("stop", { offset: "100%", stopColor: "#c5df75" }))),
    [20, 70, 120, 170, 220].map((y) => node("line", { key: `grid-${y}`, className: "chart-grid", x1: "0", x2: "800", y1: y, y2: y })),
    node("line", { className: "chart-threshold", x1: "0", x2: "800", y1: thresholdY, y2: thresholdY }),
    node("polygon", { className: "chart-area", points: `0,220 ${points} 800,220` }),
    node("polyline", { className: "chart-line", points }),
    node("circle", { className: `chart-current-halo ${latestClass} ${active ? "is-active" : ""}`, cx: latestX, cy: latestY, r: "10" }),
    node("circle", { className: `chart-current ${latestClass}`, cx: latestX, cy: latestY, r: "4" }));
}

function Metric({ label, value, unit, tone }) {
  return node("div", { className: `metric metric-${tone}` },
    node("span", { className: "metric-label" }, label),
    node("strong", { className: "metric-value" }, value),
    node("span", { className: "metric-unit" }, unit));
}

function EmptyState({ children }) {
  return node("div", { className: "empty-state" }, children);
}

function App() {
  const [state, setState] = React.useState(null);
  const [startupError, setStartupError] = React.useState("");
  const [page, setPage] = React.useState("overview");
  const [bridge, setBridge] = React.useState(null);
  const [draft, setDraft] = React.useState(null);
  const [dirty, setDirty] = React.useState(false);

  React.useEffect(() => {
    let mounted = true;
    let timer = null;
    async function refresh() {
      try {
        const response = await fetch("/api/state", { cache: "no-store" });
        const nextState = await response.json();
        if (!response.ok) throw new Error(nextState.error || "Local service request failed");
        if (mounted) {
          setState(nextState);
          setStartupError("");
        }
      } catch (error) {
        if (mounted && !state) setStartupError(error.message);
      }
    }
    async function post(path, payload = {}) {
      const response = await fetch(path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "Local service request failed");
      return result;
    }
    function act(path, payload) {
      post(path, payload).then(refresh).catch((error) => {
        if (mounted) setState((previous) => previous ? { ...previous, message: error.message, message_error: true } : previous);
      });
    }
    const httpBridge = {
      connect_hardware: () => act("/api/connect"),
      disconnect_hardware: () => act("/api/disconnect"),
      toggle_demo: () => act("/api/demo"),
      test_email: () => act("/api/email/test"),
      apply_settings: (payload) => {
        try {
          act("/api/settings", JSON.parse(payload));
        } catch (error) {
          setState((previous) => previous ? { ...previous, message: error.message, message_error: true } : previous);
        }
      },
      refresh_history: refresh,
      refresh_ports: () => fetch("/api/ports", { cache: "no-store" }).then(refresh).catch(refresh),
      export_history: () => window.location.assign("/api/export.csv"),
    };
    function connectQtBridge() {
      if (!window.qt || !window.qt.webChannelTransport || !window.QWebChannel) return false;
      new window.QWebChannel(window.qt.webChannelTransport, (channel) => {
        if (!mounted) return;
        const api = channel.objects.bridge;
        setBridge(api);
        const poll = () => api.get_state((serialized) => {
          if (mounted) setState(JSON.parse(serialized));
        });
        poll();
        timer = window.setInterval(poll, 600);
      });
      return true;
    }
    if (window.qt && window.qt.webChannelTransport) {
      if (!connectQtBridge()) {
        const script = document.createElement("script");
        script.src = "qrc:///qtwebchannel/qwebchannel.js";
        script.onload = connectQtBridge;
        document.head.appendChild(script);
      }
    } else {
      setBridge(httpBridge);
      refresh();
      timer = window.setInterval(refresh, 600);
    }
    return () => {
      mounted = false;
      if (timer !== null) window.clearInterval(timer);
    };
  }, []);

  React.useEffect(() => {
    if (state && !dirty) setDraft({ ...state.settings });
  }, [state, dirty]);

  React.useEffect(() => {
    window.setGasGuardianPage = setPage;
  }, []);

  if (!state) return node("div", { className: "boot-screen" }, startupError
    ? `Local dashboard service unavailable: ${startupError}`
    : "Connecting to local sensor service...");

  const value = state.value;
  const percent = value === null ? 0 : value / 1023 * 100;
  const leaking = state.status === "LEAKING" || (value !== null && value >= state.threshold);
  const readingHeadline = value === null
    ? state.status === "LEAKING" ? "Gas leak reported by Arduino" : state.status === "NORMAL" ? "Arduino reports normal status" : "Awaiting signal"
    : state.demo ? leaking ? "Simulated alert scenario" : "Simulated normal reading"
      : leaking ? "Gas threshold exceeded" : "Reading within range";
  const readings = state.readings.slice(-60);
  const connectionText = statusLabel(state);
  const shownHistory = state.history || [];

  function updateDraft(key, nextValue) {
    setDirty(true);
    setDraft((previous) => ({ ...previous, [key]: nextValue }));
  }

  function saveSettings(event) {
    event.preventDefault();
    bridge.apply_settings(JSON.stringify(draft));
    setDirty(false);
  }

  function renderReadings() {
    return readings.length ? node(SensorChart, { readings, threshold: state.threshold, active: state.sensor_state === "live" || state.demo })
      : node(EmptyState, null, "Sensor readings will appear here when data arrives.");
  }

  function renderOverview() {
    const heading = node("div", { className: "page-heading" },
      node("div", null, node("p", { className: "eyebrow" }, "MONITORING / OVERVIEW"), node("h1", null, "System overview")),
      node("div", { className: `connection-pill ${state.demo ? "is-demo" : state.connected ? "is-online" : "is-offline"}` },
        node("span", { className: "connection-dot" }), connectionText));
    const hero = node("section", { className: `hero-status ${leaking ? "is-alert" : ""}` },
        node("div", { className: "hero-copy" },
          node("p", { className: "eyebrow" }, "CURRENT SENSOR STATE"),
          node("h2", null, readingHeadline),
          node("p", { className: "hero-subtitle" }, state.sensor_message),
          node("div", { className: "hero-actions" },
            state.connected ? node("button", { className: "button button-dark", onClick: () => bridge.disconnect_hardware() }, "Disconnect")
              : node("button", { className: "button button-dark", onClick: () => bridge.connect_hardware(), disabled: state.demo }, "Connect Arduino"),
            node("button", { className: "button button-quiet", onClick: () => bridge.toggle_demo() }, state.demo ? "Stop demo" : "Try demo"))),
        node("div", { className: "gauge-wrap" },
          node("div", { className: `gauge ${leaking ? "gauge-alert" : ""}`, style: { "--gauge-angle": `${percent * 3.6}deg` } },
            node("div", { className: "gauge-center" },
              node("strong", null, value === null ? "--" : value),
              node("span", null, "ADC / 1023"))),
          node("span", { className: "gauge-caption" }, `${percent.toFixed(1)}% of input range`)));
    const metrics = node("section", { className: "metrics-row" },
        node(Metric, { label: "Session high", value: state.maximum === 0 && value === null ? "--" : state.maximum, unit: "ADC units", tone: "blue" }),
        node(Metric, { label: "Alert threshold", value: state.threshold, unit: "ADC units", tone: "amber" }),
        node(Metric, { label: "Stored leak events", value: state.event_count, unit: "saved history", tone: "red" }),
        node(Metric, { label: "Last update", value: state.updated ? new Date(state.updated).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "--:--", unit: "local time", tone: "green" }));
    const trend = node("article", { className: "panel chart-panel" },
          node("div", { className: "panel-heading" }, node("div", null, node("p", { className: "eyebrow" }, state.demo ? "DEMO SIMULATION" : "LIVE TELEMETRY"), node("h3", null, state.demo ? "Simulated gas level" : "Gas level trend")), node("span", { className: "chart-unit" }, "0–1023 ADC")),
          renderReadings(),
          node("div", { className: "chart-legend" }, node("span", null, "Sensor reading"), node("span", { className: "legend-threshold" }, `Threshold · ${state.threshold}`)));
    const outputs = node("article", { className: "panel device-panel" },
          node("div", { className: "panel-heading" }, node("div", null, node("p", { className: "eyebrow" }, state.demo ? "SIMULATION" : "CONTROLLER"), node("h3", null, state.demo ? "Virtual output state" : "Output status"))),
          node("div", { className: "output-row" }, node("span", { className: "output-icon output-red" }, "R"), node("span", null, "Red warning LED"), node("strong", { className: !state.demo && leaking ? "output-on" : "" }, state.demo ? "SIM" : leaking ? "ON" : "OFF")),
          node("div", { className: "output-row" }, node("span", { className: "output-icon output-green" }, "G"), node("span", null, "Green status LED"), node("strong", { className: !state.demo && value !== null && !leaking ? "output-on" : "" }, state.demo ? "SIM" : value !== null && !leaking ? "ON" : "OFF")),
          node("div", { className: "output-row" }, node("span", { className: "output-icon output-amber" }, "!"), node("span", null, "Buzzer"), node("strong", { className: !state.demo && leaking ? "output-on" : "" }, state.demo ? "SIM" : leaking ? "ON" : "OFF")),
          state.demo ? node("p", { className: "helper-note demo-note" }, "No MQ-3 sensor or Arduino is being read in demo mode.") : null,
          node("div", { className: "serial-block" }, node("span", { className: "eyebrow" }, state.demo ? "DEMO SAMPLE · NOT SERIAL" : "LATEST SERIAL LINE"), node("code", null, state.raw || "No serial data received")));
    const content = node("section", { className: "content-grid" }, trend, outputs);
    const historyNote = state.demo && state.event_count > 0
      ? node("div", { className: "history-note" }, "This saved event count may include demo runs from an earlier version. It is history, not a current gas alarm.")
      : null;
    const toast = state.message ? node("div", { className: `toast ${state.message_error ? "toast-error" : ""}` }, state.message) : null;
    return node(React.Fragment, null, heading, hero, metrics, content, historyNote, toast);
  }

  function renderLive() {
    return node("div", null,
      node("div", { className: "page-heading" }, node("div", null, node("p", { className: "eyebrow" }, "MONITORING / LIVE"), node("h1", null, "Live monitor")),
        node("span", { className: "muted-note" }, state.sensor_message)),
      node("section", { className: "panel live-panel" }, node("div", { className: "panel-heading" }, node("div", null, node("p", { className: "eyebrow" }, state.demo ? "DEMO SIMULATION" : "ROLLING SENSOR HISTORY"), node("h3", null, state.demo ? "Simulated values" : "Recent gas level")), node("span", { className: "chart-unit" }, `${readings.length} samples`)), renderReadings()),
      node("section", { className: "panel serial-panel" }, node("div", { className: "panel-heading" }, node("div", null, node("p", { className: "eyebrow" }, state.demo ? "NO USB INPUT" : "USB SERIAL"), node("h3", null, state.demo ? "Demo output" : "Incoming data"))),
        node("div", { className: `serial-state serial-${state.sensor_state}` }, state.sensor_message), node("pre", { className: "serial-raw" }, state.raw || "No serial data received"),
        node("p", { className: "helper-note" }, state.demo ? "This sample is generated by the app and is not read from a COM port." : "The app accepts GAS,value,status packets and common labeled gas-reading lines. Other text is shown here and ignored as sensor input.")));
  }

  function renderEvents() {
    return node("div", null,
      node("div", { className: "page-heading" }, node("div", null, node("p", { className: "eyebrow" }, "LOCAL DATABASE"), node("h1", null, "Event history")),
        node("div", { className: "event-actions" }, node("button", { className: "button button-light", onClick: () => bridge.refresh_history() }, "Refresh"), node("button", { className: "button button-accent", onClick: () => bridge.export_history() }, "Export CSV"))),
      node("section", { className: "panel history-panel" },
        shownHistory.length ? node("table", null,
          node("thead", null, node("tr", null, ["Timestamp", "Sensor", "State", "Threshold"].map((heading) => node("th", { key: heading }, heading)))),
          node("tbody", null, shownHistory.map((row) => node("tr", { key: row.id },
            node("td", null, new Date(row.timestamp).toLocaleString()), node("td", null, row.sensor_value ?? "N/A"), node("td", null, node("span", { className: `table-status ${row.status === "LEAKING" ? "status-alert" : "status-normal"}` }, row.status)), node("td", null, row.threshold)))))
          : node(EmptyState, null, "No sensor state changes have been stored yet.")));
  }

  function renderSettings() {
    if (!draft) return node(EmptyState, null, "Loading settings...");
    const ports = Array.from(new Set([...(state.ports || []), draft.port].filter(Boolean)));
    const mailRecipient = draft.email_recipient.trim();
    const mailSubject = encodeURIComponent("Gas Guardian sensor update");
    const mailBody = encodeURIComponent(
      `Current status: ${state.status || "No sensor status"}\n` +
      `Sensor reading: ${state.value ?? "No ADC reading"}\n` +
      `Alert threshold: ${state.threshold}\n` +
      `Updated: ${state.updated || "No reading received"}`
    );
    const mailtoHref = mailRecipient
      ? `mailto:${encodeURIComponent(mailRecipient).replace(/%40/gi, "@")}?subject=${mailSubject}&body=${mailBody}`
      : undefined;
    const mailSettings = state.email_supported ? node("section", { className: "mail-settings" },
      node("div", { className: "panel-heading mail-heading" },
        node("div", null, node("p", { className: "eyebrow" }, "ALERT DELIVERY"), node("h3", null, "Email notifications")),
        node("span", { className: `mail-credential ${state.keyring_available ? "" : "mail-credential-error"}` },
          state.keyring_available ? state.smtp_password_saved ? "PASSWORD SAVED SECURELY" : "PASSWORD NOT SET" : "CREDENTIAL STORE UNAVAILABLE")),
      node("div", { className: "settings-grid" },
        node("label", { className: "toggle-setting" }, node("input", { type: "checkbox", checked: draft.email_enabled, onChange: (event) => updateDraft("email_enabled", event.target.checked) }), node("span", null, "Email me when a live gas alert begins")),
        node("label", null, "Alert recipient", node("input", { type: "email", value: draft.email_recipient, onChange: (event) => updateDraft("email_recipient", event.target.value), placeholder: "safety@example.com" })),
        node("p", { className: "mail-account-status" }, state.smtp_password_saved ? "Sending credentials are stored securely." : "Sending credentials are not configured.")),
      node("div", { className: "mail-actions" },
        node("div", null,
          node("p", { className: "helper-note" }, state.keyring_available ? "SMTP credentials are kept in Windows Credential Manager. Configure or replace the Gmail app password once from the project folder with: python -m app.configure_email" : "Windows Credential Manager is unavailable; email credentials cannot be stored securely."),
          state.message && /email|smtp|credential/i.test(state.message) ? node("p", { className: `mail-feedback ${state.message_error ? "mail-feedback-error" : ""}`, role: "status" }, state.message) : null),
        node("div", { className: "mail-actions-buttons" },
          node("a", { className: "button button-accent", href: mailtoHref, "aria-disabled": !mailRecipient }, "Open email draft"),
          node("button", { className: "button button-light", type: "button", onClick: () => bridge.test_email(), disabled: !state.keyring_available }, "Send test email")))) : null;
    return node("div", null,
      node("div", { className: "page-heading" }, node("div", null, node("p", { className: "eyebrow" }, "DEVICE CONFIGURATION"), node("h1", null, "Settings"))),
      node("form", { className: "panel settings-form", onSubmit: saveSettings },
        node("div", { className: "settings-grid" },
          node("label", null, "Arduino COM port", node("span", { className: "input-with-action" }, node("input", { list: "serial-ports", value: draft.port, onChange: (event) => updateDraft("port", event.target.value), placeholder: "COM5" }), node("datalist", { id: "serial-ports" }, ports.map((port) => node("option", { key: port, value: port }))), node("button", { className: "icon-button", type: "button", title: "Refresh ports", onClick: () => bridge.refresh_ports() }, "↻"))),
          node("label", null, "Baud rate", node("select", { value: draft.baud_rate, onChange: (event) => updateDraft("baud_rate", Number(event.target.value)) }, [9600, 19200, 38400, 57600, 115200].map((rate) => node("option", { key: rate, value: rate }, rate)))),
          node("label", null, "Alert threshold", node("input", { type: "number", min: 0, max: 1023, value: draft.threshold, onChange: (event) => updateDraft("threshold", Number(event.target.value)) })),
          node("label", null, "Graph time window", node("div", { className: "input-suffix" }, node("input", { type: "number", min: 10, max: 600, value: draft.graph_duration, onChange: (event) => updateDraft("graph_duration", Number(event.target.value)) }), node("span", null, "sec"))),
          node("label", null, "Color theme", node("select", { value: draft.theme, onChange: (event) => updateDraft("theme", event.target.value) }, ["Dark", "Light"].map((theme) => node("option", { key: theme }, theme)))),
          node("label", { className: "toggle-setting" }, node("input", { type: "checkbox", checked: draft.pc_sound, onChange: (event) => updateDraft("pc_sound", event.target.checked) }), node("span", null, "Play a PC alert sound on a new leak event"))),
        mailSettings,
        node("div", { className: "settings-footer" }, node("p", { className: "helper-note" }, "Settings are saved locally and the threshold is sent to the Arduino."), node("button", { className: "button button-accent", type: "submit" }, "Save settings"))),
      node("p", { className: "safety-note" }, "Prototype monitor only. MQ-series sensor readings are not calibrated gas concentrations and are not a substitute for certified safety equipment."));
  }

  function renderAbout() {
    return node("div", null,
      node("div", { className: "page-heading" }, node("div", null, node("p", { className: "eyebrow" }, "GAS GUARDIAN"), node("h1", null, "About this monitor"))),
      node("section", { className: "panel about-panel" }, node("h3", null, "Local-first gas monitoring"),
        node("p", null, "Gas Guardian reads an MQ-series analog sensor through an Arduino UNO over USB serial. Readings are evaluated against a configurable threshold, while state transitions are stored in a local SQLite database."),
        node("p", null, "Firmware connection: sensor AO to A0; red LED on D2; green LED on D3; buzzer on D4. Default serial speed: 9600 baud."),
        node("p", { className: "safety-note" }, "This prototype is not a certified safety device. Do not use it as a replacement for certified gas detectors, ventilation, or site procedures.")));
  }

  const pageRenderers = { overview: renderOverview, live: renderLive, events: renderEvents, settings: renderSettings, about: renderAbout };
  return node("div", { className: `application-shell ${state.settings.theme === "Light" ? "theme-light" : ""}` },
    node("aside", { className: "sidebar" },
      node("div", { className: "brand" }, node("span", { className: "brand-mark" }, node("span", null), node("span", null), node("span", null), node("span", null)), node("div", null, node("strong", null, "GAS GUARDIAN"), node("small", null, "SENSOR CONTROL"))),
      node("div", { className: "nav-caption" }, "WORKSPACE"),
      node("nav", null, navItems.map((item) => node("button", { key: item.id, className: `nav-item ${page === item.id ? "nav-active" : ""}`, onClick: () => setPage(item.id) }, node("span", { className: "nav-icon" }, item.icon), item.label))),
      node("button", { className: `nav-item about-link ${page === "about" ? "nav-active" : ""}`, onClick: () => setPage("about") }, node("span", { className: "nav-icon" }, "i"), "About"),
      node("div", { className: "sidebar-bottom" }, node("span", { className: "sidebar-light" }), node("span", null, state.demo ? "SIMULATION ACTIVE" : state.connected ? `LINKED · ${state.port}` : "LOCAL SYSTEM"), node("small", null, "Sensor data stays on this device"))),
    node("main", { className: "main-area" },
      node("header", { className: "topbar" }, node("div", { className: "breadcrumb" }, "Gas Guardian", node("span", null, "/"), page === "overview" ? "Overview" : navItems.find((item) => item.id === page)?.label || "About"),
        node("div", { className: "topbar-right" }, node("span", { className: `topbar-indicator ${state.connected || state.demo ? "indicator-live" : ""}` }), node("span", null, connectionText))),
      node("div", { className: "page-content" }, (pageRenderers[page] || renderOverview)())));
}

ReactDOM.createRoot(document.getElementById("root")).render(node(App));