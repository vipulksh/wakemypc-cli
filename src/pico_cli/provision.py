"""
provision.py -- Write secrets.json configuration to the Pico
=============================================================

WHAT IS PROVISIONING?
---------------------
"Provisioning" means configuring a device with the information it needs to operate.
For our Pico transmitters, this means writing a secrets.json file that contains:

  {
      "wifi_ssid": "MyHomeNetwork",        <-- WiFi network name to connect to
      "wifi_password": "MyWiFiPassword123", <-- WiFi password
      "server_url": "https://example.com",  <-- URL of your Django server
      "device_token": "abc123...",           <-- Authentication token for the server
      "device_id": "e6614103..."            <-- Unique hardware ID of this Pico
  }

Without this file, the Pico cannot:
  - Connect to WiFi (it does not know which network or password)
  - Send data to your server (it does not know where the server is)
  - Authenticate with the server (it has no token)

WHAT IS device_id?
------------------
Every Pico has a globally unique hardware identifier burned into the chip at the
factory. It is like a serial number that can never be changed.

In MicroPython, you read it with:
    import machine
    machine.unique_id()  # Returns bytes like b'\\xe6\\x61\\x41\\x03...'

We convert this to a hex string (e.g. "e6614103...") and use it as the device_id.
This is what identifies a specific physical Pico on the server.

HOW WE WRITE TO THE PICO
-------------------------
We use the serial REPL (see upload.py for explanation) to send Python commands
that write the secrets.json file. The process:

  1. Connect to the Pico via USB serial.
  2. Send Ctrl+C to interrupt any running program and get to the REPL prompt.
  3. Send Python commands to write the JSON file.
  4. Optionally, read back the device_id from the hardware.
"""

import json
import time

import serial


def read_device_id(port, baudrate=115200):
    """
    Read the Pico's unique hardware ID via serial REPL.

    This sends a Python command to the Pico that reads the hardware ID from
    the RP2350 chip and prints it as a hex string.

    The unique_id is 8 bytes (16 hex characters) burned into the chip at the
    factory. It cannot be changed and is globally unique -- no two Picos in
    the world have the same ID.

    Parameters:
        port:     Serial port path, e.g. "/dev/ttyACM0"
        baudrate: Serial speed (115200 is standard for MicroPython)

    Returns:
        The device ID as a hex string, e.g. "e660583883724a32"
    """
    ser = serial.Serial(port, baudrate, timeout=2)
    time.sleep(0.5)

    # Interrupt any running program (Ctrl+C twice to be sure)
    ser.write(b"\r\x03\x03")
    time.sleep(0.5)
    ser.read(ser.in_waiting)  # Clear buffer

    # Send the command to read the unique ID.
    # machine.unique_id() returns raw bytes, so we convert to hex for readability.
    # The "DEVID:" prefix helps us find the result in the serial output.
    command = (
        "import machine; "
        "uid = machine.unique_id(); "
        'print("DEVID:" + "".join("{:02x}".format(b) for b in uid))'
    )
    ser.write(command.encode() + b"\r\n")
    time.sleep(1)

    # Read the response and extract the device ID
    response = ser.read(ser.in_waiting).decode(errors="replace")
    ser.close()

    # Parse the response to find our DEVID: marker
    for line in response.split("\n"):
        line = line.strip()
        if line.startswith("DEVID:"):
            return line.split("DEVID:")[1].strip()

    raise RuntimeError(
        f"Could not read device ID from Pico.\n"
        f"Serial response was:\n{response}\n"
        f"\n"
        f"Make sure MicroPython is installed and the Pico is not in BOOTSEL mode."
    )


def read_current_secrets(port, baudrate=115200):
    """
    Read the current secrets.json from the Pico (if it exists).

    This lets us preserve existing settings when updating only some fields.
    For example, if the user only wants to change the WiFi password, we can
    keep the existing server_url and device_token.

    Returns:
        A dict of the current secrets, or an empty dict if no secrets.json exists.
    """
    ser = serial.Serial(port, baudrate, timeout=2)
    time.sleep(0.5)

    ser.write(b"\r\x03\x03")
    time.sleep(0.5)
    ser.read(ser.in_waiting)

    # Try to read the file. If it does not exist, we catch the error.
    command = (
        "try:\n"
        '    f = open("secrets.json", "r")\n'
        "    data = f.read()\n"
        "    f.close()\n"
        '    print("SECRETS:" + data)\n'
        "except:\n"
        '    print("SECRETS:__NONE__")\n'
    )
    # Use raw REPL mode (Ctrl+A) for multi-line commands
    ser.write(b"\x01")  # Enter raw REPL mode (Ctrl+A)
    time.sleep(0.2)
    ser.read(ser.in_waiting)

    ser.write(command.encode() + b"\x04")  # Ctrl+D to execute
    time.sleep(1)

    response = ser.read(ser.in_waiting).decode(errors="replace")

    # Exit raw REPL mode
    ser.write(b"\x02")  # Ctrl+B to return to normal REPL
    time.sleep(0.2)
    ser.close()

    # Parse the response
    for line in response.split("\n"):
        line = line.strip()
        if line.startswith("SECRETS:"):
            payload = line.split("SECRETS:", 1)[1]
            if payload == "__NONE__":
                return {}
            try:
                return json.loads(payload)
            except json.JSONDecodeError:
                return {}

    return {}


def write_secrets(port, secrets_dict, baudrate=115200):
    """
    Write a secrets.json file to the Pico's filesystem via serial REPL.

    Parameters:
        port:         Serial port path, e.g. "/dev/ttyACM0"
        secrets_dict: Dictionary to serialize as JSON and write to the Pico.
                      Expected keys: wifi_ssid, wifi_password, server_url,
                      device_token, device_id
        baudrate:     Serial speed

    The file is written to the root of the Pico's filesystem as "secrets.json".
    The Pico's main.py firmware reads this file on boot to get its configuration.
    """
    # Convert the dict to a pretty-printed JSON string.
    # Pretty-printing makes it easier to debug if you read the file manually.
    json_str = json.dumps(secrets_dict, indent=2)

    ser = serial.Serial(port, baudrate, timeout=2)
    time.sleep(0.5)

    ser.write(b"\r\x03\x03")
    time.sleep(0.5)
    ser.read(ser.in_waiting)

    # Use raw REPL mode for reliable multi-line execution.
    # Raw REPL (Ctrl+A) is a machine-friendly mode where:
    #   - You send Python code, terminated by Ctrl+D
    #   - The Pico executes it and sends output followed by Ctrl+D
    #   - There is no echo, no prompt, no auto-indent -- just clean I/O
    ser.write(b"\x01")  # Enter raw REPL
    time.sleep(0.2)
    ser.read(ser.in_waiting)

    # Escape the JSON string for embedding in a Python string literal.
    escaped_json = (
        json_str.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    )

    command = (
        f'f = open("secrets.json", "w")\n'
        f'f.write("{escaped_json}")\n'
        f"f.close()\n"
        f'print("WRITE_OK")\n'
    )

    ser.write(command.encode() + b"\x04")  # Ctrl+D to execute
    time.sleep(1)

    response = ser.read(ser.in_waiting).decode(errors="replace")

    # Exit raw REPL
    ser.write(b"\x02")  # Ctrl+B
    time.sleep(0.2)
    ser.close()

    if "WRITE_OK" in response:
        return True

    raise RuntimeError(
        f"Failed to write secrets.json to Pico.\n"
        f"Serial response was:\n{response}\n"
        f"\n"
        f"Make sure the Pico is running MicroPython and is not in BOOTSEL mode."
    )


def provision_pico(
    port,
    server_url,
    wifi_ssid=None,
    wifi_password=None,
    device_token=None,
    merge_existing=True,
):
    """
    High-level provisioning function: write configuration to a Pico.

    This is the main entry point for the 'pico-cli provision' command.

    Parameters:
        port:            Serial port path
        server_url:      URL of the Django server (required)
        wifi_ssid:       WiFi network name (optional if already configured)
        wifi_password:   WiFi password (optional if already configured)
        device_token:    Device authentication token (optional if already configured)
        merge_existing:  If True, keep existing settings that are not being overridden

    The function:
      1. Reads the device_id from the Pico's hardware.
      2. Optionally reads existing secrets.json to preserve unchanged settings.
      3. Builds the new secrets dict with provided and existing values.
      4. Writes the new secrets.json to the Pico.
    """
    # Step 1: Read the hardware device ID
    device_id = read_device_id(port)

    # Step 2: Optionally read existing secrets to merge with
    existing = {}
    if merge_existing:
        try:
            existing = read_current_secrets(port)
        except Exception:
            # If we cannot read existing secrets, start fresh
            existing = {}

    # Step 3: Build the new secrets dictionary.
    # For each field, use the provided value if given, otherwise fall back
    # to the existing value, otherwise use a placeholder.
    secrets = {
        "device_id": device_id,
        "server_url": server_url,
        "wifi_ssid": wifi_ssid or existing.get("wifi_ssid", ""),
        "wifi_password": wifi_password or existing.get("wifi_password", ""),
        "device_token": device_token or existing.get("device_token", ""),
    }

    # Validate that we have the minimum required configuration
    missing = []
    if not secrets["wifi_ssid"]:
        missing.append("wifi_ssid (use --wifi-ssid)")
    if not secrets["wifi_password"]:
        missing.append("wifi_password (use --wifi-pass)")

    if missing and not existing:
        raise RuntimeError(
            "Missing required configuration:\n"
            + "\n".join(f"  - {m}" for m in missing)
            + "\n\nThese are required for the Pico to connect to WiFi."
        )

    # Step 4: Write to the Pico
    write_secrets(port, secrets)

    return {
        "device_id": device_id,
        "port": port,
        "secrets_written": {
            k: ("***" if "password" in k or "token" in k else v)
            for k, v in secrets.items()
        },
    }
