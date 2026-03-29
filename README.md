# pico-cli: Raspberry Pi Pico W 2 Management Tool

A command-line tool that runs on your computer to set up and manage Raspberry Pi Pico W 2 transmitter devices. It communicates with Picos over USB serial and with your Django server over HTTP.

## Prerequisites

- Python 3.10 or higher
- A Raspberry Pi Pico W 2 connected via USB
- (Optional but recommended) `mpremote` for faster file transfers: `pip install mpremote`
- On Linux: add your user to the `dialout` group for serial port access:
  ```
  sudo usermod -a -G dialout $USER
  ```
  Then log out and back in.

## Installation

```bash
cd pico_cli
pip install .
```

Or for development (editable install):
```bash
pip install -e .
```

## Quick Start: Setting Up a New Pico

### Step 1: Flash MicroPython firmware

Download the MicroPython `.uf2` firmware for the Pico W 2 from https://micropython.org/download/ (look for "RPI_PICO2_W").

Put the Pico in BOOTSEL mode:
1. Unplug the Pico from USB.
2. Hold the BOOTSEL button (small white button on the board).
3. Plug the USB cable back in while holding the button.
4. Release the button.

Then flash:
```bash
pico-cli flash --uf2 RPI_PICO2_W-v1.24.1.uf2
```

### Step 2: Verify detection

```bash
pico-cli detect
```

You should see your Pico listed with its serial port (e.g., `/dev/ttyACM0`).

### Step 3: Upload application firmware

```bash
pico-cli upload --firmware-dir ./pico_firmware/
```

Or upload specific files:
```bash
pico-cli upload main.py boot.py lib/sensors.py
```

### Step 4: Provision WiFi and server config

```bash
pico-cli provision \
    --server-url https://your-server.com \
    --wifi-ssid "YourNetwork" \
    --wifi-pass "YourPassword"
```

### Step 5: Register on the server

```bash
pico-cli register \
    --api-url https://your-server.com \
    --username your_username \
    --password your_password \
    --name "Living Room Sensor"
```

Save the device token that is displayed. It is shown only once.

### Step 6: Identify (optional)

If you have multiple Picos, blink the LED to identify which is which:
```bash
pico-cli identify --port /dev/ttyACM0
```

## All Commands

| Command     | Description                                          |
|-------------|------------------------------------------------------|
| `detect`    | List connected Pico devices                          |
| `flash`     | Flash MicroPython firmware (.uf2) in BOOTSEL mode    |
| `upload`    | Upload .py files to the Pico's filesystem            |
| `provision` | Write WiFi and server config to secrets.json         |
| `register`  | Register the Pico on the Django server, get token    |
| `identify`  | Blink the LED for physical identification            |

Use `pico-cli <command> --help` for detailed options on each command.

## Troubleshooting

**"No Pico devices found"**
- Is the Pico plugged in via USB?
- Does it have MicroPython installed? Use `pico-cli flash` first.
- Is it in BOOTSEL mode? BOOTSEL shows as a USB drive, not a serial port.
- On Linux: `sudo usermod -a -G dialout $USER` and re-login.
- Try a different USB cable. Some cables are charge-only (no data).

**"Permission denied" on serial port**
- Linux: `sudo usermod -a -G dialout $USER` then log out and back in.
- macOS: Should work out of the box.
- Windows: Install the Raspberry Pi Pico driver if needed.

**"mpremote not found"**
- Install it: `pip install mpremote`
- The tool works without mpremote (uses serial fallback) but mpremote is faster.

**"Could not connect to server"**
- Check the URL (include https:// or http://).
- Make sure the Django server is running.
- Check your firewall and network connectivity.
