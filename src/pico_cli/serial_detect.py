"""
serial_detect.py -- Detect Raspberry Pi Pico W 2 devices connected via USB
==========================================================================

HOW USB DEVICE DETECTION WORKS
------------------------------
Every USB device in the world has two important numbers baked into it:

  - Vendor ID (VID): Identifies the manufacturer. Raspberry Pi Foundation's VID is 0x2E8A.
  - Product ID (PID): Identifies the specific product from that manufacturer.

When you plug a Pico into your computer via USB, your operating system sees these
numbers and knows what kind of device it is. We use this to filter out all the other
serial devices (Bluetooth adapters, GPS modules, Arduinos, etc.) and find only Picos.

PICO USB MODES
--------------
The Pico can appear as two different types of USB device:

  1. BOOTSEL mode (PID 0x0003 / 0x0005 depending on variant):
     - The Pico shows up as a USB mass storage drive (like a flash drive).
     - This is the mode you use to install MicroPython firmware (.uf2 files).
     - You enter BOOTSEL by holding the BOOTSEL button while plugging in USB.
     - In this mode, there is NO serial port -- it is just a drive.

  2. Normal mode (PID 0x0005 for RP2040, 0x000A for RP2350 / Pico W 2):
     - After MicroPython is installed, the Pico shows up as a USB serial device.
     - This is the mode you use for everything else: uploading code, provisioning, etc.
     - The serial port is typically /dev/ttyACM0 on Linux, COM3+ on Windows.

WHAT pyserial DOES FOR US
--------------------------
The `serial.tools.list_ports` module scans your operating system for all connected
serial ports and returns details about each one, including VID and PID. We just
filter that list to find Raspberry Pi Picos.
"""

import platform
from pathlib import Path

import serial.tools.list_ports

# Raspberry Pi Foundation USB Vendor ID.
# Every Raspberry Pi product (including Pico) uses this VID.
RASPBERRY_PI_VID = 0x2E8A

# Product IDs for different Pico variants in serial (normal) mode.
# When MicroPython is running, the Pico presents itself as a CDC serial device
# with one of these PIDs depending on the chip variant.
PICO_SERIAL_PIDS = {
    0x0005,  # RP2040-based Pico / Pico W (original)
    0x000A,  # RP2350-based Pico 2 / Pico W 2 (newer)
    0x0009,  # RP2350 RISC-V variant
}

# In BOOTSEL mode the Pico appears as a USB mass-storage device, not a serial
# port -- it never shows up via pyserial. We find those by scanning the OS's
# mount points for a drive named RPI-RP2 / RP2350 with an INFO_UF2.TXT in it.
BOOTSEL_DRIVE_NAMES = {"RPI-RP2", "RP2350"}


def _read_info_uf2(mount_path):
    """
    Parse INFO_UF2.TXT from a BOOTSEL mount. Pico writes useful identification
    here -- Model and Board-ID lines are the most useful. Returns a dict like
    {"model": "...", "board_id": "..."}; missing fields are absent.
    """
    info = {}
    try:
        text = (Path(mount_path) / "INFO_UF2.TXT").read_text(errors="ignore")
    except OSError:
        return info
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip().lower()
        value = value.strip()
        if key == "model":
            info["model"] = value
        elif key == "board-id":
            info["board_id"] = value
    return info


def list_bootsel_picos():
    """
    Find every Pico currently in BOOTSEL mode (unflashed / firmware-update
    mode) by scanning for the mounted USB mass-storage drives Pico exposes
    in that state.

    Returns a list of dicts with:
      - state:      always "unflashed"
      - mount_path: filesystem path to the mounted drive
      - model:      e.g. "Raspberry Pi RP2350" (from INFO_UF2.TXT, if readable)
      - board_id:   e.g. "RPI-RP2350"          (from INFO_UF2.TXT, if readable)
    """
    system = platform.system()
    candidates = []

    if system == "Linux":
        # Auto-mounted under /media/<user>/ or /run/media/<user>/ depending on DE.
        for base in (Path("/media"), Path("/run/media")):
            if not base.exists():
                continue
            for user_dir in base.iterdir():
                if not user_dir.is_dir():
                    continue
                for name in BOOTSEL_DRIVE_NAMES:
                    candidates.append(user_dir / name)
    elif system == "Darwin":
        for name in BOOTSEL_DRIVE_NAMES:
            candidates.append(Path("/Volumes") / name)
    elif system == "Windows":
        import string

        for letter in string.ascii_uppercase:
            candidates.append(Path(f"{letter}:\\"))

    found = []
    for candidate in candidates:
        if not candidate.is_dir():
            continue
        if not (candidate / "INFO_UF2.TXT").exists():
            continue
        info = _read_info_uf2(candidate)
        found.append(
            {
                "state": "unflashed",
                "mount_path": str(candidate),
                "model": info.get("model", "Raspberry Pi Pico (BOOTSEL)"),
                "board_id": info.get("board_id", "unknown"),
            }
        )
    return found


def list_all_picos():
    """
    One-stop scan: returns both flashed Picos (running MicroPython, exposed
    as USB serial) and unflashed Picos (in BOOTSEL mode, mounted as mass
    storage).

    Each entry has a "state" key: "flashed" or "unflashed". Other keys vary
    by state -- flashed entries have a "port" + "serial", unflashed entries
    have a "mount_path" + "board_id".
    """
    flashed = [{**p, "state": "flashed"} for p in list_pico_serial_ports()]
    return flashed + list_bootsel_picos()


def list_pico_serial_ports():
    """
    Scan all USB serial ports and return only those that belong to a Raspberry Pi Pico.

    Returns a list of dicts, each containing:
      - port:        The OS device path, e.g. "/dev/ttyACM0" or "COM3"
      - description: Human-readable description from the OS
      - vid:         USB Vendor ID  (will always be 0x2E8A for Pico)
      - pid:         USB Product ID (tells us which Pico variant)
      - serial:      USB serial number string (unique per device)
    """
    picos = []

    # serial.tools.list_ports.comports() returns an iterable of ListPortInfo objects.
    # Each object has attributes: device, description, hwid, vid, pid, serial_number, etc.
    for port_info in serial.tools.list_ports.comports():
        # Filter: only keep ports whose VID matches Raspberry Pi
        # and whose PID is one of the known Pico serial-mode PIDs.
        if port_info.vid == RASPBERRY_PI_VID and port_info.pid in PICO_SERIAL_PIDS:
            picos.append(
                {
                    "port": port_info.device,
                    "description": port_info.description,
                    "vid": port_info.vid,
                    "pid": port_info.pid,
                    "serial": port_info.serial_number or "unknown",
                }
            )

    return picos


def get_single_pico_port(preferred_port=None):
    """
    Convenience function: return exactly one Pico serial port path.

    If `preferred_port` is given (e.g. the user typed --port /dev/ttyACM0),
    verify it is actually a Pico and return it.

    If no preference, auto-detect. If exactly one Pico is found, return it.
    If zero or multiple are found, raise an error with helpful guidance.
    """
    picos = list_pico_serial_ports()

    # If the user specified a port, validate it
    if preferred_port:
        for p in picos:
            if p["port"] == preferred_port:
                return preferred_port
        # The port exists but might not be a Pico, or might not be connected
        raise RuntimeError(
            f"Port {preferred_port} was specified but no Pico was detected on it.\n"
            f"Make sure the Pico is plugged in and MicroPython is installed.\n"
            f"Detected Pico ports: {[p['port'] for p in picos] or 'none'}"
        )

    # Auto-detect
    if len(picos) == 0:
        raise RuntimeError(
            "No Raspberry Pi Pico detected on any USB serial port.\n"
            "\n"
            "Troubleshooting:\n"
            "  1. Is the Pico plugged into your computer via USB?\n"
            "  2. Does it have MicroPython installed? (If not, use 'pico-cli flash' first)\n"
            "  3. Is it in BOOTSEL mode? (BOOTSEL won't show a serial port)\n"
            "  4. On Linux, do you have permission? Try: sudo usermod -a -G dialout $USER\n"
            "     then log out and back in."
        )

    if len(picos) == 1:
        return picos[0]["port"]

    # Multiple Picos found -- the user needs to specify which one
    port_list = "\n".join(f"  {p['port']}  (serial: {p['serial']})" for p in picos)
    raise RuntimeError(
        f"Multiple Picos detected. Please specify which one with --port:\n"
        f"{port_list}\n"
        f"\n"
        f"Tip: use 'pico-cli identify --port /dev/ttyACMx' to blink the LED\n"
        f"on a specific Pico so you can tell them apart physically."
    )
