"""
flash.py -- Flash MicroPython firmware (.uf2) onto a Raspberry Pi Pico
======================================================================

WHAT IS FIRMWARE?
-----------------
"Firmware" is the base software that runs on a microcontroller. Think of it like
the operating system on your computer. Without firmware, the Pico is a blank chip
that cannot do anything.

We use MicroPython as our firmware. MicroPython is a tiny version of Python that
runs directly on microcontrollers. Once MicroPython is installed, you can write
Python scripts and the Pico will execute them.

WHAT IS A .uf2 FILE?
---------------------
UF2 stands for "USB Flashing Format". It is a special file format designed by
Microsoft for flashing microcontrollers. The key insight is:

  A .uf2 file can be flashed by simply copying it to a USB drive.

No special programmer hardware needed. No complex flashing software. Just drag
and drop (or cp on the command line).

HOW BOOTSEL MODE WORKS
-----------------------
BOOTSEL = "Boot Select". The Pico has a physical button labeled BOOTSEL on the board.

  1. Unplug the Pico from USB.
  2. Hold down the BOOTSEL button (it is a small white button on the board).
  3. While holding BOOTSEL, plug the USB cable back in.
  4. Release the BOOTSEL button.

Now the Pico appears as a USB mass storage device -- just like a flash drive!
It will show up as a drive called "RPI-RP2" (for original Pico) or "RP2350"
(for Pico 2 / Pico W 2).

The drive is tiny (only a few hundred KB) and contains two files:
  - INFO_UF2.TXT  (information about the bootloader)
  - INDEX.HTM     (a redirect to the Raspberry Pi documentation)

To flash new firmware, you just copy a .uf2 file onto this drive. The Pico
detects the new file, writes it to its internal flash memory, and automatically
reboots. After reboot, the Pico is no longer a USB drive -- it is now running
whatever firmware was in the .uf2 file.

AFTER FLASHING
--------------
Once MicroPython is flashed, the Pico reboots and appears as a USB serial device.
You can then connect to it via serial port (e.g. /dev/ttyACM0) and type Python
commands interactively, or upload .py files for it to run.
"""

import platform
import shutil
import time
from pathlib import Path


# Known mount point names for Pico in BOOTSEL mode.
# These are the "drive names" that appear when the Pico is in BOOTSEL.
BOOTSEL_DRIVE_NAMES = {"RPI-RP2", "RP2350"}


def find_bootsel_drive():
    """
    Look for a Pico in BOOTSEL mode by searching for its USB mass storage mount point.

    On Linux:   typically mounted at /media/<username>/RPI-RP2 or /run/media/...
    On macOS:   typically mounted at /Volumes/RPI-RP2
    On Windows: appears as a new drive letter like E:\\

    Returns the path to the mounted drive, or None if not found.
    """
    system = platform.system()

    if system == "Linux":
        # On Linux, removable drives are usually auto-mounted under /media/<user>/
        # or /run/media/<user>/ depending on the desktop environment.
        search_dirs = []

        # Check /media/<username>/
        media_path = Path("/media")
        if media_path.exists():
            for user_dir in media_path.iterdir():
                if user_dir.is_dir():
                    search_dirs.append(user_dir)

        # Check /run/media/<username>/
        run_media_path = Path("/run/media")
        if run_media_path.exists():
            for user_dir in run_media_path.iterdir():
                if user_dir.is_dir():
                    search_dirs.append(user_dir)

        for search_dir in search_dirs:
            for drive_name in BOOTSEL_DRIVE_NAMES:
                candidate = search_dir / drive_name
                if candidate.is_dir() and (candidate / "INFO_UF2.TXT").exists():
                    return str(candidate)

    elif system == "Darwin":
        # macOS mounts volumes under /Volumes/
        for drive_name in BOOTSEL_DRIVE_NAMES:
            candidate = Path("/Volumes") / drive_name
            if candidate.is_dir() and (candidate / "INFO_UF2.TXT").exists():
                return str(candidate)

    elif system == "Windows":
        # On Windows, check all drive letters for the BOOTSEL drive.
        # The drive will have INFO_UF2.TXT in its root.
        import string

        for letter in string.ascii_uppercase:
            candidate = Path(f"{letter}:\\")
            if candidate.exists() and (candidate / "INFO_UF2.TXT").exists():
                return str(candidate)

    return None


def read_bootsel_info(drive_path):
    """
    Read the INFO_UF2.TXT file on the BOOTSEL drive to get board information.

    This file contains lines like:
      UF2 Bootloader v1.0
      Model: Raspberry Pi RP2350
      Board-ID: RPI-RP2350
    """
    info_file = Path(drive_path) / "INFO_UF2.TXT"
    if info_file.exists():
        return info_file.read_text()
    return "INFO_UF2.TXT not found"


def flash_uf2(uf2_path, drive_path=None):
    """
    Flash a .uf2 firmware file to a Pico in BOOTSEL mode.

    This is literally just copying a file to a USB drive. That is all flashing is!
    The Pico's bootloader detects the .uf2 file, writes it to internal flash,
    and reboots automatically.

    Parameters:
        uf2_path:   Path to the .uf2 firmware file (e.g. "micropython-pico-w2.uf2")
        drive_path: Path to the BOOTSEL drive. If None, auto-detect.

    Returns:
        True on success, raises on failure.
    """
    uf2_path = Path(uf2_path)

    # Validate the .uf2 file exists
    if not uf2_path.exists():
        raise FileNotFoundError(
            f"UF2 file not found: {uf2_path}\n"
            f"\n"
            f"You need to download the MicroPython firmware for your Pico variant.\n"
            f"Get it from: https://micropython.org/download/\n"
            f"  - For Pico W 2: look for 'RPI_PICO2_W' or 'PICO2-W'\n"
            f"  - The file will be named something like: RPI_PICO2_W-v1.xx.x.uf2"
        )

    if not uf2_path.suffix.lower() == ".uf2":
        raise ValueError(
            f"File does not have .uf2 extension: {uf2_path}\n"
            f"Make sure you downloaded the correct firmware file."
        )

    # Find the BOOTSEL drive
    if drive_path is None:
        drive_path = find_bootsel_drive()
        if drive_path is None:
            raise RuntimeError(
                "No Pico in BOOTSEL mode detected.\n"
                "\n"
                "To put the Pico in BOOTSEL mode:\n"
                "  1. Unplug the Pico from USB.\n"
                "  2. Hold down the BOOTSEL button (small white button on the board).\n"
                "  3. While holding BOOTSEL, plug the USB cable back in.\n"
                "  4. Release the BOOTSEL button.\n"
                "\n"
                "The Pico should appear as a USB drive named 'RPI-RP2' or 'RP2350'.\n"
                "If it does not appear, try a different USB cable -- some cables are\n"
                "charge-only and do not carry data."
            )

    # Read board info before flashing (for display purposes)
    board_info = read_bootsel_info(drive_path)

    # The actual flash: copy the .uf2 file to the BOOTSEL drive.
    # shutil.copy2 preserves file metadata. The Pico's bootloader will
    # detect the new file and start writing it to flash memory.
    dest = Path(drive_path) / uf2_path.name
    shutil.copy2(str(uf2_path), str(dest))

    # After the copy completes, the Pico will automatically reboot.
    # The BOOTSEL drive will disappear (unmount) as the Pico restarts.
    # Give it a moment to start the reboot process.
    return {
        "uf2_file": str(uf2_path),
        "drive_path": drive_path,
        "board_info": board_info,
    }


def wait_for_serial_after_flash(timeout=15):
    """
    After flashing, wait for the Pico to reboot and appear as a serial device.

    The typical sequence after flashing MicroPython:
      1. .uf2 is copied to BOOTSEL drive (~2 seconds)
      2. Pico writes firmware to flash memory (~3 seconds)
      3. Pico reboots (~1 second)
      4. MicroPython starts and USB serial device appears (~2 seconds)

    Total: about 5-10 seconds.
    """
    # Import here to avoid circular imports
    from .serial_detect import list_pico_serial_ports

    start = time.time()
    while time.time() - start < timeout:
        picos = list_pico_serial_ports()
        if picos:
            return picos[0]["port"]
        time.sleep(1)

    return None
