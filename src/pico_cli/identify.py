"""
identify.py -- Blink the Pico's LED for physical identification
================================================================

WHY YOU NEED THIS
-----------------
Imagine you have 5 Picos plugged into a USB hub, and your computer shows them as:
    /dev/ttyACM0
    /dev/ttyACM1
    /dev/ttyACM2
    /dev/ttyACM3
    /dev/ttyACM4

Which physical Pico is /dev/ttyACM2? They all look the same! You cannot tell
just by looking at them.

The "identify" command solves this: it tells a specific Pico to blink its LED
rapidly. Now you can look at your pile of Picos and see which one is blinking.
Then you can label it with a sticker or note its position.

HOW IT WORKS
------------
We send a small Python script to the Pico via the serial REPL (the interactive
Python prompt accessible over USB). The script:

  1. Imports the 'machine' module (MicroPython's hardware control library).
  2. Gets a reference to the onboard LED pin.
     - On Pico W / Pico W 2, the LED is connected to the WiFi chip, so we
       use the string "LED" instead of a pin number.
  3. Toggles the LED on and off rapidly in a loop.

The Pico W 2's onboard LED is a small green LED next to the USB connector.
It is not super bright, but it is visible enough to identify the device.

SERIAL REPL COMMUNICATION
--------------------------
The serial REPL is like having a Python terminal running on the Pico. When you
open a serial connection (like we do here), you can type Python code and the
Pico executes it immediately. This is the same thing that happens when you use
tools like Thonny, PuTTY, or 'screen' to talk to the Pico.

We use "raw REPL" mode (entered with Ctrl+A) for sending multi-line scripts.
In raw mode, there is no echo or prompt, making it easier for programs (vs humans)
to communicate with the Pico.
"""

import time

import serial


# The MicroPython script that runs ON THE PICO (not on your computer!).
# This script is sent over USB serial and executed by the Pico's MicroPython
# interpreter.
#
# Note: This code uses MicroPython APIs (machine.Pin, time.sleep) which are
# different from regular Python. These only work on the Pico, not on your computer.
BLINK_SCRIPT = """\
import machine
import time

# On Pico W and Pico W 2, the onboard LED is controlled via the WiFi chip,
# so we reference it by the string "LED" rather than a GPIO pin number.
# On the original Pico (non-W), the LED is on GPIO 25: machine.Pin(25, machine.Pin.OUT)
led = machine.Pin("LED", machine.Pin.OUT)

# Blink rapidly 20 times (takes about 4 seconds total).
# Each cycle: 100ms on + 100ms off = 200ms per blink.
for i in range(20):
    led.on()
    time.sleep(0.1)
    led.off()
    time.sleep(0.1)

# Leave the LED off when done
led.off()
print("IDENTIFY_DONE")
"""


def blink_led(port, duration_seconds=4, baudrate=115200):
    """
    Make a Pico's onboard LED blink rapidly for physical identification.

    Parameters:
        port:             Serial port path, e.g. "/dev/ttyACM0"
        duration_seconds: Approximate duration of blinking (not precise)
        baudrate:         Serial speed (115200 is standard for MicroPython)

    How it works:
        1. Open a serial connection to the Pico.
        2. Enter raw REPL mode (Ctrl+A) for clean script execution.
        3. Send the blink script.
        4. Wait for the script to finish.
        5. Return to normal REPL mode (Ctrl+B).

    The raw REPL protocol:
        - Ctrl+A (0x01): Enter raw REPL mode. Pico responds with "raw REPL; CTRL-B to exit"
        - Send Python code as plain text.
        - Ctrl+D (0x04): Execute the code. Pico responds with "OK" then output then Ctrl+D.
        - Ctrl+B (0x02): Exit raw REPL, return to normal interactive mode.
    """
    try:
        ser = serial.Serial(port, baudrate, timeout=2)
    except serial.SerialException as e:
        raise RuntimeError(
            f"Could not open serial port {port}: {e}\n"
            f"\n"
            f"Make sure:\n"
            f"  - The Pico is plugged in and has MicroPython installed\n"
            f"  - No other program (Thonny, screen, etc.) is using the port\n"
            f"  - You have permission to access the port (Linux: add yourself to 'dialout' group)"
        )

    time.sleep(0.5)

    # Interrupt any currently running program on the Pico.
    # Sending Ctrl+C (0x03) twice is the standard way to get back to the REPL
    # prompt, even if a program is in the middle of a time.sleep() or a loop.
    ser.write(b"\r\x03\x03")
    time.sleep(0.5)
    ser.read(ser.in_waiting)  # Discard any buffered output

    # Enter raw REPL mode.
    # Normal REPL: echoes what you type, has ">>> " prompt, auto-indents.
    # Raw REPL: no echo, no prompt, executes code blocks terminated by Ctrl+D.
    # Raw mode is better for programmatic use because we do not have to parse prompts.
    ser.write(b"\x01")  # Ctrl+A = enter raw REPL
    time.sleep(0.3)
    ser.read(ser.in_waiting)  # Read and discard the "raw REPL" banner

    # Calculate blink count based on desired duration.
    # Each blink cycle is ~200ms (100ms on + 100ms off).
    blink_count = max(5, int(duration_seconds / 0.2))

    # Build the script with the custom blink count
    script = (
        "import machine\n"
        "import time\n"
        'led = machine.Pin("LED", machine.Pin.OUT)\n'
        f"for i in range({blink_count}):\n"
        "    led.on()\n"
        "    time.sleep(0.1)\n"
        "    led.off()\n"
        "    time.sleep(0.1)\n"
        "led.off()\n"
        'print("IDENTIFY_DONE")\n'
    )

    # Send the script and execute it
    ser.write(script.encode())
    ser.write(b"\x04")  # Ctrl+D = execute the code

    # Wait for the blinking to finish.
    # The script takes approximately `duration_seconds` to complete.
    timeout = duration_seconds + 5  # Extra buffer for slow serial
    start = time.time()
    response = b""

    while time.time() - start < timeout:
        if ser.in_waiting:
            response += ser.read(ser.in_waiting)
            if b"IDENTIFY_DONE" in response:
                break
        time.sleep(0.1)

    # Exit raw REPL mode and return to normal mode
    ser.write(b"\x02")  # Ctrl+B = exit raw REPL
    time.sleep(0.2)
    ser.close()

    success = b"IDENTIFY_DONE" in response
    return {
        "port": port,
        "success": success,
        "duration": duration_seconds,
        "message": (
            f"LED on {port} blinked for ~{duration_seconds} seconds."
            if success
            else f"Blink command was sent to {port} but completion was not confirmed."
        ),
    }


def read_device_id_and_blink(port, baudrate=115200):
    """
    Read the device ID AND blink the LED, so the user can match ID to physical device.

    This is a convenience function that:
      1. Reads the Pico's unique hardware ID.
      2. Blinks the LED so you can see which physical Pico it is.
      3. Returns both the device ID and the port, so you can label the device.

    Typical usage:
        "I have 3 Picos. Let me identify each one."
        For each port, call this function. It will tell you:
        "Port /dev/ttyACM0 has device ID e660583883724a32 -- that's the one blinking now."
    """
    from .provision import read_device_id

    device_id = read_device_id(port)
    blink_result = blink_led(port)

    return {
        "port": port,
        "device_id": device_id,
        "blink_success": blink_result["success"],
        "message": (
            f"Device on {port} has ID: {device_id}\n"
            f"The LED is blinking now -- look for the flashing green light!"
        ),
    }
