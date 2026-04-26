## v1.0.1

**`wakemypc logs` improvements:**
- **Reboot recovery.** When the Pico hardware-resets (OTA, watchdog,
  USB blip), the CLI now waits up to 10 seconds for the serial port
  to reappear and resumes streaming automatically -- no more crash on
  every reboot.
- **Boot log recovery on reconnect.** When the port comes back, the
  CLI briefly mpremote-execs into the Pico to dump
  `log_buffer.get_dump()` (the firmware's in-RAM ring buffer of recent
  print() output, captured even while USB CDC was down). Recovered
  lines are printed with relative timestamps. Then a Ctrl+D over
  serial soft-resets main.py to resume normal operation.
  Requires firmware v0.2.0+.
- **`--debug` verbosity flag.** Default mode hides high-frequency
  output (heartbeat metrics, per-probe scanner timing, per-message
  dispatch). Pass `--debug` for the full firehose.

**`wakemypc upload` improvements:**
- `--firmware-dir` auto-falls-through to a `src/` subdirectory if the
  given path has no `.py` files. So `wakemypc upload --firmware-dir
  ./pico_firmware/` works without knowing the internal layout.

**Install / upgrade:**
```
pip install --upgrade git+https://github.com/vipulksh/wakemypc-cli.git
```
