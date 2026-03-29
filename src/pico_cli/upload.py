"""
upload.py -- Upload Python files to the Pico's filesystem
==========================================================

THE PICO HAS TWO SEPARATE STORAGE AREAS
----------------------------------------
This is a common source of confusion, so let's be very clear:

  1. FIRMWARE (flash memory):
     - This is where MicroPython itself lives.
     - Installed via .uf2 file in BOOTSEL mode (see flash.py).
     - You do NOT touch this when uploading your application code.

  2. FILESYSTEM (internal file system):
     - This is a small filesystem (~800KB on Pico W 2) on top of the flash.
     - This is where YOUR Python scripts live (main.py, secrets.json, etc.).
     - MicroPython automatically runs main.py on boot (if it exists).
     - You upload files here via serial connection (USB cable, normal mode).

Think of it like a computer: the firmware is like Windows/macOS/Linux, and the
filesystem is like your Documents folder where your own files live.

HOW mpremote WORKS
------------------
mpremote is the official tool from the MicroPython project for managing Pico devices.
It communicates over the USB serial connection (the same connection you would use
to type Python commands manually).

mpremote can:
  - Copy files to/from the Pico:  mpremote cp local_file.py :remote_file.py
  - Run a script on the Pico:     mpremote run script.py
  - List files on the Pico:       mpremote ls
  - Enter the REPL:               mpremote repl
  - Reset the Pico:               mpremote reset

The colon (:) prefix means "on the Pico". So ":main.py" means the file called
main.py on the Pico's filesystem.

FALLBACK: SERIAL REPL
----------------------
If mpremote is not installed, we fall back to sending raw Python commands over
the serial REPL (Read-Eval-Print Loop). This is slower and more fragile, but
works without any extra tools.

The REPL is like a Python interactive shell running on the Pico. You type
Python code, the Pico executes it, and sends back the result. We use this to
write files by sending commands like:

    f = open("main.py", "w")
    f.write("print('hello')")
    f.close()
"""

import subprocess
import shutil
import time
from pathlib import Path

import serial


def is_mpremote_available():
    """
    Check if mpremote is installed on this computer.

    mpremote is a pip-installable tool:  pip install mpremote
    It is the recommended way to manage MicroPython devices.
    """
    return shutil.which("mpremote") is not None


def upload_via_mpremote(port, local_files, remote_dir="/"):
    """
    Upload files to the Pico using mpremote (the preferred method).

    Parameters:
        port:        Serial port path, e.g. "/dev/ttyACM0"
        local_files: List of local file paths to upload
        remote_dir:  Directory on the Pico to upload into (default: root "/")

    How it works:
        mpremote connects to the Pico's serial port, enters raw REPL mode
        (a machine-friendly protocol), and transfers the file contents.
        It is much more reliable than manually sending data over the REPL.
    """
    results = []

    for local_path in local_files:
        local_path = Path(local_path)
        if not local_path.exists():
            results.append(
                {
                    "file": str(local_path),
                    "success": False,
                    "error": f"File not found: {local_path}",
                }
            )
            continue

        # The remote path on the Pico.
        # ":" prefix tells mpremote this is a path on the device.
        remote_path = f":{remote_dir.rstrip('/')}/{local_path.name}"

        cmd = ["mpremote", "connect", port, "cp", str(local_path), remote_path]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                results.append(
                    {
                        "file": str(local_path),
                        "remote": remote_path.lstrip(":"),
                        "success": True,
                    }
                )
            else:
                results.append(
                    {
                        "file": str(local_path),
                        "success": False,
                        "error": result.stderr.strip() or "Unknown error",
                    }
                )
        except subprocess.TimeoutExpired:
            results.append(
                {
                    "file": str(local_path),
                    "success": False,
                    "error": "Upload timed out after 30 seconds",
                }
            )
        except FileNotFoundError:
            results.append(
                {
                    "file": str(local_path),
                    "success": False,
                    "error": "mpremote not found. Install it with: pip install mpremote",
                }
            )

    return results


def upload_via_serial_repl(port, local_files, remote_dir="/", baudrate=115200):
    """
    Upload files to the Pico by sending Python commands over the serial REPL.

    This is the fallback method when mpremote is not available. It works by:
      1. Opening a serial connection to the Pico (same as plugging in and opening
         a terminal program like PuTTY or screen).
      2. Sending raw Python commands that create and write files.

    It is slower and less reliable than mpremote because:
      - We have to encode file contents carefully (escaping special characters).
      - Large files must be sent in chunks to avoid buffer overflows.
      - The serial connection can be finicky with timing.

    Parameters:
        port:      Serial port path, e.g. "/dev/ttyACM0"
        local_files: List of local file paths to upload
        remote_dir:  Directory on the Pico (default: root "/")
        baudrate:  Serial communication speed (115200 is standard for MicroPython)
    """
    results = []

    try:
        # Open the serial connection.
        # Think of this like opening a chat window with the Pico.
        ser = serial.Serial(port, baudrate, timeout=2)
        time.sleep(0.5)  # Give the connection a moment to stabilize

        # Interrupt any running program on the Pico by sending Ctrl+C.
        # This drops us into the interactive Python prompt (>>>).
        ser.write(b"\r\x03\x03")
        time.sleep(0.5)
        ser.read(ser.in_waiting)  # Clear the input buffer

        for local_path in local_files:
            local_path = Path(local_path)
            if not local_path.exists():
                results.append(
                    {
                        "file": str(local_path),
                        "success": False,
                        "error": f"File not found: {local_path}",
                    }
                )
                continue

            remote_path = f"{remote_dir.rstrip('/')}/{local_path.name}"
            content = local_path.read_text()

            try:
                _write_file_via_repl(ser, remote_path, content)
                results.append(
                    {
                        "file": str(local_path),
                        "remote": remote_path,
                        "success": True,
                    }
                )
            except Exception as e:
                results.append(
                    {
                        "file": str(local_path),
                        "success": False,
                        "error": str(e),
                    }
                )

        ser.close()

    except serial.SerialException as e:
        # If we cannot even open the serial port, all files fail
        for local_path in local_files:
            results.append(
                {
                    "file": str(local_path),
                    "success": False,
                    "error": f"Serial connection failed: {e}",
                }
            )

    return results


def _write_file_via_repl(ser, remote_path, content):
    """
    Write a single file to the Pico by sending Python commands over serial.

    We send commands like:
        f = open("/main.py", "w")
        f.write("...chunk of content...")
        f.write("...next chunk...")
        f.close()

    The content is sent in small chunks (256 bytes) to avoid overflowing the
    Pico's serial input buffer. After each command, we wait briefly for the
    Pico to process it.
    """
    # Open the file for writing on the Pico
    _send_repl_command(ser, f'__f = open("{remote_path}", "w")')

    # Send content in chunks to avoid buffer overflow.
    # The Pico's serial input buffer is limited (usually 256-512 bytes),
    # so we must not send too much data at once.
    chunk_size = 256
    for i in range(0, len(content), chunk_size):
        chunk = content[i : i + chunk_size]
        # Escape backslashes and quotes so the Python string is valid
        escaped = (
            chunk.replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("\n", "\\n")
            .replace("\r", "\\r")
        )
        _send_repl_command(ser, f'__f.write("{escaped}")')

    # Close the file
    _send_repl_command(ser, "__f.close()")
    _send_repl_command(ser, "del __f")


def _send_repl_command(ser, command, timeout=3):
    """
    Send a single Python command to the Pico's REPL and wait for the prompt.

    The REPL works like this:
      1. We send a line of Python code followed by Enter (\\r\\n).
      2. The Pico executes it.
      3. The Pico sends back any output, followed by the ">>> " prompt.
      4. We wait until we see ">>> " to know the command finished.
    """
    ser.write(command.encode() + b"\r\n")
    time.sleep(0.1)

    # Read the response and wait for the prompt
    response = b""
    start = time.time()
    while time.time() - start < timeout:
        if ser.in_waiting:
            response += ser.read(ser.in_waiting)
            if b">>> " in response:
                break
        time.sleep(0.05)

    # Check for errors in the response
    if b"Traceback" in response or b"Error" in response:
        raise RuntimeError(f"REPL error: {response.decode(errors='replace')}")

    return response.decode(errors="replace")


def upload_files(port, local_files, remote_dir="/"):
    """
    Upload files to the Pico, using the best available method.

    Tries mpremote first (faster, more reliable), falls back to serial REPL.
    """
    if is_mpremote_available():
        return upload_via_mpremote(port, local_files, remote_dir)
    else:
        return upload_via_serial_repl(port, local_files, remote_dir)


def list_files_on_pico(port, baudrate=115200):
    """
    List files on the Pico's filesystem.

    Uses mpremote if available, otherwise falls back to serial REPL.
    """
    if is_mpremote_available():
        try:
            result = subprocess.run(
                ["mpremote", "connect", port, "ls"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.stdout.strip()
        except Exception:
            pass

    # Fallback: use REPL to list files
    try:
        ser = serial.Serial(port, baudrate, timeout=2)
        time.sleep(0.5)
        ser.write(b"\r\x03\x03")
        time.sleep(0.5)
        ser.read(ser.in_waiting)

        output = _send_repl_command(ser, "import os; print(os.listdir('/'))")
        ser.close()
        return output
    except Exception as e:
        return f"Error listing files: {e}"
