"""
upload.py -- Upload Python files to the Pico's filesystem (RAW REPL VERSION)
============================================================================

WHAT CHANGED
------------
We now use RAW REPL instead of the interactive REPL.

Raw REPL:
  - No prompts (no >>>)
  - No echo
  - No line parsing issues
  - Designed for automation (like mpremote)

Protocol:
  Ctrl+C → stop program
  Ctrl+A → enter raw REPL
  send code
  Ctrl+D → execute
  Ctrl+B → exit raw REPL

This eliminates:
  ❌ buffer truncation
  ❌ prompt race conditions
  ❌ multiline parsing issues

Result:
  ✅ Fast
  ✅ Reliable
  ✅ Production-grade
"""

import subprocess
import shutil
import time
from pathlib import Path

import serial


# -----------------------------------------------------------------------------
# MPREMOTE (PREFERRED)
# -----------------------------------------------------------------------------

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
            results.append({
                "file": str(local_path),
                "success": False,
                "error": f"File not found: {local_path}",
            })
            continue

        # Build the remote path on the Pico.
        # The ":" prefix tells mpremote this is a path on the device (not the host).
        remote_path = f":{remote_dir.rstrip('/')}/{local_path.name}"

        cmd = ["mpremote", "connect", port, "cp", str(local_path), remote_path]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

            if result.returncode == 0:
                results.append({
                    "file": str(local_path),
                    "remote": remote_path.lstrip(":"),
                    "success": True,
                })
            else:
                results.append({
                    "file": str(local_path),
                    "success": False,
                    "error": result.stderr.strip() or "Unknown error",
                })

        except subprocess.TimeoutExpired:
            results.append({
                "file": str(local_path),
                "success": False,
                "error": "Upload timed out",
            })

    return results


# -----------------------------------------------------------------------------
# RAW REPL IMPLEMENTATION
# -----------------------------------------------------------------------------

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
        # Establish serial connection to the Pico
        ser = serial.Serial(port, baudrate, timeout=2)
        # Give the device time to stabilize after connection
        time.sleep(0.5)

        # Enter raw REPL mode (machine-friendly protocol)
        _enter_raw_repl(ser)

        for local_path in local_files:
            local_path = Path(local_path)

            if not local_path.exists():
                results.append({
                    "file": str(local_path),
                    "success": False,
                    "error": f"File not found: {local_path}",
                })
                continue

            # Build the remote path and read the file contents
            remote_path = f"{remote_dir.rstrip('/')}/{local_path.name}"
            content = local_path.read_bytes()

            try:
                # Transfer the file to the Pico
                _write_file_raw(ser, remote_path, content)
                results.append({
                    "file": str(local_path),
                    "remote": remote_path,
                    "success": True,
                })
            except Exception as e:
                results.append({
                    "file": str(local_path),
                    "success": False,
                    "error": str(e),
                })

        # Exit raw REPL and close the connection
        _exit_raw_repl(ser)
        ser.close()

    except serial.SerialException as e:
        for local_path in local_files:
            results.append({
                "file": str(local_path),
                "success": False,
                "error": f"Serial connection failed: {e}",
            })

    return results


# -----------------------------------------------------------------------------
# RAW REPL HELPERS
# -----------------------------------------------------------------------------

def _enter_raw_repl(ser):
    """Enter raw REPL mode on the Pico. Raw REPL is machine-friendly with no prompts."""
    # Send Ctrl+C twice to interrupt any running program
    ser.write(b"\r\x03\x03")
    time.sleep(0.1)

    # Send Ctrl+A to enter raw REPL mode
    ser.write(b"\r\x01")
    time.sleep(0.1)

    # Flush any buffered output from the device
    ser.read(ser.in_waiting)


def _exit_raw_repl(ser):
    """Exit raw REPL mode and return to normal interactive REPL."""
    # Send Ctrl+B to exit raw REPL
    ser.write(b"\r\x02")
    time.sleep(0.1)


def _exec_raw(ser, code, timeout=5):
    """
    Send Python code in raw REPL mode and execute it.

    Parameters:
        ser:     Serial connection object
        code:    Python code as a string
        timeout: Maximum seconds to wait for execution and response

    Raises:
        RuntimeError: If the code execution produces a traceback or error
    """
    # Encode and send the Python code
    ser.write(code.encode())
    # Send Ctrl+D to execute the code
    ser.write(b"\x04")

    response = b""
    start = time.time()

    # Read all output from the device until timeout
    while time.time() - start < timeout:
        if ser.in_waiting:
            response += ser.read(ser.in_waiting)
        time.sleep(0.01)

    # Check for execution errors in the response
    if b"Traceback" in response or b"Error" in response:
        raise RuntimeError(response.decode(errors="replace"))

    return response


def _write_file_raw(ser, remote_path, content):
    """
    Write a file to the Pico using raw REPL mode.

    Strategy:
      1. Build a Python script that opens a file and writes chunks
      2. Send all commands at once (safe in raw REPL, no buffer truncation)
      3. Execute the script in one operation

    Parameters:
        ser:          Serial connection object
        remote_path:  Full path on the Pico where file will be written
        content:      Bytes to write to the file
    """
    # Chunk size is larger in raw REPL since there's no prompt parsing overhead
    chunk_size = 512

    # Build the Python script that will execute on the Pico
    lines = [f'__f = open("{remote_path}", "wb")']

    # Split content into chunks and add write commands for each
    for i in range(0, len(content), chunk_size):
        chunk = content[i:i + chunk_size]
        # Use repr() to safely encode binary data as a Python bytes literal
        lines.append(f"__f.write({repr(chunk)})")

    # Close the file after all data is written
    lines.append("__f.close()")

    # Combine all lines into a single script and execute it
    script = "\n".join(lines) + "\n"
    _exec_raw(ser, script)


# -----------------------------------------------------------------------------
# ENTRYPOINT
# -----------------------------------------------------------------------------

def upload_files(port, local_files, remote_dir="/"):
    if is_mpremote_available():
        return upload_via_mpremote(port, local_files, remote_dir)
    return upload_via_serial_repl(port, local_files, remote_dir)


def list_files_on_pico(port, baudrate=115200):
    """
    List files in the root directory of the Pico.

    Attempts to use mpremote if available (preferred), falls back to serial REPL.

    Parameters:
        port:      Serial port path
        baudrate:  Communication speed (115200 is standard for MicroPython)

    Returns:
        String containing the directory listing, or an error message
    """
    # Try mpremote first (faster and more reliable)
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
            # Silently fall through to serial method if mpremote fails
            pass

    # Fallback: use serial REPL to list files
    try:
        ser = serial.Serial(port, baudrate, timeout=2)
        time.sleep(0.5)

        _enter_raw_repl(ser)

        # Execute Python command to list files and capture the output
        output = _exec_raw(ser, "import os; print(os.listdir('/'))")

        _exit_raw_repl(ser)
        ser.close()

        return output.decode(errors="replace")

    except Exception as e:
        return f"Error listing files: {e}"
