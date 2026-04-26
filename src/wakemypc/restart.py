"""
restart.py -- reboot a Pico via the MicroPython REPL
=====================================================

A Pico in normal mode runs MicroPython and exposes a serial REPL on
/dev/ttyACM* (or COM* on Windows). To restart it we just need to:

  1. Open the serial port.
  2. Send Ctrl-C twice to interrupt any program currently running.
     (The Pico's own main.py runs an infinite loop, so without this
     break the REPL prompt is unreachable.)
  3. Send `import machine; machine.reset()` and a newline.
  4. Close the port.

Within ~1 second the Pico reboots: USB enumeration drops and comes
back, MicroPython re-runs boot.py + main.py.

ALTERNATIVE -- machine.bootloader()
-----------------------------------
Replacing machine.reset() with machine.bootloader() reboots the Pico
straight into BOOTSEL mode (mass-storage drive). Useful when the user
wants to reflash without unplugging and holding the BOOTSEL button.
"""

import time

import serial


def restart_pico(port, into_bootloader=False, baudrate=115200, timeout=2.0):
    """
    Soft-reboot a Pico over its USB serial REPL.

    Args:
        port: serial device path (e.g. "/dev/ttyACM0").
        into_bootloader: if True, reboot into BOOTSEL / mass-storage mode
            instead of normal MicroPython mode. Handy for reflashing.
        baudrate: ignored by the Pico's USB CDC stack (it's USB, not UART)
            but still required by pyserial.
        timeout: how long to wait for the Pico to acknowledge before we
            give up and close the port.

    Returns nothing on success; raises serial.SerialException or OSError
    if the port can't be opened.
    """
    command = (
        b"import machine; machine.bootloader()\r\n"
        if into_bootloader
        else b"import machine; machine.reset()\r\n"
    )

    with serial.Serial(port, baudrate, timeout=timeout) as ser:
        # Settle: USB CDC needs a beat after open before bytes flow reliably.
        time.sleep(0.2)

        # Break out of any running program. \r flushes a partial line, then
        # two Ctrl-C in a row reliably interrupts even tight loops.
        ser.write(b"\r\x03\x03")
        time.sleep(0.2)
        # Drain whatever the REPL just printed so it doesn't bleed into our
        # next read; we don't actually care about the contents.
        if ser.in_waiting:
            ser.read(ser.in_waiting)

        ser.write(command)
        ser.flush()

        # Give the Pico a moment to start executing the reset() before we
        # close the port. Without this brief sleep the close() can race
        # the write and the command never lands.
        time.sleep(0.3)
