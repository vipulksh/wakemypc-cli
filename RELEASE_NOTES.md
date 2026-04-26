## v1.0.4 — pyserial DTR/RTS API fix (v1.0.3 was broken)

**Hotfix for v1.0.3.** v1.0.3 passed `dtr=False, rts=False` as
constructor kwargs to `serial.Serial(...)`. pyserial does not accept
those as constructor arguments — it raises `ValueError: unexpected
keyword arguments: {'dtr': False, 'rts': False}` and `wakemypc logs`
crashed on startup. Anyone who upgraded to v1.0.3 should upgrade
straight to v1.0.4.

The supported pattern is:

```python
ser = serial.Serial()
ser.port = port
ser.baudrate = 115200
ser.timeout = 0.5
ser.dtr = False
ser.rts = False
ser.open()
```

Properties set on an unopened `Serial()` instance determine the
initial state of the DTR/RTS lines when `.open()` is called. v1.0.4
uses this pattern.

Same intent as v1.0.3 — DTR/RTS are held low so opening the serial
port can no longer pulse the rp2 USB CDC stack and interrupt the
booting Pico. The post-reconnect grace delay is still 3s, the
`--catch-up` flag and `_recover_log_buffer_after_reconnect` are still
gone. Only the API call shape changed.

## v1.0.3 — Stop interrupting the Pico after OTA (broken; use v1.0.4)

**Bug fix.** `wakemypc logs` was the actual cause of the "Pico stuck
after OTA" loop that we chased through firmware v0.3.2 -> v0.3.4. With
no logs streamer attached, post-OTA reboots worked correctly even on
v0.3.2. With the streamer attached, two things broke the boot:

1. `serial.Serial(port, ...)` was opened with pyserial's defaults,
   which assert DTR and RTS on open. On the rp2 USB CDC stack that
   pulse is enough to interrupt MicroPython startup before main.py
   runs, leaving the firmware parked in REPL with no WiFi.

2. The `--catch-up` / post-reconnect flow called
   `_recover_log_buffer_after_reconnect`, which sent a literal Ctrl+D
   (`\x04`) over serial to soft-reset and resume the firmware. In
   MicroPython REPL terms Ctrl+D is "soft reset and reload main.py" --
   it does NOT cycle the CYW43 chip. After OTA, the chip stayed in
   its previous association state and the new firmware couldn't
   re-associate. Same end result: stuck.

**What changed in v1.0.3:**

- Every `serial.Serial(...)` open in `wakemypc logs` now passes
  `dtr=False, rts=False` so opening the port can no longer pulse the
  Pico's USB lines. (NOTE: this API call is invalid on stock pyserial
  and crashes on startup — see v1.0.4 for the correct shape.)
- The post-reconnect grace delay was bumped from 500ms to 3s so
  MicroPython has clear runway to finish boot.py + main.py before the
  host attaches.
- `_recover_log_buffer_after_reconnect` and the `--catch-up` flag are
  removed entirely. The function's whole purpose was to pull the
  in-RAM `log_buffer` after a reset, but the buffer is wiped by the
  hard reset machine.reset() actually performs, so the dump was
  always empty after a real reboot anyway. Net loss: we no longer
  recover boot logs that printed before this command attached. Net
  gain: the firmware is no longer interrupted.

**Apply:**

```
pip install --upgrade wakemypc
```

(or `pip install -e /home/vipul/wakemypc-cli` from a checkout)

After the upgrade, run `wakemypc logs` while triggering an OTA. The
post-OTA boot should reconnect to WiFi within ~3s and live-stream
should resume cleanly.

The matching firmware release v0.3.5 keeps the v0.3.3/v0.3.4 chip
defenses as belt-and-suspenders and adds a small post-`machine.reset`
settling delay so older v1.0.2 CLI builds also stop breaking the boot.
