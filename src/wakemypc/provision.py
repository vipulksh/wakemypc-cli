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
    Read secrets.json from Pico safely via serial REPL.

    This lets us preserve existing settings when updating only some fields.
    For example, if the user only wants to change the WiFi password, we can
    keep the existing server_url and device_token.

    Returns:
        A dict of the current secrets, or an empty dict if no secrets.json exists.

    """
    import json
    import time
    import serial

    ser = serial.Serial(port, baudrate, timeout=2)
    time.sleep(0.5)

    try:
        # Interrupt anything running
        ser.write(b"\r\x03\x03")
        time.sleep(0.2)
        ser.read(ser.in_waiting or 1)

        # Safe Python command with explicit marker
        cmd = (
            "import json\n"
            "try:\n"
            "    f = open('secrets.json')\n"
            "    data = json.loads(f.read())\n"
            "    f.close()\n"
            "    print('__SECRETS__:' + json.dumps(data))\n"
            "except Exception as e:\n"
            "    print('__SECRETS__:__NONE__')\n"
        )

        ser.write(cmd.encode() + b"\r\n")
        time.sleep(0.8)

        response = ser.read(ser.in_waiting or 4096).decode(errors="replace")

        for line in response.splitlines():
            line = line.strip()
            if line.startswith("__SECRETS__:"):
                payload = line.split("__SECRETS__:", 1)[1].strip()

                if payload == "__NONE__":
                    return {}

                try:
                    return json.loads(payload)
                except json.JSONDecodeError:
                    return {}

        return {}

    finally:
        ser.close()


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
    server_url=None,
    wifi_ssid=None,
    wifi_password=None,
    add_new_wifi=False,
    clear_wifi=False,
    device_token=None,
    merge_existing=True,
    remove_wifi=False,
    order=None,
):
    """
    High-level provisioning function: write configuration to a Pico.

    This is the main entry point for the 'wakemypc provision' command.

    Parameters:
        port:            Serial port path
        server_url:      URL of the server (required)
        wifi_ssid:       WiFi network name (optional if already configured)
        wifi_password:   WiFi password (optional if already configured)
        device_token:    Device authentication token (optional if already configured)
        merge_existing:  If True, keep existing settings that are not being overridden
        order:           Helpful when adding multiple WiFi networks over time. Networks with lower order values are tried first. If not provided, networks will be tried in the order they appear in the list.
        add_new_wifi:    If True, add the provided WiFi network to the existing list instead of replacing it
        clear_wifi:      If True, clear all existing WiFi networks from the config

    The function:
      1. Reads the device_id from the Pico's hardware.
      2. Optionally reads existing secrets.json to preserve unchanged settings.
      3. Builds the new secrets dict with provided and existing values.
      4. Writes the new secrets.json to the Pico.
    """
    # Step 1: Read the hardware device ID
    device_id = read_device_id(port)
    # Websocket endpoint path is based on device_id, e.g. "/ws/pico/e6614103.../"
    path = f"/ws/pico/{device_id}/"
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
    if add_new_wifi:
        secrets = {
            "device_id": device_id,
            "device_token": device_token or existing.get("device_token", ""),
            "server_url": server_url or existing.get("server_url", ""),
            "ws_endpoint": (server_url or existing.get("server_url", "")) + path,
            "wifi_networks": existing.get("wifi_networks", []),
        }
        if wifi_ssid and wifi_password:
            # Check if the SSID already exists in the list
            if any(net.get("ssid") == wifi_ssid for net in secrets["wifi_networks"]):
                # If it exists, update the password
                for net in secrets["wifi_networks"]:
                    if net.get("ssid") == wifi_ssid:
                        net["password"] = wifi_password
            else:
                # If it does not exist, add a new entry
                secrets["wifi_networks"].append(
                    {"ssid": wifi_ssid, "password": wifi_password, "order": order or 0}
                )
    elif clear_wifi:
        secrets = {
            "device_id": device_id,
            "device_token": device_token or existing.get("device_token", ""),
            "server_url": server_url or existing.get("server_url", ""),
            "ws_endpoint": (server_url or existing.get("server_url", "")) + path,
            "wifi_networks": [],
        }
        if wifi_ssid or wifi_password:
            if not (wifi_ssid and wifi_password):
                raise RuntimeError(
                    "To set a WiFi network when using --clear-wifi, you must provide both --wifi-ssid and --wifi-pass."
                )
            # If user provided new WiFi info, add it as the only network
            secrets["wifi_networks"] = [{
                "ssid": wifi_ssid,
                "password": wifi_password,
                "order": 0
            }]
    elif remove_wifi:
        if not wifi_ssid:
            raise RuntimeError(
                "To remove a WiFi network, you must specify the SSID with --wifi-ssid."
            )
        secrets = {
            "device_id": device_id,
            "device_token": device_token or existing.get("device_token", ""),
            "server_url": server_url or existing.get("server_url", ""),
            "ws_endpoint": (server_url or existing.get("server_url", "")) + path,
            "wifi_networks": [
                net for net in existing.get("wifi_networks", [])
                if net.get("ssid") != wifi_ssid
            ],
        }
    else:
        # Default behavior: replace WiFi config if new SSID/password provided, otherwise keep existing
        secrets = {
            "device_id": device_id,
            "device_token": device_token or existing.get("device_token", ""),
            "server_url": server_url or existing.get("server_url", ""),
            "ws_endpoint": (server_url or existing.get("server_url", "")) + path,
            "wifi_networks": (
                [{"ssid": wifi_ssid, "password": wifi_password, "order": order or 0}]
                if wifi_ssid and wifi_password
                else existing.get("wifi_networks", [])
            ),
        }
    # Step 4: Write to the Pico
    write_secrets(port, secrets)

    return {
        "device_id": device_id,
        "port": port,
        "secrets_written": {
            # only mask  after 4 letters of anything sensitive like passwords or tokens, e.g. "abc123..." becomes "abc1***"
            k: (f"{v[:4]}***" if "password" in k or "token" in k else v)
            for k, v in secrets.items()
        },
    }
