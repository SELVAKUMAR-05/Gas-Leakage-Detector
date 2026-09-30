# GAS GUARDIAN

**Real-Time Arduino Gas Leakage Monitoring System** is a local browser dashboard for an Arduino UNO and an MQ-series analog gas sensor. Run the Python service and open it at `http://127.0.0.1:8765`; no cloud account is needed. The dashboard runs locally, and outbound network access is used only if optional SMTP email alerts are enabled.

> **Safety:** This system is a prototype monitoring system. MQ-series sensor readings are not calibrated gas concentration measurements and should not be treated as a certified safety device. Do not rely on it as a replacement for certified gas detectors, ventilation, or site safety procedures.

## Features

- Responsive React dashboard served locally in a browser, with dark and light themes.
- USB serial monitoring in a background Python thread (default 9600 baud).
- Automatic serial-port discovery, editable COM selector, and COM5 default.
- Configurable threshold synchronized to the Arduino firmware.
- Live 0-1023 gauge, percentage, rolling graph, and threshold marker.
- State-transition event history in SQLite and CSV export.
- Optional SMTP email alerts on a new live leakage event, with a configurable recipient and a test-email action.
- Manual email drafts for the configured recipient via the computer's default mail app, without SMTP credentials.
- Optional local PC alert sound; this does not replace the physical Arduino buzzer.
- Clearly labeled Demo Mode for interface testing without hardware. Demo readings are never presented as hardware readings.
- Locally vendored React runtime; no Node.js, npm, or cloud account is required. Internet access is only needed for optional SMTP email alerts.
- Local JSON settings; sensor readings and history stay on this device.

## Hardware

- Arduino UNO
- MQ-3 gas sensor module with analog output (AO)
- Red LED and suitable series resistor (typically 220-330 ohms)
- Green LED and suitable series resistor (typically 220-330 ohms)
- Buzzer compatible with the Arduino output pin
- 128x64 SSD1306 SPI OLED display (7-pin module)
- USB cable
- Breadboard and jumper wires

### Wiring

| Component | Arduino UNO |
| --- | --- |
| MQ-3 AO | A0 |
| MQ-3 VCC | 5V |
| MQ-3 GND | GND |
| Red LED anode through resistor | D2 |
| Green LED anode through resistor | D3 |
| LED cathodes | GND |
| Buzzer signal / positive | D4 |
| Buzzer ground / negative | GND |
| OLED GND | GND |
| OLED VCC | 3.3V or 5V, according to the module rating |
| OLED D0 (SCK / clock) | D13 (SCK) |
| OLED D1 (MOSI / data) | D11 (MOSI) |
| OLED RES | D9 |
| OLED DC | D8 |
| OLED CS | D10 |

Use a shared ground. OLED modules vary: check the board's supply-voltage and logic-level requirements before wiring it. Check the MQ module and buzzer voltage/current requirements before connecting them. Do not drive a load that exceeds an Arduino pin's limits; use a suitable transistor driver for a higher-current buzzer. The MQ sensor requires warm-up and appropriate calibration for meaningful measurements.

## Arduino Setup

1. Install and open the Arduino IDE.
2. In Library Manager, install **Adafruit SSD1306** and **Adafruit GFX Library**.
3. Open `arduino/gas_detector.ino`.
4. Select **Arduino UNO** and the board's port under **Tools**.
5. Upload the sketch.
6. The OLED first shows **GAS GUARDIAN / OLED READY**, then the live gas reading, alarm state, and threshold. Open the Serial Monitor at **9600 baud** to check for lines such as `GAS,235,NORMAL`. Close the Serial Monitor before connecting the desktop application because only one program can normally own the port at a time.

The firmware transmits `GAS,<value>,<status>` every 500 ms. The application can also send `THRESHOLD,<value>` so the firmware's LEDs and buzzer use the same threshold selected in the UI.

## Python Installation

Python 3.11 or later is required. From the directory containing this README, create and activate an environment:

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

To install packages on other platforms, activate `.venv` using that platform's command, then run `python -m pip install -r requirements.txt`.

## Find the COM Port

On Windows, open **Device Manager → Ports (COM & LPT)** after plugging in the UNO. The port appears as a device such as `Arduino Uno (COM5)`. The app scans available ports when it starts and has a **Refresh ports** button in Settings. COM5 remains selectable as a default even when no Arduino is connected; the application does not permanently hard-code the port.

## Run as a Local Website

From the project directory, start the local service:

```powershell
python -m app.web_server
```

Open `http://127.0.0.1:8765` in a browser. Keep the terminal window open while using the dashboard; press **Ctrl+C** there to stop the service. To use another local port, run `python -m app.web_server --port 8080` and open `http://127.0.0.1:8080`.

The service binds only to `127.0.0.1` by default, so it is available on this computer and is not exposed to your network. To open the dashboard on a phone, connect the phone and computer to the same trusted Wi-Fi network, then run:

```powershell
python -m app.web_server --host 0.0.0.0
```

Find the computer's IPv4 address with `ipconfig` and open `http://<computer-ip>:8765` on the phone (for example, `http://192.168.1.20:8765`). Allow Python through Windows Firewall on **Private networks** if prompted. The phone layout is provided by the same dashboard; keep the service running on the computer while using it.

**Network security:** The local HTTP service has no login and is not encrypted. Anyone who can reach it on the network can view sensor data and use dashboard controls, including connecting or disconnecting hardware and changing settings. Use this only on a trusted private network, stop it when finished, and never port-forward it or expose it to the internet. The default localhost-only mode remains the safer choice when phone access is not needed.

Connect the Arduino from the dashboard's **Connect Arduino** button after choosing its port in Settings. Close Arduino Serial Monitor first. Do not run the desktop and localhost versions against the same Arduino simultaneously, because the COM port can only be owned by one process at a time.

### Email Alerts

In **Settings → Email notifications**, enter the alert recipient and enable email notifications. The sender account is preconfigured. Gmail does not accept a regular account password for this SMTP login; create a Google app password, then run `python -m app.configure_email` from the project folder to store it securely in Windows Credential Manager. This is a one-time credential setup, not a Settings field, and the password is never sent through the dashboard or written to `data/settings.json`. Use **Send test email** to verify delivery. Alerts are sent automatically when a live hardware reading transitions to `LEAKING`; demo readings do not send alerts. Gmail uses `smtp.gmail.com`, port `587`, and `STARTTLS`. Email is supplementary and is not an emergency notification or a replacement for certified alarms.

To compose an email without configuring an SMTP sender, set the recipient and choose **Open email draft**. Gas Guardian opens the default email application with the current sensor snapshot filled in; review and send it there. This is manual and does not send automatic alerts.

## Run the Desktop Version

From the project directory with the virtual environment active:

```powershell
python main.py
```

Use **Settings** to choose the COM port and baud rate (9600 by default), then select **Live Monitor → Connect**. To explore the dashboard without hardware, select **Start Demo Mode** in Live Monitor. The page and readings are explicitly marked as simulated. Stop Demo Mode before connecting to an Arduino.

Change the threshold in Settings and choose **Save settings**. The new value is persisted locally and sent to connected firmware. The live graph keeps the configured 10-600 second window. In Event History, use **Export History** to save a CSV file.

## Local Files

- `data/settings.json` - saved port, baud, threshold, graph window, theme, sound, and non-secret email settings.
- Windows Credential Manager - SMTP password used by localhost email alerts.
- `data/gas_guardian.db` - locally stored state-transition events.
- `exports/` - suggested location for exported CSV files.

These are created or populated locally when the app runs. Sensor readings are not sent off-device unless optional email alerts are enabled; then alert details are sent to the configured email recipient through the selected SMTP provider.

## Troubleshooting

- **OLED stays dark:** Confirm the 7-pin OLED is wired as listed above: D0 to D13, D1 to D11, RES to D9, DC to D8, and CS to D10. Check VCC and GND against the module rating, then upload the sketch again. Verify that the module uses the SSD1306 controller; SPI displays do not provide an I2C address scan or acknowledge signal.
- **Port is missing:** Check the USB cable, install the board's USB driver if needed, then refresh ports. Some USB cables are charge-only.
- **Access denied / port busy:** Close Arduino Serial Monitor, other serial terminals, or any second Gas Guardian instance. Unplug and reconnect the board if the port remains locked.
- **Could not open COM port:** Confirm the selected port in Device Manager and retry. The app remains open when a port is unavailable.
- **No readings:** Confirm the sketch is uploaded, the Serial Monitor is closed, baud is 9600, and AO is connected to A0. Check sensor power and allow the sensor to warm up.
- **Unrecognized serial data:** Check the raw line shown in Live Monitor. The included sketch sends `GAS,<value>,NORMAL` or `GAS,<value>,LEAKING`; upload `arduino/gas_detector.ino` and set the app baud rate to match the sketch. Boot messages and unrelated text are displayed but ignored. The parser tolerates case, extra whitespace, a UTF-8 BOM, and common `Gas Level: <value>` formats.
- **Firmware sends only `NORMAL` or `GAS LEAKING`:** The app shows the firmware-reported alarm status, but leaves the ADC gauge blank because no numeric sensor value was transmitted. Upload the included sketch to get numeric readings and keep the configured threshold synchronized.
- **Threshold/output mismatch:** Save the new threshold while connected. The application sends `THRESHOLD,<value>` to the included firmware. Firmware not using this sketch may ignore that command and keep its own output threshold.
- **Database cannot be written:** Ensure the project directory is writable. Event history and CSV export need access to the local `data/` and destination folders.
- **Demo values appear:** Stop Demo Mode and connect a serial port; demo readings are labeled in the live page and raw message.

## Architecture

```text
MQ-series sensor -> Arduino UNO firmware -> USB serial (9600 baud)
    -> SerialWorker (QThread, timeout-based reads)
    -> tolerant, range-checked gas packet parser
    -> threshold-derived application state
         -> state transitions -> SQLite database -> CSV export
         -> local HTTP API -> React dashboard in the browser
```

The localhost service reads serial data in a background Python thread; HTTP requests never block on serial reads. The desktop version retains its Qt worker. Both use the same parser, SQLite event store, and JSON settings under `data/`. The parser rejects malformed packets and values outside 0-1023. The configured threshold determines the displayed application status, and the same threshold is sent back to the included firmware for physical LED/buzzer behavior. SQLite records only state changes, rather than every sensor sample.

The React interface and React 18 production runtime are served from local files in `web/`; no JavaScript package installation or network access is needed.

## Project Layout

```text
gas_guardian/
├── main.py
├── requirements.txt
├── README.md
├── arduino/
│   └── gas_detector.ino
├── app/
│   ├── main_window.py
│   ├── web_server.py
│   ├── react_page.py
│   ├── serial_manager.py
│   ├── database.py
│   ├── models.py
│   ├── settings.py
│   ├── charts.py
│   └── widgets/
│       ├── dashboard.py
│       ├── live_monitor.py
│       ├── history.py
│       └── settings_page.py
├── web/
│   ├── app.js
│   ├── index.html
│   ├── styles.css
│   ├── react.production.min.js
│   ├── react-dom.production.min.js
│   └── LICENSE.react
├── data/
└── exports/
```
