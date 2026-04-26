"""
main.py -- Click-based CLI for managing Raspberry Pi Pico W 2 devices
======================================================================

WHAT THIS TOOL DOES
--------------------
This is a command-line tool that runs on YOUR COMPUTER (not on the Pico).
It helps you set up and manage Raspberry Pi Pico W 2 transmitter devices
by communicating with them over USB.

Think of it like a setup wizard: you plug in a Pico, run these commands,
and the Pico is configured and ready to transmit data.

THE SETUP WORKFLOW
------------------
Here is the typical order of operations for a brand new Pico:

  1. pico-cli flash --uf2 firmware.uf2
     Install MicroPython on the Pico. You only do this once (or when updating).
     The Pico must be in BOOTSEL mode (hold button while plugging in).

  2. pico-cli detect
     Verify the Pico is detected on a serial port after flashing.

  3. pico-cli upload --firmware-dir ./pico_firmware/
     Upload your application Python files to the Pico's filesystem.

  4. pico-cli provision --server-url https://example.com --wifi-ssid MyNetwork --wifi-pass secret
     Write WiFi credentials and server URL to the Pico's secrets.json.

  5. pico-cli register --api-url https://example.com --username admin --password pass
     Register the Pico on the server and get a device_token written to it.

  6. pico-cli identify
     Blink the LED to verify which physical Pico you just configured.

After these steps, unplug the Pico and plug it into a power source.
It will boot, connect to WiFi, and start sending data to your server.

HOW USB SERIAL DETECTION WORKS
-------------------------------
When you plug a Pico into your computer via USB, the operating system creates
a "serial port" for it. On Linux this is typically /dev/ttyACM0, on macOS it is
/dev/cu.usbmodem..., and on Windows it is COM3 or higher.

We detect Picos by looking at the USB Vendor ID (VID) and Product ID (PID).
Raspberry Pi's VID is 0x2E8A. If a serial port has this VID, it is a Pico.

WHAT IS BOOTSEL MODE?
---------------------
BOOTSEL = "Boot Select". It is a special mode where the Pico appears as a USB
flash drive instead of a serial device. You enter it by holding the BOOTSEL
button (small white button on the board) while plugging in the USB cable.

In BOOTSEL mode, you can copy a .uf2 firmware file to the drive, and the Pico
will install it and reboot. This is how you install or update MicroPython.

HOW mpremote COPIES FILES
--------------------------
mpremote is the official MicroPython tool for managing devices over serial.
When you run 'pico-cli upload', we use mpremote to copy Python files from your
computer to the Pico's tiny internal filesystem. mpremote connects to the serial
port, enters a special "raw REPL" mode, and transfers file data efficiently.

If mpremote is not installed, we fall back to sending Python commands directly
over the serial connection to write files (slower but works without extra tools).

HOW REGISTRATION WORKS
-----------------------
Registration is how the server learns about a new Pico:

  1. You provide your server login credentials (username + password).
  2. This tool logs into the server and gets a JWT (temporary access token).
  3. The tool reads the Pico's unique hardware ID via USB.
  4. It sends the hardware ID to the server's API to register the device.
  5. The server creates a device record and returns a device_token.
  6. The tool writes the device_token to the Pico's secrets.json file.

Now the Pico can authenticate with the server using its device_token.

ABOUT CLICK
-----------
Click is a Python library for building command-line interfaces. It turns
Python functions into CLI commands using decorators (@click.command, etc.).
Each function becomes a subcommand like 'pico-cli detect' or 'pico-cli flash'.
"""

import sys
from pathlib import Path

import click


@click.group()
@click.version_option(version="1.0.0", prog_name="pico-cli")
def cli():
    """
    CLI tool to flash, provision, and register Raspberry Pi Pico W 2 transmitters.

    This tool runs on your computer and communicates with Pico devices over USB.
    Use --help on any subcommand for details (e.g. pico-cli flash --help).
    """
    pass


# ---------------------------------------------------------------------------
# DETECT -- List connected Pico devices
# ---------------------------------------------------------------------------


@cli.command()
def detect():
    """
    List every Pico plugged in -- flashed AND unflashed.

    Scans for two states in one pass:
      - FLASHED:   Pico is running MicroPython, shows up as a USB serial port.
      - UNFLASHED: Pico is in BOOTSEL mode, shows up as a USB mass-storage drive.
                   Use 'pico-cli flash --uf2 <file>' to install MicroPython on it.

    Each device printed includes a status badge so you know exactly which step
    to take next.
    """
    from .serial_detect import list_all_picos

    click.echo("Scanning for Raspberry Pi Pico devices...")
    picos = list_all_picos()

    if not picos:
        click.echo("\nNo Pico devices found.")
        click.echo("\nTroubleshooting:")
        click.echo("  - Is the Pico plugged in via USB?")
        click.echo("  - To flash MicroPython, hold BOOTSEL while plugging in.")
        click.echo("  - On Linux you may need: sudo usermod -a -G dialout $USER")
        click.echo("    (then log out and back in for it to take effect.)")
        sys.exit(1)

    flashed = [p for p in picos if p["state"] == "flashed"]
    unflashed = [p for p in picos if p["state"] == "unflashed"]

    summary = []
    if flashed:
        summary.append(f"{len(flashed)} flashed")
    if unflashed:
        summary.append(f"{len(unflashed)} unflashed")
    click.echo(f"\nFound {len(picos)} Pico(s) -- {', '.join(summary)}:\n")

    for p in flashed:
        click.echo(click.style("  [FLASHED]   ", fg="green", bold=True), nl=False)
        click.echo(f"running MicroPython on {p['port']}")
        click.echo(f"              Description: {p['description']}")
        click.echo(f"              VID:PID:     {p['vid']:#06x}:{p['pid']:#06x}")
        click.echo(f"              Serial:      {p['serial']}")
        click.echo()

    for p in unflashed:
        click.echo(click.style("  [UNFLASHED] ", fg="yellow", bold=True), nl=False)
        click.echo(f"BOOTSEL mode at {p['mount_path']}")
        click.echo(f"              Model:    {p['model']}")
        click.echo(f"              Board ID: {p['board_id']}")
        click.echo(
            "              Next step: pico-cli flash --uf2 <path-to-firmware.uf2>"
        )
        click.echo()


# ---------------------------------------------------------------------------
# FLASH -- Flash MicroPython firmware to a Pico in BOOTSEL mode
# ---------------------------------------------------------------------------


@cli.command()
@click.option(
    "--uf2",
    type=click.Path(exists=True),
    help="Path to the .uf2 MicroPython firmware file. Download from https://micropython.org/download/",
)
def flash(uf2):
    """
    Flash MicroPython firmware to a Pico in BOOTSEL mode.

    The Pico must be in BOOTSEL mode for this to work. To enter BOOTSEL:
      1. Unplug the Pico from USB.
      2. Hold the BOOTSEL button (small white button on the board).
      3. Plug the USB cable back in while holding the button.
      4. Release the button.

    The Pico should appear as a USB drive named 'RPI-RP2' or 'RP2350'.
    This command copies the .uf2 file to that drive, which installs the firmware.
    """
    from .flash import find_bootsel_drive, flash_uf2, wait_for_serial_after_flash

    if uf2 is None:
        # If no .uf2 file specified, just check if BOOTSEL drive is present
        drive = find_bootsel_drive()
        if drive:
            click.echo(f"Pico in BOOTSEL mode detected at: {drive}")
            click.echo("\nTo flash MicroPython, run:")
            click.echo("  pico-cli flash --uf2 <path-to-firmware.uf2>")
            click.echo("\nDownload firmware from: https://micropython.org/download/")
            click.echo("  For Pico W 2, look for 'RPI_PICO2_W'")
        else:
            click.echo("No Pico in BOOTSEL mode detected.")
            click.echo("\nTo enter BOOTSEL mode:")
            click.echo("  1. Unplug the Pico")
            click.echo("  2. Hold the BOOTSEL button")
            click.echo("  3. Plug USB back in while holding the button")
            click.echo("  4. Release the button")
            sys.exit(1)
        return

    click.echo(f"Flashing firmware: {uf2}")
    try:
        result = flash_uf2(uf2)
        click.echo(f"Firmware copied to {result['drive_path']}")
        click.echo("\nBoard info:")
        for line in result["board_info"].strip().split("\n"):
            click.echo(f"  {line}")
        click.echo("\nThe Pico is rebooting with new firmware...")
        click.echo("Waiting for serial port to appear...")

        port = wait_for_serial_after_flash(timeout=15)
        if port:
            click.echo(f"\nSuccess! Pico is now running MicroPython on {port}")
            click.echo("Next step: upload your firmware files with 'pico-cli upload'")
        else:
            click.echo("\nPico did not appear as a serial device within 15 seconds.")
            click.echo(
                "It may still be booting. Try 'pico-cli detect' in a few seconds."
            )
    except Exception as e:
        click.echo(f"\nError: {e}", err=True)
        sys.exit(1)


# ---------------------------------------------------------------------------
# UPLOAD -- Upload .py files to the Pico's filesystem
# ---------------------------------------------------------------------------


@cli.command()
@click.option(
    "--port",
    default=None,
    help="Serial port of the Pico (e.g. /dev/ttyACM0). Auto-detected if not specified.",
)
@click.option(
    "--firmware-dir",
    type=click.Path(exists=True),
    default=None,
    help="Directory containing .py files to upload to the Pico.",
)
@click.argument("files", nargs=-1, type=click.Path(exists=True))
def upload(port, firmware_dir, files):
    """
    Upload Python files to the Pico's filesystem.

    You can specify individual files or a directory containing .py files:

      pico-cli upload main.py config.py

      pico-cli upload --firmware-dir ./pico_firmware/

    The files are uploaded to the root of the Pico's filesystem. The Pico
    runs main.py automatically on boot, so make sure that file exists.

    Uses mpremote if installed (recommended: pip install mpremote), otherwise
    falls back to slower serial REPL transfer.
    """
    from .serial_detect import get_single_pico_port
    from .upload import upload_files, is_mpremote_available

    # Resolve the port
    try:
        port = get_single_pico_port(port)
    except RuntimeError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    # Collect files to upload
    file_list = list(files)
    if firmware_dir:
        firmware_path = Path(firmware_dir)
        py_files = sorted(firmware_path.glob("*.py"))
        if not py_files:
            click.echo(f"No .py files found in {firmware_dir}", err=True)
            sys.exit(1)
        file_list.extend(str(f) for f in py_files)

    if not file_list:
        click.echo(
            "No files specified. Use --firmware-dir or pass file paths.", err=True
        )
        click.echo("Example: pico-cli upload --firmware-dir ./pico_firmware/")
        sys.exit(1)

    # Show transfer method
    if is_mpremote_available():
        click.echo("Using mpremote for file transfer (fast, reliable)")
    else:
        click.echo("mpremote not found, using serial REPL fallback (slower)")
        click.echo("Tip: install mpremote for faster transfers: pip install mpremote")

    click.echo(f"\nUploading {len(file_list)} file(s) to Pico on {port}...\n")

    results = upload_files(port, file_list)

    success_count = sum(1 for r in results if r["success"])
    fail_count = len(results) - success_count

    for r in results:
        if r["success"]:
            click.echo(f"  OK   {r['file']} -> {r.get('remote', '?')}")
        else:
            click.echo(f"  FAIL {r['file']}: {r['error']}")

    click.echo(f"\nUploaded: {success_count}  Failed: {fail_count}")

    if fail_count > 0:
        sys.exit(1)
    else:
        click.echo(
            "\nNext step: provision with 'pico-cli provision' or register with 'pico-cli register'"
        )


# ---------------------------------------------------------------------------
# PROVISION -- Write secrets.json config to the Pico
# ---------------------------------------------------------------------------


@cli.command(context_settings=dict(help_option_names=["-h", "--help"]))
@click.option(
    "--server-url",
    required=False,
    help="URL of your Django server (e.g. https://example.com)",
)
@click.option("-a", "--add-new-wifi", required=False, is_flag=True, help="Add new WiFi network instead of replacing existing ones")
@click.option("-c", "--clear-wifi", required=False, is_flag=True, help="Clear all existing WiFi networks from config")
@click.option("-r", "--remove-wifi", required=False, is_flag=True, help="Remove existing WiFi networks (use with --wifi-ssid to specify which one to remove)")
@click.option("--wifi-ssid", help="WiFi network name (SSID)")
@click.option("--wifi-pass", help="WiFi password")
@click.option(
    "--port", default=None, help="Serial port (auto-detected if not specified)"
)
@click.option("--order", required=False, type=int, help="Order value for the WiFi network (lower is tried first)")
def provision(server_url, wifi_ssid, wifi_pass, port, add_new_wifi, clear_wifi, remove_wifi, order):
    """
    Write WiFi and server configuration to the Pico's secrets.json.

    This writes a secrets.json file to the Pico containing the WiFi credentials
    and server URL. The Pico reads this file on boot to know how to connect.

    If the Pico already has a secrets.json, existing values are preserved
    unless you explicitly override them with flags.

    Examples:

      First-time setup (all fields required):
        pico-cli provision --server-url https://example.com --add-new-wifi --wifi-ssid MyNetwork --wifi-pass secret123

      Update just the server URL (keep existing WiFi):
        pico-cli provision --server-url https://new-server.com
        
        Add a new WiFi network without removing existing ones:
        pico-cli provision --add-new-wifi --wifi-ssid AnotherNetwork --wifi-pass anotherpass --order 1
        pico-cli provision -a --wifi-ssid AnotherNetwork --wifi-pass anotherpass --order 1
        (The --order flag is optional but can be used to control the priority of WiFi networks)

        Clear all WiFi networks and set a new one:
        pico-cli provision --clear-wifi --wifi-ssid FreshNetwork --wifi-pass freshpass
        pico-cli provision -c --wifi-ssid FreshNetwork --wifi-pass freshpass

        Clear all WiFi networks without adding a new one:
        pico-cli provision --clear-wifi
        pico-cli provision -c

        Remove a specific WiFi network:
        pico-cli provision --remove-wifi --wifi-ssid NetworkToRemove
        pico-cli provision -r --wifi-ssid NetworkToRemove

    Notes: 
     - You can run this command multiple times to update the configuration as needed.
     - If you change the server URL, make sure to also update it on the server side if necessary.
     - If you change WiFi credentials, the Pico will use the new ones on next boot.
     """
    from .serial_detect import get_single_pico_port
    from .provision import provision_pico

    
    # If user runs without required args → show help instead of error
    if not (
        server_url
        or (add_new_wifi and wifi_ssid and wifi_pass)
        or clear_wifi
        or (remove_wifi and wifi_ssid)
    ):
        click.echo("\nMissing required options.\n")
        click.echo(click.get_current_context().get_help())
        sys.exit(1)
    # Validate incompatible options
    if add_new_wifi and clear_wifi:
        click.echo("\nCannot use --add-new-wifi and --clear-wifi together.\n")
        click.echo(click.get_current_context().get_help())
        sys.exit(1)
    if remove_wifi and clear_wifi:
        click.echo("\nCannot use --remove-wifi and --clear-wifi together.\n")
        click.echo(click.get_current_context().get_help())
        sys.exit(1)
    if remove_wifi and not wifi_ssid:
        click.echo("\nTo remove a WiFi network, you must specify the SSID with --wifi-ssid.\n")
        click.echo(click.get_current_context().get_help())
        sys.exit(1)
    if order is not None and not add_new_wifi:
        click.echo("\nThe --order option can only be used when adding a new WiFi network with --add-new-wifi.\n")
        click.echo(click.get_current_context().get_help())
        sys.exit(1)
    try:
        port = get_single_pico_port(port)
    except RuntimeError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    click.echo(f"Provisioning Pico on {port}...")

    try:
        result = provision_pico(
            port=port,
            server_url=server_url,
            wifi_ssid=wifi_ssid,
            wifi_password=wifi_pass,
            add_new_wifi=add_new_wifi,
            clear_wifi=clear_wifi,
            remove_wifi=remove_wifi,
            order=order,
        )
        click.echo(f"\nDevice ID: {result['device_id']}")
        click.echo(f"Port:      {result['port']}")
        click.echo("\nConfiguration written to secrets.json:")
        for key, value in result["secrets_written"].items():
            # For sensitive fields, we show a masked or summarized version instead of the raw value
            if key in ["server_url", 
                       "device_id", 
                       "wifi_networks", 
                       "device_token"]:
                display_value = value
                if key == "device_token":
                    display_value = value[:8] + "..." if value != "" else "not set"
                elif key == "wifi_networks":
                    # Dispaly only the SSIDs and orders of the configured WiFi networks, not the passwords
                    display_value = [
                        f"{net['ssid']} (order: {net.get('order', 0)})"
                        for net in value
                    ] if value else "not set"
                else:
                    display_value = value or "not set"
                click.echo(f"  {key}: {display_value}")
        click.echo("\nProvisioning complete!")
        click.echo("Next step: register with 'pico-cli register' to get a device_token")
    except RuntimeError as e:
        click.echo(f"\nError: {e}", err=True)
        sys.exit(1)


# ---------------------------------------------------------------------------
# REGISTER -- Register the Pico on the Django server
# ---------------------------------------------------------------------------


@cli.command()
@click.option(
    "--api-url",
    required=True,
    help="Base URL of your Django server (e.g. https://example.com)",
)
@click.option("--username", required=True, help="Your Django server username")
@click.option(
    "--password",
    required=True,
    prompt=True,
    hide_input=True,
    help="Your Django server password",
)
@click.option(
    "--port", default=None, help="Serial port (auto-detected if not specified)"
)
@click.option(
    "--name",
    default=None,
    help="Human-friendly name for this Pico (e.g. 'Kitchen Sensor')",
)
def register(api_url, username, password, port, name):
    """
    Register this Pico on the Django server and get a device_token.

    This command:

        1. Logs into the server with your credentials.

        2. Reads the Pico's unique hardware ID.

        3. Registers the device on the server.

        4. Writes the device_token back to the Pico's secrets.json.

    After registration, the Pico can authenticate with the server
    to send sensor data.

    Example usage:

    pico-cli register --api-url https://example.com --username admin --password pass

    pico-cli register --api-url https://example.com --username admin --password pass --name "Kitchen Sensor"
    """
    from .serial_detect import get_single_pico_port
    from .register import register_and_provision

    try:
        port = get_single_pico_port(port)
    except RuntimeError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    click.echo(f"Registering Pico on {port} with server {api_url}...")

    try:
        result = register_and_provision(
            api_url=api_url,
            username=username,
            password=password,
            port=port,
            device_name=name,
        )
        click.echo(f"\n{'=' * 60}")
        click.echo("Device registered successfully!")
        click.echo(f"{'=' * 60}")
        click.echo(f"\n  Device ID:    {result['device_id']}")
        click.echo(f"  Device Token: {result['device_token']}")
        click.echo(f"  Port:         {result['port']}")
        click.echo(f"\n{'=' * 60}")
        click.echo("SAVE THE DEVICE TOKEN ABOVE -- it is shown only once!")
        click.echo(f"{'=' * 60}")
        click.echo("\nThe token has also been written to the Pico's secrets.json.")
        click.echo(
            "The Pico is now ready. Plug it into a power source to start transmitting."
        )
    except RuntimeError as e:
        click.echo(f"\nError: {e}", err=True)
        sys.exit(1)


# ---------------------------------------------------------------------------
# IDENTIFY -- Blink LED for physical identification
# ---------------------------------------------------------------------------


@cli.command()
@click.option(
    "--port", default=None, help="Serial port (auto-detected if not specified)"
)
@click.option(
    "--duration", default=4, type=int, help="How long to blink in seconds (default: 4)"
)
def identify(port, duration):
    """
    Blink the Pico's onboard LED rapidly for physical identification.

    When you have multiple Picos and need to know which physical device
    corresponds to which serial port, use this command. The LED will blink
    rapidly so you can spot which Pico it is.

    You can then label the physical device with its port name or device ID.

    Example:
      pico-cli identify                       # auto-detect single Pico
      pico-cli identify --port /dev/ttyACM0   # identify a specific Pico
      pico-cli identify --duration 10         # blink for 10 seconds
    """
    from .serial_detect import get_single_pico_port
    from .identify import read_device_id_and_blink

    try:
        port = get_single_pico_port(port)
    except RuntimeError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    click.echo(f"Identifying Pico on {port}...")
    click.echo(f"Watch for the blinking LED! (blinking for ~{duration} seconds)")

    try:
        result = read_device_id_and_blink(port)
        click.echo(f"\n{result['message']}")
        click.echo(f"\nYou can label this device as: {result['device_id']}")
    except RuntimeError as e:
        click.echo(f"\nError: {e}", err=True)
        sys.exit(1)


# ---------------------------------------------------------------------------
# STATUS -- Show current Pico status (config, WiFi, server connection)
# ---------------------------------------------------------------------------


@cli.command()
@click.option(
    "--port", default=None, help="Serial port (auto-detected if not specified)"
)
def status(port):
    """
    Show current Pico status: config, WiFi connection, and server info.

    This connects to the Pico over USB serial and reads:
      - The device's unique hardware ID
      - WiFi connection status and IP address
      - Server URL and device token (masked) from secrets.json
      - Free memory and firmware info

    Useful for debugging connection issues. If WiFi shows "not connected",
    check your WiFi credentials with 'pico-cli provision'. If the server
    URL is wrong, update it with 'pico-cli provision --server-url ...'.

    HOW THIS WORKS UNDER THE HOOD
    ------------------------------
    This command opens the Pico's USB serial port and sends raw Python
    commands to the MicroPython REPL (Read-Eval-Print Loop). MicroPython
    executes the commands and prints the output, which we capture and
    parse. This is the same mechanism that Thonny IDE uses to interact
    with MicroPython devices.
    """
    import json
    import time
    import serial

    from .serial_detect import get_single_pico_port

    try:
        port = get_single_pico_port(port)
    except RuntimeError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    click.echo(f"Reading status from Pico on {port}...\n")

    try:
        # Open serial connection to the Pico's MicroPython REPL.
        # 115200 baud is the default for MicroPython on Pico.
        # timeout=2 means read() will wait up to 2 seconds for data.
        ser = serial.Serial(port, 115200, timeout=2)
        time.sleep(0.5)  # Wait for REPL to be ready after connection

        def run_command(cmd):
            """
            Send a Python command to the MicroPython REPL and capture output.

            We send Ctrl+C first to interrupt any running program, then
            send the command followed by Enter. The REPL executes it and
            prints the result, which we read back from the serial port.
            """
            # Interrupt any running program (Ctrl+C)
            ser.write(b"\x03")
            time.sleep(0.1)
            ser.read(ser.in_waiting or 1)  # Clear buffer

            # Send the command
            ser.write(cmd.encode() + b"\r\n")
            time.sleep(0.5)

            # Read response
            response = ser.read(ser.in_waiting or 1024).decode(errors="replace")
            return response

        # --- Read device ID ---
        click.echo("Device Info:")
        click.echo("-" * 40)
        response = run_command("import machine; print(machine.unique_id().hex())")
        # Parse the device ID from the REPL output
        for line in response.strip().split("\n"):
            line = line.strip()
            if line and not line.startswith(">>>") and "import" not in line:
                click.echo(f"  Unique ID:    {line}")
                break

        # --- Read free memory ---
        response = run_command("import gc; gc.collect(); print(gc.mem_free())")
        for line in response.strip().split("\n"):
            line = line.strip()
            if line.isdigit():
                click.echo(f"  Free RAM:     {int(line):,} bytes")
                break

        # --- Read CPU frequency ---
        response = run_command("import machine; print(machine.freq())")
        for line in response.strip().split("\n"):
            line = line.strip()
            if line.isdigit():
                click.echo(f"  CPU Freq:     {int(line) // 1_000_000} MHz")
                break

        # --- Read WiFi status ---
        click.echo(f"\nWiFi Status:")
        click.echo("-" * 40)

        response = run_command(
            "import network, json; "
            "w = network.WLAN(network.STA_IF); "
            "print('__JSON__:' + json.dumps({"
            "'active': w.active(), "
            "'connected': w.isconnected(), "
            "'ifconfig': w.ifconfig()"
            "}))"
        )

        data = None

        for line in response.splitlines():
            line = line.strip()
            if line.startswith("__JSON__:"):
                try:
                    payload = line.split("__JSON__:", 1)[1]
                    data = json.loads(payload)
                except Exception:
                    data = None
                break

        if not data:
            click.echo("  WiFi: unable to read status")
            click.echo("  Raw output:")
            for l in response.splitlines():
                click.echo(f"    {l}")
        else:
            click.echo(f"  Active:       {'Yes' if data['active'] else 'No'}")
            click.echo(f"  Connected:    {'Yes' if data['connected'] else 'No'}")

            if data["active"] and data["connected"]:
                ip, subnet, gateway, dns = data["ifconfig"]
                click.echo(f"  IP Address:   {ip}")
                click.echo(f"  Subnet:       {subnet}")
                click.echo(f"  Gateway:      {gateway}")
                click.echo(f"  DNS:          {dns}")
        # --- Read secrets.json (masked) ---
        click.echo(f"\nServer Config:")
        click.echo("-" * 40)
        response = run_command(
            "import json; f=open('secrets.json','r'); c=json.load(f); f.close(); "
            "print(json.dumps(c))"
        )
        for line in response.strip().split("\n"):
            line = line.strip()
            if line.startswith("{"):
                try:
                    config = json.loads(line)
                    click.echo(f"  Server URL:   {config.get('server_url', 'not set')}")
                    token = config.get("device_token", "")
                    if token:
                        # Mask the token for security (show first 8 chars only)
                        click.echo(f"  Device Token: {token[:8]}...{'*' * 20}")
                    else:
                        click.echo("  Device Token: not set")
                    wifi = config.get("wifi_networks", config.get("wifi_ssid", "not set"))
                    if isinstance(wifi, list):
                        click.echo(f"  WiFi Networks: {len(wifi)} configured")
                    else:
                        click.echo(f"  WiFi SSID:    {wifi}")
                except json.JSONDecodeError:
                    click.echo("  Could not parse secrets.json")
                break
        else:
            click.echo("  secrets.json: not found (run pico-cli provision)")

        ser.close()
        click.echo(f"\n{'=' * 40}")
        click.echo("Status read complete.")

    except serial.SerialException as e:
        click.echo(f"\nSerial error: {e}", err=True)
        click.echo("Make sure no other program (Thonny, etc.) has the port open.")
        sys.exit(1)
    except Exception as e:
        click.echo(f"\nError: {e}", err=True)
        sys.exit(1)


# Entry point: this is what runs when you type 'pico-cli' on the command line.
# The pyproject.toml maps 'pico-cli' -> 'pico_cli.main:cli', so this function
# is called directly.
if __name__ == "__main__":
    cli()
